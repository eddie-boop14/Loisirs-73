#!/usr/bin/env python3
"""build_pilot_langs.py — STAGED facts-first pilot for new (vocab-verified) langs.

HANDOFF-06 Phase B, the safe way. Renders a ~20-page marquee pilot per
new language whose `reviewed` flag in data/i18n-labels.json is non-false AND
which is not one of the 6 already-live locales AND not RTL (ar/he need the RTL
engine — Phase C). Each page is FACTS-FIRST:

  descriptor (from `category` → descriptors_by_type) + a card of ONLY
  language-independent / enum facts (Pavillon Bleu, PMR status, free/paid,
  price €, official link) labelled from the vocab. No FR free-text prose is
  ever shown, so no FR fallback can leak. `null` → "not stated".

CRITICAL ISOLATION (so it can never disturb the 6 ranking languages):
  - pages carry <meta name="robots" content="noindex,nofollow"> (staging).
  - written to <lang>/<slug>.html for langs OUTSIDE every live roster
    (build_site LOCALES, check_reachability ALL_LANGS, fix_hreflang_sitemap
    LANGS are all en/de/it/es/nl) → not deployed, not in sitemap, not in
    hreflang, not reachability-checked.
  - NOT wired into build_all. Run manually; commit as review artifacts.

Frozen FR proper nouns verbatim. Protected fiches never rendered.
"""
import html as _h
import siteconfig  # HANDOFF-73: per-site identity
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import locales  # noqa: E402
import assets  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABELS = json.loads(open(os.path.join(ROOT, "data", "i18n-labels.json"), encoding="utf-8").read())
LIVE6 = set(locales.VISIBLE)  # isolation-ok: exclude visible langs from the pilot
RTL = set(LABELS["_meta"].get("rtl", []))
PROTECTED = {"chez-nous-a-la-plage", "chalet-du-tornet"}
BASE = siteconfig.BASE_URL
# HANDOFF-11 — the Latin pilot is flipped INDEXABLE to start the GSC clock:
# self-canonical + index,follow + listed in sitemap (own URLs only), but kept
# OUT of the 6 live languages' hreflang clusters. RTL (ar/he) stay excluded.
INDEXABLE = set(locales.STAGED_INDEXABLE)
PILOT_LASTMOD = "2026-06-30"  # the flip date — deterministic for byte-stable rebuilds

# ~20 marquee pilot fiches (Mont-Blanc / Chamonix / Annecy / Évian / Megève set).
PILOT = [
    "telepherique-aiguille-du-midi", "telepherique-du-brevent",
    "telepherique-des-grands-montets", "train-du-montenvers-mer-de-glace",
    "tramway-du-mont-blanc", "musee-du-mont-blanc-chamonix",
    "espace-tairraz-musee-des-cristaux-chamonix", "patinoire-richard-bozon-chamonix",
    "cascade-d-angon", "gorges-du-fier", "musee-chateau-annecy",
    "palais-de-l-ile-annecy", "plage-imperial-annecy", "jardins-europe-annecy",
    "le-semnoz", "mont-saleve", "telepherique-du-saleve",
    "plage-d-evian-centre-nautique", "casino-evian-resort-evian",
    "patinoire-palais-megeve",
]

CATEGORY_DESCRIPTOR = {
    "plage": "plage", "lac": "lac", "cascade": "cascade", "chateau": "chateau",
    "musee": "musee", "telecabine": "telecabine", "point-de-vue": "point_de_vue",
    "sentier": "sentier", "parc": "parc", "voie-verte": "voie_verte",
    "base-nautique": "base_loisirs", "eglise": "eglise",
}


def V(section, key, lang):
    return LABELS.get(section, {}).get(key, {}).get(lang, "")


def esc(s):
    return _h.escape(str(s or ""), quote=True)


def fact_rows(d, lang):
    """Only language-independent / enum facts, each with a vocab label."""
    rows = []
    so = d.get("schema_org", {}) or {}
    facts = d.get("i18n", {}).get("fr", {}).get("facts", {}) or {}
    # commune — a place name (language-independent)
    commune = d.get("commune") or facts.get("commune")
    if commune:
        rows.append((V("fact_labels", "commune", lang), esc(commune)))
    # price / free-paid — from structured signals only, never the FR prose
    price_from = d.get("price_from")
    cur = {"EUR": "€"}.get(d.get("price_currency"), d.get("price_currency") or "")
    is_free = so.get("is_free")
    if isinstance(price_from, (int, float)) and price_from > 0:
        rows.append((V("fact_labels", "tarif", lang), f"{price_from:.2f}".replace(".", ",") + "\u00a0" + cur))
    elif is_free is True:
        rows.append((V("fact_labels", "tarif", lang), V("fact_values", "gratuit", lang)))
    elif is_free is False:
        rows.append((V("fact_labels", "tarif", lang), V("fact_values", "payant", lang)))
    # Pavillon Bleu — show only the positive marker
    if str(facts.get("pavillon_bleu_2026", "")).strip().upper() == "OUI":
        rows.append((V("fact_labels", "pavillon_bleu", lang), V("fact_values", "oui", lang)))
    # PMR — enum status; null => "not stated"
    ap = d.get("acces_pmr")
    if isinstance(ap, dict):
        st = ap.get("status")
        valkey = {"accessible": "pmr_accessible", "partiel": "pmr_partiel",
                  "non_accessible": "pmr_non"}.get(st, "pmr_non_renseigne")
        rows.append((V("fact_labels", "acces_pmr", lang), V("fact_values", valkey, lang)))
    return rows


