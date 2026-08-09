#!/usr/bin/env python3
"""gate_hubs_membership.py — guard the multi-hub `hubs[]` field.

Lieux can opt into extra hubs via a top-level `hubs: [<hub-slug>]` (additive to
their `category` hub). This gate keeps that from drifting into dilution or typos:

  1. VALID  — every entry in hubs[] must be a real hub slug (a HUB_FILTERS key).
  2. NO-DUPE — a lieu must not list a hub it ALREADY belongs to via its
     category/curated filter (redundant self-add).
  3. NO DILUTION — no hub may exceed MEMBER_CAP members (category + hubs[] opt-ins).
     A diluted hub loses topical authority; this catches a blanket keyword add.

Read-only over Json/. Exit 1 on any violation.

Usage:
    python3 scripts/gate_hubs_membership.py
"""
import glob
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from build_hubs import HUB_FILTERS   # noqa: E402  (authoritative hub slugs + filters)

VALID_HUBS = set(HUB_FILTERS)
MEMBER_CAP = 150   # generous: current max hub is ~85; catches runaway hubs[] adds
RENDERABLE = ("published", "verified")


def main():
    fiches = []
    for fp in sorted(glob.glob(os.path.join(ROOT, "Json", "*.json"))):
        try:
            fiches.append(json.loads(open(fp, encoding="utf-8").read()))
        except Exception:
            continue

    violations = []
    members = Counter()
    for d in fiches:
        slug = d.get("slug")
        hubs = d.get("hubs") or []
        if not isinstance(hubs, list):
            violations.append(f"{slug}: hubs is not a list")
            continue
        for h in hubs:
            if h not in VALID_HUBS:
                violations.append(f"{slug}: hubs entry '{h}' is not a real hub slug")
            elif HUB_FILTERS[h](d):
                violations.append(f"{slug}: hubs entry '{h}' is redundant "
                                  f"(already a member via category/curated filter)")
        # membership count (renderable only): filter OR hubs[] opt-in
        if d.get("status") in RENDERABLE:
            for hub, filt in HUB_FILTERS.items():
                if filt(d) or hub in hubs:
                    members[hub] += 1

    over = [(h, n) for h, n in members.items() if n > MEMBER_CAP]
    for h, n in sorted(over, key=lambda x: -x[1]):
        violations.append(f"hub '{h}' has {n} members > cap {MEMBER_CAP} (dilution)")

    n_multi = sum(1 for d in fiches if d.get("hubs"))
    print(f"gate_hubs_membership: {len(fiches)} fiches, {n_multi} with a hubs[] "
          f"opt-in; largest hub {max(members.values()) if members else 0}/{MEMBER_CAP}")
    if not violations:
        print("✓ all hubs[] entries valid, non-redundant; no hub diluted")
        sys.exit(0)

    print(f"::error::{len(violations)} hub-membership violation(s):")
    for v in violations:
        print(f"    ✗ {v}")
    sys.exit(1)


if __name__ == "__main__":
    main()
