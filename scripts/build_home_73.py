#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_home_73.py — the Savoie homepage, in the sister site's shape.

Reproduces loisirs74.fr's homepage — savoitised — from the fiche layer:
  * a fixed top bar (brand · Savoie, "Près de moi", language picker);
  * a full-bleed animated skyline hero (CSS/SVG, no JS needed) with a
    two-tone serif headline;
  * a "Par catégorie" directory grouping every family of places;
  * thematic BANDS, each introducing a run of category carousels;
  * rich cards (photo, free/paid badge, commune, serif title, a two-line
    description, quick actions) in the engine's shared card shape.

The design (CSS) is the sister site's own, read verbatim from
data/home-73.css. Everything else is generated: bands from the roster,
cards from the fiches — the homepage cannot drift from the catalogue. The
markup uses the engine's class names, so the shared post-processors
(sync_home_cards, patch_homepage_duck/nearme, the facet-hub inject and the
head normaliser's canonical/hreflang pass) all still fire.
"""
import json, glob, os, sys, html
from urllib.parse import quote
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import siteconfig as S
import build_lieu_page as _BLP  # canonical hub slug table — single source

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("fr", "en", "de", "it", "es", "nl")
E = lambda s: html.escape(str(s or ""), quote=True)
_SIS = getattr(S, "SISTER", None) or {"name": S.SITE_NAME, "url": S.BASE_URL, "dept": S.DEPT_NAME}
CSS = open(os.path.join(ROOT, "data", "home-73.css"), encoding="utf-8").read()
# Branded sister panel — themed with the sister site's own tokens (day/dark aware).
SIS_CSS = (
    ".sister-band{margin:3.4rem auto 0;max-width:var(--max);padding:0 var(--pad)}"
    ".sister-card{display:flex;gap:1.4rem;align-items:center;flex-wrap:wrap;background:var(--card);"
    "border:1px solid var(--card-line);border-radius:18px;padding:1.6rem 1.8rem;transition:var(--turn)}"
    ".sister-card img{width:78px;height:78px;border-radius:16px;flex:0 0 auto;box-shadow:0 3px 14px rgba(0,0,0,.12)}"
    ".sister-card .st{flex:1 1 18rem;min-width:0}"
    ".sister-card .k{display:block;font:600 .72rem var(--sans);letter-spacing:.13em;text-transform:uppercase;"
    "color:var(--card-ink3);margin-bottom:.25rem}"
    ".sister-card .n{display:block;font-family:var(--serif);font-size:1.45rem;font-weight:500;"
    "color:var(--card-ink);letter-spacing:-.01em;line-height:1.1}"
    ".sister-card p{margin:.5rem 0 0;color:var(--card-ink2);font-size:.96rem;line-height:1.5}"
    ".sister-card .go{flex:0 0 auto;display:inline-flex;align-items:center;gap:.5rem;padding:.75rem 1.35rem;"
    "border-radius:999px;background:var(--accent);color:#fff;font-weight:600;font-family:var(--sans);transition:var(--turn)}"
    ".sister-card .go:hover{gap:.8rem;filter:brightness(1.05)}"
    "@media(max-width:560px){.sister-card{flex-direction:column;align-items:flex-start}.sister-card .go{align-self:stretch;justify-content:center}}"
    # header logo: use the real 73 mark (navy · blue peaks · Savoie red cross), a touch larger
    ".brand .mark{width:40px;height:40px}.brand .mark img{width:40px;height:40px;border-radius:9px;display:block}")

# --- hubs: category set + localized "&"-style label per hub ------------------
HUBS = {
    "lacs-plages":   {"cats": ("lac", "plage"),
                      "label": {"fr": "Lacs & plages", "en": "Lakes & beaches", "de": "Seen & Strände",
                                "it": "Laghi & spiagge", "es": "Lagos & playas", "nl": "Meren & stranden"}},
    "cascades":      {"cats": ("cascade",),
                      "label": {"fr": "Cascades & gorges", "en": "Waterfalls & gorges", "de": "Wasserfälle & Schluchten",
                                "it": "Cascate & gole", "es": "Cascadas & gargantas", "nl": "Watervallen & kloven"}},
    "points-de-vue": {"cats": ("point-de-vue",),
                      "label": {"fr": "Points de vue & cols", "en": "Viewpoints & passes", "de": "Aussichtspunkte & Pässe",
                                "it": "Punti panoramici & colli", "es": "Miradores & puertos", "nl": "Uitzichtpunten & passen"}},
    "sentiers":      {"cats": ("sentier",),
                      "label": {"fr": "Sentiers & randonnées", "en": "Trails & hikes", "de": "Wege & Wanderungen",
                                "it": "Sentieri & escursioni", "es": "Senderos & rutas", "nl": "Paden & tochten"}},
    "voies-vertes":  {"cats": ("voie-verte",),
                      "label": {"fr": "Voies vertes", "en": "Greenways", "de": "Radwege",
                                "it": "Vie verdi", "es": "Vías verdes", "nl": "Fietsroutes"}},
    "telecabines":   {"cats": ("telecabine",),
                      "label": {"fr": "Télécabines & trains", "en": "Cable cars & trains", "de": "Bergbahnen & Züge",
                                "it": "Cabinovie & treni", "es": "Telecabinas & trenes", "nl": "Kabelbanen & treinen"}},
    "chateaux":      {"cats": ("chateau",),
                      "label": {"fr": "Châteaux & forts", "en": "Castles & forts", "de": "Schlösser & Festungen",
                                "it": "Castelli & forti", "es": "Castillos & fuertes", "nl": "Kastelen & forten"}},
    "musees":        {"cats": ("musee",),
                      "label": {"fr": "Musées", "en": "Museums", "de": "Museen",
                                "it": "Musei", "es": "Museos", "nl": "Musea"}},
}

# --- glance directory: thematic groups of hub tiles --------------------------
GROUPS = [
    ({"fr": "Nature & grand air", "en": "Nature & the outdoors", "de": "Natur & frische Luft",
      "it": "Natura & aria aperta", "es": "Naturaleza & aire libre", "nl": "Natuur & buitenlucht"},
     ["lacs-plages", "cascades", "points-de-vue", "sentiers", "telecabines", "voies-vertes"]),
    ({"fr": "Patrimoine & culture", "en": "Heritage & culture", "de": "Erbe & Kultur",
      "it": "Patrimonio & cultura", "es": "Patrimonio & cultura", "nl": "Erfgoed & cultuur"},
     ["chateaux", "musees"]),
]

# --- bands: each introduces a run of category carousels ----------------------
BANDS = [
    ({"fr": "Nature & grand air", "en": "Nature & the outdoors", "de": "Natur & frische Luft",
      "it": "Natura & aria aperta", "es": "Naturaleza & aire libre", "nl": "Natuur & buitenlucht"},
     {"fr": "Lacs, plages, cascades, panoramas et sentiers — la Savoie à ciel ouvert.",
      "en": "Lakes, beaches, waterfalls, panoramas and trails — Savoie in the open air.",
      "de": "Seen, Strände, Wasserfälle, Panoramen und Wege — die Savoie unter freiem Himmel.",
      "it": "Laghi, spiagge, cascate, panorami e sentieri — la Savoie a cielo aperto.",
      "es": "Lagos, playas, cascadas, panoramas y senderos — la Savoie a cielo abierto.",
      "nl": "Meren, stranden, watervallen, panorama's en paden — de Savoie in de open lucht."},
     ["lacs-plages", "cascades", "points-de-vue", "sentiers", "telecabines", "voies-vertes"]),
    ({"fr": "Patrimoine & culture", "en": "Heritage & culture", "de": "Erbe & Kultur",
      "it": "Patrimonio & cultura", "es": "Patrimonio & cultura", "nl": "Erfgoed & cultuur"},
     {"fr": "Châteaux des ducs, forts de l'Esseillon, musées de la Savoie et de son histoire.",
      "en": "The dukes' castles, the Esseillon forts, the museums of Savoie and its history.",
      "de": "Herzogsschlösser, die Festungen des Esseillon, die Museen der Savoie und ihrer Geschichte.",
      "it": "I castelli dei duchi, i forti dell'Esseillon, i musei della Savoie e della sua storia.",
      "es": "Los castillos de los duques, los fuertes del Esseillon, los museos de la Savoie y su historia.",
      "nl": "De hertogenkastelen, de forten van de Esseillon, de musea van de Savoie en haar geschiedenis."},
     ["chateaux", "musees"]),
]

UI = {
 "brand_tag": {"fr": "· Savoie", "en": "· Savoie", "de": "· Savoie", "it": "· Savoie", "es": "· Savoie", "nl": "· Savoie"},
 "near": {"fr": "◎ Près de moi", "en": "◎ Near me", "de": "◎ In meiner Nähe", "it": "◎ Vicino a me",
          "es": "◎ Cerca de mí", "nl": "◎ Bij mij in de buurt"},
 "kicker": {"fr": "Le guide indépendant · %d lieux vérifiés", "en": "The independent guide · %d verified places",
            "de": "Der unabhängige Guide · %d geprüfte Orte", "it": "La guida indipendente · %d luoghi verificati",
            "es": "La guía independiente · %d lugares verificados", "nl": "De onafhankelijke gids · %d geverifieerde plekken"},
 "h1_pre": {"fr": "Où aller et quoi faire en", "en": "Where to go and what to do in",
            "de": "Wohin und was unternehmen in", "it": "Dove andare e cosa fare in",
            "es": "Adónde ir y qué hacer en", "nl": "Waar naartoe en wat te doen in"},
 "dept": {"fr": "Savoie", "en": "Savoie", "de": "Savoie", "it": "Savoie", "es": "Savoie", "nl": "Savoie"},
 "lede": {"fr": "Lacs, cascades, châteaux, musées, points de vue. <b>Tout le département, vérifié un par un</b> — "
                "et quand les sources se contredisent, la fiche le dit au lieu de choisir.",
          "en": "Lakes, waterfalls, castles, museums, viewpoints. <b>The whole department, checked one by one</b> — "
                "and where sources disagree, the page says so instead of picking one.",
          "de": "Seen, Wasserfälle, Schlösser, Museen, Aussichtspunkte. <b>Das ganze Département, Ort für Ort geprüft</b> — "
                "und wenn Quellen sich widersprechen, sagt die Seite es, statt zu wählen.",
          "it": "Laghi, cascate, castelli, musei, punti panoramici. <b>Tutto il dipartimento, verificato uno per uno</b> — "
                "e quando le fonti si contraddicono, la scheda lo dice invece di scegliere.",
          "es": "Lagos, cascadas, castillos, museos, miradores. <b>Todo el departamento, verificado uno por uno</b> — "
                "y cuando las fuentes se contradicen, la ficha lo dice en vez de elegir.",
          "nl": "Meren, watervallen, kastelen, musea, uitzichtpunten. <b>Het hele departement, stuk voor stuk getoetst</b> — "
                "en als bronnen elkaar tegenspreken, zegt de pagina dat in plaats van te kiezen."},
 "glance_h": {"fr": "Par catégorie", "en": "By category", "de": "Nach Kategorie",
              "it": "Per categoria", "es": "Por categoría", "nl": "Op categorie"},
 "glance_sub": {"fr": "Tout le site en un coup d'œil.", "en": "The whole site at a glance.",
                "de": "Die ganze Seite auf einen Blick.", "it": "Tutto il sito in un colpo d'occhio.",
                "es": "Todo el sitio de un vistazo.", "nl": "De hele site in één oogopslag."},
 "sel_h": {"fr": "Nos sélections", "en": "Our selections", "de": "Unsere Auswahl",
           "it": "Le nostre selezioni", "es": "Nuestras selecciones", "nl": "Onze selecties"},
 "sel_sub": {"fr": "Des réponses aux questions qu'on se pose vraiment.",
             "en": "Answers to the questions people actually ask.",
             "de": "Antworten auf die Fragen, die man sich wirklich stellt.",
             "it": "Risposte alle domande che ci si pone davvero.",
             "es": "Respuestas a las preguntas que uno se hace de verdad.",
             "nl": "Antwoorden op de vragen die je je echt stelt."},
 "count_tile": {"fr": "%d lieux", "en": "%d places", "de": "%d Orte", "it": "%d luoghi",
                "es": "%d lugares", "nl": "%d plekken"},
 "see_all": {"fr": "Voir tout", "en": "See all", "de": "Alle ansehen", "it": "Vedi tutto",
             "es": "Ver todo", "nl": "Alles bekijken"},
 "free": {"fr": "Gratuit", "en": "Free", "de": "Kostenlos", "it": "Gratuito", "es": "Gratis", "nl": "Gratis"},
 "paid": {"fr": "Payant", "en": "Paid", "de": "Kostenpflichtig", "it": "A pagamento", "es": "De pago", "nl": "Betaald"},
 "route": {"fr": "Itinéraire", "en": "Directions", "de": "Route", "it": "Itinerario", "es": "Cómo llegar", "nl": "Route"},
 "official": {"fr": "Site officiel", "en": "Official site", "de": "Offizielle Seite",
              "it": "Sito ufficiale", "es": "Sitio oficial", "nl": "Officiële site"},
 "foot_about": {"fr": "Guide indépendant des lieux de loisirs en Savoie. Chaque page : une source officielle, "
                      "une adresse, une carte — et les contradictions affichées plutôt qu'arbitrées.",
                "en": "Independent guide to leisure places in Savoie. Every page: an official source, an address, "
                      "a map — and contradictions shown rather than quietly resolved.",
                "de": "Unabhängiger Führer zu den Freizeitorten der Savoie. Jede Seite: eine offizielle Quelle, "
                      "eine Adresse, eine Karte — und Widersprüche gezeigt statt still aufgelöst.",
                "it": "Guida indipendente ai luoghi di svago della Savoie. Ogni pagina: una fonte ufficiale, "
                      "un indirizzo, una mappa — e le contraddizioni mostrate anziché risolte.",
                "es": "Guía independiente de los lugares de ocio de la Savoie. Cada página: una fuente oficial, "
                      "una dirección, un mapa — y las contradicciones mostradas en vez de resueltas.",
                "nl": "Onafhankelijke gids voor de vrijetijdsplekken van de Savoie. Elke pagina: een officiële bron, "
                      "een adres, een kaart — en tegenstrijdigheden getoond in plaats van opgelost."},
 "foot_cats": {"fr": "Catégories", "en": "Categories", "de": "Kategorien", "it": "Categorie",
               "es": "Categorías", "nl": "Categorieën"},
 "foot_lang": {"fr": "Langue", "en": "Language", "de": "Sprache", "it": "Lingua", "es": "Idioma", "nl": "Taal"},
 "foot_sister_k": {"fr": "L'autre département", "en": "The other department", "de": "Das andere Département",
                   "it": "L'altro dipartimento", "es": "El otro departamento", "nl": "Het andere departement"},
 "sis_kicker": {"fr": "L'autre département", "en": "The other department", "de": "Das andere Département",
                "it": "L'altro dipartimento", "es": "El otro departamento", "nl": "Het andere departement"},
 "sis_body": {"fr": "Même éditeur, même règle : chaque fait vérifié auprès d'une source officielle, "
                    "et les contradictions affichées plutôt qu'arbitrées. Passez la frontière départementale.",
              "en": "Same publisher, same rule: every fact checked against an official source, and contradictions "
                    "shown rather than quietly resolved. Cross the departmental border.",
              "de": "Gleicher Herausgeber, gleiche Regel: jede Angabe an einer offiziellen Quelle geprüft, "
                    "Widersprüche gezeigt statt still aufgelöst. Über die Départementsgrenze.",
              "it": "Stesso editore, stessa regola: ogni dato verificato su una fonte ufficiale, e le contraddizioni "
                    "mostrate anziché risolte in silenzio. Passate il confine dipartimentale.",
              "es": "Mismo editor, misma regla: cada dato verificado en una fuente oficial, y las contradicciones "
                    "mostradas en vez de resueltas en silencio. Cruce la frontera departamental.",
              "nl": "Zelfde uitgever, zelfde regel: elk feit getoetst aan een officiële bron, en tegenstrijdigheden "
                    "getoond in plaats van stilletjes opgelost. Steek de departementsgrens over."},
 "sis_go": {"fr": "Ouvrir loisirs74.fr", "en": "Open loisirs74.fr", "de": "loisirs74.fr öffnen",
            "it": "Apri loisirs74.fr", "es": "Abrir loisirs74.fr", "nl": "loisirs74.fr openen"},
 "prep": {"fr": "Site en préparation : rien n'est indexé pour l'instant.",
          "en": "Site in preparation: nothing is indexed yet.",
          "de": "Website in Vorbereitung: noch nichts indexiert.",
          "it": "Sito in preparazione: nulla è ancora indicizzato.",
          "es": "Sitio en preparación: nada está indexado todavía.",
          "nl": "Site in voorbereiding: nog niets geïndexeerd."},
}

_LANG_NAMES = {"fr": "Français", "en": "English", "de": "Deutsch", "it": "Italiano", "es": "Español", "nl": "Nederlands"}

# Brand mark + see-all arrow, lifted from the sister site's markup.
_MARK = ('<svg fill="none" viewBox="0 0 34 34"><path d="M3 28 L11 12 L16 20 L22 6 L31 28 Z" fill="currentColor"/>'
         '<polygon fill="#fdfaf3" points="22,6 25,11 19,11"/><circle cx="28" cy="10" fill="#e07a3f" r="2.5"/></svg>')
_ARROW = ('<svg fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" '
          'stroke-width="1.5" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">'
          '<line x1="5" x2="19" y1="12" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>')
# Decorative sky/skyline scaffold (aria-hidden, pure CSS-driven).
_SKY = (
    '<div aria-hidden="true" class="sky"></div>\n'
    '<div aria-hidden="true" class="orb" id="orb"></div>\n'
    '<div aria-hidden="true" class="clouds" id="clouds"><svg preserveAspectRatio="none" viewBox="0 0 1440 400">'
    '<g fill="#cdd5e0" opacity=".55"><ellipse cx="220" cy="120" rx="180" ry="48"/><ellipse cx="360" cy="150" rx="140" ry="40"/>'
    '<ellipse cx="720" cy="100" rx="220" ry="54"/><ellipse cx="900" cy="140" rx="150" ry="42"/>'
    '<ellipse cx="1180" cy="120" rx="200" ry="50"/><ellipse cx="1340" cy="160" rx="150" ry="40"/></g></svg></div>\n'
    '<div aria-hidden="true" class="rainveil" id="rainveil"></div>\n<div aria-hidden="true" class="lamp" id="lamp"></div>\n')
_HERO_STAGE = (
    '<div class="hero-stage" aria-hidden="true"><div class="hero-sun"></div>'
    '<div class="hero-layer hero-layer-back"></div><div class="hero-layer hero-layer-mid"></div>'
    '<div class="hero-layer hero-layer-front"></div><div class="hero-stars">'
    + "".join(f'<span style="--x:{x}%;--y:{y}%;--d:{d}s"></span>'
              for x, y, d in [(14, 32, 0), (28, 52, 1.2), (46, 24, 2.4), (58, 46, .6), (72, 28, 1.8),
                              (84, 44, 3.2), (18, 62, 2.1), (64, 62, .9), (38, 38, 2.7)])
    + '</div></div>')


def t(d, lang):
    return d.get(lang) or d["fr"]


def load():
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "Json", "*.json"))):
        d = json.load(open(p, encoding="utf-8"))
        if d.get("status") == "published":
            out.append(d)
    return out


def hub_url(hubkey, lang):
    slugs = _BLP.HUB_LOCALE_SLUGS.get(hubkey, {})
    slug = slugs.get(lang) or slugs.get("fr") or hubkey
    return f'{S.BASE_URL}/' + ("" if lang == "fr" else f"{lang}/") + f'{slug}/'


def card(d, lang):
    """Rich card in the engine's shared shape (sync_home_cards contract)."""
    i = d["i18n"].get(lang) or d["i18n"]["fr"]
    href = f"{S.BASE_URL}/{d['slug']}" if lang == "fr" else f"{S.BASE_URL}/{lang}/{d['slug']}"
    img = d.get("hero_image") or ""
    webp = img[:-4] + ".webp" if img.lower().endswith(".jpg") else img
    alt = i.get("hero_alt") or i.get("name") or ""
    name = i.get("name") or ""
    desc = (i.get("hero") or {}).get("lead") or i.get("meta_description") or ""
    free = bool((d.get("schema_org") or {}).get("is_free"))
    tag_txt = t(UI["free"], lang) if free else t(UI["paid"], lang)
    tag_cls = "card-tag is-gratuit" if free else "card-tag is-payant"

    if img:
        # Only offer the webp <source> when the file truly exists — many collected
        # hero photos ship as .jpg only, and a <picture> whose webp source 404s does
        # NOT fall back to <img> (the browser prefers webp and then shows broken).
        img_tag = (f'<img src="{E(img)}" alt="{E(alt)}" width="1600" height="1000" '
                   f'loading="lazy" decoding="async">')
        has_webp = webp != img and os.path.exists(os.path.join(ROOT, webp.lstrip("/")))
        photo_inner = (f'<picture><source srcset="{E(webp)}" type="image/webp">{img_tag}</picture>'
                       if has_webp else img_tag)
    else:
        photo_inner = '<span class="placeholder" aria-hidden="true">🏔</span>'
    photo = (f'<a class="card-photo" href="{E(href)}">{photo_inner}'
             f'<span class="{tag_cls}">{E(tag_txt)}</span></a>')

    dest = f'{name}, {d.get("commune","")}, {S.DEPT_NAME}'
    maps = f'https://www.google.com/maps/dir/?api=1&destination={quote(dest)}'
    actions = f'<a href="{E(maps)}" rel="noopener" target="_blank">{E(t(UI["route"], lang))} ↗</a>'
    off = d.get("official_site_url")
    if off:
        actions += f'<a href="{E(off)}" rel="noopener" target="_blank">{E(t(UI["official"], lang))} ↗</a>'

    return (f'<article class="card">{photo}<div class="card-body">'
            f'<div class="card-commune"><span>{E(d.get("commune",""))}</span></div>'
            f'<a class="title" href="{E(href)}">{E(name)}</a>'
            f'<p class="card-desc">{E(desc)}</p>'
            f'<div class="card-actions">{actions}</div></div></article>')


def build(lang, fiches):
    by_cat = {}
    for f in fiches:
        by_cat.setdefault(f.get("category"), []).append(f)

    def hub_items(hubkey):
        out = []
        for c in HUBS[hubkey]["cats"]:
            out += by_cat.get(c, [])
        return out

    live = [h for h in HUBS if hub_items(h)]  # only hubs that actually have places

    # --- top bar ---------------------------------------------------------------
    lang_menu = "".join(
        f'<a href="{S.BASE_URL}/' + ("" if L == "fr" else f"{L}/") + f'" hreflang="{L}"'
        + (' aria-current="true"' if L == lang else '') + f'>{_LANG_NAMES[L]}</a>' for L in LANGS)
    header = (
        f'<header class="site" id="siteHeader"><a class="brand" href="{S.BASE_URL}/">'
        f'<span class="mark"><img src="/logo.png" alt="{E(S.SITE_NAME)}" width="40" height="40"></span>'
        f'<span><b>loisirs73</b> <i>{E(t(UI["brand_tag"], lang))}</i></span></a>'
        f'<div class="nav-right"><button class="near-me" id="nearMe">{E(t(UI["near"], lang))}</button>'
        f'<details class="lang-picker"><summary><b>{lang.upper()}</b></summary>'
        f'<div class="lang-menu">{lang_menu}</div></details></div></header>')

    # --- hero ------------------------------------------------------------------
    hero = (
        f'<section class="hero">{_HERO_STAGE}<div class="wrap hero-content">'
        f'<div class="kicker" id="kicker">{E(t(UI["kicker"], lang) % len(fiches))}</div>'
        f'<h1>{E(t(UI["h1_pre"], lang))}<br/><em>{E(t(UI["dept"], lang))}</em></h1>'
        f'<p class="lede">{t(UI["lede"], lang)}</p></div></section>')

    # --- glance directory ------------------------------------------------------
    groups_html = ""
    for glabel, keys in GROUPS:
        keys = [k for k in keys if k in live]
        if not keys:
            continue
        tiles = "".join(
            f'<a class="glance-tile" href="{hub_url(k, lang)}">'
            f'<span class="gt-name">{E(t(HUBS[k]["label"], lang))}</span>'
            f'<span class="gt-count">{E(t(UI["count_tile"], lang) % len(hub_items(k)))}</span></a>'
            for k in keys)
        groups_html += (f'<div class="glance-group"><div class="glance-label">{E(t(glabel, lang))}</div>'
                        f'<div class="glance-grid">{tiles}</div></div>')
    glance = (
        f'<section aria-label="{E(t(UI["glance_h"], lang))}" class="glance" id="glance"><div class="wrap" id="categories">'
        f'<div class="glance-head"><h2>{E(t(UI["glance_h"], lang))}</h2><p>{E(t(UI["glance_sub"], lang))}</p></div>'
        f'{groups_html}</div></section>')

    # --- "Nos sélections" strip: the curated intent hubs ----------------------
    selections = ""
    _intent_path = os.path.join(ROOT, "data", "intent-hubs.json")
    if os.path.exists(_intent_path):
        intents = json.load(open(_intent_path, encoding="utf-8"))
        if intents:
            tiles = ""
            for h in intents:
                slug = h["slug"]
                url = f'{S.BASE_URL}/' + ("" if lang == "fr" else f"{lang}/") + slug
                h1 = (h.get("h1") or {}).get(lang) or (h.get("h1") or {}).get("fr") or slug
                tiles += (f'<a class="glance-tile" href="{E(url)}">'
                          f'<span class="gt-name">{E(h1)}</span>'
                          f'<span class="gt-count">{len(h.get("members", []))}</span></a>')
            selections = (
                f'<section aria-label="{E(t(UI["sel_h"], lang))}" class="glance" id="selections"><div class="wrap">'
                f'<div class="glance-head"><h2>{E(t(UI["sel_h"], lang))}</h2><p>{E(t(UI["sel_sub"], lang))}</p></div>'
                f'<div class="glance-group"><div class="glance-grid">{tiles}</div></div>'
                f'</div></section>')

    # --- bands + category carousels -------------------------------------------
    body_sections = ""
    for blabel, bsub, keys in BANDS:
        keys = [k for k in keys if k in live]
        if not keys:
            continue
        body_sections += (f'<div class="band"><div class="wrap"><h2 class="band-title">{E(t(blabel, lang))}</h2>'
                          f'<p class="band-sub">{E(t(bsub, lang))}</p></div></div>')
        for k in keys:
            cid = HUBS[k]["cats"][0]
            body_sections += (
                f'<section class="cat" id="{E(cid)}"><div class="wrap"><div class="cat-head">'
                f'<div class="cat-head-left"><h2>{E(t(HUBS[k]["label"], lang))}</h2></div>'
                f'<a class="see-all" href="{hub_url(k, lang)}">{E(t(UI["see_all"], lang))} {_ARROW}</a></div>'
                f'<div class="carousel">' + "".join(card(f, lang) for f in hub_items(k)) + '</div></div></section>')

    # --- branded sister panel --------------------------------------------------
    sister = (
        f'<aside class="sister-band" aria-label="{E(t(UI["sis_kicker"], lang))}"><div class="sister-card">'
        f'<img src="/img/sister/loisirs74-logo.png" alt="{E(_SIS["name"])}" width="78" height="78" loading="lazy">'
        f'<div class="st"><span class="k">{E(t(UI["sis_kicker"], lang))}</span>'
        f'<span class="n">{E(_SIS["name"])} · {E(_SIS["dept"])}</span>'
        f'<p>{E(t(UI["sis_body"], lang))}</p></div>'
        f'<a class="go" href="{E(_SIS["url"])}" rel="noopener">{E(t(UI["sis_go"], lang))} {_ARROW}</a>'
        f'</div></aside>')

    # --- footer ----------------------------------------------------------------
    foot_cats = "".join(f'<li><a href="{hub_url(k, lang)}">{t(HUBS[k]["label"], lang).replace("&", "&amp;")}</a></li>'
                        for k in live)
    # que-faire is the site's "what to do" selection hub (not a place category);
    # link it so its localized directories stay reachable, as the sister does.
    _qf = {"fr": "Que faire ?", "en": "What to do?", "de": "Was unternehmen?",
           "it": "Cosa fare?", "es": "¿Qué hacer?", "nl": "Wat te doen?"}
    if "que-faire" in _BLP.HUB_LOCALE_SLUGS:
        foot_cats += f'<li><a href="{hub_url("que-faire", lang)}">{E(t(_qf, lang))}</a></li>'
    foot_langs = "".join(
        f'<li><a href="{S.BASE_URL}/' + ("" if L == "fr" else f"{L}/") + f'" hreflang="{L}">{_LANG_NAMES[L]}</a></li>'
        for L in LANGS)
    footer = (
        f'<footer class="site"><div class="wrap"><div class="foot-grid">'
        f'<div class="foot-col"><h3>{E(S.SITE_NAME)}</h3><p>{E(t(UI["foot_about"], lang))}</p></div>'
        f'<div class="foot-col"><h3>{E(t(UI["foot_cats"], lang))}</h3><ul>{foot_cats}</ul></div>'
        f'<div class="foot-col"><h3>{E(t(UI["foot_lang"], lang))}</h3><ul>{foot_langs}</ul></div>'
        f'<div class="foot-col"><h3>{E(t(UI["foot_sister_k"], lang))}</h3>'
        f'<p><a href="{E(_SIS["url"])}" rel="noopener">{E(_SIS["name"])} · {E(_SIS["dept"])}</a></p></div>'
        f'</div><p style="margin-top:1.4rem;opacity:.7">© 2026 · {E(S.IMPRINT)} · Tous droits réservés 🦆</p>'
        f'</div></footer>')

    alts = "".join(f'<link rel="alternate" hreflang="{L}" href="{S.BASE_URL}/'
                   + ("" if L == "fr" else f"{L}/") + '"/>\n' for L in LANGS)

    # Pre-launch only: block metas track robots.txt's FLIP-AT-LAUNCH marker.
    _robots = os.path.join(ROOT, "robots.txt")
    _prelaunch = os.path.exists(_robots) and "FLIP-AT-LAUNCH" in open(_robots, encoding="utf-8").read()
    noindex_block = (
        '<!-- FLIP-AT-LAUNCH: the robots metas below block this site until launch;\n'
        '     robots.txt carries the matching marker and this homepage is generated\n'
        '     by scripts/build_home_73.py. -->\n'
        '<meta name="robots" content="noindex,nofollow">\n'
        '<meta name="googlebot" content="noindex,nofollow">\n') if _prelaunch else ''
    prep_banner = (f'<div class="band"><div class="wrap"><p class="band-sub" style="margin:0">'
                   f'{E(t(UI["prep"], lang))}</p></div></div>') if _prelaunch else ''

    title = f'{S.SITE_NAME} · {t(UI["h1_pre"], lang)} {t(UI["dept"], lang)}'
    desc = t(UI["lede"], lang).replace("<b>", "").replace("</b>", "")

    return (
        f'<!doctype html>\n<html lang="{lang}">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        + noindex_block +
        f'<title>{E(title)}</title>\n<meta name="description" content="{E(desc)}">\n'
        '<link rel="icon" type="image/x-icon" href="/favicon.ico">\n'
        '<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png">\n'
        '<link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png">\n'
        '<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">\n'
        f'<link rel="manifest" href="/site.webmanifest">\n{alts}'
        f'<style>{CSS}{SIS_CSS}</style>\n</head>\n<body>\n'
        f'{_SKY}{header}\n<main>\n{hero}\n{glance}\n{selections}\n{prep_banner}{body_sections}{sister}\n</main>\n{footer}\n'
        f'<script src="/scripts/l74sort.js" defer></script>\n'
        f'<script src="/scripts/nearme.js" defer></script>\n'
        '</body>\n</html>\n')


def main():
    fiches = load()
    n = 0
    for lang in LANGS:
        d = ROOT if lang == "fr" else os.path.join(ROOT, lang)
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(build(lang, fiches))
        n += 1
    print(f"build_home_73: {n} homepages from {len(fiches)} published fiches")


if __name__ == "__main__":
    main()
