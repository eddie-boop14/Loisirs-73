#!/usr/bin/env python3
"""build_homepage_lang.py — HANDOFF-31: a facts-first language's homepage
through the REAL homepage template.

The EN locale homepage is the structural twin every non-FR locale shares
(hero + weather-reactive cat sections + cards + footer + STR i18n dict).
This module transforms it per language: lang/dir attributes, head, the STR
dict, every static chrome string, per-card links/alt/excerpt — all from
reviewed vocabulary (data/site-chrome-langs.json + i18n-labels + Json/).

Strict prose rule: a card's excerpt is the language's OWN translated
meta_description or nothing; alt falls back to the frozen FR name only.
Legal links route to the FR root pages (same rule as fiche/hub chrome —
no /xx/legal 404s). The six live locales are never touched by this module.

Run: python3 scripts/build_homepage_lang.py <lang>   (writes <lang>/index.html)
"""
import json
import siteconfig  # HANDOFF-73: per-site identity
import re
import sys
import html as _html
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import locales  # noqa: E402
import build_hubs as H  # noqa: E402

BASE = siteconfig.BASE_URL

_LEGAL_FR_ROOT = [  # (key in legal_labels, FR root page — the strict chrome routing)
    ("legal", "mentions-legales"),
    ("privacy", "confidentialite"),
    ("terms", "cgv"),
    ("report", "signaler"),
    ("partner", "devenir-partenaire"),
]

_OG = {"pl": "pl_PL", "pt": "pt_PT", "cs": "cs_CZ", "ja": "ja_JP", "ar": "ar_AR", "he": "he_IL"}


def e(s):
    return _html.escape(s, quote=False)


def a(s):
    return _html.escape(str(s or ""), quote=True)


def _legal_lis(labels):
    return "\n          ".join(
        f'<li><a href="{BASE}/{slug}">{e(labels[key])}</a></li>'
        for key, slug in _LEGAL_FR_ROOT)


def _en_hub_slug_map():
    """en-slug -> fr_hub, from each FR hub's own hreflang block."""
    out = {}
    for fr_hub in H.HUB_DISPLAY:
        if (ROOT / fr_hub / "index.html").exists():
            out[H.hub_slug_for(fr_hub, "en")] = fr_hub
    return out


def _load_fiche(slug, _cache={}):
    if slug not in _cache:
        p = ROOT / "Json" / f"{slug}.json"
        _cache[slug] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    return _cache[slug]


