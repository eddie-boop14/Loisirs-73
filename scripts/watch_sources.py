#!/usr/bin/env python3
"""watch_sources.py — détection-only watcher for official source pages.

Generic tool (CLAUDIUS-VERDICT: detection autonomous, correction human-gated);
client #1 = the 28 stations' pass-price pages. It NEVER writes a fiche — it
fetches each pinned URL, extracts the price-bearing text region, diffs it
against the last run's snapshot, and writes a report. A CHANGED row is a job
for the report→verify→apply lane with human eyes.

Doctrine: watchers detect, humans apply — no exceptions.

Manifest: data/watch-sources.json
  {"watches": [{"slug", "url", "label", "manual": bool, "anchor": regex|null}]}
  manual:true = page is JS-only/unfetchable — checked by hand (Jan pass),
  skipped here and listed as MANUAL rather than faking coverage.
  anchor = optional regex narrowing which text lines are price-bearing.

Snapshots: reports/watch/<slug>.txt — normalized (whitespace-stable) price
lines from the previous run, committed so runs diff against real history.

Report: reports/<report-name>-<date>.md — one row per station, three states
(unchanged / CHANGED with diff / FETCH_FAILED) + MANUAL rows. Self-check
« show your witness »: every fetched row prints its URL + a matched text
snippet — no counting at unproven addresses. FETCH_FAILED ≠ price change:
an error is never data and never overwrites a snapshot.

Exit codes:
  0  nothing changed
  2  ≥1 CHANGED row (the actionable signal)
  1  circuit breaker — ≥10 % of fetched rows FETCH_FAILED (a mass failure is
     a fact about the fetcher, not about prices), or manifest broken.
     No retry, ever (doctrine du 1er juillet).

Usage:
  python3 scripts/watch_sources.py --date 2026-09-01 [--report-name watch-station-tarifs]
                                   [--dry-run] [--only SLUG]
  --dry-run writes the report but leaves snapshots untouched.
"""
import argparse
import siteconfig  # HANDOFF-73 phase 5: per-site identity
import difflib
import hashlib
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "data", "watch-sources.json")
SNAP_DIR = os.path.join(ROOT, "reports", "watch")
UA = (f"Mozilla/5.0 (compatible; {siteconfig.WORDMARK}-watch/1.0; "
      f"+{siteconfig.BASE_URL}) source-change-detector")
TIMEOUT = 30
BREAKER_PCT = 10  # ≥10 % FETCH_FAILED → run fails loud

EURO_LINE = re.compile(r"\d+(?:[.,]\d+)?\s*€|€\s*\d+(?:[.,]\d+)?")
TAG = re.compile(r"<(script|style|noscript)\b.*?</\1\s*>|<[^>]+>", re.S | re.I)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Language": "fr"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", errors="replace")


def price_lines(html, anchor=None):
    """Normalized price-bearing lines. Whitespace-stable so cosmetic HTML
    churn doesn't cry wolf; numbers are kept — they ARE the signal. Falls
    back to a single full-text fingerprint line when a page shows no € in
    static HTML (a redesign or unlock still moves it)."""
    text = TAG.sub(" ", html)
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    keep = re.compile(anchor) if anchor else None
    hits = [ln for ln in lines if ln and (EURO_LINE.search(ln)
                                          or (keep and keep.search(ln)))]
    if hits:
        return hits
    digest = hashlib.sha256(
        re.sub(r"\s+", " ", text).strip().encode("utf-8")).hexdigest()
    return [f"<no €-line in static HTML — full-text fingerprint sha256:{digest}>"]


def snap_path(slug):
    return os.path.join(SNAP_DIR, f"{slug}.txt")


def read_snap(slug):
    p = snap_path(slug)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return f.read().splitlines()


