#!/usr/bin/env python3
"""build_communes.py — Commune layer, phase 1 (PLACE axis).

Builds net-new commune landing pages that aggregate lieux already in
`Json/*.json`, mirroring the category-hub page chrome, and injects a
reciprocal "À <Commune>" backlink onto each aggregated fiche.

Source of truth:
  - data/commune-layer.json  : the 13-commune manifest (commune→lieux + intro_fr + centroid)
  - data/commune-intros.json : per-locale intro translations (fr from manifest, en/de/it/es/nl)
  - Json/<slug>.json         : live fiche data (names, hero, coords, access)

Chrome is LIFTED verbatim from a per-locale template hub (the big <style> block,
the three trailing <script> IIFEs, and the <footer>), so the commune pages stay
byte-consistent with the hubs. Only the per-page variable regions are generated.

Idempotent: deterministic ordering (langs fixed; lieux sorted (category, slug);
categories in first-appearance order), no datetime.now(), and the reciprocal
backlink is insert-or-replace between stable fences — re-running yields a
byte-identical tree.

Usage:
    python3 scripts/build_communes.py --dry-run   # print plan, write nothing
    python3 scripts/build_communes.py             # render pages + inject backlinks
    # then: python3 scripts/fix_hreflang_sitemap.py --apply --sitemap
"""
from __future__ import annotations
import siteconfig  # HANDOFF-73: per-site identity

import argparse
import html as html_lib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_hubs as H  # noqa: E402  reuse fiche_card_html / acces_value / CHROME / picture_tag
import locales  # noqa: E402
import assets  # noqa: E402

LANGS = list(locales.PROSE)          # render axis: commune pages built per prose lang
VIS = list(locales.VISIBLE)          # isolation-ok: nav/hreflang lists the visible roster (incl. pl facts tree)
BASE = siteconfig.BASE_URL
# "loisirs74.fr" -> "loisirs74": the lowercase wordmark used in the commune
# page chrome. Derived, so a new site never hand-edits it.
BRAND_SHORT = siteconfig.DOMAIN.split(".")[0]
MANIFEST = ROOT / "data" / "commune-layer.json"
INTROS = ROOT / "data" / "commune-intros.json"
NEARME_LABELS = json.loads((ROOT / "data" / "nearme-labels.json").read_text(encoding="utf-8"))


def nearme_button(lang, extra_style=""):
    """Shared "◎ Près de moi" button — labels via data-* (consumed by
    /scripts/nearme.js). Honest deny state, no fake location."""
    lab = NEARME_LABELS.get(lang) or NEARME_LABELS["fr"]
    a = lambda s: html_lib.escape(str(s), quote=True)
    style = f' style="{extra_style}"' if extra_style else ""
    return (
        f'<button class="near-me" id="nearMe"{style}'
        f' data-default="{a(lab["def"])}" data-loading="{a(lab["loading"])}"'
        f' data-on="{a(lab["on"])}" data-off="{a(lab["off"])}"'
        f' data-results-title="{a(lab["title"])}" data-results-sub="{a(lab["sub"])}"'
        f' data-cta="{a(lab["cta"])}" data-km="{a(lab["km"])}">{a(lab["def"])}</button>'
    )

# Per-locale template hub to lift invariant chrome from.
# HANDOFF-73 phase 6: ANY rendered hub serves as the chrome template — "cascades"
# was simply the 74's first. A site without it must not inherit the name, so the
# default is the first hub this site's roster actually declares.
def _template_hub_fr():
    try:
        import build_hubs as _H
        return next(iter(_H.ALL_BASE_HUBS))
    except Exception:
        return "cascades"

_TPL_FR = _template_hub_fr()
def _template_hub_map():
    """Locale template-hub paths derived from THIS site's roster, not the 74's
    slugs. Falls back to the FR dir for any locale the hub has not been
    rendered into yet, which is what a young site looks like."""
    m = {"fr": _TPL_FR}
    try:
        import build_hubs as _H
        loc = _H.hub_locale_map(_TPL_FR)
    except Exception:
        loc = {}
    for lang in ("en", "de", "it", "es", "nl"):
        slug = loc.get(lang)
        m[lang] = f"{lang}/{slug}" if slug else _TPL_FR
    return m

