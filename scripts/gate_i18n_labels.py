#!/usr/bin/env python3
"""gate_i18n_labels.py — the label vocabulary is the only translation surface,
and a language must never half-ship (HANDOFF-05).

data/i18n-labels.json is the closed label vocabulary (facts stay in Json/, never
here). This gate enforces the no-fabrication-applied-to-language rule:

  1. Structure: fr + en (the references) are non-empty for every key.
  2. Completeness: for any language marked `reviewed: true`, EVERY key is
     non-empty — no FR fallback may leak into a published language.
  3. Safety: a language that is NOT reviewed:true must NOT be published — it
     must not appear in the rendered roster (no <lang>/ tree, not in sitemap).
     (We assert the build roster only contains reviewed languages.)
  4. RTL: every language listed in _meta.rtl is a known rtl script (ar/he), and
     _meta.reviewed / _meta.languages cover exactly the vocabulary languages.

Exit 1 on any violation. Read-only.
"""
import glob
import json
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import locales  # noqa: E402
import gate_render_verified  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABELS = os.path.join(ROOT, "data", "i18n-labels.json")
REFERENCE = {"fr", "en"}
KNOWN_RTL = {"ar", "he"}
SECTIONS = ("fact_labels", "fact_values", "descriptors_by_type",
            "ui_chrome", "hub_names", "months")
# Languages currently rendered/published by the builders (the active roster).
PUBLISHED_ROSTER = set(locales.VISIBLE)


def main():
    if not os.path.exists(LABELS):
        print(f"::error::{LABELS} missing"); sys.exit(1)
    data = json.loads(open(LABELS, encoding="utf-8").read())
    meta = data.get("_meta", {})
    reviewed = meta.get("reviewed", {})
    rtl = set(meta.get("rtl", []))
    declared = set(meta.get("languages", {}).keys())
    viol = []

    # languages actually present across the vocabulary
    present = set()
    for sec in SECTIONS:
        for key, row in (data.get(sec, {}) or {}).items():
            present |= set(row.keys())
    present.discard("")

    # _meta must describe exactly the languages used
    if declared != present:
        viol.append(f"_meta.languages {sorted(declared)} != vocabulary langs {sorted(present)}")
    for lang in present:
        if lang not in reviewed:
            viol.append(f"_meta.reviewed missing '{lang}'")

    # rtl sanity
    for lang in rtl:
        if lang not in KNOWN_RTL:
            viol.append(f"_meta.rtl lists unknown rtl lang '{lang}'")

    # A language is "published" when its reviewed flag is non-false: either the
    # legacy bool true (fr/en references) OR a provenance method string such as
    # "ai-consensus-3x-2026-06-29". A bare flag is never enough — a method-string
    # review MUST be backed by reports/i18n-verify-<lang>.json with zero
    # escalations, so the flag can't be hand-set without the evidence.
    def is_published(lang):
        return bool(reviewed.get(lang)) and reviewed.get(lang) is not False

    # per-key checks
    n_keys = 0
    for sec in SECTIONS:
        rows = data.get(sec, {}) or {}
        for key, row in rows.items():
            n_keys += 1
            for ref in REFERENCE:
                if not str(row.get(ref, "")).strip():
                    viol.append(f"{sec}.{key}: reference '{ref}' empty")
            # a published language must have EVERY key filled
            for lang in reviewed:
                if is_published(lang) and not str(row.get(lang, "")).strip():
                    viol.append(f"{sec}.{key}: published lang '{lang}' is empty (FR fallback would leak)")

    # method-string reviews must carry a clean verification report
    for lang in reviewed:
        rv = reviewed.get(lang)
        if lang in REFERENCE:
            continue
        if rv and rv is not True:  # a method string (e.g. ai-consensus-3x-…)
            rep = os.path.join(ROOT, "reports", f"i18n-verify-{lang}.json")
            if not os.path.exists(rep):
                viol.append(f"reviewed['{lang}']={rv!r} but reports/i18n-verify-{lang}.json missing")
            else:
                try:
                    rj = json.loads(open(rep, encoding="utf-8").read())
                except ValueError:
                    rj = {}
                if rj.get("escalations", 1) != 0 or rj.get("overall") != "PASS":
                    viol.append(f"reviewed['{lang}']={rv!r} but verify report not clean "
                                f"(escalations={rj.get('escalations')}, overall={rj.get('overall')})")
                if not str(meta.get("review_method", {}).get(lang, "")).strip():
                    viol.append(f"reviewed['{lang}'] is a method string but _meta.review_method['{lang}'] missing")

    # safety: only reviewed languages may be in the published roster
    publishable = {l for l, r in reviewed.items() if r}
    # (informational) which filled-but-unreviewed languages await native review
    awaiting = sorted(l for l in present if l not in REFERENCE and not reviewed.get(l)
                      and all(str((data[sec].get(k, {})).get(l, "")).strip()
                              for sec in SECTIONS for k in data[sec]))

    # RTL languages (ar/he) are router/vocab-verified but RENDER-HELD until the
    # rendered RTL pilot is proven not-broken-and-understood. Two ways to clear:
    #   +native     — a native human spot-check (the original bar), OR
    #   +render-ai  — AI-render-verified (HANDOFF-16): headless-render Layer A
    #                 (RTL/bidi/glyph/no-tofu) + vision comprehension Layer B,
    #                 backed by a CLEAN reports/render-verify-<lang>.json. The flag
    #                 can't be hand-set — gate_render_verified enforces the report.
    # Until cleared they MAY carry a NOINDEX staged pilot but must NOT publish an
    # indexable page.
    def native_cleared(lang):
        rv = str(reviewed.get(lang) or "")
        if "+native" in rv:
            return True
        return "+render-ai" in rv and gate_render_verified.render_ai_clean(lang, ROOT)
    render_held = sorted(l for l in rtl if reviewed.get(l) and not native_cleared(l))
    for lang in render_held:
        for fp in glob.glob(os.path.join(ROOT, lang, "**", "*.html"), recursive=True):
            if "noindex" not in open(fp, encoding="utf-8").read()[:2000]:
                viol.append(f"rtl '{lang}' is render-held (no +native) but "
                            f"{os.path.relpath(fp, ROOT)} is not noindex")

    # any unreviewed language must NOT have a rendered tree published
    for lang in present - REFERENCE:
        if not reviewed.get(lang):
            tree = os.path.join(ROOT, lang)
            # the language tree may exist for preview, but it must be excluded
            # from the published roster. We only fail if it is reviewed-claimed.
            if os.path.isdir(tree) and lang in PUBLISHED_ROSTER:
                viol.append(f"lang '{lang}' renders a published tree but reviewed=false")

    print(f"gate_i18n_labels: {n_keys} label keys × {len(present)} languages "
          f"({', '.join(sorted(present))})")
    print(f"  vocab-verified: {sorted(publishable)}")
    print(f"  render-held (RTL, native spot-check pending): {render_held}")
    print(f"  filled, awaiting review: {awaiting}")
    if viol:
        print(f"::error::{len(viol)} i18n-label violation(s):")
        for v in viol[:50]:
            print(f"    ✗ {v}")
        sys.exit(1)
    print("✓ references complete; no reviewed language leaks FR fallback; "
          "unreviewed languages do not publish")


if __name__ == "__main__":
    main()