CSS = ("*{box-sizing:border-box}body{margin:0;font-family:-apple-system,system-ui,Segoe UI,Roboto,sans-serif;"
       "background:#FAF7F0;color:#22302f;line-height:1.55}.wrap{max-width:680px;margin:0 auto;padding:18px}"
       ".staging{background:#fff3cd;border:1px solid #ffe69c;color:#7a5b00;border-radius:8px;"
       "padding:6px 12px;font-size:12px;font-weight:600;margin-bottom:14px}"
       "h1{font-size:25px;margin:.2em 0}.desc{color:#1F6E78;font-weight:600;margin:.2em 0 1em}"
       "dl.facts{display:grid;grid-template-columns:auto 1fr;gap:6px 16px;background:#fff;border:1px solid #e3ddd0;"
       "border-radius:12px;padding:14px 16px}dt{color:#5b6b6a;font-size:14px}dd{margin:0;font-weight:600;text-align:end}"
       "a.site{display:inline-block;margin-top:12px;color:#1F6E78;font-weight:600}"
       "footer{margin-top:26px;padding-top:12px;border-top:1px solid #e3ddd0;font-size:12px;color:#5b6b6a}")


# Non-Latin script fonts per held language (HANDOFF-13 RTL ar/he, HANDOFF-14 ja).
SCRIPT_FONT = {"ar": "Noto Sans Arabic", "he": "Noto Sans Hebrew", "ja": "Noto Sans JP"}


def render(d, lang):
    name = d.get("i18n", {}).get("fr", {}).get("name") or d["slug"]   # frozen FR name, verbatim
    commune = d.get("commune", "")
    desc_key = CATEGORY_DESCRIPTOR.get(d.get("category"))
    descriptor = V("descriptors_by_type", desc_key, lang) if desc_key else ""
    rtl = locales.DIR.get(lang) == "rtl"

    # RTL bidi isolation (HANDOFF-13): every Latin/numeric run — frozen FR names,
    # communes, prices, hours, URLs — is wrapped in <bdi> so it never renders
    # scrambled inside the RTL flow. One helper, impossible to forget. LTR pages
    # pass straight through, so the Latin pilot stays byte-identical.
    def bidi(s_esc):
        return f"<bdi>{s_esc}</bdi>" if rtl else s_esc

    rows = fact_rows(d, lang)
    facts_html = "".join(f"<dt>{esc(lbl)}</dt><dd>{bidi(val)}</dd>" for lbl, val in rows if lbl)
    site = d.get("official_site_url")
    site_html = (f'<a class="site" href="{esc(site)}" rel="nofollow noopener" target="_blank">'
                 f'{esc(V("ui_chrome", "site_officiel", lang))} ↗</a>') if site else ""
    method = LABELS["_meta"].get("review_method", {}).get(lang, "")
    schema = {"@context": "https://schema.org", "@type": "TouristAttraction",
              "name": name, "inLanguage": lang,
              "address": {"@type": "PostalAddress", "addressLocality": commune,
                          "addressRegion": siteconfig.DEPT_NAME, "addressCountry": "FR"}}
    if d.get("latitude") and d.get("longitude"):
        schema["geo"] = {"@type": "GeoCoordinates", "latitude": d["latitude"], "longitude": d["longitude"]}
    title = f"{name} · {commune} — {siteconfig.DOMAIN.split('.')[0]}"
    meta_desc = (descriptor + (", " if descriptor else "") + commune + f" ({siteconfig.DEPT_NAME}).").strip()
    indexable = lang in INDEXABLE
    self_url = f"{BASE}/{lang}/{d['slug']}"
    robots = "index,follow" if indexable else "noindex,nofollow"
    canonical = f'<link rel="canonical" href="{self_url}">' if indexable else ""
    staging = ("" if indexable else
               f'<div class="staging">⚠ STAGING — {esc(lang)} pilot · not indexed '
               f'· awaiting native review</div>')
    # Held-pilot chrome — kept off the indexable Latin pilot so its only delta is
    # the shared logical-property CSS. dir="rtl" rides only on RTL pages; the
    # script font rides on any non-Latin-script lang (ar/he/ja); the duck (which
    # quacks the page language + mirrors its bubble on dir=rtl) rides on every
    # held noindex pilot — ar/he/ja — so it can be eyeballed in the spot-check.
    dir_attr = ' dir="rtl"' if rtl else ''
    rtl_head = ""
    fam = SCRIPT_FONT.get(lang)
    if fam:
        fam_url = fam.replace(" ", "+")
        rtl_head = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
                    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
                    f'<link href="https://fonts.googleapis.com/css2?family={fam_url}:wght@400;600&display=swap" rel="stylesheet">'
                    f'<style>body{{font-family:"{fam}",system-ui,sans-serif}}</style>')
    duck = assets.script_tag("duck.js") if not indexable else ""
    return f"""<!doctype html><html lang="{lang}"{dir_attr}><head><script>document.documentElement.classList.add('js')</script>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="robots" content="{robots}">
{canonical}
<meta name="description" content="{esc(meta_desc)}">{rtl_head}
<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>
<style>{CSS}</style></head><body><div class="wrap">
{staging}
<h1>{bidi(esc(name))}</h1>
{f'<p class="desc">{esc(descriptor)}</p>' if descriptor else ''}
<dl class="facts">{facts_html}</dl>
{site_html}
<footer>© 2026 · Bleu canard édition · Edmaster &amp; Claudius 🦆<br>
Facts-first pilot · labels: {esc(method)}</footer>{duck}
</div></body></html>"""


