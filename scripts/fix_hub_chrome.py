#!/usr/bin/env python3
"""fix_hub_chrome.py — localize the FR chrome strings stuck in non-FR hub indexes.

After the JOB B breadcrumb fix and the sensations-plein-air/que-faire
regeneration (commit e287d0c1), the 15 hub directories per locale all
exist with locale-prefixed slugs and locale-correct card URLs. But the
*static chrome* of each hub index — breadcrumb labels, filter-bar text,
"read more" toggle, count labels, JS counter strings — was still hard-
coded French across all 5 non-FR locales (14/15 hubs each).

This script patches every non-FR hub index in place with locale strings.
Idempotent: only replaces when the FR original is currently present.

Strings localized (per hub × 5 locales):
  - Breadcrumb root link target + label ("Accueil" → "Home"/"Startseite"/...)
  - Breadcrumb hub label ("Cascades" → "Waterfalls"/"Wasserfälle"/...)
  - SEO "more" toggle ("Lire la suite" → "Read more"/...)
  - Filter-bar count label + JS counter consts ("lieu(x) affiché(s)" → ...)
  - Filters toggle ("Filtres" → "Filters"/...)
  - Filter panel: Commune / Accès / Tri labels + their options
"""
import re
import siteconfig  # HANDOFF-73: per-site identity
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import locales  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LOCS = locales.PROSE_SECONDARY

HUB_LOCALE_SLUGS = {
    "cascades":            {"en":"waterfalls","de":"wasserfaelle","it":"cascate","es":"cascadas","nl":"watervallen"},
    "chateaux":            {"en":"castles","de":"schloesser","it":"castelli","es":"castillos","nl":"kastelen"},
    "musees":              {"en":"museums","de":"museen","it":"musei","es":"museos","nl":"musea"},
    "points-de-vue":       {"en":"viewpoints","de":"aussichtspunkte","it":"punti-panoramici","es":"miradores","nl":"uitzichtpunten"},
    "sentiers":            {"en":"trails","de":"wanderwege","it":"sentieri","es":"senderos","nl":"wandelpaden"},
    "telecabines":         {"en":"cable-cars","de":"seilbahnen","it":"funivie","es":"telefericos","nl":"kabelbanen"},
    "voies-vertes":        {"en":"greenways","de":"radwege","it":"vie-verdi","es":"vias-verdes","nl":"fietsroutes"},
    "lacs-plages":         {"en":"lakes","de":"seen","it":"laghi","es":"lagos","nl":"meren"},
    "bases-de-loisirs":    {"en":"leisure-parks","de":"freizeitparks","it":"aree-ricreative","es":"areas-de-ocio","nl":"recreatieparken"},
    "baignade-nautisme":   {"en":"swimming-watersports","de":"baden-wassersport","it":"nuoto-sport-acquatici","es":"bano-deportes-acuaticos","nl":"zwemmen-watersport"},
    "parcs-jardins":       {"en":"parks-gardens","de":"parks-gaerten","it":"parchi-giardini","es":"parques-jardines","nl":"parken-tuinen"},
    "que-faire":           {"en":"what-to-do","de":"was-unternehmen","it":"cosa-fare","es":"que-hacer","nl":"wat-te-doen"},
    "sensations-plein-air":{"en":"outdoor-thrills","de":"outdoor-nervenkitzel","it":"brividi-aria-aperta","es":"sensaciones-aire-libre","nl":"buitenavontuur"},
    "sorties-detente":     {"en":"outings-relax","de":"ausfluege-erholung","it":"uscite-relax","es":"salidas-relax","nl":"uitstapjes-ontspanning"},
    "sport-jeux":          {"en":"sport-games","de":"sport-spiele","it":"sport-giochi","es":"deporte-juegos","nl":"sport-spelen"},
}

