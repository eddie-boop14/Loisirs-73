#!/usr/bin/env python3
"""Seed proximity-based `partners[]` entries onto sparse fiches from the
DataTourisme flow #261672 out-of-scope pool (restaurants, hotels, shops),
and extend the two hand-curated featured partners (Chalet du Tornet,
Chez Nous à la Plage) to other nearby fiches.

Modes:
    --report          Dry-run. Print per-fiche plan + CSV to /tmp/dt-partners-report.csv.
    --apply           Write partner cards onto fiches + add data_sources[] attribution.
    --extend-featured Replicate Chalet du Tornet + Chez Nous featured-business entries
                      onto nearby fiches whose category fits the editorial concept.
    --slug SLUG       Restrict to one fiche (debugging).
    --cap-km N        Distance cap (default 10).
    --max-per-fiche N Slot target (default 3).
    --only-empty      Skip fiches with any existing partners[] entry.
"""
import argparse
import csv
import json
import math
import os
import re
import sys
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FLUX = Path("/tmp/flux")
JSON_DIR = REPO / "Json"
TODAY = "2026-06-09"

# Skip these fiches entirely — user explicitly asked not to touch them
EXCLUDED_SLUGS = {"domaine-du-tornet", "plage-de-saint-jorioz"}

# DT @type → partner card type
RESTAURANT_TYPES = {"schema:Restaurant", "FoodEstablishment", "schema:FoodEstablishment",
                    "BistroOrWineBar", "HotelRestaurant"}
HEBERGEMENT_TYPES = {"schema:Hotel", "Accommodation", "schema:Accommodation",
                     "LodgingBusiness", "schema:LodgingBusiness", "Hotel", "HotelTrade"}
COMMERCE_TYPES = {"Store", "CraftsmanShop", "schema:Winery", "WineryProducer",
                  "schema:LocalBusiness"}
SKIP_TYPES = {"schema:Library", "schema:Event", "EntertainmentAndEvent",
              "SportsEvent", "CulturalEvent", "Tour", "WalkingTour"}

# Quality bar
MIN_DESC_LEN = 60
MAX_DESC_LEN = 200


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.lower().strip())


def slugify(s):
    s = norm(s)
    s = re.sub(r"\b(le|la|les|des|de|du|d|l|aux|au)\b", " ", s)
    s = re.sub(r"[^\w\s-]", " ", s)
    return re.sub(r"\s+", "-", s).strip("-")


def haversine_km(a_lat, a_lon, b_lat, b_lon):
    if None in (a_lat, a_lon, b_lat, b_lon):
        return float("inf")
    R = 6371.0
    p1, p2 = math.radians(float(a_lat)), math.radians(float(b_lat))
    dp = math.radians(float(b_lat) - float(a_lat))
    dl = math.radians(float(b_lon) - float(a_lon))
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _first(v):
    if isinstance(v, list):
        return v[0] if v else None
    return v


def _label(v, lang="fr"):
    if isinstance(v, dict):
        x = v.get(lang) or v.get("fr") or next(iter(v.values()), None)
        return _first(x) or ""
    return _first(v) or ""


def parse_dt_record(d):
    types = d.get("@type") or []
    if not isinstance(types, list):
        types = [types]
    loc = _first(d.get("isLocatedAt")) or {}
    addr = _first(loc.get("schema:address")) or {}
    geo = loc.get("schema:geo") or {}
    creator = d.get("hasBeenCreatedBy") or {}
    if isinstance(creator, list):
        creator = creator[0] if creator else {}
    contact = _first(d.get("hasContact")) or {}
    descs = _first(d.get("hasDescription")) or {}
    sd = descs.get("shortDescription") or {}
    fr_desc = _first(sd.get("fr") or []) or ""
    homepage = _first(contact.get("foaf:homepage")) or ""
    return {
        "id": d.get("dc:identifier", ""),
        "name": _label(d.get("rdfs:label")),
        "types": types,
        "commune": addr.get("schema:addressLocality", ""),
        "lat": float(geo["schema:latitude"]) if geo.get("schema:latitude") else None,
        "lon": float(geo["schema:longitude"]) if geo.get("schema:longitude") else None,
        "creator_name": creator.get("schema:legalName", ""),
        "creator_url": _first(creator.get("foaf:homepage")) or "",
        "last_update": d.get("lastUpdate", ""),
        "homepage": homepage,
        "phone": _first(contact.get("schema:telephone")) or "",
        "desc_fr": fr_desc.strip(),
    }


