#!/usr/bin/env python3
"""build_hubs.py — regenerate the 9 basic category hubs from Json/, all locales.

For each canonical category (cascade, chateau, musee, point-de-vue, sentier,
telecabine, voie-verte, lac/plage, domaine/parc) we own a hub directory in FR
and a mirror per locale. Each hub's `<main>` block is rebuilt: every fiche
matching the filter rule is rendered as a commune-grouped card.

We DO NOT touch:
  - thematic hubs (baignade-nautisme, sport-jeux, sorties-detente,
    sensations-plein-air, parcs-jardins, que-faire) — they're curated
    cross-cuts that build_hubs would not be able to reproduce faithfully.
    Orphans falling under those hubs remain known JOB 7 fodder.
  - anything outside <main>…</main> — the intro copy, filters, FAQ, footer,
    JSON-LD are all preserved byte-faithfully.

Idempotent: two consecutive runs produce identical files.
"""
import argparse
import siteconfig  # HANDOFF-73: per-site identity
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(Path(__file__).resolve().parent))
from picture_tag import picture_tag
import locales  # noqa: E402
import assets  # noqa: E402
LOCALES = locales.PROSE_SECONDARY

# Filter rules per hub. Basic + thematic hubs that can be derived from
# category/subcategories deterministically.
# Curated cross-cuts for the détente/wellness/hands-on identity. Source of truth
# for the non-cinema/casino members of sorties-detente, so membership is declared
# here instead of being scraped from baked HTML. Cross-listing is intentional
# (a lieu may also appear in its own category hub — e.g. the two musées below).
CURATED_SORTIES = {
    # ateliers (hands-on)
    "atelier-poterie-chez-el-annecy",
    "atelier-poterie-du-prunier-thones",
    "atelier-poterie-ryokan-thones",
    # wellness
    "spa-qc-terme-chamonix",
    "spa-vitam-bien-etre-neydens",
    "thermes-saint-gervais-mont-blanc",
    # cross-cuts (kept in their own category; cross-listed here)
    "thermes-evian",                     # category=chateau (Anciens Thermes) — cross-list, not recategorised
    "musee-poterie-savoyarde-filliere",  # category=musee — sibling of the poterie ateliers
    "maison-fromage-abondance-abondance",  # category=musee — cheese atelier/visit
    # artisan/terroir batch 2 (category=divers; draft until COORDS/HERO/hours cleared)
    "cooperative-reblochon-le-farto-thones",
    "atelier-chocolat-faverges-seythenex",
    "distillerie-des-aravis-la-clusaz",
    "brasserie-artisanale-du-leman-allinges",
    "cooperative-fruitiere-mont-saleve-cruseilles",
}

HUB_FILTERS = {
    "cascades":         lambda d: d.get("category") == "cascade",
    "chateaux":         lambda d: d.get("category") == "chateau",
    "musees":           lambda d: d.get("category") == "musee",
    "points-de-vue":    lambda d: d.get("category") == "point-de-vue",
    "sentiers":         lambda d: d.get("category") == "sentier",
    "telecabines":      lambda d: d.get("category") == "telecabine",
    "stations-de-ski":  lambda d: d.get("category") == "station",
    "voies-vertes":     lambda d: d.get("category") == "voie-verte",
    "lacs-plages":      lambda d: d.get("category") in ("lac", "plage"),
    "bases-de-loisirs": lambda d: d.get("category") in ("domaine", "parc", "base-nautique", "wakepark", "accrobranche"),
    # Thematic but deterministic
    "parcs-jardins":    lambda d: d.get("category") in ("parc", "jardin"),
    "baignade-nautisme":lambda d: d.get("category") in ("aquaparc", "croisiere", "base-nautique", "wakepark"),
    "sorties-detente":  lambda d: d.get("category") in ("cinema", "casino") or d.get("slug") in CURATED_SORTIES,
    "sport-jeux":       lambda d: d.get("category") in ("bowling", "karting", "patinoire") or
                                  (isinstance(d.get("subcategories"), list) and
                                   any(s in ("sport","sport-jeux","jeu","arcade") for s in d.get("subcategories"))),
    # Curated cross-cuts: the FR hub holds the canonical curation. We
    # preserve it verbatim (filter returns False) and let build_main_block
    # re-emit the cards through fiche_card_html(d, lang, slug) so every
    # locale gets locale-prefixed URLs. Without this the non-FR hubs were
    # left frozen with FR-canonical card hrefs (audit 2026-06-13).
    "sensations-plein-air": lambda d: False,
    "que-faire":            lambda d: False,
}

# Chrome translations for the card grid
CHROME = {
    "lieu_singular":   {"fr": "lieu", "en": "place", "de": "Ort", "it": "luogo", "es": "lugar", "nl": "plek"},
    "lieu_plural":     {"fr": "lieux", "en": "places", "de": "Orte", "it": "luoghi", "es": "lugares", "nl": "plekken"},
    "free":            {"fr": "Gratuit", "en": "Free", "de": "Kostenlos", "it": "Gratis", "es": "Gratis", "nl": "Gratis"},
    "paid":            {"fr": "Payant", "en": "Paid", "de": "Kostenpflichtig", "it": "A pagamento", "es": "De pago", "nl": "Betaald"},
    "seasonal":        {"fr": "Selon saison", "en": "Seasonal", "de": "Saisonal", "it": "Stagionale", "es": "Por temporada", "nl": "Seizoensgebonden"},
    "google_maps":     {"fr": "Google Maps", "en": "Google Maps", "de": "Google Maps", "it": "Google Maps", "es": "Google Maps", "nl": "Google Maps"},
    "official_site":   {"fr": "Site officiel", "en": "Official site", "de": "Offizielle Website", "it": "Sito ufficiale", "es": "Sitio oficial", "nl": "Officiële site"},
}


def hub_locale_map(hub_dir):
    """Pull locale hub names from the FR hub's hreflang block."""
    p = ROOT / hub_dir / "index.html"
    # HANDOFF-73 phase 6: a site whose hub pages have not been rendered yet has
    # nothing to read alternates out of. Fall back to the canonical slug table
    # rather than to the FR slug — returning {"fr": ...} made every locale
    # inherit the French directory, which is how the German homepage came to
    # link /de/points-de-vue/ instead of /de/aussichtspunkte/. The table is the
    # same one the fiche pages link against, so the two cannot drift.
    if not p.exists():
        import build_lieu_page as _blp
        canon = _blp.HUB_LOCALE_SLUGS.get(hub_dir)
        if canon:
            return {l: s for l, s in canon.items()
                    if l == "fr" or l in locales.PROSE_SECONDARY}
        return {"fr": hub_dir}
    h = p.read_text(encoding="utf-8")
    m = {"fr": hub_dir}
    for mt in re.finditer(
        r'<link rel="alternate" hreflang="([^"]+)" href="' + siteconfig.SITE_URL_RE + r'/(?:([a-z]+)/)?([a-z-]+)/?"',
        h
    ):
        lang, prefix, name = mt.group(1), mt.group(2), mt.group(3)
        if lang in locales.PROSE_SECONDARY:
            m[lang] = name
    return m


# ---------------------------------------------------------------------------
# Phase 4 — description-driven photo picker
# ---------------------------------------------------------------------------

# Minimal FR stopword list — purely structural words that carry no fiche
# signal. Kept short and predictable for idempotency.
_STOPWORDS_FR = {
    "de","la","le","les","du","des","et","en","un","une","à","au","aux",
    "avec","pour","sur","par","ou","est","sont","dans","plus","aussi",
    "très","que","qui","se","il","elle","ce","ces","cette","son","sa",
    "ses","si","mais","donc","car","ne","pas","au","aux","si","non","oui",
    "comme","tout","tous","toutes","toute","quelque","entre","sous","vers",
    "depuis","après","avant","être","avoir","fait","faire","peut","aussi",
    "ainsi","leur","leurs","puis","encore","déjà",
}


def _load_photo_index():
    p = ROOT / "data" / "photo-index.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _fiche_words(d):
    """Extract description keywords from a fiche's FR text fields."""
    fr = d.get("i18n", {}).get("fr", {}) or {}
    parts = [fr.get("name", "") or "",
             fr.get("meta_description", "") or "",
             fr.get("short_intro", "") or ""]
    facts = fr.get("facts", {}) or {}
    for v in facts.values():
        if v:
            parts.append(str(v))
    text = " ".join(parts).lower()
    words = re.findall(r"[a-zà-ÿ]+", text)
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS_FR}


def pick_photo(d, photo_index, used_in_hub):
    """Hub-card photo selector.

    2026-06-15: simplified per the architecture decision — `pick_photo`
    now ALWAYS defers to `hero_image` from the fiche JSON. The single
    source of truth for which photo a fiche carries is
    `scripts/pick_generique.py` → `Json/<slug>.json.hero_image`.

    The previous Phase 4 description-keyword scoring + `used_in_hub`
    diversity tracking has been removed because it silently overrode
    `pick_generique.py`'s deliberate family routing on hub cards (a
    re-routed fiche would show its new hero on the catalog index and
    its own fiche page, but a different one on the hub card). That
    contradiction is gone.

    Signature kept stable (photo_index, used_in_hub still accepted) so
    callers in `build_main_block` continue to work; both args are now
    ignored. The returned tuple shape (src, score, basename, reason)
    is also preserved for the assignments-report capture.
    """
    hero = (d.get("hero_image") or "").strip()
    if not hero:
        return (None, None, "", "no hero in JSON")
    # Absolute URL hero (Wikimedia, Unsplash, etc.)
    if hero.startswith(("http://", "https://")):
        return (hero, None, hero.rsplit("/", 1)[-1], "json hero (url)")
    # Local path hero ("/<slug>-hero.jpg" or "/generique-X.jpg")
    if hero.startswith("/"):
        return (f"{siteconfig.BASE_URL}{hero}", None,
                hero.lstrip("/").rsplit("/", 1)[-1], "json hero (local)")
    # Bare filename (e.g. "generique-aquatique-toboggan.jpg")
    return (f"{siteconfig.BASE_URL}/{hero}", None, hero, "json hero (bare)")


