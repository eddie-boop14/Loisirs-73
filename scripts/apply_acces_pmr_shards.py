#!/usr/bin/env python3
"""apply_acces_pmr_shards.py — reduce Layer 2 agent shard outputs into Json/.

Reads every shard output JSON (a list of {slug, acces_pmr, note}) from a
directory, validates each against the acces_pmr controlled vocab, and writes the
field into Json/<slug>.json. status==null rows get verify_flags +=
ACCES_PMR_UNVERIFIED (and source/detail/equipment forced null). Protected fiches
and fiches that already carry acces_pmr are skipped. No-clobber, idempotent.

Usage: apply_acces_pmr_shards.py <out_dir> [--apply]
Default is a dry-run validation pass.
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROTECTED = {"chez-nous-a-la-plage", "chalet-du-tornet"}
STATUS_VOCAB = {"accessible", "partiel", "non_accessible", None}
CONF_VOCAB = {"official", "declarative", None}
HANDICAP_VOCAB = {"moteur", "visuel", "auditif", "mental"}
EQUIP_VOCAB = {
    "tiralo", "hippocampe", "audioplage", "rampe", "wc_adapte", "parking_pmr",
    "ascenseur", "place_pmr", "boucle_magnetique", "chemin_stabilise",
    "fauteuil_tout_terrain", "sanitaire_adapte",
}
UNVERIFIED_FLAG = "ACCES_PMR_UNVERIFIED"
TODAY = "2026-06-26"


def clean(a):
    """Validate + normalize one acces_pmr object; return (obj, error|None)."""
    if not isinstance(a, dict):
        return None, "not an object"
    status = a.get("status")
    if status not in STATUS_VOCAB:
        return None, f"bad status {status!r}"
    out = {
        "status": status,
        "detail": a.get("detail") or None,
        "equipment": a.get("equipment") or None,
        "handiplage_level": a.get("handiplage_level"),
        "tourisme_handicap": a.get("tourisme_handicap") or None,
        "source_url": a.get("source_url") or None,
        "source_name": a.get("source_name") or None,
        "checked": a.get("checked") or TODAY,
        "confidence": a.get("confidence") if a.get("confidence") in CONF_VOCAB else None,
    }
    if status is None:
        # force the unverified shape
        out.update(detail=None, equipment=None, tourisme_handicap=None,
                   source_url=None, source_name=None, confidence=None,
                   handiplage_level=None)
        return out, None
    # status != null -> must have an authoritative source
    su = out["source_url"]
    if not su or not str(su).startswith(("http://", "https://")):
        return None, f"status={status} without valid source_url"
    if not out["source_name"]:
        return None, f"status={status} without source_name"
    eq = out["equipment"]
    if eq is not None:
        if not isinstance(eq, list) or any(e not in EQUIP_VOCAB for e in eq):
            return None, f"equipment out-of-vocab {eq}"
    th = out["tourisme_handicap"]
    if th is not None:
        if not isinstance(th, list) or any(t not in HANDICAP_VOCAB for t in th):
            return None, f"tourisme_handicap out-of-vocab {th}"
    hl = out["handiplage_level"]
    if hl is not None and str(hl) not in {"1", "2", "3", "4"}:
        return None, f"handiplage_level {hl!r}"
    if hl is not None:
        out["handiplage_level"] = int(hl)
    ck = out["checked"]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(ck)):
        out["checked"] = TODAY
    return out, None


def main():
    if len(sys.argv) < 2:
        print("usage: apply_acces_pmr_shards.py <out_dir> [--apply]"); sys.exit(2)
    out_dir = sys.argv[1]
    apply = "--apply" in sys.argv
    recs = {}
    for fp in sorted(glob.glob(os.path.join(out_dir, "*.json"))):
        data = json.loads(open(fp, encoding="utf-8").read())
        for r in data:
            slug = r.get("slug")
            if slug:
                recs[slug] = r  # last wins (shards are disjoint anyway)
    n_src = n_null = n_skip = n_err = n_write = 0
    errs = []
    for slug, r in sorted(recs.items()):
        if slug in PROTECTED:
            n_skip += 1; continue
        fp = os.path.join(ROOT, "Json", f"{slug}.json")
        if not os.path.exists(fp):
            errs.append(f"{slug}: no Json file"); n_err += 1; continue
        d = json.loads(open(fp, encoding="utf-8").read())
        if d.get("acces_pmr") is not None:
            n_skip += 1; continue   # already sourced (Layer 1 / pilot)
        obj, err = clean(r.get("acces_pmr"))
        if err:
            errs.append(f"{slug}: {err}"); n_err += 1; continue
        if obj["status"] is None:
            n_null += 1
        else:
            n_src += 1
        if apply:
            d["acces_pmr"] = obj
            if obj["status"] is None:
                vf = d.get("verify_flags") or []
                if UNVERIFIED_FLAG not in vf:
                    vf = list(vf) + [UNVERIFIED_FLAG]
                d["verify_flags"] = vf
            with open(fp, "w", encoding="utf-8") as fh:
                json.dump(d, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            n_write += 1
    print(f"apply_acces_pmr_shards: {len(recs)} shard records | "
          f"sourced={n_src} null={n_null} skip={n_skip} err={n_err} "
          f"written={n_write if apply else 0} (apply={apply})")
    for e in errs[:40]:
        print(f"    ✗ {e}")
    if errs and not apply:
        print(f"    ({len(errs)} validation error(s) — fix shards before --apply)")
    sys.exit(1 if (errs and apply) else 0)


if __name__ == "__main__":
    main()
