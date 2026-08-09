#!/usr/bin/env python3
"""gate_venue_centroid.py — preventive gate (builder-audit defect 2).

Centroid-placeholder coords: a fiche created without a geocode step inherits a
commune-centre fallback, so several venues in one commune land on the SAME
point. Maps deep-links then resolve to the town centre, parking/transport
badges point at the wrong spot, and the fiche can never earn geo_verified.
audit_venue_locations.py only catches coords >10 km from the centroid — a
venue sitting *on* the centroid (0 km) passes silently.

This gate catches the on-centroid case structurally: cluster every renderable
fiche by its exact (lat, lng) and look at how many NON-EXEMPT venues land on
one point.

  FAIL  — any single coord shared by >= 3 non-exempt venues. Three distinct
          businesses on one identical point is a centroid fallback, not a real
          co-location. (After the §C backfill this is 0.)
  WARN  — any coord shared by exactly 2 non-exempt venues. Often a real
          co-location (same building / base nautique) but sometimes a fallback;
          surfaced for a human glance, never fails the build.

Exemptions (legitimately lack a single precise point):
  - category 'voie-verte'                      (linear greenways)
  - 'sentier' that is a GR/GRP/tour/littoral/ViaRhôna route
  - any fiche with  "meeting_point": true       (guides/activities w/ a RV point)

Usage:
    python3 scripts/gate_venue_centroid.py              # fail on >=3, warn on 2
    python3 scripts/gate_venue_centroid.py --warn-only  # never fail (report only)
"""
import argparse
import glob
import json
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_DIR = os.path.join(ROOT, "Json")
RENDERABLE = ("published", "verified")
ROUTE_TOKENS = ("gr ", "grp", "gr®", "tour du", "tour de", "viarhona",
                "via rhona", "littoral", "sentier du tour")


def is_exempt(d):
    cat = d.get("category")
    name = ((d.get("i18n", {}) or {}).get("fr", {}) or {}).get("name", "") or ""
    if cat == "voie-verte":
        return True
    if d.get("meeting_point") is True:
        return True
    if cat == "sentier" and any(t in name.lower() for t in ROUTE_TOKENS):
        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--warn-only", action="store_true",
                    help="Report clusters but always exit 0.")
    args = ap.parse_args()

    clusters = defaultdict(list)   # (lat,lng) -> [(slug, exempt)]
    for fp in sorted(glob.glob(os.path.join(JSON_DIR, "*.json"))):
        d = json.loads(open(fp, encoding="utf-8").read())
        if d.get("status") not in RENDERABLE:
            continue
        lat, lng = d.get("latitude"), d.get("longitude")
        if lat is None or lng is None:
            continue
        clusters[(round(lat, 5), round(lng, 5))].append((d["slug"], is_exempt(d)))

    fails, warns = [], []
    for coord, members in clusters.items():
        nonexempt = [s for s, e in members if not e]
        if len(nonexempt) >= 3:
            fails.append((coord, nonexempt))
        elif len(nonexempt) == 2:
            warns.append((coord, nonexempt))

    print(f"gate_venue_centroid: {len(clusters)} distinct coords among renderable fiches")
    if warns:
        print(f"  ⚠ {len(warns)} coord(s) shared by 2 non-exempt venues "
              f"(review — co-location or leftover fallback):")
        for coord, ne in sorted(warns):
            print(f"      {coord}: {sorted(ne)}")
    if not fails:
        print("✓ no centroid cluster (no coord shared by ≥3 non-exempt venues)")
        sys.exit(0)

    print(f"::error::{len(fails)} centroid cluster(s) — ≥3 non-exempt venues on one point:")
    for coord, ne in sorted(fails):
        print(f"    ✗ {coord}: {sorted(ne)}")
    print("\nThese share a commune-centre placeholder. Backfill real per-venue "
          "pins (official site / BAN / OSM) — see reports/geo-placeholder-coords.md.")
    if args.warn_only:
        print("(--warn-only set → exiting 0)")
        sys.exit(0)
    sys.exit(1)


if __name__ == "__main__":
    main()
