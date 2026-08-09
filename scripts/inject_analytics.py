#!/usr/bin/env python3
"""inject_analytics.py — Cloudflare Web Analytics beacon, sitewide.

Final HTML pass: ensure every published page carries the loisirs74.fr beacon
immediately before </body>. Modelled on version_assets.py — same walk, same
skip set, same idempotency contract.

WHY A SCRIPT AND NOT A HAND-PASTE
  The tag has to sit on ~6,000 pages across 12 locales, and new pages are
  emitted on every build. Hand-pasting guarantees drift: the next fiche, hub or
  intent page ships without it and nobody notices, exactly the way the homepage
  cards and the hub banners rotted. Wired into build_all, this is derived —
  a page cannot be published without the beacon.

THE TOKEN IS THE POINT
  A Web Analytics token identifies WHICH SITE the traffic is attributed to.
  Pasting another property's token silently ships your visitors' data to that
  property and leaves loisirs74.fr with no data at all — and nothing in a build
  or a gate would flag it, because the markup is perfectly valid either way.
  So the token lives here, once, named and commented, rather than in prose.

Idempotent: a page already carrying the beacon is skipped. A page carrying a
DIFFERENT token is rewritten to the correct one — that is the repair path.

Usage:
    python3 scripts/inject_analytics.py            # report, writes nothing
    python3 scripts/inject_analytics.py --apply
"""
import argparse
import siteconfig  # HANDOFF-73: per-site identity
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = ("_site", ".git", "node_modules", "scripts", "reports", "Json", "api", "content")

# loisirs74.fr — Cloudflare Web Analytics. NOT any partner property's token.
TOKEN = siteconfig.CF_BEACON_TOKEN

SNIPPET = (
    "<!-- Cloudflare Web Analytics -->"
    "<script type='module' src='https://static.cloudflareinsights.com/beacon.min.js' "
    f"data-cf-beacon='{{\"token\": \"{TOKEN}\"}}'></script>"
    "<!-- End Cloudflare Web Analytics -->"
)

BEACON_RE = re.compile(
    r"<!-- Cloudflare Web Analytics -->.*?<!-- End Cloudflare Web Analytics -->", re.S
)
TOKEN_RE = re.compile(r'data-cf-beacon=\'\{"token":\s*"([0-9a-f]+)"\}\'')


def main():
    ap = argparse.ArgumentParser(description="Inject the Cloudflare Web Analytics beacon sitewide.")
    ap.add_argument("--apply", action="store_true", help="write changes (default: report only)")
    args = ap.parse_args()

    seen = added = repaired = skipped_nobody = 0
    foreign = {}

    for fp in glob.glob(os.path.join(ROOT, "**", "*.html"), recursive=True):
        rel = os.path.relpath(fp, ROOT)
        if rel.split(os.sep)[0] in SKIP_DIRS:
            continue
        seen += 1
        html = open(fp, encoding="utf-8").read()

        existing = BEACON_RE.search(html)
        if existing:
            m = TOKEN_RE.search(existing.group(0))
            if m and m.group(1) == TOKEN:
                continue                      # already correct
            foreign[m.group(1) if m else "unparseable"] = foreign.get(
                m.group(1) if m else "unparseable", 0) + 1
            new = BEACON_RE.sub(SNIPPET, html, count=1)
            repaired += 1
        else:
            if "</body>" not in html:
                skipped_nobody += 1
                continue
            new = html.replace("</body>", SNIPPET + "</body>", 1)
            added += 1

        if args.apply:
            with open(fp, "w", encoding="utf-8") as fh:
                fh.write(new)

    verb = "" if args.apply else "would "
    print(f"inject_analytics: {seen} page(s) scanned · {verb}add {added} · {verb}repair {repaired}")
    if foreign:
        for tok, n in foreign.items():
            print(f"  ⚑ FOREIGN TOKEN found on {n} page(s): {tok} — rewritten to {siteconfig.DOMAIN}'s")
    if skipped_nobody:
        print(f"  skipped (no </body>): {skipped_nobody}")
    if not args.apply and (added or repaired):
        print("  report only — re-run with --apply to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
