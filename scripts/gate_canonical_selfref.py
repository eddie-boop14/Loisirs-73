#!/usr/bin/env python3
"""Canonical self-reference gate — JOB P1.

Read-only. Fails the build if any INDEXABLE built page (skips 404.html and
noindex/robots pages such as studio) violates canonical correctness:

  * 0 or >1  <link rel="canonical">             (must be exactly one)
  * canonical href != the page's own public URL  (self-referential, per 1a)
  * a literal `${` inside the canonical          (unsubstituted template)
  * an md-alt (<link type="text/markdown">) pointing to a missing content/*.md

Self URL rules (must match fix_hreflang_sitemap.py):
  index.html → /            · {lang}/index.html → /{lang}/
  {hub}/index.html (± lang) → /…/  (trailing slash)
  {slug}.html (± lang)      → /{slug}  (clean: no .html, no trailing slash)

Prints a table (path · is · expected) of any violators. Exit 1 on any.
"""
import glob
import siteconfig  # HANDOFF-73: per-site identity
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import locales  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = siteconfig.BASE_URL + "/"
LANGS = set(locales.VISIBLE_SECONDARY)
CANON_ANY = re.compile(r'<link\b[^>]*\brel=("|\')canonical\1[^>]*>', re.I)
HREF_RE = re.compile(r'href=("|\')([^"\']*)\1')
MDALT_ANY = re.compile(r'<link\b[^>]*\btype=("|\')text/markdown\1[^>]*>', re.I)
NOIDX_RE = re.compile(r'<meta[^>]*name=("|\')robots\1[^>]*content=("|\')[^"\']*noindex', re.I)
SKIP_FILES = {"404.html"}


def self_url(rel):
    rel = rel.replace(os.sep, "/")
    if rel == "index.html":
        return BASE
    if re.fullmatch(r"[a-z]{2}/index\.html", rel) and rel[:2] in LANGS:
        return BASE + rel[:3]
    if rel.endswith("/index.html"):                 # hub (fr or locale)
        return BASE + rel[:-len("index.html")]
    return BASE + rel[:-len(".html")]               # lieu / utility


def indexable_pages():
    seen = set()
    for pat in ("*.html", "*/index.html", "*/*.html", "*/*/index.html"):
        for f in glob.glob(os.path.join(ROOT, pat)):
            rel = os.path.relpath(f, ROOT).replace(os.sep, "/")
            if rel in seen or os.path.basename(rel) in SKIP_FILES:
                continue
            # only our content trees (skip _site/, content/, api/, etc. — none are *.html anyway)
            top = rel.split("/")[0]
            if top in {"_site", "node_modules", "scripts", "reports", "content"}:
                continue
            seen.add(rel)
    return sorted(seen)


def main():
    violations = []
    checked = skipped = 0
    for rel in indexable_pages():
        html = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        if NOIDX_RE.search(html):
            skipped += 1
            continue
        checked += 1
        want = self_url(rel)
        canons = CANON_ANY.findall(html)  # returns the quote groups; recount via finditer
        tags = [m.group(0) for m in CANON_ANY.finditer(html)]
        if len(tags) != 1:
            violations.append((rel, f"{len(tags)} canonical tags", "exactly 1"))
            continue
        hm = HREF_RE.search(tags[0])
        got = hm.group(2) if hm else "(no href)"
        if "${" in tags[0]:
            violations.append((rel, "${…} literal", want))
        elif got != want:
            violations.append((rel, got, want))
        # md-alt existence
        for md in MDALT_ANY.finditer(html):
            mh = HREF_RE.search(md.group(0))
            href = mh.group(2) if mh else ""
            if href.startswith("/content/"):
                if not os.path.exists(os.path.join(ROOT, href.lstrip("/"))):
                    violations.append((rel, f"md-alt → {href} (missing)", "existing content/*.md or none"))

    print(f"gate_canonical_selfref: checked {checked} indexable pages, skipped {skipped} noindex")
    if not violations:
        print("✓ every indexable page has exactly one self-referential canonical; md-alts resolve")
        sys.exit(0)
    print(f"::error::{len(violations)} canonical violation(s):")
    print(f"  {'path':<48} {'is':<40} expected")
    for path, is_, exp in violations[:60]:
        print(f"  {path:<48} {is_:<40} {exp}")
    sys.exit(1)


if __name__ == "__main__":
    main()
