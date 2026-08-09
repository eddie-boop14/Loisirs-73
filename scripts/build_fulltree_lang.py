#!/usr/bin/env python3
"""build_fulltree_lang.py — ORCHESTRATION ONLY (HANDOFF-31).

One site, one standard: a facts-first language's full tree renders through the
SAME templates the six live locales use —

    fiches    → build_lieu_page.build_page   (strict-prose mode: missing prose
                is OMITTED, never FR-filled; facts from the reviewed vocabulary)
    hubs      → build_hubs.build_facts_lang_hubs  (FR shell chrome + this
                template's card grid, prose regions omitted)
    communes  → build_communes.build_for_lang    (same chrome lift + backlinks)
    homepage  → build_homepage_lang.render_homepage (EN structural twin)

The parallel shell()/CSS/card mini-templates that used to live here are GONE.
This module only decides WHAT to render and stages the language-clean data
(vocabulary facts, composed meta descriptions) each fiche needs.

Run: python3 scripts/build_fulltree_lang.py pt
"""
import glob
import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import locales  # noqa: E402
import build_hubs as H  # noqa: E402
import build_communes as BC  # noqa: E402
import build_homepage_lang as HL  # noqa: E402
import build_pilot_langs as P  # noqa: E402  (V + CATEGORY_DESCRIPTOR: reviewed vocabulary)

PROTECTED = {"chez-nous-a-la-plage", "chalet-du-tornet"}
V = P.V


def load_fiches():
    out = []
    for fp in sorted(glob.glob(os.path.join(ROOT, "Json", "*.json"))):
        d = json.loads(open(fp, encoding="utf-8").read())
        slug = d.get("slug") or os.path.basename(fp)[:-5]
        if slug in PROTECTED or d.get("status") not in (None, "published"):
            continue
        d["slug"] = slug
        out.append(d)
    return out


def prose_complete(d, lang):
    """True when the fiche carries this language's batch-translated prose
    (HANDOFF-25 write-back). meta_title is the marker: the validators enforce
    full key parity vs the EN source before anything is written, so its
    presence implies the whole prose set is present and validated."""
    blk = (d.get("i18n") or {}).get(lang) or {}
    return bool(blk.get("meta_title"))


def _vocab_facts(d, lang):
    """A language-clean facts dict for the rich page's 'At a glance' panel.

    The batch translates PROSE only — the six originals carry hand-translated
    facts dicts, a new language does not. Letting the panel fall back to FR
    would print free-text FR ('Toute l'année · Été pour les jardins') on a pt
    page. Instead we mirror the retired facts shell's policy: language-
    independent values + reviewed-vocabulary enums ONLY; free-text FR fact
    values are omitted, never leaked. In-memory only — never written back."""
    fr = (d.get("i18n") or {}).get("fr", {}).get("facts") or {}
    so = d.get("schema_org") or {}
    out = {}
    commune = d.get("commune") or fr.get("commune")
    if commune:
        out["commune"] = commune
    dur = fr.get("duration")
    if dur:
        # Only genuinely language-neutral durations pass ("1 h 30 – 2 h 30",
        # "45 min", "2h A/R"). Some source durations carry FR free text
        # ("5–10 min depuis parking (été)") — that is prose, so it is OMITTED,
        # never leaked. (Also fixes the pt pages that shipped with it.)
        words = re.findall(r"[A-Za-zÀ-ÿ]+", dur)
        if all(w.lower() in {"h", "min", "mn", "a", "r", "km"} for w in words):
            out["duration"] = dur
    # A genuine per-language tarif SENTENCE (not FR) may exist — e.g. the
    # station forfait prose written in this exact language. That is a real
    # translation, not an FR scaffold, so it passes the language-clean bar and
    # is preferred over the bare price_from number (Eddie's phone test: the
    # Arabic page must show the Arabic tarif sentence, not just "44 €").
    loc_tarif = ((d.get("i18n") or {}).get(lang) or {}).get("facts", {}).get("tarif")
    price_from = d.get("price_from")
    cur = {"EUR": "€"}.get(d.get("price_currency"), d.get("price_currency") or "")
    if isinstance(loc_tarif, str) and loc_tarif.strip():
        out["tarif"] = loc_tarif
    elif isinstance(price_from, (int, float)) and price_from > 0:
        out["tarif"] = f"{price_from:.2f}".replace(".", ",") + " " + cur
    elif so.get("is_free") is True:
        out["tarif"] = V("fact_values", "gratuit", lang)
    elif so.get("is_free") is False:
        out["tarif"] = V("fact_values", "payant", lang)
    if str(fr.get("pavillon_bleu_2026", "")).strip().upper() == "OUI":
        out["pavillon_bleu_2026"] = V("fact_values", "oui", lang)
    return out


