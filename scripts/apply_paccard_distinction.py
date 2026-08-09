#!/usr/bin/env python3
"""apply_paccard_distinction.py — add the Fonderie Paccard distinction row.

Adds ONE attributed practical_info entry ("Distinction") to fonderie-paccard-
sevrier.json in all 12 locales. Framed as ANNOUNCED by the Maison, not asserted
as an independently juried honour: the Comité de France laureates page does not
list Paccard and the Palme d'Or is a self-entered promotional distinction, so
the honest register is attribution. Proper nouns (the award name, "Comité de
France", "Maison Paccard") stay verbatim in every locale. practical_info is not
translation-payload-tracked, so no payload sync is needed. Idempotent (upsert by
localized label). --report writes nothing.
"""
import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SLUG = "fonderie-paccard-sevrier"

LABEL = {
    "fr": "Distinction", "en": "Distinction", "de": "Auszeichnung",
    "it": "Riconoscimento", "es": "Distinción", "nl": "Onderscheiding",
    "pl": "Wyróżnienie", "pt": "Distinção", "cs": "Ocenění",
    "ar": "تكريم", "he": "הוקרה", "ja": "受賞",
}
VALUE = {
    "fr": "Palme d'or de l'artisanat 2026 (Comité de France), distinction annoncée par la Maison Paccard.",
    "en": "Palme d'or de l'artisanat 2026 (Comité de France), a distinction announced by Maison Paccard.",
    "de": "Palme d'or de l'artisanat 2026 (Comité de France), eine von der Maison Paccard bekannt gegebene Auszeichnung.",
    "it": "Palme d'or de l'artisanat 2026 (Comité de France), riconoscimento annunciato dalla Maison Paccard.",
    "es": "Palme d'or de l'artisanat 2026 (Comité de France), distinción anunciada por la Maison Paccard.",
    "nl": "Palme d'or de l'artisanat 2026 (Comité de France), een door Maison Paccard aangekondigde onderscheiding.",
    "pl": "Palme d'or de l'artisanat 2026 (Comité de France), wyróżnienie ogłoszone przez Maison Paccard.",
    "pt": "Palme d'or de l'artisanat 2026 (Comité de France), distinção anunciada pela Maison Paccard.",
    "cs": "Palme d'or de l'artisanat 2026 (Comité de France), ocenění oznámené společností Maison Paccard.",
    "ar": "«Palme d'or de l'artisanat 2026» (Comité de France) — تكريم أعلنت عنه Maison Paccard.",
    "he": "«Palme d'or de l'artisanat 2026» (Comité de France) — הוקרה שעליה הודיעה Maison Paccard.",
    "ja": "Palme d'or de l'artisanat 2026(Comité de France)。Maison Paccard が発表した受賞。",
}


def upsert(blk, label, value):
    pi = blk.setdefault("practical_info", [])
    for e in pi:
        if isinstance(e, dict) and (e.get("k") or "").strip() == label:
            st = "same" if e.get("v") == value else "updated"
            e["v"] = value
            return st
    pi.append({"k": label, "v": value})
    return "set"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    fp = os.path.join(ROOT, "Json", f"{SLUG}.json")
    d = json.load(open(fp, encoding="utf-8"))
    i18n = d.setdefault("i18n", {})
    for lang in LABEL:
        blk = i18n.get(lang)
        if not isinstance(blk, dict):
            print(f"  {lang}: no locale block — skipped"); continue
        st = upsert(blk, LABEL[lang], VALUE[lang]) if args.apply else "would-set"
        print(f"  {lang}: {st} [{LABEL[lang]}]")
    if args.apply:
        json.dump(d, open(fp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        if not open(fp, encoding="utf-8").read().endswith("\n"):
            open(fp, "a", encoding="utf-8").write("\n")
    print("APPLIED" if args.apply else "(report only — nothing written)")


if __name__ == "__main__":
    main()