# ---------------------------------------------------------------------------
# Hub <head> patching — title trim + OG block + meta description
# Source of truth for meta descriptions: data/hub-meta-descriptions.json
# (90 entries, 120-160 chars, frozen FR place names, QA-gated by Eddie)
# ---------------------------------------------------------------------------

# Hub titles are AUTHORED content, so they live in data/hub-titles.json, not
# here. {dept} / {site} come from site.config.json — that is the whole reason a
# second departement can reuse this engine instead of forking it.
def _load_hub_titles():
    p = ROOT / "data" / "hub-titles.json"
    raw = json.loads(p.read_text(encoding="utf-8"))["titles"]
    dept, site = siteconfig.DEPT_NAME, siteconfig.SITE_NAME
    return {h: {l: s.replace("{dept}", dept).replace("{site}", site)
                for l, s in v.items()} for h, v in raw.items()}


HUB_TITLE = _load_hub_titles()

OG_LOCALE_TAG = {
    "fr": "fr_FR", "en": "en_US", "de": "de_DE",
    "it": "it_IT", "es": "es_ES", "nl": "nl_NL",
}


def _load_hub_meta_descriptions():
    p = ROOT / "data" / "hub-meta-descriptions.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _attr_escape(s):
    """Escape for HTML attribute (quote=True)."""
    import html as _html
    return _html.escape(s or "", quote=True)


def patch_hub_head(html, canon, lang, slug, descriptions):
    """Replace <title>, <meta name="description">, and the OG block with
    the canonical sources of truth: HUB_TITLE constant + hub-meta-
    descriptions.json. Idempotent.
    """
    import html as _html

    new_title = HUB_TITLE.get(canon, {}).get(lang)
    if not new_title:
        return html  # safety: leave alone if no template

    new_desc = descriptions.get(canon, {}).get(lang)

    # 1) title
    html = re.sub(
        r'<title>[^<]*</title>',
        f'<title>{_html.escape(new_title, quote=False)}</title>',
        html, count=1,
    )

    # 2) meta description — replace the existing one (any attribute order)
    # Idempotency: use subn to detect whether the tag WAS present (count==0
    # means no tag found). Comparing strings would incorrectly fall through
    # when the existing tag already has the same content as the new one,
    # which would then duplicate the tag on every rebuild. Also collapse
    # any pre-existing duplicate copies into one.
    if new_desc:
        esc = _attr_escape(new_desc)
        new_meta = f'<meta content="{esc}" name="description"/>'
        desc_re = re.compile(r'<meta[^>]*name="description"[^>]*/>')
        n = len(desc_re.findall(html))
        if n == 0:
            # No description tag — insert right after the canonical <link>
            html = re.sub(
                r'(<link[^>]*rel="canonical"[^>]*/>)',
                r'\1\n' + new_meta, html, count=1,
            )
        elif n == 1:
            html = desc_re.sub(new_meta, html, count=1)
        else:
            # Multiple copies (drift from earlier builds) — collapse to one
            html = desc_re.sub(new_meta, html, count=1)
            html = desc_re.sub('', html)

    # 3) OG block (og:type, og:site_name, og:locale, og:url, og:title,
    # og:description). og:image stays where it is. Idempotent — replace
    # an existing block of our 6 tags or insert before og:image.
    url = f"{siteconfig.BASE_URL}/{slug}/" if lang == "fr" else f"{siteconfig.BASE_URL}/{lang}/{slug}/"
    og_html = (
        f'<meta property="og:type" content="website"/>\n'
        f'<meta property="og:site_name" content="{siteconfig.SITE_NAME}"/>\n'
        f'<meta property="og:locale" content="{OG_LOCALE_TAG[lang]}"/>\n'
        f'<meta property="og:url" content="{url}"/>\n'
        f'<meta property="og:title" content="{_attr_escape(new_title)}"/>\n'
        f'<meta property="og:description" content="{_attr_escape(new_desc or "")}"/>'
    )
    if 'property="og:title"' in html:
        # Replace existing 1-6 of our managed OG tags as one block
        block_re = re.compile(
            r'(?:<meta property="og:(?:type|site_name|locale|url|title|description)"[^>]*/>\s*){1,6}',
            re.IGNORECASE,
        )
        html = block_re.sub(lambda _: og_html + '\n', html, count=1)
    elif 'property="og:image"' in html:
        html = re.sub(
            r'(<meta[^>]*property="og:image"[^>]*/>)',
            og_html + r'\n\1',
            html, count=1,
        )
    else:
        # No OG at all (FR que-faire used to be in this state) —
        # inject everything including og:image before </head>.
        html = html.replace(
            '</head>',
            og_html + f'\n<meta property="og:image" content="{siteconfig.BASE_URL}/og-image.jpg"/>\n</head>',
            1,
        )
    return html


def acces_value(d):
    """Return the canonical access value for `data-acces` from JSON.

    Phase 3 single source of truth: schema_org.tariff_kind + is_free.
    Returns one of 'seasonal' | 'gratuit' | 'payant' | ''. The empty
    string means the field is intentionally absent (caller can skip
    the data-acces attribute or render it empty).
    """
    so = d.get("schema_org", {}) or {}
    if so.get("tariff_kind") == "seasonal":
        return "seasonal"
    if so.get("is_free") is True:
        return "gratuit"
    if so.get("is_free") is False:
        return "payant"
    return ""


def fiche_card_html(d, lang, slug, picked_photo=None):
    """Render one card. URL = https://loisirs74.fr[/lang]/slug; title + desc from i18n.

    `picked_photo`, when provided, overrides the fiche's hero_image as
    the displayed card photo. Carries (src, score, basename, reason) from
    pick_photo() so the card emits data-photo=basename verbatim.
    """
    i18n = d.get("i18n", {}) or {}
    loc = i18n.get(lang) or {}
    fr = i18n.get("fr") or {}
    name = loc.get("name") or fr.get("name") or slug
    if lang in STRICT_LANGS:
        # facts-first language: the card excerpt is this language's OWN
        # translated meta_description or nothing — never FR prose. The frozen
        # FR name above is the only permitted fallback.
        desc = (loc.get("meta_description") or "").strip()[:280]
    else:
        desc = (loc.get("meta_description") or fr.get("meta_description") or "").strip()[:280]
    # tariff_kind takes precedence over is_free for the visual tag.
    # "seasonal" → "Selon saison" (mixed-access lieux: site libre · visites guidées payantes)
    # otherwise → is_free True/False → Gratuit/Payant
    so = d.get("schema_org", {}) or {}
    if so.get("tariff_kind") == "seasonal":
        tag_class = "is-seasonal"
        tag_text = CHROME["seasonal"][lang]
    else:
        is_free = bool(so.get("is_free", False))
        tag_class = "is-gratuit" if is_free else "is-payant"
        tag_text = CHROME["free" if is_free else "paid"][lang]
    commune = d.get("commune", "")

    # Hero image: picker-overridden when provided (Phase 4), otherwise
    # fall back to the fiche's hero_image (Phase 3 behaviour).
    if picked_photo is not None and picked_photo[0]:
        img_src = picked_photo[0]
    else:
        hero = d.get("hero_image") or ""
        if hero.startswith(("http://", "https://", "//")):
            img_src = hero
        elif hero.startswith("/"):
            img_src = f"{siteconfig.BASE_URL}{hero}"
        elif hero:
            img_src = f"{siteconfig.BASE_URL}/{hero}"
        else:
            cat = d.get("category") or "attraction"
            img_src = f"{siteconfig.BASE_URL}/img/generique/generique-{cat}.jpg"

    if lang in STRICT_LANGS:
        alt = loc.get("hero_alt") or name   # never FR alt prose on a facts page
    else:
        alt = (loc.get("hero_alt") or fr.get("hero_alt") or name)
    lang_prefix = f"/{lang}" if lang != "fr" else ""
    fiche_url = f"{siteconfig.BASE_URL}{lang_prefix}/{slug}"
    official = d.get("official_site_url") or ""
    lat = d.get("latitude"); lon = d.get("longitude")
    from urllib.parse import quote
    # Name+commune first → Maps resolves to the real POI; a stored coord can be
    # a centroid/label point and pins off-venue. Coords = last-resort fallback.
    if name and commune:
        maps_url = f"https://www.google.com/maps/search/?api=1&amp;query={quote(name + ', ' + commune + ', ' + siteconfig.DEPT_NAME + ', France')}"
    elif lat is not None and lon is not None:
        maps_url = f"https://www.google.com/maps/search/?api=1&amp;query={lat},{lon}"
    else:
        maps_url = f"https://www.google.com/maps/search/?api=1&amp;query={quote((name or '') + ', ' + (commune or '') + ', ' + siteconfig.DEPT_NAME + ', France')}"

    actions = [
        f'<a href="{maps_url}" rel="noopener" target="_blank">{CHROME["google_maps"][lang]}</a>'
    ]
    if official:
        actions.append(
            f'<a href="{official}" rel="noopener" target="_blank">{CHROME["official_site"][lang]}</a>'
        )

    import html as html_lib
    e = lambda s: html_lib.escape(str(s or ""), quote=False)
    a = lambda s: html_lib.escape(str(s or ""), quote=True)

    # Phase 3: emit data-* attributes derived from JSON. Single source of
    # truth = the fiche JSON. Empty values mean "field intentionally
    # absent" — never invented, never inferred at render time.
    # commune is lowercased per the architecture brief; the section-level
    # data-commune attribute keeps original casing for the legacy filter.
    data_commune = (commune or "").lower()
    data_acces   = acces_value(d)
    data_lac     = d.get("lake") or ""
    data_type    = d.get("type") or ""
    # data-photo: basename of the chosen card photo. Phase 4 uses the
    # picker's own basename (so URL-encoding from img_src never leaks
    # into the attribute); Phase 3 fallback derives from img_src.
    if picked_photo is not None and picked_photo[2]:
        data_photo = picked_photo[2]
    elif img_src:
        data_photo = img_src.rsplit("/", 1)[-1]
    else:
        data_photo = ""

    card_img_extra = ' referrerpolicy="no-referrer"'
    return (
        f'<article class="card"'
        f' data-commune="{a(data_commune)}"'
        f' data-acces="{a(data_acces)}"'
        f' data-lac="{a(data_lac)}"'
        f' data-type="{a(data_type)}"'
        f' data-photo="{a(data_photo)}">\n'
        f'<a class="card-photo" href="{fiche_url}">\n'
        f'{picture_tag(img_src, alt, eager=False, extra=card_img_extra)}\n'
        f'<span class="card-tag {tag_class}">{tag_text}</span>\n'
        '</a>\n'
        '<div class="card-body">\n'
        f'<div class="card-commune"><span>{e(commune)}</span></div>'
        f'<a class="title" href="{fiche_url}">{e(name)}</a>\n'
        f'<p class="card-desc">{e(desc)}</p>\n'
        '<div class="card-actions">\n'
        + '\n'.join(actions) + '\n'
        '</div>\n'
        '</div>\n'
        '</article>'
    )


