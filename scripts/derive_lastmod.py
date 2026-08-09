#!/usr/bin/env python3
"""derive_lastmod.py — HANDOFF lastmod. Honest per-lieu <lastmod>, derived once.

The problem: sitemap.xml stamped 4,434 URLs the same build date because the
existing git-date logic credits the last NON-BOUNDARY commit that touched a
fiche — and a corpus-wide i18n backfill (one commit touching 389 Json files)
is non-boundary, so it stamped nearly every page the same day. That is the
uniform-stamp anti-pattern in a new disguise.

Semantic rule (the whole point):
    "Mis à jour" = the lieu's DATA was last MEANINGFULLY edited.
    A cross-cutting sweep — a mass i18n backfill, a reserialize, a schema
    migration — touches many lieux at once and is NOT a per-lieu editorial
    change. It must not reset every page's freshness to one date. A commit
    that touches more than BULK_MAX lieux in one shot is therefore treated as
    such a sweep and skipped when dating a lieu; the lieu keeps the date of its
    last genuinely targeted edit (winter batches of ~22-25 files still count).
    Builder/template/chrome changes (footer, CSS) never touch Json, so by
    construction they never bump a lieu date either.

Derived once → data/lastmod.json  {slug: "YYYY-MM-DD"}. Committed so builds are
deterministic and need no git history at render time. Three consumers read it:
the visible "Mis à jour le jj/mm/aa" stamp, schema.org dateModified (ISO), and
the sitemap <lastmod> (ISO).

    --report   print oldest/newest + drift vs date_modified_human. No write.
    --write    write data/lastmod.json (default action).
    --verify   fail if manifest missing/short/uniform (anti-pattern tripwire).

Requires FULL git history — a shallow clone silently dates everything to the
boundary commit. Aborts with a clear error if the repo is shallow.
"""
import argparse
import collections
import datetime
import glob
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_DIR = os.path.join(ROOT, "Json")
MANIFEST = os.path.join(ROOT, "data", "lastmod.json")

# A commit touching more than this many Json files in one shot is a corpus-wide
# sweep (i18n backfill, reserialize, migration), not a per-lieu edit. The
# largest legit *targeted* editorial batch observed is the winter JOB B commits
# (~22-25 files); the i18n backfill was 389. 50 sits cleanly between them.
BULK_MAX = 50


def _is_shallow():
    r = subprocess.run(["git", "rev-parse", "--is-shallow-repository"],
                       cwd=ROOT, capture_output=True, text=True)
    return r.stdout.strip() == "true"


def _history():
    """Single git pass → (commit_json_count, per-slug ordered commit list newest-first,
    commit_date). Only commits touching Json/ are considered."""
    res = subprocess.run(
        ["git", "log", "--format=COMMIT %H %cs", "--name-only", "--", "Json/"],
        cwd=ROOT, capture_output=True, text=True, check=True)
    cdate = {}
    njson = collections.Counter()
    slug_commits = collections.defaultdict(list)
    commit = None
    for line in res.stdout.splitlines():
        if line.startswith("COMMIT "):
            sha, date = line[len("COMMIT "):].strip().split(" ", 1)
            commit = sha
            cdate[sha] = date
        elif line.startswith("Json/") and line.endswith(".json"):
            slug = line[len("Json/"):-len(".json")]
            njson[commit] += 1
            slug_commits[slug].append(commit)
    return cdate, njson, slug_commits


def derive():
    """{slug: 'YYYY-MM-DD'} for every current Json file, skipping bulk sweeps."""
    cdate, njson, slug_commits = _history()
    live = {os.path.basename(p)[:-5] for p in glob.glob(os.path.join(JSON_DIR, "*.json"))}
    out = {}
    for slug in sorted(live):
        commits = slug_commits.get(slug)
        if not commits:
            continue  # no git history at all (shouldn't happen post-unshallow)
        # newest commit that is NOT a corpus-wide sweep
        for c in commits:
            if njson[c] <= BULK_MAX:
                out[slug] = cdate[c]
                break
        else:
            # every commit touching this slug was a sweep → its creation
            # (oldest) commit is the only honest floor we have
            out[slug] = cdate[commits[-1]]
    return out


