"""Shared `picture_tag()` helper. Emits `<picture><source webp>` with a
JPG fallback when the hero is a local jpg that has a webp sibling, and
a plain `<img>` otherwise (URL heroes, jpg without webp). Always
bakes real width/height to kill CLS — looked up from
`data/img-dims.json` (built by `scripts/build_img_dims.py`).
"""
from __future__ import annotations
import siteconfig  # HANDOFF-73: per-site identity

import html as _html
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_DIMS: dict[str, list[int]] = {}


def _load_dims():
    p = ROOT / "data" / "img-dims.json"
    if p.exists():
        _DIMS.update(json.loads(p.read_text(encoding="utf-8")))


_load_dims()


def _attr(s):
    return _html.escape(str(s or ""), quote=True)


def _local_rel(img_src):
    """Return the repo-relative path of `img_src` if it points to a local
    file that exists on disk, else None.

    Accepts either an absolute URL on the production host or a root-
    relative path. Anything else (http://, data:, //) → None.
    """
    if not img_src:
        return None
    for pre in (siteconfig.BASE_URL + "/", "/"):
        if img_src.startswith(pre):
            rel = img_src[len(pre):].lstrip("/")
            if rel and (ROOT / rel).exists():
                return rel
            return None
    return None


def picture_tag(img_src, alt, *, eager=False, extra=""):
    """Render a <picture> if a webp sibling exists for this local jpg,
    else a plain <img>.

    `eager` → fetchpriority="high" (LCP hero); default → loading="lazy"
    decoding="async" for below-fold cards.
    `extra` is verbatim attribute markup appended to the <img>.
    """
    rel = _local_rel(img_src)
    loading_attr = ' fetchpriority="high"' if eager else ' loading="lazy" decoding="async"'
    wh = ""
    if rel and rel in _DIMS:
        w, h = _DIMS[rel]
        wh = f' width="{w}" height="{h}"'
    img = f'<img src="{_attr(img_src)}" alt="{_attr(alt)}"{wh}{loading_attr}{extra}>'
    if rel and rel.lower().endswith(".jpg"):
        webp_rel = rel[:-4] + ".webp"
        if (ROOT / webp_rel).exists():
            webp_src = img_src[:-4] + ".webp"
            return f'<picture><source srcset="{_attr(webp_src)}" type="image/webp">{img}</picture>'
    return img
