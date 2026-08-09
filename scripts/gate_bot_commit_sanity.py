#!/usr/bin/env python3
"""gate_bot_commit_sanity.py — CI tripwire: no commit may mass-delete verified data.

HANDOFF-24 Job 3. On 2026-07-01 a dead Google key made the scheduled check
overwrite 397 fiches, deleting place_id, hours, verified website/phone,
ratings and GPS — and it sailed through CI because gate_no_key_drop only
watches TOP-LEVEL keys, while the damage was nested inside the
google_check / freshness blocks. This gate watches exactly those fields.

Rule: comparing against --base, if more than --max-fiches fiches (default 20)
each lost at least one VERIFIED field, the diff is not a data update — it's a
broken checker (or a broken script) rewriting the world. Fail the build.

A verified field is "lost" when it was present and non-null at base and is
missing or null now. Watched fields:
    google_check.place_id     google_check.hours     google_check.match
    freshness.place_id        freshness.hours        freshness.google_match
    freshness.website         freshness.phone        (verified stamps)

Legitimate per-venue changes (a real closure, a CONFIRMED_ABSENT) touch a
handful of fiches and pass untouched. Only mass deletion trips the wire.

CLI:
    python3 scripts/gate_bot_commit_sanity.py --base REF [--head REF]
        [--max-fiches N] [--root DIR]
    --head compares two refs instead of ref-vs-working-tree (forensics mode:
      --base ad73fc07^ --head ad73fc07 reproduces the July 1 catch).
"""
import argparse
import glob
import json
import os
import subprocess
import sys

DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

VERIFIED_FIELDS = [
    ("google_check", "place_id"),
    ("google_check", "hours"),
    ("google_check", "match"),
    ("freshness", "place_id"),
    ("freshness", "hours"),
    ("freshness", "google_match"),
    ("freshness", "website"),
    ("freshness", "phone"),
]


def show_at(root, ref, slug):
    """Parsed Json/<slug>.json at ref, or None if absent/unparseable there."""
    r = subprocess.run(
        ["git", "show", f"{ref}:Json/{slug}.json"],
        cwd=root, capture_output=True, text=True,
    )
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def list_slugs(root, ref):
    if ref is None:
        return sorted(os.path.splitext(os.path.basename(p))[0]
                      for p in glob.glob(os.path.join(root, "Json", "*.json")))
    r = subprocess.run(["git", "ls-tree", "-r", "--name-only", ref, "Json/"],
                       cwd=root, capture_output=True, text=True)
    return sorted(os.path.splitext(os.path.basename(p))[0]
                  for p in r.stdout.split() if p.endswith(".json"))


def load_head(root, ref, slug):
    if ref is not None:
        return show_at(root, ref, slug)
    fp = os.path.join(root, "Json", f"{slug}.json")
    if not os.path.exists(fp):
        return None
    try:
        return json.loads(open(fp, encoding="utf-8").read())
    except json.JSONDecodeError:
        return None


def lost_fields(old, new):
    """Verified fields present+non-null at base and missing/null now."""
    lost = []
    for block, field in VERIFIED_FIELDS:
        ov = (old.get(block) or {}).get(field)
        nv = (new.get(block) or {}).get(field)
        if ov not in (None, "", []) and nv in (None, "", []):
            lost.append(f"{block}.{field}")
    return lost


def ref_exists(root, ref):
    return subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        cwd=root, capture_output=True, text=True,
    ).returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="HEAD~1",
                    help="Ref to compare against (default HEAD~1)")
    ap.add_argument("--head", default=None,
                    help="Ref to compare TO (default: working tree)")
    ap.add_argument("--max-fiches", type=int, default=20,
                    help="Fail when MORE than this many fiches lost verified fields")
    ap.add_argument("--root", default=DEFAULT_ROOT,
                    help="Repo root (tests only)")
    args = ap.parse_args()

    if not ref_exists(args.root, args.base):
        print(f"gate_bot_commit_sanity: base ref '{args.base}' not available "
              "(shallow checkout or first commit) — skipping.")
        return

    hit = []      # (slug, [lost fields])
    checked = 0
    for slug in list_slugs(args.root, args.head):
        old = show_at(args.root, args.base, slug)
        if old is None:
            continue   # new fiche — nothing to lose
        new = load_head(args.root, args.head, slug)
        if new is None:
            continue   # deleted fiche — gate_no_key_drop / review owns that
        checked += 1
        lost = lost_fields(old, new)
        if lost:
            hit.append((slug, lost))

    head_desc = args.head or "working tree"
    print(f"gate_bot_commit_sanity: {checked} fiches compared "
          f"({args.base} → {head_desc}); verified-field loss in {len(hit)}"
          f" (limit {args.max_fiches})")
    if len(hit) <= args.max_fiches:
        if hit:
            print("  under the limit — per-venue changes are allowed:")
            for slug, lost in hit:
                print(f"    ~ {slug}: {', '.join(lost)}")
        print("✓ no mass deletion of verified fields")
        return

    print(f"::error::{len(hit)} fiches lost verified fields in ONE diff "
          f"(limit {args.max_fiches}). A checker is rewriting the world "
          "from an error state — this is the 2026-07-01 failure shape.")
    for slug, lost in hit[:30]:
        print(f"    ✗ {slug}: {', '.join(lost)}")
    if len(hit) > 30:
        print(f"    … and {len(hit) - 30} more")
    print("\nA legitimate mass migration must be split, or land with this gate "
          "consciously updated in the same PR — never silently.")
    sys.exit(1)


if __name__ == "__main__":
    main()
