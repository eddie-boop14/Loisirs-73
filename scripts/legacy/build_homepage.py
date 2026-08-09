#!/usr/bin/env python3
"""
Build the 5 locale homepages from the prototype's design + the existing
per-locale section content.

For each locale {fr, en, de, it, es} the script:
  1. Reads {lang}/index.html (or /index.html for fr) and extracts
     - the <head> block (canonical, hreflang, JSON-LD, OG, AI links, meta
       description, title) — preserved byte-for-byte EXCEPT the inline
       <style> which is replaced by the prototype's CSS.
     - the language-picker <details> block — preserved.
     - each existing <section class="cat" id="X">...</section> — captures
       h2 HTML, see-all href + label, and the verbatim list of
       <article class="card">...</article> blocks. No card content drift.
     - the footer's Categories list (Task-4 hubs) — preserved.
  2. Emits a new homepage assembled from the prototype's chrome:
     fixed scene layers (.sky/.orb/.clouds/.rainveil/.lamp), header with
     near-me + weather toggle + language picker, hero with weather-now
     strip, then sections re-ordered into the outdoor→mix→crossover→indoor
     story flow, with each h2 retagged with a weather-band kicker and a
     <span class="count"></span> placeholder populated at runtime from
     /lieux.json.
  3. Loads /scripts/l74sort.js and embeds the scene engine inline.
  4. Injects an inline <script type="application/json" id="l74-data">
     keyed by slug, providing lat/lng/categories/subcategories so the
     sort engine can run without a fetch.

The sitemap.xml, _redirects, _headers, all per-fiche pages and all hub
pages are NOT touched. Only index.html, en/index.html, de/index.html,
it/index.html, es/index.html are rewritten.
"""
from __future__ import annotations

import json
import sys
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LIEUX = json.loads((REPO / "lieux.json").read_text(encoding="utf-8"))["lieux"]
BY_SLUG = {l["slug"]: l for l in LIEUX}

# --- Locale configuration -----------------------------------------------------

LOCALES = [
    {"code": "fr", "subdir": "",   "lang": "fr"},
    {"code": "en", "subdir": "en", "lang": "en"},
    {"code": "de", "subdir": "de", "lang": "de"},
    {"code": "it", "subdir": "it", "lang": "it"},
    {"code": "es", "subdir": "es", "lang": "es"},
]

# Section order in the new story flow.
# fr has 'voie-verte'; locales don't — handled by skipping absent sections.
OUTDOOR_SECTIONS = ["lac", "cascade", "point-de-vue", "sentier", "voie-verte", "telecabine", "domaine"]
MIX_SECTIONS = ["chateau"]
INDOOR_SECTIONS = ["musee", "attraction", "divers"]

# lieux.json `categories` value → homepage section id.
# `plage` shares the `#lac` section ("Lacs & plages"); `parc` shares `#domaine`
# ("Bases de loisirs"). Everything else is 1:1.
CAT_TO_SECTION = {
    "lac": "lac", "plage": "lac",
    "cascade": "cascade",
    "point-de-vue": "point-de-vue",
    "sentier": "sentier",
    "voie-verte": "voie-verte",
    "telecabine": "telecabine",
    "domaine": "domaine", "parc": "domaine",
    "chateau": "chateau",
    "musee": "musee",
    "attraction": "attraction",
    "divers": "divers",
}

# Per-slug override: venues whose lieux.json category is `divers` per the
# "uncertain → divers" rule but which are clearly OUTDOOR and should sit under
# the ☀ band on the homepage, not under ☂ rain. Routes 14 venues out of
# #divers; the rainy #divers shrinks to abbayes + thermes + bureau-des-guides.
HOMEPAGE_SECTION_OVERRIDE = {
    # jardins (botanical gardens)
    "jardin-cimes-passy": "domaine",
    "jardin-des-cinq-sens": "domaine",
    "jardin-jaysinia-samoens": "domaine",
    # parcs animaliers (outdoor wildlife parks)
    "les-aigles-du-leman": "domaine",
    "parc-de-merlet": "domaine",
    # croisières (lake boat tours — outdoor lake experience)
    "croisiere-bateaux-annecy-annecy": "lac",
    "croisiere-cgn-evian": "lac",
    "croisiere-cgn-thonon": "lac",
    "croisiere-cgn-yvoire": "lac",
    # karting (mostly open-air circuits)
    "karting-mk-circuit-scientrier": "domaine",
    "karting-mont-blanc-passy": "domaine",
    "karting-onlykart-roche-sur-foron": "domaine",
    "karting-rumilly-rumilly": "domaine",
    "karting-team-bouvier-pringy": "domaine",
    # jardins (v2 enriched batch) — outdoor on homepage
    "jardin-alpin-de-bellevaux": "domaine",
    "jardin-alpin-des-montets-vallorcine": "domaine",
    "jardin-les-jardins-secrets-vaulx": "domaine",
    "jardin-parc-des-jardins-de-haute-savoie-la-balme-de-sillingy": "domaine",
    "jardin-pre-curieux-evian": "domaine",
}


def section_for_slug(slug: str) -> str | None:
    """Map a slug to its target homepage section. Returns None if the lieu
    can't be placed (no known category)."""
    if slug in HOMEPAGE_SECTION_OVERRIDE:
        return HOMEPAGE_SECTION_OVERRIDE[slug]
    lieu = BY_SLUG.get(slug)
    if not lieu:
        return None
    for cat in lieu.get("categories", []):
        sid = CAT_TO_SECTION.get(cat)
        if sid:
            return sid
    return None

