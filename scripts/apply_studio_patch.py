#!/usr/bin/env python3
"""apply_studio_patch.py — the SINGLE ingress for Studio output into Json/.

Studio (editor / enricher / phototheque) emits a dotted-path PATCH that lists
ONLY the keys it changed. This script deep-merges that patch into the
*freshly-pulled live* Json/<slug>.json, touching nothing else. It is the only
sanctioned way Studio data enters the repo — never `cp` a full fiche over a
live one (that silently reverts fields written upstream since Studio loaded).

Spec: SPEC-studio-data-safety.md (§4.3). Reuses ingest_translations.set_path so
the write granularity is identical to the translation-ingest door.

Patch format (SPEC §4.1):
    {
      "slug": "musee-chateau-annecy",
      "source": "studio-editor",          # editor | enricher | phototheque
      "base_head": "aebd297",             # HEAD authored against (or null)
      "patch": { "i18n.fr.intro": "…", "hero_image": "/x-hero.jpg" },
      "delete": []                        # explicit paths to remove (rare)
    }

Semantics:
  - Values replace wholesale at their path. Arrays replace whole (no element
    merge). Objects are expressed via dotted paths, not nested objects.
  - slug must match an existing Json/<slug>.json (no create-via-patch in v1).
  - Guard: a "patch" carrying a full i18n tree for >=2 locales, or >40 paths,
    is a disguised full-file dump → rejected.

Conflict tripwire (SPEC §4.2):
  - If base_head is a real git ref and differs from current HEAD, each path is
    compared live-vs-base_head. If live changed that exact path since base_head
    AND the incoming value differs from live, that's a CONFLICT → abort unless
    --allow-conflict.

CLI:
    python3 scripts/apply_studio_patch.py PATCH.json [--dry-run] [--allow-conflict]

Exit codes: 0 ok · 2 malformed patch · 3 slug/target missing · 4 conflict.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingest_translations import set_path  # noqa: E402  (reuse the same writer)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# LOISIRS_JSON_DIR lets the test suite point at a tmpdir; prod uses ROOT/Json.
JSON_DIR = os.environ.get("LOISIRS_JSON_DIR") or os.path.join(ROOT, "Json")
TODAY = datetime.date.today().isoformat()

MAX_PATHS = 40
_TOK = re.compile(r"[^.\[\]]+|\[\d+\]")


def get_path(obj, dotted, _MISSING=object()):
    """Read obj at a dotted path (supports a.b[2].c). Returns _MISSING if absent."""
    cur = obj
    for tok in _TOK.findall(dotted):
        try:
            if tok.startswith("["):
                cur = cur[int(tok[1:-1])]
            else:
                cur = cur[tok]
        except (KeyError, IndexError, TypeError):
            return _MISSING
    return cur


def pop_path(obj, dotted):
    """Remove the leaf at a dotted path. Returns True if something was removed."""
    tokens = _TOK.findall(dotted)
    cur = obj
    for tok in tokens[:-1]:
        try:
            cur = cur[int(tok[1:-1])] if tok.startswith("[") else cur[tok]
        except (KeyError, IndexError, TypeError):
            return False
    last = tokens[-1]
    try:
        if last.startswith("["):
            del cur[int(last[1:-1])]
        else:
            del cur[last]
        return True
    except (KeyError, IndexError, TypeError):
        return False


def validate_patch(doc, path_label):
    """Return (slug, patch_dict, delete_list) or raise ValueError (→ exit 2)."""
    if not isinstance(doc, dict):
        raise ValueError(f"{path_label}: top-level must be an object")
    slug = doc.get("slug")
    if not slug or not isinstance(slug, str):
        raise ValueError(f"{path_label}: missing/invalid 'slug'")
    patch = doc.get("patch", {})
    if not isinstance(patch, dict):
        raise ValueError(f"{path_label}: 'patch' must be an object of dotted-path → value")
    delete = doc.get("delete", []) or []
    if not isinstance(delete, list):
        raise ValueError(f"{path_label}: 'delete' must be a list of dotted paths")

    # Guard §4.1 — reject disguised full-file dumps.
    if len(patch) > MAX_PATHS:
        raise ValueError(
            f"{path_label}: {len(patch)} paths > {MAX_PATHS} — looks like a full-file dump, "
            "not a patch. Re-export from Studio (it should emit changed keys only)."
        )
    whole_locale = [p for p in patch if re.fullmatch(r"i18n\.[a-z]{2}", p)]
    if len(whole_locale) >= 2:
        raise ValueError(
            f"{path_label}: sets entire locale objects for {whole_locale} — a patch must "
            "descend into the changed leaves, not replace whole i18n trees."
        )
    return slug, patch, delete


def base_value(slug, dotted, base_head, _MISSING):
    """Value at `dotted` in Json/<slug>.json as of base_head, or _MISSING."""
    try:
        blob = subprocess.run(
            ["git", "show", f"{base_head}:Json/{slug}.json"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout
        return get_path(json.loads(blob), dotted, _MISSING)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return _MISSING


def current_head():
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        return None


def ref_exists(ref):
    if not ref:
        return False
    return subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        cwd=ROOT, capture_output=True, text=True,
    ).returncode == 0


def main():
    ap = argparse.ArgumentParser(description="Apply a Studio dotted-path patch into Json/.")
    ap.add_argument("patch", help="Path to the Studio *-patch.json file")
    ap.add_argument("--dry-run", action="store_true", help="Print changes; write nothing")
    ap.add_argument("--allow-conflict", action="store_true",
                    help="Overwrite paths that moved upstream since base_head")
    args = ap.parse_args()
    MISSING = object()

    # 1. Load + validate patch.
    try:
        doc = json.loads(open(args.patch, encoding="utf-8").read())
        slug, patch, delete = validate_patch(doc, os.path.basename(args.patch))
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: cannot read/parse patch: {e}", file=sys.stderr)
        sys.exit(2)
    except ValueError as e:
        print(f"ERROR (malformed patch): {e}", file=sys.stderr)
        sys.exit(2)

    # 2. Resolve target.
    target = os.path.join(JSON_DIR, f"{slug}.json")
    if not os.path.exists(target):
        print(f"ERROR: Json/{slug}.json not found — no create-via-patch in v1.", file=sys.stderr)
        sys.exit(3)
    d = json.loads(open(target, encoding="utf-8").read())

    base_head = doc.get("base_head")
    do_conflict = bool(base_head) and ref_exists(base_head) and base_head != current_head()

    # 3. Apply each path: no-op → conflict → set.
    changed, skipped, conflicts = [], 0, []
    for path, value in patch.items():
        live = get_path(d, path, MISSING)
        if live is not MISSING and live == value:
            skipped += 1
            continue
        if do_conflict:
            base = base_value(slug, path, base_head, MISSING)
            moved_upstream = (base is not MISSING and live is not MISSING and base != live)
            if moved_upstream and live != value:
                conflicts.append((path, base, live, value))
                if not args.allow_conflict:
                    continue
        set_path(d, path, value)
        changed.append(path)

    if conflicts and not args.allow_conflict:
        print(f"\nCONFLICT: {len(conflicts)} path(s) moved upstream since base_head "
              f"{base_head[:7] if base_head else '?'} — refusing to overwrite.", file=sys.stderr)
        for p, base, live, inc in conflicts:
            print(f"  {p}\n    base    : {json.dumps(base, ensure_ascii=False)[:120]}"
                  f"\n    live    : {json.dumps(live, ensure_ascii=False)[:120]}"
                  f"\n    incoming: {json.dumps(inc, ensure_ascii=False)[:120]}", file=sys.stderr)
        print("\nRe-run with --allow-conflict to overwrite, or rebuild the patch on fresh live.",
              file=sys.stderr)
        sys.exit(4)

    # 4. Deletions (rare, explicit).
    deleted = []
    for path in delete:
        if pop_path(d, path):
            deleted.append(path)
        else:
            print(f"  warn: delete path not present (skipped): {path}", file=sys.stderr)

    # 5. research_log stamp (only if something actually changed).
    touched = changed + deleted
    if touched:
        rl = d.setdefault("research_log", [])
        rl.append({
            "date": TODAY,
            "by": "apply_studio_patch.py",
            "note": f"Studio patch [{doc.get('source', 'studio')}]: "
                    f"{len(changed)} set, {len(deleted)} removed.",
            "fields": touched,
        })

    # 6/7. Write (or dry-run) and report.
    if args.dry_run:
        print(f"[dry-run] {slug}: would set {len(changed)}, remove {len(deleted)}, "
              f"skip {skipped} no-ops"
              + (f", {len(conflicts)} conflict(s)" if conflicts else ""))
        for p in changed:
            print(f"  + {p}")
        for p in deleted:
            print(f"  - {p}")
        print("(dry-run — no JSON written)")
    else:
        if touched:
            with open(target, "w", encoding="utf-8") as f:
                f.write(json.dumps(d, ensure_ascii=False, indent=2) + "\n")
        print(f"{slug}: changed={len(changed)} skipped={skipped} "
              f"deleted={len(deleted)} conflicts={len(conflicts)}")


if __name__ == "__main__":
    main()
