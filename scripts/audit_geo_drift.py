#!/usr/bin/env python3
"""Coordinate-quality triage: turn drift into a fix queue (SPECgeoverify §G4).

279 fiches carry a Google place_id + a measured gps_drift_m; 113 have no Google
match at all. Where the stored coordinate disagrees with Google by a lot, either
the stored coord is wrong (the off-venue-pin bug) or Google matched the wrong
place (generic names). This script splits the disagreement into three buckets
and writes reports/geo-drift-triage.md:

  FIX-COORD  drift > 150 m AND strong name-match (overlap >= 0.6)
             -> the stored coord is almost certainly wrong. We have Google's
                lat/lng (google_check.google_lat/lng); propose it as the fix.
                Do NOT auto-apply.

  RE-MATCH   drift > 150 m AND weak name-match (overlap < 0.6)
             -> Google likely matched the WRONG place (generic name). Never
                trust Google's coord here; needs a better query / human eyes.

  NO-MATCH   no place_id + no drift (the 113)
             -> re-query / manual.

`--apply-fix-coord` (gated, OFF by default) does NOT rewrite coordinates itself.
It EMITS one Studio patch file per FIX-COORD fiche under
reports/geo-fixcoord-patches/, each setting latitude+longitude to Google's
values. Those are applied — when a human chooses to — via apply_studio_patch.py,
which enforces the no-clobber / no-silent-key-drop semantics. Coordinates are
therefore never canonicalised without (a) a human reading this report and (b)
the patch passing apply_studio_patch's guards.

Read-only by default: with no flags it only writes the markdown report.
"""
import argparse
import glob
import json
import os
import re
import sys
import unicodedata

JSON_DIR = "Json"
REPORT = "reports/geo-drift-triage.md"
PATCH_DIR = "reports/geo-fixcoord-patches"
DRIFT_TRIAGE = 150          # > this enters triage (beyond the grey band)
NAME_OVERLAP_MIN = 0.6      # same bar as derive_geo_verified

# Haute-Savoie bounding box (padded). A "strong name-match" is NOT enough to
# trust Google's coord: same-named places exist all over France (a "Château de
# Bellegarde" near Orléans, a "Parc de pêche" in Limousin). If Google's proposed
# coordinate falls OUTSIDE the department, that is itself proof Google matched
# the wrong place — such fiches are RE-MATCH, never FIX-COORD, however well the
# name scores. Guards the report from proposing 350 km clobbers.
HS_LAT_MIN, HS_LAT_MAX = 45.60, 46.50
HS_LNG_MIN, HS_LNG_MAX = 5.70, 7.10


def in_haute_savoie(lat, lng):
    if lat is None or lng is None:
        return False
    return HS_LAT_MIN <= lat <= HS_LAT_MAX and HS_LNG_MIN <= lng <= HS_LNG_MAX

STOP = {
    "de", "la", "le", "les", "du", "des", "d", "l", "a", "au", "aux",
    "et", "en", "sur", "sous", "the", "of", "and",
}


def get_path(d, *path):
    cur = d
    for key in path:
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return None
    return cur


def norm_tokens(s):
    if not s:
        return set()
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return {t for t in re.findall(r"[a-z0-9]+", s.lower()) if t not in STOP}


def name_overlap(name, match):
    a, b = norm_tokens(name), norm_tokens(match)
    return len(a & b) / len(a) if a else 0.0


def fiche_name(d):
    i18n = d.get("i18n", {}) or {}
    return (get_path(i18n, "fr", "name")
            or get_path(i18n, "en", "name")
            or d.get("slug"))


def classify(d):
    """Return a dict describing the fiche's triage state."""
    place_id = (get_path(d, "google_check", "place_id")
                or get_path(d, "freshness", "place_id"))
    drift = get_path(d, "google_check", "gps_drift_m")
    if drift is None:
        drift = get_path(d, "freshness", "gps_drift_m")
    match = (get_path(d, "freshness", "google_match")
             or get_path(d, "google_check", "match"))
    name = fiche_name(d)
    overlap = name_overlap(name, match) if match else 0.0
    glat = get_path(d, "google_check", "google_lat")
    glng = get_path(d, "google_check", "google_lng")

    google_in_region = in_haute_savoie(glat, glng)
    reason = ""
    if not place_id and drift is None:
        bucket = "NO-MATCH"
    elif drift is not None and drift > DRIFT_TRIAGE:
        if overlap < NAME_OVERLAP_MIN:
            bucket, reason = "RE-MATCH", f"weak name (overlap {overlap:.2f})"
        elif glat is None or glng is None:
            bucket, reason = "RE-MATCH", "strong name but no Google coord stored"
        elif not google_in_region:
            bucket, reason = "RE-MATCH", (
                f"Google coord {glat:.4f},{glng:.4f} outside Haute-Savoie "
                f"(same-named place elsewhere)")
        else:
            bucket = "FIX-COORD"
    else:
        bucket = "OK"  # within band — verified or close; not in triage

    return {
        "slug": d.get("slug"), "name": name, "match": match, "overlap": overlap,
        "drift": drift, "bucket": bucket, "place_id": place_id,
        "stored_lat": d.get("latitude"), "stored_lng": d.get("longitude"),
        "google_lat": glat, "google_lng": glng, "reason": reason,
        "google_in_region": google_in_region,
        "verified": d.get("geo_verified") is True,
    }