# Per-locale chrome strings.
STRINGS = {
    "fr": {
        "brand_tag_clear": "· Haute-Savoie",
        "brand_tag_var": "· le ciel hésite",
        "brand_tag_rain": "· côté abri",
        "kicker": "Le guide de la Haute-Savoie",
        "h1_top": "Où aller en",
        "h1_em": "Haute-Savoie",
        "lede_html": 'Tous les lieux de loisirs du département, vérifiés un par un. <b>Beau temps comme mauvais temps</b> — la page suit la météo, comme vous.',
        "wn_label_clear": "Grand beau",
        "wn_text_clear": "lacs, cascades, points de vue — dehors, tout est ouvert.",
        "wn_label_var": "Ça se couvre",
        "wn_text_var": "le ciel hésite — gardez un plan B au chaud.",
        "wn_label_rain": "Il pleut",
        "wn_text_rain": "piscines, spas, musées, bowlings — on passe à l’intérieur.",
        "footstate_clear": "Météo : grand beau",
        "footstate_var": "Météo : variable",
        "footstate_rain": "Météo : pluie",
        "wband_out": "☀ Quand il fait beau",
        "wband_in": "☂ Quand il pleut",
        "wband_mix": "☀☂ Beau temps ou pluie",
        "cross_text": "…et puis le ciel se couvre.",
        "cross_small": "continuez à descendre, on passe à l’intérieur",
        "btn_auto": "Auto",
        "btn_sun": "☀ Beau",
        "btn_rain": "☂ Pluie",
        "btn_near": "◎ Près de moi",
        "btn_near_loading": "…localisation",
        "btn_near_on": "◎ Au plus proche",
        "btn_near_demo": "◎ Depuis Annecy (démo)",
        "btn_near_off": "géoloc indisponible",
        "see_all_fallback": "Voir tout",
    },
    "en": {
        "brand_tag_clear": "· Haute-Savoie",
        "brand_tag_var": "· clouds rolling in",
        "brand_tag_rain": "· indoor side",
        "kicker": "The Haute-Savoie leisure guide",
        "h1_top": "Where to go in",
        "h1_em": "Haute-Savoie",
        "lede_html": 'Every leisure site in the department, fact-checked one by one. <b>Sun or rain</b> — the page follows the weather, just like you.',
        "wn_label_clear": "Clear skies",
        "wn_text_clear": "lakes, waterfalls, viewpoints — everything outdoors is open.",
        "wn_label_var": "Clouding over",
        "wn_text_var": "the sky is hesitating — keep a plan B in your pocket.",
        "wn_label_rain": "Raining",
        "wn_text_rain": "pools, spas, museums, bowling — let’s head inside.",
        "footstate_clear": "Weather: clear",
        "footstate_var": "Weather: variable",
        "footstate_rain": "Weather: rain",
        "wband_out": "☀ When the weather is good",
        "wband_in": "☂ When it rains",
        "wband_mix": "☀☂ Rain or shine",
        "cross_text": "…and then the sky clouds over.",
        "cross_small": "keep scrolling, we’re heading inside",
        "btn_auto": "Auto",
        "btn_sun": "☀ Sun",
        "btn_rain": "☂ Rain",
        "btn_near": "◎ Near me",
        "btn_near_loading": "…locating",
        "btn_near_on": "◎ Closest first",
        "btn_near_demo": "◎ From Annecy (demo)",
        "btn_near_off": "geolocation unavailable",
        "see_all_fallback": "View all",
    },
    "de": {
        "brand_tag_clear": "· Haute-Savoie",
        "brand_tag_var": "· der Himmel zögert",
        "brand_tag_rain": "· drinnen",
        "kicker": "Der Freizeitführer der Haute-Savoie",
        "h1_top": "Wohin in der",
        "h1_em": "Haute-Savoie",
        "lede_html": 'Alle Freizeitorte des Departements, einzeln geprüft. <b>Bei Sonne wie bei Regen</b> — die Seite folgt dem Wetter, genau wie Sie.',
        "wn_label_clear": "Strahlend schön",
        "wn_text_clear": "Seen, Wasserfälle, Aussichtspunkte — draußen ist alles offen.",
        "wn_label_var": "Es zieht sich zu",
        "wn_text_var": "der Himmel zögert — halten Sie einen Plan B bereit.",
        "wn_label_rain": "Es regnet",
        "wn_text_rain": "Schwimmbäder, Spas, Museen, Bowling — wir gehen rein.",
        "footstate_clear": "Wetter: strahlend",
        "footstate_var": "Wetter: wechselhaft",
        "footstate_rain": "Wetter: Regen",
        "wband_out": "☀ Bei schönem Wetter",
        "wband_in": "☂ Wenn es regnet",
        "wband_mix": "☀☂ Bei jedem Wetter",
        "cross_text": "…und dann zieht der Himmel zu.",
        "cross_small": "weiter scrollen, wir gehen nach drinnen",
        "btn_auto": "Auto",
        "btn_sun": "☀ Sonne",
        "btn_rain": "☂ Regen",
        "btn_near": "◎ In meiner Nähe",
        "btn_near_loading": "…wird geortet",
        "btn_near_on": "◎ Am nächsten zuerst",
        "btn_near_demo": "◎ Ab Annecy (Demo)",
        "btn_near_off": "Standort nicht verfügbar",
        "see_all_fallback": "Alle anzeigen",
    },
    "it": {
        "brand_tag_clear": "· Alta Savoia",
        "brand_tag_var": "· il cielo è incerto",
        "brand_tag_rain": "· al coperto",
        "kicker": "La guida del tempo libero dell’Alta Savoia",
        "h1_top": "Dove andare in",
        "h1_em": "Alta Savoia",
        "lede_html": 'Tutti i luoghi di svago del dipartimento, verificati uno per uno. <b>Con il sole come con la pioggia</b> — la pagina segue il meteo, come voi.',
        "wn_label_clear": "Tempo splendido",
        "wn_text_clear": "laghi, cascate, panorami — fuori è tutto aperto.",
        "wn_label_var": "Si annuvola",
        "wn_text_var": "il cielo è incerto — tenete un piano B al caldo.",
        "wn_label_rain": "Piove",
        "wn_text_rain": "piscine, terme, musei, bowling — si va al coperto.",
        "footstate_clear": "Meteo: splendido",
        "footstate_var": "Meteo: variabile",
        "footstate_rain": "Meteo: pioggia",
        "wband_out": "☀ Quando c’è bel tempo",
        "wband_in": "☂ Quando piove",
        "wband_mix": "☀☂ Con sole o pioggia",
        "cross_text": "…e poi il cielo si copre.",
        "cross_small": "continuate a scorrere, si va al coperto",
        "btn_auto": "Auto",
        "btn_sun": "☀ Sole",
        "btn_rain": "☂ Pioggia",
        "btn_near": "◎ Vicino a me",
        "btn_near_loading": "…localizzazione",
        "btn_near_on": "◎ Più vicini",
        "btn_near_demo": "◎ Da Annecy (demo)",
        "btn_near_off": "geolocalizzazione non disponibile",
        "see_all_fallback": "Vedi tutto",
    },
    "es": {
        "brand_tag_clear": "· Alta Saboya",
        "brand_tag_var": "· el cielo duda",
        "brand_tag_rain": "· bajo techo",
        "kicker": "La guía del ocio en la Alta Saboya",
        "h1_top": "A dónde ir en",
        "h1_em": "Alta Saboya",
        "lede_html": 'Todos los lugares de ocio del departamento, verificados uno a uno. <b>Haga sol o llueva</b> — la página sigue el tiempo, como usted.',
        "wn_label_clear": "Despejado",
        "wn_text_clear": "lagos, cascadas, miradores — todo está abierto al aire libre.",
        "wn_label_var": "Se nubla",
        "wn_text_var": "el cielo duda — guarde un plan B a mano.",
        "wn_label_rain": "Llueve",
        "wn_text_rain": "piscinas, balnearios, museos, boleras — entramos bajo techo.",
        "footstate_clear": "Tiempo: despejado",
        "footstate_var": "Tiempo: variable",
        "footstate_rain": "Tiempo: lluvia",
        "wband_out": "☀ Con buen tiempo",
        "wband_in": "☂ Cuando llueve",
        "wband_mix": "☀☂ Con sol o lluvia",
        "cross_text": "…y luego el cielo se cubre.",
        "cross_small": "siga bajando, entramos a cubierto",
        "btn_auto": "Auto",
        "btn_sun": "☀ Sol",
        "btn_rain": "☂ Lluvia",
        "btn_near": "◎ Cerca de mí",
        "btn_near_loading": "…localizando",
        "btn_near_on": "◎ Los más cercanos",
        "btn_near_demo": "◎ Desde Annecy (demo)",
        "btn_near_off": "geolocalización no disponible",
        "see_all_fallback": "Ver todo",
    },
}

# --- Extraction helpers -------------------------------------------------------

SECTION_RE = re.compile(
    r'<section class="cat" id="(?P<id>[a-z-]+)">(?P<body>.*?)</section>',
    re.S,
)
H2_RE = re.compile(r'<h2[^>]*>(?P<inner>.*?)</h2>', re.S)
COUNT_SPAN_RE = re.compile(r'\s*<span class="count"[^>]*>.*?</span>\s*', re.S)
SEE_ALL_RE_A = re.compile(
    r'<a\s+href="(?P<href>[^"]+)"\s+class="see-all"[^>]*>(?P<body>.*?)</a>', re.S,
)
SEE_ALL_RE_B = re.compile(
    r'<a\s+class="see-all"\s+href="(?P<href>[^"]+)"[^>]*>(?P<body>.*?)</a>', re.S,
)
CARD_RE = re.compile(r'<article class="card">.*?</article>', re.S)
CARD_HREF_RE = re.compile(r'<a\s+href="https://loisirs74\.fr/(?:[a-z]{2}/)?([a-z0-9-]+)"\s+class="card-photo"')
# Hubs use the reversed attribute order; this matches either.
CARD_SLUG_RE = re.compile(r'<a\s+(?:href="https://loisirs74\.fr/(?:[a-z]{2}/)?([a-z0-9-]+)"\s+class="card-photo"|class="card-photo"\s+href="https://loisirs74\.fr/(?:[a-z]{2}/)?([a-z0-9-]+)")')