TEMPLATE_HUB = _template_hub_map()

OG_LOCALE = {"fr": "fr_FR", "en": "en_US", "de": "de_DE", "it": "it_IT", "es": "es_ES", "nl": "nl_NL"}

# HANDOFF-31: facts-first languages render commune pages through THIS template
# too. Their chrome comes from reviewed vocabulary (data/site-chrome-langs.json)
# via register_facts_lang(); their hub-lift template is their OWN freshly built
# hub (so the lifted style/scripts/footer are already localized). The six live
# locales' path is untouched.
STRICT_LANGS = set()


def register_facts_lang(lang):
    """Extend C / CATEGORY_LABELS / TEMPLATE_HUB / OG_LOCALE with a facts-first
    language from reviewed sources. Requires the lang's cascades hub to exist
    (build_hubs.build_facts_lang_hubs runs first). Idempotent."""
    if lang in STRICT_LANGS:
        return
    H.register_facts_lang(lang)
    sc = H._data("site-chrome-langs.json")
    for k, v in sc["commune_chrome"][lang].items():
        if k in C:
            C[k][lang] = v
    for k, v in sc["category_labels"][lang].items():
        if k in CATEGORY_LABELS:
            CATEGORY_LABELS[k][lang] = v
    TEMPLATE_HUB[lang] = f"{lang}/{H.hub_slug_for(_TPL_FR, lang)}"
    OG_LOCALE[lang] = H._FACTS_OG[lang]
    _TEMPLATE_CACHE.pop(lang, None)
    STRICT_LANGS.add(lang)


def _filter_strings(lang):
    """Filter-bar strings for render_page. The six live locales ship these as
    the FR literals below (frozen chrome — byte-identity contract); facts-first
    languages get the reviewed translations."""
    if lang in STRICT_LANGS:
        hc = H._data("site-chrome-langs.json")["hub_chrome"][lang]
        il = H._data("i18n-labels.json")
        return {"filtres": hc["filtres"], "acces": hc["acces"], "tous": hc["tous"],
                "gratuit": il["fact_values"]["gratuit"][lang],
                "payant": il["fact_values"]["payant"][lang],
                "tri": hc["tri"], "by_category": hc["by_category"],
                "no_results": hc["no_results"], "no_match": hc["no_match"]}
    return {"filtres": "Filtres", "acces": "Accès", "tous": "Tous",
            "gratuit": "Gratuit", "payant": "Payant", "tri": "Tri",
            "by_category": "Par catégorie", "no_results": "Aucun résultat",
            "no_match": "Aucun lieu ne correspond aux filtres actifs."}


def _title_q(lang, commune):
    """'Que faire à <Commune> ?' composed per language. The six keep the exact
    historical FR-style spacing (byte-identity); facts langs compose with their
    own punctuation: ja uses its colon prefix and no question mark, ar the
    Arabic question mark, prefix languages (he 'ב-') attach without a space."""
    w = C["whattodo"][lang]
    if lang not in STRICT_LANGS:
        return f"{w} {commune} ?"
    sep = "" if w.endswith(("-", ":", "：")) else " "
    q = {"ja": "", "ar": "؟"}.get(lang, "?")
    return f"{w}{sep}{commune}{q}"
LANG_NATIVE = locales.endonyms(locales.VISIBLE)  # isolation-ok: picker endonyms

C = {  # chrome labels (commune name itself is frozen, never translated)
    "whattodo":  {"fr": "Que faire à", "en": "What to do in", "de": "Was tun in", "it": "Cosa fare a", "es": "Qué hacer en", "nl": "Wat te doen in"},
    "home":      {"fr": "Accueil", "en": "Home", "de": "Startseite", "it": "Home", "es": "Inicio", "nl": "Home"},
    "langues":   {"fr": "6 langues", "en": "6 languages", "de": "6 Sprachen", "it": "6 lingue", "es": "6 idiomas", "nl": "6 talen"},
    "places_in": {"fr": "lieux de loisirs à", "en": "leisure spots in", "de": "Freizeitorte in", "it": "luoghi per il tempo libero a", "es": "lugares de ocio en", "nl": "vrijetijdsplekken in"},
    "backlink":  {"fr": "À", "en": "In", "de": "In", "it": "A", "es": "En", "nl": "In"},
    "meta_tail": {"fr": "Toutes les activités et lieux de loisirs à découvrir.", "en": "All the activities and leisure spots to discover.", "de": "Alle Aktivitäten und Freizeitorte zum Entdecken.", "it": "Tutte le attività e i luoghi per il tempo libero da scoprire.", "es": "Todas las actividades y lugares de ocio por descubrir.", "nl": "Alle activiteiten en vrijetijdsplekken om te ontdekken."},
}

