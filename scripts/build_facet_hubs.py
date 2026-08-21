#!/usr/bin/env python3
"""build_facet_hubs.py — HANDOFF-facet-hubs. Inverted facet layer.

The per-lieu facet layer (api/lieu/<slug>.json, content/<slug>.md) is inverted
into one surface PER FACET across all lieux, in two forms from this one builder:

  1. HTML facet hub pages (FR + locales.PROSE), answer-first, modeled on
     build_intent_hubs.py — for the 5 discriminating facets (parking, transport,
     access_pmr, is_free, winter). Editorial copy (title/h1/meta/intro/FAQ) comes
     ONLY from data/facet-hubs.json (Claudius payload); membership + displayed
     values are DERIVED LIVE and never claimed:
       • member iff api/lieu.<facet> is non-null  (is_free: lieux.json bool true)
       • displayed value = the fiche's own verbatim source text (api / i18n.fr /
         the winter controlled-vocab labels) — never re-derived, never summarised
  2. Facet mirror markdown content/facets/<facet>.md (+ /en/) for all 8 facets —
     one section per lieu, verbatim value, for agents answering cross-cutting
     questions in one fetch.

Info-framing (never a capability claim) lives in the registry copy. Coverage
counts are computed here, never hardcoded. Canonicals/hreflang/sitemap are added
by fix_hreflang_sitemap.py downstream. No timestamps/random → byte-stable
(md `last_built` is the corpus's newest lastmod date, a committed stable value).
"""
import html as _html
import siteconfig  # HANDOFF-73: per-site identity
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import locales  # noqa: E402
import build_ai_content as _bac  # noqa: E402  winter controlled-vocab labels + WINTER_NODES
import derive_access_cost as _dac  # noqa: E402  the derived access-cost state (free_seasonal badge)
from build_intent_hubs import CSS, esc, L, url_for  # noqa: E402  reuse chrome + helpers

REGISTRY = os.path.join(ROOT, "data", "facet-hubs.json")
API_DIR = os.path.join(ROOT, "api", "lieu")
JSON_DIR = os.path.join(ROOT, "Json")
LIEUX = os.path.join(ROOT, "lieux.json")
LASTMOD = os.path.join(ROOT, "data", "lastmod.json")
FACET_MD_DIR = os.path.join(ROOT, "content", "facets")
BASE = siteconfig.BASE_URL
LANGS = locales.PROSE

