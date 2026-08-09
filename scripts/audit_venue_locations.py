#!/usr/bin/env python3
"""Local audit: catch venue-location mismatches without external APIs.

Cross-checks each Json/<slug>.json across four signals:
  1. Slug-encoded commune    (e.g. slug ends with "-saint-jorioz")
  2. commune field
  3. Commune mentioned in i18n.fr.practical_info Adresse / Localisation
  4. lat/lng compared to known commune centroid (>10 km = flag)

Also flags:
  - lat/lng (0, 0) or null
  - lat/lng outside Haute-Savoie envelope (roughly 45.6-46.5 N, 5.8-7.2 E)

Writes venue-audit.md to repo root. Read-only — no fiches modified.
Run after every batch integration or whenever you suspect a commune is wrong.
"""
import json
import glob
import os
import re
import math

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Commune centroids (lat, lng) — extend as needed.
COMMUNE_CENTROID = {
    "Annecy": (45.8992, 6.1294),
    "Annemasse": (46.1933, 6.2350),
    "Cluses": (46.0617, 6.5817),
    "Sallanches": (45.9367, 6.6311),
    "Thonon-les-Bains": (46.3712, 6.4789),
    "Évian-les-Bains": (46.4011, 6.5886),
    "Chamonix-Mont-Blanc": (45.9237, 6.8694),
    "Megève": (45.8569, 6.6175),
    "Bonneville": (46.0801, 6.4093),
    "Rumilly": (45.8636, 5.9469),
    "Sciez": (46.3389, 6.3856),
    "Doussard": (45.7800, 6.2244),
    "Talloires-Montmin": (45.8408, 6.2247),
    "Yvoire": (46.3697, 6.3253),
    "Veyrier-du-Lac": (45.9089, 6.1819),
    "Manigod": (45.8689, 6.4203),
    "La Clusaz": (45.9050, 6.4244),
    "Morzine": (46.1797, 6.7081),
    "Samoëns": (46.0814, 6.7233),
    "Combloux": (45.8978, 6.6494),
    "Passy": (45.9244, 6.7036),
    "Faverges": (45.7497, 6.2942),
    "Seynod": (45.8742, 6.0958),
    "Cran-Gevrier": (45.9089, 6.1014),
    "Pringy": (45.9514, 6.1306),
    "Sevrier": (45.8606, 6.1378),
    "Sévrier": (45.8606, 6.1378),
    "Saint-Jorioz": (45.8328, 6.1631),
    "Argonay": (45.9408, 6.1517),
    "Poisy": (45.9389, 6.0786),
    "Sillingy": (45.9667, 6.0500),
    "Saint-Pierre-en-Faucigny": (46.0606, 6.4108),
    "Saint-Jean-d'Aulps": (46.2231, 6.6553),
    "Cuvat": (45.9942, 6.1331),
    "Lully": (46.3486, 6.4133),
    "Brenthonne": (46.3122, 6.3933),
    "Présilly": (46.0808, 6.0892),
    "Cervens": (46.3164, 6.4081),
    "Châtel": (46.2667, 6.8417),
    "Ville-la-Grand": (46.2042, 6.2628),
    "La Roche-sur-Foron": (46.0656, 6.3133),
    "Saint-Gervais-les-Bains": (45.8920, 6.7142),
    "Vetraz-Monthoux": (46.1742, 6.2756),
    "Annecy-le-Vieux": (45.9192, 6.1467),
    "Saint-Martin-Bellevue": (45.9683, 6.1631),
    "Epagny Metz-Tessy": (45.9419, 6.0944),
    "Bellevaux": (46.2719, 6.5511),
    "Perrignier": (46.3083, 6.4253),
    "Saint-Jean-de-Sixt": (45.8819, 6.4011),
    "Le Grand-Bornand": (45.9461, 6.4275),
    "Vallorcine": (46.0292, 6.9344),
    "La Chapelle-d'Abondance": (46.2865, 6.7950),
    "Arâches-la-Frasse": (46.0481, 6.6589),
    "Les Gets": (46.1583, 6.6711),
    "Vaulx": (45.9606, 6.0686),
    "La Balme-de-Sillingy": (45.9667, 6.0500),
    "Allinges": (46.3458, 6.4869),
    "Margencel": (46.3389, 6.4083),
    "Magland": (46.0119, 6.6383),
    "Publier": (46.3933, 6.5269),
    "Marnaz": (46.0617, 6.5350),
    "Sixt-Fer-à-Cheval": (46.0606, 6.7706),
    "Thônes": (45.8806, 6.3231),
    "Ayse": (46.0794, 6.5497),
    "Archamps": (46.1306, 6.1389),
    "Metz-Tessy": (45.9419, 6.0944),
    "Vétraz-Monthoux": (46.1742, 6.2756),
    "Anthy-sur-Léman": (46.3592, 6.4131),
    "Viry": (46.1422, 5.9542),
    "Faverges-Seythenex": (45.7494, 6.2925),
    "Neydens": (46.1281, 6.0978),
    "Fillinges": (46.1842, 6.3414),
}