HUB_DISPLAY = {
    "cascades":            {"fr":"Cascades","en":"Waterfalls","de":"Wasserfälle","it":"Cascate","es":"Cascadas","nl":"Watervallen"},
    "chateaux":            {"fr":"Châteaux","en":"Castles","de":"Schlösser","it":"Castelli","es":"Castillos","nl":"Kastelen"},
    "musees":              {"fr":"Musées","en":"Museums","de":"Museen","it":"Musei","es":"Museos","nl":"Musea"},
    "points-de-vue":       {"fr":"Points de vue","en":"Viewpoints","de":"Aussichtspunkte","it":"Punti panoramici","es":"Miradores","nl":"Uitzichtpunten"},
    "sentiers":            {"fr":"Sentiers","en":"Trails","de":"Wanderwege","it":"Sentieri","es":"Senderos","nl":"Wandelpaden"},
    "telecabines":         {"fr":"Télécabines","en":"Cable cars","de":"Seilbahnen","it":"Funivie","es":"Teleféricos","nl":"Kabelbanen"},
    "voies-vertes":        {"fr":"Voies vertes","en":"Greenways","de":"Radwege","it":"Vie verdi","es":"Vías verdes","nl":"Fietsroutes"},
    "lacs-plages":         {"fr":"Lacs & plages","en":"Lakes","de":"Seen","it":"Laghi","es":"Lagos","nl":"Meren"},
    "bases-de-loisirs":    {"fr":"Bases de loisirs","en":"Leisure parks","de":"Freizeitparks","it":"Aree ricreative","es":"Áreas de ocio","nl":"Recreatieparken"},
    "baignade-nautisme":   {"fr":"Baignade & nautisme","en":"Swimming & watersports","de":"Baden & Wassersport","it":"Nuoto & sport acquatici","es":"Baño & deportes acuáticos","nl":"Zwemmen & watersport"},
    "parcs-jardins":       {"fr":"Parcs & jardins","en":"Parks & gardens","de":"Parks & Gärten","it":"Parchi & giardini","es":"Parques & jardines","nl":"Parken & tuinen"},
    "que-faire":           {"fr":"Que faire ?","en":"What to do","de":"Was unternehmen","it":"Cosa fare","es":"Qué hacer","nl":"Wat te doen"},
    "sensations-plein-air":{"fr":"Sensations plein air","en":"Outdoor thrills","de":"Outdoor-Nervenkitzel","it":"Brividi all'aria aperta","es":"Sensaciones al aire libre","nl":"Buitenavontuur"},
    "sorties-detente":     {"fr":"Sorties & détente","en":"Outings & relax","de":"Ausflüge & Erholung","it":"Uscite & relax","es":"Salidas & relax","nl":"Uitstapjes & ontspanning"},
    "sport-jeux":          {"fr":"Sports & jeux","en":"Sports & games","de":"Sport & Spiele","it":"Sport & giochi","es":"Deportes & juegos","nl":"Sport & spelen"},
}

CHROME = {
    "Accueil":             {"en":"Home","de":"Startseite","it":"Home","es":"Inicio","nl":"Home"},
    "Lire la suite":       {"en":"Read more","de":"Mehr lesen","it":"Leggi tutto","es":"Leer más","nl":"Lees meer"},
    "lieu affiché":        {"en":"place shown","de":"Ort angezeigt","it":"luogo visualizzato","es":"lugar mostrado","nl":"plek weergegeven"},
    "lieux affichés":      {"en":"places shown","de":"Orte angezeigt","it":"luoghi visualizzati","es":"lugares mostrados","nl":"plekken weergegeven"},
    "Filtres":             {"en":"Filters","de":"Filter","it":"Filtri","es":"Filtros","nl":"Filters"},
    "Commune":             {"en":"Town","de":"Gemeinde","it":"Comune","es":"Municipio","nl":"Gemeente"},
    "Toutes les communes": {"en":"All towns","de":"Alle Gemeinden","it":"Tutti i comuni","es":"Todos los municipios","nl":"Alle gemeenten"},
    "Accès":               {"en":"Access","de":"Zugang","it":"Accesso","es":"Acceso","nl":"Toegang"},
    "Tous":                {"en":"All","de":"Alle","it":"Tutti","es":"Todos","nl":"Alle"},
    "Gratuit":             {"en":"Free","de":"Kostenlos","it":"Gratis","es":"Gratis","nl":"Gratis"},
    "Payant":              {"en":"Paid","de":"Kostenpflichtig","it":"A pagamento","es":"De pago","nl":"Betaald"},
    "Tri":                 {"en":"Sort","de":"Sortieren","it":"Ordina","es":"Ordenar","nl":"Sorteren"},
    "Par commune":         {"en":"By town","de":"Nach Gemeinde","it":"Per comune","es":"Por municipio","nl":"Op gemeente"},
}


