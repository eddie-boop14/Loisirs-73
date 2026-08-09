#!/usr/bin/env python3
"""acceslibre_join.py — Layer 1 PMR bulk join (Acceslibre dept-74 dump → fiches).

High-precision: a fiche matches an Acceslibre ERP only on commune + geo<=150m +
shared significant name token (or geo<=60m). Status is derived CONSERVATIVELY
from declarative entrance/sanitaire signals. Acceslibre is declarative, never
regulatory -> confidence:"declarative", source_name:"Acceslibre", web_url link.

Run with --apply to write Json/*.json; default is dry-run review to stdout/JSON.
Protected fiches (chez-nous-a-la-plage, chalet-du-tornet) are never written.
Fiches that already carry acces_pmr are left untouched.
"""
import csv, glob, json, math, os, re, sys, unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(ROOT, "data", "acceslibre", "acceslibre-74.csv")
PROTECTED = {"chez-nous-a-la-plage", "chalet-du-tornet"}
MAX_M = 150.0
TODAY = "2026-06-26"

# Positive allowlist: only Acceslibre ERP in a leisure/tourism activity can map to
# one of our fiches. Kills the dense-urban false matches (restaurant, bank,
# gendarmerie, hairdresser, real-estate within 60 m of a venue). A venue whose
# real ERP sits outside this list simply falls through to Layer 2 — honest miss.
LEISURE_ACTIVITES = {
    "Musée", "Cinéma", "Piscine, centre aquatique", "Bowling", "Parc",
    "Parc d’attraction", "Parc d'attraction", "Salle de jeux", "Spa", "Théâtre",
    "Plage, zone de baignade", "Activités nautiques", "Centre de loisirs",
    "Circuit sportif deux roues / voiture", "Patinoire", "Casino",
}

GENERIC = {
    "le","la","les","de","du","des","d","l","et","a","au","aux","sur","sous","en",
    "plage","lac","musee","chateau","parc","base","loisirs","loisir","sentier",
    "cascade","col","point","vue","jardin","domaine","piscine","centre","espace",
    "saint","sainte","st","ste","mont","val","grand","grande","petit","petite",
    "the","of","tour","gorges","gorge","pont","pointe","plateau","sommet","casino",
    "cinema","bowling","karting","patinoire","golf","camping","ferme","village",
}

def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def norm(s):
    s = strip_accents((s or "").lower())
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.strip()

def tokens(s):
    return set(norm(s).split())

def sig_tokens(s):
    return {t for t in tokens(s) if t not in GENERIC and len(t) > 2}

def haversine(la1, lo1, la2, lo2):
    R = 6371000.0
    p1, p2 = math.radians(la1), math.radians(la2)
    dp = math.radians(la2-la1); dl = math.radians(lo2-lo1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(a))

def fnum(s):
    try: return float(s)
    except (TypeError, ValueError): return None

def derive(row):
    """Return (status, equipment[], detail, th_families) or (None,...) if no signal."""
    epp = row.get("entree_plain_pied","")
    marches = fnum(row.get("entree_marches",""))
    emr = row.get("entree_marches_rampe","")        # aucune|fixe|amovible
    cer = row.get("cheminement_ext_rampe","")
    asc_pmr = row.get("entree_ascenseur_pmr","") == "True"
    epmr = row.get("entree_pmr","")
    san = row.get("sanitaires_adaptes","")
    park = row.get("stationnement_pmr","")
    labels = row.get("labels","")
    fam = row.get("labels_familles_handicap","")
    has_th = '"th"' in labels or "'th'" in labels

    equip = []
    if park == "True": equip.append("parking_pmr")
    if san == "True": equip.append("wc_adapte")
    if emr in ("fixe","amovible") or cer in ("fixe","amovible"): equip.append("rampe")
    if asc_pmr: equip.append("ascenseur")

    th_fams = []
    if has_th and fam:
        for f in ("moteur","visuel","auditif","mental"):
            if f in fam: th_fams.append(f)

    ramp_present = (emr in ("fixe","amovible")) or (cer in ("fixe","amovible")) or asc_pmr
    step_free = (epp == "True") or (epmr == "True")
    has_steps = (epp == "False") or (epmr == "False") or (marches and marches >= 1)

    # Status ladder — conservative, entrance-driven.
    status = None
    detail = None
    if has_th:
        status = "accessible"
        detail = "Établissement labellisé Tourisme & Handicap"
    elif step_free and not (has_steps and not ramp_present):
        if san == "True":
            status = "accessible"; detail = "Entrée de plain-pied, sanitaires adaptés"
        else:
            status = "partiel"; detail = "Entrée de plain-pied"
    elif has_steps:
        if ramp_present:
            status = "partiel"; detail = "Accès par rampe"
        else:
            status = "non_accessible"
            n = int(marches) if marches else None
            detail = f"Entrée avec marche(s){f' ({n})' if n else ''}, sans rampe"
    # else: no usable signal -> status stays None (skip; leave for Layer 2)
    return status, equip, detail, th_fams