# Slugs sometimes encode the commune at the end. Match these endings.
SLUG_COMMUNE_SUFFIXES = {
    "annecy": "Annecy",
    "annemasse": "Annemasse",
    "cluses": "Cluses",
    "sallanches": "Sallanches",
    "thonon": "Thonon-les-Bains",
    "evian": "Évian-les-Bains",
    "chamonix": "Chamonix-Mont-Blanc",
    "megeve": "Megève",
    "bonneville": "Bonneville",
    "rumilly": "Rumilly",
    "sciez": "Sciez",
    "doussard": "Doussard",
    "talloires": "Talloires-Montmin",
    "yvoire": "Yvoire",
    "manigod": "Manigod",
    "la-clusaz": "La Clusaz",
    "morzine": "Morzine",
    "samoens": "Samoëns",
    "combloux": "Combloux",
    "passy": "Passy",
    "faverges": "Faverges",
    "sevrier": "Sevrier",
    "saint-jorioz": "Saint-Jorioz",
    "argonay": "Argonay",
    "poisy": "Poisy",
    "sillingy": "Sillingy",
    "cuvat": "Cuvat",
    "lully": "Lully",
    "presilly": "Présilly",
    "chatel": "Châtel",
    "ville-la-grand": "Ville-la-Grand",
    "la-roche-sur-foron": "La Roche-sur-Foron",
    "saint-gervais": "Saint-Gervais-les-Bains",
    "vetraz-monthoux": "Vetraz-Monthoux",
    "annecy-le-vieux": "Annecy-le-Vieux",
    "saint-martin-bellevue": "Saint-Martin-Bellevue",
    "bellevaux": "Bellevaux",
    "perrignier": "Perrignier",
    "saint-jean-de-sixt": "Saint-Jean-de-Sixt",
    "le-grand-bornand": "Le Grand-Bornand",
    "vallorcine": "Vallorcine",
    "la-chapelle-dabondance": "La Chapelle-d'Abondance",
    "magland": "Magland",
    "publier": "Publier",
    "marnaz": "Marnaz",
    "cervens": "Cervens",
    "sixt-fer-a-cheval": "Sixt-Fer-à-Cheval",
    "thones": "Thônes",
    "vaulx": "Vaulx",
    "allinges": "Allinges",
    "margencel": "Margencel",
    "saint-pierre-en-faucigny": "Saint-Pierre-en-Faucigny",
}


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# Equivalence groups — these communes are noise (diacritics, mergers, or
# different facets of the same place). A mismatch within a group is not a
# flag.
EQUIV_GROUPS = [
    {"Faverges", "Faverges-Seythenex", "Seythenex"},     # 2016 merger
    {"Sevrier", "Sévrier"},                              # diacritic
    {"Vetraz-Monthoux", "Vétraz-Monthoux"},              # diacritic
    {"Sillingy", "La Balme-de-Sillingy", "Epagny Metz-Tessy", "Metz-Tessy"},  # Annecy agglo neighbours often interchanged
    {"Annecy", "Annecy-le-Vieux", "Cran-Gevrier", "Seynod", "Pringy", "Meythet", "Veyrier-du-Lac"},  # 2017 merger commune
    {"Saint-Gervais-les-Bains", "Saint-Gervais"},
    {"La Chapelle-d'Abondance", "La Chapelle-d-Abondance", "La Chapelle-dAbondance"},
]


def commune_equiv(a, b):
    """True if a and b are the same place (diacritics/mergers/etc)."""
    if not a or not b:
        return False
    if a == b:
        return True
    # Strip diacritics for comparison
    def norm(s):
        import unicodedata
        s = unicodedata.normalize("NFD", s)
        return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    if norm(a) == norm(b):
        return True
    for grp in EQUIV_GROUPS:
        if a in grp and b in grp:
            return True
    return False


def slug_to_commune(slug):
    for suf, commune in sorted(SLUG_COMMUNE_SUFFIXES.items(), key=lambda x: -len(x[0])):
        if slug.endswith("-" + suf) or slug == suf:
            return commune
    return None


