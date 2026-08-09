#!/usr/bin/env python3
"""gate_meta_uniqueness.py — every page introduces itself with its own name.

HANDOFF-32: Bing was flagging 508 duplicate title strings (2,369 pages — FR
titles mirrored verbatim into other languages) and 270 duplicate metas (1,343
pages — worst: a bare "Annecy (Haute-Savoie)." ×120 as the whole description).
The facts-derived fallbacks in build_lieu_page fixed the corpus; this gate
keeps it fixed.

Rules (read-only, exit 1 on violation):
  1. NO-META  — every indexable page must carry a non-empty
     <meta name="description">. Pages marked noindex (studio, merci-*, 404)
     are skipped entirely.
  2. DUP      — no <title> or meta-description string may be shared by more
     than 3 pages sitewide UNLESS every sharing page is an hreflang alternate
     of the SAME content (same fiche basename, or same directory slug, across
     the language trees). Frozen FR names + shared vocabulary words make those
     clusters legitimately coincide; two DIFFERENT pages sharing a string is
     the SERP-duplicate disease and stays red.

Usage: python3 scripts/gate_meta_uniqueness.py [--root DIR]
Prints the top offenders on failure.
"""
import argparse
import collections
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import locales  # noqa: E402

SKIP_TOP = {"_site", "scripts", "reports", "Json", "api", "content", ".git",
            "data", "node_modules", "img", ".well-known", ".github", "tests",
            "__pycache__"}
MAX_SHARED = 3

TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)
META_RE_1 = re.compile(r'<meta content="([^"]*)" name="description"')
META_RE_2 = re.compile(r'<meta name="description" content="([^"]*)"')
ROBOTS_RE = re.compile(r'<meta[^>]*name="robots"[^>]*>', re.I)


def page_identity(path, root):
    """The hreflang-cluster key: which CONTENT this page is, language-blind.
    Fiche pages share their basename; hub/commune/home index pages share their
    directory slug (with any leading language dir stripped)."""
    rel = os.path.relpath(path, root)
    base = os.path.basename(rel)
    if base != "index.html":
        return base
    parts = os.path.dirname(rel).split(os.sep)
    parts = [p for p in parts if p not in (".", "")]
    if parts and parts[0] in locales.ALL_SUBDIR_LANGS:
        parts = parts[1:]
    return "/".join(parts) or "HOME"


def scan(root):
    titles = collections.defaultdict(list)
    metas = collections.defaultdict(list)
    nometa = []
    for dirpath, dirs, files in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        top = rel.split(os.sep)[0]
        if top in SKIP_TOP:
            dirs[:] = []
            continue
        for fn in files:
            if not fn.endswith(".html"):
                continue
            p = os.path.join(dirpath, fn)
            h = open(p, encoding="utf-8", errors="ignore").read()
            robots = ROBOTS_RE.search(h)
            if robots and "noindex" in robots.group(0).lower():
                continue
            if fn == "404.html":
                continue
            t = TITLE_RE.search(h)
            if t:
                titles[re.sub(r"\s+", " ", t.group(1).strip())].append(p)
            m = META_RE_1.search(h) or META_RE_2.search(h)
            if m and m.group(1).strip():
                metas[m.group(1).strip()].append(p)
            else:
                nometa.append(p)
    return titles, metas, nometa


def violations(mp, root):
    out = []
    for s, pages in mp.items():
        if len(pages) <= MAX_SHARED:
            continue
        idents = {page_identity(p, root) for p in pages}
        if len(idents) > 1:
            out.append((s, pages, sorted(idents)))
    return sorted(out, key=lambda x: -len(x[1]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.dirname(HERE))
    args = ap.parse_args()
    titles, metas, nometa = scan(args.root)

    viol_t = violations(titles, args.root)
    viol_m = violations(metas, args.root)
    n_pages = sum(len(v) for v in titles.values())
    print(f"gate_meta_uniqueness: {n_pages} indexable pages scanned")

    ok = True
    if nometa:
        ok = False
        print(f"::error::{len(nometa)} indexable page(s) ship WITHOUT a meta description:")
        for p in nometa[:10]:
            print(f"    ✗ {os.path.relpath(p, args.root)}")
    for label, viol in (("title", viol_t), ("meta", viol_m)):
        if viol:
            ok = False
            print(f"::error::{len(viol)} {label} string(s) shared by >{MAX_SHARED} pages "
                  f"across DIFFERENT content (SERP duplicates):")
            for s, pages, idents in viol[:10]:
                print(f"    ✗ ×{len(pages)}  {s[:90]!r}")
                print(f"       identities: {idents[:5]}  e.g. {os.path.relpath(pages[0], args.root)}")
    if not ok:
        sys.exit(1)
    dup_t = sum(1 for v in titles.values() if len(v) > 1)
    print(f"✓ no duplicate titles/metas beyond same-content hreflang clusters "
          f"({dup_t} same-content title clusters allowed); every indexable page has a meta")


if __name__ == "__main__":
    main()