# Plural, tourist-facing category labels (the grid groups lieux by category).
CATEGORY_LABELS = {
    "accrobranche":  {"fr": "Accrobranche", "en": "Tree-top adventure", "de": "Kletterwald", "it": "Parco avventura", "es": "Tirolinas y arborismo", "nl": "Klimbos"},
    "aquaparc":      {"fr": "Parcs aquatiques & piscines", "en": "Water parks & pools", "de": "Wasserparks & Bäder", "it": "Acquapark e piscine", "es": "Parques acuáticos y piscinas", "nl": "Waterparken & zwembaden"},
    "attraction":    {"fr": "Attractions & loisirs", "en": "Attractions & activities", "de": "Attraktionen & Freizeit", "it": "Attrazioni e attività", "es": "Atracciones y ocio", "nl": "Attracties & activiteiten"},
    "base-nautique": {"fr": "Bases nautiques", "en": "Water-sports centres", "de": "Wassersportzentren", "it": "Centri nautici", "es": "Bases náuticas", "nl": "Watersportcentra"},
    "bowling":       {"fr": "Bowlings", "en": "Bowling", "de": "Bowling", "it": "Bowling", "es": "Bolera", "nl": "Bowling"},
    "cascade":       {"fr": "Cascades", "en": "Waterfalls", "de": "Wasserfälle", "it": "Cascate", "es": "Cascadas", "nl": "Watervallen"},
    "casino":        {"fr": "Casinos", "en": "Casinos", "de": "Casinos", "it": "Casinò", "es": "Casinos", "nl": "Casino's"},
    "chateau":       {"fr": "Châteaux & forts", "en": "Castles & forts", "de": "Schlösser & Burgen", "it": "Castelli e forti", "es": "Castillos y fuertes", "nl": "Kastelen & forten"},
    "cinema":        {"fr": "Cinémas", "en": "Cinemas", "de": "Kinos", "it": "Cinema", "es": "Cines", "nl": "Bioscopen"},
    "croisiere":     {"fr": "Croisières", "en": "Cruises", "de": "Schifffahrten", "it": "Crociere", "es": "Cruceros", "nl": "Boottochten"},
    "divers":        {"fr": "Bien-être & divers", "en": "Wellness & more", "de": "Wellness & Mehr", "it": "Benessere e altro", "es": "Bienestar y más", "nl": "Wellness & overig"},
    "domaine":       {"fr": "Bases de loisirs", "en": "Leisure parks", "de": "Freizeitgelände", "it": "Aree ricreative", "es": "Áreas de ocio", "nl": "Recreatiegebieden"},
    "jardin":        {"fr": "Jardins", "en": "Gardens", "de": "Gärten", "it": "Giardini", "es": "Jardines", "nl": "Tuinen"},
    "karting":       {"fr": "Karting", "en": "Karting", "de": "Kartbahnen", "it": "Karting", "es": "Karting", "nl": "Karting"},
    "lac":           {"fr": "Lacs & plages", "en": "Lakes & beaches", "de": "Seen & Strände", "it": "Laghi e spiagge", "es": "Lagos y playas", "nl": "Meren & stranden"},
    "musee":         {"fr": "Musées", "en": "Museums", "de": "Museen", "it": "Musei", "es": "Museos", "nl": "Musea"},
    "parc":          {"fr": "Parcs & jardins", "en": "Parks & gardens", "de": "Parks & Gärten", "it": "Parchi e giardini", "es": "Parques y jardines", "nl": "Parken & tuinen"},
    "patinoire":     {"fr": "Patinoires", "en": "Ice rinks", "de": "Eisbahnen", "it": "Piste di pattinaggio", "es": "Pistas de hielo", "nl": "IJsbanen"},
    "plage":         {"fr": "Plages", "en": "Beaches", "de": "Strände", "it": "Spiagge", "es": "Playas", "nl": "Stranden"},
    "point-de-vue":  {"fr": "Points de vue", "en": "Viewpoints", "de": "Aussichtspunkte", "it": "Punti panoramici", "es": "Miradores", "nl": "Uitzichtpunten"},
    "sentier":       {"fr": "Sentiers & randonnées", "en": "Trails & hikes", "de": "Wege & Wanderungen", "it": "Sentieri ed escursioni", "es": "Senderos y rutas", "nl": "Paden & wandelingen"},
    "telecabine":    {"fr": "Télécabines & remontées", "en": "Cable cars & lifts", "de": "Seilbahnen & Lifte", "it": "Cabinovie e impianti", "es": "Telecabinas y remontes", "nl": "Kabelbanen & liften"},
    "voie-verte":    {"fr": "Voies vertes", "en": "Greenways", "de": "Radwege", "it": "Vie verdi", "es": "Vías verdes", "nl": "Groene routes"},
    "wakepark":      {"fr": "Wakepark", "en": "Wakepark", "de": "Wakepark", "it": "Wakepark", "es": "Wakepark", "nl": "Wakepark"},
}


