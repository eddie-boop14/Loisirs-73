#!/usr/bin/env python3
"""
prune-hreflang.py — Loisirs 74
==============================
Remove <link rel="alternate" hreflang> tags and language-switcher anchors
whose target page does not exist on disk, so the site never advertises a
translation that 404s.

Every alternate link / switcher anchor carries the full target URL, so the
check is uniform: resolve the href to a file path and keep the entry only
if that file exists. This covers place pages, category hubs (localized
folder names) and both switcher markups (`lang-menu`, `lang-switch`).

Idempotent.
"""

import re
from pathlib import Path

ROOT = Path(__file__).parent

LINK_RE = re.compile(
    r'[ \t]*<link rel="alternate" hreflang="[^"]*" href="([^"]*)">\n?')
ANCHOR_RE = re.compile(
    r'\s*<a\s+href="([^"]*)"[^>]*\bhreflang="[^"]*"[^>]*>.*?</a>', re.S)


def href_to_path(href):
    """https://loisirs74.fr/de/wasserfaelle/ -> ROOT/de/wasserfaelle/index.html"""
    u = href.split('#')[0].split('?')[0]
    trailing = u.endswith('/')
    u = re.sub(r'^https?://[^/]+', '', u).strip('/')
    if u == '':
        return ROOT / 'index.html'
    return ROOT / (u + ('/index.html' if trailing else '.html'))


def exists(href):
    return href_to_path(href).exists()


def prune(text):
    removed = [0]

    def link_repl(m):
        if exists(m.group(1)):
            return m.group(0)
        removed[0] += 1
        return ''

    def anchor_repl(m):
        if exists(m.group(1)):
            return m.group(0)
        removed[0] += 1
        return ''

    text = LINK_RE.sub(link_repl, text)
    text = ANCHOR_RE.sub(anchor_repl, text)
    return text, removed[0]


def main():
    n_files = n_links = 0
    for path in sorted(ROOT.rglob('*.html')):
        if path.name == 'studio.html' or any(p == 'node_modules' for p in path.parts):
            continue
        original = path.read_text(encoding='utf-8')
        text, removed = prune(original)
        if text != original:
            path.write_text(text, encoding='utf-8')
            n_files += 1
            n_links += removed
    print(f'Files updated:           {n_files}')
    print(f'Dead hreflang/anchors removed: {n_links}')


if __name__ == '__main__':
    main()
