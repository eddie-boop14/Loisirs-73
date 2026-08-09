#!/usr/bin/env python3
"""gate_access_cost.py — enforces the one derived access-cost model.

Guards the invariants derive_access_cost.py depends on, so the "one pattern →
one treatment" law cannot silently rot back into hand-varied encodings:

  1. `schema_org.is_free` is a real bool or null — NEVER the string "True"/
     "False" (the exact bug that hid 33 fiches, incl. 2 free beaches).
  2. Every published fiche resolves to exactly one state {free, free_seasonal,
     paid}.
  3. `free_seasonal` is only assigned to a seasonal-access category (plage/lac)
     — an attraction that merely operates in summer is `paid`, not free.
  4. If api/lieu/<slug>.json carries an emitted `access_cost`, it MUST equal a
     fresh derivation (no drift between source of truth and build artifact).

Read-only. Exit 1 on any violation.
"""
import json
import os
import sys
from glob import glob

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import derive_access_cost as dac  # noqa: E402

ROOT = dac.ROOT
VALID = {"free", "free_seasonal", "paid"}


def main():
    viol = []
    n = 0
    states = {s: 0 for s in VALID}
    for fp in sorted(glob(os.path.join(dac.JSON_DIR, "*.json"))):
        d = json.load(open(fp, encoding="utf-8"))
        if d.get("status") in ("draft", "unverified"):
            continue
        slug = d["slug"]
        n += 1

        raw = (d.get("schema_org") or {}).get("is_free")
        if isinstance(raw, str):
            viol.append(f"{slug}: schema_org.is_free is a string {raw!r} — must be bool/null "
                        f"(re-run the normalization; this is the 33-fiche bug)")

        state, window, extras, note = dac.derive(d)
        if state not in VALID:
            viol.append(f"{slug}: derived to invalid state {state!r}")
            continue
        states[state] += 1

        if state == "free_seasonal" and (d.get("category") or "") not in dac.SEASONAL_CATS:
            viol.append(f"{slug}: free_seasonal but category={d.get('category')!r} "
                        f"not in {sorted(dac.SEASONAL_CATS)}")

        ap = os.path.join(dac.API_DIR, f"{slug}.json")
        if os.path.exists(ap):
            emitted = (json.load(open(ap, encoding="utf-8")).get("access_cost") or {}).get("state")
            if emitted is not None and emitted != state:
                viol.append(f"{slug}: api access_cost.state={emitted!r} drifted from derived {state!r}")

    print(f"gate_access_cost: {n} published fiches — "
          f"free={states['free']} free_seasonal={states['free_seasonal']} paid={states['paid']}")
    if viol:
        print(f"::error::{len(viol)} access-cost violation(s):")
        for v in viol[:50]:
            print(f"    x {v}")
        sys.exit(1)
    print("OK one derived state per fiche; no string is_free; free_seasonal ⊆ {plage,lac}; "
          "emitted access_cost matches source")


if __name__ == "__main__":
    main()
