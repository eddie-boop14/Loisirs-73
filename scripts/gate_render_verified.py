#!/usr/bin/env python3
"""gate_render_verified.py — the honest publish gate (HANDOFF-16).

A new language is `held` behind a `+native` human review that will never come.
A gate that can't be met = never ship. We replace it with a bar that CAN be met,
honestly, and automatically: the page is **provably understood when rendered**.

`reports/render-verify-<lang>.json` is the evidence, produced by render_verify.py
(headless render) + a vision comprehension round-trip:

  Layer A — RENDERING is not broken: dir="rtl" applied (ar/he), no horizontal
            overflow, <bdi> isolates every price / frozen FR name / number so
            they read LTR-correct inside RTL, and NO tofu / U+FFFD (the font
            actually rendered the script).
  Layer B — the page is UNDERSTOOD: a vision model reads the *rendered screenshot*
            (not the source) and its extracted facts (place, price, accessibility)
            round-trip-match the source JSON. A strong reader understanding the
            rendered page is direct evidence it communicates.

This gate validates that report. A language may carry `+render-ai` in its
`reviewed` string ONLY when its report is clean (Layer A + B PASS, 0 escalations)
— so the flag can never be hand-set without the evidence. The provenance is
honest: we claim AI-render-verified, not native.

Read-only. Exit 1 on any violation.
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def render_report(lang, root=ROOT):
    """Return the parsed render-verify report for `lang`, or None if absent/bad."""
    fp = os.path.join(root, "reports", f"render-verify-{lang}.json")
    if not os.path.exists(fp):
        return None
    try:
        return json.loads(open(fp, encoding="utf-8").read())
    except ValueError:
        return {}


def render_ai_clean(lang, root=ROOT):
    """True iff `lang` has a clean render-verify report (Layer A + B PASS, zero
    escalations). The bar that authorises `+render-ai` provenance + publish."""
    r = render_report(lang, root)
    return bool(r) and r.get("layerA") == "PASS" and r.get("layerB") == "PASS" \
        and r.get("escalations", 1) == 0 and r.get("overall") == "PASS"


def main():
    labels_fp = os.path.join(ROOT, "data", "i18n-labels.json")
    labels = json.loads(open(labels_fp, encoding="utf-8").read())
    reviewed = labels.get("_meta", {}).get("reviewed", {})
    viol = []
    claimed = sorted(l for l, r in reviewed.items() if "+render-ai" in str(r or ""))

    for lang in claimed:
        r = render_report(lang)
        if r is None:
            viol.append(f"reviewed['{lang}'] claims +render-ai but reports/render-verify-{lang}.json missing")
            continue
        if r.get("layerA") != "PASS":
            viol.append(f"{lang}: Layer A (rendering) not PASS ({r.get('layerA')}) — "
                        f"{r.get('layerA_fail', '?')} page(s) broke RTL/bidi/glyph")
        if r.get("layerB") != "PASS":
            viol.append(f"{lang}: Layer B (comprehension) not PASS ({r.get('layerB')})")
        if r.get("escalations", 1) != 0:
            viol.append(f"{lang}: {r.get('escalations')} escalation(s) — a page read garbled/wrong-meaning")
        if r.get("overall") != "PASS":
            viol.append(f"{lang}: overall != PASS ({r.get('overall')})")

    # Every render-verify report present must itself be internally consistent.
    for fp in glob.glob(os.path.join(ROOT, "reports", "render-verify-*.json")):
        lang = os.path.basename(fp)[len("render-verify-"):-len(".json")]
        r = render_report(lang)
        if not r:
            viol.append(f"reports/render-verify-{lang}.json is empty/unparseable")
            continue
        held = [p for p in r.get("results", []) if p.get("verdict") == "HOLD"]
        if held and r.get("overall") == "PASS":
            viol.append(f"{lang}: overall PASS but {len(held)} page(s) marked HOLD — inconsistent")

    print(f"gate_render_verified: langs claiming +render-ai: {claimed or 'none'}")
    for lang in claimed:
        r = render_report(lang) or {}
        print(f"  {lang}: Layer A={r.get('layerA')} Layer B={r.get('layerB')} "
              f"escalations={r.get('escalations')} overall={r.get('overall')} "
              f"({r.get('pages','?')} pages)")
    if viol:
        print(f"::error::{len(viol)} render-verify violation(s):")
        for v in viol[:50]:
            print(f"    ✗ {v}")
        sys.exit(1)
    print("✓ every +render-ai language is backed by a clean render-verify report "
          "(Layer A rendering + Layer B comprehension, zero escalations)")


if __name__ == "__main__":
    main()