def build_main_block(fiches, lang, hub_name=None, photo_index=None, assignments=None):
    """Render the <main>…</main> content for a hub: commune-grouped cards.

    When `hub_name` is "lacs-plages", each commune-section also carries
    `data-lac="annecy|leman|petits"` derived from each fiche's `lake`
    field (the JSON source of truth). All fiches in a commune share the
    same lake by construction, so reading the first one is sufficient.

    Phase 4: when `photo_index` is provided, `pick_photo()` selects the
    card photo per fiche from the keyword-scored library, tracking
    `used_in_hub` to maximise diversity within the hub. `assignments`
    (optional list) captures (hub, slug, type, photo, score, reason)
    rows for the post-build report. Picks are computed once per hub
    (FR-locale-invariant) so all 6 locale variants render the same
    photo per card — same fiche, same picture across the site.
    """
    used_in_hub = set()
    picks = {}
    if photo_index:
        # Deterministic iteration order = render order (commune asc,
        # then FR name asc). Ensures byte-identical output across runs.
        ordered = sorted(
            fiches,
            key=lambda x: (
                (x[1].get("commune") or "?").lower(),
                (x[1].get("i18n", {}).get("fr", {}).get("name") or x[0]).lower(),
            ),
        )
        for slug, d in ordered:
            pick = pick_photo(d, photo_index, used_in_hub)
            picks[slug] = pick
            if assignments is not None and hub_name and lang == "fr":
                assignments.append((hub_name, slug, d.get("type") or "",
                                    pick[2], pick[1], pick[3]))

    by_commune = defaultdict(list)
    for slug, d in fiches:
        by_commune[d.get("commune", "?")].append((slug, d))
    # Alphabetic order of communes; cards inside commune ordered by name
    parts = ['<main>\n<div class="wrap">']
    for commune in sorted(by_commune, key=lambda c: (c.lower(), c)):
        entries = sorted(by_commune[commune],
                         key=lambda x: (x[1].get("i18n", {}).get("fr", {}).get("name", x[0]).lower()))
        n = len(entries)
        word = CHROME["lieu_singular"][lang] if n == 1 else CHROME["lieu_plural"][lang]
        # Lake attribute for lacs-plages only — derived from JSON `lake` field.
        lac_attr = ""
        if hub_name == "lacs-plages":
            first_lake = entries[0][1].get("lake")
            if first_lake:
                lac_attr = f' data-lac="{first_lake}"'
        parts.append(f'<div class="commune-section" data-commune="{commune}"{lac_attr}>')
        parts.append(f'<div class="commune-head"><h3>{commune}</h3>'
                     f'<span class="commune-count">{n} {word}</span></div>')
        parts.append('<div class="carousel">')
        for slug, d in entries:
            parts.append(fiche_card_html(d, lang, slug, picked_photo=picks.get(slug)))
        parts.append('</div>')
        parts.append('</div>')
    parts.append('</div>\n</main>')
    return "\n".join(parts)


def splice_main(html, new_main):
    """Replace existing <main>…</main> with new_main. Preserve all else."""
    m_re = re.compile(r'<main\b[^>]*>.*?</main>', re.DOTALL)
    if m_re.search(html):
        return m_re.sub(lambda _: new_main, html, count=1)
    # No existing <main>: insert before </body>
    return html.replace("</body>", new_main + "\n</body>", 1)


# Localized label for the empty-value default option of filt-commune.
TOUTES_LES_COMMUNES = {
    "fr": "Toutes les communes", "en": "All towns", "de": "Alle Gemeinden",
    "it": "Tutti i comuni", "es": "Todos los municipios", "nl": "Alle gemeenten",
}


def patch_filt_commune(html, communes, lang):
    """Replace the <select id="filt-commune"> options with exactly the
    communes present in the rendered card set (sorted alphabetically).
    Eliminates ghost commune options structurally.

    Preserves the first "all communes" option with its locale label.
    """
    sel_re = re.compile(r'(<select id="filt-commune">)(.*?)(</select>)', re.DOTALL)
    m = sel_re.search(html)
    if not m:
        return html
    default_label = TOUTES_LES_COMMUNES.get(lang, TOUTES_LES_COMMUNES["fr"])
    opts = [f'<option value="">{default_label}</option>']
    for c in sorted(communes, key=lambda c: (c.lower(), c)):
        opts.append(f'<option value="{c}">{c}</option>')
    return sel_re.sub(lambda _: m.group(1) + ''.join(opts) + m.group(3), html, count=1)


def patch_filt_access_free_toggle(html, has_free):
    """If has_free is False, hide the Gratuit/Free button via the `hidden`
    attribute (preserves DOM for idempotency). Otherwise ensure it's visible.

    Locale-agnostic: we only toggle the `hidden` attribute on the button
    that carries data-v="free".
    """
    # Match the free button with possibly a `hidden` attr already.
    btn_re = re.compile(r'<button(?P<attrs>[^>]*)data-v="free"(?P<rest>[^>]*)>')

    def repl(m):
        attrs = (m.group('attrs') or '') + (m.group('rest') or '')
        # Strip any prior hidden token (idempotency).
        attrs = re.sub(r'\s*\bhidden\b\s*', ' ', attrs).strip()
        if not has_free:
            return f'<button {attrs} data-v="free" hidden>' if attrs else f'<button data-v="free" hidden>'
        return f'<button {attrs} data-v="free">' if attrs else f'<button data-v="free">'

    return btn_re.sub(repl, html, count=1)


# -- Phase 5 ---------------------------------------------------------
# Per-hub filter JS variants. Each hub keeps its own block reflecting
# the filters present on that hub (lacs-plages adds the lake filter; the
# other 13 hubs share the common shape). They all converge on ONE rule:
# they read data-* attributes from cards (and section.dataset.lac for the
# lake filter). No PINS, no paidOf, no .card-tag class queries, no slug
# arrays. The JSON → build → data-* → filter chain is closed.


def _filter_js_common_body(has_lac, sg_label, pl_label):
    """Return the (function(){...})() body used by every hub.

    `has_lac=True` adds the lake selector + a lacMatch term to applyFilters
    (lacs-plages variant). `sg_label`/`pl_label` are the singular/plural
    count labels in the page's locale.
    """
    lac_decls = (
        "  const lacSel=document.getElementById('filt-lac');\n"
        "  let curLac='';\n"
    ) if has_lac else ""
    lac_listener = (
        "  if(lacSel)lacSel.addEventListener('change',e=>{curLac=e.target.value;applyFilters();});\n"
    ) if has_lac else ""
    lac_match_line = (
        "      const lacMatch=!curLac||sec.dataset.lac===curLac;\n"
    ) if has_lac else "      const lacMatch=true;\n"
    return (
        "(function(){\n"
        f'  const SG="{sg_label}",PL="{pl_label}";\n'
        + lac_decls +
        "  const communeSel=document.getElementById('filt-commune');\n"
        "  const accessGroup=document.getElementById('filt-access');\n"
        "  const sortSel=document.getElementById('filt-sort');\n"
        "  const countN=document.getElementById('count-n');\n"
        "  const countLabel=document.getElementById('count-label');\n"
        "  const emptyState=document.getElementById('empty-state');\n"
        "  let curCommune='',curAccess='all',curSort='commune';\n"
        "  function applyFilters(){\n"
        "    let total=0;\n"
        "    document.querySelectorAll('.commune-section').forEach(sec=>{\n"
        + lac_match_line +
        "      let vis=0;\n"
        "      sec.querySelectorAll('.card').forEach(card=>{\n"
        "        const communeMatch=!curCommune||card.dataset.commune===curCommune.toLowerCase();\n"
        "        const acc=card.dataset.acces;\n"
        "        const am=curAccess==='all'||(curAccess==='free'&&(acc==='gratuit'||acc==='seasonal'))||(curAccess==='paid'&&(acc==='payant'||acc==='seasonal'));\n"
        "        const show=lacMatch&&communeMatch&&am;\n"
        "        card.classList.toggle('hidden',!show);\n"
        "        if(show){vis++;total++;}\n"
        "      });\n"
        "      sec.classList.toggle('hidden',vis===0);\n"
        "    });\n"
        "    if(countN)countN.textContent=total;\n"
        "    if(countLabel)countLabel.textContent=total===1?SG:PL;\n"
        "    if(emptyState)emptyState.style.display=total===0?'block':'none';\n"
        "  }\n"
        "  function applySort(){ if(curSort!=='alpha')return;\n"
        "    document.querySelectorAll('.commune-section .carousel').forEach(c=>{Array.from(c.querySelectorAll('.card')).sort((a,b)=>(a.querySelector('a.title')?.textContent||'').localeCompare(b.querySelector('a.title')?.textContent||'')).forEach(x=>c.appendChild(x));}); }\n"
        + lac_listener +
        "  if(communeSel)communeSel.addEventListener('change',e=>{curCommune=e.target.value;applyFilters();});\n"
        "  if(accessGroup)accessGroup.addEventListener('click',e=>{if(e.target.tagName==='BUTTON'){accessGroup.querySelectorAll('button').forEach(b=>b.classList.remove('active'));e.target.classList.add('active');curAccess=e.target.dataset.v;applyFilters();}});\n"
        "  if(sortSel)sortSel.addEventListener('change',e=>{curSort=e.target.value;applySort();});\n"
        "  applyFilters();\n"
        "})();"
    )


