#!/usr/bin/env python3
"""rename_hub_slugs.py — apply the 6 hub-slug renames identified by the
2026-06-13 locale-slug audit.

Renames (only non-FR; the FR canonical slug stays):

  1. /it/aree-recreative/    → /it/aree-ricreative/    (typo: FR spelling
                                                        in an IT slug)
  2. /en/que-faire/          → /en/what-to-do/         (coherence)
  3. /de/que-faire/          → /de/was-unternehmen/    (coherence)
  4. /it/que-faire/          → /it/cosa-fare/          (coherence)
  5. /es/que-faire/          → /es/que-hacer/          (coherence)
  6. /nl/que-faire/          → /nl/wat-te-doen/        (coherence)

The FR /que-faire/ stays at the FR canonical slug.

For each rename the script:
  - Moves the directory on disk.
  - Replaces every URL reference (locale-prefixed only) across the
    repo: *.html, *.xml, *.json, *.py (incl. scripts/build_hubs.py,
    scripts/build_lieu_page.py, scripts/fix_hub_chrome.py, scripts/
    audit_breadcrumbs.py).
  - Appends 301 redirects to _redirects so the old URL gracefully
    forwards to the new one. Idempotent — won't double-write.

Run once. Then `python3 scripts/build_all.py --no-site` should remain
green on every gate.
"""
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (locale, old slug, new slug, reason)
RENAMES = [
    ("it", "aree-recreative",  "aree-ricreative",  "FR-style spelling → IT 'ricreative'"),
    ("en", "que-faire",        "what-to-do",       "EN-native"),
    ("de", "que-faire",        "was-unternehmen",  "DE-native"),
    ("it", "que-faire",        "cosa-fare",        "IT-native"),
    ("es", "que-faire",        "que-hacer",        "ES-native"),
    ("nl", "que-faire",        "wat-te-doen",      "NL-native"),
]


def rename_directory(lang, old, new):
    src = ROOT / lang / old
    dst = ROOT / lang / new
    if not src.exists():
        print(f"  ! {src} does not exist; skip")
        return False
    if dst.exists():
        print(f"  ! {dst} already exists; skip rename")
        return False
    src.rename(dst)
    print(f"  ✓ mv {lang}/{old} → {lang}/{new}")
    return True


def update_file_references(lang, old, new):
    """Replace /<lang>/<old> with /<lang>/<new> across the repo.
    Only updates locale-prefixed URL forms so we don't touch FR canonical
    or external 3rd-party URLs that contain the same slug text."""
    # Patterns to match (each captures /<lang>/<old>{boundary})
    # We replace with /<lang>/<new>{same boundary}
    boundaries = ['"', "/", "#", "?", " ", "<", "'"]
    # Compile a single pattern that matches locale-prefixed URL
    pat = re.compile(
        r"(/" + re.escape(lang) + r"/)" + re.escape(old) + r"(?=[" + "".join(map(re.escape, boundaries)) + r"])"
    )
    n_files = 0
    n_subs = 0
    extensions = (".html", ".xml", ".json", ".py", ".md", ".txt", ".js")
    skip_dirs = {"_site", "node_modules", "__pycache__", ".git"}
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        if any(part in skip_dirs for part in p.parts):
            continue
        if p.suffix not in extensions:
            continue
        # Don't rewrite this script itself
        if p.name == "rename_hub_slugs.py":
            continue
        try:
            txt = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new_txt, k = pat.subn(lang_replacer(lang, new), txt)
        if k:
            p.write_text(new_txt, encoding="utf-8")
            n_files += 1
            n_subs += k
    return n_files, n_subs


def lang_replacer(lang, new):
    def _r(m):
        return f"/{lang}/{new}"
    return _r


def append_redirects(rename_list):
    """Append 301 rules to _redirects for each rename. Idempotent."""
    redirects = ROOT / "_redirects"
    text = redirects.read_text(encoding="utf-8")
    new_lines = []
    new_lines.append("")
    new_lines.append("# Hub slug fixes (2026-06-13 audit): IT typo + que-faire locale naturalization")
    added = 0
    for lang, old, new, _ in rename_list:
        for suffix, mapping in (
            ("",  ""),
            ("/", "/"),
            ("/*", "/:splat"),
        ):
            from_path = f"/{lang}/{old}{suffix}"
            to_path   = f"/{lang}/{new}{mapping}"
            line = f"{from_path:30}  {to_path:30}  301"
            if line.strip() in text:
                continue
            new_lines.append(line)
            added += 1
    if added:
        text = text.rstrip() + "\n" + "\n".join(new_lines) + "\n"
        redirects.write_text(text, encoding="utf-8")
    return added


def main():
    print("== rename directories ==")
    for lang, old, new, reason in RENAMES:
        rename_directory(lang, old, new)
    print("\n== update file references ==")
    for lang, old, new, reason in RENAMES:
        nf, ns = update_file_references(lang, old, new)
        print(f"  /{lang}/{old} → /{lang}/{new}:  {ns} subs in {nf} files  ({reason})")
    print("\n== append 301 redirects ==")
    n = append_redirects(RENAMES)
    print(f"  appended {n} redirect lines to _redirects")


if __name__ == "__main__":
    main()
