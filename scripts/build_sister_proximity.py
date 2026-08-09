#!/usr/bin/env python3
"""Regenerate data/sister-proximity.json — the sibling site's place index.

Cross-department "À proximité" cards are the one link no tourism office can
replicate: the same publisher, the same standard, on both sides of a border
that visitors cross without noticing. This script extracts the published,
coordinate-bearing places from the SIBLING repo's Json/ corpus into a small
local index that build_lieu_page.py reads at render time.

It is NOT part of build_all. The sibling checkout is a developer's machine
detail, not a deploy dependency — Netlify never has it. Run this by hand when
the sibling publishes new fiches, and commit the result:

    python3 scripts/build_sister_proximity.py --sister /path/to/loisir-74

Honesty rules this file exists to enforce:

  * Only PUBLISHED fiches with real coordinates travel. A draft on the other
    site must not surface here as a live recommendation.
  * URLs are absolute to the sibling origin, always — the reader is leaving
    this site and the link must say so.
  * Hero URLs are joined, not concatenated. The sibling's corpus mixes
    root-relative heroes (/img/...) with absolute ones (Wikimedia). Prefixing
    the origin onto an already-absolute URL produced 73 dead images the first
    time this index was built by hand; urljoin cannot make that mistake.
"""
import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import siteconfig  # HANDOFF-73: per-site identity
import locales

VISIBLE = tuple(locales.VISIBLE)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sister-proximity.json"

RULE = (
    "Cross-department proximity is REAL but narrow. These entries are only "
    "offered when they fall inside sister_proximity_km of a local fiche — "
    "{km:g} km, which in this terrain is roughly 40 minutes. At 60 km the pair "
    "count explodes to four figures and 'nearby' stops meaning anything on an "
    "alpine road. Cards from this file must stay visibly marked as the sibling "
    "site: they are a genuine same-publisher cross-link, not local content."
)


def _hero_url(fiche, origin):
    """Absolute hero URL, or None. Never concatenates onto an absolute URL."""
    h = fiche.get("hero_image") or fiche.get("hero") or {}
    u = h.get("url") if isinstance(h, dict) else h
    if not u or not isinstance(u, str):
        return None
    # urljoin returns u unchanged when u is already absolute — that is the
    # whole point of using it here.
    return urljoin(origin, u)


def main():
    sis = getattr(siteconfig, "SISTER", None)
    if not sis:
        sys.exit("no `sister` block in site.config.json — nothing to index")

    ap = argparse.ArgumentParser()
    ap.add_argument("--sister", required=True,
                    help="path to the sibling site's repo checkout")
    args = ap.parse_args()

    src = Path(args.sister) / "Json"
    if not src.is_dir():
        sys.exit(f"no Json/ corpus at {src}")

    origin = sis["url"].rstrip("/") + "/"
    places, skipped = [], {"draft": 0, "no_coords": 0, "no_name": 0, "unreadable": 0}

    for f in sorted(src.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            skipped["unreadable"] += 1
            continue
        if d.get("status") != "published":
            skipped["draft"] += 1
            continue
        lat, lon = d.get("latitude"), d.get("longitude")
        if lat is None or lon is None:
            skipped["no_coords"] += 1
            continue
        slug = d.get("slug") or f.stem
        i18n = d.get("i18n") or {}
        fr_name = ((i18n.get("fr") or {}).get("name") or "").strip()
        if not fr_name:
            skipped["no_name"] += 1
            continue
        # 186 of the sibling's fiches carry a genuinely translated name
        # ("Suivez la mouche" → "Follow the Fly"). A card that shows the French
        # name to a Dutch reader and then lands them on the Dutch page is
        # sloppy on both ends, so names travel per locale and only when they
        # actually differ — FR is the fallback the renderer already applies.
        names = {}
        for lang in VISIBLE:
            n = ((i18n.get(lang) or {}).get("name") or "").strip()
            if n and n != fr_name:
                names[lang] = n
        places.append({
            "slug": slug,
            "name": fr_name,
            "names": names,
            "commune": d.get("commune"),
            "lat": float(lat),
            "lon": float(lon),
            "url": urljoin(origin, slug),
            "hero": _hero_url(d, origin),
        })

    places.sort(key=lambda p: p["slug"])
    payload = {
        "_meta": {
            "source": sis["name"],
            "site": sis["url"],
            "dept": sis.get("dept"),
            "generated": date.today().isoformat(),
            "count": len(places),
            "rule": RULE.format(km=float(getattr(siteconfig, "SISTER_PROXIMITY_KM", 0) or 0)),
        },
        "places": places,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                              sort_keys=False) + "\n", encoding="utf-8")

    abs_heroes = sum(1 for p in places if p["hero"] and not p["hero"].startswith(origin))
    print(f"build_sister_proximity: {len(places)} published places from {sis['name']} "
          f"({abs_heroes} off-origin heroes kept absolute, "
          f"{sum(1 for p in places if not p['hero'])} without a hero)")
    print(f"  skipped: {skipped['draft']} draft · {skipped['no_coords']} without coords "
          f"· {skipped['no_name']} without a name · {skipped['unreadable']} unreadable")


if __name__ == "__main__":
    main()
