#!/usr/bin/env python3
"""build_transport_index.py — GTFS freshness engine (HANDOFF PART B1).

Produces `data/transport_index.json`: for every published lieu, the nearest
public-transport stops (≤ 1200 m, top 3) resolved from the operators' own
open GTFS feeds, each stamped with the build/verification date and an Etalab
attribution. Re-running this script = a fresh index. Nothing is hand-typed;
unresolved feeds are flagged, never faked.

    Run:
        python3 scripts/build_transport_index.py
        python3 scripts/build_transport_index.py --offline   # use cached zips only

Feed resolution
---------------
Feeds are resolved at run time from the national access point
(transport.data.gouv.fr) `/api/datasets` listing — we never hardcode a
resource download URL. For each network below we look up its dataset by
slug, pick its current GTFS resource, and read that resource's live `url`.

Network set (individual feeds, not the AURA "Oùra" aggregate)
-------------------------------------------------------------
The handoff floated the `agregat-oura` regional aggregate as a catch-all.
We deliberately use the individual member feeds instead: the whole point of
the rendered block is to *name the operator*, and a single stop in the
aggregate cannot be attributed to an operator from `stops.txt` alone (that
needs a routes/trips/agency join across a multi-agency feed). Individual
feeds give a clean, verbatim operator label and a smaller, per-network
freshness date. The selected feeds cover every major Haute-Savoie travel
hub: Annecy (SIBRA), the whole department (Cars Région 74 / LIHSA),
Annemasse (TAC), the Chamonix valley, Rumilly (Jybus), and rail (SNCF/TER,
which carries the French Léman Express stops).

Networks that could not be resolved to a live GTFS feed are reported in the
run log and recorded under `_meta.unresolved` — not invented.
"""
from __future__ import annotations

import argparse
import csv
import glob
import io
import json
import math
import sys
import time
import zipfile
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "_gtfs_cache"
OUT_PATH = DATA_DIR / "transport_index.json"

PAN_DATASETS = "https://transport.data.gouv.fr/api/datasets"

# Haute-Savoie generous bounding box — pre-filters national feeds (SNCF) down
# to local stops before the per-lieu haversine. (S/W .. N/E corners.)
HS_BBOX = (45.5, 5.7, 46.55, 7.15)  # (lat_min, lon_min, lat_max, lon_max)

MAX_DIST_M = 1200       # keep stops within this radius of a lieu
TOP_N = 3               # ... and at most this many per lieu
SAME_STOP_M = 35        # two candidates within this distance + same name = one stop

LICENSE = "Licence Etalab 2.0"
SOURCE = "transport.data.gouv.fr"

# (dataset_slug, operator_label, attach_lines)
#   attach_lines=True  -> join stop_times/trips/routes for serving line names
#   attach_lines=False -> skip the join (rail: huge, line names not useful here)
NETWORKS = [
    ("offre-de-transports-sibra-a-annecy-gtfs",        "SIBRA",                      True),
    ("reseau-interurbain-cars-region-haute-savoie-74", "Cars Région Haute-Savoie",   True),
    ("offre-de-transports-reseau-tac-annemasse-agglo", "TAC",                        True),
    ("gtfs-reseau-chamonix-mobilite",                  "Chamonix Bus",               True),
    ("offre-de-transports-jybus-a-rumilly",            "Jybus",                      True),
    ("horaires-sncf",                                  "SNCF (TER)",                 False),
]

# Networks known to exist but not currently resolvable to a GTFS feed on the
# national access point — recorded so the gap is visible, never fabricated.
KNOWN_UNRESOLVED = [
    "Proxim'iTi (Thonon Agglomération) — dataset present on PAN but no GTFS resource",
    "CGN (Compagnie Générale de Navigation, lake boats) — Swiss source, not on transport.data.gouv.fr",
]


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def in_bbox(lat, lon):
    return HS_BBOX[0] <= lat <= HS_BBOX[2] and HS_BBOX[1] <= lon <= HS_BBOX[3]