UI = {
    "see_fiche": {"fr": "Voir la fiche →", "en": "See details →", "de": "Zum Steckbrief →",
                  "it": "Vedi la scheda →", "es": "Ver la ficha →", "nl": "Bekijk fiche →"},
    "faq":       {"fr": "Questions fréquentes", "en": "Frequently asked questions",
                  "de": "Häufige Fragen", "it": "Domande frequenti", "es": "Preguntas frecuentes",
                  "nl": "Veelgestelde vragen"},
    "guides":    {"fr": "Guides pratiques", "en": "Practical guides", "de": "Praktische Guides",
                  "it": "Guide pratiche", "es": "Guías prácticas", "nl": "Praktische gidsen"},
    "not_docd":  {"fr": "Non renseigné", "en": "Not specified", "de": "Nicht angegeben",
                  "it": "Non specificato", "es": "No especificado", "nl": "Niet vermeld"},
    "free":      {"fr": "Accès libre", "en": "Free entry", "de": "Freier Zugang",
                  "it": "Accesso libero", "es": "Acceso libre", "nl": "Vrije toegang"},
    "free_seasonal": {
        "fr": "Gratuit hors saison · payant en été",
        "en": "Free off-season · paid in summer",
        "de": "Außerhalb der Saison gratis · im Sommer kostenpflichtig",
        "it": "Gratuito fuori stagione · a pagamento in estate",
        "es": "Gratis fuera de temporada · de pago en verano",
        "nl": "Buiten het seizoen gratis · betaald in de zomer"},
}
# coverage line, e.g. "247 sites sur 398 disposent d'une info parking vérifiée."
COVERAGE = {
    "fr": "{n} sites sur {tot} disposent d'une information {label} vérifiée sur leur fiche — les autres indiquent « Non renseigné ».",
    "en": "{n} of {tot} sites document {label} on their fiche — the others read \"Not specified\".",
    "de": "{n} von {tot} Orten dokumentieren {label} auf ihrer Fiche — die übrigen zeigen „Nicht angegeben\".",
    "it": "{n} siti su {tot} documentano {label} sulla scheda — gli altri indicano \"Non specificato\".",
    "es": "{n} de {tot} sitios documentan {label} en su ficha — los demás indican \"No especificado\".",
    "nl": "{n} van {tot} locaties documenteren {label} op hun fiche — de rest vermeldt \"Niet vermeld\".",
}
COVERAGE_LABEL = {
    "parking":    {"fr": "parking", "en": "parking", "de": "Parken", "it": "il parcheggio", "es": "el aparcamiento", "nl": "parkeren"},
    "transport":  {"fr": "d'accès en transports en commun", "en": "public transport access", "de": "die ÖPNV-Anbindung", "it": "l'accesso coi trasporti", "es": "el acceso en transporte", "nl": "ov-toegang"},
    "access_pmr": {"fr": "d'accès PMR", "en": "wheelchair access", "de": "die Barrierefreiheit", "it": "l'accesso PMR", "es": "el acceso PMR", "nl": "rolstoeltoegang"},
    "is_free":    {"fr": "de gratuité", "en": "free entry", "de": "den freien Eintritt", "it": "la gratuità", "es": "la gratuidad", "nl": "gratis toegang"},
    "winter":     {"fr": "hiver", "en": "winter", "de": "Winter", "it": "l'inverno", "es": "invierno", "nl": "winter"},
}
# category display (frozen FR from the fiche category slug) — a light readable label
CAT_LABEL = {
    "accrobranche": "Accrobranche", "aquaparc": "Parcs aquatiques", "attraction": "Attractions",
    "base-nautique": "Bases nautiques", "bowling": "Bowling", "cascade": "Cascades",
    "casino": "Casinos", "chateau": "Châteaux", "cinema": "Cinémas", "croisiere": "Croisières",
    "divers": "Divers", "domaine": "Domaines", "jardin": "Jardins", "karting": "Karting",
    "lac": "Lacs", "musee": "Musées", "parc": "Parcs", "patinoire": "Patinoires",
    "plage": "Plages", "point-de-vue": "Points de vue", "sentier": "Sentiers",
    "telecabine": "Télécabines", "voie-verte": "Voies vertes", "wakepark": "Wakeparks",
}


# ---------------------------------------------------------------- data loading
def load_registry():
    return json.loads(open(REGISTRY, encoding="utf-8").read())


CATALOG = os.path.join(ROOT, "catalog-index.json")


def load_all():
    # PUBLISHED set only — draft/unverified fiches have api/lieu entries but NO
    # built pages (build_catalog_index JOB 6), so they can never be facet members
    # (a card link would 404). Scope membership + total to the catalog.
    published = {e["slug"] for e in json.loads(open(CATALOG, encoding="utf-8").read())}
    api, fiches = {}, {}
    for fn in os.listdir(API_DIR):
        if not fn.endswith(".json"):
            continue
        slug = fn[:-5]
        if slug not in published:
            continue
        api[slug] = json.loads(open(os.path.join(API_DIR, fn), encoding="utf-8").read())
        fp = os.path.join(JSON_DIR, fn)
        if os.path.exists(fp):
            fiches[slug] = json.loads(open(fp, encoding="utf-8").read())
    lieux = {e["slug"]: e for e in json.loads(open(LIEUX, encoding="utf-8").read())["lieux"]
             if e["slug"] in published}
    return api, fiches, lieux


def newest_lastmod():
    try:
        m = json.loads(open(LASTMOD, encoding="utf-8").read())
        return max(m.values()) if m else ""
    except Exception:
        return ""


# ------------------------------------------------------------ membership (derived)
def _price_signals_paid(prices):
    """True if the fiche's authoritative price data (api/lieu.prices) shows a
    real entry cost — used to keep the free hub honest even when lieux.json's
    is_free flag has drifted. A side cost the note discloses (e.g. free access,
    paid rental) still shows the note; only an ENTRY price excludes."""
    if not isinstance(prices, dict):
        return False
    if prices.get("is_free") is False:
        return True
    frm = prices.get("from")
    try:
        if frm is not None and float(frm) > 0:
            return True
    except (TypeError, ValueError):
        pass
    for t in (prices.get("tiers") or []):
        try:
            if float(t.get("price") or 0) > 0:
                return True
        except (TypeError, ValueError):
            pass
    return False


