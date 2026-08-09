#!/usr/bin/env python3
"""Integrate a batch ZIP produced by Studio Tab 5 (AI Enricher) or Tab 6
(Photothèque).

The ZIP convention used by the Studio:
    json/<slug>.json            (one or many)
    <slug>-hero.<ext>           (optional, when Photothèque attached a photo)
    <slug>-photo-patch.json     (Photothèque only — {slug, hero_image,
                                 hero_credit, source_url})
    README.txt                  (informational)

Usage:
    python3 scripts/integrate_batch_zip.py <path/to/batch.zip>

Behaviour:
    1. Extracts to a temp dir.
    2. For each <slug>.json: writes Json/<slug>.json (overwrites; the
       Editor/Enricher pipeline already deep-merged preserved fields).
       New slugs are detected and added to lieux.json with a guessed
       category (matches the per-fiche `category` or falls back to
       'attraction').
    3. For each <slug>-hero.<ext> image: copies into repo root.
    4. For each *-photo-patch.json: applies the {hero_image, hero_credit}
       patch to the corresponding Json/<slug>.json (Photothèque flow).
    5. Runs the propagation pipeline:
        - build_lieu_page + localize_lieu for each touched slug
        - update_breadcrumbs
        - update_related
        - sync_hub_cards
        - build_homepage
        - build_catalog_index
    6. Appends new sitemap entries if any slug was added.
    7. Verifies reachability (0 orphans expected).

Prints a summary at the end with what was added/updated/skipped.
"""
import sys
import os
import json
import shutil
import subprocess
import zipfile
import re
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSON_DIR = ROOT / "Json"
LIEUX_PATH = ROOT / "lieux.json"
SITEMAP_PATH = ROOT / "sitemap.xml"


def run(cmd, **kwargs):
    """Run a subprocess; print stderr on failure."""
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, **kwargs)
    if r.returncode != 0:
        print(f"  ! {' '.join(cmd)} → exit {r.returncode}")
        if r.stderr:
            print("    " + r.stderr.strip().splitlines()[-1])
    return r


def categorize_for_lieux(per_fiche_cat: str, slug: str) -> str:
    """Map per-fiche category → lieux.json category bucket.
    Mirrors the heuristic used in earlier batch integrations.
    """
    if not per_fiche_cat:
        per_fiche_cat = ""
    cat = per_fiche_cat.lower()
    # Existing top-level buckets that go straight through
    DIRECT = {"attraction", "domaine", "divers", "lac", "plage", "cascade",
              "point-de-vue", "sentier", "voie-verte", "musee", "chateau",
              "parc", "telecabine", "jardin"}
    if cat in DIRECT:
        return cat
    # Outdoor adventure prefixes → domaine
    OUTDOOR_PREFIX = ("accrobranche", "via-ferrata", "canyoning", "rafting",
                      "bungee", "tyrolienne", "speleo", "ulm", "montgolfiere",
                      "chiens-de-traineau", "paintball", "wake", "parapente")
    for p in OUTDOOR_PREFIX:
        if slug.startswith(p + "-") or slug == p:
            return "domaine"
    # Indoor venue prefixes → attraction
    INDOOR_PREFIX = ("cinema", "arcade", "billard", "simulateur", "trampoline",
                     "padel", "tir-a-l-arc", "bowling", "karting-indoor", "vr-",
                     "atelier-poterie", "laser-game", "escape-game", "escalade",
                     "lancer-de-hache", "bar-a-jeux")
    for p in INDOOR_PREFIX:
        if slug.startswith(p):
            return "attraction"
    if slug.startswith("jardin-"):
        return "divers"
    if slug.startswith("ferme-pedagogique-"):
        return "divers"
    return "attraction"


