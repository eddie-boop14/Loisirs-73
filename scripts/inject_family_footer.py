#!/usr/bin/env python3
"""inject_family_footer.py (73 engine): the "Part of the Officiallink family" line.

WHAT IT RENDERS
  One short line in every page footer, localized from the first path segment
  (/en/, /de/, ...; anything else is French):

      Fait partie de la famille Officiallink

  Where it goes:
    - fiche, hub and commune pages: just above the bottom bar
      (<div class="foot-bottom">);
    - the locale homepages and the legal pages have no bottom bar: inside
      the footer's wrapper, after its last paragraph (before </div></footer>);
    - legal and form pages have a bare footer with no wrapper: just
      before </footer>.

WHY ONLY THE HOMEPAGES PASS PAGERANK
  The same owner runs every site involved. A followed link on every page is
  the sitewide "excessive link exchange" pattern that the 74's August 2026
  collapse was traced to. The locale homepages (/index.html and
  /<lang>/index.html for each published language) carry a followed link.
  Every other page carries rel="nofollow". Visitors see the same line
  everywhere.

CONFIG-DRIVEN, BOTH WAYS
  If siteconfig.FAMILY is present, the line is inserted or repaired. The block
  is fenced and the pass is idempotent. If FAMILY is absent, every line is
  removed.

Usage:
    python3 scripts/inject_family_footer.py            # report, writes nothing
    python3 scripts/inject_family_footer.py --apply

2026 · Bleu canard édition · Edmaster & Claudius 🦆
"""
import argparse
import html as html_lib
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import locales  # noqa: E402
import siteconfig  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MARK_A, MARK_B = "<!--family:start-->", "<!--family:end-->"
FENCE_RE = re.compile(re.escape(MARK_A) + r".*?" + re.escape(MARK_B), re.S)
SKIP_TOP = {"reports", "scripts", "_site", "scratchpad", "tests", "node_modules",
            "docs", ".git"}
SUBDIR_LANGS = set(locales.ALL_SUBDIR_LANGS)
# (anchor, style). The first anchor found exactly once wins.
ANCHORS = (
    ('<div class="foot-bottom">', "margin:0 0 1rem"),
    ("</div></footer>", "margin:.8rem 0 0"),
    ("</footer>", "margin:.8rem 0 0"),     # legal and form pages: bare footer
)


def lang_of(rel):
    first = rel.split("/", 1)[0]
    return first if "/" in rel and first in SUBDIR_LANGS else "fr"


def is_homepage(rel):
    if rel == "index.html":
        return True
    parts = rel.split("/")
    return len(parts) == 2 and parts[1] == "index.html" and parts[0] in SUBDIR_LANGS


def render(fam, lang, followed, style):
    phrase = fam["phrase"].get(lang) or fam["phrase"]["fr"]
    rel = "" if followed else ' rel="nofollow"'
    return (f'{MARK_A}<p class="family" style="{style};font-size:.8rem;opacity:.85">'
            f'{html_lib.escape(phrase)} <a href="{html_lib.escape(fam["url"])}"{rel}>'
            f'{html_lib.escape(fam["name"])}</a></p>{MARK_B}')


def process(text, fam, lang, followed):
    stripped = FENCE_RE.sub("", text)
    if not fam:
        return stripped
    if stripped.count("</footer>") != 1:
        return None
    for anchor, style in ANCHORS:
        if stripped.count(anchor) == 1:
            i = stripped.index(anchor)
            return stripped[:i] + render(fam, lang, followed, style) + stripped[i:]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    fam = siteconfig.FAMILY
    changed = followed = skipped = total = 0
    expected = 1 + sum((ROOT / l / "index.html").is_file() for l in SUBDIR_LANGS)
    for dirpath, dirnames, filenames in os.walk(ROOT):
        if os.path.relpath(dirpath, ROOT) == ".":
            dirnames[:] = [d for d in dirnames if d not in SKIP_TOP]
        for fn in filenames:
            if not fn.endswith(".html"):
                continue
            path = Path(dirpath) / fn
            rel = path.relative_to(ROOT).as_posix()
            text = path.read_text(encoding="utf-8")
            if '<footer class="site"' not in text and MARK_A not in text:
                continue
            total += 1
            home = is_homepage(rel)
            followed += bool(fam) and home
            new = process(text, fam, lang_of(rel), home)
            if new is None:
                skipped += 1
                print(f"  SKIP (footer anchor not unique): {rel}", file=sys.stderr)
                continue
            if new != text:
                changed += 1
                if args.apply:
                    path.write_text(new, encoding="utf-8")
    mode = "applied" if args.apply else "dry run"
    state = "armed" if fam else "disarmed (no family block)"
    print(f"family footer {state}: {total} footers, {changed} changed, "
          f"{followed} followed (homepages), {skipped} skipped [{mode}]")
    if fam and followed != expected:
        print(f"FAIL: expected {expected} followed homepages, got {followed}",
              file=sys.stderr)
        return 1
    return 1 if skipped else 0


if __name__ == "__main__":
    sys.exit(main())
