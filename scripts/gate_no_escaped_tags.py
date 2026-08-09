#!/usr/bin/env python3
"""gate_no_escaped_tags.py — HANDOFF-23: no page ships literal &lt;tags&gt;.

Authored prose fields (body.what_is, when_to_visit, events, practical_info,
activities, how_to_get_there) carry inline HTML. Before the raw-emit fix,
several render paths HTML-escaped them, so live pages printed literal
'<strong>' text (e.g. lac-des-confins, nl/plage-de-saint-gingolph). This gate
makes that a red build: scan every rendered page for an escaped authored tag
(&lt;p&gt;, &lt;strong&gt;, …) and fail listing the offenders.

Run AFTER the build (pages freshly rendered). It protects the six live
languages today and every batch-translated language (HANDOFF-25) tomorrow —
new prose must never render through an escaping path.

CLI:
    python3 scripts/gate_no_escaped_tags.py [--root DIR]
"""
import argparse
import glob
import os
import re
import sys

DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The authored-HTML tag vocabulary (same set as build_lieu_page.AUTHORED_TAG_RE).
ESCAPED_TAG_RE = re.compile(r"&lt;/?(p|ul|ol|li|strong|em|a|br|b|i)\b", re.I)

LOCALE_DIRS = ["en", "de", "it", "es", "nl", "pl", "pt", "cs", "ar", "he", "ja"]
# Non-content pages where escaped markup can be legitimate (editor UI, docs).
EXCLUDE = {"studio.html", "404.html"}


def pages(root):
    out = [p for p in glob.glob(os.path.join(root, "*.html"))
           if os.path.basename(p) not in EXCLUDE]
    for d in LOCALE_DIRS:
        out += glob.glob(os.path.join(root, d, "**", "*.html"), recursive=True)
    # hub folders at root (cascades/, chateaux/, …)
    out += [p for p in glob.glob(os.path.join(root, "*", "index.html"))
            if os.path.basename(os.path.dirname(p)) not in LOCALE_DIRS]
    return sorted(set(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=DEFAULT_ROOT, help="Site root to scan")
    args = ap.parse_args()

    bad = []
    checked = 0
    for p in pages(args.root):
        try:
            html = open(p, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        checked += 1
        m = ESCAPED_TAG_RE.search(html)
        if m:
            rel = os.path.relpath(p, args.root)
            bad.append((rel, m.group(0)))

    print(f"gate_no_escaped_tags: scanned {checked} pages")
    if not bad:
        print("✓ no escaped authored tags in any rendered page")
        return
    print(f"::error::{len(bad)} page(s) render literal escaped tags "
          "(prose went through an escaping path — HANDOFF-23 regression):")
    for rel, frag in bad[:40]:
        print(f"    ✗ {rel}  ({frag}…)")
    if len(bad) > 40:
        print(f"    … and {len(bad) - 40} more")
    sys.exit(1)


if __name__ == "__main__":
    main()
