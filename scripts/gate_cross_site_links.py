#!/usr/bin/env python3
"""Cross-site link gate — the 2026-08-31 tripwire.

Fails the build if a link to the SISTER site ships able to pass PageRank.

WHY
  loisirs74.fr and loisirs73.fr are the same publisher. A sitewide footer link
  put ~10,400 followed links into the sibling, reciprocated from the other
  side. Each ingredient is innocent alone — cross-linking related properties is
  fine, footers are fine, reciprocity is fine. Together, sitewide + reciprocal
  + same owner is the shape Google's link spam policy calls an excessive link
  exchange. And the upside is structurally zero: PageRank flowing between two
  properties you own cannot make either of them rank.

  So the links that remain are the ones that earn their place for a READER —
  the homepage card, the 30 km proximity cards at the département border — and
  they carry rel=nofollow. The bulk footer line is gone
  (site.config.json: sister.footer_link).

WHAT PASSES
  A link to the sister host carrying `nofollow` (or `sponsored`, which also
  withholds the vote). Anything else to that host fails.

WHAT IS NOT CHECKED
  Every other outbound link. Editorial source citations must keep their vote —
  see gate_sponsored_links for the promotional side.

Read-only. Usage: python3 scripts/gate_cross_site_links.py
"""
import glob
import os
import re
import sys

import siteconfig

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = ("_site", ".git", "node_modules", "scripts", "Json", "api", "content")

_SIS = getattr(siteconfig, "SISTER", None) or {}
_URL = (_SIS.get("url") or "").strip()
HOST = re.sub(r"^https?://", "", _URL).strip("/") if _URL else ""

A_RE = re.compile(
    r'<a\b[^>]*\bhref="https?://(?:[^"/?#]*\.)?' + re.escape(HOST)
    + r'(?:[/?#][^"]*)?"[^>]*>', re.I) if HOST else None
REL_RE = re.compile(r'\brel="([^"]*)"', re.I)


def main():
    if not HOST:
        print("gate_cross_site_links: no sister site configured — nothing to enforce. OK")
        return 0

    offenders, checked, pages = [], 0, 0
    for fp in glob.glob(os.path.join(ROOT, "**", "*.html"), recursive=True):
        rel_path = os.path.relpath(fp, ROOT)
        if rel_path.split(os.sep)[0] in SKIP_DIRS:
            continue
        hits = A_RE.findall(open(fp, encoding="utf-8").read())
        if not hits:
            continue
        pages += 1
        for tag in hits:
            checked += 1
            m = REL_RE.search(tag)
            tokens = {t.lower() for t in (m.group(1).split() if m else [])}
            if not (tokens & {"nofollow", "sponsored"}):
                offenders.append((rel_path, tag[:120]))

    print(f"gate_cross_site_links: {checked} link(s) to {HOST} on {pages} page(s) checked")
    if offenders:
        print(f"::error::{len(offenders)} cross-site link(s) ship able to pass PageRank. "
              "Sitewide + reciprocal + same owner is an excessive link exchange, and the "
              "upside is zero — PageRank between two sites you own cannot help either rank:")
        for path, tag in offenders[:20]:
            print(f"    x {path}\n        {tag}")
        if len(offenders) > 20:
            print(f"    … and {len(offenders) - 20} more")
        return 1
    print(f"✓ every link to {HOST} withholds its vote; the reader-facing cards remain")
    return 0


if __name__ == "__main__":
    sys.exit(main())
