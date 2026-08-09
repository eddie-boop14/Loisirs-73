#!/usr/bin/env python3
"""migrate_to_hub_folders.py — one-pass move of every local image into
`/img/<hub>/` folders per the approved plan
(/root/.claude/plans/do-1-2-vectorized-swing.md).

What it does:
  1. Inventory every image at repo root.
  2. Classify each into the hub(s) it serves:
     - generique-*.{jpg,webp} → FAMILY_PREFIX_TO_HUBS lookup
     - <slug>-hero.jpg + gallery <slug>-N.jpg → fiche.category → primary hub
     - PNGs, og-image.jpg, partner logos → STAY AT ROOT (skipped)
  3. mkdir -p img/<hub>/ for all 15 hubs.
  4. Copy each image into every hub folder it serves (idempotent: skip if
     dest exists with same size).
  5. Rewrite Json/<slug>.json.hero_image:
     - URL hero: unchanged
     - bare generique-X.jpg or /file.jpg: → /img/<primary-hub>/<filename>
     - already starts with /img/: unchanged
  6. Delete originals at root for everything moved.
  7. Write data/image-hub-map.json (the canonical record).
  8. Print per-hub file count + duplicates + any orphaned root images.

Idempotent — re-running on a half-migrated repo finishes the move cleanly.
"""
import json
import re
import shutil
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
JSON_DIR = ROOT / "Json"
IMG_ROOT = ROOT / "img"

# All 15 hubs
ALL_HUBS = [
    "baignade-nautisme", "bases-de-loisirs", "cascades", "chateaux",
    "lacs-plages", "musees", "parcs-jardins", "points-de-vue",
    "que-faire", "sensations-plein-air", "sentiers", "sorties-detente",
    "sport-jeux", "telecabines", "voies-vertes",
]

# Fiche category → primary hub (mirrors HUB_FILTERS in build_hubs.py).
# For categories that map to multiple hubs (e.g. 'parc' → bases-de-loisirs
# AND parcs-jardins), the first entry is the primary store; cross-hub
# cards reference the primary path.
CATEGORY_TO_PRIMARY_HUB = {
    "cascade":       "cascades",
    "chateau":       "chateaux",
    "musee":         "musees",
    "point-de-vue":  "points-de-vue",
    "sentier":       "sentiers",
    "telecabine":    "telecabines",
    "voie-verte":    "voies-vertes",
    "lac":           "lacs-plages",
    "plage":         "lacs-plages",
    "domaine":       "bases-de-loisirs",
    "parc":          "bases-de-loisirs",   # may also serve parcs-jardins
    "jardin":        "parcs-jardins",
    "base-nautique": "baignade-nautisme",
    "wakepark":      "baignade-nautisme",
    "accrobranche":  "bases-de-loisirs",
    "aquaparc":      "baignade-nautisme",
    "croisiere":     "baignade-nautisme",
    "cinema":        "sorties-detente",
    "casino":        "sorties-detente",
    "bowling":       "sport-jeux",
    "karting":       "sport-jeux",
    "patinoire":     "sport-jeux",
    "attraction":    "que-faire",          # catch-all bucket
    "divers":        "que-faire",
}

