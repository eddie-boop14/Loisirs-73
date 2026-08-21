#!/usr/bin/env python3
"""build_intent_hubs.py — registry-driven intent-hub pages (answer-first SEO).

Reads the curated registry data/intent-hubs.json. For each hub it selects the
member lieux listed there, pulls their DISPLAYED facts LIVE from each fiche's
i18n.<lang>.facts (never re-derived, never price_from), and renders an
answer-first page + Leaflet map + ItemList/FAQPage schema, FR + 5 locales.

Editorial that can't be re-derived (cost bucket, rive, tag, highlight, answer,
FAQ) lives in the registry — the single curation surface. Displayed values come
from the fiche. null facts render "voir fiche", never a value.

Each hub is linked from its category hub (so reachability stays 0-orphan); flat
<slug>.html (FR) + <lang>/<slug>.html. Canonicals/hreflang/sitemap are added by
fix_hreflang_sitemap.py downstream. No timestamps/random → byte-stable.
"""
import html as _html
import siteconfig  # HANDOFF-73: per-site identity
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from build_hubs import hub_locale_map, HUB_DISPLAY, HUB_SLUGS_FACTS  # noqa: E402
import locales  # noqa: E402

REGISTRY = os.path.join(ROOT, "data", "intent-hubs.json")
JSON_DIR = os.path.join(ROOT, "Json")
BASE = siteconfig.BASE_URL
LANGS = locales.PROSE

FACT_LABELS = {
    "access":      {"fr": "Accès", "en": "Access", "de": "Zugang", "it": "Accesso", "es": "Acceso", "nl": "Toegang"},
    "tarif":       {"fr": "Tarif", "en": "Price", "de": "Preis", "it": "Tariffa", "es": "Tarifa", "nl": "Tarief"},
    "best_season": {"fr": "Saison", "en": "Season", "de": "Saison", "it": "Stagione", "es": "Temporada", "nl": "Seizoen"},
    "duration":    {"fr": "Durée d'accès", "en": "Access time", "de": "Zugangsdauer", "it": "Durata d'accesso", "es": "Duración de acceso", "nl": "Toegangstijd"},
    "commune":     {"fr": "Commune", "en": "Town", "de": "Gemeinde", "it": "Comune", "es": "Municipio", "nl": "Gemeente"},
    "stroller":    {"fr": "Poussette", "en": "Stroller", "de": "Kinderwagen", "it": "Passeggino", "es": "Carrito", "nl": "Kinderwagen"},
}
UI = {
    "see_fiche":  {"fr": "Voir la fiche →", "en": "See details →", "de": "Zum Steckbrief →", "it": "Vedi la scheda →", "es": "Ver la ficha →", "nl": "Bekijk fiche →", "pl": "Zobacz szczegóły →", "pt": "Ver ficha →", "cs": "Zobrazit detail →", "ar": "عرض التفاصيل ←", "he": "לצפייה בפרטים ←", "ja": "詳細を見る →"},
    "voir_fiche": {"fr": "voir fiche", "en": "see details", "de": "siehe Steckbrief", "it": "vedi scheda", "es": "ver ficha", "nl": "zie fiche"},
    "faq":        {"fr": "Questions fréquentes", "en": "Frequently asked questions", "de": "Häufige Fragen", "it": "Domande frequenti", "es": "Preguntas frecuentes", "nl": "Veelgestelde vragen"},
    "verified":   {"fr": "📍 vérifiée", "en": "📍 verified", "de": "📍 geprüft", "it": "📍 verificata", "es": "📍 verificada", "nl": "📍 geverifieerd"},
    "also":       {"fr": "À lire aussi", "en": "See also", "de": "Siehe auch", "it": "Da leggere anche", "es": "Ver también", "nl": "Zie ook"},
    "guides":     {"fr": "Les guides par lac", "en": "Guides by lake", "de": "Guides nach See", "it": "Guide per lago", "es": "Guías por lago", "nl": "Gidsen per meer"},
    "see_guide":  {"fr": "Voir le guide →", "en": "See the guide →", "de": "Zum Guide →", "it": "Vedi la guida →", "es": "Ver la guía →", "nl": "Bekijk de gids →"},
    "our_selection": {"fr": "Notre sélection", "en": "Our selection", "de": "Unsere Auswahl", "it": "La nostra selezione", "es": "Nuestra selección", "nl": "Onze selectie", "pl": "Nasz wybór", "pt": "A nossa seleção", "cs": "Náš výběr", "ar": "مختاراتنا", "he": "הבחירה שלנו", "ja": "厳選"},
}

# Outbound-navigation strings — ALL 12 published locales (both templates reuse
# these; a missing token fails gate_intent_nav, no silent FR fallback).
NAV_UI = {
    "home":           {"fr": "Accueil", "en": "Home", "de": "Startseite", "it": "Home", "es": "Inicio", "nl": "Home", "pl": "Strona główna", "pt": "Início", "cs": "Domů", "ar": "الرئيسية", "he": "בית", "ja": "ホーム"},
    "back_to":        {"fr": "Retour à", "en": "Back to", "de": "Zurück zu", "it": "Torna a", "es": "Volver a", "nl": "Terug naar", "pl": "Powrót do", "pt": "Voltar a", "cs": "Zpět na", "ar": "العودة إلى", "he": "חזרה אל", "ja": "戻る："},
    "keep_exploring": {"fr": "Continuer l'exploration", "en": "Keep exploring", "de": "Weiter erkunden", "it": "Continua a esplorare", "es": "Seguir explorando", "nl": "Verder verkennen", "pl": "Odkrywaj dalej", "pt": "Continuar a explorar", "cs": "Prozkoumávejte dál", "ar": "واصل الاستكشاف", "he": "המשיכו לחקור", "ja": "探索を続ける"},
    "all_guides":     {"fr": "Tous les guides", "en": "All guides", "de": "Alle Guides", "it": "Tutte le guide", "es": "Todas las guías", "nl": "Alle gidsen", "pl": "Wszystkie przewodniki", "pt": "Todos os guias", "cs": "Všichni průvodci", "ar": "جميع الأدلة", "he": "כל המדריכים", "ja": "すべてのガイド"},
}
FOOTER_UI = {
    "explore":    {"fr": "Explorer", "en": "Explore", "de": "Entdecken", "it": "Esplora", "es": "Explorar", "nl": "Ontdekken", "pl": "Odkrywaj", "pt": "Explorar", "cs": "Prozkoumat", "ar": "استكشف", "he": "לחקור", "ja": "見つける"},
    "contribute": {"fr": "Contribuer", "en": "Contribute", "de": "Mitmachen", "it": "Contribuisci", "es": "Contribuir", "nl": "Bijdragen", "pl": "Współtwórz", "pt": "Contribuir", "cs": "Přispět", "ar": "ساهم", "he": "לתרום", "ja": "参加する"},
    "legal":      {"fr": "Légal", "en": "Legal", "de": "Rechtliches", "it": "Note legali", "es": "Legal", "nl": "Juridisch", "pl": "Informacje prawne", "pt": "Jurídico", "cs": "Právní", "ar": "قانوني", "he": "משפטי", "ja": "法的事項"},
    "report":     {"fr": "Signaler une erreur", "en": "Report an error", "de": "Fehler melden", "it": "Segnala un errore", "es": "Informar de un error", "nl": "Fout melden", "pl": "Zgłoś błąd", "pt": "Comunicar um erro", "cs": "Nahlásit chybu", "ar": "الإبلاغ عن خطأ", "he": "דיווח על טעות", "ja": "間違いを報告"},
    "partner":    {"fr": "Devenir partenaire", "en": "Become a partner", "de": "Partner werden", "it": "Diventa partner", "es": "Hazte socio", "nl": "Partner worden", "pl": "Zostań partnerem", "pt": "Torne-se parceiro", "cs": "Stát se partnerem", "ar": "كن شريكًا", "he": "להיות שותף", "ja": "パートナーになる"},
    "legal_mentions": {"fr": "Mentions légales", "en": "Legal notice", "de": "Impressum", "it": "Note legali", "es": "Aviso legal", "nl": "Juridische kennisgeving", "pl": "Nota prawna", "pt": "Aviso legal", "cs": "Právní upozornění", "ar": "إشعار قانوني", "he": "הודעה משפטית", "ja": "法的通知"},
    "privacy":    {"fr": "Confidentialité", "en": "Privacy", "de": "Datenschutz", "it": "Privacy", "es": "Privacidad", "nl": "Privacy", "pl": "Prywatność", "pt": "Privacidade", "cs": "Soukromí", "ar": "الخصوصية", "he": "פרטיות", "ja": "プライバシー"},
}
# Localized hub display names: HUB_DISPLAY literal covers fr/en/de/it/es/nl;
# i18n-labels hub_names covers fr/en/pl/pt/cs/ar/he/ja → union = all 12.
_HUB_NAMES = json.loads(open(os.path.join(ROOT, "data", "i18n-labels.json"),
                             encoding="utf-8").read()).get("hub_names", {})
