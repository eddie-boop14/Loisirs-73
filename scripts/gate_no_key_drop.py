#!/usr/bin/env python3
"""gate_no_key_drop.py — CI backstop: fail if any fiche silently lost a key.

The structural guarantee behind Studio's non-destructive writes (SPEC §4.4):
no matter the source (Studio, manual edit, an agent), a push must never drop a
top-level key, an i18n locale, or a per-locale key from a Json/<slug>.json
relative to the previous commit (HEAD~1). Intentional removals go through an
allowlist or the --allow-drop escape hatch — they can't happen silently.

For each Json/*.json:
  - load the current version and `git show HEAD~1:Json/<slug>.json`
  - new file (absent at HEAD~1) → skip
  - compare leaf-key sets: top-level keys, the i18n locale set, and each
    i18n.<lang> key set
  - any key present at HEAD~1 and absent now is a DROP

Drops fail the build (exit 1) unless every dropped id is in
reports/key-drop-allowlist.txt, or --allow-drop is passed (warn-only).

Drop id format (one per line in the allowlist; '#' comments allowed):
    <slug>:<key>                 top-level key
    <slug>:i18n.<lang>           an entire locale
    <slug>:i18n.<lang>.<key>     a key inside a locale

CLI:
    python3 scripts/gate_no_key_drop.py [--allow-drop] [--base REF]
"""
import argparse
import glob
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_DIR = os.path.join(ROOT, "Json")
ALLOWLIST = os.path.join(ROOT, "reports", "key-drop-allowlist.txt")


def load_allowlist():
    ids = set()
    if os.path.exists(ALLOWLIST):
        for line in open(ALLOWLIST, encoding="utf-8"):
            line = line.split("#", 1)[0].strip()
            if line:
                ids.add(line)
    return ids


def show_at(ref, slug):
    """Parsed Json/<slug>.json at ref, or None if absent/unparseable there."""
    r = subprocess.run(
        ["git", "show", f"{ref}:Json/{slug}.json"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def leaf_keys(d):
    """Yield comparable key ids for one fiche dict."""
    top = set(k for k in d.keys() if k != "i18n")
    out = {f":{k}" for k in top}
    i18n = d.get("i18n")
    if isinstance(i18n, dict):
        for lang in i18n:
            out.add(f":i18n.{lang}")
            blk = i18n[lang]
            if isinstance(blk, dict):
                for k in blk:
                    out.add(f":i18n.{lang}.{k}")
    return out


def ref_exists(ref):
    return subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        cwd=ROOT, capture_output=True, text=True,
    ).returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-drop", action="store_true",
                    help="Report drops but exit 0 (rollout / warn-only mode)")
    ap.add_argument("--base", default="HEAD~1", help="Ref to compare against (default HEAD~1)")
    args = ap.parse_args()

    if not ref_exists(args.base):
        print(f"gate_no_key_drop: base ref '{args.base}' not available "
              "(shallow checkout or first commit) — skipping.")
        return

    allow = load_allowlist()
    drops = []   # (slug, dropped_id, allowed?)
    checked = 0
    for fp in sorted(glob.glob(os.path.join(JSON_DIR, "*.json"))):
        slug = os.path.splitext(os.path.basename(fp))[0]
        old = show_at(args.base, slug)
        if old is None:
            continue  # new file (or unreadable at base) — nothing to lose
        try:
            new = json.loads(open(fp, encoding="utf-8").read())
        except json.JSONDecodeError:
            continue
        checked += 1
        lost = leaf_keys(old) - leaf_keys(new)
        for key_id in sorted(lost):
            drop_id = f"{slug}{key_id}"
            drops.append((drop_id, drop_id in allow))

    unallowed = [d for d, ok in drops if not ok]
    allowed = [d for d, ok in drops if ok]

    print(f"gate_no_key_drop: compared {checked} fiches against {args.base}")
    if allowed:
        print(f"  {len(allowed)} allowlisted drop(s) (ok):")
        for d in allowed:
            print(f"    ~ {d}")
    if not unallowed:
        print("✓ no silent key/locale drops")
        return

    print(f"::error::{len(unallowed)} key/locale drop(s) with no allowlist entry:")
    for d in unallowed:
        print(f"    ✗ {d}")
    print("\nIf intentional: add the id(s) to reports/key-drop-allowlist.txt, "
          "or re-run with --allow-drop. Otherwise a write clobbered data — "
          "fix the source (use apply_studio_patch.py, never a full-file cp).")
    if args.allow_drop:
        print("(--allow-drop set → exiting 0)")
        return
    sys.exit(1)


if __name__ == "__main__":
    main()