def esc(s):
    return html_lib.escape(str(s or ""), quote=False)


def attr(s):
    return html_lib.escape(str(s or ""), quote=True)


def lieu_label(category, n, lang):
    word = H.CHROME["lieu_singular"][lang] if n == 1 else H.CHROME["lieu_plural"][lang]
    return word


def cat_label(category, lang):
    row = CATEGORY_LABELS.get(category)
    if row:
        return row.get(lang) or row["fr"]
    return category.replace("-", " ").capitalize()


def commune_url(commune_slug, lang):
    return f"{BASE}/{commune_slug}/" if lang == "fr" else f"{BASE}/{lang}/{commune_slug}/"


def fiche_name(d, lang):
    i = d.get("i18n", {}) or {}
    loc = i.get(lang) or {}
    fr = i.get("fr") or {}
    return loc.get("name") or fr.get("name") or d.get("slug")


# ---------------------------------------------------------------- chrome lift

_TEMPLATE_CACHE = {}


def template_html(lang):
    if lang not in _TEMPLATE_CACHE:
        _TEMPLATE_CACHE[lang] = (ROOT / TEMPLATE_HUB[lang] / "index.html").read_text(encoding="utf-8")
    return _TEMPLATE_CACHE[lang]


def lift_style(lang, hero_css):
    style = re.search(r"<style>.*?</style>", template_html(lang), re.S).group(0)
    style = re.sub(r'--hub-hero-img:url\("[^"]*"\)', f'--hub-hero-img:url("{hero_css}")', style, count=1)
    return style


def lift_scripts(lang):
    """The three trailing <script> IIFEs between </footer> and </body>."""
    m = re.search(r"</footer>(.*?)</body>", template_html(lang), re.S)
    return m.group(1).strip("\n")


def lift_footer(lang, alts):
    """Footer with the Langue column's links swapped to this commune's URLs,
    one per visible language (incl. pl)."""
    footer = re.search(r'<footer class="site">.*?</footer>', template_html(lang), re.S).group(0)
    new_ul = "<ul>" + "".join(
        f'<li><a href="{attr(alts[l])}" hreflang="{l}">{LANG_NATIVE[l]}</a></li>' for l in VIS
    ) + "</ul>"
    # The only <ul> in the footer carrying hreflang= is the Langue column.
    footer = re.sub(
        r'<ul>(?:<li><a href="[^"]*" hreflang="[a-z-]+">[^<]*</a></li>)+</ul>',
        lambda _m: new_ul, footer, count=1,
    )
    return footer


# ---------------------------------------------------------------- hero pick

def pick_hero_css(c):
    """First local, on-disk hero among the commune's lieux; else a safe fallback."""
    for l in c["lieux"]:
        d = load_fiche(l["slug"])
        hero = (d.get("hero_image") or "").strip()
        if hero.startswith("/") and (ROOT / hero.lstrip("/")).exists():
            return hero
    if (ROOT / "og-image.jpg").exists():
        return "/og-image.jpg"
    return "/og-image.jpg"


# ---------------------------------------------------------------- fiche cache

