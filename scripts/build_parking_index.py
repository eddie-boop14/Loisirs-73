#!/usr/bin/env python3
"""build_parking_index.py — nearest-parking engine (master to-do item 3).

Produces `data/parking_index.json`: for every published lieu, the nearest
public parking lots (≤ 600 m, top 3) from OpenStreetMap, each carrying an
HONEST tri-state fee badge that is never guessed. Re-run = fresh.

    Run:
        python3 scripts/build_parking_index.py
        python3 scripts/build_parking_index.py --offline   # use cached OSM pull

Feed
----
`amenity=parking` for the Haute-Savoie bbox via the Overpass API (live,
queryable, all tags). This is the handoff's sanctioned "raw Overpass"
upgrade over the weekly osm-france-parking-area extract — it is live,
precise to dept 74, and carries `fee` / `name` / `capacity` / `access`
directly. Licence ODbL → every rendered block must show
`© les contributeurs d'OpenStreetMap sous licence ODbL`.

The one rule — fee is TRI-STATE and never guessed
-------------------------------------------------
    fee=no            -> free        ("Gratuit")
    fee=yes           -> paid        ("Payant")
    fee=conditional / fee:conditional / any other non-empty fee value
                      -> conditional ("Sous conditions" + the condition)
    fee absent        -> unknown     ("À vérifier")
We NEVER emit "free" without an explicit fee=no. That restraint is the
trust edge.

Quality gate
------------
Keep a parking only if it has a NAME or a KNOWN fee (free/paid/conditional);
drop unnamed + unknown noise. Also drop clearly non-public lots
(access=private / access=no).
"""
from __future__ import annotations
import siteconfig  # HANDOFF-73 phase 5: per-site identity

import argparse
import glob
import json
import math
import sys
import time
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CACHE = DATA_DIR / "_osm_cache" / "parking_74.json"
OUT_PATH = DATA_DIR / "parking_index.json"

OVERPASS = "https://overpass-api.de/api/interpreter"
UA = f"{siteconfig.SITE_NAME.replace(' ', '')}-parking-index/1.0 ({siteconfig.PHOTOS_EMAIL})"

# Haute-Savoie bbox (S, W, N, E).
BBOX = siteconfig.BBOX or (45.55, 5.75, 46.45, 7.10)  # config first; literal is the 74 fallback

MAX_DIST_M = 600
TOP_N = 3
SAME_LOT_M = 30          # node + way for one lot, or near-dupes → merge

SOURCE = "OpenStreetMap"
LICENSE = "ODbL"
ATTRIB = "© les contributeurs d'OpenStreetMap sous licence ODbL"

# access values that mean "not public parking for a visitor"
NON_PUBLIC_ACCESS = {"private", "no"}


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def overpass_query(offline):
    """Return the raw Overpass JSON dict (cached). Retries with backoff."""
    if offline:
        if CACHE.exists():
            return json.loads(CACHE.read_text(encoding="utf-8"))
        raise SystemExit("--offline but no cached OSM pull at " + str(CACHE))
    s, w, n, e = BBOX
    q = (
        f"[out:json][timeout:170];"
        f'(node["amenity"="parking"]({s},{w},{n},{e});'
        f' way["amenity"="parking"]({s},{w},{n},{e}););'
        f"out tags center;"
    )
    last = None
    for attempt in range(4):
        try:
            r = requests.post(OVERPASS, data={"data": q},
                              headers={"User-Agent": UA}, timeout=180)
            if r.status_code == 200 and r.content[:1] == b"{":
                CACHE.parent.mkdir(parents=True, exist_ok=True)
                CACHE.write_text(r.text, encoding="utf-8")
                return r.json()
            last = f"status={r.status_code} first={r.content[:60]!r}"
        except Exception as ex:
            last = str(ex)
        wait = 2 ** (attempt + 2)   # 4, 8, 16, 32 — Overpass rate-limits hard
        print(f"    Overpass failed ({last}); retry in {wait}s")
        time.sleep(wait)
    if CACHE.exists():
        print("    using cached OSM pull (live fetch failed)")
        return json.loads(CACHE.read_text(encoding="utf-8"))
    raise RuntimeError(f"could not reach Overpass: {last}")


def classify_fee(tags):
    """Return (status, condition) — the tri-state, never guessed."""
    fee = (tags.get("fee") or "").strip().lower()
    cond_tag = tags.get("fee:conditional") or tags.get("fee:conditional:")
    if fee == "no":
        return "free", None
    if fee == "yes":
        return "paid", None
    if fee in ("conditional",) or cond_tag:
        return "conditional", (cond_tag or tags.get("fee:conditional") or "").strip() or None
    if fee:   # blue_zone, time-window, etc. — a real but non-binary condition
        return "conditional", fee
    return "unknown", None


