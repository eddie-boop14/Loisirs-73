#!/usr/bin/env python3
"""Sponsored-link gate — the 2026-08-31 tripwire.

Fails the build if a PROMOTIONAL link ships able to pass PageRank.

WHY A GATE AND NOT JUST THE MARKING PASS
  Anything rendered after the marking pass, or written by a builder added later,
  would ship unqualified and nothing would say so. This defect is invisible from
  outside: the page looks perfect, every other gate is green, Search Console
  reports no manual action — and the site is quietly devalued. loisirs74.fr lost
  96% of its Google impressions in a day that way while Bing did not move.
  A failure that silent has to fail loudly in CI.

  It shares its detection rules with mark_sponsored_links, by import, so the
  gate and the fix can never drift apart.

WHAT COUNTS AS PROMOTIONAL (same two rules as the marking pass)
  1. every <a> inside a partner card — host-agnostic, so a new card cannot
     escape by using a new domain;
  2. every <a> to a host the publisher owns (site.config.json
     promo_link_domains), wherever it appears.

WHAT IS NOT CHECKED
  Every other outbound link. Editorial citations — the venue's own site, the
  office de tourisme, the mairie, patrimoine databases — must keep passing their
  vote. A gate demanding nofollow everywhere would be actively harmful here.

  A link carrying `sponsored` passes; `nofollow` alone also passes (the older
  spelling of the same instruction, still honoured).

Read-only. Usage: python3 scripts/gate_sponsored_links.py
"""
import glob
import os
import re
import sys

import siteconfig
import mark_sponsored_links as M

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = ("_site", ".git", "node_modules", "scripts", "Json", "api", "content")
REL_RE = re.compile(r'\brel="([^"]*)"', re.I)


def promotional_anchors(html):
    """Every anchor the marking pass would qualify, by the same two rules."""
    hits = []
    for cm in M.CARD_RE.finditer(html):
        # Absolute links to our OWN host inside a card are internal navigation
        # (the invite CTA), not promotion — the marking pass leaves them alone
        # and so must this, or the gate fails on links it is right to skip.
        hits.extend(a for a in M.EXT_A_RE.findall(cm.group(0)) if not M._is_self(a))
    if M.HOST_RE is not None:
        hits.extend(M.HOST_RE.findall(html))
    return hits


def main():
    offenders = []
    checked = pages = 0
    for fp in glob.glob(os.path.join(ROOT, "**", "*.html"), recursive=True):
        rel_path = os.path.relpath(fp, ROOT)
        if rel_path.split(os.sep)[0] in SKIP_DIRS:
            continue
        hits = promotional_anchors(open(fp, encoding="utf-8").read())
        if not hits:
            continue
        pages += 1
        for tag in hits:
            checked += 1
            m = REL_RE.search(tag)
            tokens = {t.lower() for t in (m.group(1).split() if m else [])}
            if not (tokens & {"sponsored", "nofollow"}):
                offenders.append((rel_path, tag[:120]))

    own = f" + own hosts {', '.join(M.DOMAINS)}" if M.DOMAINS else ""
    print(f"gate_sponsored_links: {checked} promotional link(s) on {pages} page(s) checked "
          f"[partner cards{own}]")
    if offenders:
        print(f"::error::{len(offenders)} promotional link(s) ship able to pass PageRank — "
              "at scale this reads as a link network, devalued algorithmically with no "
              "manual action to warn you:")
        for path, tag in offenders[:20]:
            print(f"    x {path}\n        {tag}")
        if len(offenders) > 20:
            print(f"    … and {len(offenders) - 20} more")
        print("  fix: python3 scripts/mark_sponsored_links.py --apply")
        return 1
    print("✓ every promotional link is qualified; editorial citations keep their vote")
    return 0


if __name__ == "__main__":
    sys.exit(main())
