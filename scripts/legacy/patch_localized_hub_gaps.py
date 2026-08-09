#!/usr/bin/env python3
"""Append a minimal 'See also' link list to each localized hub for fiches
that exist as HTML in that language but aren't in the hub's main listing.
Targets the residual orphans after Tasks 1-4 (fiches not in lieux.json)."""
import os, re
from pathlib import Path

ROOT = Path("/home/user/Loisir-74")
BASE = "https://loisirs74.fr"

# (orphan_slug, fr_hub_slug) — only for slugs we've confirmed exist as HTML in
# all 4 localized languages and belong to a known FR hub.
ORPHAN_FR_HUB = {
    "alpine-coaster-les-planards-chamonix": "attractions",
    "bar-a-jeux-youri-bar-cran-gevrier": "attractions",
    "base-de-loisirs-orange-montisel-saint-sixt": "bases-de-loisirs",
    "bureau-des-guides-annecy": "attractions",
    "c-l-aventure-ville-la-grand": "attractions",
    "devalkart-de-manigod": "attractions",
    "disc-golf-indiana-ventures-samoens": "attractions",
    "k2-parapente-doussard": "attractions",
    "lancer-de-hache-hachetag-annemasse": "attractions",
    "lancer-de-hache-l-hachez-vous-annecy": "attractions",
    "parc-de-peche-domaine-du-moulin-authier": "bases-de-loisirs",
    "vr-hypnotik-room-jumpers-fillinges": "attractions",
}

# Localized hub slug per (lang, fr_hub)
LANG_HUB = {
    "de/": {"attractions": "attraktionen", "bases-de-loisirs": "freizeitparks"},
    "en/": {"attractions": "attractions", "bases-de-loisirs": "leisure-parks"},
    "es/": {"attractions": "atraciones", "bases-de-loisirs": "areas-de-ocio"},
    "it/": {"attractions": "attrazioni", "bases-de-loisirs": "aree-recreative"},
}

# Localized "See also" heading
SEE_ALSO = {
    "de/": "Weitere Aktivitäten",
    "en/": "More activities",
    "es/": "Más actividades",
    "it/": "Altre attività",
}


def fiche_name(slug):
    """Extract the localized fiche name from its HTML title or h1."""
    return slug.replace("-", " ").title()


def patch_hub(path, lang_prefix, slugs):
    s = path.read_text(encoding="utf-8")
    heading = SEE_ALSO[lang_prefix]
    items = "\n".join(
        f'    <li><a href="{BASE}/{lang_prefix}{slug}">{fiche_name(slug)}</a></li>'
        for slug in slugs
    )
    block = (
        f'\n<section class="block see-also-orphans"><div class="wrap">'
        f'<h3 style="font-size:1rem;text-transform:uppercase;letter-spacing:.06em;color:var(--ink-mute,#6a727d);margin-bottom:.85rem;">{heading}</h3>'
        f'<ul style="display:grid;grid-template-columns:repeat(auto-fill,minmax(18rem,1fr));gap:.5rem;list-style:none;padding-left:0;">'
        f'\n{items}\n</ul></div></section>\n'
    )
    # Skip if we've already inserted (idempotent)
    if "see-also-orphans" in s:
        return False
    # Insert before <footer class="site"
    s2, n = re.subn(r'(<footer class="site")', block + r'\1', s, count=1)
    if n == 0:
        return False
    path.write_text(s2, encoding="utf-8")
    return True


def main():
    # Group orphans by fr_hub
    by_hub = {}
    for slug, hub in ORPHAN_FR_HUB.items():
        by_hub.setdefault(hub, []).append(slug)
    patched = 0
    for lang_prefix, hub_map in LANG_HUB.items():
        for fr_hub, slugs in by_hub.items():
            loc_hub = hub_map[fr_hub]
            path = ROOT / lang_prefix / loc_hub / "index.html"
            if not path.exists():
                continue
            if patch_hub(path, lang_prefix, slugs):
                patched += 1
                print(f"  + {path.relative_to(ROOT)} ({len(slugs)} links)")
    # plateau-de-beauregard is EN-only viewpoint — add it manually to en/viewpoints
    en_vp = ROOT / "en" / "viewpoints" / "index.html"
    if en_vp.exists():
        s = en_vp.read_text(encoding="utf-8")
        if "plateau-de-beauregard" not in s and "see-also-orphans" not in s:
            heading = "More viewpoints"
            block = (
                f'\n<section class="block see-also-orphans"><div class="wrap">'
                f'<h3 style="font-size:1rem;text-transform:uppercase;letter-spacing:.06em;color:var(--ink-mute,#6a727d);margin-bottom:.85rem;">{heading}</h3>'
                f'<ul style="display:grid;grid-template-columns:repeat(auto-fill,minmax(18rem,1fr));gap:.5rem;list-style:none;padding-left:0;">'
                f'\n    <li><a href="{BASE}/en/plateau-de-beauregard">Plateau De Beauregard</a></li>'
                f'\n</ul></div></section>\n'
            )
            s2, n = re.subn(r'(<footer class="site")', block + r'\1', s, count=1)
            if n:
                en_vp.write_text(s2, encoding="utf-8")
                patched += 1
                print(f"  + en/viewpoints/index.html (plateau-de-beauregard)")
    print(f"Patched: {patched} hub pages")


if __name__ == "__main__":
    main()
