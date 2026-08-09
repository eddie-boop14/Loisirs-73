#!/usr/bin/env python3
"""merge_secondary.py — merge agent_<X>_<lang>_secondary.json files into
Json/<slug>.json's i18n.<lang>.* fields.

JOB 7 follow-up: the 68 fiches that had only i18n.fr at campaign start now
have a translated body via wave 5+6 of JOB 7. This script applies their
SECONDARY fields (facts, activities, practical_info, faq, hero,
name_alternates, schema_amenities) translated by parallel agents I/J/K/L
(and any recovery follow-ups).

Schema accepted per agent file (top-level dict keyed by slug):
  {
    "<slug>": {
      "name_alternates": [...],
      "hero": {"badge": "...", "lead": "..."},
      "facts": {...},
      "body.activities": [{title,description,tag},...],
      "body.practical_info": [{k,v},...],
      "faq": [{q,a},...],
      "schema_amenities": [...]
    }
  }

For each key:
  body.<sub>  → i18n.<lang>.body.<sub>
  others     → i18n.<lang>.<key>

Idempotent. Writes a research_log entry per fiche per locale per day.
"""
import datetime
import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSON_DIR = ROOT / "Json"
TODAY = datetime.date.today().isoformat()


def merge_into_locale_block(blk, payload):
    """Mutate blk in place with the secondary-field payload."""
    body = blk.setdefault("body", {}) if isinstance(blk.get("body", {}), dict) else None
    if body is None:
        blk["body"] = {}; body = blk["body"]
    changed = 0
    for k, v in payload.items():
        if k.startswith("body."):
            sub = k[len("body."):]
            if body.get(sub) != v:
                body[sub] = v; changed += 1
        else:
            if blk.get(k) != v:
                blk[k] = v; changed += 1
    return changed


def main():
    files = sorted(glob.glob(str(ROOT / "translations" / "agent_*_secondary.json")))
    total_files = 0
    total_merges = 0
    for fp in files:
        total_files += 1
        # filename: agent_I_en_secondary.json → ('I','en')
        parts = Path(fp).stem.split("_")
        agent, lang = parts[1], parts[2]
        try:
            payload = json.load(open(fp))
        except Exception as e:
            print(f"  {fp}: PARSE ERROR {e}")
            continue
        n = 0
        for slug, fields in payload.items():
            jp = JSON_DIR / f"{slug}.json"
            if not jp.exists(): continue
            d = json.loads(jp.read_text(encoding="utf-8"))
            i18n = d.setdefault("i18n", {})
            blk = i18n.setdefault(lang, {})
            if not isinstance(blk, dict):
                blk = {}; i18n[lang] = blk
            if merge_into_locale_block(blk, fields):
                rl = d.setdefault("research_log", [])
                already = any(
                    isinstance(r, dict)
                    and r.get("by", "") == "scripts/merge_secondary.py"
                    and r.get("date") == TODAY
                    and lang in (r.get("note") or "")
                    for r in rl
                )
                if not already:
                    rl.append({
                        "date": TODAY,
                        "by": "scripts/merge_secondary.py",
                        "note": f"Merged secondary fields for {lang} from {fp.split('/')[-1]}.",
                    })
                jp.write_text(
                    json.dumps(d, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                n += 1
        print(f"  {fp}: {n}/{len(payload)} fiches updated")
        total_merges += n

    print(f"\nfiles processed: {total_files}")
    print(f"total fiche-lang merges: {total_merges}")


if __name__ == "__main__":
    main()