_FICHE = {}


def load_fiche(slug):
    if slug not in _FICHE:
        _FICHE[slug] = json.loads((ROOT / "Json" / f"{slug}.json").read_text(encoding="utf-8"))
    return _FICHE[slug]


# statuses held out of render (build_all_locales does the same) — a commune
# page must never link to a fiche that no _site page exists for, or the
# link-integrity gate trips (the commune-404 bug class).
HELD_STATUS = ("draft", "unverified")


def load_communes():
    """Load the commune manifest, dropping any lieu whose fiche is held out of
    render (status draft/unverified) so a demoted fiche can never leave a 404
    on a commune page. lieux_count is recomputed to match. Missing-Json entries
    are kept so main()'s drift check still reports them loudly."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for c in manifest["communes"]:
        kept = []
        for l in c["lieux"]:
            p = ROOT / "Json" / f"{l['slug']}.json"
            if p.exists() and load_fiche(l["slug"]).get("status") in HELD_STATUS:
                continue
            kept.append(l)
        c["lieux"] = kept
        c["lieux_count"] = len(kept)
    return manifest["communes"]


# ---------------------------------------------------------------- JSON-LD

def jsonld_itemlist(c, lang, url, alts):
    items = []
    for pos, l in enumerate(c["lieux"], 1):
        d = load_fiche(l["slug"])
        lang_prefix = "" if lang == "fr" else f"/{lang}"
        item = {
            "@type": "TouristAttraction",
            "name": fiche_name(d, lang),
            "url": f"{BASE}{lang_prefix}/{l['slug']}",
            "address": {
                "@type": "PostalAddress",
                "addressLocality": c["commune"],
                "addressRegion": siteconfig.DEPT_NAME,
                "addressCountry": "FR",
            },
        }
        lat, lon = d.get("latitude"), d.get("longitude")
        if lat is not None and lon is not None:
            item["geo"] = {"@type": "GeoCoordinates", "latitude": lat, "longitude": lon}
        hero = (d.get("hero_image") or "").strip()
        if hero:
            item["image"] = hero
        items.append({"@type": "ListItem", "position": pos, "item": item})
    obj = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "@id": f"{url}#itemlist",
        "name": c["commune"],
        "description": f"{c['lieux_count']} {C['places_in'][lang]} {c['commune']}",
        "numberOfItems": c["lieux_count"],
        "itemListOrder": "https://schema.org/ItemListOrderAscending",
        "inLanguage": lang,
        "isPartOf": {"@type": "CollectionPage", "@id": url},
        "itemListElement": items,
    }
    return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False, indent=2) + "</script>"


def jsonld_collection(c, lang, url):
    obj = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "url": url,
        "name": c["commune"],
        "inLanguage": lang,
        "isPartOf": {"@type": "WebSite", "url": f"{BASE}/", "name": siteconfig.SITE_NAME},
        "numberOfItems": c["lieux_count"],
    }
    return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False, indent=2) + "</script>"


# ---------------------------------------------------------------- page render

def render_page(c, lang, intros):
    slug = c["slug"]
    commune = c["commune"]
    alts = {l: commune_url(slug, l) for l in VIS}
    url = alts[lang]
    title = f"{_title_q(lang, commune)} · {siteconfig.SITE_NAME}"
    if lang in STRICT_LANGS:
        # strict prose: a facts language shows its OWN intro or none at all —
        # the FR fallback below is for the six live locales only.
        intro = intros.get(slug, {}).get(lang) or ""
    else:
        intro = intros.get(slug, {}).get(lang) or intros.get(slug, {}).get("fr") or ""
    meta_desc = f"{_title_q(lang, commune)} {c['lieux_count']} {C['places_in'][lang]} {commune}. {C['meta_tail'][lang]}"
    hero_css = pick_hero_css(c)

    # hreflang blocks (both forms, matching the hub template)
    hl1 = "\n".join(f'<link rel="alternate" hreflang="{l}" href="{alts[l]}">' for l in VIS) \
        + f'\n<link rel="alternate" hreflang="x-default" href="{alts["fr"]}">'
    hl2 = "\n".join(f'<link href="{alts[l]}" hreflang="{l}" rel="alternate"/>' for l in VIS) \
        + f'\n<link href="{alts["fr"]}" hreflang="x-default" rel="alternate"/>'

    # header lang-menu
    def _menu_link(l):
        cur = 'aria-current="true" ' if l == lang else ""
        return f'<a {cur}href="{attr(alts[l])}" hreflang="{l}">{LANG_NATIVE[l]}</a>'
    menu = "".join(_menu_link(l) for l in VIS)
    brand_href = f"{BASE}/" if lang == "fr" else f"{BASE}/{lang}/"

    # grid grouped by category (lieux already sorted (category, slug) in manifest)
    cats = []
    for l in c["lieux"]:
        if l["category"] not in cats:
            cats.append(l["category"])
    sections = []
    for cat in cats:
        entries = [l for l in c["lieux"] if l["category"] == cat]
        n = len(entries)
        cards = []
        for l in entries:
            d = load_fiche(l["slug"])
            cards.append(H.fiche_card_html(d, lang, l["slug"]))
        sections.append(
            f'<div class="commune-section" data-commune="{attr(commune)}">\n'
            f'<div class="commune-head"><h3>{esc(cat_label(cat, lang))}</h3>'
            f'<span class="commune-count">{n} {lieu_label(cat, n, lang)}</span></div>\n'
            f'<div class="carousel">\n' + "\n".join(cards) + "\n</div>\n</div>"
        )
    grid = '<main>\n<div class="wrap">\n' + "\n".join(sections) + "\n</div>\n</main>"

    # dir attribute rides ONLY on RTL pages (ar/he) — the six stay byte-identical
    dir_attr = ' dir="rtl"' if locales.DIR.get(lang) == "rtl" else ""
    head = f"""<!DOCTYPE html>

