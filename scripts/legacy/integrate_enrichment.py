#!/usr/bin/env python3
"""Full integration pipeline for one or more enriched fiches.

Background: running build_lieu_page.py alone silently wipes post-build state
that other scripts add (the 'À proximité' related-venues carousel from
update_related.py). This wrapper chains the four steps that must run together:

  1. build_lieu_page.py <slug>   → regenerates FR HTML from Json/<slug>.json
  2. update_related (single-slug) → re-inserts the related-venues section
                                    on FR + en/de/it/es HTMLs
  3. localize_lieu.py <slug>     → regenerates en/de/it/es/nl HTMLs from FR
  4. build_catalog_index.py      → refreshes catalog-index.json (once, at end)

Usage:
  python3 scripts/integrate_enrichment.py <slug1> [<slug2> ...]
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path("/home/user/Loisir-74")
SCRIPTS = ROOT / "scripts"

# Import update_related's internals so we can drive it for a single slug
# without re-running the bidirectional-fixup loop across all 327 fiches.
sys.path.insert(0, str(SCRIPTS))
import update_related as ur  # noqa: E402


def run(cmd, label):
    """Run a subprocess, surface failures."""
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    if result.returncode != 0:
        print(f"  ✗ {label} FAILED:\n    stdout: {result.stdout.strip()}\n    stderr: {result.stderr.strip()}")
        return False
    # echo the last line of stdout (these scripts print a single summary line)
    last = (result.stdout.strip().splitlines() or [""])[-1]
    if last:
        print(f"  {last}")
    return True


def patch_related_for_slug(slug, idx):
    """Run update_related's single-slug patch on FR + en/de/it/es HTMLs."""
    if slug not in idx:
        print(f"  ⚠️  {slug} not in update_related's index (no category or lat/lon); skipping related")
        return 0
    rels = ur.compute_related(slug, idx)
    patched = 0
    for lang_prefix in ("", "de/", "en/", "es/", "it/"):
        path = ROOT / lang_prefix / f"{slug}.html"
        if not path.exists():
            continue
        block = ur.render_related(slug, rels, lang_prefix, idx)
        if ur.patch_file(path, block):
            patched += 1
    return patched


def integrate(slugs):
    # Build the update_related index once (it's expensive — touches 327 fiches)
    print(f"Building related-venues index ({len(ur.LIEUX)} catalog entries)…")
    idx = ur.build_data_index()
    print(f"  {len(idx)} fiches in the related graph\n")

    failed = []
    for slug in slugs:
        json_path = ROOT / "Json" / f"{slug}.json"
        if not json_path.exists():
            print(f"✗ {slug}: Json/{slug}.json does not exist")
            failed.append(slug)
            continue

        print(f"=== {slug} ===")
        ok = run(["python3", "scripts/build_lieu_page.py", f"Json/{slug}.json"],
                 "build_lieu_page")
        if not ok:
            failed.append(slug)
            continue

        n = patch_related_for_slug(slug, idx)
        print(f"  related: {n} HTML files patched (FR + locales)")

        ok = run(["python3", "scripts/localize_lieu.py", slug], "localize_lieu")
        if not ok:
            failed.append(slug)
            continue
        print()

    # Refresh catalog-index once at the end
    print("=== Final ===")
    run(["python3", "scripts/build_catalog_index.py"], "build_catalog_index")

    print()
    if failed:
        print(f"⚠️  {len(failed)} fiche(s) failed: {failed}")
        return 1
    print(f"✓ {len(slugs)} fiche(s) integrated cleanly.")
    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(integrate(sys.argv[1:]))


if __name__ == "__main__":
    main()
