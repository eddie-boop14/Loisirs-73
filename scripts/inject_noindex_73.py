#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""inject_noindex_73.py — FLIP-AT-LAUNCH: block every rendered page, not just the homepage.

robots.txt disallows crawling, but a URL that is linked from anywhere else can
still be indexed without being crawled — Google lists it with no snippet. The
whole pre-launch stance ("an indexed *.netlify.app becomes a duplicate of
loisirs73.fr the day the domain points here") depends on that not happening, so
every page carries the meta as well as the robots rule. Belt and braces, on
purpose.

AT LAUNCH: delete this script and its call in build_all, then rebuild. Grepping
FLIP-AT-LAUNCH finds it.
"""
import glob, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
META = ('<!-- FLIP-AT-LAUNCH: remove this meta (scripts/inject_noindex_73.py) when the real domain goes live -->\n'
        '<meta name="robots" content="noindex,nofollow">\n')
SKIP = ("scripts/", "data/", "img/", "Json/", "docs/", "reports/", "brand/", "node_modules/", "_site/")

def targets():
    for p in glob.glob(os.path.join(ROOT, "**", "*.html"), recursive=True):
        rel = os.path.relpath(p, ROOT)
        if not rel.startswith(SKIP):
            yield p

def main():
    added = present = 0
    for p in targets():
        s = open(p, encoding="utf-8").read()
        if re.search(r'<meta[^>]+name="robots"[^>]+noindex', s):
            present += 1
            continue
        if "</head>" not in s:
            continue
        open(p, "w", encoding="utf-8").write(s.replace("</head>", META + "</head>", 1))
        added += 1
    print(f"inject_noindex_73: {added} page(s) blocked, {present} already carried it")

if __name__ == "__main__":
    main()