def is_member(facet, slug, api, lieux):
    key, src = facet["facet_key"], facet["source"]
    if src == "manifest_bool":                      # is_free
        # The manifest's derived access_state is the single source of truth
        # (build_catalog_index derives it from authoritative price data, so it can
        # no longer drift). The free hub carries genuinely-free entry AND
        # free-off-season/paid-in-peak (free_seasonal, badged); only `paid` and
        # unmapped are excluded.
        return lieux.get(slug, {}).get("access_state") in ("free", "free_seasonal")
    return api.get(slug, {}).get(key) is not None   # api non-null


def members_of(facet, api, lieux):
    universe = set(lieux) if facet["source"] == "manifest_bool" else set(api)
    return sorted(s for s in universe if is_member(facet, s, api, lieux))


# ---------------------------------------------------- verbatim value projection
def facet_value_text(facet_key, slug, api, fiches, lang):
    """The DISPLAYED value for one member — pulled verbatim from the fiche source,
    never re-derived, never summarised. Returns plain text ('' → 'Non renseigné')."""
    d = api.get(slug, {})
    if facet_key in ("parking", "hours", "season"):
        v = d.get(facet_key)
        return v if isinstance(v, str) else ""
    if facet_key == "access_pmr":
        a = d.get("access_pmr") or {}
        return (a.get("detail") or a.get("status") or "") if isinstance(a, dict) else ""
    if facet_key == "is_free":
        # free_seasonal (free off-season, paid in the summer window) gets an
        # honest badge instead of a bare "Accès libre" — same derivation the
        # manifest/gate use, so it stays consistent.
        if _dac.derive(fiches.get(slug, {}) or {})[0] == "free_seasonal":
            return L(UI["free_seasonal"], lang)
        note = (d.get("prices") or {}).get("note") if isinstance(d.get("prices"), dict) else None
        return note or L(UI["free"], lang)
    if facet_key == "prices":
        p = d.get("prices") or {}
        return p.get("note") or (f"À partir de {p.get('from')} {p.get('currency','')}".strip()
                                 if p.get("from") not in (None, "") else "")
    if facet_key == "transport":
        stops = (d.get("transport") or {}).get("stops") or []
        parts = []
        for s in stops:
            bits = [s.get("name", "")]
            tail = []
            if s.get("operator"): tail.append(s["operator"])
            if s.get("distance_m") is not None: tail.append(f"{s['distance_m']} m")
            if s.get("lines"): tail.append("lignes " + ", ".join(s["lines"]))
            if tail: bits.append("(" + " · ".join(tail) + ")")
            parts.append(" ".join(b for b in bits if b))
        return " ; ".join(p for p in parts if p)
    if facet_key == "winter":
        # winter controlled-vocab labels — STRICT per-locale, NO fallback (R1): a
        # token missing a PROSE locale must FAIL the build, never silently emit an
        # EN string on a non-EN page (the reverse-leak class gate_i18n_leak kills).
        def wl(m):
            if lang not in m:
                raise KeyError(f"winter vocab missing locale {lang!r} for {m!r} — "
                               "extend the map in build_ai_content.py (no fallback)")
            return m[lang]
        fk = ((fiches.get(slug, {}).get("i18n") or {}).get("fr") or {}).get("facts") or {}
        rows = []
        a = fk.get("winter_access")
        if a in _bac.WINTER_ACCESS: rows.append(wl(_bac.WINTER_ACCESS[a]))
        infra = [wl(_bac.WINTER_INFRA[x]) for x in (fk.get("winter_infra") or []) if x in _bac.WINTER_INFRA]
        if infra: rows.append(" · ".join(infra))
        sv = fk.get("snow_view")
        if sv in _bac.SNOW_VIEW: rows.append(wl(_bac.SNOW_VIEW[sv]))
        rows.append(wl(_bac.EQUIP) + (wl(_bac.EQUIP_COL) if fk.get("col_chains") else ""))
        return " · ".join(r for r in rows if r)
    return ""