# Singular / plural localized labels for the X lieux affichés count.
COUNT_LABELS = {
    "fr": ("lieu affiché",         "lieux affichés"),
    "en": ("place shown",          "places shown"),
    "de": ("Ort angezeigt",        "Orte angezeigt"),
    "it": ("luogo visualizzato",   "luoghi visualizzati"),
    "es": ("lugar mostrado",       "lugares mostrados"),
    "nl": ("plek weergegeven",     "plekken weergegeven"),
}


def build_filter_js_for_hub(hub_name, lang):
    """Return the per-hub filter JS body (no <script> wrapper)."""
    sg, pl = COUNT_LABELS.get(lang, COUNT_LABELS["fr"])
    has_lac = (hub_name == "lacs-plages")
    return _filter_js_common_body(has_lac=has_lac, sg_label=sg, pl_label=pl)


# Marker comment lives on the FR canonical hub so we can detect prior
# Phase 5 emissions and re-write idempotently.
_LACS_PLAGES_COMMENT = "// FILTERS (lake + commune + access + sort) — card-tag mechanism"
_STANDARD_COMMENT    = "// FILTERS (commune + access + sort) — card-tag mechanism"


def patch_hub_filter_js(html, hub_name, lang):
    """Replace the inline filter `<script>` block on this hub with the
    Phase 5 data-* variant. Idempotent: detects an existing applyFilters
    IIFE and swaps it for the new body; runs as no-op if no filter
    script is present (curated hubs without filters).
    """
    new_body = build_filter_js_for_hub(hub_name, lang)
    comment = _LACS_PLAGES_COMMENT if hub_name == "lacs-plages" else _STANDARD_COMMENT
    # Match every variant of the existing filter block on every hub:
    #   // FILTERS (commune + access + sort)
    #   // FILTERS (commune + access + sort) — card-tag mechanism
    #   // FILTERS (lake + commune + access + sort) — card-tag mechanism
    block_re = re.compile(
        r'// FILTERS \([^)]*\)(?:\s*—\s*card-tag mechanism)?\s*\n'
        r'\(function\(\)\{.*?applyFilters.*?\}\)\(\);',
        re.DOTALL,
    )
    if block_re.search(html):
        return block_re.sub(lambda _: comment + "\n" + new_body, html, count=1)
    return html


def load_all_json():
    """Load every Json/<slug>.json. JOB 6: skip draft fiches so they don't
    appear in any hub."""
    out = {}
    for p in sorted((ROOT / "Json").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        # 'unverified' (source-audit) is kept out of hubs exactly like draft.
        if d.get("status") in ("draft", "unverified"):
            continue
        out[p.stem] = d
    return out


def existing_hub_fiches(html_path, exclude_chrome):
    """Pull all internal fiche slugs currently linked from this hub HTML.
    These are the curated cross-references we must preserve."""
    if not html_path.exists():
        return set()
    h = html_path.read_text(encoding="utf-8")
    # Strip locale prefix for matching
    slugs = set()
    for m in re.finditer(r'href="' + siteconfig.SITE_URL_RE + r'/(?:[a-z]+/)?([a-z0-9-]+)/?"', h):
        slugs.add(m.group(1))
    return slugs - exclude_chrome


# Per-locale label for the "all categories" footer nav added when a homepage
# lacks links to one or more hubs.
ALL_CATS_LABEL = {
    "fr": "Toutes les catégories", "en": "All categories", "de": "Alle Kategorien",
    "it": "Tutte le categorie", "es": "Todas las categorías", "nl": "Alle categorieën",
}
# Display name per locale per hub (slug)
HUB_DISPLAY = {
    "cascades":          {"fr":"Cascades","en":"Waterfalls","de":"Wasserfälle","it":"Cascate","es":"Cascadas","nl":"Watervallen"},
    "chateaux":          {"fr":"Châteaux","en":"Castles","de":"Schlösser","it":"Castelli","es":"Castillos","nl":"Kastelen"},
    "musees":            {"fr":"Musées","en":"Museums","de":"Museen","it":"Musei","es":"Museos","nl":"Musea"},
    "points-de-vue":     {"fr":"Points de vue","en":"Viewpoints","de":"Aussichtspunkte","it":"Punti panoramici","es":"Miradores","nl":"Uitzichtpunten"},
    "sentiers":          {"fr":"Sentiers","en":"Trails","de":"Wanderwege","it":"Sentieri","es":"Senderos","nl":"Wandelpaden"},
    "telecabines":       {"fr":"Télécabines","en":"Cable cars","de":"Seilbahnen","it":"Funivie","es":"Teleféricos","nl":"Kabelbanen"},
    "stations-de-ski":   {"fr":"Stations de ski","en":"Ski resorts","de":"Skigebiete","it":"Stazioni sciistiche","es":"Estaciones de esquí","nl":"Skigebieden"},
    "voies-vertes":      {"fr":"Voies vertes","en":"Greenways","de":"Radwege","it":"Vie verdi","es":"Vías verdes","nl":"Fietsroutes"},
    "lacs-plages":       {"fr":"Lacs & plages","en":"Lakes","de":"Seen","it":"Laghi","es":"Lagos","nl":"Meren"},
    "bases-de-loisirs":  {"fr":"Bases de loisirs","en":"Leisure parks","de":"Freizeitparks","it":"Aree ricreative","es":"Áreas de ocio","nl":"Recreatieparken"},
    "parcs-jardins":     {"fr":"Parcs & jardins","en":"Parks & gardens","de":"Parks & Gärten","it":"Parchi & giardini","es":"Parques & jardines","nl":"Parken & tuinen"},
    "baignade-nautisme": {"fr":"Baignade & nautisme","en":"Swimming & watersports","de":"Baden & Wassersport","it":"Nuoto & sport acquatici","es":"Baño & deportes acuáticos","nl":"Zwemmen & watersport"},
    "sorties-detente":   {"fr":"Sorties & détente","en":"Outings & relax","de":"Ausflüge & Erholung","it":"Uscite & relax","es":"Salidas & relax","nl":"Uitstapjes & ontspanning"},
    "sport-jeux":        {"fr":"Sports & jeux","en":"Sports & games","de":"Sport & Spiele","it":"Sport & giochi","es":"Deportes & juegos","nl":"Sport & spelen"},
    "sensations-plein-air": {"fr":"Sensations plein air","en":"Outdoor thrills","de":"Outdoor-Nervenkitzel","it":"Brividi all'aria aperta","es":"Sensaciones al aire libre","nl":"Buitenavontuur"},
    "que-faire":         {"fr":"Que faire ?","en":"What to do","de":"Was unternehmen","it":"Cosa fare","es":"Qué hacer","nl":"Wat te doen"},
}
ALL_BASE_HUBS = list(HUB_DISPLAY.keys())

# HANDOFF-73 phase 6 — the hub ROSTER is per-site, the wording is not.
# HUB_FILTERS above is the engine's full taxonomy; a given site only owns the
# subset it has fiches for. data/hub-titles.json is that subset (it is already
# authored per site and already carries {dept}/{site} placeholders), so it is
# the natural roster. Without this, a new departement inherits the 74's
# cascades/chateaux/lacs-plages and build_hubs dies looking for pages that were
# never meant to exist here.
try:
    _roster = set(json.loads(
        (ROOT / "data" / "hub-titles.json").read_text(encoding="utf-8"))["titles"])
except Exception:
    _roster = None
if _roster:
    HUB_FILTERS = {k: v for k, v in HUB_FILTERS.items() if k in _roster}
    HUB_DISPLAY = {k: v for k, v in HUB_DISPLAY.items() if k in _roster}
    ALL_BASE_HUBS = list(HUB_DISPLAY.keys())


# Homepage "Sorties & détente" section — curated lead order (real heroes first),
# cards lifted from the locale sorties-detente hub so the homepage can't drift.
CURATED_SORTIES_LEAD = [
    "casino-imperial-palace-annecy", "spa-qc-terme-chamonix",
    "thermes-saint-gervais-mont-blanc", "thermes-evian",
    "atelier-poterie-du-prunier-thones", "cinema-pathe-annecy",
]
SORTIES_SUBLINE = {
    "fr": "Cinémas, casinos, spas et thermes, ateliers — la journée continue, même à l'abri.",
    "en": "Cinemas, casinos, spas and thermal baths, workshops — the day goes on, even indoors.",
    "de": "Kinos, Casinos, Spas und Thermen, Ateliers — der Tag geht weiter, auch im Trockenen.",
    "it": "Cinema, casinò, spa e terme, atelier — la giornata continua, anche al coperto.",
    "es": "Cines, casinos, spas y termas, talleres — el día continúa, incluso a cubierto.",
    "nl": "Bioscopen, casino's, spa's en thermen, ateliers — de dag gaat door, ook binnen.",
}
SEEALL_SVG = ('<svg fill="none" stroke="currentColor" stroke-linecap="round" '
              'stroke-linejoin="round" stroke-width="1.5" viewbox="0 0 24 24">'
              '<line x1="5" x2="19" y1="12" y2="12"></line>'
              '<polyline points="12 5 19 12 12 19"></polyline></svg>')


def _hub_cards_by_slug(hub_html):
    """slug -> its <article class="card">…</article> block from a built hub."""
    out = {}
    for m in re.finditer(r'<article class="card"[^>]*>.*?</article>', hub_html, re.S):
        block = m.group(0)
        sm = (re.search(r'href="' + siteconfig.SITE_URL_RE + r'/(?:[a-z]{2}/)?([a-z0-9-]+)"\s+class="card-photo"', block)
              or re.search(r'class="card-photo"\s+href="' + siteconfig.SITE_URL_RE + r'/(?:[a-z]{2}/)?([a-z0-9-]+)"', block))
        if sm:
            out[sm.group(1)] = block
    return out


def build_hub_itemlist(union, fr_hub, lang, hub_slug):
    """Build the hub's <head> JSON-LD ItemList from its CURRENT members, so a
    publish-flip (or dedupe) propagates into structured data. Returns a JSON
    string (indent=2). Deterministic: members are already slug-sorted in
    `union`. Replaces the previously-static, drift-prone block."""
    prefix = "" if lang == "fr" else f"/{lang}"
    hub_url = f"{siteconfig.BASE_URL}{prefix}/{hub_slug}/"
    display = HUB_DISPLAY[fr_hub][lang]
    elements = []
    for i, (slug, d) in enumerate(union, start=1):
        blk = (d.get("i18n", {}) or {})
        name = ((blk.get(lang) or {}).get("name")
                or (blk.get("fr") or {}).get("name") or slug)
        item = {
            "@type": "TouristAttraction",
            "name": name,
            "url": f"{siteconfig.BASE_URL}{prefix}/{slug}",
        }
        commune = d.get("commune")
        if commune:
            item["address"] = {
                "@type": "PostalAddress",
                "addressLocality": commune,
                "addressRegion": siteconfig.DEPT_NAME,
                "addressCountry": "FR",
            }
        lat, lng = d.get("latitude"), d.get("longitude")
        if lat is not None and lng is not None:
            item["geo"] = {"@type": "GeoCoordinates", "latitude": lat, "longitude": lng}
        if d.get("hero_image"):
            item["image"] = d["hero_image"]
        elements.append({"@type": "ListItem", "position": i, "item": item})
    obj = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "@id": hub_url + "#itemlist",
        "name": display,
        "description": f"{display} · {siteconfig.DEPT_NAME}",
        "numberOfItems": len(elements),
        "itemListOrder": "https://schema.org/ItemListOrderAscending",
        "inLanguage": lang,
        "isPartOf": {"@type": "CollectionPage", "@id": hub_url},
        "itemListElement": elements,
    }
    return json.dumps(obj, ensure_ascii=False, indent=2)