def load_erps():
    erps = []
    with open(CSV, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            la, lo = fnum(row.get("latitude")), fnum(row.get("longitude"))
            row["_lat"], row["_lng"] = la, lo
            row["_commune_n"] = norm(row.get("commune",""))
            row["_sig"] = sig_tokens(row.get("name",""))
            erps.append(row)
    # index by commune
    by_commune = {}
    for r in erps:
        by_commune.setdefault(r["_commune_n"], []).append(r)
    return by_commune

def best_match(d, by_commune):
    commune_n = norm(d.get("commune",""))
    cand = by_commune.get(commune_n, [])
    if not cand: return None, []
    flat, flng = fnum(d.get("latitude")), fnum(d.get("longitude"))
    fsig = sig_tokens(d["i18n"]["fr"]["name"])
    commune_toks = set(norm(d.get("commune","")).split())
    scored = []
    for r in cand:
        # gate 1: activity must be leisure/tourism-compatible
        if r.get("activite") not in LEISURE_ACTIVITES: continue
        esig = r["_sig"]
        # gate 2: name containment — one significant-token set ⊆ the other,
        # both non-empty (a generic-only name never matches).
        if not (fsig and esig): continue
        if not (fsig <= esig or esig <= fsig): continue
        # the shared tokens must include something beyond the commune name —
        # else "Patinoire de Morzine" matches "Espace Aquatique de Morzine".
        shared = fsig & esig
        if not (shared - commune_toks): continue
        overlap = len(shared)
        if overlap < 1: continue
        # gate 3: geo. With coords on both sides require <=MAX_M; if the fiche has
        # no coords, demand an exact significant-name equality instead.
        dist = None
        if flat is not None and r["_lat"] is not None:
            dist = haversine(flat, flng, r["_lat"], r["_lng"])
            if dist > MAX_M: continue
        elif fsig != esig:
            continue
        score = (overlap, -(dist if dist is not None else 9e9))
        scored.append((score, dist, overlap, r))
    if not scored: return None, []
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0], scored

def main():
    apply = "--apply" in sys.argv
    by_commune = load_erps()
    files = sorted(glob.glob(os.path.join(ROOT, "Json", "*.json")))
    review = []
    written = 0
    for fp in files:
        slug = os.path.splitext(os.path.basename(fp))[0]
        if slug in PROTECTED: continue
        d = json.loads(open(fp, encoding="utf-8").read())
        if d.get("acces_pmr") is not None: continue   # already sourced (pilot beaches)
        top, allc = best_match(d, by_commune)
        if not top: continue
        _, dist, overlap, r = top
        status, equip, detail, th_fams = derive(r)
        if status is None:   # matched ERP but no usable accessibility signal
            continue
        rec = {
            "slug": slug, "fiche_name": d["i18n"]["fr"]["name"],
            "commune": d.get("commune"), "erp_name": r.get("name"),
            "erp_activite": r.get("activite"), "dist_m": round(dist,1) if dist else None,
            "overlap": overlap, "status": status, "equipment": equip,
            "detail": detail, "th": th_fams, "web_url": r.get("web_url"),
            "n_candidates": len(allc),
        }
        review.append(rec)
        if apply:
            acces = {
                "status": status,
                "detail": detail,
                "equipment": equip or None,
                "handiplage_level": None,
                "tourisme_handicap": th_fams or None,
                "source_url": r.get("web_url") or None,
                "source_name": "Acceslibre",
                "checked": TODAY,
                "confidence": "declarative",
            }
            if not acces["source_url"]:
                continue  # gate requires source_url when status!=null
            d["acces_pmr"] = acces
            with open(fp, "w", encoding="utf-8") as fh:
                json.dump(d, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            written += 1
    out = os.path.join(ROOT, "reports", "acceslibre-join-review.json")
    json.dump(review, open(out,"w",encoding="utf-8"), ensure_ascii=False, indent=2)
    from collections import Counter
    cs = Counter(x["status"] for x in review)
    print(f"acceslibre_join: {len(review)} match(es) with derivable status "
          f"({dict(cs)}); written={written if apply else 0} (apply={apply})")
    print(f"review -> {out}")

if __name__ == "__main__":
    main()