# --------------------------------------------------------------- name / category
def fr_name(fiches, slug):
    return ((fiches.get(slug, {}).get("i18n") or {}).get("fr") or {}).get("name") or slug


def category_of(fiches, slug):
    return fiches.get(slug, {}).get("category") or "divers"


# ------------------------------------------------------------------- HTML render
def render_card(facet, slug, api, fiches, lang):
    name = fr_name(fiches, slug)                       # frozen FR name
    commune = fiches.get(slug, {}).get("commune") or ""
    val = facet_value_text(facet["facet_key"], slug, api, fiches, lang) or L(UI["not_docd"], lang)
    return (
        '<article class="card">\n'
        f'  <div class="ch"><h3>{esc(name)}</h3></div>\n'
        f'  <div class="meta">{esc(commune)}</div>\n'
        f'  <p class="hi"><bdi>{esc(val)}</bdi></p>\n'
        f'  <a class="fiche" href="{url_for(slug, lang)}">{esc(L(UI["see_fiche"], lang))}</a>\n'
        '</article>'
    )


def schema_block(facet, members, fiches, lang):
    hub_url = url_for(facet["hub_slug"], lang)
    items = [{"@type": "ListItem", "position": i, "name": fr_name(fiches, s),
              "url": url_for(s, lang)} for i, s in enumerate(members, 1)]
    coll = {"@type": "CollectionPage", "name": facet["i18n"][lang]["h1"], "url": hub_url}
    itemlist = {"@type": "ItemList", "name": facet["i18n"][lang]["h1"], "itemListElement": items}
    faq = {"@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": L(q["q"], lang),
         "acceptedAnswer": {"@type": "Answer", "text": L(q["a"], lang)}}
        for q in facet.get("faq", [])]}
    return json.dumps({"@context": "https://schema.org", "@graph": [coll, itemlist, faq]},
                      ensure_ascii=False)


def render_hub(facet, members, api, fiches, lang, total):
    cp = facet["i18n"][lang]
    # group by category, categories sorted by member count desc then label
    by_cat = {}
    for s in members:
        by_cat.setdefault(category_of(fiches, s), []).append(s)
    order = sorted(by_cat, key=lambda c: (-len(by_cat[c]), c))
    sections = []
    for cat in order:
        grp = by_cat[cat]
        label = f'{esc(CAT_LABEL.get(cat, cat))} · {len(grp)}'
        cards = "".join(render_card(facet, s, api, fiches, lang) for s in grp)
        sections.append(f'<h2>{label}</h2>\n<div class="cards">{cards}</div>')

    cov = COVERAGE[lang].format(n=len(members), tot=total, label=L(COVERAGE_LABEL[facet["facet_key"]], lang))

    # map (members with coords)
    pts = []
    for s in members:
        f = fiches.get(s, {})
        lat, lng = f.get("latitude"), f.get("longitude")
        if lat is None or lng is None:
            continue
        pts.append({"name": fr_name(fiches, s), "commune": f.get("commune") or "",
                    "url": url_for(s, lang), "lat": lat, "lng": lng})
    map_data = json.dumps(pts, ensure_ascii=False)
    head_leaflet = ('<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">'
                    '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>') if pts else ""
    map_div = '<div id="map"></div>' if pts else ""
    map_script = ("" if not pts else
        f'<script>var B={map_data};var map=L.map("map",{{scrollWheelZoom:false}});'
        'L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:18,attribution:"© OpenStreetMap"}).addTo(map);'
        'var g=[];B.forEach(function(b){var m=L.circleMarker([b.lat,b.lng],{radius:7,color:"#155059",fillColor:"#1F6E78",fillOpacity:.9,weight:2}).addTo(map);'
        'm.bindPopup("<b>"+b.name+"</b><br>"+b.commune+"<br><a href=\\""+b.url+"\\">'
        + esc(L(UI["see_fiche"], lang)) + '</a>");g.push([b.lat,b.lng]);});'
        'if(g.length)map.fitBounds(L.latLngBounds(g).pad(.15));</script>')

    faq_html = "".join(
        f'<details class="q"><summary>{esc(L(q["q"], lang))}</summary><p>{esc(L(q["a"], lang))}</p></details>'
        for q in facet.get("faq", []))

    return f"""<!doctype html><html lang="{lang}"><head><script>document.documentElement.classList.add('js')</script>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(cp["title"])}</title>
<meta name="description" content="{esc(cp["meta_description"])}">
{head_leaflet}
<script type="application/ld+json">{schema_block(facet, members, fiches, lang)}</script>
<style>{CSS}</style></head><body><div class="wrap">

<h1>{esc(cp["h1"])}</h1>
<div class="answer">{esc(cp["intro"])}</div>
<p class="note">{esc(cov)}</p>

{map_div}

{"".join(sections)}

<h2>{esc(L(UI["faq"], lang))}</h2>
{faq_html}

<footer>© 2026 · Bleu canard édition · Edmaster &amp; Claudius · Tous droits réservés 🦆</footer>
</div>
{map_script}
</body></html>"""