_DIR = locales.DIR

# Populated by main() so render_hub can resolve linked_hubs by slug.
_ALL_HUBS = {}
RIVE = {
    "Nord": {"fr": "Nord", "en": "North", "de": "Nord", "it": "Nord", "es": "Norte", "nl": "Noord"},
    "Sud": {"fr": "Sud", "en": "South", "de": "Süd", "it": "Sud", "es": "Sur", "nl": "Zuid"},
    "Est": {"fr": "Est", "en": "East", "de": "Ost", "it": "Est", "es": "Este", "nl": "Oost"},
    "Ouest": {"fr": "Ouest", "en": "West", "de": "West", "it": "Ovest", "es": "Oeste", "nl": "West"},
}
TAGS_BUILTIN = {
    "seasonal": {"fr": "Saisonnier", "en": "Seasonal", "de": "Saisonal", "it": "Stagionale", "es": "De temporada", "nl": "Seizoensgebonden"},
    "quick":    {"fr": "Arrêt court", "en": "Quick stop", "de": "Kurzer Halt", "it": "Sosta breve", "es": "Parada corta", "nl": "Korte stop"},
    "rando":    {"fr": "Randonnée", "en": "Hike", "de": "Wanderung", "it": "Escursione", "es": "Senderismo", "nl": "Wandeling"},
}

CSS = """:root{--cream:#FAF7F0;--teal:#1F6E78;--teal2:#155059;--ink:#22302f;--ink2:#5b6b6a;--line:#e3ddd0}
*{box-sizing:border-box}body{margin:0;font-family:-apple-system,system-ui,Segoe UI,Roboto,sans-serif;color:var(--ink);background:var(--cream);line-height:1.55}
.wrap{max-width:760px;margin:0 auto;padding:18px}
.kicker{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--teal);font-weight:700}
h1{font-size:26px;line-height:1.2;margin:.3em 0}
.lead{font-size:16px;color:var(--ink2)}
.answer{background:#fff;border:1px solid var(--line);border-left:4px solid var(--teal);border-radius:12px;padding:14px 16px;margin:16px 0}
.answer b{color:var(--teal2)}
.pill{display:inline-block;background:#eef4f2;border:1px solid #d6e6e2;color:var(--teal2);border-radius:999px;padding:2px 10px;font-size:13px;font-weight:600;margin:2px 4px 2px 0}
#map{height:300px;border-radius:12px;border:1px solid var(--line);margin:14px 0}
h2{font-size:13px;letter-spacing:.1em;text-transform:uppercase;margin:26px 0 10px}
.cards{display:grid;gap:12px}
.card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:13px 15px}
.ch{display:flex;align-items:center;justify-content:space-between;gap:8px}
.ch h3{margin:0;font-size:17px}
.rive{font-size:12px;font-weight:700;color:var(--teal2);background:#eef4f2;border:1px solid #d6e6e2;border-radius:999px;padding:2px 9px}
.tag{font-size:11px;font-weight:700;border-radius:999px;padding:2px 9px}
.tag.quick{color:#1d6b3a;background:#e7f3ea;border:1px solid #c6e3cf}
.tag.rando{color:#8a4b1e;background:#f6ecde;border:1px solid #e6cfb0}
.meta{color:var(--ink2);font-size:13px;margin:2px 0 6px}
.chip{display:inline-block;background:#f3ecdc;border:1px solid #e6d8b8;color:#8a6a1e;border-radius:999px;padding:1px 8px;font-size:11px;font-weight:700;margin-left:4px}
.hi{margin:6px 0 10px;font-size:14px}
.facts{display:grid;gap:6px}
.f{display:flex;justify-content:space-between;font-size:13px;border-bottom:1px dashed var(--line);padding:3px 0;gap:10px}
.f span{color:var(--ink2);flex:0 0 auto}.f b{font-weight:600;text-align:right}
.fiche{display:inline-block;margin-top:10px;color:var(--teal);font-weight:600;text-decoration:none;font-size:14px}
.q{background:#fff;border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin:8px 0}
.q summary{font-weight:600;cursor:pointer}.q p{color:var(--ink2);margin:8px 0 2px}
.note{font-size:12px;color:var(--ink2);margin-top:8px}
.topbar{position:sticky;top:0;z-index:1000;background:var(--cream);border-bottom:1px solid var(--line);padding:8px 18px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.topbar .brand{font-weight:800;color:var(--teal);text-decoration:none;white-space:nowrap}
.crumbs{font-size:13px;color:#6b7a78}
.crumbs ol{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;align-items:center}
.crumbs li{display:flex;align-items:center}
.crumbs li+li::before{content:"\\203A";margin-inline:6px;color:var(--ink2)}
[dir=rtl] .crumbs li+li::before{content:"\\2039"}
.crumbs a{color:var(--teal2);text-decoration:none}.crumbs a:hover{text-decoration:underline}
.crumbs [aria-current=page]{color:var(--ink2)}
@media(max-width:520px){.crumbs{font-size:12px}}
.keepgoing{background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:22px 0}
.keepgoing h2{margin:0 0 10px;font-size:16px;color:var(--teal);text-transform:none;letter-spacing:0}
.keepgoing a{display:inline-block;margin:3px 10px 3px 0;color:var(--teal2);font-weight:600;text-decoration:none}
.keepgoing a.up{display:block;margin:6px 0}
footer{margin-top:30px;padding-top:14px;border-top:1px solid var(--line);font-size:12px;color:var(--ink2);text-align:center}
footer.site{text-align:start}
.foot-grid{display:flex;flex-wrap:wrap;gap:24px 40px;margin-bottom:14px}
.foot-col h4{margin:0 0 6px;font-size:13px;color:var(--teal);text-transform:none;letter-spacing:0}
.foot-col ul{list-style:none;margin:0;padding:0}
.foot-col li{margin:3px 0}
.foot-col a{color:var(--teal2);text-decoration:none;font-size:13px}.foot-col a:hover{text-decoration:underline}
.foot-bottom{border-top:1px solid var(--line);padding-top:10px;color:var(--ink2)}"""


def L(d, lang):
    """Resolve an i18n dict to lang with FR fallback."""
    if not isinstance(d, dict):
        return d
    return d.get(lang) or d.get("fr") or ""


def esc(s):
    return _html.escape(str(s or ""), quote=True)


def fiche_facts(fiche, lang):
    i = fiche.get("i18n", {})
    return (i.get(lang, {}).get("facts") or i.get("fr", {}).get("facts") or {})


def fiche_name(fiche, lang):
    i = fiche.get("i18n", {})
    return i.get(lang, {}).get("name") or i.get("fr", {}).get("name") or fiche.get("slug")