# Image family-prefix → hubs it serves (ordered: first = primary).
# Used for generique-*.jpg + .webp.
def _classify_generic(name):
    """Return list of hubs for a generique-*.jpg|webp file. Primary first."""
    n = name.lower()
    # Exact catch-all → every hub
    if n in ("generique-attraction.jpg", "generique-attraction.webp"):
        return list(ALL_HUBS)

    # Most-specific → broad. First match wins.
    rules = [
        # === hub-exclusive prefixes ===
        (r"^generique-cascade",           ["cascades"]),
        (r"^generique-chateau",           ["chateaux"]),
        (r"^generique-musee",             ["musees"]),
        (r"^generique-sentier",           ["sentiers"]),
        (r"^generique-voie-verte",        ["voies-vertes"]),
        (r"^generique-(telecabine|telesiege)", ["telecabines"]),
        (r"^generique-plage-lac-",        ["lacs-plages"]),
        (r"^generique-lac",               ["lacs-plages"]),
        (r"^generique-point-de-vue",      ["points-de-vue"]),
        (r"^generique-jardin-",           ["parcs-jardins"]),
        (r"^generique-(parc|domaine)\.",  ["bases-de-loisirs", "parcs-jardins"]),
        # parc-pelouse and similar parc-* variants
        (r"^generique-parc-",             ["parcs-jardins", "bases-de-loisirs"]),
        # === sensations-plein-air primary ===
        (r"^generique-canyoning-",        ["sensations-plein-air"]),
        (r"^generique-via-ferrata-",      ["sensations-plein-air"]),
        (r"^generique-rafting-",          ["sensations-plein-air"]),
        (r"^generique-parapente",         ["sensations-plein-air"]),
        (r"^generique-montgolfiere",      ["sensations-plein-air"]),
        (r"^generique-tyrolienne",        ["sensations-plein-air"]),
        (r"^generique-(grotte|speleo)",   ["sensations-plein-air"]),
        (r"^generique-alpine-coaster",    ["sensations-plein-air", "que-faire"]),
        (r"^generique-chiens-de-traineau",["sensations-plein-air", "que-faire"]),
        (r"^generique-parachutisme",      ["sensations-plein-air"]),
        # === cross-cut sensations + sport ===
        (r"^generique-escalade-",         ["sport-jeux", "sensations-plein-air"]),
        (r"^generique-paintball-",        ["sport-jeux", "sensations-plein-air"]),
        (r"^generique-segway-",           ["sensations-plein-air", "que-faire"]),
        (r"^generique-tir-arc",           ["sport-jeux", "sensations-plein-air"]),
        (r"^generique-cible",             ["sport-jeux", "sensations-plein-air"]),
        # === pure sport-jeux ===
        (r"^generique-padel-",            ["sport-jeux"]),
        (r"^generique-tennis-",           ["sport-jeux"]),
        (r"^generique-karting-",          ["sport-jeux"]),
        (r"^generique-bowling-",          ["sport-jeux"]),
        (r"^generique-patinoire-",        ["sport-jeux"]),
        (r"^generique-escape-game-",      ["sport-jeux"]),
        (r"^generique-laser-game",        ["sport-jeux"]),
        (r"^generique-trampoline-",       ["sport-jeux"]),
        (r"^generique-vr-",               ["sport-jeux"]),
        (r"^generique-bar-jeux",          ["sport-jeux", "sorties-detente"]),
        (r"^generique-lancer-",           ["sport-jeux"]),
        # === sorties-detente ===
        (r"^generique-spa-",              ["sorties-detente"]),
        (r"^generique-thermes-",          ["sorties-detente"]),
        (r"^generique-cinema",            ["sorties-detente"]),
        # === bases-de-loisirs + sensations cross-cuts ===
        (r"^generique-accrobranche-",     ["bases-de-loisirs", "sensations-plein-air"]),
        # === wetland (cross-cut: parcs-jardins + sentiers) ===
        (r"^generique-reserve-zone-humide-", ["parcs-jardins", "sentiers"]),
        # === aquatique (multi-hub water) ===
        (r"^generique-aquatique-",        ["baignade-nautisme", "bases-de-loisirs"]),
        # === water sports / nautical ===
        (r"^generique-(paddle|barque|port|voile|voiliers|croisiere|canal)",
                                          ["baignade-nautisme", "bases-de-loisirs"]),
        (r"^generique-wakeboard",         ["baignade-nautisme", "sensations-plein-air"]),
        # === winter sports → télécabines + sensations ===
        (r"^generique-(ski|snowboard|telesiege)",
                                          ["telecabines", "sensations-plein-air"]),
        (r"^generique-foret-(enneigee|neige)", ["telecabines", "sensations-plein-air"]),
        (r"^generique-lac-hiver",         ["telecabines", "sensations-plein-air"]),
        # === family / kids → que-faire primary ===
        (r"^generique-aire-jeux-",        ["que-faire", "sport-jeux"]),
        (r"^generique-animation-enfants-",["que-faire", "sport-jeux"]),
        (r"^generique-atelier-enfants-",  ["que-faire", "sport-jeux"]),
        (r"^generique-famille-",          ["que-faire", "sensations-plein-air", "bases-de-loisirs"]),
        (r"^generique-ferme-",            ["bases-de-loisirs", "que-faire"]),
        # === atelier poterie ===
        (r"^generique-atelier-poterie-",  ["que-faire"]),
        # === plaine (generic green field) ===
        (r"^generique-plaine-",           ["parcs-jardins", "que-faire"]),
        # === jardin-detente (added by hero pack) — already covered by jardin- above
    ]
    for pat, hubs in rules:
        if re.search(pat, n):
            return hubs
    return None  # orphan → flagged in report