def slug_from_card_html(card_html: str) -> str | None:
    m = CARD_SLUG_RE.search(card_html)
    if not m:
        return None
    return m.group(1) or m.group(2)


# Where to read top-up indoor cards from per locale (the hub pages).
HUB_PATH_FOR_LOCALE = {
    "fr": "attractions/index.html",
    "en": "en/attractions/index.html",
    "de": "de/attraktionen/index.html",
    "it": "it/attrazioni/index.html",
    "es": "es/atraciones/index.html",
}


def topup_attraction_cards(loc_code: str, existing_slugs: set[str], desired: int = 6) -> list[str]:
    """Pull additional <article class="card"> blocks from the locale's
    attractions hub for slugs whose lieux.json category is still 'attraction'.
    Returns up to (desired - len(existing slugs in #attraction)) cards."""
    rel = HUB_PATH_FOR_LOCALE.get(loc_code)
    if not rel:
        return []
    p = REPO / rel
    if not p.exists():
        return []
    html = p.read_text(encoding="utf-8")
    out: list[str] = []
    for card in CARD_RE.findall(html):
        slug = slug_from_card_html(card)
        if not slug or slug in existing_slugs:
            continue
        lieu = BY_SLUG.get(slug)
        if not lieu:
            continue
        if "attraction" not in (lieu.get("categories") or []):
            continue
        out.append(card)
        existing_slugs.add(slug)
        if len(out) >= desired:
            break
    return out
HEAD_RE = re.compile(r'(?P<head><head>.*?</head>)', re.S)
STYLE_BLOCK_RE = re.compile(r'<style[^>]*>.*?</style>', re.S)
TITLE_RE = re.compile(r'<title>(?P<t>.*?)</title>', re.S)
META_DESC_RE = re.compile(r'<meta name="description" content="[^"]*">')
CANONICAL_RE = re.compile(r'<link rel="canonical" href="[^"]+">')


def extract_h2_text(body: str) -> str:
    m = H2_RE.search(body)
    if not m:
        return ""
    txt = COUNT_SPAN_RE.sub("", m.group("inner")).strip()
    return txt


def extract_see_all(body: str, fallback_label: str) -> tuple[str, str]:
    m = SEE_ALL_RE_A.search(body) or SEE_ALL_RE_B.search(body)
    if not m:
        return ("#", fallback_label)
    href = m.group("href")
    inner = m.group("body")
    # take leading non-svg text
    label_m = re.match(r"\s*([^<]*?)\s*(?=<|$)", inner)
    label = label_m.group(1).strip() if label_m else fallback_label
    if not label:
        label = fallback_label
    return (href, label)


def extract_cards(body: str) -> list[str]:
    return CARD_RE.findall(body)


def slugs_in_html(html: str) -> set[str]:
    return set(CARD_HREF_RE.findall(html))


def extract_head_with_replacements(html: str) -> str:
    """Preserve the full <head> verbatim except the inline <style> block,
    which is removed (the new <style> is appended right before </head>)."""
    m = HEAD_RE.search(html)
    if not m:
        raise SystemExit("no <head> found")
    head = m.group("head")
    head = STYLE_BLOCK_RE.sub("", head, count=1)
    return head


def extract_lang_picker(html: str) -> str:
    m = re.search(r'<details class="lang-picker">.*?</details>', html, re.S)
    return m.group(0) if m else ""


def extract_body_ld_blocks(html: str) -> list[str]:
    """Return any <script type=application/ld+json> blocks that live in
    <body> (not in <head>). Preserves them verbatim so the SEO surface stays
    identical."""
    body_start = html.find("<body>")
    if body_start == -1:
        return []
    body = html[body_start:]
    return re.findall(
        r'<script type="application/ld\+json">.*?</script>',
        body,
        re.S,
    )


def extract_footer_categories(html: str) -> str | None:
    """Return the inner <ul>...</ul> from the footer's 'Categories' column."""
    m = re.search(
        r'<div class="foot-col">\s*<h[34]>[^<]*[Cc]at[eé]gor[íi]as?\b[^<]*</h[34]>\s*(<ul>.*?</ul>)',
        html,
        re.S,
    )
    if m:
        return m.group(1)
    # Locale variants: Categorías, Categorie, Kategorien, Categories
    m = re.search(
        r'<div class="foot-col">\s*<h[34]>(?:[Kk]ategorien|[Cc]ategor(?:ies|íe|ías|ie))[^<]*</h[34]>\s*(<ul>.*?</ul>)',
        html, re.S,
    )
    return m.group(1) if m else None


# --- New CSS, scene HTML, and JS templates -----------------------------------