def write_snap(slug, lines):
    os.makedirs(SNAP_DIR, exist_ok=True)
    with open(snap_path(slug), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYY-MM-DD run stamp (never guessed)")
    ap.add_argument("--report-name", default="watch-sources")
    ap.add_argument("--dry-run", action="store_true",
                    help="write the report but leave snapshots untouched")
    ap.add_argument("--only", help="restrict to one slug (debug)")
    args = ap.parse_args()

    try:
        with open(MANIFEST, encoding="utf-8") as f:
            watches = json.load(f)["watches"]
        assert isinstance(watches, list) and watches
    except Exception as e:  # noqa: BLE001 — manifest broken = loud stop
        sys.exit(f"[watch] FAIL: unreadable manifest {MANIFEST}: {e}")

    rows = []  # (state, slug, url, witness, diff_lines)
    n_fetched = n_failed = 0
    for w in watches:
        slug, url = w.get("slug"), w.get("url")
        if args.only and slug != args.only:
            continue
        if not slug or not url:
            rows.append(("FETCH_FAILED", slug or "?", url or "?",
                         "manifest row missing slug/url", []))
            n_fetched += 1
            n_failed += 1
            continue
        if w.get("manual"):
            rows.append(("MANUAL", slug, url,
                         "page JS-only/unfetchable — checked by hand", []))
            continue
        n_fetched += 1
        try:
            fresh = price_lines(fetch(url), w.get("anchor"))
        except Exception as e:  # noqa: BLE001 — no retry; error is never data
            rows.append(("FETCH_FAILED", slug, url, f"{type(e).__name__}: {e}", []))
            n_failed += 1
            continue
        old = read_snap(slug)
        witness = fresh[0][:160]
        if old is None:
            rows.append(("SEEDED", slug, url, witness, []))
        elif old == fresh:
            rows.append(("unchanged", slug, url, witness, []))
        else:
            diff = list(difflib.unified_diff(old, fresh, "previous", "current",
                                             lineterm="", n=0))
            rows.append(("CHANGED", slug, url, witness, diff))
        if not args.dry_run:
            write_snap(slug, fresh)

    counts = {}
    for st, *_ in rows:
        counts[st] = counts.get(st, 0) + 1
    changed = counts.get("CHANGED", 0)
    breaker = n_fetched and (100 * n_failed / n_fetched) >= BREAKER_PCT

    # report — every row shows its witness (URL + matched snippet)
    L = [f"# Watch sources — {args.report_name} · {args.date}\n\n",
         f"- rows: **{len(rows)}** — unchanged {counts.get('unchanged', 0)} · "
         f"CHANGED {changed} · seeded {counts.get('SEEDED', 0)} · "
         f"FETCH_FAILED {n_failed} · MANUAL {counts.get('MANUAL', 0)}\n",
         f"- circuit breaker (≥{BREAKER_PCT}% failed): "
         f"{'**TRIPPED — run failed loud, snapshots of failed rows untouched**' if breaker else 'armed, not tripped'}\n",
         "- doctrine : *watchers detect, humans apply — no exceptions.* "
         "FETCH_FAILED ≠ price change; a CHANGED row goes to the "
         "report→verify→apply lane with human eyes.\n\n"]
    order = {"CHANGED": 0, "FETCH_FAILED": 1, "SEEDED": 2, "MANUAL": 3, "unchanged": 4}
    for st, slug, url, witness, diff in sorted(rows, key=lambda r: (order[r[0]], r[1])):
        L.append(f"## `{slug}` — {st}\n{url}\n\n> {witness}\n\n")
        if diff:
            L.append("```diff\n" + "\n".join(diff) + "\n```\n\n")
    report = os.path.join(ROOT, "reports", f"{args.report_name}-{args.date}.md")
    os.makedirs(os.path.dirname(report), exist_ok=True)
    with open(report, "w", encoding="utf-8") as f:
        f.write("".join(L))

    print(f"[watch] {counts.get('unchanged', 0)} unchanged · {changed} CHANGED · "
          f"{counts.get('SEEDED', 0)} seeded · {n_failed} FETCH_FAILED · "
          f"{counts.get('MANUAL', 0)} MANUAL → {os.path.relpath(report, ROOT)}")
    for st, slug, url, witness, _ in rows:
        if st in ("CHANGED", "FETCH_FAILED"):
            print(f"  {st:12} {slug}  {url}  — {witness}",
                  file=sys.stderr if st == "FETCH_FAILED" else sys.stdout)
    if breaker:
        print(f"[watch] CIRCUIT BREAKER: {n_failed}/{n_fetched} fetches failed "
              f"(≥{BREAKER_PCT}%) — mass failure is a fact about the fetcher. "
              "Exit 1, no retry.", file=sys.stderr)
        sys.exit(1)
    sys.exit(2 if changed else 0)


if __name__ == "__main__":
    main()
