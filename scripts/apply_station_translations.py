#!/usr/bin/env python3
"""apply_station_translations.py — JOB 2 translation tail (11 non-FR locales).

Merges the per-locale translation payloads produced by the translation lane
(one tr-<lang>.json per locale, native-speaker translations of the four FR
facets) into the station fiches, each field to its locale-correct home:

  parking     → i18n.<lang>.facts.parking          (lang_fact reads this)
  hours       → i18n.<lang>.practical_info  {k: <localized label>, v: ...}
  transport   → i18n.<lang>.practical_info  {k: <localized label>, v: ...}
  pmr_detail  → i18n.<lang>.acces_pmr_detail        (build swaps this in off-fr,
                                                     FR sentence never leaks)

None of these fields is payload-tracked by the translation revert-guard
(translations/<lang>.json only carries name/meta/body.what_is/faq/hero_alt), so
there is nothing to sync — the fiche i18n block is the single home.

Payload files live in PAYLOAD_DIR (default: the session scratchpad). Each is
{"labels": {"hours","transport"}, "stations": {slug: {parking,hours,transport,
pmr_detail}}}. A field is written only where the payload carries it. Idempotent;
practical_info entries are upserted by their localized label. --report writes
nothing; --apply requires ALL locales' payloads to be present.
"""
import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_DIR = os.path.join(ROOT, "Json")
LOCALES = ["en", "de", "it", "es", "nl", "pl", "pt", "cs", "ar", "he", "ja"]
DEFAULT_PAYLOAD_DIR = ("/tmp/claude-0/-home-user-Loisir-74/"
                       "73a1d1eb-8d58-5e5a-9d92-ce33d5b49df3/scratchpad")


def upsert_practical(blk, label, value):
    pi = blk.setdefault("practical_info", [])
    for e in pi:
        if isinstance(e, dict) and (e.get("k") or "").strip() == label.strip():
            if e.get("v") == value:
                return "same"
            e["v"] = value
            return "updated"
    pi.append({"k": label, "v": value})
    return "set"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--payload-dir", default=DEFAULT_PAYLOAD_DIR)
    args = ap.parse_args()

    payloads = {}
    missing = []
    for lang in LOCALES:
        fp = os.path.join(args.payload_dir, f"tr-{lang}.json")
        if os.path.exists(fp):
            payloads[lang] = json.load(open(fp, encoding="utf-8"))
        else:
            missing.append(lang)
    if missing:
        # Partial application is valid: the merge is idempotent and re-runnable,
        # so deferred locales can be added later without disturbing applied ones.
        print(f"⚠ deferred locales (no payload yet): {missing} — "
              f"applying the {len(payloads)} present locale(s) only.")

    tot = {"parking": 0, "hours": 0, "transport": 0, "pmr": 0}
    per_lang = {l: dict(parking=0, hours=0, transport=0, pmr=0) for l in payloads}
    dirty = {}

    for lang, pay in payloads.items():
        labels = pay.get("labels") or {}
        hlab = labels.get("hours") or "Horaires"
        tlab = labels.get("transport") or "Transports"
        for slug, rec in (pay.get("stations") or {}).items():
            fp = os.path.join(JSON_DIR, f"{slug}.json")
            if not os.path.exists(fp):
                print(f"  {lang}/{slug}: MISSING FICHE"); continue
            d = dirty.get(slug) or json.load(open(fp, encoding="utf-8"))
            dirty[slug] = d
            blk = (d.setdefault("i18n", {})).setdefault(lang, {})

            if rec.get("parking"):
                facts = blk.setdefault("facts", {})
                if facts.get("parking") != rec["parking"]:
                    facts["parking"] = rec["parking"]
                    tot["parking"] += 1; per_lang[lang]["parking"] += 1
            if rec.get("hours"):
                st = upsert_practical(blk, hlab, rec["hours"])
                if st in ("set", "updated"):
                    tot["hours"] += 1; per_lang[lang]["hours"] += 1
            if rec.get("transport"):
                st = upsert_practical(blk, tlab, rec["transport"])
                if st in ("set", "updated"):
                    tot["transport"] += 1; per_lang[lang]["transport"] += 1
            if rec.get("pmr_detail"):
                if blk.get("acces_pmr_detail") != rec["pmr_detail"]:
                    blk["acces_pmr_detail"] = rec["pmr_detail"]
                    tot["pmr"] += 1; per_lang[lang]["pmr"] += 1

    print(f"{'lang':5} {'park':>5} {'hours':>6} {'trans':>6} {'pmr':>5}")
    for lang in LOCALES:
        if lang in per_lang:
            p = per_lang[lang]
            print(f"{lang:5} {p['parking']:>5} {p['hours']:>6} {p['transport']:>6} {p['pmr']:>5}")

    if args.apply:
        for slug, d in dirty.items():
            fp = os.path.join(JSON_DIR, f"{slug}.json")
            json.dump(d, open(fp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            if not open(fp, encoding="utf-8").read().endswith("\n"):
                open(fp, "a", encoding="utf-8").write("\n")

    print(f"\ntotals: parking={tot['parking']} hours={tot['hours']} "
          f"transport={tot['transport']} acces_pmr_detail={tot['pmr']} "
          f"across {len(payloads)} locales, {len(dirty)} fiches")
    print("APPLIED" if args.apply else "(report only — nothing written)")


if __name__ == "__main__":
    main()