PROTOTYPE_STYLE = r"""<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth}
ul,ol{list-style:none}img,svg{display:block;max-width:100%;height:auto}a{color:inherit;text-decoration:none}

:root{
  --day-sky-1:#f6e7d4;--day-sky-2:#e8d5b8;--day-paper:#f6f1e7;
  --day-ink:#1c1814;--day-ink-2:#3d342a;--day-ink-3:#7a6b58;--day-line:#d9cdb3;
  --day-card:#fdfaf3;--day-card-ink:#1c1814;--day-card-ink2:#3d342a;--day-card-ink3:#7a6b58;--day-card-line:#d9cdb3;
  --day-accent:#e07a3f;--day-accent-soft:#f4b88a;
  --rain-sky-1:#202b3d;--rain-sky-2:#161d29;--rain-paper:#161d29;
  --rain-ink:#f3eee3;--rain-ink-2:#cdd5e0;--rain-ink-3:#93a1b4;--rain-line:#33415a;
  --rain-card:#f6f1e7;--rain-card-ink:#1c1814;--rain-card-ink2:#3d342a;--rain-card-ink3:#7a6b58;--rain-card-line:#d9cdb3;
  --rain-accent:#f3a64b;--rain-accent-soft:#ffc987;
  --sky-1:var(--day-sky-1);--sky-2:var(--day-sky-2);--paper:var(--day-paper);
  --ink:var(--day-ink);--ink-2:var(--day-ink-2);--ink-3:var(--day-ink-3);--line:var(--day-line);
  --card:var(--day-card);--card-ink:var(--day-card-ink);--card-ink2:var(--day-card-ink2);--card-ink3:var(--day-card-ink3);--card-line:var(--day-card-line);
  --accent:var(--day-accent);--accent-soft:var(--day-accent-soft);
  --max:1280px;--pad:clamp(1.25rem,3.5vw,2rem);
  --serif:"Fraunces",ui-serif,Georgia,serif;
  --sans:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,system-ui,sans-serif;
  --ease:cubic-bezier(.4,0,.2,1);--ease-out:cubic-bezier(.16,1,.3,1);
  --turn:background-color 1.1s var(--ease),color 1.1s var(--ease),border-color 1.1s var(--ease);
}
html,body{background:var(--paper);color:var(--ink);transition:var(--turn)}
body{font-family:var(--sans);font-size:16px;line-height:1.55;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;overflow-x:hidden}
::selection{background:var(--accent);color:var(--paper)}
.wrap{max-width:var(--max);margin-inline:auto;padding-inline:var(--pad);position:relative;z-index:2}

header.site{position:fixed;top:0;left:0;right:0;z-index:60;padding:1rem var(--pad);
  display:flex;align-items:center;justify-content:space-between;gap:1rem;
  transition:var(--turn),padding .35s var(--ease);border-bottom:1px solid transparent}
header.site.scrolled{backdrop-filter:blur(14px) saturate(1.1);-webkit-backdrop-filter:blur(14px) saturate(1.1);
  border-bottom-color:var(--line);padding:.7rem var(--pad);
  background:color-mix(in srgb,var(--paper) 86%,transparent)}
.brand{display:flex;align-items:center;gap:.75rem;color:var(--ink);font-family:var(--serif);font-weight:500;transition:var(--turn)}
.brand .mark{width:34px;height:34px;display:inline-flex;align-items:center;justify-content:center}
.brand b{font-size:1.2rem;line-height:1;font-weight:500}
.brand i{font-style:normal;color:var(--ink-3);font-size:.82rem;font-weight:400;letter-spacing:.06em;transition:var(--turn)}

.nav-right{display:flex;align-items:center;gap:.6rem;flex-wrap:wrap;justify-content:flex-end}
.weather-toggle{display:inline-flex;gap:.25rem;padding:.28rem;border:1px solid var(--line);border-radius:999px;
  background:color-mix(in srgb,var(--paper) 70%,transparent);transition:var(--turn)}
.weather-toggle button{font:600 .7rem var(--sans);letter-spacing:.06em;color:var(--ink-3);background:none;border:0;
  cursor:pointer;padding:.35rem .8rem;border-radius:999px;transition:all .3s var(--ease);display:inline-flex;align-items:center;gap:.35rem}
.weather-toggle button.on{background:var(--accent);color:var(--paper)}
.weather-toggle button:not(.on):hover{color:var(--ink)}
.near-me{font:600 .7rem var(--sans);letter-spacing:.04em;color:var(--ink-3);background:none;border:1px solid var(--line);
  border-radius:999px;padding:.4rem .8rem;cursor:pointer;transition:var(--turn);display:inline-flex;align-items:center;gap:.35rem}
.near-me:hover{color:var(--ink);border-color:var(--ink-3)}
.near-me.on{background:var(--accent);color:#fff;border-color:var(--accent)}

.lang-picker{position:relative;font:600 .7rem var(--sans)}
.lang-picker summary{cursor:pointer;list-style:none;padding:.4rem .8rem;border:1px solid var(--line);border-radius:999px;color:var(--ink-3);transition:var(--turn)}
.lang-picker summary::-webkit-details-marker{display:none}
.lang-picker summary:hover{color:var(--ink);border-color:var(--ink-3)}
.lang-picker[open] .lang-menu{display:flex}
.lang-menu{display:none;position:absolute;top:calc(100% + .4rem);right:0;flex-direction:column;background:var(--paper);border:1px solid var(--line);border-radius:10px;box-shadow:0 18px 40px -22px rgba(0,0,0,.35);padding:.35rem;min-width:9rem;z-index:70}
.lang-menu a{padding:.5rem .65rem;border-radius:6px;font-size:.85rem;color:var(--ink-2);transition:var(--turn)}
.lang-menu a:hover{background:color-mix(in srgb,var(--accent) 14%,transparent);color:var(--ink)}
.lang-menu a[aria-current="true"]{background:color-mix(in srgb,var(--ink) 8%,transparent);color:var(--ink);font-weight:600}

main{position:relative;z-index:3}

.sky{position:fixed;inset:0;z-index:0;pointer-events:none;
  background:linear-gradient(180deg,var(--sky-2) 0%,var(--sky-1) 45%,var(--paper) 100%);transition:var(--turn)}
.orb{position:fixed;right:12vw;top:14vh;width:clamp(180px,26vw,420px);height:clamp(180px,26vw,420px);
  border-radius:50%;z-index:0;pointer-events:none;transition:background 1.1s var(--ease),transform 1.1s var(--ease),opacity 1.1s var(--ease)}
.clouds{position:fixed;inset:0 0 auto 0;height:60vh;z-index:0;pointer-events:none;opacity:0;transition:opacity 1.1s var(--ease)}
.clouds svg{width:140%;animation:drift 60s linear infinite}
@keyframes drift{from{transform:translateX(0)}to{transform:translateX(-28%)}}
.rainveil{position:fixed;inset:0;z-index:1;pointer-events:none;opacity:0;transition:opacity 1.1s var(--ease);
  background-image:repeating-linear-gradient(101deg,rgba(127,168,201,0) 0 22px,rgba(127,168,201,.12) 22px 23px,rgba(127,168,201,0) 23px 46px);
  mask-image:linear-gradient(180deg,transparent 0,#000 25%,#000 100%);animation:raindrift 14s linear infinite}
@keyframes raindrift{from{background-position:0 -200px}to{background-position:-120px 600px}}
.lamp{position:fixed;right:8vw;bottom:14vh;width:clamp(280px,40vw,560px);height:clamp(280px,40vw,560px);
  border-radius:50%;z-index:1;pointer-events:none;opacity:0;transition:opacity 1.4s var(--ease);
  background:radial-gradient(circle,rgba(243,166,75,.30) 0%,rgba(224,113,47,.12) 35%,rgba(243,166,75,0) 68%);
  animation:flicker 6s ease-in-out infinite alternate}
@keyframes flicker{from{opacity:1;transform:scale(1)}to{opacity:1;transform:scale(1.04)}}

.hero{position:relative;min-height:100vh;display:flex;flex-direction:column;justify-content:flex-end;padding:140px 0 0;isolation:isolate}
.hero-content{position:relative;z-index:10;padding-bottom:16vh}
.kicker{display:inline-flex;align-items:center;gap:.65rem;font:600 .75rem var(--sans);color:var(--ink-3);
  letter-spacing:.16em;text-transform:uppercase;margin-bottom:2rem;transition:var(--turn)}
.kicker::before{content:"";width:1.5rem;height:1px;background:var(--accent);transition:var(--turn)}
.hero h1{font-family:var(--serif);font-size:clamp(52px,10vw,170px);font-weight:400;line-height:.92;letter-spacing:-.035em;
  color:var(--ink);font-variation-settings:"SOFT" 50;max-width:15ch;transition:var(--turn)}
.hero h1 em{font-style:italic;font-weight:300;background:linear-gradient(120deg,var(--accent),var(--accent-soft));
  -webkit-background-clip:text;background-clip:text;color:transparent}
.lede{max-width:640px;margin-top:2rem;font-family:var(--serif);font-size:clamp(1.05rem,1rem + .4vw,1.35rem);
  line-height:1.5;color:var(--ink-2);transition:var(--turn)}
.lede b{color:var(--ink);font-weight:500}
.weather-now{margin-top:2.25rem;padding-top:1.5rem;border-top:1px solid var(--line);display:flex;align-items:baseline;
  gap:.75rem;flex-wrap:wrap;transition:var(--turn)}
.weather-now .dot{width:8px;height:8px;border-radius:50%;background:var(--accent);align-self:center;transition:var(--turn)}
.weather-now b{font:600 .72rem var(--sans);letter-spacing:.16em;text-transform:uppercase;color:var(--ink-3);transition:var(--turn)}
.weather-now span{font-family:var(--serif);font-style:italic;font-size:1.1rem;color:var(--ink-2);transition:var(--turn)}

section.cat{padding:clamp(3rem,5vw,5rem) 0;position:relative;z-index:2}
section.cat + section.cat{border-top:1px solid var(--line);transition:var(--turn)}
.cat-head{display:flex;align-items:flex-end;justify-content:space-between;gap:1rem;margin-bottom:2.5rem;flex-wrap:wrap}
.cat-head-left{display:flex;flex-direction:column;gap:.4rem}
.weather-band{font:600 .65rem var(--sans);letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);
  display:inline-flex;align-items:center;gap:.4rem;transition:var(--turn)}
section.cat h2{font-family:var(--serif);font-size:clamp(1.9rem,1.4rem + 1.7vw,3rem);line-height:1.02;letter-spacing:-.02em;
  font-weight:400;color:var(--ink);font-variation-settings:"SOFT" 50;display:flex;align-items:baseline;gap:.65rem;
  flex-wrap:wrap;transition:var(--turn)}
section.cat h2 .count{font:600 .7rem var(--sans);letter-spacing:.16em;text-transform:uppercase;color:var(--ink-3);transition:var(--turn)}
.see-all{font-family:var(--serif);font-style:italic;font-size:1.05rem;color:#a04612;display:inline-flex;
  align-items:center;gap:.45rem;border-bottom:1px solid #a04612;padding-bottom:1px;align-self:flex-end;
  transition:gap .3s var(--ease-out),color 1.1s var(--ease),border-color 1.1s var(--ease)}
.see-all svg{width:14px;height:14px}
.see-all:hover{gap:.7rem}

.crossover{position:relative;z-index:2;text-align:center;padding:clamp(2.5rem,6vw,5rem) 0;border-top:1px solid var(--line);transition:var(--turn)}
.crossover p{font-family:var(--serif);font-style:italic;font-size:clamp(1.3rem,1rem + 1.4vw,2.2rem);
  color:var(--ink-2);max-width:18ch;margin-inline:auto;line-height:1.25;transition:var(--turn)}
.crossover small{display:block;margin-top:1rem;font:600 .68rem var(--sans);letter-spacing:.16em;text-transform:uppercase;color:var(--ink-3);transition:var(--turn)}

.carousel{display:grid;grid-template-columns:repeat(auto-fill,minmax(17rem,1fr));gap:2rem 1.6rem}
@media(max-width:680px){.carousel{display:flex;gap:1rem;overflow-x:auto;padding-bottom:.5rem;scrollbar-width:none}
  .carousel::-webkit-scrollbar{display:none}.carousel>.card{flex:0 0 78vw;max-width:19rem}}
.card{background:var(--card);border:1px solid var(--card-line);border-radius:10px;overflow:hidden;
  display:flex;flex-direction:column;position:relative;color:var(--card-ink);min-width:0;
  transition:transform .5s var(--ease-out),box-shadow .5s var(--ease),background-color 1.1s var(--ease),border-color 1.1s var(--ease)}
.card:hover{transform:translateY(-6px);box-shadow:0 30px 55px -25px rgba(0,0,0,.4)}
.card-photo{display:block;width:100%;aspect-ratio:4/3;position:relative;overflow:hidden;
  background:linear-gradient(135deg,#2c3a52,#1f2836 60%,#161d29)}
.card-photo::after{content:"";position:absolute;inset:0;pointer-events:none;
  background:radial-gradient(120% 90% at 75% 110%,rgba(243,166,75,.22),rgba(224,113,47,.06) 35%,rgba(31,40,54,0) 70%)}
.card-photo img{width:100%;height:100%;object-fit:cover;transition:transform 1.2s var(--ease-out);font-size:0;color:transparent}
.card:hover .card-photo img{transform:scale(1.06)}
.card-photo .placeholder{position:absolute;inset:0;display:grid;place-items:center;color:rgba(243,238,227,.45)}
.card-photo .placeholder svg{width:48px;height:48px;opacity:.55}
.card-tag{position:absolute;top:13px;right:13px;padding:.3rem .7rem;border-radius:999px;font:700 .66rem var(--sans);
  letter-spacing:.06em;text-transform:uppercase;z-index:2;backdrop-filter:blur(8px);background:var(--accent);color:#fff}
.card-tag.is-payant{background:var(--accent);color:#fff}
.card-tag.is-gratuit{background:#2e4a3a;color:#fff}
.card-body{padding:1.2rem 1.3rem 1.3rem;display:flex;flex-direction:column;gap:.4rem;flex:1}
.card-commune{font-size:.76rem;letter-spacing:.04em;color:var(--card-ink3);display:flex;align-items:center;gap:.3rem}
.card-commune svg{width:11px;height:11px;flex-shrink:0;opacity:.7}
.card-body a.title{font-family:var(--serif);font-weight:500;font-size:1.32rem;color:var(--card-ink);line-height:1.15;letter-spacing:-.01em;transition:color .2s}
.card-body a.title:hover{color:var(--accent)}
.card-desc{font:400 .86rem/1.5 var(--sans);color:var(--card-ink2);margin:.1rem 0 .8rem;
  display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.card-actions{display:flex;gap:1.1rem;margin-top:auto;padding-top:.8rem;border-top:1px dashed var(--card-line);font-size:.76rem;color:var(--card-ink3);flex-wrap:wrap}
.card-actions a{font-weight:500;color:var(--card-ink2);transition:color .2s,transform .3s var(--ease-out);display:inline-flex;align-items:center;gap:.3rem}
.card-actions a:hover{color:var(--accent);transform:translateX(2px)}
.card-actions a svg{width:13px;height:13px}

.card-meta{display:flex;align-items:center;gap:.5rem;flex-wrap:wrap;margin-bottom:.1rem}
.badge{font:600 .62rem var(--sans);letter-spacing:.04em;padding:.2rem .5rem;border-radius:999px;line-height:1}
.badge.dist{background:color-mix(in srgb,var(--accent) 16%,transparent);color:var(--accent)}
.badge.zone{background:color-mix(in srgb,var(--card-ink) 8%,transparent);color:var(--card-ink3)}
.badge.open{background:#2e4a3a;color:#fff}
.badge.closed{background:color-mix(in srgb,var(--card-ink) 12%,transparent);color:var(--card-ink3)}
.card.is-closed{opacity:.62}
.card.is-closed:hover{opacity:.85}

footer.site{background:color-mix(in srgb,var(--paper) 92%,#000 8%);border-top:1px solid var(--line);
  padding:clamp(3rem,6vw,4.5rem) 0 2.25rem;color:var(--ink-2);font-size:.9rem;margin-top:3rem;position:relative;z-index:2;transition:var(--turn)}
.foot-grid{display:grid;grid-template-columns:1fr;gap:2.5rem;margin-bottom:2.5rem}
@media(min-width:720px){.foot-grid{grid-template-columns:2fr 1fr 1fr 1fr}}
.foot-col h3{font:600 .7rem var(--sans);color:var(--ink);text-transform:uppercase;letter-spacing:.18em;margin-bottom:1rem;transition:var(--turn)}
.foot-col ul{display:flex;flex-direction:column;gap:.55rem}
.foot-col ul a{font-family:var(--serif);font-style:italic;font-size:1rem;color:var(--ink-2);transition:var(--turn)}
.foot-col ul a:hover{color:var(--accent)}
.foot-col p{font-family:var(--serif);font-style:italic;font-size:1.04rem;color:var(--ink-3);max-width:24rem;line-height:1.55;transition:var(--turn)}
.foot-bottom{display:flex;flex-wrap:wrap;justify-content:space-between;gap:1rem;padding-top:2rem;border-top:1px solid var(--line);color:var(--ink-3);font-size:.75rem;letter-spacing:.06em;transition:var(--turn)}

@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}.clouds svg,.rainveil,.lamp{animation:none}*{transition-duration:.001ms!important}}
</style>"""

