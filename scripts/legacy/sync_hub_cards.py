#!/usr/bin/env python3
"""Sync hub-page card membership with lieux.json after the Phase B
reclassification (commit 3c7e3c5 moved 29 fiches out of 'attraction').

Scope (5 + 2 = 7 files):
- /attractions/, /en/attractions/, /de/attraktionen/, /it/attrazioni/,
  /es/atraciones/  →  remove every <article class="card"> whose slug is
  no longer in categories.attraction per lieux.json. Drop any
  commune-section that ends up with zero cards. Update count claims in
  the <title>, <meta name="description">, and <p class="meta"> blocks.
- /bases-de-loisirs/ (FR only)  →  append a new commune-grouped section
  holding the 15 reclassified fiches now tagged 'domaine'.
- /divers/ (FR only)  →  append a new commune-grouped section holding
  the 14 reclassified fiches now tagged 'divers'.

Locale /bases-de-loisirs/ and /divers/ are out of scope. They were
already pre-Phase-B thin (because their template lineage uses simpler
localized chrome that doesn't accept arbitrary card synthesis without
per-locale copy work).

The 'ghost' slugs that live in the FR /attractions/ hub but not in
lieux.json (escape-game-*, lancer-de-hache-*, etc., 28 of them) are
left alone — they predate Phase B.

Implementation: uses BeautifulSoup for HTML-safe surgery — regex
removal of nested <article>/<div> blocks would risk corrupting the
markup.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from bs4 import BeautifulSoup

REPO = Path(__file__).resolve().parent.parent
LIEUX = json.loads((REPO / "lieux.json").read_text(encoding="utf-8"))["lieux"]
BY_SLUG = {l["slug"]: l for l in LIEUX}

# Which hub each lieux.json category should appear in.
CAT_TO_HUB = {
    "attraction": "attractions",
    "domaine": "bases-de-loisirs",
    "parc": "bases-de-loisirs",
    "divers": "divers",
    "lac": "lacs",
    "plage": "plages",
    "cascade": "cascades",
    "point-de-vue": "points-de-vue",
    "sentier": "sentiers",
    "voie-verte": "voies-vertes",
    "telecabine": "telecabines",
    "musee": "musees",
    "chateau": "chateaux",
}

# Locale-specific path of each hub.
HUB_PATH = {
    "fr": {"attractions": "attractions", "bases-de-loisirs": "bases-de-loisirs", "divers": "divers",
           "lacs": "lacs", "plages": "plages", "cascades": "cascades",
           "points-de-vue": "points-de-vue", "sentiers": "sentiers", "voies-vertes": "voies-vertes",
           "telecabines": "telecabines", "musees": "musees", "chateaux": "chateaux"},
    "en": {"attractions": "en/attractions", "bases-de-loisirs": "en/leisure-parks", "divers": "en/other",
           "lacs": "en/lakes", "plages": "en/beaches", "cascades": "en/waterfalls",
           "points-de-vue": "en/viewpoints", "sentiers": "en/trails", "voies-vertes": "en/greenways",
           "telecabines": "en/cable-cars", "musees": "en/museums", "chateaux": "en/castles"},
    "de": {"attractions": "de/attraktionen", "bases-de-loisirs": "de/freizeitparks", "divers": "de/sonstiges",
           "lacs": "de/seen", "plages": "de/straende", "cascades": "de/wasserfaelle",
           "points-de-vue": "de/aussichtspunkte", "sentiers": "de/wanderwege", "voies-vertes": "de/radwege",
           "telecabines": "de/seilbahnen", "musees": "de/museen", "chateaux": "de/schloesser"},
    "it": {"attractions": "it/attrazioni", "bases-de-loisirs": "it/aree-recreative", "divers": "it/altro",
           "lacs": "it/laghi", "plages": "it/spiagge", "cascades": "it/cascate",
           "points-de-vue": "it/punti-panoramici", "sentiers": "it/sentieri", "voies-vertes": "it/vie-verdi",
           "telecabines": "it/funivie", "musees": "it/musei", "chateaux": "it/castelli"},
    "es": {"attractions": "es/atraciones", "bases-de-loisirs": "es/areas-de-ocio", "divers": "es/otros",
           "lacs": "es/lagos", "plages": "es/playas", "cascades": "es/cascadas",
           "points-de-vue": "es/miradores", "sentiers": "es/senderos", "voies-vertes": "es/vias-verdes",
           "telecabines": "es/telefericos", "musees": "es/museos", "chateaux": "es/castillos"},
}

# Plural words by language: (singular, plural, communes_singular, communes_plural).
PLURAL = {
    "fr": ("lieu", "lieux", "commune", "communes"),
    "en": ("place", "places", "commune", "communes"),
    "de": ("Ort", "Orte", "Gemeinde", "Gemeinden"),
    "it": ("luogo", "luoghi", "comune", "comuni"),
    "es": ("lugar", "lugares", "comuna", "comunas"),
}

LABELS = {
    "fr": {"free": "Gratuit", "paid": "Payant", "route": "Itinéraire", "site": "Site officiel"},
    "en": {"free": "Free", "paid": "Paid", "route": "Directions", "site": "Official site"},
    "de": {"free": "Kostenlos", "paid": "Kostenpflichtig", "route": "Route", "site": "Offizielle Website"},
    "it": {"free": "Gratis", "paid": "A pagamento", "route": "Indicazioni", "site": "Sito ufficiale"},
    "es": {"free": "Gratis", "paid": "De pago", "route": "Ruta", "site": "Sitio oficial"},
}

SLUG_RE = re.compile(
    r'https://loisirs74\.fr/(?:[a-z]{2}/)?([a-z0-9-]+)'
)


def canonical_slugs(hub: str) -> set[str]:
    out = set()
    for lieu in LIEUX:
        for cat in lieu.get("categories", []):
            if CAT_TO_HUB.get(cat) == hub:
                out.add(lieu["slug"])
                break
    return out


def article_slug(article) -> str | None:
    a = article.find("a", class_="card-photo")
    if not a or not a.get("href"):
        return None
    m = SLUG_RE.search(a["href"])
    return m.group(1) if m else None


def per_fiche(slug: str) -> dict:
    p = REPO / "Json" / f"{slug}.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def synth_locale_card_html(slug: str, lang: str) -> str:
    """Card for a locale hub. Same shape as the FR card (<img> when
    hero_image present, placeholder SVG fallback) + locale chrome labels.
    Use FR name if no locale name available."""
    lieu = BY_SLUG.get(slug, {})
    fiche = per_fiche(slug)
    name = (lieu.get("i18n", {}).get(lang, {}).get("name")
            or fiche.get("i18n", {}).get(lang, {}).get("name")
            or lieu.get("i18n", {}).get("fr", {}).get("name")
            or slug.replace("-", " ").title())
    commune = (lieu.get("i18n", {}).get("fr", {}).get("commune")
               or fiche.get("commune") or "")
    desc = (fiche.get("i18n", {}).get(lang, {}).get("meta_description")
            or fiche.get("i18n", {}).get("fr", {}).get("meta_description") or "")
    if len(desc) > 200:
        cut = desc.rfind(" ", 0, 200)
        if cut > 0:
            desc = desc[:cut].rstrip(".,;:") + "."
    is_free = bool(lieu.get("is_free", False))
    tag_class = "is-gratuit" if is_free else "is-payant"
    tag_text = LABELS[lang]["free"] if is_free else LABELS[lang]["paid"]
    from urllib.parse import quote
    map_q = quote(f"{name}, {commune}, Haute-Savoie", safe="")
    map_url = f"https://www.google.com/maps/dir/?api=1&amp;destination={map_q}"
    site = fiche.get("official_site_url") or ""
    actions = (f'<a href="{map_url}" rel="noopener" target="_blank">{LABELS[lang]["route"]}</a>')
    if site:
        actions += f'\n<a href="{site}" rel="noopener" target="_blank">{LABELS[lang]["site"]}</a>'

    # Photo slot: real <img> when hero_image present, placeholder otherwise.
    # Mark with data-generique="true" when src points at /generique-*.jpg so
    # the CSS overlay surfaces the badge; otherwise the attribute is absent.
    hero = fiche.get("hero_image")
    if hero:
        if not hero.startswith(("http://", "https://", "/")):
            hero = "/" + hero
        alt_text = (fiche.get("i18n", {}).get(lang, {}).get("hero_alt")
                    or fiche.get("i18n", {}).get("fr", {}).get("hero_alt")
                    or name).replace('"', '&quot;')
        is_generic = hero.lstrip("/").startswith("generique-")
        if is_generic:
            import re as _re
            cm = _re.match(r"generique-([a-z0-9-]+?)(?:-[a-z0-9-]+)?\.\w+$", hero.lstrip("/"))
            gen_cat = cm.group(1) if cm else "attraction"
            gen_attr = f' data-generique="true" data-generique-cat="{gen_cat}"'
        else:
            gen_attr = ""
        photo_inner = (f'<img alt="{alt_text}"{gen_attr} loading="lazy" '
                       f'referrerpolicy="no-referrer" src="{hero}"/>')
    else:
        photo_inner = ('<div class="placeholder"><svg fill="none" stroke="currentColor" '
                       'stroke-linecap="round" stroke-linejoin="round" stroke-width="2" '
                       'viewbox="0 0 24 24"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z">'
                       '</path><circle cx="12" cy="10" r="3"></circle></svg></div>')

    return (
        f'<article class="card">\n'
        f'<a class="card-photo" href="https://loisirs74.fr/{lang}/{slug}">\n'
        f'{photo_inner}\n'
        f'<span class="card-tag {tag_class}">{tag_text}</span>\n'
        f'</a>\n'
        f'<div class="card-body">\n'
        f'<div class="card-commune"><span>{commune}</span></div>'
        f'<a class="title" href="https://loisirs74.fr/{lang}/{slug}">{name}</a>\n\n'
        f'<p class="card-desc">{desc}</p>\n'
        f'<div class="card-actions">\n{actions}\n</div>\n'
        f'</div>\n'
        f'</article>'
    )


def synth_fr_card_html(slug: str) -> str:
    lieu = BY_SLUG.get(slug, {})
    fiche = per_fiche(slug)
    name = (lieu.get("i18n", {}).get("fr", {}).get("name")
            or fiche.get("i18n", {}).get("fr", {}).get("name")
            or slug.replace("-", " ").title())
    commune = (lieu.get("i18n", {}).get("fr", {}).get("commune")
               or fiche.get("commune") or "")
    hero = fiche.get("hero_image", f"/{slug}-hero.jpg")
    if hero and not hero.startswith(("http://", "https://", "/")):
        hero = "/" + hero
    alt = fiche.get("i18n", {}).get("fr", {}).get("hero_alt") or name
    desc = fiche.get("i18n", {}).get("fr", {}).get("meta_description") or ""
    if len(desc) > 200:
        cut = desc.rfind(" ", 0, 200)
        if cut > 0:
            desc = desc[:cut].rstrip(".,;:") + "."
    is_free = bool(lieu.get("is_free", False))
    tag_class = "is-gratuit" if is_free else "is-payant"
    tag_text = LABELS["fr"]["free"] if is_free else LABELS["fr"]["paid"]
    from urllib.parse import quote
    map_q = quote(f"{name}, {commune}, Haute-Savoie", safe="")
    map_url = f"https://www.google.com/maps/dir/?api=1&amp;destination={map_q}"
    site = fiche.get("official_site_url") or ""
    actions = f'<a href="{map_url}" rel="noopener" target="_blank">Itinéraire</a>'
    if site:
        actions += f'\n<a href="{site}" rel="noopener" target="_blank">Site officiel</a>'
    # Mark with data-generique only when src is /generique-*.jpg
    is_generic = hero.lstrip("/").startswith("generique-") if hero else False
    if is_generic:
        import re as _re
        cm = _re.match(r"generique-([a-z0-9-]+?)(?:-[a-z0-9-]+)?\.\w+$", hero.lstrip("/"))
        gen_cat = cm.group(1) if cm else "attraction"
        gen_attr = f' data-generique="true" data-generique-cat="{gen_cat}"'
    else:
        gen_attr = ""
    return (
        f'<article class="card">\n'
        f'<a class="card-photo" href="https://loisirs74.fr/{slug}">\n'
        f'<img alt="{alt}"{gen_attr} loading="lazy" src="{hero}"/>\n'
        f'<span class="card-tag {tag_class}">{tag_text}</span>\n'
        f'</a>\n'
        f'<div class="card-body">\n'
        f'<div class="card-commune"><span>{commune}</span></div>'
        f'<a class="title" href="https://loisirs74.fr/{slug}">{name}</a>\n\n'
        f'<p class="card-desc">{desc}</p>\n'
        f'<div class="card-actions">\n{actions}\n</div>\n'
        f'</div>\n'
        f'</article>'
    )


def commune_section_html(commune: str, cards_html: list[str], lang: str = "fr") -> str:
    word_singular, word_plural, _, _ = PLURAL[lang]
    label = word_singular if len(cards_html) == 1 else word_plural
    return (
        f'<div class="commune-section" data-commune="{commune}">\n'
        f'<div class="commune-head"><h3>{commune}</h3>'
        f'<span class="commune-count">{len(cards_html)} {label}</span></div>\n'
        f'<div class="carousel">\n' + "\n".join(cards_html) + "\n</div>\n</div>\n"
    )


def update_counts(soup: BeautifulSoup, lang: str, total: int, communes: int) -> None:
    sing, plural, com_sing, com_plural = PLURAL[lang]
    lieux_word = sing if total == 1 else plural
    communes_word = com_sing if communes == 1 else com_plural

    # <p class="meta"><b>N lieux</b><span class="dot">·</span><span>M communes</span></p>
    for p in soup.find_all("p", class_="meta"):
        b = p.find("b")
        if b and re.match(r'^\d+\s+\S+', b.get_text()):
            b.string = f"{total} {lieux_word}"
        spans = p.find_all("span")
        for sp in spans:
            t = sp.get_text()
            if re.match(r'^\d+\s+\S+', t) and "·" not in t:
                sp.string = f"{communes} {communes_word}"
                break
        break

    # <meta name="description" content="... · N lieux.">
    md = soup.find("meta", attrs={"name": "description"})
    if md and md.get("content"):
        md["content"] = re.sub(
            r'·\s*\d+\s+\S+',
            f'· {total} {lieux_word}',
            md["content"],
            count=1,
        )


def remove_stale_articles(soup: BeautifulSoup, keep_slugs: set[str]) -> int:
    removed = 0
    for article in list(soup.find_all("article", class_="card")):
        slug = article_slug(article)
        if slug and slug in BY_SLUG and slug not in keep_slugs:
            article.decompose()
            removed += 1
    return removed


def drop_empty_commune_sections(soup: BeautifulSoup) -> int:
    dropped = 0
    for section in list(soup.find_all("div", class_="commune-section")):
        if not section.find("article", class_="card"):
            section.decompose()
            dropped += 1
    return dropped


def update_commune_counts(soup: BeautifulSoup, lang: str) -> None:
    word_singular, word_plural, _, _ = PLURAL[lang]
    for section in soup.find_all("div", class_="commune-section"):
        cards = section.find_all("article", class_="card")
        n = len(cards)
        head = section.find("div", class_="commune-head")
        if not head:
            continue
        count_span = head.find("span", class_="commune-count")
        if not count_span:
            continue
        label = word_singular if n == 1 else word_plural
        count_span.string = f"{n} {label}"


def update_filter_dropdown(soup: BeautifulSoup) -> None:
    """The FR /attractions/ filter bar holds a <select id="filt-commune"> with
    one <option> per commune in the hub. Sync it with the post-edit commune set."""
    select = soup.find("select", id="filt-commune")
    if not select:
        return
    # Keep the first 'all communes' option, replace the rest with current set.
    options = select.find_all("option")
    if not options:
        return
    first = options[0]  # keep '' value
    # remove all others
    for o in options[1:]:
        o.decompose()
    communes_present = sorted({
        s.get("data-commune", "")
        for s in soup.find_all("div", class_="commune-section")
    } - {""})
    for c in communes_present:
        opt = soup.new_tag("option", value=c)
        opt.string = c
        first.insert_after(opt)
        first = opt  # maintain order


def add_cards_to_hub(soup: BeautifulSoup, lang: str, slugs_to_add: list[str]) -> int:
    """Insert new commune-section blocks (one per commune) before the closing
    </main> ... </div>. Uses raw HTML synthesis then parses for insertion."""
    if not slugs_to_add:
        return 0
    by_commune: dict[str, list[str]] = defaultdict(list)
    for slug in slugs_to_add:
        lieu = BY_SLUG.get(slug, {})
        commune = (lieu.get("i18n", {}).get("fr", {}).get("commune")
                   or per_fiche(slug).get("commune") or "Haute-Savoie")
        card_html = synth_fr_card_html(slug) if lang == "fr" else synth_locale_card_html(slug, lang)
        by_commune[commune].append(card_html)

    # Build a single HTML string of new commune-sections.
    blocks = []
    for commune in sorted(by_commune):
        blocks.append(commune_section_html(commune, by_commune[commune], lang=lang))
    new_html = "\n".join(blocks)

    # Find insertion point: end of <main><div class="wrap">…</div></main>.
    main = soup.find("main")
    if not main:
        return 0
    wrap = main.find("div", class_="wrap")
    target = wrap or main
    # Parse new fragment and append.
    frag = BeautifulSoup(new_html, "html.parser")
    for child in list(frag.children):
        target.append(child)
    return len(slugs_to_add)


# Hubs where we should both REMOVE stale and ADD missing — only the
# Phase-B-impacted attraction family. Other hubs are additive-only so we
# don't disturb intentional cross-listings (lacs ↔ plages share fiches).
REMOVE_ALSO = {"attractions", "bases-de-loisirs", "divers"}


def patch_hub(lang: str, hub: str, log: list[str]) -> None:
    rel = HUB_PATH[lang][hub]
    path = REPO / rel / "index.html"
    if not path.exists():
        log.append(f"  [skip] {path} — missing")
        return
    keep = canonical_slugs(hub)
    html = path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")

    pre = len(soup.find_all("article", class_="card"))
    removed = 0
    dropped = 0
    if hub in REMOVE_ALSO:
        removed = remove_stale_articles(soup, keep)
        dropped = drop_empty_commune_sections(soup)

    # Add cards for slugs that should be here but aren't.
    existing = {article_slug(a) for a in soup.find_all("article", class_="card")}
    existing.discard(None)
    to_add = sorted([s for s in (keep - existing)
                     if s and (REPO / "Json" / f"{s}.json").exists()])
    added = add_cards_to_hub(soup, lang, to_add)

    update_commune_counts(soup, lang)
    post = len(soup.find_all("article", class_="card"))
    communes = len({a.get("data-commune", "")
                    for a in soup.find_all("div", class_="commune-section")} - {""})
    update_counts(soup, lang, post, communes)
    update_filter_dropdown(soup)

    path.write_text(str(soup), encoding="utf-8")
    log.append(
        f"  {rel}: {pre} → {post} cards "
        f"(removed {removed}, added {added}, dropped {dropped} empty sections, {communes} communes)"
    )


def main() -> None:
    log: list[str] = []
    log.append("=== /attractions/ family — remove reclassified + add ===")
    for lang in ["fr", "en", "de", "it", "es"]:
        patch_hub(lang, "attractions", log)
    log.append("=== /bases-de-loisirs/ family — add reclassified ===")
    for lang in ["fr", "en", "de", "it", "es"]:
        patch_hub(lang, "bases-de-loisirs", log)
    log.append("=== /divers/ family — add reclassified ===")
    for lang in ["fr", "en", "de", "it", "es"]:
        patch_hub(lang, "divers", log)
    log.append("=== other hubs — additive only (no removals) ===")
    for hub in ["lacs", "plages", "cascades", "points-de-vue", "sentiers",
                "voies-vertes", "telecabines", "musees", "chateaux"]:
        for lang in ["fr", "en", "de", "it", "es"]:
            patch_hub(lang, hub, log)
    print("\n".join(log))
    (REPO / "scripts" / "sync_hub_cards.log").write_text(
        "\n".join(log) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