def render_fiche_rich(d, lang):
    """Every facts-lang fiche renders through build_lieu_page — the same page
    the six originals get. build_lieu_page is import-gated on locales.PROSE,
    so this orchestrator enables the one language explicitly; partner
    placements stay OUT (their byte-faithful snapshot contract covers only the
    six live languages). Strict mode: missing prose is omitted, never FR."""
    import build_lieu_page as LP
    if lang not in LP.SUPPORTED_LANGS:
        LP.SUPPORTED_LANGS.append(lang)
    if lang not in LP.HUB_LOCALE_SLUGS.get("cascades", {}):
        # Breadcrumb + JSON-LD hub links must point at THIS tree's localized
        # hub dirs (/pt/cascatas/), not the FR slugs (dead /pt/cascades/ —
        # the link-integrity 404 class). Slugs from build_hubs (the single
        # owner since HANDOFF-31), labels from the reviewed vocabulary.
        # Languages absent from HUB_SLUGS_FACTS (ja/ar/he) keep the
        # FR-canonical fallback — their trees use FR hub dirs.
        for fr_slug in LP.HUB_LOCALE_SLUGS:
            loc = H.HUB_SLUGS_FACTS.get(lang, {}).get(fr_slug)
            if loc:
                LP.HUB_LOCALE_SLUGS[fr_slug][lang] = loc
            lbl = V("hub_names", fr_slug, lang)
            if lbl:
                LP.HUB_LOCALE_LABELS[fr_slug][lang] = lbl
    if lang not in LP._REL_LABELS:
        # Related-carousel labels from REVIEWED sources only (rich chrome +
        # the facts vocabulary) — never hand-invented, never FR fallback.
        ch = LP.CHROME
        LP._REL_LABELS[lang] = {
            "kicker": ch["k_see_also"][lang], "h2": ch["k_see_also"][lang],
            "lead": "",
            "free": V("fact_values", "gratuit", lang),
            "paid": V("fact_values", "payant", lang),
            "route": ch["directions"][lang], "site": ch["official_site"][lang],
        }
    d["i18n"][lang]["facts"] = _vocab_facts(d, lang)
    # HANDOFF-35: acces_pmr now travels — the renderer localizes the short
    # status (reviewed fact_values.pmr_*) and suppresses the FR free-text
    # detail off-fr until i18n.<lang>.acces_pmr_detail exists. The old blunt
    # `d["acces_pmr"] = None` here hid the whole row on facts langs.
    html = LP.build_page(d, lang, include_partners=False, fr_prose_fallback=False)
    return html, LP.LAST_FALLBACK_FIELDS


def write(path, html):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)


def main():
    lang = sys.argv[1] if len(sys.argv) > 1 else "pl"
    assert locales.status(lang) == "published", \
        f"{lang} must be status:published in data/languages.json before full-tree render"
    fiches = load_fiches()
    out = os.path.join(ROOT, lang)
    # Clean slate: a facts language's whole subtree is owned by this
    # orchestrator, so wipe it before rendering — no stale page can survive.
    if os.path.isdir(out):
        shutil.rmtree(out)

    # 1. fiches — ONE render path: build_lieu_page for every fiche. Prose-
    # complete fiches render rich; prose-less fiches render strict (prose
    # sections OMITTED). Title + meta description fall back inside
    # build_lieu_page to the HANDOFF-32 facts-derived builders (localized
    # type + frozen name + commune + tariff + per-language meta_tail) —
    # unique per fiche per language, never a bare shared commune string.
    n_f = n_rich = 0
    fallback_counts = {}
    for d in fiches:
        if prose_complete(d, lang):
            n_rich += 1
        else:
            d.setdefault("i18n", {}).setdefault(lang, {})
        html, fb = render_fiche_rich(d, lang)
        write(os.path.join(out, d["slug"] + ".html"), html)
        for f in fb:
            fallback_counts[f] = fallback_counts.get(f, 0) + 1
        n_f += 1

    # 2. hubs — the real hub template (FR shell chrome, localized slugs)
    hubs = H.build_facts_lang_hubs(lang)

    # 3. communes + reciprocal backlinks — the real commune template
    n_c, bstats = BC.build_for_lang(lang)

    # 4. homepage — the real homepage template (EN structural twin)
    write(os.path.join(out, "index.html"), HL.render_homepage(lang))

    print(f"build_fulltree_lang[{lang}]: {n_f} fiches ({n_rich} rich, {n_f - n_rich} strict-facts) "
          f"+ {len(hubs)} hubs + {n_c} communes + 1 homepage — all through the real templates")
    print(f"  backlinks: {bstats}")
    if fallback_counts:
        print(f"  fiche FR-fallback fields: {sorted(fallback_counts.items())} "
              "(name is frozen-FR by design)")


if __name__ == "__main__":
    main()