def _slug_from_local_image(name):
    """For per-fiche files (<slug>-hero.jpg, <slug>-N.jpg), extract the slug.
    Returns the slug or None if the name doesn't match either pattern."""
    n = name
    # <slug>-hero.jpg
    m = re.match(r"^(.+)-hero\.(jpg|jpeg|webp)$", n)
    if m:
        return m.group(1)
    # <slug>-N.jpg (gallery image, N=1..20)
    m = re.match(r"^(.+)-(\d{1,2})\.(jpg|jpeg|webp)$", n)
    if m:
        return m.group(1)
    return None


def _stay_at_root(name):
    """Files we never move: favicons, logos, og-image, partner logos."""
    keep = {
        "og-image.jpg",
        "favicon.ico",
        "favicon-16x16.png", "favicon-32x32.png",
        "apple-touch-icon.png",
        "android-chrome-192x192.png", "android-chrome-512x512.png",
        "site.webmanifest",
        "browserconfig.xml",
        "logo.png", "logo-full.png",
        "chez-nous-a-la-plage-logo.jpg", "chez-nous-a-la-plage-logo.png",
        "chalet-du-tornet-logo.png", "chalet-du-tornet-logo.jpg",
    }
    if name in keep:
        return True
    # PNG icons + .ico + .webmanifest patterns
    if name.lower().endswith((".ico", ".webmanifest", ".xml")):
        return True
    if name.lower().endswith(".png") and (
        "logo" in name.lower() or "favicon" in name.lower()
        or "android-chrome" in name.lower() or "apple-touch" in name.lower()
    ):
        return True
    return False


def _fiche_primary_hub(slug):
    """Look up the fiche's category and return its primary hub.
    Returns None if the fiche JSON doesn't exist or has no known category."""
    p = JSON_DIR / f"{slug}.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    cat = (d.get("category") or "").strip()
    return CATEGORY_TO_PRIMARY_HUB.get(cat)