<html lang="{lang}"{dir_attr}>
<head>
<script>document.documentElement.classList.add('js')</script>
{hl1}
<meta charset="utf-8"/>
<meta content="width=device-width,initial-scale=1,viewport-fit=cover" name="viewport"/>
<meta content="#f6f1e7" name="theme-color"/>
<title>{esc(title)}</title>
<link href="/favicon.ico" rel="icon" type="image/x-icon"/>
<link href="/favicon-32x32.png" rel="icon" sizes="32x32" type="image/png"/>
<link href="/favicon-48x48.png" rel="icon" sizes="48x48" type="image/png"/>
<link href="/favicon-16x16.png" rel="icon" sizes="16x16" type="image/png"/>
<link href="/apple-touch-icon.png" rel="apple-touch-icon" sizes="180x180"/>
<link href="/site.webmanifest" rel="manifest"/>

<link href="{url}" rel="canonical"/>
<meta content="{attr(meta_desc)}" name="description"/>

{hl2}
<link href="https://fonts.googleapis.com" rel="preconnect"/>
<link crossorigin="" href="https://fonts.gstatic.com" rel="preconnect"/>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght,SOFT@0,9..144,300..600,50;1,9..144,300..500,50&amp;family=Inter:wght@400;500;600;700&amp;display=swap" rel="stylesheet"/>
{lift_style(lang, hero_css)}
<meta property="og:type" content="website"/>
<meta property="og:site_name" content="{siteconfig.SITE_NAME}"/>
<meta property="og:locale" content="{OG_LOCALE[lang]}"/>
<meta property="og:url" content="{url}"/>
<meta property="og:title" content="{attr(title)}"/>
<meta property="og:description" content="{attr(meta_desc)}"/>
<meta content="{BASE}/og-image.jpg" property="og:image"/>
<meta content="{BASE}/og-image.jpg" name="twitter:image"/>
{jsonld_itemlist(c, lang, url, alts)}
{jsonld_collection(c, lang, url)}
</head>"""

    catcher = f"{c['lieux_count']} {C['places_in'][lang]} {commune} · {siteconfig.DEPT_NAME}"
    fs = _filter_strings(lang)
    intro_section = (
        '<section aria-label="intro" class="hub-intro">\n'
        '<div class="wrap">\n'
        f'<p class="lead">{esc(intro)}</p>\n'
        '</div>\n'
        '</section>'
    )
    if lang in STRICT_LANGS and not intro:
        intro_section = ""   # strict: no intro prose yet → no empty shell section
    body = f"""<body>
