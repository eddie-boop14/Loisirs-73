#!/usr/bin/env python3
"""Extract slim candidate dataset for the Studio "Importer DT" tab.

Reads /tmp/dt2-report/candidates.csv (3056 in-scope, unmatched candidates) plus the
underlying DT records under /tmp/flux/objects/ and writes dt-candidates.json
(repo root) — one slim row per candidate, suitable for in-browser filtering.
"""
import csv
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FLUX = Path("/tmp/flux")
OUT = REPO / "dt-candidates.json"
CANDIDATES_CSV = Path("/tmp/dt2-report/candidates.csv")

HIGH_PRIORITY = {'CulturalSite', 'Museum', 'Castle', 'ArcheologicalSite',
                 'CityHeritage', 'CulturalRoute', 'Abbey', 'ReligiousSite',
                 'ParkAndGarden', 'schema:Park', 'Beach', 'Lake', 'Pond',
                 'Mountain', 'schema:Landform', 'NaturalHeritage',
                 'TourismCableCar', 'CableCarStation', 'TouristTrain',
                 'EducationalTrail', 'CrossCountrySkiTrail', 'CyclingTour',
                 'TourismCircuit', 'WalkingTour', 'Tour',
                 'ClimbingWall', 'schema:GolfCourse', 'schema:MovieTheater',
                 'schema:WaterPark', 'EquestrianCenter', 'NauticalCentre',
                 'SightseeingBoat', 'LeisureComplex', 'FitnessPath',
                 'RemarkableBuilding'}


def slugify(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s-]", " ", s.lower())
    s = re.sub(r"\b(le|la|les|des|de|du|d|l)\b", " ", s)
    s = re.sub(r"[\s_]+", "-", s).strip("-")
    return re.sub(r"-+", "-", s)


def primary_type(types):
    for t in types:
        if t in HIGH_PRIORITY:
            return t
    for t in types:
        if t not in ("PointOfInterest", "PlaceOfInterest", "schema:LocalBusiness"):
            return t
    return types[0] if types else "Unknown"


def first(v):
    if isinstance(v, list):
        return v[0] if v else None
    return v


def label(v, lang="fr"):
    if isinstance(v, dict):
        x = v.get(lang) or v.get("fr") or next(iter(v.values()), None)
        return first(x) or ""
    return first(v) or ""


def build_id_index():
    """Map dc:identifier → full DT record path."""
    index = {}
    for root, _, files in os.walk(FLUX / "objects"):
        for f in files:
            if not f.endswith(".json"):
                continue
            p = os.path.join(root, f)
            try:
                d = json.load(open(p))
            except Exception:
                continue
            dt_id = d.get("dc:identifier", "")
            if dt_id:
                index[str(dt_id)] = p
    return index


def extract_row(dt_id, dt_path, csv_row):
    d = json.load(open(dt_path))
    types = csv_row["types"].split("|")
    name = csv_row["label"]
    commune = csv_row["commune"]

    loc = first(d.get("isLocatedAt")) or {}
    addr = first(loc.get("schema:address")) or {}
    geo = loc.get("schema:geo") or {}
    creator = d.get("hasBeenCreatedBy") or {}
    if isinstance(creator, list):
        creator = creator[0] if creator else {}
    contact = first(d.get("hasContact")) or {}
    descs = first(d.get("hasDescription")) or {}
    sd_fr = first((descs.get("shortDescription") or {}).get("fr") or [])

    return {
        "id": dt_id,
        "name": name,
        "commune": commune,
        "postal": addr.get("schema:postalCode", ""),
        "lat": float(geo["schema:latitude"]) if geo.get("schema:latitude") else None,
        "lon": float(geo["schema:longitude"]) if geo.get("schema:longitude") else None,
        "type_bucket": "high" if set(types) & HIGH_PRIORITY else "medium",
        "type_primary": primary_type(types),
        "types": types,
        "creator": creator.get("schema:legalName", ""),
        "homepage": first(contact.get("foaf:homepage")) or "",
        "desc_fr": (sd_fr or "")[:280],  # snippet for preview
        "suggested_slug": slugify(f"{name}-{commune}") if commune else slugify(name),
    }


def main():
    if not CANDIDATES_CSV.exists():
        sys.exit(f"Missing {CANDIDATES_CSV} — run ingest_datatourisme.py --report first")
    if not (FLUX / "objects").exists():
        sys.exit(f"Missing {FLUX}/objects — flux not extracted")

    print(f"Indexing DT records...", flush=True)
    id_index = build_id_index()
    print(f"  indexed {len(id_index)} records")

    rows = []
    with open(CANDIDATES_CSV) as f:
        reader = csv.DictReader(f)
        for csv_row in reader:
            dt_id = csv_row["dt_id"]
            dt_path = id_index.get(str(dt_id))
            if not dt_path:
                continue
            try:
                rows.append(extract_row(dt_id, dt_path, csv_row))
            except Exception as e:
                print(f"  ! {dt_id}: {e}", file=sys.stderr)

    rows.sort(key=lambda r: (r["type_bucket"] != "high", r["commune"], r["name"]))
    payload = {
        "generated_at": "2026-06-09",
        "source": "DataTourisme flow #261672 (5508 records, partial_2)",
        "count": len(rows),
        "rows": rows,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
                   encoding="utf-8")
    size_kb = OUT.stat().st_size / 1024
    print(f"\n  ✓ {OUT} — {len(rows)} candidates, {size_kb:.0f} KB")


if __name__ == "__main__":
    main()
