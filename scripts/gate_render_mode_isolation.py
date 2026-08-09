#!/usr/bin/env python3
"""gate_render_mode_isolation.py — the facts/prose lane's structural guard
(HANDOFF-19, follow-up to the pl full-tree activation).

The roster carries two orthogonal axes: status (visibility) x render_mode
(prose | facts). A facts language (pl, and pt/cs/ar/he/ja next) is rendered ONLY
by build_fulltree_lang from curated JSON; it must NEVER pass through a prose
builder, which would emit FR-fallback prose and clobber the facts tree.

scripts/locales.py makes this structural: PROSE / PROSE_SECONDARY exclude facts
langs by derivation, and the old mixed-mode `PUBLISHED` symbol is deleted so a
stale `locales.PUBLISHED` raises at import. This gate PROVES those invariants
hold and stops the one regression a future edit could introduce: a prose/deploy
builder reaching for a facts-containing roster (VISIBLE / VISIBLE_SECONDARY /
FACTS_PUBLISHED) in a way that renders pages.

Some facts-roster references in prose/deploy builders ARE legitimate (the
language picker, the hreflang cluster, the deploy copy that ships pl's
already-rendered tree). So the contract is explicit, not a blanket ban: every
such reference in a policed builder MUST carry a trailing `# isolation-ok:
<reason>` tag, making each a reviewed, justified decision. An untagged
reference fails the build -- which is exactly what a careless
`for lang in locales.VISIBLE: render_fiche(...)` would be.

Read-only. Exit 1 on any violation.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import locales  # noqa: E402

REF_RE = re.compile(r"\blocales\.(VISIBLE|VISIBLE_SECONDARY|FACTS_PUBLISHED)\b")
TAG = "# isolation-ok:"

# Prose / deploy builders that emit or ship pages. A facts-roster reference here
# is allowed ONLY with an explicit isolation-ok tag (picker / hreflang / deploy).
POLICED = (
    "build_site.py", "build_all_locales.py", "build_lieu_page.py",
    "build_hubs.py", "build_intent_hubs.py", "build_communes.py",
    "build_catalog_index.py", "ingest_translations.py", "fix_hub_chrome.py",
    "build_pilot_langs.py", "fix_lang_nav.py",
)
# Exempt (not scanned): build_fulltree_lang.py (the facts orchestrator) and
# build_homepage_lang.py (its homepage renderer, HANDOFF-31 — refuses the six
# by assertion), build_all.py (orchestrator), and gate_*/fix_hreflang_sitemap.py
# (visibility validators / the hreflang+sitemap authority) which are SUPPOSED
# to scope to VISIBLE.


def main():
    viol = []

    # 1) roster algebra -- the structural guarantee, proven not assumed
    prose = set(locales.PROSE)
    facts = set(locales.FACTS_PUBLISHED)
    vis = set(locales.VISIBLE)
    if prose & facts:
        viol.append(f"PROSE n FACTS_PUBLISHED must be empty, got {sorted(prose & facts)}")
    if prose | facts != vis:
        viol.append(f"PROSE u FACTS_PUBLISHED must equal VISIBLE; symmetric diff "
                    f"{sorted((prose | facts) ^ vis)}")
    if not set(locales.PROSE_SECONDARY) <= prose:
        viol.append("PROSE_SECONDARY must be a subset of PROSE")
    if not set(locales.VISIBLE_SECONDARY) <= vis:
        viol.append("VISIBLE_SECONDARY must be a subset of VISIBLE")

    # 2) the deleted nuisance symbol stays deleted
    if hasattr(locales, "PUBLISHED"):
        viol.append("locales.PUBLISHED must stay deleted -- it mixed render modes and is the "
                    "clobber footgun; consumers must choose PROSE/FACTS/VISIBLE explicitly")

    # 3) the tag contract on policed builders
    for fn in POLICED:
        fp = os.path.join(HERE, fn)
        if not os.path.exists(fp):
            continue
        for i, line in enumerate(open(fp, encoding="utf-8"), 1):
            if REF_RE.search(line) and TAG not in line:
                viol.append(f"{fn}:{i} references a facts-containing roster without "
                            f"`{TAG} <reason>` -- tag it (picker/hreflang/deploy) or switch to "
                            f"PROSE/PROSE_SECONDARY: {line.strip()[:80]}")

    # 4) the facts owner must actually drive the facts langs
    ba = os.path.join(HERE, "build_all.py")
    if os.path.exists(ba) and "FACTS_PUBLISHED" not in open(ba, encoding="utf-8").read():
        viol.append("build_all.py no longer drives FACTS_PUBLISHED -- facts langs would not render")

    print(f"gate_render_mode_isolation: PROSE={sorted(prose)} FACTS={sorted(facts)} "
          f"VISIBLE={sorted(vis)}")
    if viol:
        print(f"::error::{len(viol)} render-mode isolation violation(s):")
        for v in viol[:50]:
            print(f"    x {v}")
        sys.exit(1)
    print("OK roster algebra holds; PUBLISHED deleted; every facts-roster use in a prose/deploy "
          "builder is tagged isolation-ok; facts langs render only via build_fulltree_lang")


if __name__ == "__main__":
    main()
