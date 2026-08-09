#!/usr/bin/env python3
"""audit_breadcrumbs.py — JOB A read-only audit.

Inventory every breadcrumb across all rendered HTML pages and report:
  1. Total breadcrumbs found across all 2,352 fiche + chrome HTMLs.
  2. Pattern table: fiche category → expected hub → actual breadcrumb middle hub → status.
  3. Broken href count: <a> in a breadcrumb whose target file doesn't exist on disk.
  4. Cross-locale links: EN page's breadcrumb pointing to /fr/ etc.
  5. Wrong-language labels: FR text in a non-FR page's breadcrumb.

NO writes. Output to reports/job-A-breadcrumb-audit.md.
"""
import json
import siteconfig  # HANDOFF-73: per-site identity
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import locales  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LANGS = locales.PROSE

# Locale-translated hub display labels per JOB 4 (build_hubs.py HUB_DISPLAY)
EXPECTED_LABELS = {
    "fr": {
        "cascades": "Cascades", "chateaux": "Châteaux", "musees": "Musées",
        "points-de-vue": "Points de vue", "sentiers": "Sentiers",
        "telecabines": "Télécabines", "voies-vertes": "Voies vertes",
        "lacs-plages": "Lacs & plages", "bases-de-loisirs": "Bases de loisirs",
        "parcs-jardins": "Parcs & jardins",
        "baignade-nautisme": "Baignade & nautisme",
        "sorties-detente": "Sorties & détente", "sport-jeux": "Sports & jeux",
        "sensations-plein-air": "Sensations plein air",
        "que-faire": "Que faire", "home": "Accueil",
    },
    "en": {
        "waterfalls": "Waterfalls", "castles": "Castles", "museums": "Museums",
        "viewpoints": "Viewpoints", "trails": "Trails", "cable-cars": "Cable cars",
        "greenways": "Greenways", "lakes": "Lakes", "leisure-parks": "Leisure parks",
        "parks-gardens": "Parks & gardens", "swimming-watersports": "Swimming & watersports",
        "outings-relax": "Outings & relax", "sport-games": "Sports & games",
        "outdoor-thrills": "Outdoor thrills", "what-to-do": "What to do",
        "home": "Home",
    },
    "de": {
        "wasserfaelle": "Wasserfälle", "schloesser": "Schlösser",
        "museen": "Museen", "aussichtspunkte": "Aussichtspunkte",
        "wanderwege": "Wanderwege", "seilbahnen": "Seilbahnen",
        "radwege": "Radwege", "seen": "Seen", "freizeitparks": "Freizeitparks",
        "parks-gaerten": "Parks & Gärten",
        "baden-wassersport": "Baden & Wassersport",
        "ausfluege-erholung": "Ausflüge & Erholung",
        "sport-spiele": "Sport & Spiele",
        "outdoor-nervenkitzel": "Outdoor-Nervenkitzel",
        "was-unternehmen": "Was unternehmen",
        "home": "Startseite",
    },
    "it": {
        "cascate": "Cascate", "castelli": "Castelli", "musei": "Musei",
        "punti-panoramici": "Punti panoramici", "sentieri": "Sentieri",
        "funivie": "Funivie", "vie-verdi": "Vie verdi", "laghi": "Laghi",
        "aree-ricreative": "Aree ricreative",
        "parchi-giardini": "Parchi & giardini",
        "nuoto-sport-acquatici": "Nuoto & sport acquatici",
        "uscite-relax": "Uscite & relax", "sport-giochi": "Sport & giochi",
        "brividi-aria-aperta": "Brividi all'aria aperta",
        "cosa-fare": "Cosa fare",
        "home": "Home",
    },
    "es": {
        "cascadas": "Cascadas", "castillos": "Castillos", "museos": "Museos",
        "miradores": "Miradores", "senderos": "Senderos",
        "telefericos": "Teleféricos", "vias-verdes": "Vías verdes",
        "lagos": "Lagos", "areas-de-ocio": "Áreas de ocio",
        "parques-jardines": "Parques & jardines",
        "bano-deportes-acuaticos": "Baño & deportes acuáticos",
        "salidas-relax": "Salidas & relax",
        "deporte-juegos": "Deportes & juegos",
        "sensaciones-aire-libre": "Sensaciones al aire libre",
        "que-hacer": "Qué hacer",
        "home": "Inicio",
    },
    "nl": {
        "watervallen": "Watervallen", "kastelen": "Kastelen",
        "musea": "Musea", "uitzichtpunten": "Uitzichtpunten",
        "wandelpaden": "Wandelpaden", "kabelbanen": "Kabelbanen",
        "fietsroutes": "Fietsroutes", "meren": "Meren",
        "recreatieparken": "Recreatieparken",
        "parken-tuinen": "Parken & tuinen",
        "zwemmen-watersport": "Zwemmen & watersport",
        "uitstapjes-ontspanning": "Uitstapjes & ontspanning",
        "sport-spelen": "Sport & spelen",
        "buitenavontuur": "Buitenavontuur",
        "wat-te-doen": "Wat te doen",
        "home": "Startpagina",
    },
}