def url_for(slug, lang):
    return f"{BASE}/{slug}" if lang == "fr" else f"{BASE}/{lang}/{slug}"


def render_card(hub, m, fiche, lang):
    name = fiche_name(fiche, lang)
    facts = fiche_facts(fiche, lang)
    head_right = ""
    if m.get("rive"):
        head_right = f'<span class="rive">{esc(L(RIVE.get(m["rive"], {"fr": m["rive"]}), lang))}</span>'
    elif m.get("tag") in ("quick", "rando"):
        cls = m["tag"]
        head_right = f'<span class="tag {cls}">{esc(L(TAGS_BUILTIN[cls], lang))}</span>'
    # commune + geo-verified badge + seasonal chip
    bits = [esc(facts.get("commune") or fiche.get("commune") or "")]
    if fiche.get("geo_verified"):
        bits.append(esc(L(UI["verified"], lang)))
    meta = " · ".join(b for b in bits if b)
    chip = ""
    if m.get("tag") == "seasonal":
        chip = f' <span class="chip">{esc(L(TAGS_BUILTIN["seasonal"], lang))}</span>'
    hi = ""
    if m.get("hi"):
        hv = L(m["hi"], lang)
        if hv:
            hi = f'<p class="hi">{esc(hv)}</p>'
    # facts rows
    rows = []
    for fs in hub["facts_shown"]:
        field = fs["field"]
        label = esc(L(FACT_LABELS.get(field, fs.get("label", {})), lang) or L(fs.get("label", {}), lang))
        val = facts.get(field)
        if not val:
            if fs.get("mode") == "if_present":
                continue
            val_html = f'<a class="fiche" style="margin:0;font-size:13px" href="{url_for(fiche["slug"], lang)}">{esc(L(UI["voir_fiche"], lang))}</a>'
        else:
            val_html = esc(val)
        rows.append(f'<div class="f"><span>{label}</span><b>{val_html}</b></div>')
    facts_html = '<div class="facts">' + "".join(rows) + "</div>" if rows else ""
    return (
        '<article class="card">\n'
        f'  <div class="ch"><h3>{esc(name)}</h3>{head_right}</div>\n'
        f'  <div class="meta">{meta}{chip}</div>\n'
        f'  {hi}{facts_html}\n'
        f'  <a class="fiche" href="{url_for(fiche["slug"], lang)}">{esc(L(UI["see_fiche"], lang))}</a>\n'
        '</article>'
    )


def schema_block(hub, members_fiches, lang, breadcrumb=None):
    items = []
    for i, (m, f) in enumerate(members_fiches, 1):
        items.append({"@type": "ListItem", "position": i,
                      "name": fiche_name(f, lang), "url": url_for(f["slug"], lang)})
    itemlist = {"@type": "ItemList", "name": L(hub["h1"], lang), "itemListElement": items}
    faq = {"@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": L(q["q"], lang),
         "acceptedAnswer": {"@type": "Answer", "text": L(q["a"], lang)}}
        for q in hub.get("faq", [])]}
    graph = {"@context": "https://schema.org", "@graph": [itemlist, faq]}
    if breadcrumb:
        graph["@graph"].append(breadcrumb)
    return json.dumps(graph, ensure_ascii=False)


def _dir_attr(lang):
    return ' dir="rtl"' if _DIR.get(lang) == "rtl" else ""


def _hub_label(hub, lang):
    return (HUB_DISPLAY.get(hub, {}).get(lang)
            or _HUB_NAMES.get(hub, {}).get(lang)
            or HUB_DISPLAY.get(hub, {}).get("fr")
            or _HUB_NAMES.get(hub, {}).get("fr") or hub)


def _home_url(lang):
    return f"{BASE}/" if lang == "fr" else f"{BASE}/{lang}/"


def _qf_index_url(lang):
    pfx = _qf_prefix(lang)
    return f"{BASE}/{pfx}/" if lang == "fr" else f"{BASE}/{lang}/{pfx}/"


def _cat_url(hub, lang):
    d = _hub_dir(hub, lang)
    return f"{BASE}/{d}/" if lang == "fr" else f"{BASE}/{lang}/{d}/"


def _topbar(lang, crumbs):
    """Sticky header + visible breadcrumb. crumbs = [(label, url|None)]; the
    last crumb (url None) renders as aria-current plain text."""
    lis = []
    for label, url in crumbs:
        if url:
            lis.append(f'<li><a href="{url}">{esc(label)}</a></li>')
        else:
            lis.append(f'<li><span aria-current="page">{esc(label)}</span></li>')
    return (f'<header class="topbar"><a class="brand" href="{_home_url(lang)}">{siteconfig.SITE_NAME}</a>'
            f'<nav class="crumbs" aria-label="breadcrumb"><ol>{"".join(lis)}</ol></nav></header>')


def _breadcrumb_node(page_url, crumbs):
    """BreadcrumbList JSON-LD mirroring build_lieu_page (leaf carries no item)."""
    items = []
    for i, (label, url) in enumerate(crumbs, 1):
        el = {"@type": "ListItem", "position": i, "name": label}
        if url:
            el["item"] = url
        items.append(el)
    return {"@type": "BreadcrumbList", "@id": f"{page_url}#breadcrumb", "itemListElement": items}


def _keepgoing(lang, parent_label, parent_url, siblings, qf_url):
    """The dead-end fix: back-to-parent + sibling pages + all-guides, before footer."""
    up = (f'<a class="up" href="{parent_url}">↑ {esc(L(NAV_UI["back_to"], lang))} {esc(parent_label)}</a>'
          if parent_url else "")
    sib = "".join(f'<a href="{u}">{esc(t)} →</a>' for t, u in siblings)
    allg = f'<a href="{qf_url}">{esc(L(NAV_UI["all_guides"], lang))} →</a>'
    return (f'<section class="keepgoing"><h2>{esc(L(NAV_UI["keep_exploring"], lang))}</h2>'
            f'{up}{sib}<div style="margin-top:8px">{allg}</div></section>')


def _linked_footer(lang):
    """4-column linked footer (site_footer shape); copyright byte-identical."""
    home, qf = _home_url(lang), _qf_index_url(lang)

    def li(url, label):
        return f'<li><a href="{url}">{esc(label)}</a></li>'
    col1 = (f'<div class="foot-col"><h4>{esc(L(FOOTER_UI["explore"], lang))}</h4><ul>'
            + li(home, L(NAV_UI["home"], lang)) + li(qf, _hub_label("que-faire", lang)) + "</ul></div>")
    col2 = (f'<div class="foot-col"><h4>{esc(L(FOOTER_UI["contribute"], lang))}</h4><ul>'
            + li(f"{BASE}/signaler", L(FOOTER_UI["report"], lang))
            + li(f"{BASE}/devenir-partenaire", L(FOOTER_UI["partner"], lang)) + "</ul></div>")
    col3 = (f'<div class="foot-col"><h4>{esc(L(FOOTER_UI["legal"], lang))}</h4><ul>'
            + li(f"{BASE}/mentions-legales", L(FOOTER_UI["legal_mentions"], lang))
            + li(f"{BASE}/confidentialite", L(FOOTER_UI["privacy"], lang)) + "</ul></div>")
    return (f'<footer class="site"><div class="foot-grid">{col1}{col2}{col3}</div>'
            '<div class="foot-bottom">© 2026 · Bleu canard édition · Edmaster &amp; Claudius · '
            'Tous droits réservés 🦆</div></footer>')


