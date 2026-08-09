#!/usr/bin/env python3
"""dt_null_fill.py — DATAtourisme (ARA, dept 74, leisure) null-fill.

Report-before-apply, nulls-only, low-risk fields ONLY. The feed fills official
URLs, geo, and official classements — NEVER price/booking/photo credits (absent
from DATAtourisme) and NEVER a verified value. Descriptions are research hints,
never published (our-own-words law).

  --report  (default) : match candidates -> fiches, live-check proposed URLs,
            write reports/dt-match-report.md (counts + strong lines + evidence
            + maj dates + dt_id). Writes NO fiche.
  --apply   : write ONLY official_site_url / geo (lat,lon,commune,postal) /
            facts.classement on STRONG matches where the fiche field is null.
            Logs dt_id in research_log. Never overwrites verified; never moves a
            geo_verified pin.

Matching (no shared key): commune from cp_commune split on '#'; name fuzzy via
difflib; GPS haversine.
  STRONG : fuzzy >=0.90 AND commune exact AND GPS <=150 m -> auto-eligible.
  WEAK   : fuzzy 0.70-0.90 or commune-only -> SUGGESTED, never auto-filled.
"""
import argparse
import siteconfig  # HANDOFF-73 phase 5: per-site identity
import glob
import json
import math
import os
import re
import unicodedata
import urllib.request
from difflib import SequenceMatcher

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_DIR = os.path.join(ROOT, "Json")
REPORT = os.path.join(ROOT, "reports", "dt-match-report.md")
DEFAULT_CANDIDATES = os.path.join(ROOT, "data", "dt-ara-74-candidates.json")
TODAY = "2026-07-21"

SCOPE = ('"This feed fills official URLs, geo, and official classements. It '
         "cannot fill price, booking, or photo credits - absent from "
         "DATAtourisme. The completeness gap closed here is the factual-"
         'reference layer, not the commercial layer."')

STRONG_FUZZY, WEAK_FUZZY, GPS_M = 0.90, 0.70, 150.0
OFFICIAL_CLASSEMENT = re.compile(r"classement officiel|etoile|étoile|\*", re.I)

_STOP = {"de", "du", "des", "la", "le", "les", "l", "d", "et", "a", "au", "aux",
         "the", "of", "musee", "parc", "chateau"}


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


def norm(s):
    s = strip_accents((s or "").lower())
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return " ".join(t for t in s.split() if t and t not in _STOP)


def fuzzy(a, b):
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def haversine_m(la1, lo1, la2, lo2):
    R = 6371000.0
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = math.radians(la2 - la1), math.radians(lo2 - lo1)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def load_candidates(path):
    d = json.load(open(path, encoding="utf-8"))
    rows = d if isinstance(d, list) else (d.get("rows") or d.get("candidates"))
    out = []
    for r in rows:
        cp = (r.get("cp_commune") or "").split("#")
        postal = cp[0].strip() if cp and cp[0].strip().isdigit() else None
        commune = cp[1].strip() if len(cp) > 1 else None
        try:
            lat = float(r["lat"]); lon = float(r["lon"])
        except (KeyError, ValueError, TypeError):
            lat = lon = None
        out.append({"dt_id": r.get("dt_id"), "name": r.get("name") or "",
                    "postal": postal, "commune": commune, "lat": lat, "lon": lon,
                    "website": (r.get("website") or "").strip(),
                    "maj": r.get("maj") or "",
                    "classement": (r.get("classement") or "").strip()})
    return out


def load_fiches():
    out = {}
    for p in sorted(glob.glob(os.path.join(JSON_DIR, "*.json"))):
        d = json.load(open(p, encoding="utf-8"))
        out[d["slug"]] = d
    return out


def fiche_name(d):
    return ((d.get("i18n") or {}).get("fr") or {}).get("name") or d.get("slug", "")