def main():
    # ---- Phase 1: inventory + classify ----
    candidates = []  # list of (path, basename, list_of_hubs, kind)
    orphans = []
    stayed = []
    for p in sorted(ROOT.iterdir()):
        if not p.is_file():
            continue
        name = p.name
        if _stay_at_root(name):
            stayed.append(name)
            continue
        # Image-like extensions
        if not name.lower().endswith((".jpg", ".jpeg", ".webp", ".png")):
            continue
        # generique-*.jpg / .webp
        if name.startswith("generique-"):
            hubs = _classify_generic(name)
            if hubs:
                candidates.append((p, name, hubs, "generic"))
            else:
                orphans.append(name)
            continue
        # Per-fiche heros + galleries
        slug = _slug_from_local_image(name)
        if slug:
            hub = _fiche_primary_hub(slug)
            if hub:
                candidates.append((p, name, [hub], "fiche"))
            else:
                orphans.append(name)
            continue
        # Unknown image at root — flag
        orphans.append(name)

    # ---- Phase 2: mkdir + copy ----
    for hub in ALL_HUBS:
        (IMG_ROOT / hub).mkdir(parents=True, exist_ok=True)

    copied = 0
    skipped = 0
    for src, name, hubs, kind in candidates:
        for hub in hubs:
            dst = IMG_ROOT / hub / name
            if dst.exists() and dst.stat().st_size == src.stat().st_size:
                skipped += 1
                continue
            shutil.copy2(src, dst)
            copied += 1

    # ---- Phase 3: rewrite Json/<slug>.json hero_image ----
    written = 0
    unchanged = 0
    skipped_url = 0
    skipped_already = 0
    not_found_target = 0
    for jp in sorted(JSON_DIR.glob("*.json")):
        d = json.loads(jp.read_text(encoding="utf-8"))
        if d.get("status") == "draft":
            continue
        slug = jp.stem
        json_changed = False
        primary_hub = _fiche_primary_hub(slug) or "que-faire"

        # ---- hero_image rewrite ----
        hero = (d.get("hero_image") or "").strip()
        if hero and not hero.startswith(("http://", "https://")) and not hero.startswith("/img/"):
            basename = hero.lstrip("/").rsplit("/", 1)[-1]
            # Determine target hub: generic → image's hub list; per-fiche → primary
            target_hub = None
            if basename.startswith("generique-"):
                hubs = _classify_generic(basename)
                if hubs:
                    target_hub = primary_hub if primary_hub in hubs else hubs[0]
            else:
                target_hub = primary_hub
            if target_hub and (IMG_ROOT / target_hub / basename).exists():
                new_hero = f"/img/{target_hub}/{basename}"
                if d.get("hero_image") != new_hero:
                    d["hero_image"] = new_hero
                    json_changed = True
            else:
                not_found_target += 1
                print(f"  ! {slug}: cannot route hero_image='{hero}'")
        elif hero.startswith(("http://", "https://")):
            skipped_url += 1
        elif hero.startswith("/img/"):
            skipped_already += 1

        # ---- gallery_photos[].src rewrite (run on EVERY fiche, even when
        # hero was URL/already-migrated/empty) ----
        gallery = d.get("gallery_photos") or []
        if isinstance(gallery, list):
            for g in gallery:
                if not isinstance(g, dict):
                    continue
                src = (g.get("src") or "").strip()
                if not src:
                    continue
                if src.startswith(("http://", "https://")):
                    continue
                if src.startswith("/img/"):
                    continue
                g_basename = src.lstrip("/").rsplit("/", 1)[-1]
                if (IMG_ROOT / primary_hub / g_basename).exists():
                    new_src = f"/img/{primary_hub}/{g_basename}"
                    if g.get("src") != new_src:
                        g["src"] = new_src
                        json_changed = True

        if json_changed:
            jp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            written += 1
        else:
            unchanged += 1

    # ---- Phase 4: delete originals at root (only files we successfully copied) ----
    # Build set of basenames we placed under /img/ — these are safe to delete at root.
    placed = set()
    for src, name, hubs, kind in candidates:
        # Confirm at least one copy actually exists at destination
        if any((IMG_ROOT / h / name).exists() for h in hubs):
            placed.add(name)
    removed = 0
    for src, name, _, _ in candidates:
        if name not in placed:
            continue
        root_path = ROOT / name
        if root_path.exists():
            root_path.unlink()
            removed += 1

    # ---- Phase 4.5: rewrite legacy paths inside existing HTML ----
    # build_homepage.py reads cards from the existing index.html as a
    # baseline and copies them verbatim. Cards from the pre-migration
    # state carry old "/<slug>-hero.jpg" paths. Same goes for any other
    # rendered HTML that still references the old layout.
    # We scan every .html file and rewrite legacy refs to /img/<hub>/<file>
    # using the on-disk map (the file we know exists there).
    on_disk_by_basename = {}  # basename → first hub it's found in
    for hub in ALL_HUBS:
        for f in (IMG_ROOT / hub).iterdir():
            if f.is_file():
                on_disk_by_basename.setdefault(f.name, hub)

    # Fallback: if a legacy "/<slug>-hero.jpg" or "/<slug>-N.jpg" path
    # has no matching file on disk (dangling reference from the old
    # state — e.g. an old hub card pointing at a hero that was never
    # actually produced), look up the slug's fiche JSON hero_image and
    # use that. Caches per-slug JSON reads.
    def _hero_from_fiche(slug):
        p = JSON_DIR / f"{slug}.json"
        if not p.exists():
            return None
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
        h = (d.get("hero_image") or "").strip()
        if h.startswith("/img/") or h.startswith(("http://", "https://")):
            return h
        return None

    # Match three legacy patterns at root:
    #   /<slug>-hero.jpg, /<slug>-N.jpg, /generique-X.jpg
    legacy_re = re.compile(
        r'(?:src|href|content)="('
        r'/(?:generique-[a-z0-9_-]+'                # /generique-X.jpg
        r'|[a-z][a-z0-9_-]*-hero'                    # /<slug>-hero.jpg
        r'|[a-z][a-z0-9_-]*-\d{1,2}'                 # /<slug>-N.jpg
        r')\.(?:jpg|jpeg|webp))"'
    )
    slug_hero_re = re.compile(r"^([a-z][a-z0-9_-]*)-hero\.(?:jpg|jpeg|webp)$")
    html_rewrites = 0
    html_touched = 0
    for p in ROOT.rglob("*.html"):
        if any(x in p.parts for x in ("_site", ".claude", "node_modules", "reports", "data")):
            continue
        txt = p.read_text(encoding="utf-8", errors="replace")

        def _rewrite(m):
            nonlocal html_rewrites
            old_path = m.group(1)
            basename = old_path.lstrip("/").rsplit("/", 1)[-1]
            attr = m.group(0).split('="', 1)[0]  # "src", "href" or "content"
            target_hub = on_disk_by_basename.get(basename)
            if target_hub:
                new_path = f"/img/{target_hub}/{basename}"
                html_rewrites += 1
                return f'{attr}="{new_path}"'
            # Fallback: dangling <slug>-hero.jpg → resolve via fiche JSON
            sm = slug_hero_re.match(basename)
            if sm:
                slug = sm.group(1)
                new_hero = _hero_from_fiche(slug)
                if new_hero:
                    html_rewrites += 1
                    return f'{attr}="{new_hero}"'
            return m.group(0)

        new_txt = legacy_re.sub(_rewrite, txt)
        if new_txt != txt:
            p.write_text(new_txt, encoding="utf-8")
            html_touched += 1

    print(f"\n  HTML legacy-path rewrites: {html_rewrites} refs across {html_touched} files")

    # ---- Phase 4.6: rewrite api/lieux.json `photo` fields ----
    api_path = ROOT / "api" / "lieux.json"
    api_rewrites = 0
    if api_path.exists():
        api = json.loads(api_path.read_text(encoding="utf-8"))
        for entry in api.get("lieux", []):
            photo = (entry.get("photo") or "").strip()
            if not photo:
                continue
            if photo.startswith(("http://", "https://")) or photo.startswith("/img/"):
                continue
            basename = photo.lstrip("/").rsplit("/", 1)[-1]
            target_hub = on_disk_by_basename.get(basename)
            new_photo = None
            if target_hub:
                new_photo = f"/img/{target_hub}/{basename}"
            else:
                sm = slug_hero_re.match(basename)
                if sm:
                    new_photo = _hero_from_fiche(sm.group(1))
            if new_photo and new_photo != photo:
                entry["photo"] = new_photo
                api_rewrites += 1
        if api_rewrites:
            api_path.write_text(
                json.dumps(api, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    print(f"  api/lieux.json photo rewrites: {api_rewrites}")

    # ---- Phase 5: write data/image-hub-map.json (scan img/<hub>/) ----
    # Rebuild the canonical map from the actual on-disk state so re-runs
    # on a half-migrated repo produce the full map, not just the delta.
    img_map = defaultdict(list)
    for hub in ALL_HUBS:
        for f in (IMG_ROOT / hub).iterdir():
            if f.is_file():
                img_map[f.name].append(hub)
    img_map = {k: sorted(v) for k, v in img_map.items()}
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "image-hub-map.json").write_text(
        json.dumps(img_map, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # ---- Phase 6: report ----
    per_hub = defaultdict(int)
    for hub in ALL_HUBS:
        per_hub[hub] = sum(1 for f in (IMG_ROOT / hub).iterdir() if f.is_file())
    dup_count = defaultdict(int)
    for name, hubs in img_map.items():
        dup_count[len(hubs)] += 1

    print(f"\n=== Migration summary ===")
    print(f"  candidates classified:       {len(candidates)}")
    print(f"  copied to img/<hub>/:        {copied}")
    print(f"  skipped (dest existed):      {skipped}")
    print(f"  removed at root:             {removed}")
    print(f"  stayed at root (logos etc.): {len(stayed)}")
    print(f"  orphan images (unclassified):{len(orphans)}")
    for o in orphans:
        print(f"    ✗ {o}")
    print(f"\n  Json/ rewrites:")
    print(f"    written:                   {written}")
    print(f"    unchanged:                 {unchanged}")
    print(f"    skipped URL:               {skipped_url}")
    print(f"    skipped already migrated:  {skipped_already}")
    print(f"    no primary hub / no file:  {not_found_target}")
    print(f"\n  per-hub file count:")
    for hub in ALL_HUBS:
        print(f"    img/{hub:22}: {per_hub[hub]}")
    print(f"\n  duplication histogram (# of files served by N hubs):")
    for n in sorted(dup_count):
        print(f"    served by {n} hub(s):  {dup_count[n]}")

    return 0 if not orphans else 1


if __name__ == "__main__":
    sys.exit(main())
