#!/usr/bin/env python3
"""version_assets.py — cache-bust runtime /scripts/ includes sitewide (HANDOFF-12).

Final HTML pass: rewrite every `<script src="/scripts/{duck,nearme,l74sort}.js">`
to carry the asset's current content hash (`?v=<hash>`), via scripts/assets.py.
Idempotent — re-stamps to the current hash, so a changed asset auto-busts on the
next build with zero manual bumps. Catches pages no builder re-emits (the locale
homepages carry their includes as committed chrome). Pairs with the `/scripts/*`
`immutable` rule in `_headers`: long-cached AND never-stale.

Read/writes the source tree in place (build_site then copies to _site/). The
protected partner fiches carry no duck include (build_lieu_page skips them), so
they are untouched.
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assets  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = ("_site", ".git", "node_modules", "scripts", "reports", "Json", "api")


def main():
    seen = changed = 0
    for fp in glob.glob(os.path.join(ROOT, "**", "*.html"), recursive=True):
        rel = os.path.relpath(fp, ROOT)
        if rel.split(os.sep)[0] in SKIP_DIRS:
            continue
        seen += 1
        html = open(fp, encoding="utf-8").read()
        new = assets.stamp(html)
        if new != html:
            with open(fp, "w", encoding="utf-8") as fh:
                fh.write(new)
            changed += 1
    vers = ", ".join(f"{k}?v={v}" for k, v in assets.VERSIONS.items())
    print(f"version_assets: stamped runtime includes on {changed}/{seen} pages ({vers})")


if __name__ == "__main__":
    main()