def patch_hub_itemlist(html, json_str):
    """Replace the hub's existing ItemList ld+json script with json_str.
    Leaves the other ld+json blocks (CollectionPage, FAQPage) untouched.
    Idempotent. No-op if no ItemList script is present."""
    def repl(m):
        if '"@type": "ItemList"' in m.group(1):
            return f'<script type="application/ld+json">{json_str}</script>'
        return m.group(0)
    return re.sub(r'<script type="application/ld\+json">(.*?)</script>',
                  repl, html, flags=re.S)


def patch_hub_h1(html, fr_hub, lang):
    """Single-source the hub <h1> from HUB_DISPLAY (the same string as title/nav),
    so the homepage, nav, title and h1 read identically per locale. Idempotent."""
    import html as _html
    disp = HUB_DISPLAY.get(fr_hub, {}).get(lang)
    if not disp:
        return html
    return re.sub(r'<h1([^>]*)>.*?</h1>',
                  lambda m: f'<h1{m.group(1)}>{_html.escape(disp, quote=False)}</h1>',
                  html, count=1, flags=re.S)


def patch_homepage_sorties(lang):
    """Inject (or replace) the homepage 'Sorties & détente' section in the rain
    band. Cards are lifted from the locale sorties-detente hub (URLs already
    locale-prefixed → the homepage can't drift from the hub), data-* filter
    attrs stripped to the homepage card shape. Replaces the FR ghost (ViaRhôna +
    casino); adds the section to the 5 locales (absent today). Idempotent."""
    import html as _html
    base = ROOT if lang == "fr" else ROOT / lang
    home = base / "index.html"
    if not home.exists():
        return False
    html = home.read_text(encoding="utf-8")
    # HANDOFF-73 phase 6: this band is lifted from the sorties-detente hub, which
    # is part of the 74's roster and not every site's. A site whose hub-titles.json
    # does not declare it simply has no band to build — skip rather than KeyError.
    if "sorties-detente" not in HUB_DISPLAY:
        return False
    hub_slug = hub_locale_map("sorties-detente").get(lang) or "sorties-detente"
    hub_path = base / hub_slug / "index.html"
    if not hub_path.exists():
        return False
    by_slug = _hub_cards_by_slug(hub_path.read_text(encoding="utf-8"))
    cards = []
    for slug in CURATED_SORTIES_LEAD:
        block = by_slug.get(slug)
        if block:
            cards.append(re.sub(r'<article class="card"[^>]*>', '<article class="card">', block, count=1))
    if not cards:
        return False
    prefix = f"/{lang}" if lang != "fr" else ""
    hub_url = f"{siteconfig.BASE_URL}{prefix}/{hub_slug}/"
    h2 = _html.escape(HUB_DISPLAY["sorties-detente"][lang], quote=False)
    subline = _html.escape(SORTIES_SUBLINE.get(lang, SORTIES_SUBLINE["fr"]), quote=False)
    sa = re.search(r'<a class="see-all"[^>]*>(.*?)<svg', html, re.S)
    see_label = sa.group(1).strip() if sa else "Voir tout"
    section = (
        '<section class="cat" id="sorties">\n<div class="wrap">\n<div class="cat-head">\n'
        f'<div class="cat-head-left">\n<h2>{h2}</h2>\n<p class="cat-sub">{subline}</p>\n</div>\n'
        f'<a class="see-all" href="{hub_url}">{see_label}\n{SEEALL_SVG}\n</a>\n</div>\n'
        '<div class="carousel">\n' + "\n".join(cards) + '\n</div>\n</div>\n</section>'
    )
    # remove any existing #sorties (FR ghost / prior run), collapsing the
    # surrounding blank lines to a single newline so the pass is idempotent.
    html = re.sub(r'\n*<section class="cat" id="sorties">.*?</section>\n*', '\n', html, flags=re.S)
    if '<section class="all-categories"' in html:
        html = html.replace('<section class="all-categories"', section + '\n<section class="all-categories"', 1)
    elif '</main>' in html:
        html = html.replace('</main>', section + '\n</main>', 1)
    else:
        html = re.sub(r'<footer', section + '\n<footer', html, count=1)
    home.write_text(html, encoding="utf-8")
    return True


def patch_duck(html):
    """Inject the sitewide duck easter egg before </body> if missing. Idempotent.
    Hubs/homepages are never protected fiches, so no skip needed here."""
    if '/scripts/duck.js' in html or "</body>" not in html:
        return html
    return html.replace("</body>", assets.script_tag("duck.js") + "\n</body>", 1)


def patch_homepage_duck(lang):
    base = ROOT if lang == "fr" else ROOT / lang
    home = base / "index.html"
    if not home.exists():
        return False
    html = home.read_text(encoding="utf-8")
    new = patch_duck(html)
    if new == html:
        return False
    home.write_text(new, encoding="utf-8")
    return True


def patch_homepage_nearme(lang):
    """Ensure the locale homepage loads /scripts/nearme.js — the script that
    powers the "◎ Près de moi" proximity button (#nearMe). The button ships in
    the homepage chrome, but only l74sort.js (sort-only, no geolocation) was
    included, so the button was bound to nothing. Inject nearme.js right after
    l74sort.js (or before </body>). Idempotent."""
    base = ROOT if lang == "fr" else ROOT / lang
    home = base / "index.html"
    if not home.exists():
        return False
    html = home.read_text(encoding="utf-8")
    if '/scripts/nearme.js' in html:
        return False
    tag = assets.script_tag("nearme.js")
    l74 = '<script src="/scripts/l74sort.js"></script>'
    if l74 in html:
        html = html.replace(l74, l74 + "\n" + tag, 1)
    elif "</body>" in html:
        html = html.replace("</body>", tag + "\n</body>", 1)
    else:
        return False
    home.write_text(html, encoding="utf-8")
    return True