def match(cands, fiches):
    by_commune = {}
    for slug, d in fiches.items():
        by_commune.setdefault(norm(d.get("commune") or ""), []).append(slug)
    strong, weak = [], []
    for c in cands:
        cc = norm(c["commune"] or "")
        pool = by_commune.get(cc, []) if cc else []
        best = None
        for slug in pool:
            d = fiches[slug]
            r = fuzzy(c["name"], fiche_name(d))
            dist = None
            if c["lat"] is not None and d.get("latitude") is not None:
                dist = haversine_m(c["lat"], c["lon"], d["latitude"], d["longitude"])
            if best is None or r > best[1]:
                best = (slug, r, dist)
        if not best:
            continue
        slug, r, dist = best
        row = {"slug": slug, "cand": c, "ratio": r, "dist": dist}
        if r >= STRONG_FUZZY and dist is not None and dist <= GPS_M:
            strong.append(row)
        elif r >= WEAK_FUZZY:
            weak.append(row)
    return strong, weak


def url_live(url):
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method, headers={
                "User-Agent": f"Mozilla/5.0 ({siteconfig.WORDMARK} dt-null-fill link-check)"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return 200 <= resp.status < 400
        except Exception:  # noqa: BLE001
            continue
    return False


def proposed_fills(row, fiches, do_livecheck):
    d = fiches[row["slug"]]
    c = row["cand"]
    fills = []
    if not d.get("official_site_url") and c["website"]:
        live = url_live(c["website"]) if do_livecheck else None
        note = "live 200/3xx" if live else ("DEAD - skip" if live is False else "not checked")
        fills.append(("official_site_url", c["website"], note))
    if d.get("latitude") is None and c["lat"] is not None and not d.get("geo_verified"):
        fills.append(("latitude/longitude", f"{c['lat']},{c['lon']}", "geo null"))
    if not d.get("commune") and c["commune"]:
        fills.append(("commune", c["commune"], ""))
    if not d.get("postal_code") and c["postal"]:
        fills.append(("postal_code", c["postal"], ""))
    facts = ((d.get("i18n") or {}).get("fr") or {}).get("facts") or {}
    if not facts.get("classement") and c["classement"] and OFFICIAL_CLASSEMENT.search(c["classement"]):
        fills.append(("facts.classement", c["classement"], "official rating"))
    return fills


def write_report(strong, weak, n_cands, fiches, do_livecheck):
    fillable = [(row, proposed_fills(row, fiches, do_livecheck)) for row in strong]
    fillable = [(r, fs) for r, fs in fillable if fs]
    n_url = sum(1 for _, fs in fillable for f in fs if f[0] == "official_site_url" and f[2] == "live 200/3xx")
    n_dead = sum(1 for _, fs in fillable for f in fs if f[0] == "official_site_url" and "DEAD" in f[2])
    n_geo = sum(1 for _, fs in fillable for f in fs if f[0].startswith("lat"))
    n_class = sum(1 for _, fs in fillable for f in fs if f[0] == "facts.classement")
    L = ["# DATAtourisme null-fill - match report\n\n", SCOPE + "\n\n",
         f"Source: `dt-ara-74-candidates.json` - {n_cands} leisure POIs (dept 74) - generated {TODAY}\n\n",
         f"- **Strong** (fuzzy >={STRONG_FUZZY} + commune exact + GPS <={int(GPS_M)} m): "
         f"**{len(strong)}** - **Weak** (suggested, never auto): **{len(weak)}**\n",
         f"- Proposed fills on strong matches: **official_site_url** {n_url} live "
         f"(+{n_dead} dead skipped) - **geo** {n_geo} - **classement** {n_class}\n\n",
         "---\n\n## Strong matches with a proposed null-fill\n\n",
         "| fiche | dt name | maj | fuzzy | dist | field -> value | check |\n|---|---|---|---|---|---|---|\n"]
    for row, fills in sorted(fillable, key=lambda x: -x[0]["ratio"]):
        c = row["cand"]
        for (field, val, note) in fills:
            dist = f"{row['dist']:.0f} m" if row["dist"] is not None else "-"
            v = (str(val)[:48] + "…") if len(str(val)) > 49 else val
            L.append(f"| `{row['slug']}` | {c['name'][:40]} | {c['maj']} | {row['ratio']:.2f} | "
                     f"{dist} | {field} -> {v} | {note} |\n")
    L.append("\n_dt_id provenance logged per fill on --apply._\n\n---\n\n"
             "## Weak (SUGGESTED - never auto-filled, Eddie reviews)\n\n"
             "| fiche | dt name | commune | fuzzy | dt_id |\n|---|---|---|---|---|\n")
    for row in sorted(weak, key=lambda x: -x["ratio"])[:80]:
        c = row["cand"]
        L.append(f"| `{row['slug']}` | {c['name'][:38]} | {c['commune']} | {row['ratio']:.2f} | "
                 f"{(c['dt_id'] or '').split('/')[-1][:12]} |\n")
    if len(weak) > 80:
        L.append(f"\n_(+{len(weak) - 80} more weak suggestions omitted)_\n")
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    open(REPORT, "w", encoding="utf-8").write("".join(L))
    return fillable


def do_apply(strong, fiches, min_maj=None):
    n = 0
    for row in strong:
        # Freshness floor (HANDOFF: Eddie may hold pre-cutoff rows extra-safe).
        if min_maj and (row["cand"]["maj"] or "") < min_maj:
            continue
        fills = proposed_fills(row, fiches, True)
        if not fills:
            continue
        p = os.path.join(JSON_DIR, f"{row['slug']}.json")
        d = json.load(open(p, encoding="utf-8"))
        c = row["cand"]
        wrote = []
        for (field, val, note) in fills:
            if field == "official_site_url" and note == "live 200/3xx" and not d.get("official_site_url"):
                d["official_site_url"] = val; wrote.append(field)
            elif field == "latitude/longitude" and d.get("latitude") is None and not d.get("geo_verified"):
                lat, lon = val.split(","); d["latitude"] = float(lat); d["longitude"] = float(lon); wrote.append("geo")
            elif field == "commune" and not d.get("commune"):
                d["commune"] = val; wrote.append(field)
            elif field == "postal_code" and not d.get("postal_code"):
                d["postal_code"] = val; wrote.append(field)
            elif field == "facts.classement":
                facts = d.setdefault("i18n", {}).setdefault("fr", {}).setdefault("facts", {})
                if not facts.get("classement"):
                    facts["classement"] = val; wrote.append(field)
        if wrote:
            d.setdefault("research_log", []).append({
                "date": TODAY, "by": "DATAtourisme null-fill",
                "note": f"filled {', '.join(wrote)} from {c['dt_id']} (maj {c['maj']})"})
            with open(p, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2); f.write("\n")
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", default=DEFAULT_CANDIDATES)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--no-livecheck", action="store_true")
    ap.add_argument("--min-maj", default=None,
                    help="freshness floor YYYY-MM-DD; DT rows older than this are held")
    args = ap.parse_args()
    cands = load_candidates(args.candidates)
    fiches = load_fiches()
    strong, weak = match(cands, fiches)
    if args.apply:
        n = do_apply(strong, fiches, args.min_maj)
        print(f"APPLIED fills on {n} fiche(s) (strong, nulls-only, live URLs"
              + (f", maj >= {args.min_maj}" if args.min_maj else "") + ").")
    else:
        fillable = write_report(strong, weak, len(cands), fiches, not args.no_livecheck)
        print(f"REPORT -> {os.path.relpath(REPORT, ROOT)}")
        print(f"  {len(cands)} candidates - strong {len(strong)} - weak {len(weak)} - "
              f"strong-with-fills {len(fillable)}")


if __name__ == "__main__":
    main()
