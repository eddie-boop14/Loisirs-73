#!/usr/bin/env python3
"""mark_sponsored_links.py — rel=sponsored on every PAID placement link.

WHY THIS EXISTS
  loisirs74.fr carried 1,044 followed links to two paid, contractual partner
  domains across 426 pages, every one of them `rel="noopener"` — not one
  sponsored, not one nofollow. Google's link-spam policy is explicit: a link
  given in exchange for payment must be qualified. Unqualified, it is a link
  scheme, and the enforcement is ALGORITHMIC — SpamBrain devalues the linking
  site with no manual action to warn you. Search Console stays green while the
  site sinks, which is exactly what happened here: Google impressions fell 96%
  (5,095 → 210 in a day, position 10.7 → 37.5 over three) while Bing, which is
  far more tolerant of link schemes, did not move at all (436 → 418/day, noise).

WHAT IS AND IS NOT MARKED
  Marked: every outbound <a> whose host is (or is a subdomain of) a host in
  site.config.json `paid_partner_domains`. Those links are advertising.

  NOT marked, deliberately: every other outbound link — the venue's own site,
  the tourist office, patrimoines.savoie.fr, Wikimedia credit links. Those are
  editorial citations, the evidence layer the whole engine is built to earn.
  Nofollowing them would throw away the site's reason to exist to fix a problem
  they are not part of. The distinction is the point of this script.

  `noopener` is preserved wherever it was (it is a security attribute, not an
  SEO one); `sponsored nofollow` is added alongside it. Both are emitted because
  sponsored is the precise term and nofollow is the universally understood
  fallback for older parsers.

A POST-PASS, NOT A TEMPLATE EDIT
  Modelled on inject_analytics.py: one derived, idempotent sweep over the built
  tree, wired into build_all. Partner links are emitted from several builders
  (fiche cards, hub cards, commune pages, the facts-lang trees) and a
  template-by-template fix would silently miss one the next time a builder is
  added — the exact failure mode the reveal-hidden fix hit on the 73.

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

DOMAINS = tuple(siteconfig.PAID_PARTNER_DOMAINS)

# <a ...> with an href on one of the paid hosts. Host match is anchored to the
# authority component so "notcheznousalaplage.com.evil.test" cannot match.
_HOST_ALT = "|".join(re.escape(d) for d in DOMAINS)
ANCHOR_RE = re.compile(
    r'<a\b[^>]*\bhref="https?://(?:[^"/?#]*\.)?(?:' + _HOST_ALT + r')(?:[/?#][^"]*)?"[^>]*>',
    re.I,
) if DOMAINS else None

REL_RE = re.compile(r'\brel="([^"]*)"', re.I)
REQUIRED = ("sponsored", "nofollow")


def qualify(tag: str) -> str:
    """Return `tag` with sponsored+nofollow present in its rel, order preserved."""
    m = REL_RE.search(tag)
    if not m:
        return tag[:-1].rstrip() + ' rel="sponsored nofollow">'
    tokens = m.group(1).split()
    lowered = {t.lower() for t in tokens}
    additions = [r for r in REQUIRED if r not in lowered]
    if not additions:
        return tag
    return tag[:m.start(1)] + " ".join(additions + tokens) + tag[m.end(1):]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="write changes (default: report only)")
    args = ap.parse_args()

    if not DOMAINS:
        print("mark_sponsored_links: no paid_partner_domains configured for "
              f"{siteconfig.DOMAIN} — nothing to mark (editorial links stay followed).")
        return 0

    seen = touched = links = already = 0
    for fp in glob.glob(os.path.join(ROOT, "**", "*.html"), recursive=True):
        rel = os.path.relpath(fp, ROOT)
        if rel.split(os.sep)[0] in SKIP_DIRS:
            continue
        seen += 1
        html = open(fp, encoding="utf-8").read()
        found = ANCHOR_RE.findall(html)
        if not found:
            continue
        new = ANCHOR_RE.sub(lambda m: qualify(m.group(0)), html)
        n = len(found)
        if new == html:
            already += n
            continue
        links += n
        touched += 1
        if args.apply:
            with open(fp, "w", encoding="utf-8") as fh:
                fh.write(new)

    verb = "" if args.apply else "would "
    print(f"mark_sponsored_links [{', '.join(DOMAINS)}]: {seen} page(s) scanned · "
          f"{verb}qualify {links} link(s) on {touched} page(s) · {already} already sponsored")
    if not args.apply and links:
        print("  report only — re-run with --apply to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