def patch_homepage_completeness(lang):
    """Was the 'all-categories' injector → now a stripper + que-faire footer link.

    The mid-page <section class="all-categories"> duplicated the footer category
    mesh with inconsistent labels (menu "Cascades" vs block/footer "Cascades &
    gorges") — removed per Eddie. But que-faire lived ONLY in that block on the
    locale homepages (locale hub navs don't link it), so a naive strip orphaned
    es/que-hacer, de/was-unternehmen, … (reachability fail). Fix (handoff §A):
    also ensure que-faire sits in the footer category column, so the footer is
    the single complete canonical mesh and nothing orphans. Idempotent."""
    base = ROOT if lang == "fr" else ROOT / lang
    home = base / "index.html"
    if not home.exists():
        return False
    html = orig = home.read_text(encoding="utf-8")
    # 1. strip the duplicated all-categories block
    html = re.sub(r'\n*<section class="all-categories"[^>]*>.*?</section>\n*',
                  '\n', html, flags=re.DOTALL)
    # 2. footer completeness: ANY hub whose localized URL is linked from neither
    #    the footer nor the <main> body gets a localized <li> in the footer
    #    category column (after parcs-jardins). Re-homes que-faire AND
    #    voies-vertes on the locale homepages; FR (which links them via body
    #    carousels) is untouched. Immunizes any future strip against orphaning a
    #    hub. Deterministic order (ALL_BASE_HUBS) ⇒ idempotent.
    prefix = f"/{lang}" if lang != "fr" else ""
    pj_slug = hub_locale_map("parcs-jardins").get(lang) or "parcs-jardins"
    pj_url = f"{siteconfig.BASE_URL}{prefix}/{pj_slug}/"
    missing = []
    for hub in ALL_BASE_HUBS:
        slug = hub_locale_map(hub).get(lang) or hub
        if not (base / slug / "index.html").exists():
            continue
        url = f"{siteconfig.BASE_URL}{prefix}/{slug}/"
        if url not in html:
            missing.append(f'<li><a href="{url}">{HUB_DISPLAY[hub][lang]}</a></li>')
    if missing:
        html = re.sub(r'(<li><a href="' + re.escape(pj_url) + r'">[^<]*</a></li>)',
                      r'\1' + "".join(missing), html, count=1)
    if html == orig:
        return False
    home.write_text(html, encoding="utf-8")
    return True


CHROME_SLUGS = {
    "cgv","mentions-legales","mentions-legales-loisirs74-phase1",
    "signaler","signaler-info","devenir-partenaire","confidentialite",
    "politique-confidentialite-loisirs74-phase1","merci-partenaire",
    "merci-signalement","studio","404","index",
}


# ---------------------------------------------------------------------------
# HANDOFF-31 — facts-first languages (pl/pt/cs/ja/ar/he) render through THIS
# template too: one hub standard for 12 languages. The FR canonical shell is
# the chrome source (CSS, filters, footer, scripts); its prose regions
# (hub-catcher, hub-intro/seo-more, hub-faq + FAQPage JSON-LD) are OMITTED —
# never FR-filled, never machine-invented. Every localized string comes from
# reviewed vocabulary files: data/site-chrome-langs.json, data/i18n-labels.json,
# data/rich-chrome-langs.json, data/nearme-labels.json.
# The six live locales' code path above is untouched (byte-identity contract).
# ---------------------------------------------------------------------------

STRICT_LANGS = set()   # facts langs: cards never fall back to FR prose

_FACTS_OG = {"pl": "pl_PL", "pt": "pt_PT", "cs": "cs_CZ",
             "ja": "ja_JP", "ar": "ar_AR", "he": "he_IL"}

# Localized hub slugs for the facts-first languages (ASCII-folded, URL-clean),
# moved here from build_fulltree_lang (HANDOFF-31) — this template is now the
# single owner of hub-slug knowledge. ja/ar/he intentionally absent → the
# FR-canonical slug rides until a transliteration scheme is chosen.
HUB_SLUGS_FACTS = {
    "pl": {
        "cascades": "wodospady", "chateaux": "zamki", "lacs-plages": "jeziora-plaze",
        "musees": "muzea", "parcs-jardins": "parki-ogrody", "points-de-vue": "punkty-widokowe",
        "sentiers": "szlaki", "telecabines": "koleje-gondolowe", "voies-vertes": "zielone-szlaki",
        "stations-de-ski": "osrodki-narciarskie",
        "baignade-nautisme": "kapiel-sporty-wodne", "bases-de-loisirs": "parki-rekreacyjne",
        "que-faire": "co-robic", "sensations-plein-air": "emocje-plenerowe",
        "sorties-detente": "relaksujace-wycieczki", "sport-jeux": "sport-zabawa",
    },
    "pt": {
        "cascades": "cascatas", "chateaux": "castelos", "lacs-plages": "lagos-e-praias", "musees": "museus",
        "parcs-jardins": "parques-e-jardins", "points-de-vue": "miradouros", "sentiers": "trilhos",
        "telecabines": "telefericos", "voies-vertes": "vias-verdes", "stations-de-ski": "estancias-de-esqui", "baignade-nautisme": "banhos-e-desportos-aquaticos",
        "bases-de-loisirs": "parques-de-lazer", "que-faire": "o-que-fazer", "sensations-plein-air": "emocoes-ao-ar-livre",
        "sorties-detente": "passeios-relaxantes", "sport-jeux": "desporto-e-jogos",
    },
    "cs": {
        "cascades": "vodopady", "chateaux": "zamky", "lacs-plages": "jezera-a-plaze", "musees": "muzea",
        "parcs-jardins": "parky-a-zahrady", "points-de-vue": "vyhlidky", "sentiers": "stezky",
        "telecabines": "kabinkove-lanovky", "voies-vertes": "zelene-stezky", "stations-de-ski": "lyzarska-strediska", "baignade-nautisme": "koupani-a-vodni-sporty",
        "bases-de-loisirs": "rekreacni-arealy", "que-faire": "co-delat", "sensations-plein-air": "zazitky-pod-sirym-nebem",
        "sorties-detente": "vylety-pro-odpocinek", "sport-jeux": "sport-a-hry",
    },
}

_DATA_CACHE = {}


def _data(name):
    if name not in _DATA_CACHE:
        _DATA_CACHE[name] = json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))
    return _DATA_CACHE[name]


def register_facts_lang(lang):
    """Extend every per-locale chrome dict of this template with a facts-first
    language, from reviewed sources only. Idempotent. Must be called before any
    facts-lang render; the six's dict entries are never touched."""
    if lang in STRICT_LANGS:
        return
    sc = _data("site-chrome-langs.json")
    hc = sc["hub_chrome"][lang]
    il = _data("i18n-labels.json")
    rc = _data("rich-chrome-langs.json")["chrome"][lang]
    CHROME["lieu_singular"][lang] = hc["lieu_sg"]
    CHROME["lieu_plural"][lang] = hc["lieu_pl"]
    CHROME["free"][lang] = il["fact_values"]["gratuit"][lang]
    CHROME["paid"][lang] = il["fact_values"]["payant"][lang]
    CHROME["seasonal"][lang] = hc["seasonal"]
    CHROME["google_maps"][lang] = "Google Maps"
    CHROME["official_site"][lang] = rc["official_site"]
    TOUTES_LES_COMMUNES[lang] = hc["toutes_communes"]
    COUNT_LABELS[lang] = (hc["count_sg"], hc["count_pl"])
    ALL_CATS_LABEL[lang] = il["ui_chrome"]["toutes_categories"][lang]
    for hub in HUB_DISPLAY:
        HUB_DISPLAY[hub][lang] = il["hub_names"][hub][lang]
    for hub in HUB_TITLE:
        HUB_TITLE[hub][lang] = f'{il["hub_names"][hub][lang]} · {siteconfig.DEPT_NAME} · {siteconfig.SITE_NAME}'
    OG_LOCALE_TAG[lang] = _FACTS_OG[lang]
    SORTIES_SUBLINE[lang] = sc["homepage"][lang]["sorties_sub"]
    STRICT_LANGS.add(lang)


def facts_hub_descriptions(lang):
    """Composed meta descriptions for a facts lang — reviewed strings only
    (hub name + the commune meta_tail sentence); the six's hand-written
    data/hub-meta-descriptions.json entries are never machine-extended."""
    sc = _data("site-chrome-langs.json")
    il = _data("i18n-labels.json")
    tail = sc["commune_chrome"][lang]["meta_tail"]
    return {hub: {lang: f'{il["hub_names"][hub][lang]} · {siteconfig.DEPT_NAME}. {tail}'}
            for hub in HUB_DISPLAY}


def hub_slug_for(fr_hub, lang):
    """Localized hub slug for ANY visible language: HUB_SLUGS_FACTS is the
    authoritative source for the facts langs (pl/pt/cs localized; ja/ar/he
    fall through to FR-canonical); the six's slugs come from the FR shell's
    hreflang cluster, exactly like hub_locale_map."""
    if lang in HUB_SLUGS_FACTS:
        return HUB_SLUGS_FACTS[lang].get(fr_hub, fr_hub)
    if lang == "fr":
        return fr_hub
    p = ROOT / fr_hub / "index.html"
    h = p.read_text(encoding="utf-8")
    m = re.search(
        rf'<link rel="alternate" hreflang="{lang}" href="{siteconfig.SITE_URL_RE}/(?:[a-z]+/)?([a-z0-9-]+)/?"', h)
    return m.group(1) if m else fr_hub


def _nearme_button_html(lang):
    lab = _data("nearme-labels.json")[lang]
    a = lambda s: _attr_escape(str(s))
    return (
        f'<button class="near-me" id="nearMe" style="margin-left:auto"'
        f' data-default="{a(lab["def"])}" data-loading="{a(lab["loading"])}"'
        f' data-on="{a(lab["on"])}" data-off="{a(lab["off"])}"'
        f' data-results-title="{a(lab["title"])}" data-results-sub="{a(lab["sub"])}"'
        f' data-cta="{a(lab["cta"])}" data-km="{a(lab["km"])}">{a(lab["def"])}</button>'
    )


