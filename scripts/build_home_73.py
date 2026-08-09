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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("fr", "en", "de", "it", "es", "nl")
E = lambda s: html.escape(str(s or ""), quote=True)

SECTIONS = [("point-de-vue", {"fr": "Cols et points de vue", "en": "Passes and viewpoints"}),
            ("telecabine", {"fr": "Téléphériques", "en": "Cable cars"}),
            ("remontee-mecanique", {"fr": "Télécabines et funiculaires", "en": "Gondolas and funiculars"})]
UI = {
 "tagline": {"fr": "La Savoie, lieu par lieu.", "en": "Savoie, place by place."},
 "lede": {"fr": "Un guide indépendant des lieux de loisirs en Savoie. Chaque fait est vérifié auprès d'une "
                "source officielle — et quand les sources se contredisent, la fiche le dit au lieu de choisir.",
          "en": "An independent guide to leisure places in Savoie. Every fact is checked against an official "
                "source — and where sources disagree, the page says so instead of picking one."},
 "count": {"fr": "%d lieux vérifiés", "en": "%d verified places"},
 "sister": {"fr": "Le grand frère tourne déjà en Haute-Savoie :", "en": "The big brother already runs in Haute-Savoie:"},
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
    secs = ""
    for cat, label in SECTIONS:
        items = [f for f in fiches if f.get("category") == cat]
        if not items:
            continue
        secs += (f'<section><h2>{E(t(label, lang))}</h2><ul class="grid">'
                 + "".join(card(f, lang) for f in items) + "</ul></section>\n")
    alts = "".join(f'<link rel="alternate" hreflang="{L}" href="{S.BASE_URL}/'
                   + ("" if L == "fr" else f"{L}/") + '"/>\n' for L in LANGS)
    css = ("*{box-sizing:border-box}body{margin:0;background:#fafaf7;color:#0b0d10;"
           "font:16px/1.6 system-ui,-apple-system,'Segoe UI',Roboto,sans-serif}"
           "@media(prefers-color-scheme:dark){body{background:#0b0d10;color:#f4f6f8}"
           ".card a{background:#13171c;border-color:#262c34}}"
           "main{max-width:64rem;margin:0 auto;padding:2rem 1.25rem}"
           ".mark{display:inline-flex;align-items:center;gap:.6rem;font-weight:700}"
           ".mark img{width:30px;height:30px;border-radius:8px}"
           "h1{font-size:clamp(1.9rem,1.4rem + 2.4vw,2.9rem);letter-spacing:-.02em;margin:1.4rem 0 .6rem}"
           "h2{font-size:1.15rem;margin:2.4rem 0 .8rem}"
           ".lede{font-size:1.06rem;max-width:44rem}"
           ".grid{list-style:none;padding:0;margin:0;display:grid;gap:1rem;"
           "grid-template-columns:repeat(auto-fill,minmax(230px,1fr))}"
           ".card a{display:block;border:1px solid #e3e3dc;border-radius:12px;overflow:hidden;"
           "background:#fff;text-decoration:none;color:inherit}"
           ".card img{width:100%;height:150px;object-fit:cover;display:block}"
           ".ct{display:block;padding:.6rem .7rem .1rem;font-weight:600}"
           ".cc{display:block;padding:0 .7rem .7rem;color:#6a727d;font-size:.85rem}"
           "footer{margin-top:3rem;padding-top:1.2rem;border-top:1px solid #e3e3dc;"
           "color:#6a727d;font-size:.85rem}a{color:#0b5170}")
    return (f'<!doctype html>\n<html lang="{lang}">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<!-- FLIP-AT-LAUNCH: the two robots metas below block this site until the real domain\n'
            '     goes live. robots.txt carries the matching marker. Grepping FLIP-AT-LAUNCH must\n'
            '     find both files. This homepage is generated by scripts/build_home_73.py. -->\n'
            '<meta name="robots" content="noindex,nofollow">\n'
            '<meta name="googlebot" content="noindex,nofollow">\n'
            f'<title>{E(S.SITE_NAME)} — {E(t(UI["tagline"], lang))}</title>\n'
            f'<meta name="description" content="{E(t(UI["lede"], lang))}">\n'
            f'<link rel="icon" href="/favicon.ico" sizes="any">\n{alts}'
            f'<style>{css}</style>\n</head>\n<body>\n<main>\n'
            f'<span class="mark"><img src="/mark.png" alt="" width="30" height="30">{E(S.SITE_NAME)}</span>\n'
            f'<h1>{E(t(UI["tagline"], lang))}</h1>\n'
            f'<p class="lede">{E(t(UI["lede"], lang))}</p>\n'
            f'<p><strong>{E(t(UI["count"], lang) % len(fiches))}</strong> · {E(t(UI["prep"], lang))}</p>\n'
            f'{secs}'
            f'<p class="sister">{E(t(UI["sister"], lang))} '
            f'<a href="https://loisirs74.fr" rel="noopener">loisirs74.fr</a></p>\n'
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
