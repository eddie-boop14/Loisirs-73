#!/usr/bin/env python3
"""robots.txt parse test — HANDOFF-39A-C3.

The authored robots.txt is chrome the whole crawl budget hangs on; a stray
edit (an accidental `Disallow: /`, a broken directive, a lost Sitemap line)
must go red in CI, not in Search Console three weeks later.

Asserts, on the AUTHORED file (build_site injects the Studio Disallows at
deploy — that step is additive and out of scope here):
  1. every non-comment line is `Directive: value` with a known directive
  2. no `Disallow: /` (site-wide block) under ANY user-agent group
  3. `User-agent: *` group exists and carries `Allow: /`
  4. exactly one Sitemap line, absolute https URL on the site's own host
  5. the AI fast lane stays advertised: llms.txt + api/lieux.json comments
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import siteconfig  # HANDOFF-73: per-site identity — the host was hardcoded here
KNOWN = {"user-agent", "allow", "disallow", "sitemap", "crawl-delay"}


def main():
    path = os.path.join(ROOT, "robots.txt")
    text = open(path, encoding="utf-8").read()
    errors = []

    # A site that has not launched yet asserts the OPPOSITE contract. The
    # FLIP-AT-LAUNCH marker means the site-wide block is deliberate: a thin
    # placeholder must not be indexed, and neither must the *.netlify.app
    # preview domain. Testing such a file for "no Disallow: /" and "exactly
    # one Sitemap" reports five failures for a file that is exactly right.
    if "FLIP-AT-LAUNCH" in text:
        blocked = re.search(r"^User-agent:\s*\*\s*$.*?^Disallow:\s*/\s*$",
                            text, re.M | re.S)
        if not blocked:
            print("::error::robots.txt carries the FLIP-AT-LAUNCH marker but "
                  "does NOT block the site — that marker is the only thing "
                  "keeping a pre-launch placeholder out of the index")
            sys.exit(1)
        print("robots.txt: pre-launch (FLIP-AT-LAUNCH) — site-wide block "
              "present and correct; launched-shape checks deferred")
        return

    groups = {}          # ua -> list of (directive, value)
    current_uas = []
    sitemaps = []
    for i, line in enumerate(text.split("\n"), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z-]+)\s*:\s*(.*)$", s)
        if not m:
            errors.append(f"line {i}: unparseable: {s!r}")
            continue
        directive, value = m.group(1).lower(), m.group(2).strip()
        if directive not in KNOWN:
            errors.append(f"line {i}: unknown directive {m.group(1)!r}")
            continue
        if directive == "sitemap":
            sitemaps.append((i, value))
            continue
        if directive == "user-agent":
            current_uas = [value]
            groups.setdefault(value, [])
            continue
        if not current_uas:
            errors.append(f"line {i}: {directive} outside any User-agent group")
            continue
        for ua in current_uas:
            groups[ua].append((i, directive, value))

    # 2. no site-wide block anywhere
    for ua, rules in groups.items():
        for i, directive, value in rules:
            if directive == "disallow" and value == "/":
                errors.append(f"line {i}: Disallow: / under User-agent: {ua} — "
                              "site-wide block!")

    # 3. the * group allows /
    star = groups.get("*")
    if star is None:
        errors.append("no `User-agent: *` group")
    elif not any(d == "allow" and v == "/" for _i, d, v in star):
        errors.append("`User-agent: *` group lacks `Allow: /`")

    # 4. exactly one absolute Sitemap
    if len(sitemaps) != 1:
        errors.append(f"expected exactly 1 Sitemap line, found {len(sitemaps)}")
    else:
        i, v = sitemaps[0]
        if not v.startswith(siteconfig.BASE_URL + "/"):
            errors.append(f"line {i}: Sitemap must be absolute on "
                          f"{siteconfig.DOMAIN}: {v!r}")

    # 5. AI fast-lane advertisement intact (comment lines, HANDOFF-39 blocker 3)
    for needle in (siteconfig.BASE_URL + "/llms.txt",
                   siteconfig.BASE_URL + "/api/lieux.json"):
        if needle not in text:
            errors.append(f"AI fast-lane advertisement lost: {needle} not in robots.txt")

    if errors:
        print(f"::error::robots.txt: {len(errors)} problem(s):")
        for e in errors:
            print(f"    ✗ {e}")
        sys.exit(1)
    print(f"test_robots_txt: {len(groups)} UA groups, 1 sitemap, fast lane advertised. ✓")


if __name__ == "__main__":
    main()