def address_commune(fiche):
    """Look for a commune name in i18n.fr.practical_info adresse/localisation values."""
    fr = (fiche.get("i18n") or {}).get("fr") or {}
    rows = fr.get("practical_info") or []
    for row in rows:
        if not isinstance(row, dict):
            continue
        k = (row.get("k") or "").lower()
        if any(kw in k for kw in ("adresse", "addr", "localisation", "address")):
            v = row.get("v") or ""
            for commune in COMMUNE_CENTROID:
                if re.search(rf"\b{re.escape(commune)}\b", v, re.I):
                    return commune
    return None


def main():
    fiches = []
    for f in sorted(glob.glob(os.path.join(ROOT, "Json", "*.json"))):
        try:
            fiches.append(json.load(open(f)))
        except Exception:
            pass

    flags = []  # (slug, level, signal, detail)

    for d in fiches:
        slug = d.get("slug", "")
        commune = (d.get("commune") or "").strip()
        lat = d.get("latitude")
        lng = d.get("longitude")

        # 1. Coord sanity
        if lat in (None, "", 0, 0.0) or lng in (None, "", 0, 0.0):
            flags.append((slug, "ERR", "no-coords", f"lat={lat}, lng={lng}"))
        else:
            try:
                lat_f, lng_f = float(lat), float(lng)
                # Haute-Savoie envelope (generous)
                if not (45.5 <= lat_f <= 46.6 and 5.7 <= lng_f <= 7.2):
                    flags.append((slug, "ERR", "out-of-bounds",
                                  f"lat={lat_f:.4f}, lng={lng_f:.4f} (outside HS)"))
                # 2. Distance to commune centroid
                if commune in COMMUNE_CENTROID:
                    clat, clng = COMMUNE_CENTROID[commune]
                    dist = haversine_km(lat_f, lng_f, clat, clng)
                    if dist > 10:
                        flags.append((slug, "WARN", "coord-vs-commune",
                                      f"lat/lng {dist:.1f} km from commune centroid"))
                    elif dist > 5:
                        flags.append((slug, "INFO", "coord-vs-commune",
                                      f"lat/lng {dist:.1f} km from commune centroid"))
            except (TypeError, ValueError):
                flags.append((slug, "ERR", "bad-coords", f"lat={lat!r}, lng={lng!r}"))

        # 3. Slug suffix vs commune
        slug_commune = slug_to_commune(slug)
        if slug_commune and commune and not commune_equiv(slug_commune, commune):
            flags.append((slug, "WARN", "slug-vs-commune",
                          f"slug suggests {slug_commune!r}, commune is {commune!r}"))

        # 4. Address mention vs commune
        addr_commune = address_commune(d)
        if addr_commune and commune and not commune_equiv(addr_commune, commune):
            flags.append((slug, "WARN", "addr-vs-commune",
                          f"address mentions {addr_commune!r}, commune is {commune!r}"))

        # 5. Missing commune
        if not commune:
            flags.append((slug, "ERR", "no-commune", "commune field is empty"))

    # Write report
    out = []
    out.append("# Venue location audit\n")
    out.append(f"Scanned {len(fiches)} fiches. Local cross-check only "
               "(no external API access in this sandbox).\n\n")

    by_level = {"ERR": [], "WARN": [], "INFO": []}
    for f in flags:
        by_level[f[1]].append(f)

    out.append("## Summary\n")
    out.append("| Level | Count | Distinct slugs |")
    out.append("|---|---:|---:|")
    for lvl in ("ERR", "WARN", "INFO"):
        lst = by_level[lvl]
        out.append(f"| {lvl} | {len(lst)} | {len({x[0] for x in lst})} |")
    out.append("")

    by_signal = {}
    for f in flags:
        by_signal.setdefault(f[2], []).append(f)
    out.append("## By signal\n")
    out.append("| Signal | Count |")
    out.append("|---|---:|")
    for sig, lst in sorted(by_signal.items(), key=lambda x: -len(x[1])):
        out.append(f"| `{sig}` | {len(lst)} |")
    out.append("")

    for lvl in ("ERR", "WARN", "INFO"):
        lst = by_level[lvl]
        if not lst:
            continue
        out.append(f"\n## {lvl} — {len(lst)} rows\n")
        out.append("| slug | signal | detail |")
        out.append("|---|---|---|")
        for slug, _, sig, det in sorted(lst):
            out.append(f"| `{slug}` | {sig} | {det} |")

    out_path = os.path.join(ROOT, "venue-audit.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))

    # Print summary to stdout
    print(f"Scanned: {len(fiches)} fiches")
    print(f"Flags: {len(flags)} total")
    for lvl in ("ERR", "WARN", "INFO"):
        print(f"  {lvl}: {len(by_level[lvl])}")
    print(f"\nReport: {out_path}")


if __name__ == "__main__":
    main()