def _human_field(slug):
    try:
        d = json.load(open(os.path.join(JSON_DIR, slug + ".json"), encoding="utf-8"))
    except Exception:
        return ""
    return ((d.get("i18n") or {}).get("fr") or {}).get("facts", {}).get("date_modified_human") \
        or d.get("date_modified_human", "")


def cmd_report():
    m = derive()
    items = sorted(m.items(), key=lambda kv: kv[1])
    dist = collections.Counter(m.values())
    top_date, top_n = dist.most_common(1)[0]
    drift = sum(1 for s in m)  # placeholder; compute real drift below
    drift = 0
    for s in m:
        hv = _human_field(s)
        if hv and hv[:10] != m[s]:
            drift += 1
    print(f"[lastmod] {len(m)} lieux · {len(dist)} distinct dates · "
          f"top {top_date} = {top_n} ({100 * top_n // max(len(m), 1)}%)")
    print(f"[lastmod] {drift} lieux differ from their manual date_modified_human")
    print("  — 20 OLDEST —")
    for s, dt in items[:20]:
        print(f"    {dt}  {s}")
    print("  — 20 NEWEST —")
    for s, dt in items[-20:]:
        print(f"    {dt}  {s}")
    if len(dist) < 15 or top_n > 0.40 * len(m):
        print("[lastmod] ⚠ WOULD FAIL --verify: too few distinct dates or a date "
              "covers >40% — derivation is not honest.")


def cmd_write():
    m = derive()
    os.makedirs(os.path.dirname(MANIFEST), exist_ok=True)
    with open(MANIFEST, "w", encoding="utf-8") as fh:
        json.dump({k: m[k] for k in sorted(m)}, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    dist = collections.Counter(m.values())
    print(f"[lastmod] wrote {len(m)} entries · {len(dist)} distinct dates → "
          f"{os.path.relpath(MANIFEST, ROOT)}")


def cmd_verify():
    if not os.path.exists(MANIFEST):
        sys.exit("[lastmod] FAIL: data/lastmod.json missing — run derive_lastmod.py --write")
    m = json.load(open(MANIFEST, encoding="utf-8"))
    live = {os.path.basename(p)[:-5] for p in glob.glob(os.path.join(JSON_DIR, "*.json"))}
    problems = []
    missing = live - set(m)
    if missing:
        problems.append(f"{len(missing)} live lieux missing from manifest: {sorted(missing)[:5]}")
    iso = datetime.date.fromisoformat
    for s, dt in m.items():
        try:
            iso(dt)
        except Exception:
            problems.append(f"{s}: non-ISO date {dt!r}")
    dist = collections.Counter(m.values())
    if len(dist) < 15:
        problems.append(f"only {len(dist)} distinct dates (<15) — derivation looks uniform")
    if dist:
        top_date, top_n = dist.most_common(1)[0]
        if top_n > 0.40 * len(m):
            problems.append(f"date {top_date} covers {top_n}/{len(m)} lieux "
                            f"({100 * top_n // len(m)}%) > 40% — anti-pattern tripwire")
    # Sitemap tripwire (acceptance): no single <lastmod> may cover >40% of URLs.
    sitemap = os.path.join(ROOT, "sitemap.xml")
    if os.path.exists(sitemap):
        import re
        sm = collections.Counter(re.findall(r"<lastmod>(\d{4}-\d{2}-\d{2})</lastmod>",
                                             open(sitemap, encoding="utf-8").read()))
        if sm:
            tot = sum(sm.values())
            sd, sn = sm.most_common(1)[0]
            if sn > 0.40 * tot:
                problems.append(f"sitemap: {sd} covers {sn}/{tot} URLs "
                                f"({100 * sn // tot}%) > 40% — uniform-stamp anti-pattern")
    if problems:
        print("[lastmod] verify: FAIL")
        for p in problems:
            print(f"    ✗ {p}")
        sys.exit(1)
    print(f"[lastmod] verify: ✓ {len(m)} entries · {len(dist)} distinct dates · "
          f"max share {100 * dist.most_common(1)[0][1] // len(m)}%")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    if (args.report or args.write) and _is_shallow():
        sys.exit("[lastmod] FATAL: shallow clone — every file would date to the "
                 "boundary commit. Run `git fetch --unshallow` first.")

    if args.report:
        cmd_report()
    elif args.verify:
        cmd_verify()
    else:  # default = write
        cmd_write()


if __name__ == "__main__":
    main()