# --------------------------------------------------------------- md mirror render
def render_md(facet, members, api, fiches, lang, total, built):
    key = facet["facet_key"]
    head_label = {"parking": "Parking", "transport": "Transports", "access_pmr": "Accès PMR",
                  "is_free": "Gratuité", "winter": "Hiver", "hours": "Horaires",
                  "prices": "Tarifs", "season": "Saison"}[key]
    out = [f"---\nfacet: {key}\nscope: haute-savoie-74\nlieux_documented: {len(members)}\n"
           f"lieux_total: {total}\nlast_built: {built}\nsource: {siteconfig.DOMAIN}\n---\n",
           f"# {head_label} — index transversal ({total} lieux, {len(members)} documentés)\n"]
    for s in members:
        name = fr_name(fiches, s)
        commune = fiches.get(s, {}).get("commune") or ""
        val = facet_value_text(key, s, api, fiches, "fr" if lang == "fr" else "en") or ""
        out.append(f"## {name} — {commune}\n{val}\n"
                   f"Fiche: {BASE}/{s} · JSON: {BASE}/api/lieu/{s}.json\n")
    return "\n".join(out) + "\n"


# ------------------------------------------------- llms.txt + ai-info discovery
FACET_MD_LABEL = {"parking": "Parking, all sites", "transport": "Public transport access",
                  "access_pmr": "PMR access info", "is_free": "Free-entry sites",
                  "winter": "Winter info", "hours": "Opening hours", "prices": "Prices",
                  "season": "Season"}


def wire_discovery(facets):
    """Idempotently add the §6 'Facet indexes' section to llms.txt and the
    facet_indexes key to .well-known/ai-info.json (both regenerated upstream by
    build_ai_content, so this patches the fresh output — byte-stable)."""
    import re
    keys = [f["facet_key"] for f in facets]
    # llms.txt — insert before the '## Category hubs' heading, idempotent
    llms_p = os.path.join(ROOT, "llms.txt")
    if os.path.exists(llms_p):
        A, Z = "<!-- facet-indexes:start -->", "<!-- facet-indexes:end -->"
        t = open(llms_p, encoding="utf-8").read()
        t = re.sub(re.escape(A) + r".*?" + re.escape(Z) + r"\n*", "", t, flags=re.S)  # strip old (incl. markers + trailing blanks)
        lines = [A, "## Facet indexes (cross-cutting answers in one fetch)",
                 "Use these when the question spans many sites (e.g. \"which waterfalls have parking\"):"]
        lines += [f"- [{FACET_MD_LABEL[k]}]({BASE}/content/facets/{k}.md)" for k in keys]
        lines.append(Z)
        block = "\n".join(lines) + "\n\n"
        if "## Category hubs" in t:
            t = t.replace("## Category hubs", block + "## Category hubs", 1)
        else:
            t = t.rstrip() + "\n\n" + block
        open(llms_p, "w", encoding="utf-8").write(t)
    # ai-info.json — facet_indexes key
    ai_p = os.path.join(ROOT, ".well-known", "ai-info.json")
    if os.path.exists(ai_p):
        d = json.loads(open(ai_p, encoding="utf-8").read())
        d["facet_indexes"] = {"url_pattern": BASE + "/content/facets/{facet}.md",
                              "facets": keys}
        with open(ai_p, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=2)
            fh.write("\n")


