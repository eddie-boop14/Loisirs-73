#!/usr/bin/env python3
"""gate_winter_schema.py — HANDOFF-winter §6. Fail the build if:

  1. winter bullets appear in a facet md whose lieu is NOT a WINTER_NODES category
  2. any facts.winter_access / winter_infra / snow_view value is off the
     controlled vocab (typo / inference guard)
  3. a snow_view value carries a subjective rating word (anti-fabrication)
  4. the equipment line is missing on a qualifying HS node, or its text differs
     from EQUIP[lang] (+ optional col clause)
  5. the frozen tokens `Mont-Blanc` / `Loi Montagne II` are altered or translated

Runs on the built content/ facet md + Json/ source. Wire AFTER gate_facet_layer.
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import build_ai_content as B  # noqa: E402  (single source of vocab)

JSON_DIR = os.path.join(ROOT, "Json")
CONTENT = {"fr": os.path.join(ROOT, "content"),
           "en": os.path.join(ROOT, "content", "en")}
SUBJECTIVE = re.compile(
    r"\b(exceptionnel|exceptionnelle|exceptional|meilleur|best|incroyable|stunning)\b",
    re.I)
# every winter LABEL line, per lang, keyed by the access/infra/view/equip label
LABELS = {lang: {k: v[lang] for k, v in B.WINTER_LABELS.items()}
          for lang in ("fr", "en")}
FROZEN = ("Mont-Blanc", "Loi Montagne II")


def slug_category():
    out = {}
    for p in glob.glob(os.path.join(JSON_DIR, "*.json")):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        out[d.get("slug") or os.path.basename(p)[:-5]] = d
    return out


def check_json_vocab(d, viol):
    slug = d.get("slug")
    facts = ((d.get("i18n") or {}).get("fr") or {}).get("facts") or {}
    a = facts.get("winter_access")
    if a is not None and a not in B.WINTER_ACCESS:
        viol.append(f"{slug}: winter_access {a!r} off controlled vocab")
    for x in (facts.get("winter_infra") or []):
        if x not in B.WINTER_INFRA:
            viol.append(f"{slug}: winter_infra {x!r} off controlled vocab")
    sv = facts.get("snow_view")
    if sv is not None:
        if sv not in B.SNOW_VIEW:
            viol.append(f"{slug}: snow_view {sv!r} off controlled vocab")
        if SUBJECTIVE.search(str(sv)):
            viol.append(f"{slug}: snow_view {sv!r} carries a subjective rating word")


def check_md(rel, text, lang, cats, dicts, viol):
    slug = os.path.basename(rel)[:-3]
    is_winter = cats.get(slug) in B.WINTER_NODES
    labels = LABELS[lang]
    winter_lines = [ln for ln in text.splitlines()
                    if any(ln.startswith(f"- {lbl}:") for lbl in labels.values())]
    if winter_lines and not is_winter:
        viol.append(f"{rel}: winter bullets on non-WINTER_NODES lieu")
        return
    if not is_winter:
        return
    # rule 4b (JOB B): the inforoute74 delegation suffix on the ACCESS line must be
    # present exactly when the régime requires it (closed/partial OR col_chains), and
    # absent otherwise. The gate ACCEPTS the suffix (recognizes it as valid schema).
    facts = ((dicts.get(slug) or {}).get("i18n") or {}).get("fr", {}).get("facts") or {}
    acc_label = labels["access"]
    acc_lines = [ln for ln in winter_lines if ln.startswith(f"- {acc_label}:")]
    if acc_lines:
        suffix = f"— {B.WINTER_LIVE[lang]} {B.INFOROUTE_HOST}"
        has = suffix in acc_lines[0]
        need = B.winter_needs_inforoute(facts)
        if need and not has:
            viol.append(f"{rel}: access line missing the inforoute74 suffix (régime requires it)")
        if has and not need:
            viol.append(f"{rel}: access line carries the inforoute74 suffix but régime doesn't require it")
    # rule 4: equipment line present and byte-exact (constant + optional col clause)
    eq_label = labels["equip"]
    eq_lines = [ln for ln in winter_lines if ln.startswith(f"- {eq_label}:")]
    if not eq_lines:
        viol.append(f"{rel}: qualifying node missing the equipment line")
    else:
        val = eq_lines[0].split(":", 1)[1].strip()
        ok = val in (B.EQUIP[lang], B.EQUIP[lang] + B.EQUIP_COL[lang])
        if not ok:
            viol.append(f"{rel}: equipment line text drift: {val!r}")
    # rule 3: no subjective rating word on the snow-panorama line
    for ln in winter_lines:
        if ln.startswith(f"- {labels['view']}:") and SUBJECTIVE.search(ln):
            viol.append(f"{rel}: snow panorama line carries a subjective rating word")
    # rule 5: frozen tokens verbatim — ONLY within the winter schema lines
    # (existing prose has its own conventions; the freeze is on the schema).
    for ln in winter_lines:
        if "Loi Montagne" in ln and "Loi Montagne II" not in ln:
            viol.append(f"{rel}: 'Loi Montagne II' altered in a winter line")
        for bad in ("Mont Blanc", "Montblanc", "Mont-blanc"):
            if bad in ln:
                viol.append(f"{rel}: 'Mont-Blanc' altered to {bad!r} in a winter line")


def main():
    dicts = slug_category()
    cats = {s: d.get("category") for s, d in dicts.items()}
    viol = []
    for d in dicts.values():
        check_json_vocab(d, viol)
    for lang, base in CONTENT.items():
        if not os.path.isdir(base):
            continue
        for p in glob.glob(os.path.join(base, "*.md")):
            rel = os.path.relpath(p, ROOT)
            text = open(p, encoding="utf-8").read()
            check_md(rel, text, lang, cats, dicts, viol)
    if viol:
        print("gate_winter_schema: FAIL")
        for v in viol[:60]:
            print(f"  ✗ {v}")
        if len(viol) > 60:
            print(f"  … and {len(viol) - 60} more")
        sys.exit(1)
    print(f"gate_winter_schema: ✓ winter schema clean "
          f"({sum(1 for c in cats.values() if c in B.WINTER_NODES)} winter nodes)")


if __name__ == "__main__":
    main()
