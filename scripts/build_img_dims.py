#!/usr/bin/env python3
"""Precompute `data/img-dims.json` — relative-path → [width, height] for
every local image referenced by the site. The `picture_tag` helper
looks up dims here instead of opening files per page (we render ~2,400
HTML files; opening the same PIL image 6×6 times each was wasteful).

Idempotent. Re-run after any image add/remove.
"""
import glob
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent


def main():
    paths = sorted(
        glob.glob(str(ROOT / "img/generique/*.jpg")) +
        glob.glob(str(ROOT / "img/generique/*.webp")) +
        glob.glob(str(ROOT / "img/*/*-hero.jpg")) +
        glob.glob(str(ROOT / "img/*/*-hero.webp")) +
        glob.glob(str(ROOT / "img/*/*-[0-9].jpg")) +
        glob.glob(str(ROOT / "img/*/*-[0-9][0-9].jpg")) +
        # event affiches (e.g. fete-musique-tornet) match none of the slug
        # patterns above; a regen without this glob drops their dims and
        # breaks the protected tornet card (bit us in 4ecaac74a).
        glob.glob(str(ROOT / "img/events/*.jpg"))
    )
    dims = {}
    for p in paths:
        rel = str(Path(p).relative_to(ROOT))
        try:
            with Image.open(p) as im:
                dims[rel] = list(im.size)
        except Exception as e:
            print(f"  ! {rel}: {e}")
    out = ROOT / "data" / "img-dims.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(dims, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}: {len(dims)} entries")


if __name__ == "__main__":
    main()
