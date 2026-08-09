#!/usr/bin/env python3
"""Render/derive gate: no orphan ✅ badges, no hand-set geo stamps.

geo_verified is DERIVED (by derive_geo_verified.py) from real Google signals.
This gate is the structural guarantee that nobody hand-edits a `geo_verified:
true` into a fiche without the evidence that earns it. It asserts, read-only,
for every Json/<slug>.json:

  if geo_verified is true, then
    * google_place_id is present (non-empty), AND
    * a gps_drift_m is recorded under google_check or freshness, AND
    * geo_verified_drift_m matches that recorded drift (the audit trail is real,
      not invented), AND that drift is within the verification bound.

Any violation -> exit 1 (build red). Clean -> exit 0.

This complements the no-silent-key-drop gate: that one guards data we already
trust; this one guards a *claim* (the ✅) from being asserted without proof.
"""
import argparse
import glob
import json
import os
import sys

JSON_DIR = "Json"
# Upper bound the stamp's recorded drift may take. Matches derive's default
# --max-drift. A stamp whose audit drift exceeds this is stale/forged.
MAX_VERIFIED_DRIFT = 150  # generous ceiling; derive writes <=100 by default


def get_path(d, *path):
    cur = d
    for key in path:
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return None
    return cur


def recorded_drift(d):
    drift = get_path(d, "google_check", "gps_drift_m")
    if drift is None:
        drift = get_path(d, "freshness", "gps_drift_m")
    return drift


def check_fiche(d):
    """Return a list of violation strings for one fiche (empty = clean)."""
    if d.get("geo_verified") is not True:
        return []  # no claim -> nothing to prove
    slug = d.get("slug", "?")
    violations = []
    if not d.get("google_place_id"):
        violations.append(f"{slug}: geo_verified:true but no google_place_id")
    drift = recorded_drift(d)
    if drift is None:
        violations.append(f"{slug}: geo_verified:true but no gps_drift_m on record")
    stamped = d.get("geo_verified_drift_m")
    if stamped is None:
        violations.append(f"{slug}: geo_verified:true but no geo_verified_drift_m audit field")
    elif drift is not None and stamped != drift:
        violations.append(
            f"{slug}: geo_verified_drift_m={stamped} disagrees with recorded "
            f"gps_drift_m={drift} (audit trail invented?)")
    elif stamped is not None and stamped > MAX_VERIFIED_DRIFT:
        violations.append(
            f"{slug}: geo_verified_drift_m={stamped} > {MAX_VERIFIED_DRIFT}m ceiling")
    return violations


def main():
    ap = argparse.ArgumentParser(description="Assert no orphan/hand-set geo_verified stamps.")
    ap.add_argument("--json-dir", default=JSON_DIR)
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.json_dir, "*.json")))
    if not files:
        print(f"::error::no fiches under {args.json_dir}/", file=sys.stderr)
        sys.exit(1)

    violations = []
    verified = 0
    for f in files:
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        if d.get("geo_verified") is True:
            verified += 1
        violations.extend(check_fiche(d))

    print(f"gate_geo_verified: checked {len(files)} fiches, {verified} verified")
    if not violations:
        print("✓ every geo_verified:true is backed by google_place_id + recorded drift")
        sys.exit(0)

    print(f"::error::{len(violations)} orphan/hand-set geo_verified stamp(s):")
    for v in violations:
        print(f"    ✗ {v}")
    print("\ngeo_verified is DERIVED — run scripts/derive_geo_verified.py, never "
          "hand-set the stamp.")
    sys.exit(1)


if __name__ == "__main__":
    main()