def fetch_dataset_index():
    """Return {slug: dataset} from the PAN datasets listing (with retries)."""
    last = None
    for attempt in range(4):
        try:
            r = requests.get(PAN_DATASETS, timeout=60)
            r.raise_for_status()
            return {d.get("slug"): d for d in r.json() if d.get("slug")}
        except Exception as e:  # network blip — exp backoff
            last = e
            wait = 2 ** (attempt + 1)
            print(f"    PAN listing failed ({e}); retry in {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"could not reach PAN datasets API: {last}")


def resolve_gtfs(dataset):
    """Pick the current GTFS resource of a dataset; return (url, meta) or None."""
    for res in dataset.get("resources", []):
        if res.get("format") == "GTFS":
            url = res.get("original_url") or res.get("url")
            md = res.get("metadata") or {}
            return url, {
                "start_date": md.get("start_date"),
                "end_date": md.get("end_date"),
                "updated": res.get("updated"),
            }
    return None


def download_zip(url, cache_name, offline=False):
    """Download a GTFS zip (4 retries, exp backoff); cache to disk. In offline
    mode read only from cache. Returns bytes or None."""
    cache = CACHE_DIR / cache_name
    if offline:
        return cache.read_bytes() if cache.exists() else None
    last = None
    for attempt in range(4):
        try:
            r = requests.get(url, timeout=120, allow_redirects=True)
            if r.status_code == 200 and r.content[:2] == b"PK":
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                cache.write_bytes(r.content)
                return r.content
            last = f"status={r.status_code} first={r.content[:48]!r}"
        except Exception as e:
            last = str(e)
        wait = 2 ** (attempt + 1)
        print(f"    download failed ({last}); retry in {wait}s")
        time.sleep(wait)
    # fall back to a stale cache copy rather than dropping the network entirely
    if cache.exists():
        print(f"    using cached copy of {cache_name} (live fetch failed)")
        return cache.read_bytes()
    return None


def _read_csv(zf, name):
    if name not in zf.namelist():
        return []
    with zf.open(name) as f:
        return list(csv.DictReader(io.TextIOWrapper(f, "utf-8-sig")))


def feed_validity(zf, meta):
    """Prefer feed_info.txt validity; fall back to the resource metadata."""
    rows = _read_csv(zf, "feed_info.txt")
    if rows:
        s = rows[0].get("feed_start_date") or ""
        e = rows[0].get("feed_end_date") or ""
        def fmt(x):
            return f"{x[0:4]}-{x[4:6]}-{x[6:8]}" if len(x) == 8 else (x or None)
        if s or e:
            return fmt(s), fmt(e)
    return meta.get("start_date"), meta.get("end_date")


def stop_lines_map(zf):
    """Build stop_id -> sorted[route_short_name] via stop_times→trips→routes.
    Returns {} if any required file is absent."""
    routes = _read_csv(zf, "routes.txt")
    trips = _read_csv(zf, "trips.txt")
    if not routes or not trips:
        return {}
    route_name = {r["route_id"]: (r.get("route_short_name") or "").strip()
                  for r in routes if r.get("route_id")}
    trip_route = {t["trip_id"]: t.get("route_id") for t in trips if t.get("trip_id")}
    out: dict[str, set] = {}
    # stop_times can be large — stream it instead of materialising the list.
    if "stop_times.txt" not in zf.namelist():
        return {}
    with zf.open("stop_times.txt") as f:
        for row in csv.DictReader(io.TextIOWrapper(f, "utf-8-sig")):
            sid = row.get("stop_id")
            rid = trip_route.get(row.get("trip_id"))
            if not sid or rid is None:
                continue
            name = route_name.get(rid, "")
            if name:
                out.setdefault(sid, set()).add(name)
    return out


def read_agency(zf):
    """Return {"url": agency_url, "fare_url": agency_fare_url} from agency.txt.

    Both come straight from the feed (required/optional GTFS fields) — never
    typed or guessed. For multi-agency feeds we take the most common non-blank
    value. Missing values are omitted (so the caller can flag a blank url).
    """
    rows = _read_csv(zf, "agency.txt")
    if not rows:
        return {}
    from collections import Counter
    def pick(col):
        vals = [(r.get(col) or "").strip() for r in rows]
        vals = [v for v in vals if v]
        return Counter(vals).most_common(1)[0][0] if vals else ""
    out = {}
    url = pick("agency_url")
    fare_url = pick("agency_fare_url")
    if url:
        out["url"] = url
    if fare_url:
        out["fare_url"] = fare_url
    return out


def load_feed(slug, operator, attach_lines, dataset_index, offline):
    """Resolve, download and read one network feed.

    Returns (stops, validity, agency, info) where stops is a list of dicts
    {name, operator, lat, lon, lines:[...]} pre-filtered to the HS bbox and
    agency is {"url", "fare_url"} read verbatim from agency.txt.
    Returns (None, None, None, reason) on failure.
    """
    ds = dataset_index.get(slug)
    if not ds:
        return None, None, None, f"dataset slug not found on PAN: {slug}"
    resolved = resolve_gtfs(ds)
    if not resolved:
        return None, None, None, f"no GTFS resource in dataset: {slug}"
    url, meta = resolved
    content = download_zip(url, f"{slug}.zip", offline=offline)
    if content is None:
        return None, None, None, f"download failed: {slug}"
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        return None, None, None, f"corrupt zip: {slug}"

    validity = feed_validity(zf, meta)
    agency = read_agency(zf)
    lines_map = stop_lines_map(zf) if attach_lines else {}

    stops = []
    for row in _read_csv(zf, "stops.txt"):
        # location_type 1 = station (parent); 2/3/4 = entrances/nodes. Keep
        # actual boarding stops (0/empty) and stations.
        lt = (row.get("location_type") or "0").strip()
        if lt not in ("", "0", "1"):
            continue
        try:
            lat = float(row["stop_lat"])
            lon = float(row["stop_lon"])
        except (KeyError, ValueError, TypeError):
            continue
        if not in_bbox(lat, lon):
            continue
        name = (row.get("stop_name") or "").strip()
        if not name:
            continue
        lines = sorted(lines_map.get(row.get("stop_id"), ()), key=_line_sort_key)
        stops.append({"name": name, "operator": operator,
                      "lat": lat, "lon": lon, "lines": lines})
    return stops, validity, agency, f"{len(stops)} stops in bbox"


def _line_sort_key(s):
    """Sort line names naturally: numeric first by value, then alphabetic."""
    return (0, int(s), "") if s.isdigit() else (1, 0, s)


def _norm(name):
    return " ".join(name.lower().split())


import re as _re
_LINE_RE = _re.compile(r"\blignes?\s+([0-9A-Za-z]{1,4})\b", _re.I)


def public_transport_prose(d):
    """Return the FR curated how_to_get_there.public_transport string, if any."""
    fr = (d.get("i18n", {}) or {}).get("fr", {}) or {}
    body = fr.get("body") if isinstance(fr.get("body"), dict) else {}
    how = (body or {}).get("how_to_get_there") or fr.get("how_to_get_there") or {}
    if isinstance(how, dict):
        return how.get("public_transport") or ""
    return ""


def prose_line_tokens(text):
    """Extract line identifiers cited in prose, e.g. 'ligne 15' -> {'15'}.
    Drops bare words that are not plausible line codes."""
    if not text:
        return set()
    out = set()
    for m in _LINE_RE.finditer(text):
        tok = m.group(1).strip()
        # a plausible line code has at least one digit (15, Y51, J5) — skip
        # accidental captures like 'ligne de' truncations.
        if any(c.isdigit() for c in tok):
            out.add(tok)
    return out


def nearest_stops(lat, lon, all_stops):
    """Top-N unique physical stops within MAX_DIST_M of (lat, lon).

    Candidates from different feeds that are the same physical stop (same
    normalised name within SAME_STOP_M) are merged: operators joined, lines
    unioned.
    """
    cand = []
    for s in all_stops:
        d = haversine_m(lat, lon, s["lat"], s["lon"])
        if d <= MAX_DIST_M:
            cand.append((d, s))
    cand.sort(key=lambda x: x[0])

    picked = []  # list of dicts being assembled
    for d, s in cand:
        merged = None
        for p in picked:
            if _norm(p["name"]) == _norm(s["name"]) and \
                    haversine_m(p["_lat"], p["_lon"], s["lat"], s["lon"]) <= SAME_STOP_M:
                merged = p
                break
        if merged:
            ops = merged["operator"].split(" / ")
            if s["operator"] not in ops:
                merged["operator"] = " / ".join(ops + [s["operator"]])
            merged["lines"] = sorted(set(merged["lines"]) | set(s["lines"]),
                                     key=_line_sort_key)
            continue
        if len(picked) >= TOP_N:
            continue
        picked.append({
            "name": s["name"],
            "operator": s["operator"],
            "distance_m": int(round(d)),
            "lines": list(s["lines"]),
            "_lat": s["lat"], "_lon": s["lon"],
        })
    # strip private fields, preserve nearest-first order
    out = []
    for p in picked:
        entry = {"name": p["name"], "operator": p["operator"],
                 "distance_m": p["distance_m"]}
        if p["lines"]:
            entry["lines"] = p["lines"]
        out.append(entry)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true",
                    help="Use cached GTFS zips only (no network).")
    args = ap.parse_args()

    today = date.today().isoformat()
    print(f"build_transport_index — verification date {today}")
    print("Resolving feeds via transport.data.gouv.fr/api/datasets ...")
    dataset_index = fetch_dataset_index()

    all_stops = []
    feeds_meta = []
    operators = {}            # operator label -> {"url", "fare_url"} from agency.txt
    unresolved = list(KNOWN_UNRESOLVED)
    for slug, operator, attach_lines in NETWORKS:
        stops, validity, agency, info = load_feed(slug, operator, attach_lines,
                                                  dataset_index, args.offline)
        if stops is None:
            print(f"  [SKIP] {operator:28} {info}")
            unresolved.append(f"{operator} ({slug}): {info}")
            continue
        vfrom, vto = validity
        agency = agency or {}
        if not agency.get("url"):
            print(f"         (no agency_url in {operator} feed — official link omitted)")
        operators[operator] = agency
        print(f"  [ OK ] {operator:28} stops={len(stops):<5} "
              f"valid {vfrom}→{vto}  url={agency.get('url', '—')}")
        all_stops.extend(stops)
        feeds_meta.append({"operator": operator, "slug": slug,
                           "valid_from": vfrom, "valid_to": vto,
                           "stops_in_bbox": len(stops)})

    if not all_stops:
        print("No feeds resolved — aborting without writing the index.", file=sys.stderr)
        sys.exit(1)
    print(f"\nTotal stops (HS bbox, all feeds): {len(all_stops)}")

    # ---- per-lieu nearest-stop join ----------------------------------------
    index = {}
    empty = []
    null_coords = []
    line_conflicts = []   # prose line numbers the feed doesn't corroborate nearby
    total = 0
    for jp in sorted(glob.glob(str(ROOT / "Json" / "*.json"))):
        d = json.loads(Path(jp).read_text(encoding="utf-8"))
        if d.get("status") in ("draft", "unverified"):
            continue
        total += 1
        slug = d["slug"]
        lat, lon = d.get("latitude"), d.get("longitude")
        if lat is None or lon is None:
            null_coords.append(slug)
            continue
        stops = nearest_stops(lat, lon, all_stops)
        if not stops:
            empty.append(slug)
            continue
        index[slug] = {
            "verified": today,
            "source": SOURCE,
            "license": LICENSE,
            "stops": stops,
        }
        # Line-number conflict check: compare line numbers cited in the curated
        # public_transport prose against the lines the feed shows on nearby
        # stops. Disagreements are FLAGGED for human review — never auto-edited
        # (a script must not pick a winner between editor and feed).
        prose_lines = prose_line_tokens(public_transport_prose(d))
        feed_lines = {ln.upper() for s in stops for ln in s.get("lines", [])}
        unconfirmed = sorted(t for t in prose_lines if t.upper() not in feed_lines)
        if unconfirmed and feed_lines:
            line_conflicts.append({
                "slug": slug,
                "prose_lines": sorted(prose_lines),
                "feed_lines_nearby": sorted(feed_lines),
                "unconfirmed": unconfirmed,
            })

    payload = {
        "_meta": {
            "generated": today,
            "source": SOURCE,
            "license": LICENSE,
            "max_distance_m": MAX_DIST_M,
            "top_n": TOP_N,
            "feeds": feeds_meta,
            "operators": operators,
            "unresolved": unresolved,
            "line_conflicts": line_conflicts,
            "counts": {
                "lieux_total": total,
                "lieux_with_stops": len(index),
                "lieux_empty": len(empty),
                "lieux_null_coords": len(null_coords),
                "line_conflicts": len(line_conflicts),
            },
        },
    }
    payload.update(index)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    # ---- run report ---------------------------------------------------------
    print(f"\nWrote {OUT_PATH.relative_to(ROOT)}")
    print(f"  lieux total:            {total}")
    print(f"  lieux with ≥1 stop:     {len(index)}")
    print(f"  lieux with no stop ≤{MAX_DIST_M}m: {len(empty)} "
          f"(remote/alpine — legitimately empty)")
    if null_coords:
        print(f"  lieux with null coords: {len(null_coords)} (skipped + flagged)")
    if unresolved:
        print("  unresolved feeds (flagged, not faked):")
        for u in unresolved:
            print(f"    - {u}")
    print(f"\n  operators with official link: "
          f"{sum(1 for o in operators.values() if o.get('url'))}/{len(operators)}")
    if line_conflicts:
        print(f"\n  LINE-NUMBER CONFLICTS — {len(line_conflicts)} fiche(s) cite a line "
              f"the feed doesn't show nearby (human review, NOT auto-edited):")
        for c in line_conflicts:
            print(f"    - {c['slug']}: prose={c['prose_lines']} "
                  f"nearby_feed={c['feed_lines_nearby']} unconfirmed={c['unconfirmed']}")


if __name__ == "__main__":
    main()