def render_hub(hub, lang, fiches):
    members_fiches = [(m, fiches[m["slug"]]) for m in hub["members"] if m["slug"] in fiches]
    # group by bucket, preserving registry order
    by_bucket = {}
    for m, f in members_fiches:
        by_bucket.setdefault(m["bucket"], []).append((m, f))

    sections = []
    for b in hub["buckets"]:
        grp = by_bucket.get(b["key"], [])
        if not grp:
            continue
        label = f'{esc(L(b["label"], lang))} · {len(grp)}'
        cards = "".join(render_card(hub, m, f, lang) for m, f in grp)
        sections.append(f'<h2 style="color:{b["color"]}">{label}</h2>\n<div class="cards">{cards}</div>')

    pills = "".join(f'<span class="pill">{esc(p)}</span>' for p in (L(hub.get("pills", {}), lang) or []))
    faq_html = "".join(
        f'<details class="q"><summary>{esc(L(q["q"], lang))}</summary><p>{esc(L(q["a"], lang))}</p></details>'
        for q in hub.get("faq", []))

    # map data
    if hub.get("map"):
        colors = {b["key"]: b["color"] for b in hub["buckets"]}
        pts = []
        for m, f in members_fiches:
            lat, lng = f.get("latitude"), f.get("longitude")
            if lat is None or lng is None:
                continue
            facts = fiche_facts(f, lang)
            pts.append({"name": fiche_name(f, lang),
                        "commune": facts.get("commune") or f.get("commune") or "",
                        "url": url_for(f["slug"], lang),
                        "color": colors.get(m["bucket"], "#155059"),
                        "lat": lat, "lng": lng})
        map_data = json.dumps(pts, ensure_ascii=False)
        map_script = (
            f'<script>var B={map_data};'
            "var map=L.map('map',{scrollWheelZoom:false});"
            "L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,attribution:'© OpenStreetMap'}).addTo(map);"
            "var g=[];B.forEach(function(b){var m=L.circleMarker([b.lat,b.lng],{radius:8,color:'#155059',fillColor:b.color,fillOpacity:.95,weight:2}).addTo(map);"
            "m.bindPopup('<b>'+b.name+'</b><br>'+b.commune+'<br><a href=\"'+b.url+'\">'+"
            f"{json.dumps(L(UI['see_fiche'], lang))}+'</a>');g.push([b.lat,b.lng]);}});"
            "if(g.length)map.fitBounds(L.latLngBounds(g).pad(.15));</script>")
        head_leaflet = ('<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">'
                        '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>')
        map_div = '<div id="map"></div>'
    else:
        map_script = map_div = head_leaflet = ""

    # linked-hub cards (a master hub points at sub-hubs by slug)
    linked_html = ""
    linked = [_ALL_HUBS[s] for s in hub.get("linked_hubs", []) if s in _ALL_HUBS]
    if linked:
        cards = "".join(
            '<article class="card"><div class="ch"><h3>' + esc(L(lh["h1"], lang)) + '</h3>'
            f'<span class="rive">{len(lh.get("members", []))}</span></div>'
            f'<a class="fiche" href="{url_for(lh["slug"], lang)}">{esc(L(UI["see_guide"], lang))}</a></article>'
            for lh in linked)
        linked_html = (f'<h2 style="color:var(--teal)">{esc(L(UI["guides"], lang))}</h2>'
                       f'<div class="cards">{cards}</div>')

    foot = L(hub.get("footer_note", {}), lang)
    foot_html = f'<p class="note">{esc(foot)}</p>' if foot else ""

    # outbound navigation (topbar + breadcrumb + keepgoing + linked footer)
    page_url = url_for(hub["slug"], lang)
    parent_hub = hub.get("category_hub")
    parent_label = _hub_label(parent_hub or "que-faire", lang)
    parent_url = _cat_url(parent_hub, lang) if parent_hub else _qf_index_url(lang)
    crumbs = [(L(NAV_UI["home"], lang), _home_url(lang)),
              (parent_label, parent_url),
              (L(hub["h1"], lang), None)]
    topbar = _topbar(lang, crumbs)
    breadcrumb = _breadcrumb_node(page_url, crumbs)
    siblings = [(L(h["h1"], lang), url_for(h["slug"], lang))
                for h in _ALL_HUBS.values() if h["slug"] != hub["slug"]]
    keepgoing_html = _keepgoing(lang, parent_label, parent_url, siblings, _qf_index_url(lang))
    footer_html = _linked_footer(lang)

    return f"""<!doctype html><html lang="{lang}"{_dir_attr(lang)}><head><script>document.documentElement.classList.add('js')</script>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(L(hub["title"], lang))}</title>
<meta name="description" content="{esc(L(hub["description"], lang))}">
{head_leaflet}
<script type="application/ld+json">{schema_block(hub, members_fiches, lang, breadcrumb)}</script>
<style>{CSS}</style></head><body>{topbar}<div class="wrap">

<div class="kicker">{esc(L(hub.get("kicker", {}), lang))}</div>
<h1>{esc(L(hub["h1"], lang))}</h1>
<p class="lead">{L(hub["lead"], lang)}</p>

<div class="answer">{L(hub["answer"], lang)}
<div style="margin-top:8px">{pills}</div></div>

{linked_html}

{map_div}

{"".join(sections)}
{foot_html}

<h2 style="color:var(--teal)">{esc(L(UI["faq"], lang))}</h2>
{faq_html}

{keepgoing_html}
{footer_html}
</div>
{map_script}
</body></html>"""


MARK_A, MARK_B = "<!--intent-hubs:start-->", "<!--intent-hubs:end-->"


def _place_above_footer(html, block):
    """Insert a reachability block where a human sees it: inside <main> if the
    hub template has one, else immediately ABOVE the page footer (facts-lang
    hubs have no <main>), else before </body>. Never below the footer. Paired
    with a leading-\\s* MARK strip so strip+reinsert is a byte-stable fixpoint."""
    if "<main>" in html:
        return html.replace("<main>", block + "\n<main>", 1)
    idx = html.rfind("<footer")
    if idx != -1:
        return html[:idx] + "\n" + block + html[idx:]
    return html.replace("</body>", "\n" + block + "</body>", 1)


def inject_category_links(hub_links_by_cat, lang):
    """Add a reachable link to each intent hub from its category hub page."""
    import re
    for cat, links in hub_links_by_cat.items():
        slug = (hub_locale_map(cat).get(lang) or cat) if lang != "fr" else cat
        path = os.path.join(ROOT, slug, "index.html") if lang == "fr" else os.path.join(ROOT, lang, slug, "index.html")
        if not os.path.exists(path):
            continue
        html = open(path, encoding="utf-8").read()
        # strip prior block AND any whitespace before it (idempotent — no
        # accumulating newlines across rebuilds → byte-stable)
        html = re.sub(r"\s*" + re.escape(MARK_A) + r".*?" + re.escape(MARK_B), "", html, flags=re.S)
        block = (MARK_A + '<nav class="intent-hubs" style="max-width:760px;margin:18px auto;padding:0 18px">'
                 + "".join(f'<a href="{u}" style="display:inline-block;margin:2px 8px 2px 0;color:#1F6E78;font-weight:600">{esc(t)} →</a>'
                          for u, t in links)
                 + '</nav>' + MARK_B)
        # place inside <main> (visible, ~mid-page) not after </body> (below
        # footer — crawlers count it, humans never see it). Facts-lang hubs
        # have no <main> → insert just ABOVE the footer instead. Idempotent
        # MARK strip above → byte-stable.
        html = _place_above_footer(html, block)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(html)


def main():
    global _ALL_HUBS
    hubs = json.loads(open(REGISTRY, encoding="utf-8").read())
    _ALL_HUBS = {h["slug"]: h for h in hubs}
    # load member fiches once
    need = {m["slug"] for h in hubs for m in h["members"]}
    fiches = {}
    for slug in need:
        fp = os.path.join(JSON_DIR, f"{slug}.json")
        if os.path.exists(fp):
            fiches[slug] = json.loads(open(fp, encoding="utf-8").read())
    written = 0
    for lang in LANGS:
        cat_links = {}
        for hub in hubs:
            html = render_hub(hub, lang, fiches)
            out = os.path.join(ROOT, f"{hub['slug']}.html") if lang == "fr" \
                else os.path.join(ROOT, lang, f"{hub['slug']}.html")
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(html)
            written += 1
            cat_links.setdefault(hub["category_hub"], []).append(
                (url_for(hub["slug"], lang), L(hub["h1"], lang)))
        inject_category_links(cat_links, lang)
    print(f"build_intent_hubs: {len(hubs)} hub(s) × {len(LANGS)} locales = {written} pages; "
          f"category links injected")
    build_intent_pages()




