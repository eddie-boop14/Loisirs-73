#!/usr/bin/env python3
"""One-shot pass that wraps every `<img>` inside an `<article class="card">`
in a `<picture>` element (with webp source) and bakes width/height.

Why a separate pass: `build_homepage.py` extracts card blocks verbatim
from the previous index.html — its section-id mapping is upstream-
broken so we don't invoke it. Hub pages already emit `<picture>` via
`build_hubs.py` (Phase 4 wiring). This pass closes the gap on the 5
locale homepages (and any other HTML where a card still has a plain
`<img>`).

Idempotent: skips `<article>` blocks that already contain `<picture>`.
"""
from __future__ import annotations

import html as _html
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO / "scripts"))
from picture_tag import picture_tag

ARTICLE_RE = re.compile(
    r'(<article class="card"[^>]*>)(.*?)(</article>)',
    re.S,
)

CARD_IMG_RE = re.compile(
    r'<img\b([^>]*?)>',
    re.S,
)


def _src_of(img_attrs: str) -> str:
    m = re.search(r'\bsrc="([^"]+)"', img_attrs)
    return m.group(1) if m else ""


def _alt_of(img_attrs: str) -> str:
    m = re.search(r'\balt="([^"]*)"', img_attrs)
    return _html.unescape(m.group(1)) if m else ""


def _upgrade(card: str) -> str:
    if "<picture>" in card:
        return card

    def repl(m):
        attrs = m.group(1)
        src = _src_of(attrs)
        if not src:
            return m.group(0)
        alt = _alt_of(attrs)
        return picture_tag(src, alt, eager=False, extra=' referrerpolicy="no-referrer"')

    return CARD_IMG_RE.sub(repl, card)


def main():
    touched = 0
    rewrites = 0
    for p in REPO.rglob("*.html"):
        if any(x in p.parts for x in ("_site", ".claude", "node_modules", "reports")):
            continue
        txt = p.read_text(encoding="utf-8", errors="replace")
        if "<article class=\"card\"" not in txt:
            continue
        before = txt

        def article_repl(m):
            nonlocal rewrites
            head, body, tail = m.group(1), m.group(2), m.group(3)
            new_body = _upgrade(head + body + tail)
            if new_body != head + body + tail:
                rewrites += 1
            return new_body

        new = ARTICLE_RE.sub(article_repl, txt)
        if new != before:
            p.write_text(new, encoding="utf-8")
            touched += 1
    print(f"upgrade_card_pictures: rewrote {rewrites} card(s) across {touched} file(s)")


if __name__ == "__main__":
    main()