def patch_one_hub(html, hub_canon, lang):
    """Return (new_html, n_replacements). Only touches static chrome blocks."""
    n = 0
    home = CHROME["Accueil"][lang]
    hub_label_fr = HUB_DISPLAY[hub_canon]["fr"]
    hub_label_loc = HUB_DISPLAY[hub_canon][lang]

    # 1. Breadcrumb root link target + label: <a href="https://loisirs74.fr/">Accueil</a>
    pat = f'<a href="{siteconfig.BASE_URL}/">Accueil</a>'
    new = f'<a href="{siteconfig.BASE_URL}/{lang}/">{home}</a>'
    if pat in html:
        html = html.replace(pat, new, 1)
        n += 1

    # 2. Breadcrumb hub label: <b>Cascades</b> (or <b>Châteaux</b> etc.)
    #    Only inside the breadcrumb nav (anchored to surrounding span sep).
    crumb_pat = re.compile(
        r'(<nav[^>]*class="crumb"[^>]*>.*?<span class="sep">/</span>\s*)<b>'
        + re.escape(hub_label_fr) + r'</b>',
        re.DOTALL,
    )
    new_html, k = crumb_pat.subn(lambda m: m.group(1) + f'<b>{hub_label_loc}</b>', html, count=1)
    if k:
        html = new_html
        n += 1

    # 3. SEO "more" toggle: <summary>Lire la suite</summary>
    pat = '<summary>Lire la suite</summary>'
    new = f'<summary>{CHROME["Lire la suite"][lang]}</summary>'
    if pat in html:
        html = html.replace(pat, new, 1)
        n += 1

    # 4. Count label: <span id="count-label">lieux affichés</span>
    pat = '<span id="count-label">lieux affichés</span>'
    new = f'<span id="count-label">{CHROME["lieux affichés"][lang]}</span>'
    if pat in html:
        html = html.replace(pat, new, 1)
        n += 1

    # 5. JS counter constants: const SG="lieu affiché",PL="lieux affichés"
    js_pat = re.compile(r'const\s+SG\s*=\s*"lieu affiché"\s*,\s*PL\s*=\s*"lieux affichés"')
    js_new = f'const SG="{CHROME["lieu affiché"][lang]}",PL="{CHROME["lieux affichés"][lang]}"'
    new_html, k = js_pat.subn(js_new, html, count=1)
    if k:
        html = new_html
        n += 1

    # 6. Filters toggle: <span>Filtres</span> (inside .filter-toggle button)
    ft_pat = re.compile(r'(<button[^>]*class="filter-toggle"[^>]*>\s*)<span>Filtres</span>', re.DOTALL)
    new_html, k = ft_pat.subn(lambda m: m.group(1) + f'<span>{CHROME["Filtres"][lang]}</span>', html, count=1)
    if k:
        html = new_html
        n += 1

    # 7. Filter panel labels (anchored to surrounding <label><span>X</span>):
    for fr_label in ("Commune", "Accès", "Tri"):
        loc_label = CHROME[fr_label][lang]
        lab_pat = re.compile(r'(<label>\s*)<span>' + re.escape(fr_label) + r'</span>', re.DOTALL)
        new_html, k = lab_pat.subn(lambda m, ll=loc_label: m.group(1) + f'<span>{ll}</span>', html, count=1)
        if k:
            html = new_html
            n += 1

    # 8. Commune select default option: <option value="">Toutes les communes</option>
    pat = '<option value="">Toutes les communes</option>'
    new = f'<option value="">{CHROME["Toutes les communes"][lang]}</option>'
    if pat in html:
        html = html.replace(pat, new, 1)
        n += 1

    # 9. Access filter buttons (inside .access-group div):
    ag_pat = re.compile(
        r'(<div[^>]*class="access-group"[^>]*id="filt-access"[^>]*>)\s*'
        r'<button class="active" data-v="all">Tous</button>\s*'
        r'<button data-v="free">Gratuit</button>\s*'
        r'<button data-v="paid">Payant</button>\s*'
        r'(</div>)',
        re.DOTALL,
    )
    def _access_repl(m):
        return (
            m.group(1)
            + f'<button class="active" data-v="all">{CHROME["Tous"][lang]}</button>'
            + f'<button data-v="free">{CHROME["Gratuit"][lang]}</button>'
            + f'<button data-v="paid">{CHROME["Payant"][lang]}</button>'
            + m.group(2)
        )
    new_html, k = ag_pat.subn(_access_repl, html, count=1)
    if k:
        html = new_html
        n += 1

    # 10. Sort select first option: <option value="commune">Par commune</option>
    pat = '<option value="commune">Par commune</option>'
    new = f'<option value="commune">{CHROME["Par commune"][lang]}</option>'
    if pat in html:
        html = html.replace(pat, new, 1)
        n += 1

    return html, n


def main():
    total_files = 0
    total_repls = 0
    for hub_canon, mp in HUB_LOCALE_SLUGS.items():
        for lang in LOCS:
            slug = mp[lang]
            p = ROOT / lang / slug / "index.html"
            if not p.exists():
                print(f"  ! [{lang}] {slug}/index.html missing")
                continue
            html = p.read_text(encoding="utf-8")
            new_html, n = patch_one_hub(html, hub_canon, lang)
            if n and new_html != html:
                p.write_text(new_html, encoding="utf-8")
                total_files += 1
                total_repls += n
                print(f"  [{lang}] {slug}: {n} chrome strings localized")
    print(f"\nfiles changed: {total_files}")
    print(f"total replacements: {total_repls}")


if __name__ == "__main__":
    main()
