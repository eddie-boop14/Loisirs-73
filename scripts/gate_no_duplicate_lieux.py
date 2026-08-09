#!/usr/bin/env python3
"""gate_no_duplicate_lieux.py — preventive gate (builder-audit defect 1).

Duplicate "twins" — two slugs for the SAME lieu (same name + commune, both
rendered) — self-compete for the same query and split ranking signal. The DT
seeding path guards against this (seed_dt_partners.py skips existing names),
but Studio / agent / legacy integration paths have no name+commune existence
check, so twins can still be created (this session removed four:
sentier-des-roselieres, Urban Kart'in, Centre Aquatique Cluses, Château des
Rubins).

This gate is the structural backstop: normalise every renderable fiche's
(i18n.fr.name, commune) — accent-insensitive, lower-case, articles dropped —
and FAIL if any normalised pair appears on more than one slug.

Scope: status in (published, verified) — the surfaces that actually render and
get indexed. Drafts/unverified are intentionally held out of render, so they
are not twins yet; they're reported as a non-fatal heads-up so a draft that
would collide on publish is visible early.

Exit 1 on any colliding renderable pair. Reintroduce a twin → red.

Usage:
    python3 scripts/gate_no_duplicate_lieux.py
"""
import glob
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_DIR = os.path.join(ROOT, "Json")
RENDERABLE = ("published", "verified")

# Articles / prepositions that carry no discriminating signal for a place name.
STOP = {
    "de", "la", "le", "les", "du", "des", "d", "l", "a", "au", "aux",
    "et", "en", "sur", "sous", "the", "of", "and",
}


def norm(s):
    """Accent-insensitive, lower-case, article-stripped token string."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    toks = [t for t in re.findall(r"[a-z0-9]+", s.lower()) if t not in STOP]
    return " ".join(toks)


def fiche_name(d):
    i18n = d.get("i18n", {}) or {}
    return ((i18n.get("fr") or {}).get("name")
            or (i18n.get("en") or {}).get("name")
            or d.get("slug"))


def main():
    renderable = defaultdict(list)
    staged = defaultdict(list)   # draft/unverified, for the heads-up
    for fp in sorted(glob.glob(os.path.join(JSON_DIR, "*.json"))):
        d = json.loads(open(fp, encoding="utf-8").read())
        key = (norm(fiche_name(d)), norm(d.get("commune")))
        (renderable if d.get("status") in RENDERABLE else staged)[key].append(d["slug"])

    dups = {k: v for k, v in renderable.items() if len(v) > 1}

    # heads-up: a staged fiche whose (name,commune) already matches a renderable one
    pending = []
    for k, slugs in staged.items():
        if k in renderable:
            pending.append((k, slugs, renderable[k]))

    n = sum(len(v) for v in renderable.values())
    print(f"gate_no_duplicate_lieux: {n} renderable fiches, "
          f"{len(renderable)} distinct (name, commune) keys")

    if pending:
        print(f"  heads-up: {len(pending)} staged fiche(s) would collide on publish:")
        for (name, commune), s, r in pending:
            print(f"    ~ draft {s} vs published {r}  [{name} · {commune}]")

    if not dups:
        print("✓ no duplicate twins (every renderable name+commune is unique)")
        sys.exit(0)

    print(f"::error::{len(dups)} duplicate twin(s) — same name+commune, "
          f"multiple renderable slugs:")
    for (name, commune), slugs in sorted(dups.items()):
        print(f"    ✗ {sorted(slugs)}   [{name} · {commune}]")
    print("\nDedupe: keep the stronger fiche, 301 the other (see "
          "HANDOFF-dedupe recipe), and remove it from lieux.json + Json/.")
    sys.exit(1)


if __name__ == "__main__":
    main()
