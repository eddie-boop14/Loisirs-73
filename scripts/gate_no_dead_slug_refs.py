#!/usr/bin/env python3
"""gate_no_dead_slug_refs.py — no generated index may point at a deleted fiche.

After a dedup/merge/rename, generated indexes can keep pointing at a slug whose
Json/<slug>.json no longer exists. Downstream that becomes a dead link or a
crash (see review_agent on aquaparc-aqualis-cluses; HANDOFF-15's
chateau-des-rubins-observatoire-des-alpes lingered in transport_index's
_meta.line_conflicts for weeks because only TOP-LEVEL keys were checked).

Covered sources:
  - data/*_index.json           top-level keys (minus _meta) AND every nested
                                "slug" value, wherever it hides (_meta included)
                                — auto-covers future *_index.json files.
  - data/intent-hubs.json       members[].slug

Known non-fiche namespaces are excluded explicitly (transport_index's
_meta.feeds[].slug are transport.data.gouv.fr dataset ids, not fiches).

Exit 1 on any dead reference. Read-only.

CLI:
    python3 scripts/gate_no_dead_slug_refs.py [--root DIR]
"""
import argparse
import glob
import json
import os
import sys

DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Subtrees whose "slug" values are NOT fiche slugs: (filename, path-prefix)
NON_FICHE_SUBTREES = [
    ("transport_index.json", ("_meta", "feeds")),
]


def _live(root):
    return {os.path.splitext(os.path.basename(p))[0]
            for p in glob.glob(os.path.join(root, "Json", "*.json"))}


def _index_slugs(path):
    """Top-level keys (minus _meta) + every nested 'slug' string value,
    excluding the declared non-fiche namespaces."""
    fname = os.path.basename(path)
    excluded = tuple(pfx for f, pfx in NON_FICHE_SUBTREES if f == fname)
    d = json.loads(open(path, encoding="utf-8").read())
    refs = [k for k in d if k != "_meta"]

    def walk(o, trail):
        if any(trail[:len(pfx)] == pfx for pfx in excluded):
            return
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "slug" and isinstance(v, str):
                    refs.append(v)
                walk(v, trail + (k,))
        elif isinstance(o, list):
            for x in o:
                walk(x, trail)

    walk(d, ())
    return refs


def _intent_members(path):
    hubs = json.loads(open(path, encoding="utf-8").read())
    return [m["slug"] for h in hubs for m in h.get("members", [])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=DEFAULT_ROOT,
                    help="Repo root containing Json/ and data/ (tests only)")
    args = ap.parse_args()
    root = args.root

    sources = {rel: _index_slugs
               for rel in sorted(
                   os.path.relpath(p, root)
                   for p in glob.glob(os.path.join(root, "data", "*_index.json")))}
    sources["data/intent-hubs.json"] = _intent_members

    live = _live(root)
    viol = []
    checked = 0
    for rel, extractor in sources.items():
        path = os.path.join(root, rel)
        if not os.path.exists(path):
            continue
        refs = extractor(path)
        checked += len(refs)
        for slug in refs:
            # only flag plausible fiche slugs (skip obvious non-slug strings)
            if slug and "/" not in slug and slug not in live:
                viol.append(f"{rel} -> {slug} (no Json/{slug}.json)")
    print(f"gate_no_dead_slug_refs: checked {checked} slug ref(s) across {len(sources)} index(es)")
    if viol:
        print(f"::error::{len(viol)} dead slug reference(s):")
        for v in viol:
            print(f"    ✗ {v}")
        sys.exit(1)
    print("✓ every indexed slug resolves to a live fiche")


if __name__ == "__main__":
    main()
