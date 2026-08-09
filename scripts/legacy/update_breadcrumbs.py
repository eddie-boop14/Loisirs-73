#!/usr/bin/env python3
"""Task 2 — replace commune-only crumb middle with category-hub link, all 5 langs."""
import json, os, re, html as html_lib
from pathlib import Path

ROOT = Path("/home/user/Loisir-74")
LIEUX = json.loads((ROOT / "lieux.json").read_text(encoding="utf-8"))["lieux"]

# Category → FR hub slug (verified by counting current cross-references)
CAT_TO_FR_HUB = {
    "attraction": "attractions",
    "cascade": "cascades",
    "chateau": "chateaux",
    "divers": "divers",
    "domaine": "bases-de-loisirs",
    "lac": "lacs",
    "musee": "musees",
    "parc": "bases-de-loisirs",
    "plage": "plages",
    "point-de-vue": "points-de-vue",
    "sentier": "sentiers",
    "telecabine": "telecabines",
    "voie-verte": "voies-vertes",
}

# FR hub slug → (localized slug, breadcrumb label) per language
HUB_BY_LANG = {
    "":    {"attractions":("attractions","Attractions"), "bases-de-loisirs":("bases-de-loisirs","Bases de loisirs"),
            "cascades":("cascades","Cascades"), "chateaux":("chateaux","Châteaux"), "divers":("divers","Divers"),
            "lacs":("lacs","Lacs"), "musees":("musees","Musées"), "plages":("plages","Plages"),
            "points-de-vue":("points-de-vue","Points de vue"), "sentiers":("sentiers","Sentiers"),
            "telecabines":("telecabines","Télécabines"), "voies-vertes":("voies-vertes","Voies vertes")},
    "de/": {"attractions":("attraktionen","Attraktionen"), "bases-de-loisirs":("freizeitparks","Freizeitparks"),
            "cascades":("wasserfaelle","Wasserfälle"), "chateaux":("schloesser","Schlösser"), "divers":("sonstiges","Sonstiges"),
            "lacs":("seen","Seen"), "musees":("museen","Museen"), "plages":("straende","Strände"),
            "points-de-vue":("aussichtspunkte","Aussichtspunkte"), "sentiers":("wanderwege","Wanderwege"),
            "telecabines":("seilbahnen","Seilbahnen"), "voies-vertes":("radwege","Radwege")},
    "en/": {"attractions":("attractions","Attractions"), "bases-de-loisirs":("leisure-parks","Leisure parks"),
            "cascades":("waterfalls","Waterfalls"), "chateaux":("castles","Castles"), "divers":("other","Other"),
            "lacs":("lakes","Lakes"), "musees":("museums","Museums"), "plages":("beaches","Beaches"),
            "points-de-vue":("viewpoints","Viewpoints"), "sentiers":("trails","Trails"),
            "telecabines":("cable-cars","Cable cars"), "voies-vertes":("greenways","Greenways")},
    "es/": {"attractions":("atraciones","Atracciones"), "bases-de-loisirs":("areas-de-ocio","Áreas de ocio"),
            "cascades":("cascadas","Cascadas"), "chateaux":("castillos","Castillos"), "divers":("otros","Otros"),
            "lacs":("lagos","Lagos"), "musees":("museos","Museos"), "plages":("playas","Playas"),
            "points-de-vue":("miradores","Miradores"), "sentiers":("senderos","Senderos"),
            "telecabines":("telefericos","Teleféricos"), "voies-vertes":("vias-verdes","Vías verdes")},
    "it/": {"attractions":("attrazioni","Attrazioni"), "bases-de-loisirs":("aree-recreative","Aree ricreative"),
            "cascades":("cascate","Cascate"), "chateaux":("castelli","Castelli"), "divers":("altro","Altro"),
            "lacs":("laghi","Laghi"), "musees":("musei","Musei"), "plages":("spiagge","Spiagge"),
            "points-de-vue":("punti-panoramici","Punti panoramici"), "sentieri":("sentieri","Sentieri"),
            "sentiers":("sentieri","Sentieri"),
            "telecabines":("funivie","Funivie"), "voies-vertes":("vie-verdi","Vie verdi")},
}

BASE = "https://loisirs74.fr"


def primary_hub(lieu):
    cats = lieu.get("categories") or ([lieu.get("category")] if lieu.get("category") else [])
    for c in cats:
        if c in CAT_TO_FR_HUB:
            return CAT_TO_FR_HUB[c]
    return None


# Pattern A: modern palais-lumière template (commune is <span> plain text)
CRUMB_RE = re.compile(
    r'(<nav class="crumb"[^>]*>'
    r'<a href="[^"]+">[^<]+</a>'
    r'<span class="sep">/</span>)'
    r'<span>[^<]+</span>'
    r'(<span class="sep">/</span>'
    r'<span aria-current="page">[^<]+</span>'
    r'</nav>)'
)

# Pattern B: older bleu-canard template (commune is <a href="/commune-slug">, › separator, multiline)
CRUMB_RE_B = re.compile(
    r'(<nav class="crumb"[^>]*>'
    r'<a href="[^"]+">[^<]+</a>'
    r'<span class="sep">[^<]+</span>)'
    r'\s*<a href="[^"]+">[^<]+</a>'
    r'(<span class="sep">[^<]+</span>'
    r'\s*<span aria-current="page">[^<]+</span>'
    r'</nav>)',
    re.DOTALL,
)

# JSON-LD BreadcrumbList item 2 — match the commune entry and rewrite
LDJSON_LI2_RE = re.compile(
    r'(\{"@type":\s*"ListItem",\s*"position":\s*2,\s*"name":\s*)'
    r'"([^"]+)"(,\s*"item":\s*")[^"]*("\s*\})'
)


def patch_file(path, hub_url, hub_label, hub_label_for_json):
    try:
        s = path.read_text(encoding="utf-8")
    except Exception:
        return False
    new_crumb = (
        rf'\1<a href="{hub_url}">{html_lib.escape(hub_label, quote=False)}</a>\2'
    )
    s2, n1 = CRUMB_RE.subn(new_crumb, s, count=1)
    if n1 == 0:
        s2, n1 = CRUMB_RE_B.subn(new_crumb, s, count=1)
    if n1 == 0:
        return False
    def _li2_sub(m):
        return f'{m.group(1)}"{hub_label_for_json}"{m.group(3)}{hub_url}{m.group(4)}'
    s3, n2 = LDJSON_LI2_RE.subn(_li2_sub, s2, count=1)
    path.write_text(s3, encoding="utf-8")
    return True


def main():
    total = 0
    skipped = []
    unmapped = []
    for lieu in LIEUX:
        slug = lieu["slug"]
        hub_fr = primary_hub(lieu)
        if not hub_fr:
            unmapped.append(slug)
            continue
        for lang_prefix, hub_map in HUB_BY_LANG.items():
            hub_slug, hub_label = hub_map[hub_fr]
            hub_url = f"{BASE}/{lang_prefix}{hub_slug}/"
            path = ROOT / f"{lang_prefix}{slug}.html"
            if not path.exists():
                continue
            ok = patch_file(path, hub_url, hub_label, hub_label)
            if ok:
                total += 1
            else:
                skipped.append(str(path.relative_to(ROOT)))
    print(f"Patched: {total} files")
    if unmapped:
        print(f"Unmapped slugs ({len(unmapped)}): {unmapped[:20]}")
    if skipped:
        print(f"Skipped (no crumb match) ({len(skipped)}): {skipped[:20]}")


if __name__ == "__main__":
    main()
