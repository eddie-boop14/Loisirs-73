#!/usr/bin/env python3
"""audit_hero_themes.py — gate the picker's output.

Three assertions:
  1. Hero file family ↔ fiche `facts.type` family. A château fiche should
     not show a museum image; a parc/jardin fiche should not show
     accrobranche. Mismatches are flagged with slug + facts.type +
     hero token.
  2. No `generique-*.{jpg,webp}` exists outside `img/generique/`.
  3. Every local `hero_image` resolves on disk.

Exit code: 0 when nothing flagged, 1 otherwise.
"""
import glob
import json
import os
import re
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
JSON_DIR = ROOT / "Json"

# Map facts.type prose patterns → required hero token (substring of the
# generique-*.jpg basename). When facts.type matches one of `patterns`,
# the hero token must match one of `tokens` to be considered family-
# coherent. Patterns are lowercased substring checks; the first matching
# row wins.
THEME_RULES = [
    # Compound phrases FIRST — the primary activity in a multi-activity
    # facts.type usually leads the string.
    ("parc accrobranche", ["accrobranche", "escalade", "via-ferrata"]),
    ("parc aventure",    ["accrobranche"]),
    ("parcours aventure",["accrobranche"]),
    ("centre aquatique", ["aquatique", "spa", "thermes"]),
    ("base nautique",    ["paddle", "barque", "voile", "port"]),
    ("aquaparc",         ["aquatique", "spa", "thermes"]),
    ("ferme pédagogique",["famille", "ferme"]),
    ("centre de loisirs multi-espaces", ["aquatique", "spa", "thermes", "famille"]),
    ("salle d'escalade", ["escalade"]),
    ("salle de bloc",    ["escalade"]),
    ("réalité virtuelle",["vr-"]),
    ("centre de réalité virtuelle", ["vr-"]),
    ("réserve naturelle",["reserve-zone-humide", "sentier"]),
    ("zone humide",      ["reserve-zone-humide", "sentier"]),
    ("alpine coaster",   ["alpine-coaster"]),
    ("luge sur rails",   ["alpine-coaster"]),
    ("dévalkart",        ["alpine-coaster"]),
    ("chiens de traîneau",["chiens-de-traineau"]),
    ("mushing",          ["chiens-de-traineau"]),
    ("atelier poterie",  ["atelier-poterie"]),
    ("céramique",        ["atelier-poterie"]),
    ("via ferrata",      ["escalade", "via-ferrata", "accrobranche"]),
    ("escape game",      ["escape-game"]),
    ("escape-game",      ["escape-game"]),
    ("escape forest",    ["escape-game", "accrobranche"]),
    ("laser game",       ["laser-game"]),
    ("voie verte",       ["voie-verte"]),
    ("piste cyclable",   ["voie-verte"]),
    ("point de vue",     ["point-de-vue", "sentier"]),
    ("belvédère",        ["point-de-vue"]),
    # Single-keyword rules — order matters: more specific → broader.
    ("château",          ["chateau"]),
    ("chateau",          ["chateau"]),
    ("ruines",           ["chateau"]),
    ("vestiges",         ["chateau"]),
    ("musée",            ["musee", "chateau"]),
    ("musee",            ["musee", "chateau"]),
    ("muséum",           ["musee", "chateau"]),
    ("cascade",          ["cascade"]),
    ("escalade",         ["escalade"]),
    ("canyon",           ["canyoning"]),
    ("rafting",          ["rafting", "attraction"]),
    ("parapente",        ["parapente"]),
    ("ulm",              ["parapente"]),
    ("montgolf",         ["montgolfiere"]),
    ("aérostation",      ["montgolfiere"]),
    ("trampoline",       ["trampoline"]),
    ("bar à jeux",       ["bar-jeux"]),
    ("bar ludique",      ["bar-jeux"]),
    ("lancer de hache",  ["lancer"]),
    ("vr ",              ["vr-"]),
    ("spa",              ["spa", "thermes"]),
    ("thermes",          ["thermes", "spa"]),
    ("hammam",           ["thermes", "spa"]),
    ("cinéma",           ["cinema"]),
    ("cinema",           ["cinema"]),
    ("karting",          ["karting"]),
    ("bowling",          ["bowling"]),
    ("patinoire",        ["patinoire"]),
    ("billard",          ["bar-jeux", "attraction"]),
    ("paintball",        ["paintball", "attraction"]),
    ("tir à l'arc",      ["tir-arc", "cible", "attraction"]),
    ("padel",            ["padel", "tennis", "attraction"]),
    ("tennis",           ["tennis", "padel", "attraction"]),
    ("segway",           ["segway", "attraction"]),
    ("croisière",        ["croisiere", "port", "voile"]),
    ("voile",            ["voile", "port", "voiliers", "paddle"]),
    ("paddle",           ["paddle", "barque", "port"]),
    ("aviron",           ["paddle", "barque"]),
    ("wakeboard",        ["wakeboard"]),
    ("accrobranche",     ["accrobranche", "escalade", "via-ferrata"]),
    ("tyrolienne",       ["tyrolienne", "accrobranche"]),
    ("grotte",           ["grotte", "speleo"]),
    ("spéléo",           ["speleo", "grotte"]),
    ("saut à l'élastique",["attraction"]),
    ("saut pendulaire",  ["attraction"]),
    ("marais",           ["reserve-zone-humide", "sentier"]),
    ("jardin",           ["jardin", "parc"]),
    ("herbularius",      ["jardin", "parc", "chateau"]),
    ("arboretum",        ["jardin", "parc"]),
    ("piscine",          ["aquatique"]),
    ("télécabine",       ["telecabine", "telesiege", "point-de-vue"]),
    ("téléphérique",     ["telecabine", "point-de-vue"]),
    ("sentier",          ["sentier"]),
    ("randonnée",        ["sentier"]),
    ("plage",            ["plage-lac", "lac"]),
    ("baignade",         ["plage-lac", "lac", "aquatique"]),
    ("simulateur",       ["vr-", "karting", "attraction"]),
]


