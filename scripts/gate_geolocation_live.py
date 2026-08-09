#!/usr/bin/env python3
"""gate_geolocation_live.py — regression guard for the "Près de moi" feature.

The proximity feature is invisible when it breaks (no error, just a button that
does nothing), so it has silently died twice. Two independent failure modes,
one grep each:

  1. netlify.toml Permissions-Policy must not forbid geolocation. A header of
     `geolocation=()` is an EMPTY allowlist → the Geolocation API is blocked
     for every origin, including loisirs74.fr itself. The directive must be
     present AND include `self`.

  2. Any rendered page that carries the button (`id="nearMe"`) must also load
     `/scripts/nearme.js` — the only script with geolocation logic (l74sort.js
     has none). A button with no script is dead.

Read-only. Exit 1 on either. Run after build_all (so the homepages are patched).

Usage:
    python3 scripts/gate_geolocation_live.py
"""
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def check_header():
    path = os.path.join(ROOT, "netlify.toml")
    if not os.path.exists(path):
        return ["netlify.toml not found at repo root"]
    toml = open(path, encoding="utf-8").read()
    pps = re.findall(r'Permissions-Policy\s*=\s*"([^"]*)"', toml)
    if not pps:
        return ["netlify.toml: no Permissions-Policy header"]
    out = []
    for pp in pps:
        m = re.search(r"geolocation=\(([^)]*)\)", pp)
        if m is None:
            out.append(f'Permissions-Policy has no geolocation directive: "{pp}"')
        elif m.group(1).strip() == "":
            out.append('Permissions-Policy "geolocation=()" — EMPTY allowlist '
                       'blocks geolocation for ALL origins. Use geolocation=(self).')
        elif "self" not in m.group(1):
            out.append(f'Permissions-Policy geolocation=({m.group(1).strip()}) '
                       'omits self → same-origin geolocation blocked.')
    return out


def check_pages():
    out = []
    seen = 0
    for fp in glob.glob(os.path.join(ROOT, "**", "*.html"), recursive=True):
        rel = os.path.relpath(fp, ROOT)
        if rel.startswith("_site" + os.sep) or rel.startswith("node_modules" + os.sep):
            continue
        html = open(fp, encoding="utf-8").read()
        if 'id="nearMe"' not in html:
            continue
        seen += 1
        if '/scripts/nearme.js' not in html:
            out.append(rel)
    return out, seen


def main():
    header = check_header()
    bad_pages, n_nearme = check_pages()

    print(f"gate_geolocation_live: checked netlify.toml header + "
          f"{n_nearme} page(s) carrying the #nearMe button")

    violations = []
    for h in header:
        violations.append(f"HEADER: {h}")
    for p in bad_pages:
        violations.append(f"PAGE: {p} has #nearMe but does not load /scripts/nearme.js")

    if not violations:
        print("✓ geolocation allowed for self; every #nearMe page loads nearme.js")
        sys.exit(0)

    print(f"::error::{len(violations)} geolocation regression(s):")
    for v in violations:
        print(f"    ✗ {v}")
    print("\nFix: netlify.toml → Permissions-Policy geolocation=(self); homepages "
          "include /scripts/nearme.js via build_hubs.patch_homepage_nearme.")
    sys.exit(1)


if __name__ == "__main__":
    main()