def categorize(types):
    """DT @type list → partner card type, or None to skip.

    Hebergement checked first: hotels often carry FoodEstablishment too, but
    a hotel-restaurant is primarily a hotel."""
    tset = set(types)
    if tset & SKIP_TYPES:
        return None
    in_scope = {"CulturalSite", "Museum", "Castle", "ArcheologicalSite", "Abbey",
                "ReligiousSite", "ParkAndGarden", "Beach", "Lake", "Pond", "Mountain",
                "schema:Landform", "TourismCableCar", "CableCarStation",
                "EducationalTrail", "CrossCountrySkiTrail", "CyclingTour",
                "ClimbingWall", "schema:GolfCourse", "schema:MovieTheater",
                "schema:WaterPark", "SightseeingBoat", "LeisureComplex"}
    if tset & in_scope:
        return None
    if tset & HEBERGEMENT_TYPES:
        return "hebergement"
    if tset & RESTAURANT_TYPES:
        return "restaurant"
    if tset & COMMERCE_TYPES:
        return "commerce"
    return None


LOW_VALUE_NAME_PREFIXES = (
    "office de tourisme", "office du tourisme", "bureau d'information",
    "bureau d information", "point d'information", "point d information",
    "point information", "syndicat d'initiative", "syndicat d initiative",
    "mairie ", "mairie de", "communauté de communes", "préfecture",
    "sous-préfecture",
)


def is_low_value_name(name):
    n = (name or "").lower()
    return any(n.startswith(p) for p in LOW_VALUE_NAME_PREFIXES)


def build_dt_pool():
    pool = []
    rejected = {"no_homepage": 0, "no_desc": 0, "no_gps": 0,
                "no_type_match": 0, "no_name": 0, "low_value_name": 0}
    for root, _, files in os.walk(FLUX / "objects"):
        for f in files:
            if not f.endswith(".json"):
                continue
            try:
                d = json.load(open(os.path.join(root, f)))
            except Exception:
                continue
            rec = parse_dt_record(d)
            ptype = categorize(rec["types"])
            if not ptype:
                rejected["no_type_match"] += 1
                continue
            if not rec["name"] or len(rec["name"]) < 4:
                rejected["no_name"] += 1
                continue
            if is_low_value_name(rec["name"]):
                rejected["low_value_name"] += 1
                continue
            if not rec["homepage"]:
                rejected["no_homepage"] += 1
                continue
            if len(rec["desc_fr"]) < MIN_DESC_LEN:
                rejected["no_desc"] += 1
                continue
            if rec["lat"] is None or rec["lon"] is None:
                rejected["no_gps"] += 1
                continue
            rec["partner_type"] = ptype
            pool.append(rec)
    return pool, rejected