def render_homepage(lang):
    H.register_facts_lang(lang)
    sc = H._data("site-chrome-langs.json")
    il = H._data("i18n-labels.json")
    rc = H._data("rich-chrome-langs.json")["chrome"][lang]
    hp = sc["homepage"][lang]
    en = sc["homepage"]["en"]
    cc = sc["commune_chrome"][lang]

    html = (ROOT / "en" / "index.html").read_text(encoding="utf-8")

    # --- html tag + direction --------------------------------------------------
    dir_attr = ' dir="rtl"' if locales.DIR.get(lang) == "rtl" else ""
    html = re.sub(r'<html lang="en"([^>]*)>', rf'<html lang="{lang}"\1{dir_attr}>', html, count=1)

    # --- head -------------------------------------------------------------------
    html = re.sub(r'<title>.*?</title>', f'<title>{e(hp["title"])}</title>', html, count=1)
    html = re.sub(r'(<meta content=")[^"]*(" name="description")',
                  lambda m: m.group(1) + a(hp["meta_description"]) + m.group(2), html, count=1)
    html = re.sub(r'(<meta name="description" content=")[^"]*(")',
                  lambda m: m.group(1) + a(hp["meta_description"]) + m.group(2), html, count=1)
    html = re.sub(r'<link rel="canonical" href="[^"]*"\s*/?>',
                  f'<link rel="canonical" href="{BASE}/{lang}/">', html, count=1)
    html = re.sub(r'<link href="[^"]*" rel="canonical"\s*/?>',
                  f'<link href="{BASE}/{lang}/" rel="canonical"/>', html, count=1)
    html = re.sub(r'(<meta property="og:locale" content=")[^"]*(")',
                  lambda m: m.group(1) + _OG[lang] + m.group(2), html)
    html = re.sub(r'(<meta content=")[^"]*(" property="og:locale")',
                  lambda m: m.group(1) + _OG[lang] + m.group(2), html)
    html = re.sub(r'(property="og:url" content=")[^"]*(")',
                  lambda m: m.group(1) + f"{BASE}/{lang}/" + m.group(2), html)
    html = re.sub(r'(content=")[^"]*(" property="og:url")',
                  lambda m: m.group(1) + f"{BASE}/{lang}/" + m.group(2), html)
    html = re.sub(r'(property="og:title" content=")[^"]*(")',
                  lambda m: m.group(1) + a(hp["title"]) + m.group(2), html)
    html = re.sub(r'(content=")[^"]*(" property="og:title")',
                  lambda m: m.group(1) + a(hp["title"]) + m.group(2), html)
    html = re.sub(r'(property="og:description" content=")[^"]*(")',
                  lambda m: m.group(1) + a(hp["meta_description"]) + m.group(2), html)
    html = re.sub(r'(content=")[^"]*(" property="og:description")',
                  lambda m: m.group(1) + a(hp["meta_description"]) + m.group(2), html)
    html = html.replace('"inLanguage": "en"', f'"inLanguage": "{lang}"')
    html = html.replace('"inLanguage":"en"', f'"inLanguage":"{lang}"')

    # --- the STR i18n dict (weather narrator, buttons, JS-rendered footer) ------
    str_dict = dict(hp["str"])
    str_dict["foot_mentions_lis"] = _legal_lis(hp["legal_labels"])
    html = re.sub(r'var STR=\{.*?\};',
                  lambda _m: "var STR=" + json.dumps(str_dict, ensure_ascii=False) + ";",
                  html, count=1, flags=re.S)

    # --- static chrome strings (anchored to their EN markup) -------------------
    html = re.sub(r'(<div class="kicker" id="kicker">).*?(</div>)',
                  lambda m: m.group(1) + hp["kicker_badge"] + m.group(2), html, count=1, flags=re.S)
    html = re.sub(r'(<div class="wrap hero-content">.*?)<h1>.*?</h1>',
                  lambda m: m.group(1) + "<h1>" + hp["h1_html"] + "</h1>", html, count=1, flags=re.S)
    html = re.sub(r'(<p class="lede"[^>]*>).*?(</p>)',
                  lambda m: m.group(1) + hp["lede_html"] + m.group(2), html, count=1, flags=re.S)
    for sec_id, en_h2 in en["sec_h2"].items():
        html = html.replace(f'<h2>{en_h2}</h2>', f'<h2>{hp["sec_h2"][sec_id]}</h2>')
    html = html.replace(f'<p class="cat-sub">{en["sorties_sub"]}</p>',
                        f'<p class="cat-sub">{e(hp["sorties_sub"])}</p>')
    for key in ("wband_out", "wband_in", "wband_mix"):
        html = html.replace(f'<span class="weather-band">{en["str"][key]}</span>',
                            f'<span class="weather-band">{e(hp["str"][key])}</span>')
    # static header controls (JS only re-labels them on state change)
    html = html.replace(f'<button class="near-me" id="nearMe">{en["str"]["btn_near"]}</button>',
                        f'<button class="near-me" id="nearMe">{e(hp["str"]["btn_near"])}</button>')
    for bid, key in (("bAuto", "btn_auto"), ("bSun", "btn_sun"), ("bRain", "btn_rain")):
        html = re.sub(rf'(<button[^>]*id="{bid}"[^>]*>)' + re.escape(en["str"][key]) + r'(</button>)',
                      lambda m, k=key: m.group(1) + e(hp["str"][k]) + m.group(2), html, count=1)
    html = re.sub(r'(<a class="see-all"[^>]*>)\s*' + re.escape(en["see_all"]),
                  lambda m: m.group(1) + e(hp["see_all"]), html)

    # --- footer -----------------------------------------------------------------
    foot = re.search(r'<footer class="site">.*?</footer>', html, re.S).group(0)
    new_foot = foot
    new_foot = re.sub(r'(<h3>' + siteconfig.SITE_NAME_RE + r'</h3>\s*<p>).*?(</p>)',
                      lambda m: m.group(1) + e(hp["foot_blurb"]) + m.group(2), new_foot, flags=re.S)
    new_foot = new_foot.replace(f'<h3>{en["foot_categories_h3"]}</h3>', f'<h3>{e(hp["foot_categories_h3"])}</h3>')
    new_foot = new_foot.replace(f'<h3>{en["foot_language_h3"]}</h3>', f'<h3>{e(hp["foot_language_h3"])}</h3>')
    new_foot = new_foot.replace(f'<h3>{en["foot_legal_h3"]}</h3>', f'<h3>{e(hp["foot_legal_h3"])}</h3>')
    # legal column -> FR root pages, translated labels (BEFORE the /en/ rewrite)
    new_foot = re.sub(
        r'<ul>\s*(?:<li><a href="' + siteconfig.SITE_URL_RE + r'/en/(?:legal|privacy|terms|report|partner)">[^<]*</a></li>\s*)+</ul>',
        "<ul>\n          " + _legal_lis(hp["legal_labels"]) + "\n        </ul>",
        new_foot, count=1)
    # language column -> the full visible roster, homepage equivalents
    ends = locales.endonyms(locales.VISIBLE)  # isolation-ok: roster nav
    lang_lis = "\n ".join(
        '<li><a href="{u}" hreflang="{l}">{n}</a></li>'.format(
            u=(BASE + "/") if l == "fr" else f"{BASE}/{l}/", l=l, n=ends[l])
        for l in locales.VISIBLE)  # isolation-ok: roster nav
    new_foot = re.sub(
        r'<ul>\s*(?:<li><a href="' + siteconfig.SITE_URL_RE + r'/(?:[a-z]{2}/)?" hreflang="[a-z-]+">[^<]*</a></li>\s*)+</ul>',
        "<ul>\n " + lang_lis + "\n </ul>", new_foot, count=1)
    # categories column: relabel each hub link from the reviewed hub names
    # (the EN footer uses its own label variants — match by URL, not by text;
    # URLs themselves are handled by the global /en/ rewrite below)
    slug_map = _en_hub_slug_map()

    def _cat_li(m):
        fr_hub = slug_map.get(m.group(1))
        if fr_hub:
            return f'{m.group(0)[:m.group(0).index(">", m.group(0).index("href")) + 1]}{e(H.HUB_DISPLAY[fr_hub][lang])}</a></li>'
        return m.group(0)

    new_foot = re.sub(r'<li><a href="' + siteconfig.SITE_URL_RE + r'/en/([a-z0-9-]+)/">[^<]*</a></li>',
                      _cat_li, new_foot)
    new_foot = new_foot.replace('>Weather: clear<', f'>{e(hp["str"]["footstate_clear"])}<')
    html = html.replace(foot, new_foot, 1)

    # --- cards: links, tags, excerpts, alt, action labels ----------------------
    free_w = il["fact_values"]["gratuit"][lang]
    paid_w = il["fact_values"]["payant"][lang]
    seasonal_w = sc["hub_chrome"][lang]["seasonal"]

    def card_repl(m):
        card = m.group(0)
        sm = re.search(r'href="' + siteconfig.SITE_URL_RE + r'/en/([a-z0-9-]+)"', card)
        d = _load_fiche(sm.group(1)) if sm else None
        # A card whose fiche is gone or unpublished has NO page in this tree
        # (the tree is fully regenerated from Json/) — drop it rather than
        # link a 404. Stale cards can survive in the EN frozen chrome because
        # the EN tree keeps its old HTML; a facts tree cannot.
        if d is None or d.get("status") not in (None, "published"):
            return ""
        loc = (d.get("i18n") or {}).get(lang) or {}
        fr = (d.get("i18n") or {}).get("fr") or {}
        # excerpt: own language's translated meta_description or nothing
        own = (loc.get("meta_description") or "").strip()
        if own:
            card = re.sub(r'(<p class="card-desc">).*?(</p>)',
                          lambda mm: mm.group(1) + e(own) + mm.group(2), card, count=1, flags=re.S)
        else:
            card = re.sub(r'\n?<p class="card-desc">.*?</p>', '', card, count=1, flags=re.S)
        # alt: own hero_alt or the frozen FR name
        alt = loc.get("hero_alt") or fr.get("name")
        if alt:
            card = re.sub(r'alt="[^"]*"', f'alt="{a(alt)}"', card, count=1)
        for en_w, new_w in (("Free", free_w), ("Paid", paid_w), ("Seasonal", seasonal_w)):
            card = re.sub(r'(<span class="card-tag[^"]*">)' + en_w + r'(</span>)',
                          lambda mm: mm.group(1) + e(new_w) + mm.group(2), card, count=1)
        card = card.replace('<span>Directions</span>', f'<span>{e(rc["directions"])}</span>')
        card = card.replace('<span>Official site</span>', f'<span>{e(rc["official_site"])}</span>')
        card = card.replace('<span>Website</span>', f'<span>{e(rc["official_site"])}</span>')
        return card

    html = re.sub(r'<article class="card">.*?</article>', card_repl, html, flags=re.S)

    # --- global /en/ URL rewrite (after legal column was re-routed) ------------
    def url_repl(m):
        path = m.group(1)
        if path == "":
            return f'"{BASE}/{lang}/"'
        if path.endswith("/"):
            slug = path[:-1]
            fr_hub = slug_map.get(slug)
            if fr_hub:  # localized hub slug
                return f'"{BASE}/{lang}/{H.hub_slug_for(fr_hub, lang)}/"'
            return f'"{BASE}/{lang}/{slug}/"'   # commune dirs share slugs
        return f'"{BASE}/{lang}/{path}"'        # fiche pages share slugs

    html = re.sub(r'"' + siteconfig.SITE_URL_RE + r'/en/([^"]*)"', url_repl, html)

    # header near-me + language picker if present in the homepage chrome
    html = re.sub(r'<!--nearme:start-->.*?<!--nearme:end-->',
                  lambda _m: f'<!--nearme:start-->{H._nearme_button_html(lang)}<!--nearme:end-->',
                  html, flags=re.S)
    nm = H._data("nearme-labels.json").get(lang)
    if nm:
        en_nm = H._data("nearme-labels.json")["en"]
        for k in ("def", "loading", "on", "off", "title", "sub", "cta"):
            if en_nm.get(k):
                html = html.replace(f'"{en_nm[k]}"', f'"{nm[k]}"')
    # header lang-picker summary + menu (same markup family as hubs/communes)
    cur_attr = 'aria-current="true" '
    menu = "".join(
        f'<a {cur_attr if l == lang else ""}href="{(BASE + "/") if l == "fr" else f"{BASE}/{l}/"}" '
        f'hreflang="{l}">{ends[l]}</a>' for l in locales.VISIBLE)  # isolation-ok: roster nav
    html = re.sub(
        r'<details class="lang-picker">\s*<summary>.*?</summary>\s*<div class="lang-menu">.*?</div>\s*</details>',
        f'<details class="lang-picker">\n<summary><b>{lang.upper()}</b> · {e(cc["langues"])}</summary>\n'
        f'<div class="lang-menu">\n{menu}\n</div>\n</details>',
        html, flags=re.S, count=1)

    return html


def main():
    lang = sys.argv[1]
    assert lang not in locales.PROSE, "the six live locales are never rendered by this module"
    out = ROOT / lang / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_homepage(lang), encoding="utf-8")
    print(f"wrote {lang}/index.html")


if __name__ == "__main__":
    main()
