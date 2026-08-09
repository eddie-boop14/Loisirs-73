#!/usr/bin/env python3
"""gate_locale_status.py — the roster's status model is the contract that
protects the live originals (HANDOFF-10 Job 2).

data/languages.json assigns every language a status. This gate fails the build
if any language violates what its status permits:

  published         full tree — MAY appear in sitemap, hreflang clusters, and
                    the language picker.
  staged-indexable  indexable pilot — its OWN URLs in sitemap.xml, but NEVER in
                    any hreflang cluster and NEVER in the picker (HANDOFF-11).
  staged            noindex pilot — absent from sitemap, hreflang, and picker.
  held              render-blocked — no rendered tree at all (RTL + native pending).

The decisive guard is a single scan of the `hreflang="xx"` attribute across
every built page: in this codebase BOTH the on-page hreflang cluster AND the
language picker links emit `hreflang="xx"` (build_lieu_page renders the picker
as <a … hreflang="lg">). So one scan proves "only published languages appear in
hreflang OR the picker." A non-published code anywhere = a leak into the 6.

Provenance (the `reviewed` method string) is owned solely by data/i18n-labels.json
(gate_i18n_labels.py); this gate only cross-checks that a non-published language
is vocabulary-verified there before it is allowed to stage or hold.

Read-only. Exit 1 on any violation.
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import locales  # noqa: E402

VALID_STATUS = {"published", "staged-indexable", "staged", "held"}
HREFLANG_RE = re.compile(r'hreflang="([a-zA-Z-]+)"')
SITEMAP_LANG_RE = re.compile(r'<loc>https?://[^/]+/([a-z]{2})/')
LABELS_PATH = os.path.join(ROOT, "data", "i18n-labels.json")
SITEMAP = os.path.join(ROOT, "sitemap.xml")
# directories that hold build output / vendored copies — scanning them would
# double-count; the source tree in-place is the authority.
SKIP_DIRS = ("_site", ".git", "node_modules", "scripts")


def iter_html():
    for fp in glob.glob(os.path.join(ROOT, "**", "*.html"), recursive=True):
        rel = os.path.relpath(fp, ROOT)
        if rel.split(os.sep)[0] in SKIP_DIRS:
            continue
        yield fp, rel


def main():
    viol = []
    L = locales.LANGUAGES
    published = set(locales.VISIBLE)
    staged_idx = set(locales.STAGED_INDEXABLE)
    staged = set(locales.STAGED)
    held = set(locales.HELD)

    # 1) roster well-formedness
    roots = [l for l, v in L.items() if v.get("root")]
    if roots != ["fr"]:
        viol.append(f"expected exactly one root locale 'fr', found {roots}")
    for l, v in L.items():
        if v.get("status") not in VALID_STATUS:
            viol.append(f"{l}: invalid status {v.get('status')!r}")
        if not str(v.get("endonym", "")).strip():
            viol.append(f"{l}: missing endonym")
        if v.get("dir") not in ("ltr", "rtl"):
            viol.append(f"{l}: invalid dir {v.get('dir')!r}")

    # 2) cross-validate non-published status against the single provenance source
    labels = json.loads(open(LABELS_PATH, encoding="utf-8").read())
    reviewed = labels.get("_meta", {}).get("reviewed", {})
    for l in sorted(staged_idx | held):
        rv = reviewed.get(l)
        if not rv or rv is False:
            viol.append(f"{l} is '{L[l]['status']}' but data/i18n-labels.json reviewed[{l!r}]={rv!r} "
                        f"— a non-published language must be vocabulary-verified before it stages/holds")
    # A held language stays noindex until it is render-cleared: +native (a human
    # spot-check) OR +render-ai (HANDOFF-16: AI-render-verified, report-backed).
    # A render-ai-cleared language may legitimately remain 'held' while its full
    # tree is built (verified, publish-pending) — so only the legacy +native flag
    # (which meant "ship now") is flagged as a held inconsistency here.
    for l in sorted(held):
        if "+native" in str(reviewed.get(l) or ""):
            viol.append(f"{l} is 'held' but i18n-labels marks it +native — promote it, don't hold it")

    # 3) hreflang/picker isolation — the core guard
    seen = {}  # code -> example file
    for fp, rel in iter_html():
        try:
            html = open(fp, encoding="utf-8").read()
        except OSError:
            continue
        for code in HREFLANG_RE.findall(html):
            if code == "x-default":
                continue
            base = code.split("-")[0].lower()
            if base not in published:
                seen.setdefault(base, rel)
    for code in sorted(seen):
        viol.append(f"hreflang/picker leak: non-published '{code}' appears in {seen[code]} "
                    f"(and likely others) — hreflang+picker must stay {sorted(published)}")

    # 4) sitemap membership — only published + staged-indexable locale prefixes
    sm = open(SITEMAP, encoding="utf-8").read() if os.path.exists(SITEMAP) else ""
    sm_langs = set(SITEMAP_LANG_RE.findall(sm))
    for code in sorted(sm_langs & (staged | held)):
        viol.append(f"sitemap lists '{code}/' URLs but status is {locales.status(code)!r} "
                    f"(staged/held must never be in the sitemap)")
    for code in sorted(staged_idx):
        if code not in sm_langs:
            viol.append(f"staged-indexable '{code}' has no URLs in sitemap.xml — the GSC clock needs them")

    # 5) held languages may carry a NOINDEX staged pilot for the render check
    #    (HANDOFF-13 Phase C / HANDOFF-16), but never an indexable page until they
    #    are render-cleared (+native or +render-ai) AND promoted to published.
    for l in sorted(held):
        for fp in glob.glob(os.path.join(ROOT, l, "**", "*.html"), recursive=True):
            if "noindex" not in open(fp, encoding="utf-8").read()[:2000]:
                viol.append(f"held language '{l}' has an indexable page {os.path.relpath(fp, ROOT)} "
                            f"— held must stay noindex until +native/+render-ai + promotion")

    print(f"gate_locale_status: published={sorted(published)} "
          f"staged-indexable={sorted(staged_idx)} held={sorted(held)} staged={sorted(staged)}")
    print(f"  hreflang codes site-wide: {sorted(published)} + x-default "
          f"(non-published leaks: {sorted(seen) or 'none'})")
    print(f"  sitemap locale prefixes: {sorted(sm_langs) or 'none'}")
    if viol:
        print(f"::error::{len(viol)} locale-status violation(s):")
        for v in viol[:50]:
            print(f"    ✗ {v}")
        sys.exit(1)
    print("✓ only published langs in hreflang/picker; staged-indexable in sitemap only; "
          "held render-blocked")


if __name__ == "__main__":
    main()