PILOT_MARK_A = "  <!-- staged-indexable pilot (HANDOFF-11): own URLs only, NO hreflang -->"
PILOT_MARK_B = "  <!-- /staged-indexable pilot -->"


def append_sitemap(urls):
    """Add the indexable pilot URLs to sitemap.xml (own <loc> only — NO hreflang
    alternates, so they never enter the 6 live languages' clusters). Idempotent:
    fix_hreflang_sitemap rewrites the file fresh each build, then this appends."""
    sm = os.path.join(ROOT, "sitemap.xml")
    if not os.path.exists(sm):
        return
    import re
    xml = open(sm, encoding="utf-8").read()
    xml = re.sub(re.escape(PILOT_MARK_A) + r".*?" + re.escape(PILOT_MARK_B) + r"\n?",
                 "", xml, flags=re.S)
    # Also drop any stray pilot <url> entries that fix_hreflang_sitemap preserved
    # WITHOUT our markers (it rebuilds the sitemap and strips comments) — else they
    # duplicate when we re-add the block. Idempotent by <loc>.
    for u in urls:
        xml = re.sub(r"[ \t]*<url><loc>" + re.escape(u) + r"</loc>.*?</url>\n?", "", xml, flags=re.S)
    block = "\n".join([PILOT_MARK_A] + [
        f'  <url><loc>{u}</loc><lastmod>{PILOT_LASTMOD}</lastmod>'
        f'<changefreq>weekly</changefreq></url>' for u in urls] + [PILOT_MARK_B, ""])
    xml = xml.replace("</urlset>", block + "</urlset>", 1)
    with open(sm, "w", encoding="utf-8") as fh:
        fh.write(xml)


def main():
    reviewed = LABELS["_meta"].get("reviewed", {})
    # Phase C (HANDOFF-13): RTL langs are now eligible too, but render NOINDEX via
    # the RTL engine (held — staged for native spot-check, never indexed). Only
    # INDEXABLE (the Latin pilot) carries index,follow + sitemap.
    eligible = [l for l, r in reviewed.items()
                if r and r is not False and l not in LIVE6]
    print(f"eligible pilot langs: {eligible} "
          f"(indexable: {sorted(set(eligible) & INDEXABLE)}, "
          f"rtl noindex: {sorted(set(eligible) & RTL)})")
    n = 0
    sitemap_urls = []
    for lang in eligible:
        os.makedirs(os.path.join(ROOT, lang), exist_ok=True)
        for slug in PILOT:
            if slug in PROTECTED:
                continue
            fp = os.path.join(ROOT, "Json", f"{slug}.json")
            if not os.path.exists(fp):
                print(f"  [skip] {slug} (no fiche)"); continue
            d = json.loads(open(fp, encoding="utf-8").read())
            out = os.path.join(ROOT, lang, f"{slug}.html")
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(render(d, lang))
            n += 1
            if lang in INDEXABLE:
                sitemap_urls.append(f"{BASE}/{lang}/{slug}")
    append_sitemap(sorted(sitemap_urls))
    print(f"build_pilot_langs: {n} pilot page(s) across {len(eligible)} lang(s); "
          f"{len(sitemap_urls)} added to sitemap (indexable, no hreflang)")


if __name__ == "__main__":
    main()
