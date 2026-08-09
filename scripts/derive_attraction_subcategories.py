#!/usr/bin/env python3
"""
Derive a `subcategories` array on each attraction-tagged fiche JSON.

The 42 fiches whose top-level `lieux.json` categories include "attraction"
share a single coarse bucket today. The homepage rebuild needs finer
buckets (escape / laser / bowling / aquatique / spa / patinoire / karting
/ casino / accrobranche / croisiere / jardin / wakepark / divers) so a
future homepage iteration can carve attraction into sub-sections without
another data pass.

Signal priority:
  1. The per-fiche `category` field (already specific for ~70% of fiches).
  2. Slug-prefix inference from the table in the plan.

Output is additive: `subcategories` is a new top-level array. No other
field is touched. Existing `category` / `categories` remain authoritative
for renderers, hubs, related-mesh, breadcrumbs, sitemap.

Every assignment is logged to scripts/derive_attraction_subcategories.log
so the user can review and correct.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LIEUX_PATH = REPO / "lieux.json"
JSON_DIR = REPO / "Json"
LOG_PATH = REPO / "scripts" / "derive_attraction_subcategories.log"

# Per-fiche `category` -> subcategory bucket. None means "fall through to slug rules".
CATEGORY_BUCKET: dict[str, str] = {
    "aquaparc": "aquatique",
    "centre-aquatique": "aquatique",
    "piscine": "aquatique",
    "centre-nautique": "aquatique",
    "espace-aquatique": "aquatique",
    "bowling": "bowling",
    "karting": "karting",
    "patinoire": "patinoire",
    "casino": "casino",
    "accrobranche": "accrobranche",
    "escape-game": "escape",
    "laser-game": "laser",
    "trampoline-park": "trampoline",
    "escalade": "escalade",
    "spa": "spa",
    "thermes": "spa",
    "base-nautique": "wakepark",
    "wakepark": "wakepark",
    "croisiere": "croisiere",
    "jardin": "jardin",
}

# Slug-prefix -> subcategory bucket. Tried in declaration order; first match wins.
# Used only when the per-fiche `category` is "attraction" (the catch-all).
SLUG_RULES: list[tuple[str, str]] = [
    ("escape-game-", "escape"),
    ("laser-game-", "laser"),
    ("bowling-", "bowling"),
    ("karting-", "karting"),
    ("patinoire-", "patinoire"),
    ("aquaparc-", "aquatique"),
    ("centre-aquatique-", "aquatique"),
    ("piscine-", "aquatique"),
    ("centre-nautique-", "aquatique"),
    ("espace-aquatique-", "aquatique"),
    ("spa-", "spa"),
    ("thermes-", "spa"),
    ("casino-", "casino"),
    ("trampoline-park-", "trampoline"),
    ("escalade-", "escalade"),
    ("accrobranche-", "accrobranche"),
    ("acro-aventures-", "accrobranche"),
    ("acroparc-", "accrobranche"),
    ("passy-accro-", "accrobranche"),
    ("wakepark-", "wakepark"),
    ("base-nautique-", "wakepark"),
    ("croisiere-", "croisiere"),
    ("jardin-", "jardin"),
]

# Subcategories that map to outdoor activities — flagged for user review.
OUTDOOR_FLAGGED = {"wakepark", "croisiere", "jardin"}


def attraction_slugs() -> list[str]:
    data = json.loads(LIEUX_PATH.read_text(encoding="utf-8"))
    out = []
    for lieu in data["lieux"]:
        cats = lieu.get("categories") or []
        if "attraction" in cats:
            out.append(lieu["slug"])
    return sorted(out)


def infer_subcategory(slug: str, fiche_category: str | None) -> tuple[str, str]:
    """Returns (subcategory, signal) where signal is 'category' or 'slug' or 'fallback'."""
    if fiche_category and fiche_category != "attraction":
        bucket = CATEGORY_BUCKET.get(fiche_category)
        if bucket:
            return bucket, f"category={fiche_category}"
    for prefix, bucket in SLUG_RULES:
        if slug.startswith(prefix):
            return bucket, f"slug-prefix={prefix}"
    return "divers", "fallback"


def main() -> None:
    log_lines: list[str] = []
    written = 0
    skipped = 0
    by_bucket: dict[str, list[str]] = {}
    flagged: list[str] = []

    for slug in attraction_slugs():
        fiche_path = JSON_DIR / f"{slug}.json"
        if not fiche_path.exists():
            log_lines.append(f"MISSING  {slug}")
            continue
        fiche = json.loads(fiche_path.read_text(encoding="utf-8"))
        bucket, signal = infer_subcategory(slug, fiche.get("category"))
        existing = fiche.get("subcategories")
        if existing == [bucket]:
            skipped += 1
            log_lines.append(f"SKIP     {slug:55s} subcategories={existing} (already set)")
            by_bucket.setdefault(bucket, []).append(slug)
            continue
        fiche["subcategories"] = [bucket]
        fiche_path.write_text(
            json.dumps(fiche, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written += 1
        flag = " [REVIEW: outdoor]" if bucket in OUTDOOR_FLAGGED else ""
        log_lines.append(
            f"WRITE    {slug:55s} -> {bucket:14s} via {signal}{flag}"
        )
        by_bucket.setdefault(bucket, []).append(slug)
        if bucket in OUTDOOR_FLAGGED:
            flagged.append(f"{slug} -> {bucket}")

    log_lines.append("")
    log_lines.append("=== Summary ===")
    log_lines.append(f"written: {written}")
    log_lines.append(f"skipped (already current): {skipped}")
    log_lines.append("")
    log_lines.append("Buckets:")
    for bucket in sorted(by_bucket):
        log_lines.append(f"  {bucket:14s} {len(by_bucket[bucket]):2d}  {by_bucket[bucket]}")
    if flagged:
        log_lines.append("")
        log_lines.append("Flagged outdoor (review):")
        for f in flagged:
            log_lines.append(f"  {f}")

    LOG_PATH.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    print(f"Wrote {written} files, skipped {skipped}. Log: {LOG_PATH}")
    for bucket in sorted(by_bucket):
        print(f"  {bucket:14s} {len(by_bucket[bucket]):2d}")


if __name__ == "__main__":
    main()
