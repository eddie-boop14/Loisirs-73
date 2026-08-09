#!/usr/bin/env python3
"""Build catalog-index.json from lieux.json + per-fiche JSONs.

Schema (compact, designed for browser fetch + filter):
    [
      {
        "slug": "plage-de-saint-jorioz",
        "name": "Plage de Saint-Jorioz",
        "commune": "Saint-Jorioz",
        "category": "plage",
        "hero": "/plage-de-saint-jorioz-hero.jpg",
        "real": true
      },
      ...
    ]

`real` = True when hero_image is NOT a generic placeholder
(i.e. doesn't start with "/generique-" or "generique-").
The Photothèque uses this to surface fiches still on generics.
"""
import json
import siteconfig  # HANDOFF-73: per-site identity
import glob
import re
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import locales  # noqa: E402
import derive_access_cost as dac  # noqa: E402  (the one derived access-cost model)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def is_real(hero):
    """A hero is 'real' only when:
    - it's an external URL (Wikimedia/Commons etc.), OR
    - it's a local per-fiche photo (/img/<hub>/<slug>-hero.jpg or
      /<slug>-hero.jpg) AND the file actually exists on disk.
    Generic placeholders (generique-*.jpg) and broken local refs both → False.

    2026-06-15: local images now live under /img/<hub>/. Both the legacy
    leading-slash format and the new /img/-prefixed format resolve via
    `lstrip("/")` + path-exists check, so this function works for both.
    """
    if not hero:
        return False
    if hero.startswith(("http://", "https://")):
        return True
    name = hero.lstrip("/")
    basename = name.rsplit("/", 1)[-1]
    if basename.startswith("generique-"):
        return False
    return os.path.exists(os.path.join(ROOT, name))


LANGS = locales.PROSE_SECONDARY


def main():
    out = []
    api_out = []
    root_out = []          # the facet-layer manifest (root lieux.json) — is_free/access_state gate
    for path in sorted(glob.glob(os.path.join(ROOT, "Json", "*.json"))):
        d = json.load(open(path))
        slug = d.get("slug")
        if not slug:
            continue
        # JOB 6: draft fiches are not in the public catalog.
        # 'unverified' (source-audit) is held out of the index exactly like draft.
        if d.get("status") in ("draft", "unverified"):
            continue
        fr = (d.get("i18n") or {}).get("fr") or {}
        name = fr.get("name") or slug
        commune = d.get("commune") or ""
        category = d.get("category") or "?"
        hero = d.get("hero_image") or ""
        # Derived access-cost state — the single source of truth for the free hub
        # (replaces the hand-maintained is_free bool that drifted on ~27 fiches).
        access_state = dac.derive(d)[0]
        root_out.append({
            "slug": slug,
            "categories": d.get("categories") or ([category] if category and category != "?" else []),
            "i18n": {lg: {"name": ((d.get("i18n") or {}).get(lg) or {}).get("name") or name,
                          "commune": commune}
                     for lg in ("fr",) + tuple(LANGS)},
            "latitude": d.get("latitude"),
            "longitude": d.get("longitude"),
            "is_free": access_state == "free",
            "access_state": access_state,
        })
        out.append({
            "slug": slug,
            "name": name,
            "commune": commune,
            "category": category,
            "hero": hero,
            "real": is_real(hero),
        })
        # api/lieux.json — the public machine index (nearme.js, AI agents).
        # Regenerated here from published Json/ so a publish-flip auto-appears
        # (it used to be a static snapshot that drifted).
        item = {
            "slug": slug,
            "name": name,
            "category": category,
            "commune": commune,
            "postal_code": d.get("postal_code") or "",
            "latitude": d.get("latitude"),
            "longitude": d.get("longitude"),
            "urls": {"fr": f"{siteconfig.BASE_URL}/{slug}",
                     **{l: f"{siteconfig.BASE_URL}/{l}/{slug}" for l in LANGS}},
            # HANDOFF-39 facet layer: per-lieu machine surfaces (md FR/EN + typed JSON)
            "facet_md": f"{siteconfig.BASE_URL}/content/{slug}.md",
            "facet_md_en": f"{siteconfig.BASE_URL}/content/en/{slug}.md",
            "facet_json": f"{siteconfig.BASE_URL}/api/lieu/{slug}.json",
        }
        if hero:
            item["photo"] = hero
        api_out.append(item)

    out.sort(key=lambda r: r["slug"])
    target = os.path.join(ROOT, "catalog-index.json")
    with open(target, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    print(f"wrote {target}: {len(out)} entries")

    api_out.sort(key=lambda r: r["slug"])
    api_target = os.path.join(ROOT, "api", "lieux.json")
    with open(api_target, "w", encoding="utf-8") as f:
        json.dump({"count": len(api_out), "lieux": api_out}, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"wrote {api_target}: {len(api_out)} entries")

    # root lieux.json — the facet-layer manifest (build_facet_hubs / gate_facet_hubs
    # / derive_attraction_subcategories read it). GENERATED here so it can never
    # drift from Json/ again (§2 the-one-law); published-only, so drafts are evicted.
    root_out.sort(key=lambda r: r["slug"])
    root_target = os.path.join(ROOT, "lieux.json")
    with open(root_target, "w", encoding="utf-8") as f:
        json.dump({"_comment": "GENERATED by scripts/build_catalog_index.py from published "
                               "Json/*.json — do not hand-edit. access_state is the derived "
                               "free-hub gate (free | free_seasonal | paid).",
                   "lieux": root_out}, f, ensure_ascii=False, indent=2)
        f.write("\n")
    from collections import Counter as _C
    _st = _C(r["access_state"] for r in root_out)
    print(f"wrote {root_target}: {len(root_out)} entries "
          f"(free={_st['free']} free_seasonal={_st['free_seasonal']} paid={_st['paid']})")

    n_real = sum(1 for r in out if r["real"])
    n_gen = len(out) - n_real
    print(f"  fiches with real hero: {n_real}")
    print(f"  fiches on generic:     {n_gen}")


if __name__ == "__main__":
    main()
