#!/usr/bin/env python3
"""gate_baignade_cluster.py — the swimming cluster keeps its on-page mesh.

The baignade intent hubs (baignade-lac-annecy, baignade-leman,
ou-se-baigner-haute-savoie) define the curated beach set. Every one of those
member fiches must render, in FR + 5 locales:
  - an "L'essentiel" highlight block, and
  - a "Plages voisines" mesh block with ≥3 links, all of which resolve.

This locks in HANDOFF-01's link-equity mesh so a refactor can't silently drop it.
Exit 1 on any violation. Read-only (run after build_all).
"""
import glob
import json
import os
import re
import siteconfig  # HANDOFF-73 phase 4: per-site domain
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import locales  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(ROOT, "data", "intent-hubs.json")
LANGS = locales.PROSE
HUBS = ("baignade-lac-annecy", "baignade-leman", "ou-se-baigner-haute-savoie")


def page_path(slug, lang):
    return os.path.join(ROOT, f"{slug}.html") if lang == "fr" \
        else os.path.join(ROOT, lang, f"{slug}.html")


def resolves(href):
    """An absolute loisirs74.fr link resolves to a built file."""
    m = re.match(r"https://" + siteconfig.DOMAIN_RE + r"(/.*)?$", href)
    if not m:
        return True  # external / non-site — out of scope
    path = (m.group(1) or "/").split("#")[0].split("?")[0].strip("/")
    if not path:
        return os.path.exists(os.path.join(ROOT, "index.html"))
    return (os.path.exists(os.path.join(ROOT, f"{path}.html"))
            or os.path.exists(os.path.join(ROOT, path, "index.html")))


def main():
    reg = json.loads(open(REG, encoding="utf-8").read())
    beaches = []
    for h in reg:
        if h["slug"] in HUBS:
            beaches += [m["slug"] for m in h["members"]]
    beaches = sorted(set(beaches))
    viol = []
    for slug in beaches:
        for lang in LANGS:
            p = page_path(slug, lang)
            if not os.path.exists(p):
                viol.append(f"{slug}/{lang}: page missing"); continue
            html = open(p, encoding="utf-8").read()
            # HANDOFF-35 defect 5: exactly ONE essentiel block per page —
            # absence and duplication are both diseases.
            n_ess = html.count('<section class="essentiel"')
            if n_ess != 1:
                viol.append(f"{slug}/{lang}: essentiel block count {n_ess} (must be exactly 1)")
            m = re.search(r'<section class="plages-voisines".*?</section>', html, re.S)
            if not m:
                viol.append(f"{slug}/{lang}: no Plages voisines block"); continue
            hrefs = re.findall(r'href="([^"]+)"', m.group(0))
            if len(hrefs) < 3:
                viol.append(f"{slug}/{lang}: Plages voisines has {len(hrefs)} link(s) (<3)")
            dead = [h for h in hrefs if not resolves(h)]
            if dead:
                viol.append(f"{slug}/{lang}: dead mesh link(s) {dead[:3]}")

    print(f"gate_baignade_cluster: {len(beaches)} beach fiche(s) × {len(LANGS)} locales")
    if viol:
        print(f"::error::{len(viol)} cluster violation(s):")
        for v in viol[:50]:
            print(f"    ✗ {v}")
        sys.exit(1)
    print("✓ every beach has L'essentiel + a resolving ≥3-link Plages voisines mesh")


if __name__ == "__main__":
    main()