# ═══════════════════════════════════════════════════════════════════════════
# HANDOFF-intentpages — compiled head-term pages (selector-driven layer)
#
# Second registry data/intent-registry.json: each entry is a QUERY (selector)
# + stated ranking + hand-authored per-lang title/lead/criteria_note. Pages
# are COMPILED: member set == selector output (gate-enforced), ranking is
# computed from the stated criteria only, and the criteria_note renders
# visibly (mandatory when the title carries a superlative). A lang ships only
# when its title+lead exist — no machine titles. URLs nest under the
# localized que-faire hub dir (fr: que-faire/<sub>/, en: what-to-do/<sub>/).
# Canonical/hreflang/sitemap fold in downstream via fix_hreflang_sitemap;
# lastmod is honest for free (byte-stable renders only change when a member
# changes, so git-derived lastmod == max member change).
# ═══════════════════════════════════════════════════════════════════════════
import re as _re

REGISTRY2 = os.path.join(ROOT, "data", "intent-registry.json")
SELECT_MD_DIR = os.path.join(ROOT, "content", "selections")

CHIP_LABELS = {
    "free":    {"fr": "Gratuit", "en": "Free", "de": "Kostenlos", "it": "Gratis", "es": "Gratis", "nl": "Gratis", "pl": "Bezpłatnie", "pt": "Gratuito", "cs": "Zdarma", "ar": "مجاني", "he": "חינם", "ja": "無料"},
    "pmr":     {"fr": "Accès PMR", "en": "Wheelchair access", "de": "Barrierefrei", "it": "Accessibile", "es": "Accesible", "nl": "Rolstoeltoegankelijk", "pl": "Dostęp dla wózków", "pt": "Acesso para cadeira de rodas", "cs": "Bezbariérový přístup", "ar": "وصول الكراسي المتحركة", "he": "נגישות לכיסא גלגלים", "ja": "車椅子アクセス"},
    "parking": {"fr": "Parking", "en": "Parking", "de": "Parkplatz", "it": "Parcheggio", "es": "Aparcamiento", "nl": "Parkeren", "pl": "Parking", "pt": "Estacionamento", "cs": "Parkování", "ar": "موقف السيارات", "he": "חניה", "ja": "駐車場"},
    "winter":  {"fr": "Hiver ✓", "en": "Winter ✓", "de": "Winter ✓", "it": "Inverno ✓", "es": "Invierno ✓", "nl": "Winter ✓", "pl": "Zima ✓", "pt": "Inverno ✓", "cs": "Zima ✓", "ar": "شتاء ✓", "he": "חורף ✓", "ja": "冬 ✓"},
}
UI2 = {
    "criteria": {"fr": "Comment cette sélection est faite", "en": "How this selection is made", "de": "Wie diese Auswahl entsteht", "it": "Come nasce questa selezione", "es": "Cómo se hace esta selección", "nl": "Hoe deze selectie tot stand komt", "pl": "Jak powstaje ten wybór", "pt": "Como é feita esta seleção", "cs": "Jak vzniká tento výběr", "ar": "كيف يتم إعداد هذا الاختيار", "he": "כיצד נעשית בחירה זו", "ja": "このセレクションの選び方"},
    "members":  {"fr": "La sélection", "en": "The selection", "de": "Die Auswahl", "it": "La selezione", "es": "La selección", "nl": "De selectie", "pl": "Wybór", "pt": "A seleção", "cs": "Výběr", "ar": "المختارات", "he": "המבחר", "ja": "セレクション"},
}
_DUR_RE = _re.compile(r"(?:(\d+)\s*h(?:\s*(\d{1,2}))?)|(?:(\d{1,3})\s*min)", _re.I)


def _duration_hours(fiche):
    """Min parsable duration (hours) from FR facts keys containing durée/duration."""
    best = None
    for k, v in (fiche.get("i18n", {}).get("fr", {}).get("facts") or {}).items():
        if not _re.search(r"dur[ée]e|duration|temps", k, _re.I) or not isinstance(v, str):
            continue
        for m in _DUR_RE.finditer(v):
            h = (int(m.group(1)) + int(m.group(2) or 0) / 60) if m.group(1) else int(m.group(3)) / 60
            best = h if best is None else min(best, h)
    return best


def _dogs_ok(f):
    """Documented-accepted only: 'Acceptés…', 'Tolérés…', 'Oui…'. 'Non admis',
    'interdits' and undocumented policies are excluded — the page promises the
    dog is WELCOME, so silence is a no. Leash wording renders on each fiche."""
    v = (_fr_facts(f).get("dogs") or "")
    return isinstance(v, str) and v.strip().lower().startswith(("accept", "tolér", "toler", "oui"))


def _fr_facts(f):
    return f.get("i18n", {}).get("fr", {}).get("facts") or {}


def _is_free(f):
    return str(f.get("schema_org", {}).get("is_free")) == "True"


def _is_pmr(f):
    return (f.get("acces_pmr") or {}).get("status") in ("accessible", "partiel")


def _has_winter(f):
    fk = _fr_facts(f)
    return bool(fk.get("winter_access") or fk.get("winter_infra"))


def _real_photo(f):
    h = f.get("hero_image") or ""
    return bool(h) and "generique" not in h


def _facet_richness(f):
    fk = _fr_facts(f)
    filled = sum(1 for v in fk.values() if v not in (None, "", [], False))
    return min(filled, 8) / 8.0


# ── season predicate — deterministic parse of the free-text best_season lane ──
import unicodedata as _ud  # noqa: E402

_MONTHS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
           "juin": 6, "juillet": 7, "aout": 8, "septembre": 9, "octobre": 10,
           "novembre": 11, "decembre": 12}
_SEASONS = {"printemps": {3, 4, 5}, "ete": {6, 7, 8},
            "automne": {9, 10, 11}, "hiver": {12, 1, 2}}
_MLIST = list(_MONTHS)
_RANGE_RE = _re.compile(r"(" + "|".join(_MLIST) + r")\s*(?:-| a | au )\s*("
                        + "|".join(_MLIST) + r")")


def _deaccent(s):
    out = "".join(c for c in _ud.normalize("NFD", s)
                  if _ud.category(c) != "Mn").lower()
    # Apostrophes (straight + curly) → space so "toute l'annee" reads as tokens.
    return out.replace("'", " ").replace("’", " ")


def _season_months_text(raw):
    """The set of calendar months a free-text best_season phrase covers.
    Year-round short-circuits to all twelve; season words and French month
    ranges (incl. wrap) and standalone months union in. Deterministic."""
    t = _deaccent(raw)
    months = set(range(1, 13)) if "toute l annee" in t else set()
    for word, ms in _SEASONS.items():
        if word in t:
            months |= ms
    t2 = _re.sub(r"[–—\-]", " - ", t)
    for m in _RANGE_RE.finditer(t2):
        a, b = _MONTHS[m.group(1)], _MONTHS[m.group(2)]
        months |= (set(range(a, b + 1)) if a <= b
                   else set(range(a, 13)) | set(range(1, b + 1)))
    for word in _MLIST:
        if _re.search(r"\b" + word + r"\b", t2):
            months.add(_MONTHS[word])
    return months


def _season_open(f, month):
    bs = _fr_facts(f).get("best_season")
    if not bs:
        return False
    if isinstance(bs, list):
        bs = " · ".join(str(x) for x in bs)
    return month in _season_months_text(str(bs))


