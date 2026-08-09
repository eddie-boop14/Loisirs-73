#!/usr/bin/env python3
"""Emit reports/acces-pmr-coverage.{md,json}: PMR-accessibility fill rate by
fiche type/category and by source. Read-only over Json/."""
import glob, json, os, datetime
from collections import Counter, defaultdict
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    by_status = Counter(); by_source = Counter(); by_cat = defaultdict(Counter)
    total = filled = null = absent = 0
    rows = []
    for fp in sorted(glob.glob(os.path.join(ROOT, "Json", "*.json"))):
        d = json.loads(open(fp, encoding="utf-8").read())
        if d.get("status") != "published":
            continue
        total += 1
        cat = d.get("category", "?")
        a = d.get("acces_pmr")
        if a is None:
            absent += 1; by_cat[cat]["absent"] += 1; continue
        st = a.get("status")
        by_status[st if st else "null"] += 1
        by_cat[cat][st if st else "null"] += 1
        if st:
            filled += 1; by_source[a.get("source_name", "?")] += 1
            rows.append((d["slug"], cat, st, a.get("source_name"), a.get("source_url")))
        else:
            null += 1
    pct = (100 * filled / total) if total else 0
    data = {"date": datetime.date.today().isoformat(), "published": total,
            "filled": filled, "null": null, "absent": absent,
            "by_status": dict(by_status), "by_source": dict(by_source),
            "by_category": {c: dict(v) for c, v in by_cat.items()}}
    with open(os.path.join(ROOT, "reports", "acces-pmr-coverage.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2); f.write("\n")
    L = [f"# Accessibilité PMR — coverage", "",
         f"_© 2026 · Bleu canard édition · {data['date']}_", "",
         f"- Published fiches: **{total}**",
         f"- Sourced (status set): **{filled}** ({pct:.1f}%) — accessible/partiel/non_accessible",
         f"- Null (flagged unverified): **{null}**",
         f"- No acces_pmr field yet: **{absent}**", "",
         "## By status", ""]
    for s, n in by_status.most_common():
        L.append(f"- {s}: {n}")
    L += ["", "## By source (sourced rows)", ""]
    for s, n in by_source.most_common():
        L.append(f"- {s}: {n}")
    L += ["", "## By category (filled / null / absent)", "",
          "| category | accessible | partiel | non_accessible | null | absent |",
          "|---|--:|--:|--:|--:|--:|"]
    for c in sorted(by_cat):
        v = by_cat[c]
        L.append(f"| {c} | {v.get('accessible',0)} | {v.get('partiel',0)} | "
                 f"{v.get('non_accessible',0)} | {v.get('null',0)} | {v.get('absent',0)} |")
    if rows:
        L += ["", "## Sourced fiches", "", "| slug | category | status | source |", "|---|---|---|---|"]
        for slug, cat, st, sn, su in sorted(rows):
            L.append(f"| `{slug}` | {cat} | {st} | [{sn}]({su}) |")
    open(os.path.join(ROOT, "reports", "acces-pmr-coverage.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"acces-pmr coverage: {filled} sourced / {null} null / {absent} absent of {total} published")

if __name__ == "__main__":
    main()
