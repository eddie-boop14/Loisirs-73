#!/usr/bin/env python3
"""gate_hero_integrity.py — the hero-image trust + performance guard
(HANDOFF-hero-integrity, FIX B).

Installs, as a build-blocking invariant, the end-state that localize_heroes.py
and Eddie's worklist B produce. Once green it stays green: no hero may regress
to a hotlink, an uncredited real photo, a placeholder credit, a dangling local
path, or a silently-shared (wrong-subject) image.

FAILS the build when any fiche:
  * has a `hero_image` served from a remote host (starts http/https or //)
    — no hotlinks, ever again. This is the rule the whole job exists to install.
  * has a real (non-`generique-`) hero with an empty / missing `hero_credit`.
  * has a `hero_credit` whose author is a placeholder / non-name
    (`*_*`, `unknown`, `n/a`, or an empty author segment).
  * references a local `hero_image` that does not exist on disk.
  * shares a non-generic hero with ANOTHER fiche, unless the shared key is
    whitelisted in data/hero-shared-allow.json — the wrong-subject detector.

WARNS (never fails) when a fiche has no hero at all (the 5 artisan/food producers).

Read-only. stdlib only (no Pillow). Exit 1 on any violation.
"""
import json
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
JSON_DIR = os.path.join(ROOT, "Json")
ALLOW_FILE = os.path.join(ROOT, "data", "hero-shared-allow.json")

# author placeholders / non-names that fail the credit check
BAD_AUTHOR_RE = re.compile(r"^\s*(\*_\*|\*|unknown|n/?a|inconnu|anonyme|-+|\?+)\s*$", re.I)
CREDIT_SEP = "·"


def is_generic(hero):
    """True if `hero` is a canonical generique image (flat store or basename)."""
    if not hero:
        return False
    base = hero.rstrip("/").split("/")[-1]
    return "/generique/" in hero or base.startswith("generique-")


def commons_filename(url):
    """The Commons File title (spaces, decoded) for a hotlink URL — used to
    match whitelist keys expressed as filenames rather than full URLs."""
    import urllib.parse
    last = url.rstrip("/").split("/")[-1]
    return urllib.parse.unquote(last).replace("_", " ").strip()


def load_allow():
    if not os.path.exists(ALLOW_FILE):
        return set()
    try:
        data = json.load(open(ALLOW_FILE, encoding="utf-8"))
    except Exception as e:
        print(f"::warning::could not read {ALLOW_FILE}: {e}")
        return set()
    keys = set()
    for entry in data.get("allow", []):
        if isinstance(entry, str):
            keys.add(entry)
        elif isinstance(entry, dict) and entry.get("file"):
            keys.add(entry["file"])
    return keys


def main():
    files = sorted(f for f in os.listdir(JSON_DIR) if f.endswith(".json"))
    allow = load_allow()

    viol = []
    warns = []
    shared = defaultdict(list)   # normalised hero key -> [slugs] (non-generic only)
    n_real = n_generic = n_hotlink = 0

    for fn in files:
        d = json.load(open(os.path.join(JSON_DIR, fn), encoding="utf-8"))
        slug = d.get("slug") or fn[:-5]
        hero = d.get("hero_image")
        credit = (d.get("hero_credit") or "").strip()

        if not hero:
            warns.append(slug)
            continue

        # 1) no hotlinks
        if hero.startswith(("http://", "https://", "//")):
            n_hotlink += 1
            viol.append(f"{slug}: hotlinked hero_image ({hero[:60]}…) — self-host it (localize_heroes.py)")
            # a hotlink is also the shared-detector's concern
            key = commons_filename(hero)
            if not is_generic(hero):
                shared[key].append((slug, hero))
            continue

        if is_generic(hero):
            n_generic += 1
            continue
        n_real += 1

        # 2) local file must exist on disk
        rel = hero.lstrip("/")
        if not os.path.exists(os.path.join(ROOT, rel)):
            viol.append(f"{slug}: hero_image {hero} not on disk")

        # 3) real hero must carry a credit
        if not credit:
            viol.append(f"{slug}: real hero with empty/missing hero_credit ({hero})")
        else:
            # 4) author segment must be a real name
            author = credit.split(CREDIT_SEP)[0].strip()
            if not author or BAD_AUTHOR_RE.match(author) or "*_*" in credit:
                viol.append(f"{slug}: placeholder/non-name credit ({credit!r})")

        # 5) shared non-generic hero detector (by local basename)
        base = rel.split("/")[-1]
        shared[base].append((slug, hero))

    # resolve the shared detector: any key used by >1 fiche and not whitelisted
    for key, members in shared.items():
        if len(members) < 2:
            continue
        slugs = [s for s, _h in members]
        # whitelisted if the key OR any member's raw hero value is allowed
        if key in allow or any(h in allow for _s, h in members):
            continue
        viol.append(f"shared hero {key!r} used by {len(slugs)} fiches (wrong-subject risk): "
                    f"{', '.join(slugs)} — supply distinct photos or whitelist in "
                    f"data/hero-shared-allow.json")

    print(f"gate_hero_integrity: {len(files)} fiches — real={n_real} generic={n_generic} "
          f"hotlinked={n_hotlink} no-hero={len(warns)}")
    for w in warns:
        print(f"  · warn: {w} has no hero (out-of-scope artisan/producer)")

    if viol:
        print(f"::error::{len(viol)} hero-integrity violation(s):")
        for v in viol[:200]:
            print(f"    x {v}")
        sys.exit(1)
    print("OK no hotlinks; every real hero credited with a real author; no dangling "
          "paths; no un-whitelisted shared heroes")


if __name__ == "__main__":
    main()
