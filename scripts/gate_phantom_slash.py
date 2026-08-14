#!/usr/bin/env python3
"""gate_phantom_slash.py — no rendered URL may differ from a sitemap URL
only by a trailing slash.

The guard that would have caught the 252 phantom trailing-slash URLs at launch
instead of at GSC position 74. Four builders once appended "/" to fiche and hub
URLs inside schema.org ItemList / CollectionPage blocks, while every canonical
is slash-less. Netlify serves both forms 200 with identical bytes, so each
phantom is a crawlable duplicate of a page we already publish — and it never
appears in an href, so gate_link_integrity (link-only) can't see it. Google
finds them by reading the ItemList `url` fields.

Rule: for every absolute site URL that appears anywhere in a rendered page
(href OR JSON-LD url field), if it is NOT in the sitemap but its slash-stripped
form IS, it is a phantom duplicate → fail.

Commune hubs and other real directories keep their trailing slash and ARE in
the sitemap that way, so they are never flagged. Read-only. Exit 1 on any hit.

    python3 scripts/gate_phantom_slash.py
"""
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import siteconfig  # noqa: E402

BASE = siteconfig.BASE_URL.rstrip("/")
# only trailing-slash URLs are candidates — a slash-less URL can't be a
# trailing-slash phantom of anything.
URL_RE = re.compile(re.escape(BASE) + r"/[A-Za-z0-9\-/]*/")
SKIP_TOPS = {"_site", "node_modules", "scripts", "reports", "content", ".git"}


def sitemap_locs():
    p = os.path.join(ROOT, "sitemap.xml")
    if not os.path.exists(p):
        sys.exit("gate_phantom_slash: sitemap.xml not found at repo root")
    return set(re.findall(r"<loc>([^<]+)</loc>", open(p, encoding="utf-8").read()))


def content_html():
    seen = set()
    for pat in ("*.html", "*/*.html", "*/*/*.html", "*/*/*/*.html"):
        for f in glob.glob(os.path.join(ROOT, pat)):
            rel = os.path.relpath(f, ROOT).replace(os.sep, "/")
            if rel.split("/")[0] in SKIP_TOPS or rel in seen:
                continue
            seen.add(rel)
    return sorted(seen)


def main():
    sm = sitemap_locs()
    phantoms = {}  # url -> sorted list of pages that name it
    for rel in content_html():
        text = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        for u in set(URL_RE.findall(text)):
            if u not in sm and u.rstrip("/") in sm:
                phantoms.setdefault(u, set()).add(rel)

    n_pages = len(content_html())
    print(f"gate_phantom_slash: {n_pages} rendered pages, {len(sm)} sitemap URLs, "
          f"{len(phantoms)} phantom trailing-slash URL(s)")
    if phantoms:
        print(f"::error::{len(phantoms)} URL(s) differ from a sitemap URL only by a "
              f"trailing slash — crawlable duplicates:")
        for u in sorted(phantoms)[:25]:
            src = sorted(phantoms[u])[0]
            more = f" (+{len(phantoms[u]) - 1} more pages)" if len(phantoms[u]) > 1 else ""
            print(f"    ✗ {u}   first seen in {src}{more}")
        if len(phantoms) > 25:
            print(f"    … and {len(phantoms) - 25} more")
        sys.exit(1)
    print("✓ no rendered URL is a trailing-slash duplicate of a canonical")


if __name__ == "__main__":
    main()