<div aria-hidden="true" class="cursor-glow" id="cursorGlow"></div>
<header class="site">
<a class="brand" href="{brand_href}">
<span aria-hidden="true" class="mark">
<svg fill="none" viewbox="0 0 34 34">
<path d="M3 28 L11 12 L16 20 L22 6 L31 28 Z" fill="#1c1814"></path>
<polygon fill="#fdfaf3" points="22,6 25,11 19,11"></polygon>
<circle cx="28" cy="10" fill="#e07a3f" r="2.5"></circle>
</svg>
</span>
<span><b>{BRAND_SHORT}</b> <i>· {siteconfig.DEPT_NAME}</i></span>
</a>
{nearme_button(lang, "margin-left:auto")}
<details class="lang-picker">
<summary><b>{lang.upper()}</b> · {C['langues'][lang]}</summary>
<div class="lang-menu">
{menu}
</div>
</details>
</header>
<nav aria-label="breadcrumb" class="crumb">
<a href="{brand_href}">{esc(C['home'][lang])}</a>
<span class="sep">/</span>
<b>{esc(commune)}</b>
</nav>
<section class="hub-hero">
<div class="wrap">
<h1>{esc(commune)}</h1>
<p class="hub-catcher">{esc(catcher)}</p>
</div>
</section>
{intro_section}
<div class="filter-bar">
<div class="wrap">
<div class="filter-bar__head">
<div class="count-live"><b id="count-n">0</b> <span id="count-label">{H.CHROME['lieu_plural'][lang]}</span></div>
<button aria-controls="filter-panel" aria-expanded="false" class="filter-toggle" type="button">
<span>{fs['filtres']}</span>
<span class="filter-toggle__badge" hidden="" id="filter-toggle-badge">0</span>
<svg aria-hidden="true" class="filter-toggle__chev" height="11" viewbox="0 0 12 12" width="11"><path d="M2 4l4 4 4-4" fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="1.5"></path></svg>
</button>
</div>
<div class="filter-panel" id="filter-panel">
<label>
<span>{fs['acces']}</span>
<div class="access-group" id="filt-access">
<button class="active" data-v="all">{fs['tous']}</button>
<button data-v="free">{fs['gratuit']}</button>
<button data-v="paid">{fs['payant']}</button>
</div>
</label>
<label>
<span>{fs['tri']}</span>
<select id="filt-sort"><option value="commune">{fs['by_category']}</option><option value="alpha">A → Z</option></select>
</label>
</div>
</div>
</div>
<div id="empty-state" style="display:none;text-align:center;padding:3rem 1rem;color:var(--ink-mute)"><p style="font:600 1.05rem var(--sans);color:var(--ink);margin:0 0 .35rem"><b>{fs['no_results']}</b></p><p style="font:400 .9rem var(--sans);margin:0">{fs['no_match']}</p></div>
{grid}
{lift_footer(lang, alts)}
{lift_scripts(lang)}
{assets.script_tag("nearme.js")}
{assets.script_tag("duck.js")}
</body>
</html>"""
    return head + "\n" + body + "\n"


# ---------------------------------------------------------------- reciprocal backlink

FENCE_RE = re.compile(r"<!--commune-link:start-->.*?<!--commune-link:end-->", re.S)
CRUMB_ANCHOR = re.compile(r'(<main id="main">\s*<div class="wrap"><nav class="crumb".*?</nav></div>)', re.S)
PROTECTED = ("Chez Nous à la Plage", "Chalet du Tornet")


def backlink_markup(commune, commune_slug, lang):
    href = commune_url(commune_slug, lang)
    b = C['backlink'][lang]
    sep = "" if b.endswith(("-", ":", "：")) else " "   # he 'ב-' / ja '所在地：' attach
    label = f"{b}{sep}{commune}"
    return (
        "<!--commune-link:start-->"
        f'<div class="wrap" style="margin:.2rem 0 .6rem"><a class="commune-link" '
        f'href="{attr(href)}" style="display:inline-block;font-size:.85rem;'
        f'font-weight:600;color:var(--accent)">← {esc(label)}</a></div>'
        "<!--commune-link:end-->"
    )


def inject_backlink(fiche_path, commune, commune_slug, lang):
    """Insert-or-replace the fenced backlink. Returns 'written'|'skip-protected'|'missing'."""
    if not fiche_path.exists():
        return "missing"
    html = fiche_path.read_text(encoding="utf-8")
    before = {p: html.count(p) for p in PROTECTED}
    block = backlink_markup(commune, commune_slug, lang)
    if FENCE_RE.search(html):
        new = FENCE_RE.sub(lambda _m: block, html, count=1)
    else:
        new, n = CRUMB_ANCHOR.subn(lambda m: m.group(1) + block, html, count=1)
        if n == 0:
            new = html.replace("</body>", block + "</body>", 1)
    # protected safety: counts of protected markers must be unchanged
    after = {p: new.count(p) for p in PROTECTED}
    if after != before:
        return "skip-protected"
    if new != html:
        fiche_path.write_text(new, encoding="utf-8")
    return "written"


# ---------------------------------------------------------------- facts langs

def build_for_lang(lang):
    """HANDOFF-31: render every commune page of ONE facts-first language through
    this template (same chrome lift, same card renderer as the six) and inject
    the reciprocal backlinks onto that language's fiches. Called by
    build_fulltree_lang after the lang's hubs exist (template lift source)."""
    register_facts_lang(lang)
    communes = load_communes()
    intros = json.loads(INTROS.read_text(encoding="utf-8")) if INTROS.exists() else {}
    written = 0
    for c in communes:
        out = ROOT / lang / c["slug"] / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_page(c, lang, intros), encoding="utf-8")
        written += 1
    stats = {"written": 0, "skip-protected": 0, "missing": 0}
    for c in communes:
        for l in c["lieux"]:
            fp = ROOT / lang / f"{l['slug']}.html"
            r = inject_backlink(fp, c["commune"], c["slug"], lang)
            stats[r] += 1
    return written, stats


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    communes = load_communes()
    intros = json.loads(INTROS.read_text(encoding="utf-8")) if INTROS.exists() else {}

    # reconcile: every commune's live lieux must match the manifest
    drift = []
    for c in communes:
        for l in c["lieux"]:
            if not (ROOT / "Json" / f"{l['slug']}.json").exists():
                drift.append(f"{c['commune']}: missing Json/{l['slug']}.json")
    if drift:
        print("LIEUX DRIFT — stopping:")
        for d in drift:
            print("  " + d)
        sys.exit(1)

    planned = []
    for c in communes:
        for lang in LANGS:
            rel = f"{c['slug']}/index.html" if lang == "fr" else f"{lang}/{c['slug']}/index.html"
            planned.append(rel)

    backlink_files = sum(len(c["lieux"]) for c in communes) * len(LANGS)

    if args.dry_run:
        print(f"PLAN — {len(communes)} communes × {len(LANGS)} langs = {len(planned)} pages")
        for c in communes:
            print(f"  {c['commune']:24} {c['lieux_count']} lieux  -> {c['slug']}/  (+{len(LANGS)} langs)")
        print(f"reciprocal backlink target fiches: {sum(len(c['lieux']) for c in communes)} × 6 = {backlink_files} files")
        miss_intro = [c["slug"] for c in communes if not intros.get(c["slug"], {}).get("en")]
        if miss_intro:
            print(f"  intros missing locale translations (will fall back to FR): {miss_intro}")
        return

    # render pages
    written = 0
    for c in communes:
        for lang in LANGS:
            out = ROOT / (f"{c['slug']}/index.html" if lang == "fr" else f"{lang}/{c['slug']}/index.html")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(render_page(c, lang, intros), encoding="utf-8")
            written += 1
    print(f"wrote {written} commune pages")

    # reciprocal backlinks
    stats = {"written": 0, "skip-protected": 0, "missing": 0}
    skipped = []
    for c in communes:
        for l in c["lieux"]:
            for lang in LANGS:
                fp = ROOT / (f"{l['slug']}.html" if lang == "fr" else f"{lang}/{l['slug']}.html")
                r = inject_backlink(fp, c["commune"], c["slug"], lang)
                stats[r] += 1
                if r == "skip-protected":
                    skipped.append(f"{lang}/{l['slug']}")
    print(f"backlinks: {stats}")
    if skipped:
        print("  skipped (protected-safety):")
        for s in skipped:
            print("   " + s)


if __name__ == "__main__":
    main()