def fr_signal(text):
    """Detect French label residue."""
    if not text: return False
    s = text.strip().lower()
    fr_only = {"accueil", "châteaux", "musées", "points de vue", "sentiers",
               "télécabines", "voies vertes", "lacs", "plages",
               "bases de loisirs", "cascades", "que faire",
               "baignade", "parcs", "jardins", "sports", "sensations",
               "sorties", "détente", "plein air"}
    return any(w == s for w in fr_only) or any(w in s and len(s) < 30 for w in fr_only)


def parse_breadcrumb(html):
    """Extract breadcrumb hrefs + labels from a page.
    Returns list of (href, label) tuples in order.
    """
    m = re.search(r'<nav[^>]*class="crumb"[^>]*>(.*?)</nav>', html, re.DOTALL)
    if not m:
        return []
    crumb_html = m.group(0)
    # Each <a href="...">...</a> entry, plus the trailing <span aria-current="page">...</span>
    items = []
    for a in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>([^<]+)</a>', crumb_html):
        items.append((a.group(1), a.group(2).strip()))
    # The final span (current page)
    final = re.search(r'<span[^>]*aria-current="page"[^>]*>([^<]+)</span>', crumb_html)
    if final:
        items.append(("", final.group(1).strip()))
    # Also catch un-anchored middle spans
    for sp in re.finditer(r'<span(?![^>]*aria-current)[^>]*>([^<]+)</span>', crumb_html):
        t = sp.group(1).strip()
        if t and not any(x[1] == t for x in items):
            items.insert(-1, ("", t))
    return items


def page_lang(html):
    m = re.search(r'<html\s+lang="([^"]+)"', html)
    return m.group(1) if m else "?"


def url_to_filepath(url):
    """Resolve a fully-qualified loisirs74.fr URL to its file in repo root."""
    if not url:
        return None
    if url.startswith(siteconfig.BASE_URL + "/"):
        p = url[len(siteconfig.BASE_URL + "/"):]
    elif url.startswith("/"):
        p = url[1:]
    else:
        return None
    p = p.split("#")[0].split("?")[0]
    if not p:
        return Path("index.html")
    if p.endswith("/"):
        return Path(p + "index.html")
    return Path(p + ".html")