def md_table(rows, headers):
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def write_patches(fixcoord):
    """Emit one Studio patch file per FIX-COORD fiche (does NOT apply them)."""
    os.makedirs(PATCH_DIR, exist_ok=True)
    written, skipped = [], []
    for r in fixcoord:
        if r["google_lat"] is None or r["google_lng"] is None:
            skipped.append(r["slug"])
            continue
        patch = {
            "slug": r["slug"],
            "source": "audit_geo_drift.py --apply-fix-coord",
            "patch": {
                "latitude": r["google_lat"],
                "longitude": r["google_lng"],
            },
        }
        path = os.path.join(PATCH_DIR, f"{r['slug']}-patch.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(patch, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        written.append(path)
    return written, skipped


def main():
    ap = argparse.ArgumentParser(description="Coordinate-drift triage report.")
    ap.add_argument("--json-dir", default=JSON_DIR)
    ap.add_argument("--report", default=REPORT)
    ap.add_argument("--apply-fix-coord", action="store_true",
                    help="GATED: emit Studio patch files for FIX-COORD fiches "
                         "(apply later via apply_studio_patch.py). Writes no "
                         "coordinates directly.")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.json_dir, "*.json")))
    if not files:
        print(f"::error::no fiches under {args.json_dir}/", file=sys.stderr)
        sys.exit(1)

    buckets = {"FIX-COORD": [], "RE-MATCH": [], "NO-MATCH": [], "OK": []}
    for f in files:
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        info = classify(d)
        buckets[info["bucket"]].append(info)

    fixc = sorted(buckets["FIX-COORD"], key=lambda r: -r["drift"])
    remat = sorted(buckets["RE-MATCH"], key=lambda r: -r["drift"])
    nomat = sorted(buckets["NO-MATCH"], key=lambda r: r["slug"])
    n_verified = sum(1 for b in buckets.values() for r in b if r["verified"])

    lines = []
    lines.append("# Coordinate-drift triage")
    lines.append("")
    lines.append(f"_Generated by `scripts/audit_geo_drift.py`. {len(files)} fiches. "
                 f"Triage threshold: drift > {DRIFT_TRIAGE} m. Name-overlap bar: "
                 f"{NAME_OVERLAP_MIN}._")
    lines.append("")
    lines.append("| bucket | count | meaning |")
    lines.append("|---|---|---|")
    lines.append(f"| **FIX-COORD** | {len(fixc)} | stored coord almost certainly wrong; Google's coord proposed |")
    lines.append(f"| **RE-MATCH** | {len(remat)} | Google matched the wrong place; needs a better query / human |")
    lines.append(f"| **NO-MATCH** | {len(nomat)} | no Google result; re-query / manual |")
    lines.append(f"| _OK (not in triage)_ | {len(buckets['OK'])} | within {DRIFT_TRIAGE} m ({n_verified} carry the ✅ stamp) |")
    lines.append("")
    lines.append("> Coordinates are **never** rewritten by this report. `--apply-fix-coord` "
                 "emits Studio patch files for the FIX-COORD set only; a human applies them "
                 "through `apply_studio_patch.py` (no-clobber) after reading this.")
    lines.append("")

    lines.append(f"## FIX-COORD ({len(fixc)}) — propose Google's coordinate")
    lines.append("")
    if fixc:
        rows = []
        for r in fixc:
            prop = (f"{r['google_lat']}, {r['google_lng']}"
                    if r["google_lat"] is not None else "_(no google coord stored)_")
            rows.append([r["slug"], f"{r['drift']} m", f"{r['overlap']:.2f}",
                         f"{r['stored_lat']}, {r['stored_lng']}", prop])
        lines.append(md_table(rows, ["slug", "drift", "overlap",
                                     "stored lat,lng", "proposed (Google)"]))
    else:
        lines.append("_none_")
    lines.append("")

    lines.append(f"## RE-MATCH ({len(remat)}) — Google matched the wrong place")
    lines.append("")
    if remat:
        rows = [[r["slug"], f"{r['drift']} m", f"{r['overlap']:.2f}",
                 repr(r["name"]), repr(r["match"]), r["reason"]] for r in remat]
        lines.append(md_table(rows, ["slug", "drift", "overlap",
                                     "fiche name", "google match", "why re-match"]))
    else:
        lines.append("_none_")
    lines.append("")

    lines.append(f"## NO-MATCH ({len(nomat)}) — no Google result")
    lines.append("")
    if nomat:
        rows = [[r["slug"], repr(r["name"]),
                 f"{r['stored_lat']}, {r['stored_lng']}"] for r in nomat]
        lines.append(md_table(rows, ["slug", "fiche name", "stored lat,lng"]))
    else:
        lines.append("_none_")
    lines.append("")

    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print(f"audit_geo_drift: wrote {args.report}")
    print(f"  FIX-COORD={len(fixc)}  RE-MATCH={len(remat)}  "
          f"NO-MATCH={len(nomat)}  OK={len(buckets['OK'])} ({n_verified} ✅)")

    if args.apply_fix_coord:
        written, skipped = write_patches(fixc)
        print(f"\n  --apply-fix-coord: emitted {len(written)} Studio patch file(s) "
              f"under {PATCH_DIR}/ (NOT applied).")
        if skipped:
            print(f"  {len(skipped)} FIX-COORD fiche(s) had no stored Google coord; skipped.")
        print(f"  Review, then apply individually, e.g.:")
        print(f"    python3 scripts/apply_studio_patch.py {PATCH_DIR}/<slug>-patch.json")


if __name__ == "__main__":
    main()
