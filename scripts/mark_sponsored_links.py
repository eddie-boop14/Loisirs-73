#!/usr/bin/env python3
"""mark_sponsored_links.py — rel=sponsored on every PROMOTIONAL link.

WHY THIS EXISTS
  The "À proximité" partner cards carried 1,140 followed outbound links to 506
  commercial hosts — hotels, restaurants, activity operators, a booking chain —
  injected across 426 pages, every one of them rel="noopener" and nothing else.
  Whether or not money changes hands, a business card block promoting a
  commercial venue is advertising, not an editorial citation, and Google's link
  spam policy asks for it to be qualified. Unqualified at this scale it reads as
  a link network, and the enforcement is ALGORITHMIC: SpamBrain devalues the
  linking site with no manual action, so Search Console stays green while the
  site sinks. That is what August looked like from the outside — Google
  impressions 5,095 → 210 in a day, position 10.7 → 37.5 over three, both
  properties reporting "Aucun problème détecté" and every technical check
  passing, while Bing (far more tolerant of link patterns) did not move at all.

  NO MONEY IS INVOLVED ON THIS SITE. The two `featured` hosts are the
  publisher's own businesses; the `recommended` cards came from a tourism data
  import. Both are promotion, which is why both are marked. The engine used to
  call these "paid, contractual" placements — that was never true and the
  wording is corrected wherever it appeared.

WHAT IS MARKED — two independent rules, either one is enough
  1. STRUCTURAL: every <a> inside a partner card (<article|button class="partner
     …">). Host-agnostic, so a new card cannot escape by using a new domain.
  2. HOST: every <a> to a host in site.config.json `promo_link_domains` —
     the publisher's own properties, wherever they appear on the page.

WHAT IS NOT MARKED, DELIBERATELY
  Every other outbound link: the venue's own official site, the office de
  tourisme, the mairie, patrimoines databases, reserves-naturelles.org,
  ffrandonnee.fr, etalab.gouv.fr, Wikimedia credits. Those are the evidence
  layer this engine exists to earn and they must keep passing their vote.
  Nofollowing them to fix a problem they are not part of would throw away the
  site's reason to exist.

  `noopener` is preserved (a security attribute, not an SEO one); `sponsored
  nofollow` is added alongside.

A POST-PASS, NOT A TEMPLATE EDIT
  Modelled on inject_analytics.py. Cards are emitted by several builders, so a
  template-by-template fix silently misses the next builder added. Runs BEFORE
  the byte-comparison gates, because the protected-card snapshots record the
  final shipped bytes.

Idempotent: a link already carrying sponsored is left byte-identical.

Usage:
    python3 scripts/mark_sponsored_links.py            # report, writes nothing
    python3 scripts/mark_sponsored_links.py --apply
"""
import argparse
import glob
import os
import re
import sys

import siteconfig

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = ("_site", ".git", "node_modules", "scripts", "Json", "api", "content")

DOMAINS = tuple(getattr(siteconfig, "PROMO_LINK_DOMAINS", ()) or ())

# Rule 1 — a partner card, opened by <article> or <button> carrying class
# "partner…", up to its matching close tag. Non-greedy so cards stay separate.
CARD_RE = re.compile(
    r'<(article|button)\b[^>]*\bclass="[^"]*\bpartner\b[^"]*"[^>]*>.*?</\1>', re.S | re.I)

# Rule 2 — an anchor to one of the publisher's own promo hosts, anywhere.
HOST_RE = re.compile(
    r'<a\b[^>]*\bhref="https?://(?:[^"/?#]*\.)?(?:'
    + "|".join(re.escape(d) for d in DOMAINS)
    + r')(?:[/?#][^"]*)?"[^>]*>', re.I) if DOMAINS else None

# Any external anchor (skip mailto:, tel:, and same-page/internal refs).
EXT_A_RE = re.compile(r'<a\b[^>]*\bhref="https?://[^"]*"[^>]*>', re.I)

# Our own host, never marked. An absolute self-link (the invite card's
# "devenir-partenaire" CTA is written with BASE_URL) is INTERNAL navigation, not
# promotion: nofollowing it only stops link equity flowing through our own site
# and tells Google we distrust our own page. Relative hrefs never match
# EXT_A_RE at all; this guard is for the absolute ones.
SELF_RE = re.compile(r'\bhref="https?://(?:[^"/?#]*\.)?'
                     + re.escape(siteconfig.DOMAIN) + r'(?:[/?#"])', re.I)


def _is_self(tag: str) -> bool:
    return bool(SELF_RE.search(tag))
REL_RE = re.compile(r'\brel="([^"]*)"', re.I)
REQUIRED = ("sponsored", "nofollow")


def qualify(tag: str) -> str:
    """Return `tag` with sponsored+nofollow in its rel, existing tokens kept."""
    m = REL_RE.search(tag)
    if not m:
        return tag[:-1].rstrip() + ' rel="sponsored nofollow">'
    tokens = m.group(1).split()
    lowered = {t.lower() for t in tokens}
    additions = [r for r in REQUIRED if r not in lowered]
    if not additions:
        return tag
    return tag[:m.start(1)] + " ".join(additions + tokens) + tag[m.end(1):]


def _mark_cards(html):
    """Qualify every external anchor inside every partner card. Returns (html, n)."""
    n = 0

    def fix_card(cm):
        nonlocal n
        card = cm.group(0)

        def fix_a(am):
            nonlocal n
            if _is_self(am.group(0)):
                return am.group(0)
            out = qualify(am.group(0))
            if out != am.group(0):
                n += 1
            return out

        return EXT_A_RE.sub(fix_a, card)

    return CARD_RE.sub(fix_card, html), n


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="write changes (default: report only)")
    args = ap.parse_args()

    seen = touched = fixed = 0
    for fp in glob.glob(os.path.join(ROOT, "**", "*.html"), recursive=True):
        rel = os.path.relpath(fp, ROOT)
        if rel.split(os.sep)[0] in SKIP_DIRS:
            continue
        seen += 1
        html = open(fp, encoding="utf-8").read()

        new, n = _mark_cards(html)
        if HOST_RE is not None:
            def fix_host(m):
                nonlocal n
                out = qualify(m.group(0))
                if out != m.group(0):
                    n += 1
                return out
            new = HOST_RE.sub(fix_host, new)

        if new == html:
            continue
        fixed += n
        touched += 1
        if args.apply:
            with open(fp, "w", encoding="utf-8") as fh:
                fh.write(new)

    verb = "" if args.apply else "would "
    own = f" · own hosts: {', '.join(DOMAINS)}" if DOMAINS else ""
    print(f"mark_sponsored_links: {seen} page(s) scanned · {verb}qualify {fixed} promotional "
          f"link(s) on {touched} page(s) [partner cards{own}] · editorial citations untouched")
    if not args.apply and fixed:
        print("  report only — re-run with --apply to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
