#!/usr/bin/env python3
"""sync_home_cards.py — make homepage card images derive from Json/, not memory.

WHY
  index.html (and its 11 locale siblings) is hand-authored chrome: no builder
  regenerates its card grid. Only head-links and the intent "Nos sélections"
  strip are patched in. So a card's <picture> keeps whatever image was chosen
  the day it was written, even after the fiche it links to gains a real,
  credited, self-hosted hero.

  The result rots silently and in one direction: every photo added to Json/
  makes the homepage staler. On 2026-07-26 eighteen cards were showing a
  generic placeholder while the fiche behind them had a real photo — including
  fiches photographed that same morning.

  This is the same failure mode as the category-hub banner: a surface that is
  authored instead of derived. The fix is to derive it.

WHAT IT DOES
  For every `<a class="card-photo" href=".../<slug>">` on a homepage, rewrite
  the following <picture> to the fiche's own hero.

WHAT IT WILL NOT DO
  * Never downgrades. A card is only rewritten when it currently shows a
    /img/generique/ placeholder AND the fiche has a real local hero.
    A curated real photo is left alone.
  * Never introduces a hotlink. Fiches whose hero is still a remote URL are
    skipped — self-host it first (localize_heroes.py --only <slug>).
  * Never points at a missing file. Both the .jpg and its .webp sibling must
    exist on disk or the card is left untouched.

Idempotent: a second run changes nothing.

Usage:
    python3 scripts/sync_home_cards.py            # report only, writes nothing
    python3 scripts/sync_home_cards.py --apply
"""
import argparse
import siteconfig  # HANDOFF-73 phase 4: per-site domain
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSON_DIR = ROOT / "Json"

CARD_RE = re.compile(
    r'(<a class="card-photo" href="' + siteconfig.SITE_URL_RE + r'/(?:[a-z]{2}/)?([a-z0-9-]+)">\s*'
    r'<picture><source srcset=")([^"]+)("[^>]*>\s*<img src=")([^"]+)(")',
    re.S,
)


def load_heroes():
    out = {}
    for fp in sorted(JSON_DIR.glob("*.json")):
        d = json.loads(fp.read_text(encoding="utf-8"))
        out[d["slug"]] = (d.get("hero_image") or "").strip()
    return out


def homepages():
    yield ROOT / "index.html"
    for sub in sorted(ROOT.iterdir()):
        if sub.is_dir() and len(sub.name) == 2 and (sub / "index.html").exists():
            yield sub / "index.html"


def main():
    ap = argparse.ArgumentParser(description="Sync homepage card images from Json/ heroes.")
    ap.add_argument("--apply", action="store_true", help="write changes (default: report only)")
    args = ap.parse_args()

    heroes = load_heroes()
    total_changed = 0
    skipped_hotlink = set()

    for page in homepages():
        html = page.read_text(encoding="utf-8")
        changed = 0

        def repl(m):
            nonlocal changed
            head, slug, srcset, mid, src, tail = m.groups()
            hero = heroes.get(slug, "")
            # only upgrade a generic placeholder
            if "/generique/" not in src:
                return m.group(0)
            if not hero:
                return m.group(0)
            if hero.startswith(("http://", "https://", "//")):
                skipped_hotlink.add(slug)
                return m.group(0)
            if not hero.startswith("/img/") or "/generique/" in hero:
                return m.group(0)
            webp = re.sub(r"\.jpg$", ".webp", hero)
            if not (ROOT / hero.lstrip("/")).exists() or not (ROOT / webp.lstrip("/")).exists():
                return m.group(0)
            changed += 1
            return f"{head}{webp}{mid}{hero}{tail}"

        new = CARD_RE.sub(repl, html)
        if changed and args.apply:
            page.write_text(new, encoding="utf-8")
        if changed:
            print(f"  {page.relative_to(ROOT)}: {changed} card(s)")
        total_changed += changed

    verb = "synced" if args.apply else "would sync"
    print(f"sync_home_cards: {verb} {total_changed} card image(s)")
    if skipped_hotlink:
        print(f"  skipped (hero still hotlinked — self-host first): "
              f"{', '.join(sorted(skipped_hotlink))}")
    if not args.apply and total_changed:
        print("  report only — re-run with --apply to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