SCENE_HTML = """<div class="sky" aria-hidden="true"></div>
<div class="orb" id="orb" aria-hidden="true"></div>
<div class="clouds" id="clouds" aria-hidden="true">
  <svg viewBox="0 0 1440 400" preserveAspectRatio="none"><g fill="#cdd5e0" opacity=".55">
    <ellipse cx="220" cy="120" rx="180" ry="48"/><ellipse cx="360" cy="150" rx="140" ry="40"/>
    <ellipse cx="720" cy="100" rx="220" ry="54"/><ellipse cx="900" cy="140" rx="150" ry="42"/>
    <ellipse cx="1180" cy="120" rx="200" ry="50"/><ellipse cx="1340" cy="160" rx="150" ry="40"/>
  </g></svg>
</div>
<div class="rainveil" id="rainveil" aria-hidden="true"></div>
<div class="lamp" id="lamp" aria-hidden="true"></div>"""


def render_header(loc: dict, s: dict, lang_picker_html: str, home_url: str) -> str:
    return f'''<header class="site" id="siteHeader">
  <a href="{home_url}" class="brand">
    <span class="mark" aria-hidden="true">
      <svg viewBox="0 0 34 34" fill="none"><path d="M3 28 L11 12 L16 20 L22 6 L31 28 Z" fill="currentColor"/>
      <polygon points="22,6 25,11 19,11" fill="#fdfaf3"/><circle cx="28" cy="10" r="2.5" fill="#e07a3f"/></svg>
    </span>
    <span><b>loisirs74</b> <i id="brandTag">{s["brand_tag_clear"]}</i></span>
  </a>
  <div class="nav-right">
    <button class="near-me" id="nearMe">{s["btn_near"]}</button>
    <div class="weather-toggle" role="group" aria-label="weather">
      <button id="bAuto" class="on">{s["btn_auto"]}</button>
      <button id="bSun">{s["btn_sun"]}</button>
      <button id="bRain">{s["btn_rain"]}</button>
    </div>
    {lang_picker_html}
  </div>
</header>'''


