#!/usr/bin/env python3
"""External venue audit via Nominatim (OSM).

Run LOCALLY (not in the deploy sandbox — Nominatim is blocked there).
Hits https://nominatim.openstreetmap.org once per fiche, compares the
returned commune + lat/lng with what we have, and writes
venue-audit-external.md.

Nominatim's usage policy: max 1 req/sec, must send a real User-Agent.
This script enforces both. ~5-6 min for 325 venues.

Caching: results are cached to .audit-cache/<slug>.json so subsequent
runs only hit Nominatim for fiches not yet cached. Delete the cache
directory to force a full re-scan.

Usage:
    python3 scripts/audit_venues_external.py            # all fiches
    python3 scripts/audit_venues_external.py --limit 20 # first 20 only
    python3 scripts/audit_venues_external.py --refresh  # clear cache
"""
import json
import siteconfig  # HANDOFF-73 phase 5: per-site identity
import glob
import os
import sys
import time
import math
import argparse
import urllib.parse
import urllib.request
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, ".audit-cache")
REPORT = os.path.join(ROOT, "venue-audit-external.md")

NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = f"{siteconfig.SITE_NAME.replace(' ', '')}-Audit/1.0 (contact: {siteconfig.PHOTOS_EMAIL})"


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def nominatim_search(name, commune):
    """Query Nominatim. Returns first result dict or None."""
    q = f"{name} {commune} Haute-Savoie France"
    url = (f"{NOMINATIM}?q={urllib.parse.quote(q)}"
           "&format=jsonv2&limit=1&addressdetails=1"
           "&countrycodes=fr")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
            return data[0] if data else None
    except Exception as e:
        return {"_error": str(e)}


def cached_search(slug, name, commune):
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = os.path.join(CACHE_DIR, f"{slug}.json")
    if os.path.exists(cache):
        return json.load(open(cache))
    result = nominatim_search(name, commune)
    with open(cache, "w") as f:
        json.dump(result or {}, f, ensure_ascii=False)
    # Rate limit: 1 req/sec
    time.sleep(1.05)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0,
                    help="audit only the first N fiches (0 = all)")
    ap.add_argument("--refresh", action="store_true",
                    help="clear cache before running")
    args = ap.parse_args()

    if args.refresh and os.path.isdir(CACHE_DIR):
        import shutil
        shutil.rmtree(CACHE_DIR)
        print("Cache cleared.")

    fiches = []
    for f in sorted(glob.glob(os.path.join(ROOT, "Json", "*.json"))):
        d = json.load(open(f))
        if d.get("slug"):
            fiches.append(d)
    if args.limit:
        fiches = fiches[:args.limit]

    print(f"Auditing {len(fiches)} fiches via Nominatim "
          f"(rate-limited; ~{len(fiches) * 1.1:.0f}s if uncached)")

    flags = []  # (slug, level, signal, detail)
    not_found = []
    errors = []

    for i, d in enumerate(fiches, 1):
        slug = d["slug"]
        name = d["i18n"]["fr"]["name"]
        commune = d.get("commune") or ""
        our_lat = d.get("latitude")
        our_lng = d.get("longitude")

        if i % 20 == 0 or i == 1:
            print(f"  [{i}/{len(fiches)}] {slug}")

        r = cached_search(slug, name, commune)
        if not r:
            not_found.append(slug)
            continue
        if "_error" in r:
            errors.append((slug, r["_error"]))
            continue

        # Nominatim returns lat/lon as strings; address.{village,town,city,...}
        try:
            nlat = float(r["lat"])
            nlng = float(r["lon"])
        except (KeyError, ValueError, TypeError):
            errors.append((slug, "missing lat/lon in result"))
            continue

        addr = r.get("address", {}) or {}
        # Possible commune fields, ordered by preference
        nominatim_commune = (addr.get("village") or addr.get("town")
                             or addr.get("municipality") or addr.get("city")
                             or addr.get("hamlet") or addr.get("locality") or "")

        # Distance between our coords and Nominatim's
        if our_lat and our_lng and isinstance(our_lat, (int, float)) and isinstance(our_lng, (int, float)):
            dist = haversine_km(float(our_lat), float(our_lng), nlat, nlng)
            if dist > 20:
                flags.append((slug, "ERR", "coord-gap",
                              f"{dist:.1f} km between our coords and OSM"))
            elif dist > 5:
                flags.append((slug, "WARN", "coord-gap",
                              f"{dist:.1f} km between our coords and OSM"))

        # Commune comparison (normalized)
        if nominatim_commune and commune:
            if norm(nominatim_commune) != norm(commune):
                flags.append((slug, "WARN", "commune-mismatch",
                              f"we say {commune!r}, OSM says {nominatim_commune!r}"))

    # Write report
    out = []
    out.append("# External venue audit (Nominatim / OSM)\n")
    out.append(f"Scanned **{len(fiches)}** fiches against Nominatim. "
               "Cached results in `.audit-cache/`.\n\n")

    by_level = {"ERR": [], "WARN": [], "INFO": []}
    for f in flags:
        by_level[f[1]].append(f)

    out.append("## Summary\n")
    out.append("| Level | Count |")
    out.append("|---|---:|")
    for lvl in ("ERR", "WARN", "INFO"):
        out.append(f"| {lvl} | {len(by_level[lvl])} |")
    out.append(f"| Not found in OSM | {len(not_found)} |")
    out.append(f"| Network errors  | {len(errors)} |")
    out.append("")

    for lvl in ("ERR", "WARN"):
        lst = by_level[lvl]
        if not lst:
            continue
        out.append(f"\n## {lvl} — {len(lst)} rows\n")
        out.append("| slug | signal | detail |")
        out.append("|---|---|---|")
        for slug, _, sig, det in sorted(lst):
            out.append(f"| `{slug}` | {sig} | {det} |")

    if not_found:
        out.append(f"\n## Not found in OSM ({len(not_found)})\n")
        out.append("(Venue couldn't be located by Nominatim. May be too small, "
                   "newly opened, or misnamed.)\n")
        for s in not_found:
            out.append(f"- `{s}`")

    if errors:
        out.append(f"\n## Network errors ({len(errors)})\n")
        for s, e in errors:
            out.append(f"- `{s}`: {e}")

    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")

    print(f"\nFlags: {sum(len(x) for x in by_level.values())} ({len(by_level['ERR'])} ERR, {len(by_level['WARN'])} WARN)")
    print(f"Not found in OSM: {len(not_found)}")
    print(f"Network errors:   {len(errors)}")
    print(f"\nReport: {REPORT}")


if __name__ == "__main__":
    main()
