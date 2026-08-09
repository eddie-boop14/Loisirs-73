#!/usr/bin/env python3
"""derive_family_ok.py — HANDOFF-intentpages §3, the family_ok micro-job.

Derives a CANDIDATE facts.family_ok flag per published fiche from two signal
tiers, writes a review report, and only applies after Eddie's sign-off:

  --report : reports/family-ok-report.md (candidate + signals per slug). Eddie
             reviews THIS. Nothing is written to fiches.
  --apply  : write facts.family_ok (true|false) for every candidate row +
             research_log entry. Fiches with no signal keep family_ok ABSENT
             (selector treats absent/null as excluded — the honest default).

Never inferred silently at build time: the intent-page builder reads only the
persisted flag. Signals:
  T1 category defaults — plage, parc, jardin, base-nautique, domaine, aquaparc,
     accrobranche, patinoire, lac, croisiere → true candidate;
     casino → false candidate.
  T2 FR prose — activities[].tag == "familial", or body text matching
     "famill/familial/dès N ans/enfant" → true candidate;
     "interdit aux moins de/à partir de 1[2-8] ans" alone → left for review.
  Overrides: via ferrata / canyoning / bungee / rafting slug-or-name patterns
     force a false candidate (sensations, not famille) regardless of prose.
"""
import argparse
import glob
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_DIR = os.path.join(ROOT, "Json")
REPORT = os.path.join(ROOT, "reports", "family-ok-report.md")
TODAY = "2026-07-17"

CAT_TRUE = {"plage", "parc", "jardin", "base-nautique", "domaine", "aquaparc",
            "accrobranche", "patinoire", "lac", "croisiere"}
CAT_FALSE = {"casino"}
HARD_FALSE = re.compile(r"via[- ]ferrata|canyoning|bungee|bun[- ]j|rafting|speleo|parapente|montgolfiere|wakepark", re.I)
PROSE_TRUE = re.compile(r"\bfamili|famille|dès \d+ ans|enfants", re.I)


def fr_text(d):
    fr = (d.get("i18n") or {}).get("fr") or {}
    parts = [fr.get("meta_description", ""), (fr.get("hero") or {}).get("lead", ""),
             (fr.get("body") or {}).get("what_is", "")]
    for a in fr.get("activities") or []:
        parts += [a.get("title", ""), a.get("description", "")]
    return " ".join(p for p in parts if p)


def derive(d):
    """→ (candidate True|False|None, [signals])."""
    slug, cat = d.get("slug", ""), d.get("category", "")
    name = ((d.get("i18n") or {}).get("fr") or {}).get("name", "")
    sig = []
    if HARD_FALSE.search(slug) or HARD_FALSE.search(name):
        return False, ["hard-false: sensations pattern (via ferrata/canyoning/…)"]
    if cat in CAT_FALSE:
        return False, [f"category default false [{cat}]"]
    cand = None
    if cat in CAT_TRUE:
        cand = True; sig.append(f"category default true [{cat}]")
    tags = [a.get("tag") for a in ((d.get("i18n") or {}).get("fr") or {}).get("activities") or []]
    if "familial" in tags:
        cand = True; sig.append('activities tag "familial"')
    # Eddie ⚑ 2026-07-17: STRICT tier only — the generic prose-mention tier
    # (famille/enfants anywhere in FR text) marked 199 extra fiches and was
    # rejected; a word occurrence is not a family-suitability claim.
    return cand, sig


def rows():
    out = []
    for p in sorted(glob.glob(os.path.join(JSON_DIR, "*.json"))):
        d = json.load(open(p, encoding="utf-8"))
        if d.get("status") != "published":
            continue
        cur = ((d.get("i18n") or {}).get("fr") or {}).get("facts", {}).get("family_ok")
        cand, sig = derive(d)
        out.append((d["slug"], d.get("category", ""), cur, cand, sig))
    return out


def write_report(rs):
    t = [r for r in rs if r[3] is True]
    f = [r for r in rs if r[3] is False]
    n = [r for r in rs if r[3] is None]
    L = [f"# family_ok — derivation report (HANDOFF-intentpages §3)\n",
         f"Generated {TODAY} · published fiches: {len(rs)} · "
         f"candidate **true: {len(t)}** · **false: {len(f)}** · no signal (stays absent): {len(n)}\n",
         "\nEddie reviews this, then `derive_family_ok.py --apply`. No-signal fiches keep the flag",
         " absent = excluded from famille selectors (honest default).\n",
         "\n## Candidate TRUE\n\n| slug | category | signals |\n|---|---|---|\n"]
    for s, c, cur, _, sig in t:
        L.append(f"| `{s}` | {c} | {'; '.join(sig)} |\n")
    L.append("\n## Candidate FALSE\n\n| slug | category | signals |\n|---|---|---|\n")
    for s, c, cur, _, sig in f:
        L.append(f"| `{s}` | {c} | {'; '.join(sig)} |\n")
    L.append(f"\n## No signal ({len(n)}) — flag stays absent\n\n")
    L.append(", ".join(f"`{s}`" for s, *_ in n) + "\n")
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    open(REPORT, "w", encoding="utf-8").write("".join(L))
    return len(t), len(f), len(n)


def do_apply(rs):
    applied = 0
    for slug, cat, cur, cand, sig in rs:
        if cand is None or cur == cand:
            continue
        p = os.path.join(JSON_DIR, f"{slug}.json")
        d = json.load(open(p, encoding="utf-8"))
        d.setdefault("i18n", {}).setdefault("fr", {}).setdefault("facts", {})["family_ok"] = cand
        d.setdefault("research_log", []).append({
            "date": TODAY, "by": "family_ok derivation",
            "note": f"facts.family_ok={str(cand).lower()} — {'; '.join(sig)} (rapport revu par Eddie avant apply)."})
        json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        applied += 1
    return applied


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    rs = rows()
    if args.apply:
        print(f"applied family_ok to {do_apply(rs)} fiches")
    else:
        t, f, n = write_report(rs)
        print(f"REPORT → {os.path.relpath(REPORT, ROOT)}: true {t} · false {f} · no-signal {n}")


if __name__ == "__main__":
    main()
