#!/usr/bin/env python3
"""Task 4 — replace each hub's footer Categories list with the complete 12-other-hubs list."""
import os, re
from pathlib import Path

ROOT = Path("/home/user/Loisir-74")
BASE = "https://loisirs74.fr"

# Per-language: list of (hub_slug, long_label) in display order.
HUBS = {
    "": [
        ("lacs", "Lacs &amp; plages"),
        ("plages", "Plages"),
        ("cascades", "Cascades"),
        ("bases-de-loisirs", "Bases de loisirs"),
        ("points-de-vue", "Points de vue"),
        ("telecabines", "Télécabines"),
        ("musees", "Musées"),
        ("chateaux", "Châteaux &amp; forts"),
        ("voies-vertes", "Voies vertes"),
        ("sentiers", "Sentiers"),
        ("attractions", "Attractions &amp; loisirs"),
        ("divers", "Divers"),
        ("que-faire", "Que faire ?"),
    ],
    "de/": [
        ("seen", "Seen &amp; Strände"),
        ("straende", "Strände"),
        ("wasserfaelle", "Wasserfälle"),
        ("freizeitparks", "Freizeitparks"),
        ("aussichtspunkte", "Aussichtspunkte"),
        ("seilbahnen", "Seilbahnen"),
        ("museen", "Museen"),
        ("schloesser", "Schlösser &amp; Burgen"),
        ("radwege", "Radwege"),
        ("wanderwege", "Wanderwege"),
        ("attraktionen", "Attraktionen &amp; Freizeit"),
        ("sonstiges", "Sonstiges"),
        ("que-faire", "Was tun?"),
    ],
    "en/": [
        ("lakes", "Lakes &amp; beaches"),
        ("beaches", "Beaches"),
        ("waterfalls", "Waterfalls"),
        ("leisure-parks", "Leisure parks"),
        ("viewpoints", "Viewpoints"),
        ("cable-cars", "Cable cars"),
        ("museums", "Museums"),
        ("castles", "Castles &amp; forts"),
        ("greenways", "Greenways"),
        ("trails", "Trails"),
        ("attractions", "Attractions &amp; activities"),
        ("other", "Other"),
        ("que-faire", "What to do?"),
    ],
    "es/": [
        ("lagos", "Lagos y playas"),
        ("playas", "Playas"),
        ("cascadas", "Cascadas"),
        ("areas-de-ocio", "Áreas de ocio"),
        ("miradores", "Miradores"),
        ("telefericos", "Teleféricos"),
        ("museos", "Museos"),
        ("castillos", "Castillos y fortalezas"),
        ("vias-verdes", "Vías verdes"),
        ("senderos", "Senderos"),
        ("atraciones", "Atracciones y ocio"),
        ("otros", "Otros"),
        ("que-faire", "¿Qué hacer?"),
    ],
    "it/": [
        ("laghi", "Laghi &amp; spiagge"),
        ("spiagge", "Spiagge"),
        ("cascate", "Cascate"),
        ("aree-recreative", "Aree ricreative"),
        ("punti-panoramici", "Punti panoramici"),
        ("funivie", "Funivie"),
        ("musei", "Musei"),
        ("castelli", "Castelli &amp; forti"),
        ("vie-verdi", "Vie verdi"),
        ("sentieri", "Sentieri"),
        ("attrazioni", "Attrazioni &amp; svago"),
        ("altro", "Altro"),
        ("que-faire", "Cosa fare?"),
    ],
}

# Regex: find the Categories foot-col <ul>...</ul> block and replace its inner list.
# H4 word varies per language: Catégories / Kategorien / Categories / Categorías / Categorie
CAT_H4 = {"": "Catégories", "de/": "Kategorien", "en/": "Categories", "es/": "Categorías", "it/": "Categorie"}


def render_ul(hubs, current_slug, lang_prefix):
    parts = []
    for slug, label in hubs:
        if slug == current_slug:
            continue
        parts.append(f'<li><a href="{BASE}/{lang_prefix}{slug}/">{label}</a></li>')
    return "<ul>" + "".join(parts) + "</ul>"


def patch_hub(path, lang_prefix, current_slug):
    s = path.read_text(encoding="utf-8")
    h4_word = CAT_H4[lang_prefix]
    pattern = re.compile(
        r'(<h4>' + re.escape(h4_word) + r'</h4>\s*)<ul>.*?</ul>',
        re.DOTALL,
    )
    new_ul = render_ul(HUBS[lang_prefix], current_slug, lang_prefix)
    s2, n = pattern.subn(r"\1" + new_ul, s, count=1)
    if n > 0:
        path.write_text(s2, encoding="utf-8")
        return True
    # Fallback for /que-faire/ pages (different footer structure):
    # inject a new foot-col with the category list right before the foot-grid closer.
    qf_block = f'<div class="foot-col"><h4>{h4_word}</h4>{new_ul}</div>'
    pattern_b = re.compile(r'(</div>\s*<div class="foot-bottom")', re.DOTALL)
    s3, n2 = pattern_b.subn(qf_block + r'\1', s, count=1)
    if n2 == 0:
        return False
    path.write_text(s3, encoding="utf-8")
    return True


def main():
    patched = 0
    skipped = []
    for lang_prefix, hubs in HUBS.items():
        for hub_slug, _ in hubs:
            path = ROOT / lang_prefix / hub_slug / "index.html"
            if not path.exists():
                continue
            if patch_hub(path, lang_prefix, hub_slug):
                patched += 1
            else:
                skipped.append(str(path.relative_to(ROOT)))
    print(f"Patched: {patched} hub pages")
    if skipped:
        print(f"Skipped ({len(skipped)}): {skipped}")


if __name__ == "__main__":
    main()