def _hours_text(f):
    for e in ((f.get("i18n", {}).get("fr") or {}).get("practical_info") or []):
        if _deaccent(e.get("k") or "").startswith("horaire") and e.get("v"):
            return str(e["v"])
    return None


_SUN_CLOSED = _re.compile(r"ferme\w*\s+(?:le\s+|les\s+)?dimanche")
_SUN_OPEN = _re.compile(r"7j/7|tous les jours|du lundi au dimanche|dimanche")


def _sunday_open(f):
    """Honest Sunday predicate: the fiche's own FR hours text must POSITIVELY
    cover Sunday (7j/7, tous les jours, or a non-negated 'dimanche' mention).
    Day-silent hours and explicit Sunday closures are excluded — no claim
    without the fiche saying so. Deterministic."""
    h = _hours_text(f)
    if not h:
        return False
    t = _deaccent(h)
    if _SUN_CLOSED.search(t):
        return False
    return bool(_SUN_OPEN.search(t))


def selector_match(f, sel, sets):
    """Deterministic membership predicate — THE page definition."""
    if f.get("status") != "published":
        return False
    communes = sel.get("communes") or (sets.get(sel["communes_set"]) if sel.get("communes_set") else None)
    if communes and f.get("commune") not in communes:
        return False
    # Exclusion — the 'loin de la foule' lane (2026-08: SMB agency de-markets
    # the saturated cores and pushes the 82% unknown; this selector key is how
    # a page states 'NOT the honeypots' as a verifiable criterion).
    excl = sel.get("communes_exclude") or (sets.get(sel["communes_exclude_set"]) if sel.get("communes_exclude_set") else None)
    if excl and f.get("commune") in excl:
        return False
    cats, pats = sel.get("categories"), sel.get("slug_patterns_extra")
    if cats or pats:
        in_cat = bool(cats) and f.get("category") in cats
        in_pat = bool(pats) and any(_re.search(p, f.get("slug", "")) for p in pats)
        if not (in_cat or in_pat):
            return False
    if sel.get("is_free") and not _is_free(f):
        return False
    if sel.get("family_ok") and _fr_facts(f).get("family_ok") is not True:
        return False
    if sel.get("pmr") and not _is_pmr(f):
        return False
    if sel.get("dogs_ok") and not _dogs_ok(f):
        return False
    if sel.get("snow_view") and _fr_facts(f).get("snow_view") != sel["snow_view"]:
        return False
    if sel.get("winter_any") and not _has_winter(f):
        return False
    if sel.get("duration_max_h") is not None:
        h = _duration_hours(f)
        if h is None or h > sel["duration_max_h"]:
            return False
    if sel.get("season_open_month") is not None and not _season_open(f, sel["season_open_month"]):
        return False
    if sel.get("sunday_open") and not _sunday_open(f):
        return False
    return True


_SCORES = {"has_real_photo": _real_photo, "is_free": _is_free,
           "facet_richness": _facet_richness, "pmr": _is_pmr, "winter": _has_winter}


def rank_members(slugs, fiches, ranking, diversify_by=None):
    def key(s):
        f = fiches[s]
        return tuple(-float(_SCORES[r](f)) for r in ranking if r in _SCORES) + (s,)
    ordered = sorted(slugs, key=key)
    if diversify_by != "category":
        return ordered
    # Opt-in only: round-robin across categories so a season-wide pool doesn't
    # surface 11 cascades in a row. Score order is preserved WITHIN each category
    # and categories cycle in first-appearance (i.e. best-ranked) order — fully
    # deterministic, so the gate's "ItemList == selector output" still holds.
    buckets = {}
    for s in ordered:
        buckets.setdefault(fiches[s].get("category") or "", []).append(s)
    out = []
    while any(buckets.values()):
        for cat in list(buckets):
            if buckets[cat]:
                out.append(buckets[cat].pop(0))
    return out


def compute_membership(fiches=None):
    """{page_id: {..entry, 'members': [slug,…]}} — the single truth used by the
    page builder, the fiche 'sélections' chips and the gate."""
    reg = json.loads(open(REGISTRY2, encoding="utf-8").read())
    sets = reg["_meta"]["commune_sets"]
    if fiches is None:
        import glob as _g
        fiches = {}
        for p in _g.glob(os.path.join(JSON_DIR, "*.json")):
            d = json.loads(open(p, encoding="utf-8").read())
            fiches[d.get("slug") or os.path.basename(p)[:-5]] = d
    out = {}
    for e in reg["pages"]:
        matched = [s for s, f in fiches.items() if selector_match(f, e["selector"], sets)]
        members = rank_members(matched, fiches, e["ranking"],
                               e.get("diversify_by"))[: e.get("max_items", 20)]
        out[e["id"]] = {**e, "members": members}
    return out, fiches


def _hub_dir(hub, lang):
    """Localized directory for a hub in this lang, resolving BOTH renderer lanes:
    prose langs via hub_locale_map (fr/en/de/it/es/nl), facts langs via
    HUB_SLUGS_FACTS (pl→co-robic, cs→co-delat, pt→o-que-fazer…). ar/he/ja aren't
    in either map → FR-canonical dir (their subtrees use the FR slugs), which is
    exactly where build_fulltree_lang renders them. This keeps the intent pages
    under the SAME dir as the localized que-faire index (no path mismatch/404)."""
    if lang == "fr":
        return hub
    return (hub_locale_map(hub).get(lang)
            or (HUB_SLUGS_FACTS.get(lang, {}) or {}).get(hub)
            or hub)


def _qf_prefix(lang):
    """Localized que-faire dir for this lang (fr: que-faire, en: what-to-do…)."""
    return _hub_dir("que-faire", lang)


def intent_page_url(entry, lang):
    sub = entry["sub"].get(lang) or entry["sub"]["fr"]
    pfx = _qf_prefix(lang)
    return f"{BASE}/{pfx}/{sub}/" if lang == "fr" else f"{BASE}/{lang}/{pfx}/{sub}/"


def _chips(f, lang, parking):
    out = []
    if _is_free(f):
        out.append(CHIP_LABELS["free"][lang])
    if _is_pmr(f):
        out.append(CHIP_LABELS["pmr"][lang])
    if f.get("slug") in parking:
        out.append(CHIP_LABELS["parking"][lang])
    if _has_winter(f):
        out.append(CHIP_LABELS["winter"][lang])
    return "".join(f'<span class="pill">{esc(c)}</span>' for c in out)


def _member_card(f, lang, parking):
    name = fiche_name(f, lang)
    i18n = f.get("i18n", {})
    desc = i18n.get(lang, {}).get("meta_description") or i18n.get("fr", {}).get("meta_description") or ""
    hero = f.get("hero_image") or ""
    thumb = (f'<img class="thumb" loading="lazy" src="{esc(hero)}" alt="{esc(name)}">'
             if _real_photo(f) else "")
    commune = esc(f.get("commune") or "")
    return (
        '<article class="card sel">\n'
        f'  {thumb}<div class="selbody"><div class="ch"><h3>{esc(name)}</h3>'
        f'<span class="rive">{commune}</span></div>\n'
        f'  <div style="margin:4px 0 6px">{_chips(f, lang, parking)}</div>\n'
        f'  <p class="meta" style="font-size:14px">{esc(desc)}</p>\n'
        f'  <a class="fiche" href="{url_for(f["slug"], lang)}">{esc(L(UI["see_fiche"], lang))}</a></div>\n'
        '</article>'
    )


CSS2 = CSS + """
.card.sel{display:flex;gap:14px;align-items:flex-start}
.thumb{width:118px;height:88px;object-fit:cover;border-radius:9px;flex:0 0 auto;border:1px solid var(--line)}
.selbody{flex:1 1 auto;min-width:0}
.criteria{background:#eef4f2;border:1px solid #d6e6e2;border-radius:12px;padding:12px 16px;margin:14px 0;font-size:14px;color:var(--teal2)}
@media(max-width:480px){.card.sel{flex-direction:column}.thumb{width:100%;height:150px}}"""