def load_catalog():
    out = []
    for p in sorted(JSON_DIR.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        out.append({
            "slug": d.get("slug", p.stem),
            "name": d.get("i18n", {}).get("fr", {}).get("name") or d.get("name", ""),
            "commune": d.get("commune", ""),
            "lat": d.get("latitude"),
            "lon": d.get("longitude"),
            "category": d.get("category", ""),
            "data": d,
            "path": p,
        })
    return out


def existing_partner_names(d):
    out = set()
    for entry in (d.get("partners") or []) + (d.get("featured_businesses") or []):
        n = entry.get("name", "")
        if n:
            out.add(slugify(n))
    return out


def pick_partners_for_fiche(fiche, pool, catalog_slug_names, cap_km):
    existing = existing_partner_names(fiche["data"])
    candidates_by_type = {"restaurant": [], "hebergement": [], "commerce": []}
    for rec in pool:
        d = haversine_km(fiche["lat"], fiche["lon"], rec["lat"], rec["lon"])
        if d > cap_km:
            continue
        sn = slugify(rec["name"])
        if sn in existing or sn in catalog_slug_names:
            continue
        rec2 = dict(rec, distance_km=d)
        candidates_by_type[rec["partner_type"]].append(rec2)
    picked = {}
    for t, lst in candidates_by_type.items():
        lst.sort(key=lambda r: r["distance_km"])
        picked[t] = lst[0] if lst else None
    return picked


def build_partner_card(rec):
    desc = rec["desc_fr"]
    if len(desc) > MAX_DESC_LEN:
        cut = desc.rfind(". ", 0, MAX_DESC_LEN)
        if cut == -1:
            cut = MAX_DESC_LEN
        desc = desc[:cut].rstrip(".") + "."
    return {
        "tier": "recommended",
        "name": rec["name"],
        "type": rec["partner_type"],
        "url": rec["homepage"],
        "cta_text": "Voir le site →",
        "description": desc,
        "i18n": {"fr": {"description": desc}},
        "i18n_placeholder": True,
        "source": "datatourisme",
        "source_id": str(rec["id"]),
        "seeded_at": TODAY,
        "proximity_km": round(rec["distance_km"], 1),
    }


def build_invite(invite_type, fiche):
    commune = fiche.get("commune", "")
    name = fiche["name"] or "ce lieu"
    here = f"à {commune}" if commune else "à proximité"
    titles = {
        "restaurant": f"Un restaurant {here} ?",
        "hebergement": "Un hébergement proche ?",
        "commerce": f"Une boulangerie, un commerce {here} ?",
    }
    descs = {
        "restaurant": f"Vous accueillez les visiteurs de {name} ? Apparaissez ici.",
        "hebergement": f"Gîte, chambre d'hôtes, camping, location {here}.",
        "commerce": f"Partagez horaires et spécialités avec les visiteurs de {name}.",
    }
    return {
        "tier": "invite",
        "invite_type": invite_type,
        "i18n": {"fr": {"title": titles[invite_type], "desc": descs[invite_type]}},
    }


def already_seeded_dt(d):
    for p in d.get("partners") or []:
        if p.get("source") == "datatourisme":
            return True
    return False


def build_data_source_entry(dt_ids, last_update, creators):
    from collections import Counter
    creator_counts = Counter(creators)
    top_creator = creator_counts.most_common(1)[0][0] if creator_counts else ""
    return {
        "platform": "DataTourisme",
        "platform_url": "https://www.datatourisme.fr",
        "publisher": "Apidae Tourisme",
        "publisher_url": "https://www.apidae-tourisme.com/",
        "creator": top_creator or "multiple OT",
        "creator_url": "",
        "license": "Licence Ouverte 2.0 (Etalab)",
        "license_url": "https://www.etalab.gouv.fr/licence-ouverte-open-licence",
        "datatourisme_ids": sorted(set(dt_ids), key=str),
        "last_updated": last_update or TODAY,
        "fields_used": ["partners_proximity"],
    }


def cmd_report(args, pool, catalog, catalog_slug_names):
    out_csv = Path("/tmp/dt-partners-report.csv")
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fiches_to_touch = []
    for fiche in catalog:
        slug = fiche["slug"]
        if args.slug and slug != args.slug:
            continue
        if slug in EXCLUDED_SLUGS:
            continue
        if fiche["lat"] is None or fiche["lon"] is None:
            continue
        existing_partners = fiche["data"].get("partners") or []
        if args.only_empty and existing_partners:
            continue
        if already_seeded_dt(fiche["data"]):
            continue
        picked = pick_partners_for_fiche(fiche, pool, catalog_slug_names, args.cap_km)
        n_existing_real = sum(1 for p in existing_partners if p.get("tier") != "invite")
        if n_existing_real >= args.max_per_fiche and not args.only_empty:
            continue
        fiches_to_touch.append((fiche, picked))

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["slug", "category", "commune", "existing",
                    "resto", "resto_km", "hebergement", "heb_km",
                    "commerce", "com_km"])
        for fiche, picked in fiches_to_touch:
            existing = len(fiche["data"].get("partners") or [])
            r, h, c = picked["restaurant"], picked["hebergement"], picked["commerce"]
            w.writerow([
                fiche["slug"], fiche["category"], fiche["commune"], existing,
                r["name"] if r else "", f"{r['distance_km']:.1f}" if r else "",
                h["name"] if h else "", f"{h['distance_km']:.1f}" if h else "",
                c["name"] if c else "", f"{c['distance_km']:.1f}" if c else "",
            ])

    filled = sum(sum(1 for p in picked.values() if p) for _, picked in fiches_to_touch)
    print(f"Pool size: {len(pool)} qualified DT records")
    print(f"Fiches to touch: {len(fiches_to_touch)}")
    print(f"Partner cards to add: {filled}")
    print(f"Report: {out_csv}")