def parse_parkings(osm):
    """Filtered, deduped list of public parkings from the Overpass payload."""
    raw = []
    for el in osm.get("elements", []):
        t = el.get("tags", {}) or {}
        if (t.get("access") or "").strip().lower() in NON_PUBLIC_ACCESS:
            continue
        c = el.get("center") or {"lat": el.get("lat"), "lon": el.get("lon")}
        try:
            lat, lon = float(c["lat"]), float(c["lon"])
        except (TypeError, KeyError, ValueError):
            continue
        name = (t.get("name") or "").strip()
        status, condition = classify_fee(t)
        # Quality gate: a name OR a known fee.
        if not name and status == "unknown":
            continue
        cap = t.get("capacity")
        capacity = int(cap) if (cap and str(cap).isdigit()) else None
        raw.append({"name": name, "status": status, "condition": condition,
                    "capacity": capacity, "lat": lat, "lon": lon})

    # Dedup: a lot mapped as both node and way, or near-duplicates with the
    # same name. Keep the richest record (named > unnamed, known fee > unknown).
    raw.sort(key=lambda p: (p["name"] == "", p["status"] == "unknown"))
    kept = []
    for p in raw:
        dup = False
        for q in kept:
            if haversine_m(p["lat"], p["lon"], q["lat"], q["lon"]) <= SAME_LOT_M and \
                    (p["name"].lower() == q["name"].lower() or not p["name"] or not q["name"]):
                dup = True
                break
        if not dup:
            kept.append(p)
    return kept


def nearest_parkings(lat, lon, parkings):
    cand = []
    for p in parkings:
        d = haversine_m(lat, lon, p["lat"], p["lon"])
        if d <= MAX_DIST_M:
            cand.append((d, p))
    cand.sort(key=lambda x: x[0])
    out = []
    for d, p in cand[:TOP_N]:
        entry = {
            "name": p["name"] or None,
            "status": p["status"],
            "distance_m": int(round(d)),
            "lat": round(p["lat"], 6),
            "lon": round(p["lon"], 6),
        }
        if p["capacity"] is not None:
            entry["capacity"] = p["capacity"]
        if p["condition"]:
            entry["condition"] = p["condition"]
        out.append(entry)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true",
                    help="Use the cached OSM pull (no network).")
    args = ap.parse_args()

    today = date.today().isoformat()
    print(f"build_parking_index — verification date {today}")
    print(f"Querying Overpass for amenity=parking in {siteconfig.DEPT_NAME} ...")
    osm = overpass_query(args.offline)
    feed_ts = osm.get("osm3s", {}).get("timestamp_osm_base", "")
    print(f"  OSM data timestamp: {feed_ts}")
    print(f"  raw parking elements: {len(osm.get('elements', []))}")

    parkings = parse_parkings(osm)
    print(f"  after quality gate + dedup + public-only: {len(parkings)}")

    index = {}
    empty = []
    null_coords = []
    total = 0
    for jp in sorted(glob.glob(str(ROOT / "Json" / "*.json"))):
        d = json.loads(Path(jp).read_text(encoding="utf-8"))
        if d.get("status") == "draft":
            continue
        total += 1
        slug = d["slug"]
        lat, lon = d.get("latitude"), d.get("longitude")
        if lat is None or lon is None:
            null_coords.append(slug)
            continue
        near = nearest_parkings(lat, lon, parkings)
        if not near:
            empty.append(slug)
            continue
        index[slug] = {
            "verified": today,
            "source": SOURCE,
            "license": LICENSE,
            "parkings": near,
        }

    payload = {
        "_meta": {
            "generated": today,
            "source": SOURCE,
            "license": LICENSE,
            "attribution": ATTRIB,
            "feed_timestamp": feed_ts,
            "max_distance_m": MAX_DIST_M,
            "top_n": TOP_N,
            "counts": {
                "lieux_total": total,
                "lieux_with_parking": len(index),
                "lieux_empty": len(empty),
                "lieux_null_coords": len(null_coords),
                "parkings_kept": len(parkings),
            },
        },
    }
    payload.update(index)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    print(f"\nWrote {OUT_PATH.relative_to(ROOT)}")
    print(f"  lieux total:              {total}")
    print(f"  lieux with ≥1 parking:    {len(index)}")
    print(f"  lieux with none ≤{MAX_DIST_M}m:   {len(empty)}")
    if null_coords:
        print(f"  lieux null coords:        {len(null_coords)} (skipped + flagged)")


if __name__ == "__main__":
    main()