def ensure_lieux_entry(d: dict) -> bool:
    """Ensure lieux.json has an entry for this fiche. Returns True if added."""
    slug = d["slug"]
    lieux = json.load(open(LIEUX_PATH))
    if any(L["slug"] == slug for L in lieux["lieux"]):
        return False
    cat = categorize_for_lieux(d.get("category", ""), slug)
    entry = {
        "slug": slug,
        "categories": [cat],
        "i18n": {lang: {
            "name": d["i18n"].get(lang, {}).get("name") or d["i18n"]["fr"]["name"],
            "commune": d.get("commune", ""),
        } for lang in ("fr", "de", "en", "it", "es")},
        "latitude": d.get("latitude"),
        "longitude": d.get("longitude"),
        "is_free": bool(d.get("schema_org", {}).get("is_free", False)),
    }
    lieux["lieux"].append(entry)
    lieux["lieux"].sort(key=lambda x: x["slug"])
    with open(LIEUX_PATH, "w", encoding="utf-8") as f:
        json.dump(lieux, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return True


def append_sitemap(slug: str) -> bool:
    """Append a sitemap entry for `slug` if absent. Returns True if added."""
    html = SITEMAP_PATH.read_text()
    if f"<loc>https://loisirs74.fr/{slug}</loc>" in html:
        return False
    block = (
        f'  <url><loc>https://loisirs74.fr/{slug}</loc><changefreq>weekly</changefreq>'
        f'<xhtml:link rel="alternate" hreflang="fr" href="https://loisirs74.fr/{slug}"/>'
        f'<xhtml:link rel="alternate" hreflang="en" href="https://loisirs74.fr/en/{slug}"/>'
        f'<xhtml:link rel="alternate" hreflang="de" href="https://loisirs74.fr/de/{slug}"/>'
        f'<xhtml:link rel="alternate" hreflang="it" href="https://loisirs74.fr/it/{slug}"/>'
        f'<xhtml:link rel="alternate" hreflang="es" href="https://loisirs74.fr/es/{slug}"/>'
        f'<xhtml:link rel="alternate" hreflang="x-default" href="https://loisirs74.fr/{slug}"/>'
        f"</url>\n"
    )
    SITEMAP_PATH.write_text(html.replace("</urlset>", block + "</urlset>", 1))
    return True


def apply_photo_patch(patch_path: Path) -> str | None:
    """Apply a Photothèque {slug, hero_image, hero_credit} patch.
    Returns the affected slug or None.
    """
    patch = json.load(open(patch_path))
    slug = patch.get("slug")
    if not slug:
        return None
    target = JSON_DIR / f"{slug}.json"
    if not target.exists():
        print(f"  ! patch for unknown slug: {slug}")
        return None
    d = json.load(open(target))
    d["hero_image"] = patch.get("hero_image") or d.get("hero_image")
    d["hero_credit"] = patch.get("hero_credit")
    with open(target, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return slug


def main(zip_path: str):
    zp = Path(zip_path)
    if not zp.exists():
        print(f"ZIP not found: {zip_path}")
        sys.exit(1)

    print(f"=== Integrating {zp.name} ===\n")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        with zipfile.ZipFile(zp) as z:
            z.extractall(tmp)

        # Inventory
        json_files = sorted(tmp.glob("json/*.json"))
        patch_files = sorted(tmp.glob("*-photo-patch.json"))
        image_files = sorted(
            [p for p in tmp.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")]
        )
        print(f"  found: {len(json_files)} JSON, {len(patch_files)} patches, {len(image_files)} images")

        # Track what changed
        touched: set[str] = set()
        added_lieux: list[str] = []
        added_sitemap: list[str] = []
        copied_images: list[str] = []

        # 1. Copy images first (so JSONs referencing them resolve)
        for img in image_files:
            target = ROOT / img.name
            shutil.copy2(img, target)
            copied_images.append(img.name)
            # If filename matches <slug>-hero.<ext>, mark the slug as touched
            m = re.match(r"(.+)-hero\.\w+$", img.name)
            if m:
                touched.add(m.group(1))

        # 2. Place per-fiche JSONs.
        # Preserve existing local hero_image / hero_credit unless the ZIP
        # bundled a matching <slug>-hero.<ext> image (in which case the new
        # image is intentional and we point hero_image at it).
        zip_image_slugs = {
            re.match(r"(.+)-hero\.(\w+)$", img.name).groups()
            for img in image_files
            if re.match(r"(.+)-hero\.\w+$", img.name)
        }
        zip_image_by_slug = {slug: ext for slug, ext in zip_image_slugs}
        for jp in json_files:
            d = json.load(open(jp))
            slug = d.get("slug")
            if not slug:
                print(f"  ! {jp.name} has no slug, skipping")
                continue
            target = JSON_DIR / f"{slug}.json"
            if target.exists():
                existing = json.load(open(target))
                if slug in zip_image_by_slug:
                    # ZIP shipped a new image for this slug — use it
                    d["hero_image"] = f"/{slug}-hero.{zip_image_by_slug[slug]}"
                    d["hero_credit"] = None
                else:
                    # No new image — keep the local hero_image/hero_credit
                    if existing.get("hero_image"):
                        d["hero_image"] = existing["hero_image"]
                    if "hero_credit" in existing:
                        d["hero_credit"] = existing["hero_credit"]
            with open(target, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
                f.write("\n")
            touched.add(slug)
            if ensure_lieux_entry(d):
                added_lieux.append(slug)
            if append_sitemap(slug):
                added_sitemap.append(slug)

        # 3. Apply photo patches (Photothèque flow)
        for pp in patch_files:
            slug = apply_photo_patch(pp)
            if slug:
                touched.add(slug)

        print(f"\n  touched: {len(touched)} fiche(s)")
        if added_lieux:
            print(f"  added to lieux.json: {len(added_lieux)} ({', '.join(added_lieux[:5])}{'…' if len(added_lieux) > 5 else ''})")
        if added_sitemap:
            print(f"  added to sitemap:    {len(added_sitemap)}")
        if copied_images:
            print(f"  images copied:       {len(copied_images)}")

        if not touched:
            print("\n  Nothing to integrate. Done.")
            return

        # 4. Re-render each touched fiche
        print(f"\n=== Rebuilding {len(touched)} fiches × 5 langs ===")
        ok = 0
        for slug in sorted(touched):
            r = run(["python3", "scripts/build_lieu_page.py", f"Json/{slug}.json"])
            if r.returncode != 0:
                continue
            r2 = run(["python3", "scripts/localize_lieu.py", slug])
            if r2.returncode == 0:
                ok += 1
        print(f"  rendered ok: {ok}/{len(touched)}")

        # 5. Propagation pipeline
        print("\n=== Propagation pipeline ===")
        if added_lieux or added_sitemap:
            run(["python3", "scripts/update_breadcrumbs.py"])
        run(["python3", "scripts/sync_hub_cards.py"])
        run(["python3", "scripts/update_related.py"])
        run(["python3", "scripts/build_homepage.py"])
        run(["python3", "scripts/build_catalog_index.py"])

        # 6. Reachability check
        print("\n=== Reachability ===")
        r = run(["python3", "scripts/check-reachability.py"])
        out = r.stdout
        for line in out.splitlines():
            if "ORPHAN" in line or "content=" in line:
                print(f"  {line}")

        print("\n=== Done ===")
        print(f"  Now: git status, review, git add -A, git commit, git push.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])