def render_intent_page(entry, lang, fiches, parking, built_langs, siblings):
    members = [fiches[s] for s in entry["members"] if s in fiches]
    title, lead = entry["title"][lang], entry["lead"][lang]
    note = entry["criteria_note"][lang]
    # bucketed (itinerary) vs flat list
    if entry.get("buckets"):
        sections, used = [], set()
        for b in entry["buckets"]:
            grp = [f for f in members if f.get("category") in b["categories"] and f["slug"] not in used]
            used.update(f["slug"] for f in grp)
            if not grp:
                continue
            cards = "".join(_member_card(f, lang, parking) for f in grp)
            sections.append(f'<h2 style="color:var(--teal)">{esc(L(b["label"], lang))} · {len(grp)}</h2>'
                            f'<div class="cards">{cards}</div>')
        body = "".join(sections)
    else:
        cards = "".join(_member_card(f, lang, parking) for f in members)
        body = (f'<h2 style="color:var(--teal)">{esc(L(UI2["members"], lang))} · {len(members)}</h2>'
                f'<div class="cards">{cards}</div>')
    items = [{"@type": "ListItem", "position": i, "name": fiche_name(f, lang),
              "url": url_for(f["slug"], lang)} for i, f in enumerate(members, 1)]
    graph = {"@context": "https://schema.org",
             "@graph": [{"@type": "ItemList", "name": title, "itemListElement": items}]}
    canon = intent_page_url(entry, lang)
    alts = "".join(f'<link rel="alternate" hreflang="{l}" href="{intent_page_url(entry, l)}">'
                   for l in built_langs)
    # outbound navigation (topbar + breadcrumb + keepgoing + linked footer)
    anchor = entry.get("hub_anchor")
    parent_label = _hub_label(anchor or "que-faire", lang)
    parent_url = _cat_url(anchor, lang) if anchor else _qf_index_url(lang)
    crumbs = [(L(NAV_UI["home"], lang), _home_url(lang)),
              (parent_label, parent_url),
              (title, None)]
    graph["@graph"].append(_breadcrumb_node(canon, crumbs))
    topbar = _topbar(lang, crumbs)
    keepgoing_html = _keepgoing(lang, parent_label, parent_url, siblings, _qf_index_url(lang))
    footer_html = _linked_footer(lang)
    return f"""<!doctype html><html lang="{lang}"{_dir_attr(lang)}><head><script>document.documentElement.classList.add('js')</script>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} · {siteconfig.SITE_NAME}</title>
<meta name="description" content="{esc(lead[:158])}">
<link rel="canonical" href="{canon}">{alts}
<script type="application/ld+json">{json.dumps(graph, ensure_ascii=False)}</script>
<style>{CSS2}</style></head><body>{topbar}<div class="wrap">

<div class="kicker">{siteconfig.SITE_NAME} · {esc(_qf_prefix(lang).replace("-", " "))}</div>
<h1>{esc(title)}</h1>
<p class="lead">{esc(lead)}</p>

<div class="criteria"><b>{esc(UI2["criteria"][lang])}</b> — {esc(note)}</div>

{body}

{keepgoing_html}
{footer_html}
</div></body></html>"""


