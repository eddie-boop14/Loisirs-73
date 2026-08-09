#!/usr/bin/env python3
"""gate_tarif_completeness.py — station tarif prose must cover the FULL roster.

The lesson of the "8 vs 12" gap (twice): a hardcoded LANGS literal drifted from
the published roster, so facts.tarif was written in 8 languages while 4 lanes
(pl/ja/ar/he — including both RTL lanes submitted to Bing) sat empty. CI stayed
green because no gate tested per-language completeness. This gate closes that:

  LAW: every published `category == "station"` fiche that carries facts.tarif in
       ANY published language must carry it in ALL published languages
       (scripts/locales.py VISIBLE). Miss one → exit 1, build blocked.

Scope note: deliberately station-only. The wider corpus carries facts.tarif in
the 6 prose langs on ~300 non-station fiches (a separate pre-existing lane); a
blanket all-fiches/all-facts gate would red-fail hundreds of fiches on many
fields (best_season, type, access…). Enforcing the invariant where it was just
established — stations — keeps the build honest without silent scope creep.
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import locales  # noqa: E402

LANGS = list(locales.VISIBLE)


def facts(d, lang):
    return ((d.get("i18n") or {}).get(lang) or {}).get("facts") or {}


def main():
    stations, gaps = 0, []
    for p in sorted(glob.glob(os.path.join(ROOT, "Json", "*.json"))):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("category") != "station":
            continue
        if d.get("status") not in (None, "published"):
            continue
        stations += 1
        present = [lg for lg in LANGS if facts(d, lg).get("tarif")]
        if not present:
            continue  # a station with no tarif at all is out of scope here
        missing = [lg for lg in LANGS if not facts(d, lg).get("tarif")]
        if missing:
            gaps.append((d["slug"], missing))

    if gaps:
        print(f"gate_tarif_completeness: FAIL — {len(gaps)} station(s) with an "
              f"incomplete tarif roster (must cover all {len(LANGS)} published langs):",
              file=sys.stderr)
        for slug, missing in gaps:
            print(f"  ✗ {slug} — missing: {', '.join(missing)}", file=sys.stderr)
        print("Fix: derive LANGS from locales.VISIBLE in the writer and backfill "
              "the missing lanes (never a hardcoded language literal).", file=sys.stderr)
        sys.exit(1)

    print(f"gate_tarif_completeness: {stations} station fiches · "
          f"facts.tarif complete across all {len(LANGS)} published langs ✓")


if __name__ == "__main__":
    main()