def render_hero(s: dict) -> str:
    return f'''<section class="hero">
  <div class="wrap hero-content">
    <div class="kicker" id="kicker">{s["kicker"]}</div>
    <h1>{s["h1_top"]}<br><em>{s["h1_em"]}</em></h1>
    <p class="lede">{s["lede_html"]}</p>
    <div class="weather-now" id="weatherNow">
      <span class="dot"></span><b id="wnLabel">{s["wn_label_clear"]}</b>
      <span id="wnText">{s["wn_text_clear"]}</span>
    </div>
  </div>
</section>'''


def render_section(sid: str, h2_html: str, see_all_href: str, see_all_label: str,
                   band_text: str, cards: list[str]) -> str:
    cards_html = "\n      ".join(cards)
    return f'''<section class="cat" id="{sid}">
  <div class="wrap">
    <div class="cat-head">
      <div class="cat-head-left">
        <span class="weather-band">{band_text}</span>
        <h2>{h2_html}</h2>
      </div>
      <a href="{see_all_href}" class="see-all">{see_all_label}
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
      </a>
    </div>
    <div class="carousel">
      {cards_html}
    </div>
  </div>
</section>'''


def render_crossover(s: dict) -> str:
    return f'''<div class="crossover" id="crossover">
  <div class="wrap">
    <p id="crossText">{s["cross_text"]}</p>
    <small id="crossSmall">{s["cross_small"]}</small>
  </div>
</div>'''


def render_footer(loc: dict, s: dict, footer_cats_ul: str | None, brand_blurb_p: str, lang_links: list[tuple[str, str, str]]) -> str:
    cats = footer_cats_ul or "<ul></ul>"
    lang_lis = "\n          ".join(
        f'<li><a href="{url}" hreflang="{code}">{label}</a></li>'
        for url, code, label in lang_links
    )
    return f'''<footer class="site">
  <div class="wrap">
    <div class="foot-grid">
      <div class="foot-col">
        <h3>Loisirs 74</h3>
        {brand_blurb_p}
      </div>
      <div class="foot-col">
        <h3>{s["foot_cats_h4"]}</h3>
        {cats}
      </div>
      <div class="foot-col">
        <h3>{s["foot_lang_h4"]}</h3>
        <ul>
          {lang_lis}
        </ul>
      </div>
      <div class="foot-col">
        <h3>{s["foot_mentions_h4"]}</h3>
        <ul>
          {s["foot_mentions_lis"]}
        </ul>
      </div>
    </div>
    <div class="foot-bottom">
      <span>© 2026 bleu canard éditions · Edmaster &amp; Claudius</span>
      <span id="footState">{s["footstate_clear"]}</span>
    </div>
  </div>
</footer>'''


def render_data_block(slugs_present: set[str]) -> str:
    data = {}
    for slug in sorted(slugs_present):
        l = BY_SLUG.get(slug)
        if not l:
            continue
        entry = {
            "categories": l.get("categories") or [],
        }
        if l.get("latitude") is not None:
            entry["lat"] = l["latitude"]
        if l.get("longitude") is not None:
            entry["lng"] = l["longitude"]
        # subcategories may be on the per-fiche JSON
        fiche_path = REPO / "Json" / f"{slug}.json"
        if fiche_path.exists():
            try:
                fiche = json.loads(fiche_path.read_text(encoding="utf-8"))
                if fiche.get("subcategories"):
                    entry["subcategories"] = fiche["subcategories"]
            except Exception:
                pass
        data[slug] = entry
    return f'<script type="application/json" id="l74-data">{json.dumps(data, ensure_ascii=False)}</script>'