# ------------------------------------------------------- homepage 0-orphan block
MARK_A, MARK_B = "<!--facet-hubs:start-->", "<!--facet-hubs:end-->"


def _strip_block(path):
    """Remove any facet-hub nav block from a homepage — for the non-PROSE locales
    (pl/pt/cs/ar/he/ja): they are EN structural twins that inherit the block from
    en/index.html but have NO facet hubs of their own (dead /<lang>/ links)."""
    import re
    if not os.path.exists(path):
        return False
    html = open(path, encoding="utf-8").read()
    new = re.sub(r"\s*" + re.escape(MARK_A) + r".*?" + re.escape(MARK_B), "", html, flags=re.S)
    if new != html:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(new)
        return True
    return False


def inject_homepage_links(html_facets, lang):
    import re
    rel = "index.html" if lang == "fr" else os.path.join(lang, "index.html")
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        return False
    html = open(path, encoding="utf-8").read()
    html = re.sub(r"\s*" + re.escape(MARK_A) + r".*?" + re.escape(MARK_B), "", html, flags=re.S)
    links = "".join(
        f'<a href="{url_for(f["hub_slug"], lang)}" style="display:inline-block;margin:2px 10px 2px 0;color:#1F6E78;font-weight:600">{esc(f["i18n"][lang]["h1"])} →</a>'
        for f in html_facets)
    block = (MARK_A + f'<nav class="facet-hubs" aria-label="{esc(L(UI["guides"], lang))}" '
             'style="max-width:760px;margin:18px auto;padding:0 18px">'
             + f'<strong style="display:block;font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:#1F6E78;margin-bottom:4px">{esc(L(UI["guides"], lang))}</strong>'
             + links + '</nav>' + MARK_B)
    html = html.replace("</body>", "\n" + block + "</body>", 1)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return True


# ------------------------------------------------------------------------- main
def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pages", action="store_true", help="build hub pages + md mirrors only")
    ap.add_argument("--links", action="store_true", help="inject homepage 0-orphan links only")
    args = ap.parse_args()
    do_pages = args.pages or not (args.pages or args.links)   # default: both
    do_links = args.links or not (args.pages or args.links)

    reg = load_registry()
    facets = reg["facets"]
    api, fiches, lieux = load_all()
    total = len(api)                      # published api set (draft fiches have no page)
    built = newest_lastmod()
    html_facets = [f for f in facets if f.get("html_hub")]
    html_pages = md_files = injected = 0

    if do_pages:
        os.makedirs(FACET_MD_DIR, exist_ok=True)
        os.makedirs(os.path.join(FACET_MD_DIR, "en"), exist_ok=True)
        for f in html_facets:
            members = members_of(f, api, lieux)
            for lang in LANGS:
                html = render_hub(f, members, api, fiches, lang, total)
                out = os.path.join(ROOT, f"{f['hub_slug']}.html") if lang == "fr" \
                    else os.path.join(ROOT, lang, f"{f['hub_slug']}.html")
                os.makedirs(os.path.dirname(out), exist_ok=True)
                with open(out, "w", encoding="utf-8") as fh:
                    fh.write(html)
                html_pages += 1
        for f in facets:
            members = members_of(f, api, lieux)
            for lang in ("fr", "en"):
                md = render_md(f, members, api, fiches, lang, total, built)
                out = os.path.join(FACET_MD_DIR, f"{f['facet_key']}.md") if lang == "fr" \
                    else os.path.join(FACET_MD_DIR, "en", f"{f['facet_key']}.md")
                with open(out, "w", encoding="utf-8") as fh:
                    fh.write(md)
                md_files += 1
        wire_discovery(facets)
    if do_links:
        injected = sum(inject_homepage_links(html_facets, lang) for lang in LANGS)
        # non-PROSE locales (EN twins) have no facet hubs → strip any inherited block
        for lang in locales.VISIBLE:
            if lang in LANGS:
                continue
            _strip_block(os.path.join(ROOT, "index.html" if lang == "fr" else os.path.join(lang, "index.html")))

    print(f"build_facet_hubs: {'pages ' if do_pages else ''}{'links ' if do_links else ''}· "
          f"{html_pages} pages · {md_files} md mirrors · homepage links in {injected} locale(s)")


if __name__ == "__main__":
    main()
