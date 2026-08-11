#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_home_73.py — the Savoie homepage, generated from the fiche layer.

Editorial homepage in the shape of the sister site: a hero band, then one
SECTION per category — each with its own header, a "see all" link to the hub,
and a carousel of rich cards (photo, free/paid badge, commune, title, a two-line
description and quick actions). Replaces the earlier flat list of bare grids.

Nothing here is hand-listed. Sections come from the fiche categories, cards from
the fiches themselves, so the homepage cannot drift from the catalogue. The card
markup matches the engine's shared post-processors (sync_home_cards's
`<a class="card-photo">…<picture>` contract, the facet-hub `</body>` inject, the
head normaliser's canonical/hreflang pass), so the whole build chain still holds.
"""
import json, glob, os, sys, html
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import siteconfig as S
import build_lieu_page as _BLP  # canonical hub slug table — single source

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("fr", "en", "de", "it", "es", "nl")
E = lambda s: html.escape(str(s or ""), quote=True)
_SIS = getattr(S, "SISTER", None) or {"name": S.SITE_NAME, "url": S.BASE_URL, "dept": S.DEPT_NAME}

# (category-or-tuple, hub-slug-key, {lang: label}). One bucket per homepage row;
# the hub key ties the row's "see all" to the engine's canonical hub table.
SECTIONS = [
    ("point-de-vue", "points-de-vue",
     {"fr": "Cols et points de vue", "en": "Passes and viewpoints", "de": "Pässe und Aussichtspunkte",
      "it": "Colli e punti panoramici", "es": "Puertos y miradores", "nl": "Bergpassen en uitzichtpunten"}),
    ("telecabine", "telecabines",
     {"fr": "Remontées mécaniques", "en": "Cable cars and lifts", "de": "Bergbahnen",
      "it": "Impianti di risalita", "es": "Remontes", "nl": "Kabelbanen en liften"}),
    ("cascade", "cascades",
     {"fr": "Cascades et gorges", "en": "Waterfalls and gorges", "de": "Wasserfälle und Schluchten",
      "it": "Cascate e gole", "es": "Cascadas y gargantas", "nl": "Watervallen en kloven"}),
    ("chateau", "chateaux",
     {"fr": "Châteaux et forts", "en": "Castles and forts", "de": "Schlösser und Festungen",
      "it": "Castelli e forti", "es": "Castillos y fuertes", "nl": "Kastelen en forten"}),
    ("musee", "musees",
     {"fr": "Musées", "en": "Museums", "de": "Museen", "it": "Musei", "es": "Museos", "nl": "Musea"}),
    (("lac", "plage"), "lacs-plages",
     {"fr": "Lacs et plages", "en": "Lakes and beaches", "de": "Seen und Strände",
      "it": "Laghi e spiagge", "es": "Lagos y playas", "nl": "Meren en stranden"}),
    ("sentier", "sentiers",
     {"fr": "Sentiers et randonnées", "en": "Trails and hikes", "de": "Wege und Wanderungen",
      "it": "Sentieri ed escursioni", "es": "Senderos y rutas", "nl": "Wandelpaden en tochten"}),
]

UI = {
 "kicker": {"fr": "Guide indépendant · Savoie", "en": "Independent guide · Savoie",
            "de": "Unabhängiger Guide · Savoie", "it": "Guida indipendente · Savoie",
            "es": "Guía independiente · Savoie", "nl": "Onafhankelijke gids · Savoie"},
 "tagline": {"fr": "La Savoie, lieu par lieu.", "en": "Savoie, place by place.",
             "de": "Savoie, Ort für Ort.", "it": "La Savoie, luogo per luogo.",
             "es": "La Savoie, lugar por lugar.", "nl": "Savoie, plek voor plek."},
 "lede": {"fr": "Un guide indépendant des lieux de loisirs en Savoie. Chaque fait est vérifié auprès d'une "
                "source officielle — et quand les sources se contredisent, la fiche le dit au lieu de choisir.",
          "en": "An independent guide to leisure places in Savoie. Every fact is checked against an official "
                "source — and where sources disagree, the page says so instead of picking one.",
          "de": "Ein unabhängiger Führer zu den Freizeitorten der Savoie. Jede Angabe ist an einer offiziellen "
                "Quelle geprüft — und wenn Quellen sich widersprechen, sagt die Seite es, statt zu wählen.",
          "it": "Una guida indipendente ai luoghi di svago della Savoie. Ogni dato è verificato su una fonte "
                "ufficiale — e quando le fonti si contraddicono, la scheda lo dice invece di scegliere.",
          "es": "Una guía independiente de los lugares de ocio de la Savoie. Cada dato se verifica en una fuente "
                "oficial — y cuando las fuentes se contradicen, la ficha lo dice en vez de elegir.",
          "nl": "Een onafhankelijke gids voor de vrijetijdsplekken van de Savoie. Elk feit is getoetst aan een "
                "officiële bron — en als bronnen elkaar tegenspreken, zegt de pagina dat in plaats van te kiezen."},
 "count": {"fr": "%d lieux vérifiés", "en": "%d verified places", "de": "%d geprüfte Orte",
           "it": "%d luoghi verificati", "es": "%d lugares verificados", "nl": "%d geverifieerde plekken"},
 "see_all": {"fr": "Voir tout", "en": "See all", "de": "Alle ansehen", "it": "Vedi tutto",
             "es": "Ver todo", "nl": "Alles bekijken"},
 "free": {"fr": "Gratuit", "en": "Free", "de": "Kostenlos", "it": "Gratuito", "es": "Gratis", "nl": "Gratis"},
 "paid": {"fr": "Payant", "en": "Paid", "de": "Kostenpflichtig", "it": "A pagamento", "es": "De pago", "nl": "Betaald"},
 "route": {"fr": "Itinéraire", "en": "Directions", "de": "Route", "it": "Itinerario", "es": "Cómo llegar", "nl": "Route"},
 "official": {"fr": "Site officiel", "en": "Official site", "de": "Offizielle Seite",
              "it": "Sito ufficiale", "es": "Sitio oficial", "nl": "Officiële site"},
 # Sister block — same publisher, same rule.
 "sis_kicker": {"fr": "L'autre département", "en": "The other department", "de": "Das andere Département",
                "it": "L'altro dipartimento", "es": "El otro departamento", "nl": "Het andere departement"},
 "sis_body": {"fr": "Même éditeur, même règle : chaque fait vérifié auprès d'une source officielle, "
                    "et les contradictions affichées plutôt qu'arbitrées.",
              "en": "Same publisher, same rule: every fact checked against an official source, "
                    "and contradictions shown rather than quietly resolved.",
              "de": "Gleicher Herausgeber, gleiche Regel: jede Angabe an einer offiziellen Quelle geprüft, "
                    "Widersprüche gezeigt statt still aufgelöst.",
              "it": "Stesso editore, stessa regola: ogni dato verificato su una fonte ufficiale, "
                    "e le contraddizioni mostrate anziché risolte in silenzio.",
              "es": "Mismo editor, misma regla: cada dato verificado en una fuente oficial, "
                    "y las contradicciones mostradas en vez de resueltas en silencio.",
              "nl": "Zelfde uitgever, zelfde regel: elk feit getoetst aan een officiële bron, "
                    "en tegenstrijdigheden getoond in plaats van stilletjes opgelost."},
 "sis_go": {"fr": "Ouvrir loisirs74.fr", "en": "Open loisirs74.fr", "de": "loisirs74.fr öffnen",
            "it": "Apri loisirs74.fr", "es": "Abrir loisirs74.fr", "nl": "loisirs74.fr openen"},
 "prep": {"fr": "Site en préparation : rien n'est indexé pour l'instant.",
          "en": "Site in preparation: nothing is indexed yet.",
          "de": "Website in Vorbereitung: noch nichts indexiert.",
          "it": "Sito in preparazione: nulla è ancora indicizzato.",
          "es": "Sitio en preparación: nada está indexado todavía.",
          "nl": "Site in voorbereiding: nog niets geïndexeerd."},
}

# The arrow used in the sister site's "see all" link.
_ARROW = ('<svg fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" '
          'stroke-width="1.5" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">'
          '<line x1="5" x2="19" y1="12" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>')


def t(d, lang):
    return d.get(lang) or d["fr"]


def load():
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "Json", "*.json"))):
        d = json.load(open(p, encoding="utf-8"))
        if d.get("status") == "published":
            out.append(d)
    return out


def _is_free(d):
    return bool((d.get("schema_org") or {}).get("is_free"))


def card(d, lang):
    """A rich card matching the engine's post-processor contract:
    <a class="card-photo" href=".../slug"><picture>…<img>…<span card-tag></a>
    then a .card-body with commune, serif title, 2-line desc and actions."""
    i = d["i18n"].get(lang) or d["i18n"]["fr"]
    href = f"{S.BASE_URL}/{d['slug']}" if lang == "fr" else f"{S.BASE_URL}/{lang}/{d['slug']}"
    img = d.get("hero_image") or ""
    webp = img[:-4] + ".webp" if img.lower().endswith(".jpg") else img
    alt = i.get("hero_alt") or i.get("name") or ""
    name = i.get("name") or ""
    desc = (i.get("hero") or {}).get("lead") or i.get("meta_description") or ""

    free = _is_free(d)
    tag_txt = t(UI["free"], lang) if free else t(UI["paid"], lang)
    tag_cls = "card-tag is-gratuit" if free else "card-tag is-payant"

    # Photo (or a gradient placeholder when a fiche carries no hero).
    if img:
        photo_inner = (f'<picture><source srcset="{E(webp)}" type="image/webp">'
                       f'<img src="{E(img)}" alt="{E(alt)}" width="1600" height="1000" '
                       f'loading="lazy" decoding="async"></picture>')
    else:
        photo_inner = '<span class="placeholder" aria-hidden="true">🏔</span>'
    photo = (f'<a class="card-photo" href="{E(href)}">{photo_inner}'
             f'<span class="{tag_cls}">{E(tag_txt)}</span></a>')

    # Actions: directions (always) + official site (when known).
    dest = f'{name}, {d.get("commune","")}, {S.DEPT_NAME}'
    from urllib.parse import quote
    maps = f'https://www.google.com/maps/dir/?api=1&destination={quote(dest)}'
    actions = (f'<a href="{E(maps)}" rel="noopener" target="_blank">{E(t(UI["route"], lang))} ↗</a>')
    off = d.get("official_site_url")
    if off:
        actions += f'<a href="{E(off)}" rel="noopener" target="_blank">{E(t(UI["official"], lang))} ↗</a>'

    body = (f'<div class="card-body">'
            f'<div class="card-commune"><span>{E(d.get("commune",""))}</span></div>'
            f'<a class="title" href="{E(href)}">{E(name)}</a>'
            f'<p class="card-desc">{E(desc)}</p>'
            f'<div class="card-actions">{actions}</div>'
            f'</div>')
    return f'<article class="card">{photo}{body}</article>'


CSS = (
    ":root{--bg:#faf8f3;--surface:#fff;--line:#e6e2d8;--ink:#14110c;--ink-soft:#4a453c;"
    "--ink-mute:#7a746a;--accent:#0b5170;--accent-ink:#0b5170;--serif:Georgia,'Times New Roman',serif}"
    "*{box-sizing:border-box}"
    "body{margin:0;background:var(--bg);color:var(--ink);"
    "font:16px/1.6 system-ui,-apple-system,'Segoe UI',Roboto,sans-serif}"
    "img{max-width:100%}"
    ".wrap{max-width:68rem;margin:0 auto;padding:0 1.25rem}"
    "a{color:var(--accent)}"
    # top mark
    ".mark{display:inline-flex;align-items:center;gap:.6rem;font-weight:700;padding:1.3rem 0 0}"
    ".mark img{width:30px;height:30px;border-radius:8px}"
    # hero
    ".hero{border-bottom:1px solid var(--line);padding:1rem 0 2.4rem;margin-bottom:.5rem}"
    ".kicker{font:700 .74rem/1 system-ui;letter-spacing:.14em;text-transform:uppercase;"
    "color:var(--accent);margin:1.6rem 0 .7rem}"
    "h1{font-family:var(--serif);font-weight:600;font-size:clamp(2rem,1.3rem + 3.4vw,3.4rem);"
    "line-height:1.04;letter-spacing:-.02em;margin:0 0 .8rem}"
    ".lede{font-size:1.08rem;max-width:46rem;color:var(--ink-soft);margin:0 0 1.1rem}"
    ".count{font-weight:600;color:var(--ink)}"
    # hub pills
    ".hubs ul{list-style:none;padding:0;display:flex;flex-wrap:wrap;gap:.55rem;margin:1.3rem 0 0}"
    ".hubs a{display:inline-block;padding:.42rem .85rem;border:1px solid var(--line);border-radius:999px;"
    "background:var(--surface);text-decoration:none;color:var(--ink);font-size:.9rem}"
    ".hubs a:hover{border-color:var(--accent);color:var(--accent)}"
    # category section
    ".cat{padding:2.6rem 0 .4rem}"
    ".cat-head{display:flex;align-items:baseline;justify-content:space-between;gap:1rem;"
    "flex-wrap:wrap;margin-bottom:1.2rem}"
    ".cat-head h2{font-family:var(--serif);font-weight:600;font-size:1.5rem;letter-spacing:-.01em;margin:0}"
    ".see-all{font-family:var(--serif);font-style:italic;font-size:1.02rem;color:var(--accent);"
    "text-decoration:none;display:inline-flex;align-items:center;gap:.4rem;"
    "border-bottom:1px solid var(--accent);padding-bottom:1px}"
    ".see-all:hover{gap:.65rem}"
    # carousel grid
    ".carousel{display:grid;grid-template-columns:repeat(auto-fill,minmax(15.5rem,1fr));gap:1.4rem 1.2rem}"
    # card
    ".card{background:var(--surface);border:1px solid var(--line);border-radius:12px;overflow:hidden;"
    "display:flex;flex-direction:column;min-width:0}"
    ".card-photo{display:block;position:relative;aspect-ratio:16/10;overflow:hidden;"
    "background:linear-gradient(135deg,#2c3a52,#1f2836 60%,#161d29)}"
    ".card-photo img{width:100%;height:100%;object-fit:cover;display:block;transition:transform .8s ease}"
    ".card:hover .card-photo img{transform:scale(1.04)}"
    ".card-photo .placeholder{position:absolute;inset:0;display:grid;place-items:center;font-size:2rem;opacity:.5}"
    ".card-tag{position:absolute;top:11px;right:11px;padding:.28rem .66rem;border-radius:999px;"
    "font:700 .64rem/1 system-ui;letter-spacing:.06em;text-transform:uppercase;color:#fff;"
    "background:rgba(20,17,12,.62);-webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px)}"
    ".card-tag.is-gratuit{background:#2e6b4a}"
    ".card-body{padding:.9rem 1rem 1rem;display:flex;flex-direction:column;gap:.32rem;flex:1}"
    ".card-commune{font-size:.73rem;letter-spacing:.04em;text-transform:uppercase;color:var(--ink-mute)}"
    "a.title{font-family:var(--serif);font-weight:600;font-size:1.14rem;line-height:1.16;"
    "letter-spacing:-.01em;color:var(--ink);text-decoration:none}"
    "a.title:hover{color:var(--accent)}"
    ".card-desc{font-size:.86rem;line-height:1.45;color:var(--ink-soft);margin:.1rem 0 .5rem;"
    "display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}"
    ".card-actions{display:flex;gap:1rem;margin-top:auto;padding-top:.6rem;border-top:1px dashed var(--line);"
    "font-size:.76rem;flex-wrap:wrap}"
    ".card-actions a{color:var(--ink-mute);text-decoration:none;font-weight:600}"
    ".card-actions a:hover{color:var(--accent)}"
    # sister panel
    ".sis{margin:3.2rem auto 0;max-width:68rem;border:1px solid var(--line);border-radius:16px;"
    "padding:1.4rem 1.5rem;background:var(--surface);display:flex;gap:1.1rem;align-items:center;flex-wrap:wrap}"
    ".sis img{width:56px;height:56px;border-radius:12px;flex:0 0 auto}"
    ".sis .txt{flex:1 1 16rem;min-width:0}"
    ".sis .k{display:block;font-size:.74rem;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-mute);margin-bottom:.15rem}"
    ".sis .n{display:block;font-size:1.22rem;font-weight:700;color:var(--ink);letter-spacing:-.01em}"
    ".sis p{margin:.35rem 0 0;color:var(--ink-soft);font-size:.94rem}"
    ".sis .go{flex:0 0 auto;display:inline-block;padding:.6rem 1.1rem;border-radius:999px;"
    "background:var(--accent);color:#fff;text-decoration:none;font-weight:600}"
    # footer
    "footer{margin-top:3rem;padding:1.3rem 0 2.4rem;border-top:1px solid var(--line);"
    "color:var(--ink-mute);font-size:.85rem}"
    # dark last so it wins on equal specificity
    "@media(prefers-color-scheme:dark){:root{--bg:#0b0d10;--surface:#13171c;--line:#262c34;"
    "--ink:#f4f6f8;--ink-soft:#c8cfd8;--ink-mute:#8b95a1;--accent:#7ad9f5}"
    ".hubs a{background:transparent}.sis .go{color:#06202c}.card-actions a:hover,a.title:hover,.hubs a:hover{color:var(--accent)}}"
)


def build(lang, fiches):
    import build_hubs as _BH
    # Hub pills — roster-driven, engine's own slug table, absolute URLs (what
    # gate_link_integrity's homepage-orphan tripwire looks for).
    hubmap = {h: _BLP.HUB_LOCALE_SLUGS[h] for h in _BH.HUB_DISPLAY if h in _BLP.HUB_LOCALE_SLUGS}
    hublab = {h: _BH.HUB_DISPLAY[h] for h in hubmap}
    hublab["que-faire"] = {"fr": "Que faire en Savoie", "en": "What to do in Savoie",
                           "de": "Was unternehmen in Savoie", "it": "Cosa fare in Savoie",
                           "es": "Qué hacer en Savoie", "nl": "Wat te doen in Savoie"}
    nav = '<nav class="hubs"><ul>' + "".join(
        f'<li><a href="{E(S.BASE_URL)}/' + ("" if lang == "fr" else f"{lang}/")
        + E(hubmap[h].get(lang) or hubmap[h]["fr"]) + '/">'
        + E(t(hublab[h], lang)) + '</a></li>' for h in hubmap) + '</ul></nav>'

    # Category sections, each a header (title + see-all to the hub) + a carousel.
    secs = ""
    for cat, hubkey, label in SECTIONS:
        cats = cat if isinstance(cat, tuple) else (cat,)
        items = [f for f in fiches if f.get("category") in cats]
        if not items:
            continue
        hub_slugs = _BLP.HUB_LOCALE_SLUGS.get(hubkey, {})
        hub_slug = hub_slugs.get(lang) or hub_slugs.get("fr") or hubkey
        hub_url = f'{S.BASE_URL}/' + ("" if lang == "fr" else f"{lang}/") + f'{hub_slug}/'
        cid = cats[0]
        secs += (
            f'<section class="cat" id="{E(cid)}"><div class="wrap">'
            f'<div class="cat-head"><div class="cat-head-left"><h2>{E(t(label, lang))}</h2></div>'
            f'<a class="see-all" href="{E(hub_url)}">{E(t(UI["see_all"], lang))} {_ARROW}</a></div>'
            f'<div class="carousel">'
            + "".join(card(f, lang) for f in items)
            + '</div></div></section>\n')

    alts = "".join(f'<link rel="alternate" hreflang="{L}" href="{S.BASE_URL}/'
                   + ("" if L == "fr" else f"{L}/") + '"/>\n' for L in LANGS)

    # Pre-launch only: block metas track robots.txt's FLIP-AT-LAUNCH marker.
    _robots = os.path.join(ROOT, "robots.txt")
    _prelaunch = os.path.exists(_robots) and "FLIP-AT-LAUNCH" in open(_robots, encoding="utf-8").read()
    noindex_block = (
        '<!-- FLIP-AT-LAUNCH: the two robots metas below block this site until the real domain\n'
        '     goes live. robots.txt carries the matching marker. This homepage is generated\n'
        '     by scripts/build_home_73.py; the metas vanish when robots.txt is flipped. -->\n'
        '<meta name="robots" content="noindex,nofollow">\n'
        '<meta name="googlebot" content="noindex,nofollow">\n') if _prelaunch else ''

    prep = f' · <span class="count">{E(t(UI["prep"], lang))}</span>' if _prelaunch else ''

    return (
        f'<!doctype html>\n<html lang="{lang}">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        + noindex_block +
        f'<title>{E(S.SITE_NAME)} — {E(t(UI["tagline"], lang))}</title>\n'
        f'<meta name="description" content="{E(t(UI["lede"], lang))}">\n'
        f'<link rel="icon" href="/favicon.ico" sizes="any">\n{alts}'
        f'<style>{CSS}</style>\n</head>\n<body>\n'
        f'<header class="hero"><div class="wrap">'
        f'<span class="mark"><img src="/mark.png" alt="" width="30" height="30">{E(S.SITE_NAME)}</span>\n'
        f'<p class="kicker">{E(t(UI["kicker"], lang))}</p>\n'
        f'<h1>{E(t(UI["tagline"], lang))}</h1>\n'
        f'<p class="lede">{E(t(UI["lede"], lang))}</p>\n'
        f'<p><span class="count">{E(t(UI["count"], lang) % len(fiches))}</span>{prep}</p>\n'
        f'{nav}'
        f'</div></header>\n'
        f'<main>\n{secs}</main>\n'
        f'<aside class="sis">'
        f'<img src="/img/sister/loisirs74-mark.png" alt="" width="56" height="56" loading="lazy">'
        f'<span class="txt"><span class="k">{E(t(UI["sis_kicker"], lang))}</span>'
        f'<span class="n">{E(_SIS["name"])} · {E(_SIS["dept"])}</span>'
        f'<p>{E(t(UI["sis_body"], lang))}</p></span>'
        f'<a class="go" href="{E(_SIS["url"])}" rel="noopener">{E(t(UI["sis_go"], lang))}</a>'
        f'</aside>\n'
        f'<footer><div class="wrap">2026 · {E(S.IMPRINT)} · Tous droits réservés</div></footer>\n'
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
