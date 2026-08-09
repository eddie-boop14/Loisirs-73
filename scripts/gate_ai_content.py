#!/usr/bin/env python3
"""AI content layer gate — SPECaicontentlayer §C4.

Read-only. Proves the machine-readable layer the site advertises actually
exists and stays true to the corpus. Asserts, for the tree as built:

  1. every Json/<slug> has a content/<slug>.md  → no 404 on an advertised
     /content/<slug>.md URL (the headline: 308 live 404s must be 0).
  2. llms-full.txt header `Total lieux: N` == corpus size, and the number of
     `===` section rulers == corpus size (no count/section drift).
  3. llms.txt advertises the right total (`catalogs N`) and its per-category
     `### … (k lieux)` counts sum to the corpus (no "87 vs 392" recurrence).
  4. no `research_log` leaks into any content/*.md, llms.txt, or llms-full.txt.

Any violation → exit 1 (build red). Regenerate with scripts/build_ai_content.py.
"""
import argparse
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser(description="Assert the AI content layer exists and matches truth.")
    ap.add_argument("--json-dir", default=os.path.join(ROOT, "Json"))
    ap.add_argument("--content-dir", default=os.path.join(ROOT, "content"))
    ap.add_argument("--root", default=ROOT)
    args = ap.parse_args()

    # Corpus = published fiches only, mirroring build_ai_content.py: a draft
    # has no rendered HTML, so the AI surface must not advertise it (its
    # canonical_url would be a live 404 — GSC coverage 2026-07-27).
    slugs = []
    for f in glob.glob(os.path.join(args.json_dir, "*.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                if json.load(fh).get("status") == "published":
                    slugs.append(os.path.basename(f)[:-5])
        except Exception:
            slugs.append(os.path.basename(f)[:-5])  # unreadable → let later gates scream
    slugs = sorted(slugs)
    n = len(slugs)
    if n == 0:
        print(f"::error::no fiches under {args.json_dir}/", file=sys.stderr)
        sys.exit(1)

    violations = []

    # 1. advertised surfaces exist for every fiche (HANDOFF-39: md FR + md EN
    #    + typed facet JSON — three surfaces, zero advertised 404s)
    for label, mk in (
        ("/content/*.md", lambda s: os.path.join(args.content_dir, f"{s}.md")),
        ("/content/en/*.md", lambda s: os.path.join(args.content_dir, "en", f"{s}.md")),
        ("/api/lieu/*.json", lambda s: os.path.join(args.root, "api", "lieu", f"{s}.json")),
    ):
        missing = [s for s in slugs if not os.path.exists(mk(s))]
        if missing:
            violations.append(f"{len(missing)} advertised {label} missing (404s): "
                              + ", ".join(missing[:8]) + (" …" if len(missing) > 8 else ""))

    # 4a. research_log must not leak into any per-lieu surface
    for label, mk in (
        ("content/*.md", lambda s: os.path.join(args.content_dir, f"{s}.md")),
        ("content/en/*.md", lambda s: os.path.join(args.content_dir, "en", f"{s}.md")),
        ("api/lieu/*.json", lambda s: os.path.join(args.root, "api", "lieu", f"{s}.json")),
    ):
        leaks = [s for s in slugs
                 if os.path.exists(mk(s))
                 and "research_log" in open(mk(s), encoding="utf-8").read()]
        if leaks:
            violations.append(f"research_log leaked into {len(leaks)} {label}: "
                              + ", ".join(leaks[:8]))

    # 5. ai-info.json is GENERATED and counts from truth (HANDOFF-39: the
    #    hand-authored file drifted to 87 vs 392 — never again)
    ai_info_path = os.path.join(args.root, ".well-known", "ai-info.json")
    if not os.path.exists(ai_info_path):
        violations.append(".well-known/ai-info.json missing")
    else:
        try:
            info = json.load(open(ai_info_path, encoding="utf-8"))
            if info.get("content_count") != n:
                violations.append(f"ai-info.json content_count={info.get('content_count')}"
                                  f" ≠ corpus {n}")
        except Exception as e:
            violations.append(f"ai-info.json unreadable: {e}")

    # 2. llms-full.txt
    full_path = os.path.join(args.root, "llms-full.txt")
    if not os.path.exists(full_path):
        violations.append("llms-full.txt missing")
    else:
        full = open(full_path, encoding="utf-8").read()
        m = re.search(r"Total lieux:\s*(\d+)", full)
        if not m:
            violations.append("llms-full.txt has no 'Total lieux:' header")
        elif int(m.group(1)) != n:
            violations.append(f"llms-full.txt Total lieux={m.group(1)} ≠ corpus {n}")
        rulers = len(re.findall(r"^={80}$", full, re.M))
        if rulers != n:
            violations.append(f"llms-full.txt has {rulers} section rulers ≠ corpus {n}")
        if "research_log" in full:
            violations.append("research_log leaked into llms-full.txt")

    # 3. llms.txt
    idx_path = os.path.join(args.root, "llms.txt")
    if not os.path.exists(idx_path):
        violations.append("llms.txt missing")
    else:
        idx = open(idx_path, encoding="utf-8").read()
        m = re.search(r"catalogs\s+(\d+)\s+leisure", idx)
        if not m:
            violations.append("llms.txt has no 'catalogs N leisure' total")
        elif int(m.group(1)) != n:
            violations.append(f"llms.txt advertises {m.group(1)} ≠ corpus {n}")
        cat_counts = [int(x) for x in re.findall(r"^###\s+.+?\((\d+)\s+lieux\)", idx, re.M)]
        if sum(cat_counts) != n:
            violations.append(f"llms.txt per-category counts sum to {sum(cat_counts)} ≠ corpus {n}")
        if "research_log" in idx:
            violations.append("research_log leaked into llms.txt")

    print(f"gate_ai_content: {n} fiches; checked content/*.md + content/en/*.md "
          f"+ api/lieu/*.json + llms.txt + llms-full.txt + ai-info.json")
    if not violations:
        print("✓ AI content layer complete and in sync with the corpus (0 advertised 404s)")
        sys.exit(0)
    print(f"::error::{len(violations)} AI-content violation(s):")
    for v in violations:
        print(f"    ✗ {v}")
    print("\nRegenerate: python3 scripts/build_ai_content.py")
    sys.exit(1)


if __name__ == "__main__":
    main()