def _patch_collectionpage_jsonld(html, display, lang):
    """Localize the CollectionPage ld+json (name + inLanguage). Idempotent."""
    def repl(m):
        block = m.group(0)
        if '"@type": "CollectionPage"' not in block and '"@type":"CollectionPage"' not in block:
            return block
        block = re.sub(r'"inLanguage":\s*"[a-z-]+"', f'"inLanguage": "{lang}"', block)
        block = re.sub(r'"name":\s*"[^"]*"', f'"name": {json.dumps(display, ensure_ascii=False)}', block, count=1)
        return block
    return re.sub(r'<script type="application/ld\+json">.*?</script>', repl, html, flags=re.S)


def render_facts_hub_page(fr_hub, lang, union, communes_in_hub, has_free):
    """One full hub page for a facts-first language, from the FR canonical
    shell: same CSS, same filters, same footer, same scripts — prose omitted."""
    import html as _html
    sc = _data("site-chrome-langs.json")
    il = _data("i18n-labels.json")
    hc = sc["hub_chrome"][lang]
    hp = sc["homepage"][lang]
    cc = sc["commune_chrome"][lang]
    accueil = il["ui_chrome"]["accueil"][lang]
    display = HUB_DISPLAY[fr_hub][lang]
    lang_slug = hub_slug_for(fr_hub, lang)
    url = f"{siteconfig.BASE_URL}/{lang}/{lang_slug}/"

    html = (ROOT / fr_hub / "index.html").read_text(encoding="utf-8")

    # --- language + direction -------------------------------------------------
    import locales as _loc
    dir_attr = ' dir="rtl"' if _loc.DIR.get(lang) == "rtl" else ""
    html = re.sub(r'<html lang="fr">', f'<html lang="{lang}"{dir_attr}>', html, count=1)

    # --- prose OUT (strict): catcher, intro/seo-more, FAQ + FAQPage JSON-LD ---
    html = re.sub(r'\n?<p class="hub-catcher">.*?</p>', '', html, flags=re.S)
    html = re.sub(r'\n?<section[^>]*class="hub-intro"[^>]*>.*?</section>', '', html, flags=re.S)
    html = re.sub(r'\n?<section[^>]*class="hub-faq"[^>]*>.*?</section>', '', html, flags=re.S)
    html = re.sub(r'<script type="application/ld\+json">.*?</script>\n?',
                  lambda m: '' if '"FAQPage"' in m.group(0) else m.group(0),
                  html, flags=re.S)

    # --- head: canonical self-reference (hreflang cluster kept — it is already
    # the complete 12-language set and identical across the cluster) ----------
    html = re.sub(r'<link rel="canonical" href="[^"]*">',
                  f'<link rel="canonical" href="{url}">', html, count=1)

    # --- header: brand link, near-me labels, language picker ------------------
    html = html.replace(f'<a class="brand" href="{siteconfig.BASE_URL}/">',
                        f'<a class="brand" href="{siteconfig.BASE_URL}/{lang}/">', 1)
    html = re.sub(r'<!--nearme:start-->.*?<!--nearme:end-->',
                  lambda _m: f'<!--nearme:start-->{_nearme_button_html(lang)}<!--nearme:end-->',
                  html, flags=re.S, count=1)
    alts = {l: u for l, u in
            re.findall(r'<link rel="alternate" hreflang="([a-z]+)" href="([^"]+)"', html)
            if l != "x-default"}
    ends = _loc.endonyms(_loc.VISIBLE)  # isolation-ok: picker endonyms for the full roster
    cur_attr = 'aria-current="true" '
    menu = "".join(
        f'<a {cur_attr if l == lang else ""}href="{alts.get(l, siteconfig.BASE_URL + "/")}" '
        f'hreflang="{l}">{ends[l]}</a>' for l in _loc.VISIBLE)  # isolation-ok: roster nav
    html = re.sub(
        r'<details class="lang-picker">\s*<summary>.*?</summary>\s*<div class="lang-menu">.*?</div>\s*</details>',
        f'<details class="lang-picker">\n<summary><b>{lang.upper()}</b> · {_html.escape(cc["langues"], quote=False)}</summary>\n'
        f'<div class="lang-menu">\n{menu}\n</div>\n</details>',
        html, flags=re.S, count=1)

    # --- breadcrumb ------------------------------------------------------------
    html = re.sub(
        r'(<nav aria-label="breadcrumb" class="crumb">\s*)<a href="' + siteconfig.SITE_URL_RE + r'/">[^<]*</a>(\s*<span class="sep">/</span>\s*)<b>[^<]*</b>',
        lambda m: f'{m.group(1)}<a href="{siteconfig.BASE_URL}/{lang}/">{_html.escape(accueil, quote=False)}</a>'
                  f'{m.group(2)}<b>{_html.escape(display, quote=False)}</b>',
        html, count=1)

    # --- filter bar static strings --------------------------------------------
    e = lambda s: _html.escape(s, quote=False)
    for old, new in [
        ('<span id="count-label">lieux affichés</span>', f'<span id="count-label">{e(hc["count_pl"])}</span>'),
        ('<span>Filtres</span>', f'<span>{e(hc["filtres"])}</span>'),
        ('<span>Commune</span>', f'<span>{e(hc["commune"])}</span>'),
        ('<span>Accès</span>', f'<span>{e(hc["acces"])}</span>'),
        ('<span>Tri</span>', f'<span>{e(hc["tri"])}</span>'),
        ('data-v="all">Tous<', f'data-v="all">{e(hc["tous"])}<'),
        ('data-v="free">Gratuit<', f'data-v="free">{e(CHROME["free"][lang])}<'),
        ('data-v="paid">Payant<', f'data-v="paid">{e(CHROME["paid"][lang])}<'),
        ('<option value="commune">Par commune</option>', f'<option value="commune">{e(hc["par_commune"])}</option>'),
        ('<b>Aucun résultat</b>', f'<b>{e(hc["no_results"])}</b>'),
    ]:
        html = html.replace(old, new)
    html = re.sub(r'Aucun lieu ne correspond aux filtres actifs\.[^<]*',
                  e(hc["no_match"]), html)

    # --- footer: blurb + column heads + category links + language + legal -----
    foot = re.search(r'<footer class="site">.*?</footer>', html, re.S)
    if foot:
        f_html = foot.group(0)
        f_html = re.sub(r'(<h4>' + siteconfig.SITE_NAME_RE + r'</h4>\s*<p>).*?(</p>)',
                        lambda m: m.group(1) + e(hp["foot_blurb"]) + m.group(2), f_html, flags=re.S)
        f_html = f_html.replace('<h4>Catégories</h4>', f'<h4>{e(hp["foot_categories_h3"])}</h4>')
        f_html = f_html.replace('<h4>Langue</h4>', f'<h4>{e(hp["foot_language_h3"])}</h4>')
        f_html = f_html.replace('<h4>Mentions</h4>', f'<h4>{e(hp["foot_legal_h3"])}</h4>')
        # category column: FR hub URL -> this language's hub URL + reviewed label
        def _cat_link(m):
            path = m.group(1)
            if path == "":
                return f'<a href="{siteconfig.BASE_URL}/{lang}/">'
            if (ROOT / path / "index.html").exists() and path in HUB_DISPLAY:
                return f'<a href="{siteconfig.BASE_URL}/{lang}/{hub_slug_for(path, lang)}/">'
            if (ROOT / path / "index.html").exists():
                return f'<a href="{siteconfig.BASE_URL}/{lang}/{hub_slug_for(path, lang)}/">'
            return m.group(0)
        f_html = re.sub(r'<a href="' + siteconfig.SITE_URL_RE + r'/([a-z0-9-]*)/?">', _cat_link, f_html)
        for fr_lbl, key in [("Mentions légales", "legal"), ("Confidentialité", "privacy"),
                            ("CGV", "terms"), ("Signaler une info", "report"),
                            ("Devenir partenaire", "partner")]:
            f_html = f_html.replace(f'>{fr_lbl}</a>', f'>{e(hp["legal_labels"][key])}</a>')
        for hub, disp in HUB_DISPLAY.items():
            f_html = f_html.replace(f'>{e(disp["fr"])}</a>', f'>{e(disp[lang])}</a>')
        # footer labels that are not HUB_DISPLAY entries (reviewed sources)
        cl = sc["category_labels"][lang]
        for fr_lbl, new_lbl in [("Plages", cl["plage"]),
                                ("Attractions &amp; loisirs", hp["sec_h2"]["attraction"]),
                                ("Divers", hp["sec_h2"]["divers"]),
                                ("Sentiers", cl["sentier"]),
                                ("Bases de loisirs", cl["domaine"]),
                                ("Points de vue", cl["point-de-vue"]),
                                ("Télécabines", cl["telecabine"]),
                                ("Musées", cl["musee"]),
                                ("Voies vertes", cl["voie-verte"])]:
            f_html = f_html.replace(f'>{fr_lbl}</a>', f'>{e(new_lbl)}</a>')
        # legal links stay on the FR root pages — the strict rule from the fiche
        # footer (no /xx/cgv 404s); only their labels are localized above.
        html = html.replace(foot.group(0), f_html, 1)
        # language column: one entry per visible language, this page's own alternates
        new_ul = "<ul>" + "".join(
            f'<li><a href="{alts.get(l, siteconfig.BASE_URL + "/")}" hreflang="{l}">{ends[l]}</a></li>'
            for l in _loc.VISIBLE) + "</ul>"  # isolation-ok: roster nav
        html = re.sub(
            r'<ul>(?:\s*<li><a href="[^"]*" hreflang="[a-z-]+">[^<]*</a></li>\s*)+</ul>',
            lambda _m: new_ul, html, count=1)

    # --- the standard splice pipeline (same calls the six get) ----------------
    html = splice_main(html, build_main_block(union, lang, hub_name=fr_hub))
    html = patch_filt_commune(html, communes_in_hub, lang)
    html = patch_filt_access_free_toggle(html, has_free)
    html = patch_hub_filter_js(html, fr_hub, lang)
    html = patch_hub_head(html, fr_hub, lang, lang_slug, facts_hub_descriptions(lang))
    html = patch_hub_h1(html, fr_hub, lang)
    html = patch_hub_itemlist(html, build_hub_itemlist(union, fr_hub, lang, lang_slug))
    html = _patch_collectionpage_jsonld(html, display, lang)
    html = patch_duck(html)
    return html