def cmd_apply(args, pool, catalog, catalog_slug_names):
    touched_slugs = []
    for fiche in catalog:
        slug = fiche["slug"]
        if args.slug and slug != args.slug:
            continue
        if slug in EXCLUDED_SLUGS:
            continue
        if fiche["lat"] is None or fiche["lon"] is None:
            continue
        existing_partners = fiche["data"].get("partners") or []
        n_existing_real = sum(1 for p in existing_partners if p.get("tier") != "invite")
        if args.only_empty and existing_partners:
            continue
        if n_existing_real >= args.max_per_fiche and not args.only_empty:
            continue
        if already_seeded_dt(fiche["data"]):
            continue
        picked = pick_partners_for_fiche(fiche, pool, catalog_slug_names, args.cap_km)
        if not any(picked.values()):
            continue

        existing_types = {p.get("type") for p in existing_partners if p.get("tier") != "invite"}
        new_partners = []
        dt_ids_added = []
        creators = []
        last_updates = []
        for slot_type in ("restaurant", "hebergement", "commerce"):
            if slot_type in existing_types:
                continue
            rec = picked.get(slot_type)
            if rec:
                new_partners.append(build_partner_card(rec))
                dt_ids_added.append(str(rec["id"]))
                if rec.get("creator_name"):
                    creators.append(rec["creator_name"])
                if rec.get("last_update"):
                    last_updates.append(rec["last_update"])
            else:
                new_partners.append(build_invite(slot_type, fiche))

        if not new_partners:
            continue

        kept_existing = [p for p in existing_partners if p.get("tier") != "invite"]
        fiche["data"]["partners"] = kept_existing + new_partners

        if dt_ids_added:
            ds_list = fiche["data"].get("data_sources") or []
            merged = False
            for ds in ds_list:
                if (ds.get("platform") == "DataTourisme"
                        and "partners_proximity" in (ds.get("fields_used") or [])):
                    existing_ids = set(ds.get("datatourisme_ids") or [])
                    existing_ids.update(dt_ids_added)
                    ds["datatourisme_ids"] = sorted(existing_ids, key=str)
                    merged = True
                    break
            if not merged:
                lu = max(last_updates) if last_updates else TODAY
                ds_list.append(build_data_source_entry(dt_ids_added, lu, creators))
                fiche["data"]["data_sources"] = ds_list

            rl = fiche["data"].get("research_log")
            if isinstance(rl, dict):
                rl = [rl]
            elif rl is None:
                rl = []
            rl.append({
                "date": TODAY,
                "by": "claude-seed-dt-partners",
                "note": f"Seeded {len(dt_ids_added)} partner cards from DataTourisme proximity (within {args.cap_km} km).",
            })
            fiche["data"]["research_log"] = rl

        fiche["path"].write_text(
            json.dumps(fiche["data"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        touched_slugs.append(slug)
        print(f"  + {slug}: {len(new_partners)} cards added "
              f"(R:{1 if picked.get('restaurant') else 0} "
              f"H:{1 if picked.get('hebergement') else 0} "
              f"C:{1 if picked.get('commerce') else 0})")

    Path("/tmp/dt-partner-touched-slugs.txt").write_text(
        "\n".join(touched_slugs) + "\n", encoding="utf-8")
    print(f"\nTouched: {len(touched_slugs)} fiches")
    print(f"Slug list: /tmp/dt-partner-touched-slugs.txt")


# ---------------------------------------------------------------------------
# EXTEND-FEATURED: Chalet du Tornet + Chez Nous à la Plage to nearby fiches
# ---------------------------------------------------------------------------

EXTEND_TARGETS = {
    "chalet-du-tornet": {
        "source_slug": "domaine-du-tornet",
        "anchor_lat": 45.970952,
        "anchor_lon": 6.032109,
        "cap_km": 10,
        "categories": {"attraction", "parc", "musee", "cascade", "point-de-vue", "jardin"},
    },
    "chez-nous-a-la-plage": {
        "source_slug": "plage-de-saint-jorioz",
        "anchor_lat": 45.8335,
        "anchor_lon": 6.1565,
        "cap_km": 10,
        "categories": {"lac", "plage", "sentier", "voie-verte", "attraction"},
    },
}


def cmd_extend_featured(args, catalog):
    touched = []
    for nickname, cfg in EXTEND_TARGETS.items():
        src_path = JSON_DIR / f"{cfg['source_slug']}.json"
        src_data = json.loads(src_path.read_text(encoding="utf-8"))
        featured = src_data.get("featured_businesses") or []
        if not featured:
            print(f"  ! {nickname}: no featured_businesses on source fiche {cfg['source_slug']}")
            continue
        source_entry = None
        nick_norm = slugify(nickname.replace("-", " "))
        for fb in featured:
            if slugify(fb.get("name", "")) == nick_norm:
                source_entry = fb
                break
        if source_entry is None and featured:
            source_entry = featured[0]
        if source_entry is None:
            print(f"  ! {nickname}: no matching featured entry on source")
            continue

        for fiche in catalog:
            if fiche["slug"] == cfg["source_slug"]:
                continue
            if fiche["slug"] in EXCLUDED_SLUGS:
                continue
            if fiche["category"] not in cfg["categories"]:
                continue
            if fiche["lat"] is None or fiche["lon"] is None:
                continue
            dist = haversine_km(cfg["anchor_lat"], cfg["anchor_lon"],
                                fiche["lat"], fiche["lon"])
            if dist > cfg["cap_km"]:
                continue
            existing = existing_partner_names(fiche["data"])
            if slugify(source_entry["name"]) in existing:
                continue
            cloned = dict(source_entry)
            cloned["proximity_km"] = round(dist, 1)
            cloned["source"] = "featured_extension"
            cloned["source_slug"] = cfg["source_slug"]
            cloned["seeded_at"] = TODAY
            fb_list = fiche["data"].get("featured_businesses") or []
            fb_list.append(cloned)
            fiche["data"]["featured_businesses"] = fb_list
            fiche["path"].write_text(
                json.dumps(fiche["data"], ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            touched.append(fiche["slug"])
            print(f"  + {fiche['slug']}: extended {source_entry['name']} ({dist:.1f} km)")

    if touched:
        p = Path("/tmp/dt-partner-touched-slugs.txt")
        prev = []
        if p.exists():
            prev = [s for s in p.read_text().splitlines() if s.strip()]
        p.write_text("\n".join(sorted(set(prev + touched))) + "\n", encoding="utf-8")
    print(f"\nExtended: {len(touched)} fiches")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--extend-featured", action="store_true")
    ap.add_argument("--slug")
    ap.add_argument("--cap-km", type=float, default=10.0)
    ap.add_argument("--max-per-fiche", type=int, default=3)
    ap.add_argument("--only-empty", action="store_true")
    args = ap.parse_args()

    if not any((args.report, args.apply, args.extend_featured)):
        ap.print_help()
        sys.exit(1)

    catalog = load_catalog()
    catalog_slug_names = {slugify(f["name"]) for f in catalog if f["name"]}

    if args.report or args.apply:
        print("Building DT partner pool...", flush=True)
        pool, rejected = build_dt_pool()
        print(f"  Pool: {len(pool)} qualified records")
        print(f"  Rejected: {rejected}")
        if args.report:
            cmd_report(args, pool, catalog, catalog_slug_names)
        if args.apply:
            cmd_apply(args, pool, catalog, catalog_slug_names)

    if args.extend_featured:
        catalog = load_catalog()
        cmd_extend_featured(args, catalog)


if __name__ == "__main__":
    main()
