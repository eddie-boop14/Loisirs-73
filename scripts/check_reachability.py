#!/usr/bin/env python3
"""BFS reachability from <locale>/index.html. Zero-orphans gate for JOB 4.

Each locale tree has:
  - 392 fiche pages (canonical)
  - 9 FR hub indexes (cascades, chateaux, …) translated per locale
  - chrome pages (cgv, mentions-legales, devenir-partenaire, signaler-info,
    merci-* — many noindex, expected to be excluded from `content` set)
  - 1 landing index.html

Algorithm:
  1. Build the `content` set: every .html under the tree that's NOT in
     EXCLUDE, plus hub dirs (foo/index.html).
  2. BFS from `index` following internal hrefs (same-locale only).
  3. Report unreachable nodes per locale.
"""
import argparse
import siteconfig  # HANDOFF-73 phase 5: per-site identity
import re
import sys
from collections import deque
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import locales  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ALL_LANGS = locales.PROSE

# Hubs per locale — keyed by local slug. Empty string = FR (root tree).
HUB_DIRS = {
    "fr": ["cascades","chateaux","musees","points-de-vue","sentiers","telecabines",
           "voies-vertes","lacs-plages","bases-de-loisirs","baignade-nautisme",
           "parcs-jardins","que-faire","sensations-plein-air","sorties-detente","sport-jeux"],
    "en": [],   # locale hubs discovered dynamically by os scan
    "de": [],
    "it": [],
    "es": [],
    "nl": [],
}
# Chrome / system pages that exist but aren't expected in reachability "content" set
EXCLUDE = {"index","404","cgv","signaler-info","devenir-partenaire",
           "merci-partenaire","merci-signalement",
           "mentions-legales-loisirs74-phase1","politique-confidentialite-loisirs74-phase1",
           "studio"}


def norm(s):
    s = s.strip("/")
    s = re.sub(r"\.html$", "", s)
    return s or "index"


NON_HUB_DIRS = {"_site", "__pycache__", "reports", "scripts", "Json", "api",
                "content", ".well-known", "node_modules", ".git",
                *locales.ALL_SUBDIR_LANGS}


def discover_hubs(base):
    """Find directories under `base` that have an index.html (hub listings).
    Skip build outputs, source data, and sibling locale trees."""
    hubs = []
    for d in sorted(base.iterdir()) if base.exists() else []:
        if d.is_dir() and d.name not in NON_HUB_DIRS and (d / "index.html").exists():
            hubs.append(d.name)
    return hubs


def links_in(path, lang):
    """Extract internal hrefs from `path` that point inside the same locale tree."""
    out = set()
    h = path.read_text(encoding="utf-8", errors="ignore")
    cur_prefix = f"/{lang}/" if lang != "fr" else "/"
    skip_prefixes = tuple(f"/{L}/" for L in ALL_LANGS if L != lang)
    for href in re.findall(r'href=["\']([^"\']+)["\']', h):
        m = re.match(r"(?:https?://(?:www\.)?" + siteconfig.DOMAIN_RE + r")?(/[^\"' ]*)", href)
        if not m:
            continue
        p = m.group(1).split("#")[0].split("?")[0]
        if p.startswith(skip_prefixes + ("/api/", "/content/", "/scripts/", "/Json/", "/_site/")):
            continue
        if cur_prefix != "/" and p.startswith(cur_prefix):
            p = p[len(cur_prefix) - 1:]
        if lang == "fr" and p.startswith("/"):
            p = p
        out.add(norm(p))
    return out


def run_locale(lang):
    base = ROOT if lang == "fr" else ROOT / lang
    if not base.exists():
        print(f"[{lang}] tree missing")
        return None
    hubs = discover_hubs(base)
    nodes = {norm(p.name) for p in base.glob("*.html")}
    nodes |= set(hubs)

    def file_for(n):
        if n == "index":
            return base / "index.html"
        if n in hubs:
            return base / n / "index.html"
        cand = base / f"{n}.html"
        return cand if cand.exists() else None

    seen = set()
    q = deque(["index"])
    while q:
        n = q.popleft()
        if n in seen: continue
        seen.add(n)
        f = file_for(n)
        if not f or not f.exists(): continue
        for t in links_in(f, lang):
            if t in nodes and t not in seen:
                q.append(t)
    content = nodes - EXCLUDE
    orphans = content - seen
    return {
        "lang": lang,
        "nodes": len(nodes),
        "content": len(content),
        "reachable": len(content & seen),
        "orphans": sorted(orphans),
        "hubs": hubs,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true",
                    help="Exit non-zero if any locale has orphans")
    args = ap.parse_args()
    total_orphans = 0
    print(f"{'lang':<5} {'hubs':<6} {'content':<10} {'reachable':<11} {'orphans':<10}")
    print("-" * 50)
    rows = []
    for lang in ALL_LANGS:
        r = run_locale(lang)
        if r is None: continue
        rows.append(r)
        print(f"{r['lang']:<5} {len(r['hubs']):<6} {r['content']:<10} {r['reachable']:<11} {len(r['orphans']):<10}")
        total_orphans += len(r["orphans"])

    if total_orphans:
        print()
        print("=== orphan detail ===")
        for r in rows:
            if r["orphans"]:
                print(f"  [{r['lang']}]:")
                for o in r["orphans"]:
                    print(f"    ORPHAN: {o}")
    print(f"\nTOTAL ORPHANS: {total_orphans}")
    if args.strict and total_orphans:
        sys.exit(1)


if __name__ == "__main__":
    main()