def _write_select_md(entry, lang, fiches):
    members = [fiches[s] for s in entry["members"] if s in fiches]
    lines = [f"# {entry['title'][lang]}", "", entry["lead"][lang], "",
             f"> {entry['criteria_note'][lang]}", ""]
    for f in members:
        nm = fiche_name(f, lang)
        lines.append(f"- [{nm}]({url_for(f['slug'], lang)}) — {f.get('commune', '')}"
                     f" · [md]({BASE}/content/{'en/' if lang == 'en' else ''}{f['slug']}.md)")
    lines += ["", f"Source: {intent_page_url(entry, lang)}", ""]
    out = os.path.join(SELECT_MD_DIR, f"{entry['id']}.md") if lang == "fr" \
        else os.path.join(SELECT_MD_DIR, "en", f"{entry['id']}.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write("\n".join(lines))


MARK2_A, MARK2_B = "<!--intent-pages:start-->", "<!--intent-pages:end-->"
MARK3_A, MARK3_B = "<!--hub-bestof:start-->", "<!--hub-bestof:end-->"
MARK4_A, MARK4_B = "<!--hub-intent:start-->", "<!--hub-intent:end-->"

# FIX C — honest category-hub → intent-page links for hubs that carry NO
# hub_anchor best-of callout. Class B pages only (12-lang, clean — no FR
# fallback). Conservative: only defensible topical matches are listed; every
# other empty hub (voies-vertes, baignade-nautisme, sensations-plein-air,
# sorties-detente, sport-jeux) has no honest single match and is served by the
# que-faire index instead — relevance beats coverage, no forced matches.
# The 4 hub_anchor hubs (cascades, points-de-vue, chateaux, stations-de-ski)
# already carry their best-of callout via _inject_hub_bestof.
# HANDOFF-73: per-site content, so it lives in data/, not here. Hardcoded, it
# put "Les plus beaux points de vue sur le Mont-Blanc" on the Savoie
# télécabines hub in six locales — a link to another département's massif,
# pointing at a page that does not exist on this site.
_HIM_PATH = os.path.join(ROOT, "data", "hub-intent-map.json")
HUB_INTENT_MAP = ((json.load(open(_HIM_PATH, encoding="utf-8")).get("map") or {})
                  if os.path.exists(_HIM_PATH) else {})


def _inject_hub_bestof(entry, lang):
    """Reachability from CATEGORY hubs: a best-of page with a natural hub home
    (registry `hub_anchor`, e.g. plus-belles-cascades → cascades) gets a callout
    injected into that hub, so a cascades visitor reaches the ranked selection.
    Localized hub dir per lang; facts langs fall back to the FR-canonical dir."""
    anchor = entry.get("hub_anchor")
    if not anchor:
        return
    hub_dir = _hub_dir(anchor, lang)
    path = os.path.join(ROOT, hub_dir, "index.html") if lang == "fr" \
        else os.path.join(ROOT, lang, hub_dir, "index.html")
    if not os.path.exists(path):
        return
    html = open(path, encoding="utf-8").read()
    html = _re.sub(r"\s*" + _re.escape(MARK3_A) + r".*?" + _re.escape(MARK3_B), "", html, flags=_re.S)
    label = esc(L(UI["our_selection"], lang))
    title = esc(entry["title"][lang])
    block = (MARK3_A
             + '<section class="hub-bestof" style="max-width:1080px;margin:14px auto 0;padding:0 18px">'
             + f'<a href="{intent_page_url(entry, lang)}" style="display:block;background:#eef4f2;'
             'border:1px solid #d6e6e2;border-radius:12px;padding:12px 16px;color:#1F6E78;'
             f'font-weight:600;text-decoration:none">★ {label} — {title} →</a></section>' + MARK3_B)
    if "<main>" in html:
        html = html.replace("<main>", block + "\n<main>", 1)
    else:
        html = html.replace("</body>", block + "\n</body>", 1)
    open(path, "w", encoding="utf-8").write(html)


def _inject_hub_intent(hub_dir, entries, lang):
    """FIX C: 'Notre sélection' callout linking honest-match intent pages into a
    category hub with no hub_anchor best-of. entries = buildable page dicts for
    this lang. Placed above the footer (byte-stable), 12-lang via Class B pages."""
    dirn = _hub_dir(hub_dir, lang)
    path = os.path.join(ROOT, dirn, "index.html") if lang == "fr" \
        else os.path.join(ROOT, lang, dirn, "index.html")
    if not os.path.exists(path):
        return
    html = open(path, encoding="utf-8").read()
    html = _re.sub(r"\s*" + _re.escape(MARK4_A) + r".*?" + _re.escape(MARK4_B), "", html, flags=_re.S)
    label = esc(L(UI["our_selection"], lang))
    links = "".join(
        f'<a href="{intent_page_url(e, lang)}" style="display:inline-block;margin:3px 12px 3px 0;'
        f'color:#1F6E78;font-weight:600;text-decoration:none">★ {esc(e["title"][lang])} →</a>'
        for e in entries)
    block = (MARK4_A + '<section class="hub-intent" style="max-width:1080px;margin:14px auto 0;padding:0 18px">'
             '<div style="background:#eef4f2;border:1px solid #d6e6e2;border-radius:12px;padding:12px 16px">'
             f'<b style="color:#155059">{label}</b><br>{links}</div></section>' + MARK4_B)
    html = _place_above_footer(html, block)
    open(path, "w", encoding="utf-8").write(html)


def _inject_qf_links(pages, lang):
    """Reachability: link every built intent page from the (localized) que-faire hub."""
    pfx = _qf_prefix(lang)
    path = os.path.join(ROOT, pfx, "index.html") if lang == "fr" \
        else os.path.join(ROOT, lang, pfx, "index.html")
    if not os.path.exists(path):
        return
    html = open(path, encoding="utf-8").read()
    html = _re.sub(r"\s*" + _re.escape(MARK2_A) + r".*?" + _re.escape(MARK2_B), "", html, flags=_re.S)
    links = "".join(
        f'<a href="{intent_page_url(e, lang)}" style="display:inline-block;margin:2px 10px 2px 0;'
        f'color:#1F6E78;font-weight:600">{esc(e["title"][lang])} →</a>'
        for e in pages)
    block = (MARK2_A + '<nav class="intent-pages" style="max-width:1080px;margin:18px auto;padding:0 18px">'
             + links + '</nav>' + MARK2_B)
    # inside <main> (visible) not below the footer; facts-lang que-faire index
    # has no <main> → insert just above the footer.
    html = _place_above_footer(html, block)
    open(path, "w", encoding="utf-8").write(html)


def build_intent_pages():
    membership, fiches = compute_membership()
    parking = set(json.loads(open(os.path.join(ROOT, "data", "parking_index.json"),
                                  encoding="utf-8").read()).keys())
    written, skipped = 0, []
    entries = list(membership.values())

    def _built_langs(e):
        return [l for l in e["title"] if e["lead"].get(l) and e["criteria_note"].get(l)]
    for entry in entries:
        built_langs = _built_langs(entry)
        if len(entry["members"]) < 6:
            skipped.append(f"{entry['id']} ({len(entry['members'])} members)")
            continue
        for lang in built_langs:
            # sibling intent pages built in this lang (the keepgoing nav)
            siblings = [(e["title"][lang], intent_page_url(e, lang))
                        for e in entries
                        if e["id"] != entry["id"] and len(e["members"]) >= 6
                        and lang in _built_langs(e)]
            html = render_intent_page(entry, lang, fiches, parking, built_langs, siblings)
            sub = entry["sub"].get(lang) or entry["sub"]["fr"]
            out = os.path.join(ROOT, _qf_prefix(lang), sub, "index.html") if lang == "fr" \
                else os.path.join(ROOT, lang, _qf_prefix(lang), sub, "index.html")
            os.makedirs(os.path.dirname(out), exist_ok=True)
            open(out, "w", encoding="utf-8").write(html)
            _write_select_md(entry, lang, fiches)
            written += 1
    # Reachability injection — derive langs from what actually built (no
    # hardcoded ("fr","en") literal that strands new languages, the "line 40"
    # class of bug). A lang is wired if it has ≥1 buildable page.
    all_langs = sorted({l for e in membership.values() for l in e["title"]})
    for lang in all_langs:
        buildable = [e for e in membership.values() if len(e["members"]) >= 6
                     and e["title"].get(lang) and e["lead"].get(lang) and e["criteria_note"].get(lang)]
        if not buildable:
            continue
        _inject_qf_links(buildable, lang)          # que-faire INDEX → every page
        for e in buildable:
            _inject_hub_bestof(e, lang)            # category HUB → its best-of page
    # FIX C — honest category-hub → intent-page links for the empty hubs.
    by_id = {e["id"]: e for e in membership.values()}
    fixc = 0
    for lang in all_langs:
        for hub_dir, page_ids in HUB_INTENT_MAP.items():
            ents = [by_id[pid] for pid in page_ids
                    if pid in by_id and len(by_id[pid]["members"]) >= 6
                    and by_id[pid]["title"].get(lang) and by_id[pid]["lead"].get(lang)
                    and by_id[pid]["criteria_note"].get(lang)]
            if ents:
                _inject_hub_intent(hub_dir, ents, lang)
                fixc += 1
    print(f"build_intent_pages: {written} page(s) written; "
          f"hub-intent callouts: {fixc}; "
          f"skipped(min_items<6): {', '.join(skipped) or 'none'}")


MARK5_A, MARK5_B = "<!--home-selections:start-->", "<!--home-selections:end-->"
# FIX D — top intent pages surfaced on the homepage (most authority on the
# site). Top-6 by search demand; all Class B (12-lang, clean localized URLs).
HOME_SELECTION_IDS = ["lac-annecy-en-famille", "quand-il-pleut-annecy", "gratuit-lac-annecy",
                      "1-jour-a-annecy", "plus-belles-cascades-haute-savoie", "chamonix-en-famille"]


def inject_home_selections():
    """FIX D: a compact 'Nos sélections' strip on every published homepage,
    linking the top intent pages (localized), just above the site footer.
    Idempotent + byte-stable. Must run LATE (after facet-hub link injection) so
    no later homepage rewrite strips it."""
    membership, _ = compute_membership()
    by_id = {e["id"]: e for e in membership.values()}
    ents = [by_id[i] for i in HOME_SELECTION_IDS if i in by_id]
    done = 0
    for lang in locales.VISIBLE:  # isolation-ok: nav strip injected into already-built homepages over the visible roster (no prose render)
        page_ents = [e for e in ents if len(e["members"]) >= 6 and e["title"].get(lang)
                     and e["lead"].get(lang) and e["criteria_note"].get(lang)]
        if not page_ents:
            continue
        path = os.path.join(ROOT, "index.html") if lang == "fr" \
            else os.path.join(ROOT, lang, "index.html")
        if not os.path.exists(path):
            continue
        html = open(path, encoding="utf-8").read()
        # strip the exact block only (NO leading \s* — the homepage is patched
        # chrome, not regenerated fresh, so strip+reinsert must be a true
        # byte-stable fixpoint; eating original whitespace would shift bytes).
        html = _re.sub(_re.escape(MARK5_A) + r".*?" + _re.escape(MARK5_B), "", html, flags=_re.S)
        label = esc(L(UI["our_selection"], lang))
        links = "".join(
            f'<a href="{intent_page_url(e, lang)}" style="display:inline-block;margin:4px 14px 4px 0;'
            f'color:#1F6E78;font-weight:600;text-decoration:none">★ {esc(e["title"][lang])} →</a>'
            for e in page_ents)
        block = (MARK5_A + f'<section class="home-selections"{_dir_attr(lang)} '
                 'style="max-width:1080px;margin:26px auto;padding:16px 18px;background:#eef4f2;'
                 'border:1px solid #d6e6e2;border-radius:14px">'
                 f'<h2 style="margin:0 0 8px;font-size:17px;color:#155059">{esc(label)}</h2>'
                 f'<div>{links}</div></section>' + MARK5_B)
        idx = html.rfind('<footer class="site"')
        if idx != -1:
            html = html[:idx] + block + html[idx:]
        else:
            html = html.replace("</body>", block + "</body>", 1)
        open(path, "w", encoding="utf-8").write(html)
        done += 1
    print(f"inject_home_selections: strip injected on {done} homepage(s)")


if __name__ == "__main__":
    if "--home-selections" in sys.argv:
        inject_home_selections()
    else:
        main()
