#!/usr/bin/env python3
"""apply_station_facets.py — JOB 2, station facet backfill (28 ski stations).

Backfills the FOUR non-seasonal facets from official-source research
(`data/station-facets-source.json`, each value carrying source_url/source_name):

  parking     → i18n.fr.facts.parking   (verbatim sourced prose; hub membership
                is derived from this being non-null — no map to maintain)
  access_pmr  → top-level `acces_pmr`    (schema-gated by gate_acces_pmr.py)
  hours       → i18n.fr.practical_info   ("Horaires" k/v — DAILY clock hours only)
  transport   → i18n.fr.practical_info   ("Transports" k/v — sourced narrative)

WHY transport is NOT written to data/transport_index.json: that index is a
GTFS-derived proximity dataset (transport.data.gouv.fr, Licence Etalab 2.0) with
per-stop distance_m. None of the 28 stations sit near a qualifying GTFS stop, and
the research findings are distant-gare + navette narrative — injecting them as
"stops" with invented distances would corrupt an authoritative open-data index.
So the sourced access narrative lands as a practical_info entry (surfaces on the
fiche) and the stations correctly do NOT join the proximity facet they don't fit.

WHY hours is only the 9 stations with genuine daily clock hours: most sourced
"hours" strings are SEASON dates ("ouvert du 20/12 au 06/04"). Season/winter/
prices are owned by Edmaster's winter-month workflow and are OFF-LIMITS here.
Only real daily operating hours (curated below, season dates stripped) are written.

NEVER TOUCHED: winter, prices, season, best_season, price_tiers, schema_org,
facts.winter_*, facts.tarif — the winter-workflow's territory. Existing
practical_info entries are preserved; only Horaires/Transports are upserted.
Idempotent. --report writes nothing.
"""
import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_DIR = os.path.join(ROOT, "Json")
SRC = os.path.join(ROOT, "data", "station-facets-source.json")
CHECKED = "2026-07-23"
UNVERIFIED_FLAG = "ACCES_PMR_UNVERIFIED"

# Daily operating hours ONLY — season dates stripped by hand (they belong to the
# winter workflow). Keyed by slug; a station absent here gets no Horaires entry.
HOURS_DAILY = {
    "bernex": "Caisses des remontées : 8h45–16h hors vacances scolaires, "
              "8h30–17h pendant les vacances scolaires (télésiège du Pré-Richard "
              "jusqu'à 16h50/17h10 en descente).",
    "combloux": "Liaison du Jaillet : 9h10–16h45 (vers Combloux), "
                "9h10–16h15 (vers La Giettaz).",
    "la-clusaz": "Remontées mécaniques : 9h–16h30.",
    "le-grand-bornand": "Remontées mécaniques : 9h–17h.",
    "le-reposoir": "Remontées : 9h–17h (7j/7 pendant les vacances scolaires ; "
                   "mercredi, samedi et dimanche hors vacances).",
    "les-brasses": "Remontées mécaniques : 9h–16h30, tous les jours.",
    "manigod": "Remontées : 9h–16h30 tous les jours (caisses 8h30–16h30) ; "
               "ski nocturne 16h30–20h les vendredis et samedis.",
    "mont-saxonnex": "Remontées : 9h–17h (tous les jours pendant les vacances "
                     "scolaires ; mercredi, samedi et dimanche hors vacances).",
    "saint-gervais-les-bains": "Télécabine de l'Alpin (Le Bettex) : 8h30–17h10, "
                               "tous les jours.",
}


def fr_block(d):
    i18n = d.setdefault("i18n", {})
    return i18n.setdefault("fr", {})


def upsert_practical(blk, key, value):
    """Upsert a {k,v} practical_info entry by key (case-insensitive). Returns
    'set' | 'updated' | 'same'."""
    pi = blk.setdefault("practical_info", [])
    for e in pi:
        if isinstance(e, dict) and (e.get("k") or "").strip().lower() == key.lower():
            if e.get("v") == value:
                return "same"
            e["v"] = value
            return "updated"
    pi.append({"k": key, "v": value})
    return "set"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    src = json.load(open(SRC, encoding="utf-8"))

    tot = {"parking": 0, "hours": 0, "transport": 0, "pmr": 0, "pmr_null": 0}
    print(f"{'slug':26} {'park':5} {'hours':6} {'trans':6} {'pmr'}")
    for s in src:
        slug = s["slug"]
        fp = os.path.join(JSON_DIR, f"{slug}.json")
        if not os.path.exists(fp):
            print(f"{slug:26} MISSING FICHE — skipped"); continue
        d = json.load(open(fp, encoding="utf-8"))
        blk = fr_block(d)
        facts = blk.setdefault("facts", {}) if args.apply else (blk.get("facts") or {})
        row = {"park": "·", "hours": "·", "trans": "·", "pmr": "·"}

        # 1. parking → facts.parking
        pk = (s.get("parking") or {}).get("value")
        if pk:
            if facts.get("parking") != pk:
                if args.apply:
                    facts["parking"] = pk
                row["park"] = "set"; tot["parking"] += 1
            else:
                row["park"] = "same"

        # 2. hours → practical_info "Horaires" (daily clock hours only)
        hv = HOURS_DAILY.get(slug)
        if hv:
            st = upsert_practical(blk, "Horaires", hv) if args.apply else "set"
            row["hours"] = st
            if st in ("set", "updated"):
                tot["hours"] += 1

        # 3. transport → practical_info "Transports" (sourced narrative)
        tv = (s.get("transport") or {}).get("value")
        if tv:
            st = upsert_practical(blk, "Transports", tv) if args.apply else "set"
            row["trans"] = st
            if st in ("set", "updated"):
                tot["transport"] += 1

        # 4. access_pmr → top-level acces_pmr (only when status is sourced)
        a = s.get("access_pmr") or {}
        status = a.get("status")
        if status:
            obj = {
                "status": status,
                "detail": a.get("detail") or None,
                "equipment": [],
                "handiplage_level": None,
                "source_url": a.get("source_url") or None,
                "source_name": a.get("source_name") or None,
                "checked": CHECKED,
                "confidence": "official",
            }
            if args.apply:
                d["acces_pmr"] = obj
                # status is now sourced → the UNVERIFIED flag is stale, strip it.
                vf = d.get("verify_flags")
                if isinstance(vf, list):
                    d["verify_flags"] = [f for f in vf
                                         if not (isinstance(f, str) and UNVERIFIED_FLAG in f)]
            row["pmr"] = status; tot["pmr"] += 1
        else:
            row["pmr"] = "null(flagged)"; tot["pmr_null"] += 1

        print(f"{slug:26} {row['park']:5} {row['hours']:6} {row['trans']:6} {row['pmr']}")

        if args.apply:
            json.dump(d, open(fp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            if not open(fp, encoding="utf-8").read().endswith("\n"):
                open(fp, "a", encoding="utf-8").write("\n")

    print(f"\ntotals: parking={tot['parking']} hours={tot['hours']} "
          f"transport={tot['transport']} acces_pmr={tot['pmr']} "
          f"(null/left-flagged={tot['pmr_null']})")
    print("NEVER touched: winter · prices · season · best_season · price_tiers · schema_org")
    print("APPLIED" if args.apply else "(report only — nothing written)")


if __name__ == "__main__":
    main()
