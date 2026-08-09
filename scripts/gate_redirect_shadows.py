#!/usr/bin/env python3
"""Redirect-shadow gate — HANDOFF-39A-C2.

Read-only. A `_redirects` 301/302 whose SOURCE matches an existing built 200
path is a dead rule: Netlify serves the file and the redirect never fires
(unless forced with `!`), so the alias silently stops working — or worse, a
future page lands on a path an alias already claims and gets eaten by a
forced rule. Either way: red.

Only 301/302 lines are checked. The legal-page 200 rewrites shadow by design
(that is what a rewrite IS) and are skipped.

Checked against the publish tree `_site/` when it exists (the deploy truth),
else the repo root. Splat sources (`/x/*`) are red when the directory `x`
exists non-empty; plain sources are red when `<path>`, `<path>.html`, or
`<path>/index.html` exists.

Usage: python3 scripts/gate_redirect_shadows.py [--tree DIR] [--redirects FILE]
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def parse_301_sources(path):
    """Yield (lineno, source) for every 301/302 rule (forced `!` included)."""
    out = []
    with open(path, encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            parts = s.split()
            if len(parts) >= 3 and parts[2].rstrip("!") in ("301", "302"):
                out.append((i, parts[0]))
    return out


def shadow_of(tree, src):
    """Return the built path that shadows `src`, or None."""
    p = src.lstrip("/")
    if src.endswith("/*"):
        base = os.path.join(tree, p[:-2])
        if os.path.isdir(base) and any(os.scandir(base)):
            return f"{p[:-2]}/ (non-empty directory)"
        return None
    if p.endswith("/"):
        candidates = [p + "index.html"]
    else:
        candidates = [p, p + ".html", p + "/index.html"]
    for c in candidates:
        if c and os.path.isfile(os.path.join(tree, c)):
            return c
    return None


def main():
    ap = argparse.ArgumentParser(description="No 301/302 source may shadow a built 200 path.")
    ap.add_argument("--tree", default=None,
                    help="Built tree to check against (default: _site/ if present, else repo root)")
    ap.add_argument("--redirects", default=os.path.join(ROOT, "_redirects"))
    args = ap.parse_args()

    tree = args.tree
    if tree is None:
        site = os.path.join(ROOT, "_site")
        tree = site if os.path.isdir(site) else ROOT

    rules = parse_301_sources(args.redirects)
    if not rules:
        print("::error::no 301/302 rules parsed from _redirects — parse failure?",
              file=sys.stderr)
        sys.exit(1)

    shadows = []
    for lineno, src in rules:
        hit = shadow_of(tree, src)
        if hit:
            shadows.append((lineno, src, hit))

    print(f"gate_redirect_shadows: {len(rules)} 301/302 sources checked "
          f"against {os.path.relpath(tree, ROOT) if tree != ROOT else 'repo root'}")
    if not shadows:
        print("✓ no redirect source shadows an existing 200 path")
        sys.exit(0)
    print(f"::error::{len(shadows)} redirect source(s) shadow a built 200 path:")
    for lineno, src, hit in shadows:
        print(f"    ✗ _redirects:{lineno}  {src}  → shadowed by {hit}")
    sys.exit(1)


if __name__ == "__main__":
    main()
