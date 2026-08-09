#!/usr/bin/env python3
"""Published-verified gate — SPECsourceexistenceaudit §S4.

Read-only. Enforces Eddie's rule: a fiche that the source-audit could not verify
(status:"unverified") must NOT be reachable through any public surface — it is
held back until a human confirms or unpublishes it. Asserts that no
status:"unverified" slug appears in:

  * catalog-index.json        (the catalog the site browses)
  * api/lieux.json            (the machine index AI agents fetch)
  * sitemap.xml               (what search engines crawl)
  * <hub>/index.html          (category hub listings, all locales)

Any leak → exit 1 (build red). With 0 unverified fiches the gate is a no-op that
passes — it only bites once the audit's --apply flags something.

The build already excludes status in ("draft","unverified") from render / index
/ hubs / sitemap; this gate is the independent proof that the exclusion held.
"""
import argparse
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELD_STATUSES = ("unverified",)  # draft already has its own long-standing handling
# top-level dirs that are NOT category hubs
NON_HUB = {"api", "content", "img", "images", "assets", "css", "js", "fonts",
           "scripts", "Json", "reports", "cache", "communes", "_site",
           ".git", ".github", ".well-known", "node_modules", "tests"}


def held_slugs(json_dir):
    out = []
    for f in sorted(glob.glob(os.path.join(json_dir, "*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        if d.get("status") in HELD_STATUSES:
            out.append(d["slug"])
    return out


def hub_index_files(root):
    """FR + locale category-hub index.html files (best-effort discovery)."""
    files = []
    for p in glob.glob(os.path.join(root, "*", "index.html")):
        if os.path.basename(os.path.dirname(p)) not in NON_HUB:
            files.append(p)
    for p in glob.glob(os.path.join(root, "??", "*", "index.html")):
        if os.path.basename(os.path.dirname(p)) not in NON_HUB:
            files.append(p)
    return files


def main():
    ap = argparse.ArgumentParser(description="Assert no unverified fiche is publicly reachable.")
    ap.add_argument("--json-dir", default=os.path.join(ROOT, "Json"))
    ap.add_argument("--root", default=ROOT)
    args = ap.parse_args()

    held = held_slugs(args.json_dir)
    print(f"gate_published_verified: {len(held)} fiche(s) held (status in {HELD_STATUSES})")
    if not held:
        print("✓ no held fiches — nothing can leak into hub / sitemap / index")
        sys.exit(0)

    held_set = set(held)
    violations = []

    def scan_text(path, label):
        if not os.path.exists(path):
            return
        txt = open(path, encoding="utf-8", errors="ignore").read()
        for slug in held_set:
            # word-boundary-ish: slug delimited by / " < or whitespace
            if re.search(rf"[\"/]{re.escape(slug)}[\"/.<\s]", txt):
                violations.append(f"{label}: references held fiche '{slug}'")

    def scan_json_slugs(path, label):
        if not os.path.exists(path):
            return
        try:
            data = json.load(open(path, encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        blob = json.dumps(data, ensure_ascii=False)
        for slug in held_set:
            if f'"{slug}"' in blob:
                violations.append(f"{label}: indexes held fiche '{slug}'")

    scan_json_slugs(os.path.join(args.root, "catalog-index.json"), "catalog-index.json")
    scan_json_slugs(os.path.join(args.root, "api", "lieux.json"), "api/lieux.json")
    scan_text(os.path.join(args.root, "sitemap.xml"), "sitemap.xml")
    for hub in hub_index_files(args.root):
        scan_text(hub, os.path.relpath(hub, args.root))

    if not violations:
        print(f"✓ {len(held)} held fiche(s) absent from catalog / lieux.json / sitemap / hubs")
        sys.exit(0)
    print(f"::error::{len(violations)} unverified-fiche leak(s) into public surfaces:")
    for v in sorted(set(violations))[:40]:
        print(f"    ✗ {v}")
    print("\nA status:\"unverified\" fiche must be held out of index/hubs/sitemap until "
          "a human verifies it. Re-run build_all (the filters exclude unverified).")
    sys.exit(1)


if __name__ == "__main__":
    main()
