#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""inject_noindex_73.py — FLIP-AT-LAUNCH: block every rendered page, not just the homepage.

robots.txt disallows crawling, but a URL that is linked from anywhere else can
still be indexed without being crawled — Google lists it with no snippet. The
whole pre-launch stance ("an indexed *.netlify.app becomes a duplicate of
loisirs73.fr the day the domain points here") depends on that not happening, so
every page carries the meta as well as the robots rule. Belt and braces, on
purpose.

AT LAUNCH: flip robots.txt (remove its FLIP-AT-LAUNCH marker) and rebuild —
this script reads the marker and becomes a no-op the moment it is gone, so
launch is a one-file change rather than a multi-file hunt. It previously
relied on being run by hand, was never wired into build_all, and the first
full rebuild silently washed the meta off 350+ pages; robots.txt Disallow
alone does NOT stop an externally-linked URL from being indexed.
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
    robots = os.path.join(ROOT, "robots.txt")
    if not (os.path.exists(robots) and
            "FLIP-AT-LAUNCH" in open(robots, encoding="utf-8").read()):
        print("inject_noindex_73: no FLIP-AT-LAUNCH marker in robots.txt — "
              "site is launched, nothing to block")
        return
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