SCENE_JS = r"""<script>
var root=document.documentElement;
var mode='auto';
var DAY={'--sky-1':'var(--day-sky-1)','--sky-2':'var(--day-sky-2)','--paper':'var(--day-paper)','--ink':'var(--day-ink)','--ink-2':'var(--day-ink-2)','--ink-3':'var(--day-ink-3)','--line':'var(--day-line)','--card':'var(--day-card)','--card-ink':'var(--day-card-ink)','--card-ink2':'var(--day-card-ink2)','--card-ink3':'var(--day-card-ink3)','--card-line':'var(--day-card-line)','--accent':'var(--day-accent)','--accent-soft':'var(--day-accent-soft)'};
var RAIN={'--sky-1':'var(--rain-sky-1)','--sky-2':'var(--rain-sky-2)','--paper':'var(--rain-paper)','--ink':'var(--rain-ink)','--ink-2':'var(--rain-ink-2)','--ink-3':'var(--rain-ink-3)','--line':'var(--rain-line)','--card':'var(--rain-card)','--card-ink':'var(--rain-card-ink)','--card-ink2':'var(--rain-card-ink2)','--card-ink3':'var(--rain-card-ink3)','--card-line':'var(--rain-card-line)','--accent':'var(--rain-accent)','--accent-soft':'var(--rain-accent-soft)'};
function applyPalette(isRain){var p=isRain?RAIN:DAY;for(var k in p)root.style.setProperty(k,p[k]);}
var orb=document.getElementById('orb');
var STR=__STR_JSON__;
function setScene(w){
  applyPalette(w>=.5);
  if(w<.5){orb.style.background='radial-gradient(circle,rgba(244,184,138,.55) 0%,rgba(244,184,138,.18) 32%,rgba(244,184,138,0) 66%)';orb.style.transform='translate(0,0) scale(1)';orb.style.opacity=(1-w*1.8);}
  else{orb.style.background='radial-gradient(circle,rgba(207,219,235,.5) 0%,rgba(207,219,235,.15) 34%,rgba(207,219,235,0) 66%)';orb.style.transform='translate(-30px,30px) scale(.85)';orb.style.opacity=((w-.5)*1.8);}
  document.getElementById('clouds').style.opacity=Math.max(0,(w-.2)*1.6);
  document.getElementById('rainveil').style.opacity=Math.max(0,(w-.55)*2);
  document.getElementById('lamp').style.opacity=Math.max(0,(w-.6)*2.2);
  var wn=document.getElementById('wnLabel'),wt=document.getElementById('wnText'),fs=document.getElementById('footState'),bt=document.getElementById('brandTag'),cx=document.getElementById('crossText'),cs=document.getElementById('crossSmall');
  if(w<.35){wn.textContent=STR.wn_label_clear;wt.textContent=STR.wn_text_clear;fs.textContent=STR.footstate_clear;bt.textContent=STR.brand_tag_clear;}
  else if(w<.6){wn.textContent=STR.wn_label_var;wt.textContent=STR.wn_text_var;fs.textContent=STR.footstate_var;bt.textContent=STR.brand_tag_var;}
  else{wn.textContent=STR.wn_label_rain;wt.textContent=STR.wn_text_rain;fs.textContent=STR.footstate_rain;bt.textContent=STR.brand_tag_rain;}
}
var crossEl=document.getElementById('crossover');
function autoFromScroll(){
  if(mode!=='auto'||!crossEl)return;
  var rect=crossEl.getBoundingClientRect();
  var center=innerHeight*.5;
  var crossMid=rect.top+rect.height/2;
  var t=(center-crossMid)/(innerHeight*1.2);
  var w=Math.min(1,Math.max(0,.5+t));
  setScene(w);
}
var navEl=document.getElementById('siteHeader');
addEventListener('scroll',function(){navEl.classList.toggle('scrolled',scrollY>20);autoFromScroll();},{passive:true});
var bAuto=document.getElementById('bAuto'),bSun=document.getElementById('bSun'),bRain=document.getElementById('bRain');
function setBtn(on){[bAuto,bSun,bRain].forEach(function(b){b.classList.remove('on')});on.classList.add('on');}
bAuto.onclick=function(){mode='auto';setBtn(bAuto);autoFromScroll();};
bSun.onclick=function(){mode='sun';setBtn(bSun);setScene(0);};
bRain.onclick=function(){mode='rain';setBtn(bRain);setScene(1);};
(function(){var els=document.querySelectorAll('section.cat .card');
  els.forEach(function(e){e.style.opacity=0;e.style.transform='translateY(24px)';e.style.transition='opacity .8s var(--ease-out),transform .8s var(--ease-out)'});
  var io=new IntersectionObserver(function(en){en.forEach(function(e){if(e.isIntersecting){e.target.style.opacity=1;e.target.style.transform='none';io.unobserve(e.target)}})},{threshold:.08,rootMargin:'0px 0px -6% 0px'});
  els.forEach(function(e){io.observe(e)});})();

/* slug -> meta lookup from inline JSON */
var DATA={};
try{DATA=JSON.parse(document.getElementById('l74-data').textContent)||{};}catch(e){}
function slugFromCard(card){
  var a=card.querySelector('a.card-photo')||card.querySelector('a.title');
  if(!a)return null;var m=a.getAttribute('href').match(/loisirs74\.fr\/(?:[a-z]{2}\/)?([a-z0-9-]+)\/?$/);
  return m?m[1]:null;
}
function renderBadges(){
  var now=new Date();
  document.querySelectorAll('section.cat .card').forEach(function(card){
    var slug=slugFromCard(card);if(!slug)return;var f=DATA[slug];if(!f)return;
    var commune=card.querySelector('.card-commune');
    var old=card.querySelector('.card-meta');if(old)old.remove();
    card.classList.remove('is-closed');
    var meta=document.createElement('div');meta.className='card-meta';
    if(origin&&f.lat!=null){var d=L74.distKm(origin.lat,origin.lng,f.lat,f.lng);
      meta.insertAdjacentHTML('beforeend','<span class="badge dist">'+STR.km_label.replace('{n}',d)+'</span>');}
    var z=(f.lat!=null)?L74.zoneOf(f.lat,f.lng):null;
    if(z)meta.insertAdjacentHTML('beforeend','<span class="badge zone">'+z.nom+'</span>');
    var st=L74.statutHoraire(f,now);
    if(st){meta.insertAdjacentHTML('beforeend','<span class="badge '+(st.ouvert?'open':'closed')+'">'+(st.ouvert?STR.open_prefix:'')+st.texte+'</span>');
      if(!st.ouvert)card.classList.add('is-closed');}
    if(commune)commune.parentNode.insertBefore(meta,commune);
  });
}
var origin=null;
function applyProximity(){
  if(!origin)return;
  document.querySelectorAll('.carousel').forEach(function(car){
    var cards=[].slice.call(car.querySelectorAll('.card'));
    cards.sort(function(a,b){
      var sa=slugFromCard(a),sb=slugFromCard(b);
      var fa=sa&&DATA[sa],fb=sb&&DATA[sb];
      if(!fa||!fb||fa.lat==null||fb.lat==null)return 0;
      return L74.distKm(origin.lat,origin.lng,fa.lat,fa.lng)-L74.distKm(origin.lat,origin.lng,fb.lat,fb.lng);
    });
    cards.forEach(function(c){car.appendChild(c);});
  });
}
var nearBtn=document.getElementById('nearMe');
nearBtn.onclick=function(){
  if(origin){origin=null;nearBtn.classList.remove('on');nearBtn.textContent=STR.btn_near;renderBadges();return;}
  nearBtn.textContent=STR.btn_near_loading;
  if(!navigator.geolocation){nearBtn.textContent=STR.btn_near_off;return;}
  navigator.geolocation.getCurrentPosition(function(pos){
    origin={lat:pos.coords.latitude,lng:pos.coords.longitude};
    nearBtn.classList.add('on');nearBtn.textContent=STR.btn_near_on;
    applyProximity();renderBadges();
  },function(){
    origin={lat:45.90,lng:6.13};
    nearBtn.classList.add('on');nearBtn.textContent=STR.btn_near_demo;
    applyProximity();renderBadges();
  },{timeout:6000});
};
renderBadges();
setScene(0);
</script>"""


# --- per-locale extra strings, language picker, footer ----------------------

EXTRA_STRINGS = {
    "fr": {
        "foot_cats_h4": "Catégories",
        "foot_lang_h4": "Langue",
        "foot_mentions_h4": "Mentions",
        "foot_mentions_lis": '<li><a href="https://loisirs74.fr/mentions-legales">Mentions légales</a></li>\n          <li><a href="https://loisirs74.fr/confidentialite">Confidentialité</a></li>\n          <li><a href="https://loisirs74.fr/cgv">CGV</a></li>\n          <li><a href="https://loisirs74.fr/signaler">Signaler une info</a></li>\n          <li><a href="https://loisirs74.fr/devenir-partenaire">Devenir partenaire</a></li>',
        "brand_blurb_p": '<p>Guide indépendant des lieux de loisirs en Haute-Savoie. Chaque page : une source officielle, une adresse, une carte.</p>',
        "km_label": "à {n} km",
        "open_prefix": "ouvert · ",
    },
    "en": {
        "foot_cats_h4": "Categories",
        "foot_lang_h4": "Language",
        "foot_mentions_h4": "Legal",
        "foot_mentions_lis": '<li><a href="https://loisirs74.fr/en/legal">Legal notice</a></li>\n          <li><a href="https://loisirs74.fr/en/privacy">Privacy</a></li>\n          <li><a href="https://loisirs74.fr/en/terms">Terms</a></li>\n          <li><a href="https://loisirs74.fr/en/report">Report info</a></li>\n          <li><a href="https://loisirs74.fr/en/partner">Become a partner</a></li>',
        "brand_blurb_p": '<p>Independent guide to public leisure sites in Haute-Savoie. Every page: one official source, an address, a map.</p>',
        "km_label": "{n} km away",
        "open_prefix": "open · ",
    },
    "de": {
        "foot_cats_h4": "Kategorien",
        "foot_lang_h4": "Sprache",
        "foot_mentions_h4": "Impressum",
        "foot_mentions_lis": '<li><a href="https://loisirs74.fr/de/impressum">Impressum</a></li>\n          <li><a href="https://loisirs74.fr/de/datenschutz">Datenschutz</a></li>\n          <li><a href="https://loisirs74.fr/de/agb">AGB</a></li>\n          <li><a href="https://loisirs74.fr/de/melden">Info melden</a></li>\n          <li><a href="https://loisirs74.fr/de/partner">Partner werden</a></li>',
        "brand_blurb_p": '<p>Unabhängiger Freizeitführer für die Haute-Savoie. Jede Seite: eine offizielle Quelle, eine Adresse, eine Karte.</p>',
        "km_label": "{n} km entfernt",
        "open_prefix": "geöffnet · ",
    },
    "it": {
        "foot_cats_h4": "Categorie",
        "foot_lang_h4": "Lingua",
        "foot_mentions_h4": "Note legali",
        "foot_mentions_lis": '<li><a href="https://loisirs74.fr/it/note-legali">Note legali</a></li>\n          <li><a href="https://loisirs74.fr/it/privacy">Privacy</a></li>\n          <li><a href="https://loisirs74.fr/it/condizioni">Condizioni</a></li>\n          <li><a href="https://loisirs74.fr/it/segnalare">Segnalare</a></li>\n          <li><a href="https://loisirs74.fr/it/partner">Diventare partner</a></li>',
        "brand_blurb_p": '<p>Guida indipendente ai luoghi di svago dell’Alta Savoia. Ogni pagina: una fonte ufficiale, un indirizzo, una mappa.</p>',
        "km_label": "a {n} km",
        "open_prefix": "aperto · ",
    },
    "es": {
        "foot_cats_h4": "Categorías",
        "foot_lang_h4": "Idioma",
        "foot_mentions_h4": "Aviso legal",
        "foot_mentions_lis": '<li><a href="https://loisirs74.fr/es/aviso-legal">Aviso legal</a></li>\n          <li><a href="https://loisirs74.fr/es/privacidad">Privacidad</a></li>\n          <li><a href="https://loisirs74.fr/es/condiciones">Condiciones</a></li>\n          <li><a href="https://loisirs74.fr/es/notificar">Notificar</a></li>\n          <li><a href="https://loisirs74.fr/es/socio">Hacerse socio</a></li>',
        "brand_blurb_p": '<p>Guía independiente de los lugares de ocio de la Alta Saboya. Cada página: una fuente oficial, una dirección, un mapa.</p>',
        "km_label": "a {n} km",
        "open_prefix": "abierto · ",
    },
}

