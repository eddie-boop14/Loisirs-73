#!/usr/bin/env python3
"""apply_image_heros.py — runs the two-step image handoff atomically.

JOB 1: copy/rename the 60 source images into the repo root with their
       new generique-*.jpg names. ONE PNG → JPG conversion (q~85) for
       1000060318.png → generique-ski-piste.jpg.

JOB 2: set hero_image = "/<value>" in Json/<slug>.json for the 49
       preselections.

Both source manifests live under data/. Source image files are
discovered in --source-dir (default: ~/.claude/uploads/<session>/).

Usage:
  python3 scripts/apply_image_heros.py --source-dir /path/to/uploads
  python3 scripts/apply_image_heros.py --source-dir … --dry-run

Idempotent: re-running with the same sources is a no-op. Reports per
job. Exits non-zero if any required source image is missing.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MANIFEST = ROOT / "data" / "rename-manifest-ALL.json"
PRESELECT = ROOT / "data" / "preselections-ALL.json"


def find_source(src_dir: Path, name: str):
    """Match a manifest source filename against files in src_dir.
    Files may be stored as `<hash>-<actual_name>` (Claude upload pattern)
    or with their raw name. Returns the first match or None.
    """
    direct = src_dir / name
    if direct.exists():
        return direct
    for f in src_dir.iterdir():
        if not f.is_file():
            continue
        if f.name == name or f.name.endswith("-" + name):
            return f
    return None


def run_job1(src_dir: Path, dry_run: bool):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    print(f"== JOB 1: {len(manifest)} image renames ==")
    missing = []
    copied = 0
    converted = 0
    already_in_place = 0
    for src_name, new_name, subject in manifest:
        target = ROOT / new_name
        # Target-on-disk short-circuits everything: the rename has
        # already happened (this run, or in a prior session, or the
        # user pre-renamed before upload). No source lookup needed.
        if target.exists():
            already_in_place += 1
            continue
        src = find_source(src_dir, src_name)
        needs_convert = src_name.lower().endswith(".png") and new_name.lower().endswith(".jpg")
        if not src:
            missing.append((src_name, new_name, subject))
            continue
        if dry_run:
            print(f"  (dry) {src_name} → {new_name}  ({'convert' if needs_convert else 'copy'})")
            continue
        if needs_convert:
            from PIL import Image
            im = Image.open(src)
            if im.mode in ("RGBA", "P", "LA"):
                # Flatten to RGB for JPEG output; preserve alpha as white
                bg = Image.new("RGB", im.size, (255, 255, 255))
                if im.mode == "P":
                    im = im.convert("RGBA")
                bg.paste(im, mask=im.split()[-1] if "A" in im.mode else None)
                im = bg
            elif im.mode != "RGB":
                im = im.convert("RGB")
            im.save(target, "JPEG", quality=85, optimize=True, progressive=True)
            converted += 1
            print(f"  ✓ convert  {src.name} → {new_name}  ({im.size[0]}×{im.size[1]})")
        else:
            shutil.copy2(src, target)
            copied += 1
            print(f"  ✓ copy     {src.name} → {new_name}")
    print(f"  -- copied: {copied}  converted: {converted}  already on disk: {already_in_place}  missing: {len(missing)}")
    if missing:
        print(f"\n  ✗ {len(missing)} source images not found in {src_dir}:")
        for s, n, subj in missing[:20]:
            print(f"    {s}  (would become {n} — {subj})")
        return False
    return True


def run_job2(dry_run: bool):
    pre = json.loads(PRESELECT.read_text(encoding="utf-8"))
    print(f"\n== JOB 2: {len(pre)} hero_image preselections ==")
    JD = ROOT / "Json"
    changed = 0
    already = 0
    not_found = 0
    for slug, photo in pre.items():
        p = JD / f"{slug}.json"
        if not p.exists():
            not_found += 1
            print(f"  ! missing: {p}")
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        new_hero = f"/{photo}"
        if d.get("hero_image") == new_hero:
            already += 1
            continue
        # Verify the target image is on disk (avoid pointing fiches at
        # absent files — would cause 404s on rendered pages).
        if not (ROOT / photo).exists():
            print(f"  ✗ {slug}: target {photo} not on disk yet — skipping")
            continue
        if dry_run:
            print(f"  (dry) {slug}: {d.get('hero_image','')} → {new_hero}")
            continue
        d["hero_image"] = new_hero
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        changed += 1
        print(f"  ✓ {slug}: → {new_hero}")
    print(f"  -- changed: {changed}  already correct: {already}  missing slug: {not_found}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--source-dir",
        required=True,
        help="Directory containing the uploaded 1000060xxx.{jpg,png} files",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src = Path(args.source_dir).expanduser()
    if not src.is_dir():
        print(f"error: --source-dir {src} not a directory")
        return 2

    ok = run_job1(src, args.dry_run)
    if not ok and not args.dry_run:
        print("\nstopping — fix missing sources before JOB 2 changes Json/")
        return 1
    run_job2(args.dry_run)
    print("\nnext: python3 scripts/build_all.py --no-site")
    return 0


if __name__ == "__main__":
    sys.exit(main())