def build_facts_lang_hubs(lang, fiches=None):
    """Render the 15 hub pages of a facts-first language under
    /<lang>/<localized-slug>/. Membership logic is byte-for-byte the six's
    (same union rule, same ordering). Returns the list of (fr_hub, lang_slug)."""
    register_facts_lang(lang)
    if fiches is None:
        fiches = load_all_json()
    fiches = {s: d for s, d in fiches.items()
              if s not in ("chez-nous-a-la-plage", "chalet-du-tornet")}
    all_hub_names = set()
    for fr_hub in HUB_FILTERS:
        all_hub_names.update(hub_locale_map(fr_hub).values())
    excludes = CHROME_SLUGS | all_hub_names
    import locales as _loc
    written = []
    for fr_hub, filt in HUB_FILTERS.items():
        existing = existing_hub_fiches(ROOT / fr_hub / "index.html", excludes)
        existing_in_json = {s for s in existing if s in fiches}
        matched = {s for s, d in fiches.items() if filt(d) or fr_hub in (d.get("hubs") or [])}
        union_slugs = existing_in_json | matched
        if not union_slugs:
            continue
        union = [(s, fiches[s]) for s in sorted(union_slugs)]
        communes_in_hub = {fiches[s].get("commune") for s in union_slugs if fiches[s].get("commune")}
        has_free = any(
            fiches[s].get("schema_org", {}).get("is_free") is True
            or fiches[s].get("schema_org", {}).get("tariff_kind") == "seasonal"
            for s in union_slugs)
        lang_slug = hub_slug_for(fr_hub, lang)
        out = ROOT / lang / lang_slug / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_facts_hub_page(fr_hub, lang, union, communes_in_hub, has_free),
                       encoding="utf-8")
        written.append((fr_hub, lang_slug))
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated FR hub names")
    args = ap.parse_args()
    only = set(args.only.split(",")) if args.only else None

    fiches = load_all_json()
    photo_index = _load_photo_index()
    hub_descriptions = _load_hub_meta_descriptions()
    assignments = []  # Phase 4: capture (hub, slug, type, photo, score, reason)
    # Hub names (FR + locales) of EVERY hub on disk, so we don't treat them as fiches
    all_hub_names = set()
    for fr_hub in HUB_FILTERS:
        all_hub_names.update(hub_locale_map(fr_hub).values())
    # Also include any other dirs with index.html (thematic hubs we don't rebuild)
    for d in ROOT.iterdir():
        if d.is_dir() and (d / "index.html").exists() and d.name not in {
            "_site","__pycache__","reports","scripts","Json","api","content",
            ".well-known", *locales.ALL_SUBDIR_LANGS
        }:
            all_hub_names.add(d.name)
    excludes = CHROME_SLUGS | all_hub_names

    regen = 0
    summary = []
    for fr_hub, filt in HUB_FILTERS.items():
        if only and fr_hub not in only: continue
        locale_names = hub_locale_map(fr_hub)
        # Build the union: existing curated slugs ∪ slugs matching the filter.
        existing = existing_hub_fiches(ROOT / fr_hub / "index.html", excludes)
        existing_in_json = {s for s in existing if s in fiches}
        # Membership = category/curated filter OR an explicit multi-hub opt-in
        # (top-level `hubs: [<hub-slug>]`). Additive: a lieu keeps its own
        # category hub and also appears in every hub it lists. Absent/empty
        # `hubs` ⇒ identical behaviour to before.
        matched_slugs = {s for s, d in fiches.items()
                         if filt(d) or fr_hub in (d.get("hubs") or [])}
        union_slugs = existing_in_json | matched_slugs
        added = sorted(matched_slugs - existing_in_json)
        union = [(s, fiches[s]) for s in sorted(union_slugs)]
        # Communes actually present in the rendered card set (source of
        # truth for filt-commune options). Used by patch_filt_commune to
        # eliminate ghost options structurally.
        communes_in_hub = {fiches[s].get("commune") for s in union_slugs if fiches[s].get("commune")}
        # Does the hub have any free fiche? Drives whether the Gratuit
        # access-toggle button is rendered hidden. Seasonal counts as
        # free-eligible (the JS filter treats seasonal as both).
        has_free = any(
            fiches[s].get("schema_org", {}).get("is_free") is True
            or fiches[s].get("schema_org", {}).get("tariff_kind") == "seasonal"
            for s in union_slugs
        )
        for lang in locales.PROSE:
            hub_name = locale_names.get(lang)
            if not hub_name: continue
            dir_path = (ROOT if lang == "fr" else ROOT / lang) / hub_name
            if not dir_path.exists():
                print(f"  ! [{lang}] {hub_name}/ does not exist; skipping")
                continue
            p = dir_path / "index.html"
            html = p.read_text(encoding="utf-8")
            new_main = build_main_block(union, lang, hub_name=fr_hub,
                                        photo_index=photo_index,
                                        assignments=assignments)
            new_html = splice_main(html, new_main)
            # Filter chrome patches (apply to every hub, every locale).
            new_html = patch_filt_commune(new_html, communes_in_hub, lang)
            new_html = patch_filt_access_free_toggle(new_html, has_free)
            # Phase 5: per-hub filter JS reads card data-* attributes
            # only. Per-hub variant kept (lacs-plages has filt-lac, the
            # other 13 don't). Idempotent.
            new_html = patch_hub_filter_js(new_html, fr_hub, lang)
            # Hub head: title (≤60 chars), meta description (120-160 from
            # data/hub-meta-descriptions.json), OG block (7 tags). All
            # idempotent. Single source of truth for descriptions = the
            # JSON file under data/.
            new_html = patch_hub_head(new_html, fr_hub, lang, hub_name, hub_descriptions)
            # JOB §5a: single-source the <h1> from HUB_DISPLAY (== title/nav),
            # fixing de/nl/en drift across all 15 hubs.
            new_html = patch_hub_h1(new_html, fr_hub, lang)
            # Regenerate the <head> ItemList from current members (publish-flip /
            # dedupe now propagate into structured data).
            new_html = patch_hub_itemlist(
                new_html, build_hub_itemlist(union, fr_hub, lang, hub_name))
            new_html = patch_duck(new_html)
            if new_html != html:
                p.write_text(new_html, encoding="utf-8")
                regen += 1
        summary.append((fr_hub, len(existing_in_json), len(union_slugs), len(added)))
    print(f"\n{'hub':<22} {'prev':<6} {'cur':<6} {'added':<6}")
    for h, prev, cur, added in summary:
        print(f"  {h:<22} {prev:<6} {cur:<6} +{added:<5}")
    print(f"\nregenerated: {regen}/{len(HUB_FILTERS)*6}")

    # Step 2: patch each locale homepage so every hub directory on disk is
    # linked. Closes the orphan gap that came from voies-vertes /
    # sorties-detente being absent from the locale-homepage nav.
    print("\npatching homepages: Sorties & détente section + hub-completeness:")
    for lang in locales.PROSE:
        sortie = patch_homepage_sorties(lang)
        changed = patch_homepage_completeness(lang)
        nearme = patch_homepage_nearme(lang)
        patch_homepage_duck(lang)
        bits = []
        if sortie: bits.append("+sorties")
        if changed: bits.append("-all-categories +que-faire-footer")
        if nearme: bits.append("+nearme.js")
        print(f"  [{lang}] {' '.join(bits) if bits else 'already complete'}")

    # Phase 4: emit the photo-assignment report so Eddie can spot-check
    # the picks. Sorted by (hub, slug) for deterministic output.
    if assignments:
        from collections import Counter
        per_hub_photo = defaultdict(Counter)
        for hub, slug, typ, photo, score, reason in assignments:
            per_hub_photo[hub][photo] += 1
        max_repeat = {hub: c.most_common(1)[0][1] for hub, c in per_hub_photo.items()}
        lines = [
            "# Phase 4 — photo assignments (gate artifact)",
            "",
            f"**Date**: 2026-06-14",
            f"**Total assignments**: {len(assignments)} (one per (hub × slug) on the FR canonical hub)",
            "",
            "## Per-hub diversity",
            "",
            "| hub | fiches | distinct photos | max repeat of one photo |",
            "|---|---:|---:|---:|",
        ]
        for hub in sorted(per_hub_photo):
            n_fiches = sum(per_hub_photo[hub].values())
            n_distinct = len(per_hub_photo[hub])
            lines.append(f"| `{hub}` | {n_fiches} | {n_distinct} | {max_repeat[hub]} |")
        lines += [
            "",
            "## Per-fiche assignments",
            "",
            "| hub | slug | type | photo | score | reason |",
            "|---|---|---|---|---:|---|",
        ]
        for row in sorted(assignments):
            hub, slug, typ, photo, score, reason = row
            score_s = str(score) if score is not None else "—"
            lines.append(f"| `{hub}` | `{slug}` | `{typ}` | `{photo}` | {score_s} | {reason} |")
        (ROOT / "reports" / "photo-assignments.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"\nwrote reports/photo-assignments.md  ({len(assignments)} rows)")


if __name__ == "__main__":
    main()
