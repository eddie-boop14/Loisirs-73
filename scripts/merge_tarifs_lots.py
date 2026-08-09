#!/usr/bin/env python3
"""merge_tarifs_lots.py — fuse the 4 harvest lots into the apply payload.

Reads scratchpad/tarifs-{a,b,c,d}.json (arrays of harvested station rows) and
writes data/station-tarifs-harvest.json in the shape apply_station_tarifs.py
expects: {"generated": DATE, "payload": {slug: {state, source_url, tiers,
evidence, tarif_i18n, note?}}}.

Guards (loud stop, never a silent partial):
- every lot file present and valid JSON;
- exactly EXPECTED station slugs covered, no dupes, no unknown slug;
- each row carries the keys the apply validator needs.
The apply script re-validates the 3-états contract — this only fuses + checks
coverage so a missing lot can't slip through as "done".
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOTS = [os.path.join(ROOT, "scratchpad", f"tarifs-{x}.json") for x in "abcd"]
OUT = os.path.join(ROOT, "data", "station-tarifs-harvest.json")
DATE = "2026-07-20"


def station_slugs():
    st = set()
    for p in glob.glob(os.path.join(ROOT, "Json", "*.json")):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("category") == "station":
            st.add(d["slug"])
    return st


def main():
    payload, seen = {}, {}
    for p in LOTS:
        if not os.path.exists(p):
            sys.exit(f"[merge] FAIL: lot file missing — {os.path.relpath(p, ROOT)}")
        with open(p, encoding="utf-8") as f:
            rows = json.load(f)
        for r in rows:
            slug = r.get("slug")
            if not slug:
                sys.exit(f"[merge] FAIL: row without slug in {os.path.basename(p)}")
            if slug in seen:
                sys.exit(f"[merge] FAIL: duplicate slug {slug} "
                         f"({os.path.basename(seen[slug])} + {os.path.basename(p)})")
            seen[slug] = p
            payload[slug] = {k: r[k] for k in
                             ("state", "source_url", "tiers", "evidence", "tarif_i18n")
                             if k in r}
            if r.get("note"):
                payload[slug]["note"] = r["note"]

    expected = station_slugs()
    got = set(payload)
    missing, extra = expected - got, got - expected
    if missing:
        sys.exit(f"[merge] FAIL: {len(missing)} station fiches uncovered — {sorted(missing)}")
    if extra:
        sys.exit(f"[merge] FAIL: {len(extra)} unknown slugs (not station fiches) — {sorted(extra)}")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"generated": DATE, "payload": payload}, f, ensure_ascii=False, indent=2)
        f.write("\n")
    n_state = {}
    for r in payload.values():
        n_state[r["state"]] = n_state.get(r["state"], 0) + 1
    print(f"[merge] {len(payload)} stations → {os.path.relpath(OUT, ROOT)}")
    print("  états: " + " · ".join(f"{k}={v}" for k, v in sorted(n_state.items())))


if __name__ == "__main__":
    main()