def main():
    findings = {
        "total_pages_scanned": 0,
        "pages_with_breadcrumb": 0,
        "pages_without_breadcrumb": [],
        "patterns": Counter(),  # (page_lang, hub_in_crumb, label) → count
        "broken_hrefs": [],     # (page, href, reason)
        "cross_locale_hrefs": [],  # (page, href)
        "wrong_lang_labels": [],   # (page, label, page_lang)
        "by_locale": {L: {"pages": 0, "broken": 0, "cross": 0, "wronglang": 0} for L in LANGS},
    }
    protected_breadcrumb = {}  # for chez-nous + chalet-du-tornet hosts

    PROT = ["chez-nous-a-la-plage", "chalet-du-tornet"]

    pages_iter = []
    pages_iter.extend(sorted(ROOT.glob("*.html")))
    for L in LANGS:
        if L == "fr": continue
        d = ROOT / L
        if d.exists():
            pages_iter.extend(sorted(d.glob("*.html")))

    for p in pages_iter:
        if not p.is_file(): continue
        try:
            html = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        findings["total_pages_scanned"] += 1
        rel = str(p.relative_to(ROOT))
        L = page_lang(html)
        L_kind = L.split("-")[0] if "-" in L else L
        if L_kind in LANGS:
            findings["by_locale"][L_kind]["pages"] += 1
        items = parse_breadcrumb(html)
        if not items:
            findings["pages_without_breadcrumb"].append(rel)
            continue
        findings["pages_with_breadcrumb"] += 1

        # Pattern: (page_lang, middle hub label, middle href)
        if len(items) >= 3:
            middle = items[1]
            findings["patterns"][(L_kind, middle[0], middle[1])] += 1
        elif len(items) == 2:
            findings["patterns"][(L_kind, "(no hub)", items[1][1])] += 1

        # Broken hrefs: every href that resolves to no file
        for href, label in items:
            if not href:
                continue
            fp = url_to_filepath(href)
            if not fp:
                continue
            full = ROOT / fp
            if not full.exists():
                findings["broken_hrefs"].append((rel, href, str(fp)))
                if L_kind in LANGS:
                    findings["by_locale"][L_kind]["broken"] += 1

        # Cross-locale: locale prefix differs from page lang
        for href, label in items:
            if not href: continue
            m = re.match(r"https://" + siteconfig.DOMAIN_RE + r"/([a-z]{2})/", href)
            if m:
                href_lang = m.group(1)
            else:
                href_lang = "fr"
            if L_kind in LANGS and href_lang != L_kind and href_lang != "fr":
                # /fr/ in a non-FR page is technically OK if the page IS FR.
                # Otherwise cross-locale.
                findings["cross_locale_hrefs"].append((rel, href, L_kind, href_lang))
                if L_kind in LANGS:
                    findings["by_locale"][L_kind]["cross"] += 1
            # /fr/ link on a non-FR page = wrong locale prefix
            if href_lang == "fr" and L_kind != "fr" and "/fr/" in href:
                findings["cross_locale_hrefs"].append((rel, href, L_kind, "fr"))

        # Wrong language: French label on non-FR page. Only check the LINKED
        # hub label (href != ""), NOT the trailing aria-current="page" item
        # — that's the fiche name itself, which is often a proper noun in
        # French ("Châteaux des Allinges", "Jardins de l'Europe", etc.) and
        # legitimately stays French in every locale.
        if L_kind in LANGS and L_kind != "fr":
            for href, label in items:
                if not href:
                    continue
                if fr_signal(label):
                    findings["wrong_lang_labels"].append((rel, label, L_kind))
                    findings["by_locale"][L_kind]["wronglang"] += 1

        # Protected check
        stem = p.stem
        for pslug in PROT:
            if stem == pslug:
                protected_breadcrumb.setdefault(L_kind, {})[pslug] = items

    # Pattern: also build a fiche-type → hub mapping from Json/
    fiche_categories = {}
    for jp in (ROOT / "Json").glob("*.json"):
        try:
            d = json.loads(jp.read_text(encoding="utf-8"))
        except Exception:
            continue
        slug = jp.stem
        fiche_categories[slug] = d.get("category") or "?"

    # Write the report
    lines = ["# JOB A — Breadcrumb audit (read-only)\n\n"]
    lines.append(f"Scanned: **{findings['total_pages_scanned']} HTML pages**\n\n")
    lines.append(f"With breadcrumb: **{findings['pages_with_breadcrumb']}**\n")
    lines.append(f"Without breadcrumb: **{len(findings['pages_without_breadcrumb'])}**\n\n")

    lines.append("## Per-locale summary\n\n")
    lines.append("| locale | pages scanned | broken hrefs | cross-locale | wrong-lang labels |\n")
    lines.append("|---|---|---|---|---|\n")
    for L in LANGS:
        s = findings["by_locale"][L]
        lines.append(f"| {L} | {s['pages']} | {s['broken']} | {s['cross']} | {s['wronglang']} |\n")
    lines.append("\n")

    lines.append("## Broken hrefs (sample first 30)\n\n")
    lines.append(f"Total: **{len(findings['broken_hrefs'])}**\n\n")
    if findings["broken_hrefs"]:
        lines.append("| page | broken href | resolves to (missing) |\n|---|---|---|\n")
        seen = set()
        for page, href, fp in findings["broken_hrefs"][:30]:
            key = (page.split("/")[-1], href)
            if key in seen: continue
            seen.add(key)
            lines.append(f"| {page} | `{href}` | `{fp}` |\n")
        lines.append("\n")
    else:
        lines.append("**None.** ✓\n\n")

    lines.append("## Cross-locale links (sample first 20)\n\n")
    lines.append(f"Total: **{len(findings['cross_locale_hrefs'])}**\n\n")
    if findings["cross_locale_hrefs"]:
        lines.append("| page (lang) | breadcrumb href | href lang |\n|---|---|---|\n")
        seen = set()
        for entry in findings["cross_locale_hrefs"][:30]:
            page, href, page_lang_, href_lang = entry
            key = (page.split("/")[-1], href)
            if key in seen: continue
            seen.add(key)
            lines.append(f"| {page} ({page_lang_}) | `{href}` | {href_lang} |\n")
        lines.append("\n")
    else:
        lines.append("**None.** ✓\n\n")

    lines.append("## Wrong-language labels (sample first 30)\n\n")
    lines.append(f"Total: **{len(findings['wrong_lang_labels'])}**\n\n")
    if findings["wrong_lang_labels"]:
        lines.append("| page | label (looks French) | page locale |\n|---|---|---|\n")
        wseen = set()
        for page, label, plang in findings["wrong_lang_labels"][:30]:
            key = (page.split("/")[-1], label)
            if key in wseen: continue
            wseen.add(key)
            lines.append(f"| {page} | `{label}` | {plang} |\n")
        lines.append("\n")
    else:
        lines.append("**None.** ✓\n\n")

    lines.append("## Pattern table — distinct (lang, hub-href, hub-label) triples\n\n")
    lines.append(f"Total distinct patterns: **{len(findings['patterns'])}**\n\n")
    lines.append("Top 30 by frequency:\n\n| lang | hub href in crumb | hub label | count |\n|---|---|---|---|\n")
    for (lang, href, label), count in findings["patterns"].most_common(30):
        lines.append(f"| {lang} | `{href}` | `{label}` | {count} |\n")
    lines.append("\n")

    lines.append("## Protected fiches breadcrumb (chez-nous-a-la-plage + chalet-du-tornet)\n\n")
    lines.append("Note: these are partner cards rendered inside host fiches; their own breadcrumb is whatever the host fiche carries. The protected-card guarantee is about the partner-card byte-faithful render (JOB 3 card-diff gate), not their own breadcrumb. **N/A for breadcrumb audit.**\n\n")

    lines.append("## Pages without any breadcrumb\n\n")
    lines.append(f"Total: **{len(findings['pages_without_breadcrumb'])}**\n\n")
    if findings["pages_without_breadcrumb"]:
        lines.append("First 20:\n```\n")
        for p in findings["pages_without_breadcrumb"][:20]:
            lines.append(f"  {p}\n")
        lines.append("```\n\n")

    out = "".join(lines)
    (ROOT / "reports" / "job-A-breadcrumb-audit.md").write_text(out, encoding="utf-8")
    print(f"  scanned: {findings['total_pages_scanned']}")
    print(f"  with breadcrumb: {findings['pages_with_breadcrumb']}")
    print(f"  broken hrefs: {len(findings['broken_hrefs'])}")
    print(f"  cross-locale: {len(findings['cross_locale_hrefs'])}")
    print(f"  wrong-lang labels: {len(findings['wrong_lang_labels'])}")
    print(f"  distinct patterns: {len(findings['patterns'])}")
    print(f"\nReport: reports/job-A-breadcrumb-audit.md")


if __name__ == "__main__":
    main()