LANG_LINKS = [
    ("https://loisirs74.fr/",    "fr", "Français"),
    ("https://loisirs74.fr/en/", "en", "English"),
    ("https://loisirs74.fr/de/", "de", "Deutsch"),
    ("https://loisirs74.fr/it/", "it", "Italiano"),
    ("https://loisirs74.fr/es/", "es", "Español"),
]


def render_lang_picker(loc_code: str) -> str:
    items = []
    summary_label = {"fr": "FR", "en": "EN", "de": "DE", "it": "IT", "es": "ES"}[loc_code]
    for url, code, label in LANG_LINKS:
        attrs = f'href="{url}" hreflang="{code}"'
        if code == loc_code:
            attrs += ' aria-current="true"'
        items.append(f'<a {attrs}>{label}</a>')
    items_html = "".join(items)
    return f'''<details class="lang-picker">
      <summary><b>{summary_label}</b></summary>
      <div class="lang-menu">{items_html}</div>
    </details>'''


# --- the build itself --------------------------------------------------------

def build(loc: dict) -> None:
    # DEPRECATED / UNSAFE (2026-06): this is a legacy builder for the old
    # raw-category homepage. The live FR homepage has migrated to a thematic-
    # hub layout this script does NOT reproduce (running it restructures the
    # page and drops sections); the locale homepages it can still match would
    # be silently rewritten too. It is NOT in the deploy chain — the homepages
    # are hub-patched/hand-maintained. Refuse to write unless explicitly forced.
    if "--force" not in sys.argv:
        print(f"  SKIP {loc.get('subdir') or 'fr'}/index.html — build_homepage is "
              f"deprecated/unsafe for the current homepage; pass --force to override.")
        return
    code = loc["code"]
    subdir = loc["subdir"]
    s = {**STRINGS[code], **EXTRA_STRINGS[code]}
    home_path = REPO / (subdir or "") / "index.html"
    html = home_path.read_text(encoding="utf-8")

    # head with the inline <style> stripped
    head_no_style = extract_head_with_replacements(html)

    # preserve body-side JSON-LD (SEO surface must not drift)
    body_ld_blocks = extract_body_ld_blocks(html)

    # extract sections
    sections = {m.group("id"): m.group("body") for m in SECTION_RE.finditer(html)}

    home_url = f"https://loisirs74.fr/{(subdir + '/') if subdir else ''}"
    lang_picker_html = render_lang_picker(code)

    # Phase A routing: extract every card from every source section, then
    # bucket each card by its lieux.json category (with HOMEPAGE_SECTION_OVERRIDE
    # for jardins). This replaces the prior "card lives in whatever section it
    # was extracted from" rule, which inherited the lieux.json miscategorisation
    # that put outdoor venues under the indoor #attraction band.

    # cards_by_section[sid] -> list of card HTML, preserving source-section
    # order then per-slug source order within each bucket.
    cards_by_section: dict[str, list[str]] = {}
    slugs_present: set[str] = set()
    placed: set[str] = set()
    # per-source section header pieces: we still want the existing localized
    # h2 text and see-all link for each section, so capture them up front.
    section_chrome: dict[str, dict[str, str]] = {}
    for sid, body in sections.items():
        section_chrome[sid] = {
            "h2": extract_h2_text(body) or sid,
            "see_href": extract_see_all(body, s["see_all_fallback"])[0],
            "see_label": extract_see_all(body, s["see_all_fallback"])[1],
        }
        for card in extract_cards(body):
            slug_match = CARD_SLUG_RE.search(card)
            if not slug_match:
                continue
            slug = slug_match.group(1) or slug_match.group(2)
            if slug in placed:
                continue  # dedupe — a slug routes to exactly one section
            target = section_for_slug(slug) or sid
            cards_by_section.setdefault(target, []).append(card)
            placed.add(slug)
            slugs_present.add(slug)

    def render_for(sid: str, band_text: str) -> str | None:
        cards = cards_by_section.get(sid)
        if not cards:
            return None
        chrome = section_chrome.get(sid)
        if not chrome:
            # the section header didn't exist in source (rare); fall back to
            # the first source section's chrome to keep the See-all link sensible
            chrome = next(iter(section_chrome.values()), {"h2": sid, "see_href": "#", "see_label": s["see_all_fallback"]})
        return render_section(sid, chrome["h2"], chrome["see_href"], chrome["see_label"], band_text, cards)

    built_outdoor: list[str] = []
    for sid in OUTDOOR_SECTIONS + MIX_SECTIONS:
        band = s["wband_out"] if sid in OUTDOOR_SECTIONS else s["wband_mix"]
        rendered = render_for(sid, band)
        if rendered:
            built_outdoor.append(rendered)

    # top up #attraction from the locale hub so the indoor section doesn't look
    # anaemic (Phase B moved 4-5 outdoor cards out of the pre-rewrite teaser).
    attraction_cards = cards_by_section.get("attraction", [])
    if len(attraction_cards) < 6:
        topup = topup_attraction_cards(code, set(slugs_present), desired=6 - len(attraction_cards))
        for card in topup:
            attraction_cards.append(card)
            m = CARD_SLUG_RE.search(card)
            if m:
                slugs_present.add(m.group(1) or m.group(2))
        cards_by_section["attraction"] = attraction_cards

    built_indoor: list[str] = []
    for sid in INDOOR_SECTIONS:
        rendered = render_for(sid, s["wband_in"])
        if rendered:
            built_indoor.append(rendered)

    crossover_html = render_crossover(s)
    sections_html = "\n\n".join(built_outdoor) + "\n\n" + crossover_html + "\n\n" + "\n\n".join(built_indoor)

    footer_cats = extract_footer_categories(html)
    data_block = render_data_block(slugs_present)

    # assemble body
    body = f"""{SCENE_HTML}

{render_header(loc, s, lang_picker_html, home_url)}

<main>
{render_hero(s)}

{sections_html}
</main>

{render_footer(loc, s, footer_cats, s["brand_blurb_p"], LANG_LINKS)}

{chr(10).join(body_ld_blocks)}

{data_block}
<script src="/scripts/l74sort.js"></script>
{SCENE_JS.replace("__STR_JSON__", json.dumps(s, ensure_ascii=False))}"""

    # inject the prototype <style> just before </head>
    head_with_style = head_no_style.replace("</head>", f"{PROTOTYPE_STYLE}\n</head>", 1)

    full = f"""<!doctype html>
<html lang="{loc['lang']}">
{head_with_style}
<body>
{body}
</body>
</html>
"""

    home_path.write_text(full, encoding="utf-8")
    print(f"wrote {home_path} ({len(full)} bytes, {len(slugs_present)} unique slugs)")


def main() -> None:
    for loc in LOCALES:
        build(loc)


if __name__ == "__main__":
    main()