def family_required(facts_type):
    if not facts_type:
        return None
    t = facts_type.lower()
    for prose, tokens in THEME_RULES:
        if prose in t:
            return (prose, tokens)
    return None


def hero_basename(hero):
    if not hero:
        return ""
    if hero.startswith(("http://", "https://", "//")):
        return ""  # URL — not auditable here
    return hero.lstrip("/").rsplit("/", 1)[-1]


def main():
    mismatches = []
    unresolved = []
    by_family = defaultdict(int)

    for fp in sorted(glob.glob(str(JSON_DIR / "*.json"))):
        d = json.loads(Path(fp).read_text(encoding="utf-8"))
        slug = Path(fp).stem
        if d.get("status") == "draft":
            continue
        hero = (d.get("hero_image") or "").strip()
        basename = hero_basename(hero)

        # Resolve check (local heros only)
        if hero and not hero.startswith(("http://", "https://", "//")):
            local = hero.lstrip("/")
            if not (ROOT / local).exists():
                unresolved.append((slug, hero))

        # Family coherence: only when (a) hero is a generic on disk,
        # (b) fiche has facts.type that matches a theme rule.
        if not basename.startswith("generique-"):
            continue
        fr = (d.get("i18n") or {}).get("fr") or {}
        facts_type = (fr.get("facts") or {}).get("type") or ""
        req = family_required(facts_type)
        if not req:
            continue
        prose, tokens = req
        by_family[prose] += 1
        if not any(tok in basename for tok in tokens):
            mismatches.append((slug, facts_type, basename, tokens))

    # Orphan generic check
    stray_generics = [
        f for f in glob.glob(str(ROOT / "img/*/generique-*.jpg"))
        if Path(f).parent.name != "generique"
    ] + [
        f for f in glob.glob(str(ROOT / "img/*/generique-*.webp"))
        if Path(f).parent.name != "generique"
    ]

    print(f"=== audit_hero_themes ({len(by_family)} family rules fired) ===")
    print(f"theme mismatches: {len(mismatches)}")
    for slug, ft, bn, toks in mismatches[:50]:
        print(f"  ✗ {slug}: facts.type={ft!r}")
        print(f"      hero={bn!r}, expected one of {toks}")
    if len(mismatches) > 50:
        print(f"  ...+{len(mismatches) - 50} more")
    print(f"\nunresolved hero paths: {len(unresolved)}")
    for slug, h in unresolved[:20]:
        print(f"  ✗ {slug}: {h}")
    print(f"\nstray per-hub generics: {len(stray_generics)}")
    for f in stray_generics[:20]:
        print(f"  ✗ {f}")

    fail = bool(mismatches or unresolved or stray_generics)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
