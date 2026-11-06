#!/usr/bin/env python3
"""inject_family_footer.py (73 engine): the "An officiallink.org project" footer line.

WHAT IT RENDERS
  The eVTOL sites' footer line, same wording and shape, localized from the
  first path segment (/en/, /de/, ...; anything else is French):

      Un projet d'officiallink.org. Pourquoi ce site existe →
      An officiallink.org project. Why it exists →

  Two links: officiallink.org and its /why/ page (the /fr/ versions on French
  pages, the only other language officiallink.org has). Wording for en, fr,
  de and ar is copied from qatarevtol.com; the other eight are DeepL.

  The line sits directly under the copyright: right after the bottom bar
  (<div class="foot-bottom">) when the footer has one; otherwise at the end
  of the footer's wrapper; otherwise just before </footer>.

WHY ONLY THE HOMEPAGES PASS PAGERANK
  The same owner runs every site involved. A followed link on every page is
  the sitewide "excessive link exchange" pattern that the 74's August 2026
  collapse was traced to. The locale homepages (/index.html and
  /<lang>/index.html for each published language) carry followed links.
  Every other page carries rel="nofollow" on both. Visitors see the same line
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
FOOT_BOTTOM_RE = re.compile(r'<div class="foot-bottom">.*?</div>', re.S)
LINK_STYLE = "color:inherit;text-decoration:underline;text-underline-offset:2px"
LINE_STYLE = "margin-top:.75rem;font-size:.75rem;opacity:.85"

def lang_of(rel):
    first = rel.split("/", 1)[0]
    return first if "/" in rel and first in SUBDIR_LANGS else "fr"


def is_homepage(rel):
    if rel == "index.html":
        return True
    parts = rel.split("/")
    return len(parts) == 2 and parts[1] == "index.html" and parts[0] in SUBDIR_LANGS


def render(fam, lang, followed):
    """The eVTOL sites' footer line, word for word in en/fr/de/ar:
    An <a>officiallink.org</a> project. <a>Why it exists →</a>"""
    before, after, why = fam["copy"].get(lang) or fam["copy"]["fr"]
    base = fam["url"] + fam.get("locale_paths", {}).get(lang, "")
    rel = "" if followed else ' rel="nofollow"'
    esc = lambda t: html_lib.escape(t, quote=False)
    attr = html_lib.escape
    a = lambda href, text: (f'<a style="{LINK_STYLE}" href="{attr(href)}"{rel}>'
                            f'{esc(text)}</a>')
    return (f'{MARK_A}<div class="family" style="{LINE_STYLE}">{esc(before)}'
            f'{a(base, fam["label"])}{esc(after)} {a(base + fam["why_path"], why)}'
            f'</div>{MARK_B}')


def insertion_point(text):
    """Directly under the copyright, wherever this footer keeps it:
    after the bottom bar when there is one; otherwise at the end of the
    footer's wrapper (</div></footer>); otherwise just before </footer>."""
    end = text.index("</footer>")
    bars = list(FOOT_BOTTOM_RE.finditer(text, 0, end))
    if len(bars) == 1:
        return bars[0].end()
    if len(bars) > 1:
        return None
    m = list(re.finditer(r"</div>\s*</footer>", text))
    return m[0].start() if len(m) == 1 else end


def process(text, fam, lang, followed):
    stripped = FENCE_RE.sub("", text)
    if not fam:
        return stripped
    if stripped.count("</footer>") != 1:
        return None
    i = insertion_point(stripped)
    if i is None:
        return None
    return stripped[:i] + render(fam, lang, followed) + stripped[i:]


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
