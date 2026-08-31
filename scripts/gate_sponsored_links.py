#!/usr/bin/env python3
"""Sponsored-link gate — the 2026-08-31 tripwire.

Fails the build if a link to a PAID placement host ships without rel=sponsored.

WHY A GATE AND NOT JUST THE MARKING PASS
  The marking pass runs at the end of build_all, so anything rendered after it,
  or a page written by a builder added later, would ship unqualified and nothing
  would say so. This failure is invisible from the outside: the page looks
  perfect, every other gate is green, Search Console reports no manual action —
  and the site is quietly devalued by SpamBrain. loisirs74.fr lost 96% of its
  Google impressions in a day that way, while Bing did not move. A defect that
  silent must fail loudly in CI.

  Read-only. It reads the built tree and site.config.json, nothing else.

WHAT PASSES
  A link to a paid host carrying `sponsored` (nofollow alone also passes — it is
  the older spelling of the same instruction and Google still honours it).

WHAT IS NOT CHECKED
  Every other outbound link. Editorial citations must keep passing their vote;
  a gate that demanded nofollow everywhere would be actively harmful here.

Usage: python3 scripts/gate_sponsored_links.py
"""
import glob
import os
import re
import sys

import siteconfig

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = ("_site", ".git", "node_modules", "scripts", "Json", "api", "content")
DOMAINS = tuple(siteconfig.PAID_PARTNER_DOMAINS)

ANCHOR_RE = re.compile(
    r'<a\b[^>]*\bhref="https?://(?:[^"/?#]*\.)?(?:'
    + "|".join(re.escape(d) for d in DOMAINS)
    + r')(?:[/?#][^"]*)?"[^>]*>', re.I,
) if DOMAINS else None
REL_RE = re.compile(r'\brel="([^"]*)"', re.I)


def main():
    if not DOMAINS:
        print(f"gate_sponsored_links: no paid_partner_domains for {siteconfig.DOMAIN} — "
              "nothing to enforce (editorial links stay followed). OK")
        return 0

    offenders = []
    checked = pages = 0
    for fp in glob.glob(os.path.join(ROOT, "**", "*.html"), recursive=True):
        rel_path = os.path.relpath(fp, ROOT)
        if rel_path.split(os.sep)[0] in SKIP_DIRS:
            continue
        html = open(fp, encoding="utf-8").read()
        hits = ANCHOR_RE.findall(html)
        if not hits:
            continue
        pages += 1
        for tag in hits:
            checked += 1
            m = REL_RE.search(tag)
            tokens = {t.lower() for t in (m.group(1).split() if m else [])}
            if not (tokens & {"sponsored", "nofollow"}):
                offenders.append((rel_path, tag[:120]))

    print(f"gate_sponsored_links: {checked} paid-placement link(s) on {pages} page(s) checked "
          f"[{', '.join(DOMAINS)}]")
    if offenders:
        print(f"::error::{len(offenders)} paid-placement link(s) ship without rel=sponsored — "
              "this is a Google link scheme, enforced algorithmically with no manual action:")
        for path, tag in offenders[:20]:
            print(f"    x {path}\n        {tag}")
        if len(offenders) > 20:
            print(f"    … and {len(offenders) - 20} more")
        print("  fix: python3 scripts/mark_sponsored_links.py --apply")
        return 1
    print("✓ every paid-placement link carries rel=sponsored; editorial citations untouched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
