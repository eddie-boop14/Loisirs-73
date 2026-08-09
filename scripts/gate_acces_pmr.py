#!/usr/bin/env python3
"""gate_acces_pmr.py — schema + anti-fabrication guard for accessibility data.

Lieux may carry a top-level, language-neutral `acces_pmr` object (rendered with
localized labels at build). This gate validates EVERY fiche that has one — no
status without a source, controlled vocab only, null ⇒ flagged. Fiches not yet
sourced simply have no `acces_pmr` and are skipped (not a violation).

  acces_pmr = {
    "status": accessible | partiel | non_accessible | null,
    "detail": "short sourced phrase" | null,
    "equipment": [controlled vocab],
    "handiplage_level": 1..4 | null,          # beaches
    "tourisme_handicap": [moteur|visuel|auditif|mental],
    "source_url": "https://…",                # REQUIRED when status != null
    "source_name": "Acceslibre | Handiplage | OT … | Commune …",
    "checked": "YYYY-MM-DD",
    "confidence": official | declarative | null
  }

Rules (acceptance §1-4): null ≠ accessible; status != null ⇒ source_url +
source_name; status == null ⇒ verify_flags has ACCES_PMR_UNVERIFIED; controlled
vocab on status / confidence / tourisme_handicap / handiplage_level.

Exit 1 on any violation.
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUS_VOCAB = {"accessible", "partiel", "non_accessible", None}
CONF_VOCAB = {"official", "declarative", None}
HANDICAP_VOCAB = {"moteur", "visuel", "auditif", "mental"}
EQUIP_VOCAB = {
    "tiralo", "hippocampe", "audioplage", "rampe", "wc_adapte", "parking_pmr",
    "ascenseur", "place_pmr", "boucle_magnetique", "chemin_stabilise",
    "fauteuil_tout_terrain", "sanitaire_adapte",
}
UNVERIFIED_FLAG = "ACCES_PMR_UNVERIFIED"


def main():
    viol = []
    n_with = 0
    for fp in sorted(glob.glob(os.path.join(ROOT, "Json", "*.json"))):
        d = json.loads(open(fp, encoding="utf-8").read())
        a = d.get("acces_pmr")
        if a is None:
            continue
        n_with += 1
        slug = d.get("slug")
        if not isinstance(a, dict):
            viol.append(f"{slug}: acces_pmr is not an object"); continue
        status = a.get("status")
        if status not in STATUS_VOCAB:
            viol.append(f"{slug}: status {status!r} not in {sorted(s for s in STATUS_VOCAB if s)}")
        if status is not None:
            if not a.get("source_url"):
                viol.append(f"{slug}: status={status} but no source_url (no claim without a source)")
            elif not str(a.get("source_url")).startswith(("http://", "https://")):
                viol.append(f"{slug}: source_url is not a URL")
            if not a.get("source_name"):
                viol.append(f"{slug}: status={status} but no source_name")
        else:
            vf = d.get("verify_flags") or []
            if not any(isinstance(f, str) and UNVERIFIED_FLAG in f for f in vf):
                viol.append(f"{slug}: status=null but no {UNVERIFIED_FLAG} verify_flag")
        if a.get("confidence") not in CONF_VOCAB:
            viol.append(f"{slug}: confidence {a.get('confidence')!r} not in {sorted(c for c in CONF_VOCAB if c)}")
        eq = a.get("equipment")
        if eq is not None:
            if not isinstance(eq, list) or any(e not in EQUIP_VOCAB for e in eq):
                bad = [e for e in (eq if isinstance(eq, list) else [eq]) if e not in EQUIP_VOCAB]
                viol.append(f"{slug}: equipment has out-of-vocab {bad}")
        th = a.get("tourisme_handicap")
        if th is not None and (not isinstance(th, list) or any(t not in HANDICAP_VOCAB for t in th)):
            viol.append(f"{slug}: tourisme_handicap out-of-vocab {th}")
        hl = a.get("handiplage_level")
        if hl is not None and str(hl) not in {"1", "2", "3", "4"}:
            viol.append(f"{slug}: handiplage_level {hl!r} not 1-4/null")
        ck = a.get("checked")
        if ck is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(ck)):
            viol.append(f"{slug}: checked {ck!r} not YYYY-MM-DD")

    print(f"gate_acces_pmr: {n_with} fiche(s) carry acces_pmr")
    if not viol:
        print("✓ acces_pmr schema valid; every status carries a source; nulls flagged")
        sys.exit(0)
    print(f"::error::{len(viol)} acces_pmr violation(s):")
    for v in viol:
        print(f"    ✗ {v}")
    sys.exit(1)


if __name__ == "__main__":
    main()
