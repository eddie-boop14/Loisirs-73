#!/usr/bin/env python3
"""Render every brand raster from the SVG sources. Derived, never authored.

Same law as the rest of the engine: the SVGs in brand/ are the source of truth,
every PNG/ICO/JPG below is generated. Edit an SVG, re-run this, commit the lot.

  brand/logo.svg   -> logo.png, og-image fallback, large sizes  (detailed, >=64px)
  brand/mark.svg   -> favicons, touch icons, maskable           (survives 16px)
  brand/og-image.svg -> og-image.jpg                            (social card)

Usage:  python3 scripts/build_brand.py
Needs:  pip install cairosvg pillow
"""
import io
import sys
from pathlib import Path

try:
    import cairosvg
    from PIL import Image
except ImportError:
    sys.exit("::error::build_brand needs cairosvg and pillow: "
             "pip install cairosvg pillow --break-system-packages")

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "brand"

# (source svg, output path, size) — mark.svg for anything small, logo.svg above 64
TARGETS = [
    ("logo.svg", "logo.png", 200),
    ("logo.svg", "logo-512.png", 512),
    ("mark.svg", "mark.png", 128),
    ("mark.svg", "favicon-16x16.png", 16),
    ("mark.svg", "favicon-32x32.png", 32),
    ("mark.svg", "favicon-48x48.png", 48),
    ("mark.svg", "apple-touch-icon.png", 180),
    ("mark.svg", "android-chrome-192x192.png", 192),
    ("mark.svg", "android-chrome-512x512.png", 512),
]


def render(svg, size):
    png = cairosvg.svg2png(url=str(BRAND / svg), output_width=size, output_height=size)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def main():
    if not BRAND.is_dir():
        sys.exit(f"::error::{BRAND} not found")
    written = []

    for svg, out, size in TARGETS:
        img = render(svg, size)
        img.save(ROOT / out)
        written.append((out, size))

    # multi-resolution .ico
    ico = [render("mark.svg", s) for s in (16, 32, 48)]
    ico[0].save(ROOT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)],
                append_images=ico[1:])
    written.append(("favicon.ico", "16/32/48"))

    # maskable icon: Android crops to a circle, so the art needs a safe zone —
    # the spec reserves the outer 20%. Render the mark at 60% and centre it on
    # the brand ground so nothing important reaches the crop.
    MASK = 512
    pad = int(MASK * 0.2)
    canvas = Image.new("RGBA", (MASK, MASK), "#15496a")
    inner = render("mark.svg", MASK - 2 * pad)
    canvas.paste(inner, (pad, pad), inner)
    canvas.save(ROOT / "android-chrome-maskable-512x512.png")
    written.append(("android-chrome-maskable-512x512.png", MASK))

    # social card
    png = cairosvg.svg2png(url=str(BRAND / "og-image.svg"),
                           output_width=1200, output_height=630)
    Image.open(io.BytesIO(png)).convert("RGB").save(
        ROOT / "og-image.jpg", quality=88, optimize=True, progressive=True)
    written.append(("og-image.jpg", "1200x630"))

    print(f"build_brand: {len(written)} file(s) from {len(set(t[0] for t in TARGETS))} SVG source(s)")
    for name, size in written:
        kb = (ROOT / name).stat().st_size // 1024
        print(f"  {str(size):>9}  {kb:>4} KB  {name}")


if __name__ == "__main__":
    main()
