#!/usr/bin/env python3
"""ingest_translations.py — JOB 7. Apply a translation payload into Json/.

Payload shape (one file per locale, at translations/<lang>.json):

  {
    "<slug>": {
      "name": "...",
      "name_alternates": ["..."],
      "meta_title": "...",
      "meta_description": "...",
      "hero_alt": "...",
      "body.what_is": "<p>...</p>",
      "body.activities[<i>].title": "...",
      "body.activities[<i>].description": "...",
      "body.practical_info[<i>].k": "...",
      "body.practical_info[<i>].v": "...",
      "body.how_to_get_there.car": "...",
      "body.how_to_get_there.public_transport": "...",
      "body.how_to_get_there.bike": "...",
      "body.when_to_visit": "...",
      "faq[<i>].q": "...",
      "faq[<i>].a": "..."
    },
    ...
  }

For each slug × locale:
  - merges the payload into the existing i18n.<lang> block (creates the
    block if missing).
  - preserves any existing translated content not in the payload.
  - writes a research_log entry recording the ingest.

Idempotent: re-running with the same payload produces no JSON changes.

CLI:
    python3 scripts/ingest_translations.py             # ingest all 5 locales
    python3 scripts/ingest_translations.py --only en   # only one locale
    python3 scripts/ingest_translations.py --dry-run   # show what would change
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import locales  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
JSON_DIR = ROOT / "Json"
TRANS_DIR = ROOT / "translations"
LANGS = locales.PROSE_SECONDARY
TODAY = datetime.date.today().isoformat()


def set_path(obj, dotted, value):
    """Set obj at dotted path (supports body.activities[2].title style).
    Creates dicts and pads lists as needed."""
    tokens = re.findall(r"[^.\[\]]+|\[\d+\]", dotted)
    cur = obj
    for i, tok in enumerate(tokens[:-1]):
        nxt = tokens[i + 1]
        if tok.startswith("["):
            idx = int(tok[1:-1])
            while len(cur) <= idx:
                cur.append({})
            cur = cur[idx]
        else:
            if tok not in cur or not isinstance(cur[tok], (dict, list)):
                cur[tok] = [] if nxt.startswith("[") else {}
            cur = cur[tok]
    last = tokens[-1]
    if last.startswith("["):
        idx = int(last[1:-1])
        while len(cur) <= idx:
            cur.append(None)
        cur[idx] = value
    else:
        cur[last] = value


def _get_at(blk, path):
    """Return (exists, value) for a dotted path; (False, None) if any hop missing."""
    cur = blk
    for tok in re.findall(r"[^.\[\]]+|\[\d+\]", path):
        if tok.startswith("["):
            i = int(tok[1:-1])
            if not isinstance(cur, list) or i >= len(cur):
                return (False, None)
            cur = cur[i]
        else:
            if not isinstance(cur, dict) or tok not in cur:
                return (False, None)
            cur = cur[tok]
    return (True, cur)


def merge_payload(blk, payload, *, force=False):
    """Mutate blk in place with payload's dotted-path values.

    Conflict-guard (builder-audit defect 3): NEVER silently overwrite a target
    that already holds a different non-empty value — that's how a stale payload
    reverts an intentional Json edit. Such a case is recorded as a CONFLICT and
    skipped (unless force=True). Missing/empty targets are filled; equal targets
    are no-ops.

    Returns (changed: bool, conflicts: list[(path, old, new)]).
    """
    changed = False
    conflicts = []
    for path, value in payload.items():
        exists, cur = _get_at(blk, path)
        if exists and cur == value:
            continue                              # no-op
        if exists and cur not in (None, "", [], {}):
            # target holds a different, non-empty value → conflict
            conflicts.append((path, cur, value))
            if not force:
                continue
        set_path(blk, path, value)
        changed = True
    return changed, conflicts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=LANGS, help="Ingest only one locale")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true",
                    help="Write nothing; exit 1 if any payload value CONFLICTS with "
                         "a different non-empty Json value (revert-risk). CI-runnable.")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite conflicting values (the old unconditional behaviour). "
                         "Use only when the payload is authoritative.")
    args = ap.parse_args()
    langs = [args.only] if args.only else list(LANGS)
    write = not (args.dry_run or args.check)

    total_changed = 0
    all_conflicts = []   # (lang, slug, path, old, new)
    for lang in langs:
        f = TRANS_DIR / f"{lang}.json"
        if not f.exists():
            print(f"  [{lang}] no payload at translations/{lang}.json — skip")
            continue
        payload = json.loads(f.read_text(encoding="utf-8"))
        n_changed = 0
        for slug, fields in payload.items():
            jp = JSON_DIR / f"{slug}.json"
            if not jp.exists():
                print(f"  [{lang}] {slug}: JSON not found — skip")
                continue
            d = json.loads(jp.read_text(encoding="utf-8"))
            i18n = d.setdefault("i18n", {})
            blk = i18n.setdefault(lang, {})
            if not isinstance(blk, dict):
                blk = {}; i18n[lang] = blk
            changed, conflicts = merge_payload(blk, fields, force=args.force)
            for path, old, new in conflicts:
                all_conflicts.append((lang, slug, path, old, new))
            if changed and write:
                rl = d.setdefault("research_log", [])
                already_logged = any(
                    isinstance(r, dict)
                    and r.get("note", "").startswith(f"Translation ingest [{lang}]")
                    and r.get("date") == TODAY
                    for r in rl
                )
                if not already_logged:
                    rl.append({
                        "date": TODAY,
                        "by": "scripts/ingest_translations.py",
                        "note": f"Translation ingest [{lang}]: {len(fields)} field(s) updated.",
                    })
                jp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if changed:
                n_changed += 1
        print(f"  [{lang}] {n_changed} fiches {'would change' if not write else 'updated'}")
        total_changed += n_changed

    if all_conflicts and not args.force:
        print(f"\n::warning::{len(all_conflicts)} CONFLICT(s) — payload differs from a "
              f"non-empty Json value; SKIPPED (not reverted). Reconcile the payload or "
              f"re-run with --force if the payload is authoritative:")
        for lang, slug, path, old, new in all_conflicts[:40]:
            print(f"    [{lang}] {slug}:{path}\n        json    = {old!r}\n        payload = {new!r}")
        if len(all_conflicts) > 40:
            print(f"    … and {len(all_conflicts) - 40} more")

    print(f"\ntotal fiches {'would change' if not write else 'updated'}: {total_changed}")
    if args.dry_run:
        print("(dry-run — no JSON was written)")
    if args.check:
        if all_conflicts:
            print(f"\n::error::--check: {len(all_conflicts)} conflict(s) — a stale payload "
                  f"would revert intentional Json edits. Reconcile translations/<lang>.json.")
            sys.exit(1)
        print("\n✓ --check: no payload/Json conflicts (ingest is idempotent and revert-safe)")
        sys.exit(0)


if __name__ == "__main__":
    main()
