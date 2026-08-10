#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_home_73.py — the Savoie homepage, generated from the fiche layer.

Replaces the pre-launch holding page with a navigable index while KEEPING the
two noindex metas and the FLIP-AT-LAUNCH marker: the site is browsable but
still blocked, exactly as robots.txt intends. The holding page's own promise
("rien n'est publié tant que les faits ne sont pas vérifiés") is kept as the
lede, because it is still true.

Nothing here is hand-listed. Sections come from the fiche categories, cards
from the fiches themselves, so the homepage cannot drift from the catalogue.
"""
import json, glob, os, sys, html
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import siteconfig as S
import build_lieu_page as _BLP  # canonical hub slug table — single source

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("fr", "en", "de", "it", "es", "nl")
E = lambda s: html.escape(str(s or ""), quote=True)
_SIS = getattr(S, "SISTER", None) or {"name": S.SITE_NAME, "url": S.BASE_URL, "dept": S.DEPT_NAME}

# One bucket for the lifts. The old split ("Téléphériques" vs "Télécabines et
# funiculaires") was an invented category the engine's vocabularies had never
# heard of — WINTER_NODES, CATEGORY_LABEL_FR and the commune labels all knew
# `telecabine` only, so 10 of the 15 lifts silently rendered no winter block at
# all. The split didn't even track the names: the Téléphérique de l'Olympique
# sat in one bucket and the Téléphérique de la Saulire in the other.
SECTIONS = [("point-de-vue", {"fr": "Cols et points de vue", "en": "Passes and viewpoints"}),
            ("telecabine", {"fr": "Remontées mécaniques", "en": "Cable cars and lifts"}),
            ("cascade", {"fr": "Cascades et gorges", "en": "Waterfalls and gorges"}),
            ("chateau", {"fr": "Châteaux et forts", "en": "Castles and forts"}),
            ("musee", {"fr": "Musées", "en": "Museums"}),
            # lac + plage share one homepage section, mirroring the lacs-plages hub
            (("lac", "plage"), {"fr": "Lacs et plages", "en": "Lakes and beaches"}),
            ("sentier", {"fr": "Sentiers et randonnées", "en": "Trails and hikes"})]
UI = {
 "tagline": {"fr": "La Savoie, lieu par lieu.", "en": "Savoie, place by place."},
 "lede": {"fr": "Un guide indépendant des lieux de loisirs en Savoie. Chaque fait est vérifié auprès d'une "
                "source officielle — et quand les sources se contredisent, la fiche le dit au lieu de choisir.",
          "en": "An independent guide to leisure places in Savoie. Every fact is checked against an official "
                "source — and where sources disagree, the page says so instead of picking one."},
 "count": {"fr": "%d lieux vérifiés", "en": "%d verified places"},
 # Wording matches build_lieu_page's f_sister ("Aussi en" / "Also in"), which is
 # the engine's own convention in six languages. A family metaphor dates badly and
 # implies a hierarchy between two sites that are simply the same publisher.
 "sister": {"fr": "Même exigence en", "en": "Same standard in", "de": "Gleicher Anspruch in",
            "it": "Stesso rigore in", "es": "El mismo rigor en", "nl": "Dezelfde maatstaf in"},
 # The sibling panel carries the proposition, not just the name. Same publisher,
 # same verification rule — that is the reason to cross the departmental border.
 "sis_kicker": {"fr": "L'autre département", "en": "The other department"},
 "sis_body": {"fr": "Même éditeur, même règle : chaque fait vérifié auprès d'une source officielle, "
                    "et les contradictions affichées plutôt qu'arbitrées.",
              "en": "Same publisher, same rule: every fact checked against an official source, "
                    "and contradictions shown rather than quietly resolved."},
 "sis_go": {"fr": "Ouvrir loisirs74.fr", "en": "Open loisirs74.fr"},
 "prep": {"fr": "Site en préparation : rien n'est indexé pour l'instant.",
          "en": "Site in preparation: nothing is indexed yet."},
}
def t(d, lang): return d.get(lang) or d["fr"]

def load():
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "Json", "*.json"))):
        d = json.load(open(p, encoding="utf-8"))
        if d.get("status") == "published":
            out.append(d)
    return out

def card(d, lang):
    i = d["i18n"].get(lang) or d["i18n"]["fr"]
    href = f"/{d['slug']}" if lang == "fr" else f"/{lang}/{d['slug']}"
    img = d.get("hero_image") or ""
    return (f'<li class="card"><a href="{E(href)}">'
            + (f'<img src="{E(img)}" alt="{E(i.get("hero_alt"))}" loading="lazy" width="400" height="260">' if img else "")
            + f'<span class="ct">{E(i["name"])}</span>'
            f'<span class="cc">{E(d["commune"])}</span></a></li>')

def build(lang, fiches):
    # Hub nav — every hub in the roster must be reachable from the homepage or the
    # reachability gate reports it as an orphan, which is exactly what it is for.
    # Slugs come from the engine's canonical table, not a second copy here — a
    # local fr/en-only map made de/it/es/nl fall through to the French slug and
    # link /de/points-de-vue/, a directory that does not exist in any locale but
    # French. Absolute URLs, because that is what the rest of the site emits and
    # what gate_link_integrity's homepage-orphan tripwire looks for.
    # Roster-driven: every hub in data/hub-titles.json appears in the nav, with
    # the engine's own display names. A hand-kept 3-hub tuple meant every new
    # category shipped with its hub orphaned from the homepage — cascades did.
    import build_hubs as _BH
    hubmap = {h: _BLP.HUB_LOCALE_SLUGS[h] for h in _BH.HUB_DISPLAY
              if h in _BLP.HUB_LOCALE_SLUGS}
    hublab = {h: _BH.HUB_DISPLAY[h] for h in hubmap}
    # que-faire keeps its fuller wording — a nav entry reading just "Que faire"
    # loses the department, and this one is the site's front door to selections.
    hublab["que-faire"] = {"fr": "Que faire en Savoie", "en": "What to do in Savoie",
                           "de": "Was unternehmen in Savoie", "it": "Cosa fare in Savoie",
                           "es": "Qué hacer en Savoie", "nl": "Wat te doen in Savoie"}
    nav = '<nav class="hubs"><ul>' + "".join(
        f'<li><a href="{E(S.BASE_URL)}/' + ("" if lang == "fr" else f"{lang}/")
        + E(hubmap[h].get(lang) or hubmap[h]["fr"]) + '/">'
        + E(t(hublab[h], lang)) + '</a></li>' for h in hubmap) + '</ul></nav>\n'
    secs = ""
    for cat, label in SECTIONS:
        cats = cat if isinstance(cat, tuple) else (cat,)
        items = [f for f in fiches if f.get("category") in cats]
        if not items:
            continue
        secs += (f'<section><h2>{E(t(label, lang))}</h2><ul class="grid">'
                 + "".join(card(f, lang) for f in items) + "</ul></section>\n")
    alts = "".join(f'<link rel="alternate" hreflang="{L}" href="{S.BASE_URL}/'
                   + ("" if L == "fr" else f"{L}/") + '"/>\n' for L in LANGS)
    css = (
        # Tokens first, so every colour has a light value before anything overrides it.
        ":root{--bg:#fafaf7;--surface:#fff;--line:#e3e3dc;--ink:#0b0d10;--ink-soft:#3a3f47;"
        "--ink-mute:#6a727d;--accent:#0b5170}"
        "*{box-sizing:border-box}"
        "body{margin:0;background:var(--bg);color:var(--ink);"
        "font:16px/1.6 system-ui,-apple-system,'Segoe UI',Roboto,sans-serif}"
        "main{max-width:64rem;margin:0 auto;padding:2rem 1.25rem}"
        ".mark{display:inline-flex;align-items:center;gap:.6rem;font-weight:700}"
        ".mark img{width:30px;height:30px;border-radius:8px}"
        "h1{font-size:clamp(1.9rem,1.4rem + 2.4vw,2.9rem);letter-spacing:-.02em;margin:1.4rem 0 .6rem}"
        "h2{font-size:1.15rem;margin:2.4rem 0 .8rem}"
        ".lede{font-size:1.06rem;max-width:44rem;color:var(--ink-soft)}"
        ".hubs ul{list-style:none;padding:0;display:flex;flex-wrap:wrap;gap:.6rem;margin:1.4rem 0}"
        ".hubs a{display:inline-block;padding:.45rem .9rem;border:1px solid var(--line);"
        "border-radius:999px;text-decoration:none;color:var(--ink)}"
        ".grid{list-style:none;padding:0;margin:0;display:grid;gap:1rem;"
        "grid-template-columns:repeat(auto-fill,minmax(230px,1fr))}"
        ".card a{display:block;border:1px solid var(--line);border-radius:12px;overflow:hidden;"
        "background:var(--surface);text-decoration:none}"
        ".card img{width:100%;height:150px;object-fit:cover;display:block;background:var(--line)}"
        # Explicit colour, never `inherit`: a card sits on --surface, not on --bg, and
        # inheriting the body colour is what made these titles invisible in dark mode.
        ".ct{display:block;padding:.6rem .7rem .1rem;font-weight:600;color:var(--ink)}"
        ".cc{display:block;padding:0 .7rem .7rem;color:var(--ink-mute);font-size:.85rem}"
        "a{color:var(--accent)}"
        "footer{margin-top:3rem;padding-top:1.2rem;border-top:1px solid var(--line);"
        "color:var(--ink-mute);font-size:.85rem}"
        # Sister block — a real panel, not a footnote.
        ".sis{margin:3rem 0 0;border:1px solid var(--line);border-radius:16px;padding:1.4rem 1.5rem;"
        "background:var(--surface);display:flex;gap:1.1rem;align-items:center;flex-wrap:wrap}"
        ".sis img{width:56px;height:56px;border-radius:12px;flex:0 0 auto}"
        ".sis .txt{flex:1 1 16rem;min-width:0}"
        ".sis .k{display:block;font-size:.78rem;letter-spacing:.08em;text-transform:uppercase;"
        "color:var(--ink-mute);margin-bottom:.15rem}"
        ".sis .n{display:block;font-size:1.25rem;font-weight:700;color:var(--ink);letter-spacing:-.01em}"
        ".sis p{margin:.35rem 0 0;color:var(--ink-soft);font-size:.95rem}"
        ".sis .go{flex:0 0 auto;display:inline-block;padding:.6rem 1.1rem;border-radius:999px;"
        "background:var(--accent);color:#fff;text-decoration:none;font-weight:600}"
        # Dark overrides LAST so they win on equal specificity. This ordering was the bug:
        # the base .card a{background:#fff} used to come after the dark block and beat it,
        # leaving white cards with near-white inherited text.
        "@media(prefers-color-scheme:dark){:root{--bg:#0b0d10;--surface:#13171c;--line:#262c34;"
        "--ink:#f4f6f8;--ink-soft:#c8cfd8;--ink-mute:#8b95a1;--accent:#7ad9f5}"
        ".sis .go{color:#06202c}}")

    # Pre-launch only: the block metas follow robots.txt's FLIP-AT-LAUNCH
    # marker, the same source of truth the injector reads. Hardcoded, they
    # survived the launch flip and kept every homepage noindexed on a live site.
    _robots = os.path.join(ROOT, "robots.txt")
    _prelaunch = os.path.exists(_robots) and "FLIP-AT-LAUNCH" in open(_robots, encoding="utf-8").read()
    noindex_block = (
        '<!-- FLIP-AT-LAUNCH: the two robots metas below block this site until the real domain\n'
        '     goes live. robots.txt carries the matching marker. This homepage is generated\n'
        '     by scripts/build_home_73.py; the metas vanish when robots.txt is flipped. -->\n'
        '<meta name="robots" content="noindex,nofollow">\n'
        '<meta name="googlebot" content="noindex,nofollow">\n') if _prelaunch else ''
    return (f'<!doctype html>\n<html lang="{lang}">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            + noindex_block +
            f'<title>{E(S.SITE_NAME)} — {E(t(UI["tagline"], lang))}</title>\n'
            f'<meta name="description" content="{E(t(UI["lede"], lang))}">\n'
            f'<link rel="icon" href="/favicon.ico" sizes="any">\n{alts}'
            f'<style>{css}</style>\n</head>\n<body>\n<main>\n'
            f'<span class="mark"><img src="/mark.png" alt="" width="30" height="30">{E(S.SITE_NAME)}</span>\n'
            f'<h1>{E(t(UI["tagline"], lang))}</h1>\n'
            f'<p class="lede">{E(t(UI["lede"], lang))}</p>\n'
            f'<p><strong>{E(t(UI["count"], lang) % len(fiches))}</strong>'
            + (f' · {E(t(UI["prep"], lang))}' if _prelaunch else '') + '</p>\n'
            f'{nav}{secs}'
            f'<aside class="sis">'
            f'<img src="/img/sister/loisirs74-mark.png" alt="" width="56" height="56" loading="lazy">'
            f'<span class="txt"><span class="k">{E(t(UI["sis_kicker"], lang))}</span>'
            f'<span class="n">{E(_SIS["name"])} · {E(_SIS["dept"])}</span>'
            f'<p>{E(t(UI["sis_body"], lang))}</p></span>'
            f'<a class="go" href="{E(_SIS["url"])}" rel="noopener">{E(t(UI["sis_go"], lang))}</a>'
            f'</aside>\n'
            f'<footer>2026 · {E(S.IMPRINT)} · Tous droits réservés</footer>\n'
            '</main>\n</body>\n</html>\n')

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
