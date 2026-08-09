#!/usr/bin/env python3
"""Phase 4 of the hero handoff (c48963a baseline) — backfill `.webp`
siblings for every local jpg hero so `build_lieu_page` / `build_hubs`
can emit `<picture><source webp>` for them.

Targets:
  - img/generique/*.jpg  (all canonical generics)
  - img/<hub>/*-hero.jpg (real per-lieu heros)

Skips a target if its `.webp` sibling already exists. Idempotent.
"""
import glob
import os
from PIL import Image


def main():
    targets = glob.glob("img/generique/*.jpg") + glob.glob("img/*/*-hero.jpg")
    made = skipped = 0
    for jpg in targets:
        webp = jpg[:-4] + ".webp"
        if os.path.exists(webp):
            skipped += 1
            continue
        Image.open(jpg).convert("RGB").save(webp, "WEBP", quality=80, method=6)
        made += 1
    print(f"webp made={made} skipped={skipped} total_jpg={len(targets)}")


if __name__ == "__main__":
    main()
