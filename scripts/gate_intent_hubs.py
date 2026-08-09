#!/usr/bin/env python3
"""gate_intent_hubs.py — registry-driven intent-hub integrity.

Asserts the intent hubs are curated (registry-only), each has a real list, and
each renders in all 6 locales with valid schema + resolvable members.

Checks (acceptance §5):
  - data/intent-hubs.json parses; every hub has slug, h1, ≥3 members.
  - every member slug has a Json/<slug>.json (member link will resolve).
  - every hub page exists FR + 5 locales (flat <slug>.html + <lang>/<slug>.html).
  - each page carries ItemList + FAQPage JSON-LD with ≥3 ItemList entries.
  - category_hub resolves to a real hub dir (FR) — the reachability anchor.

Exit 1 on any violation. Read-only.
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from build_hubs import hub_locale_map  # noqa: E402
import locales  # noqa: E402

REGISTRY = os.path.join(ROOT, "data", "intent-hubs.json")
LANGS = locales.PROSE


def page_path(slug, lang):
    return os.path.join(ROOT, f"{slug}.html") if lang == "fr" \
        else os.path.join(ROOT, lang, f"{slug}.html")


def main():
    viol = []
    hubs = json.loads(open(REGISTRY, encoding="utf-8").read())
    slugs = [h["slug"] for h in hubs]
    if len(slugs) != len(set(slugs)):
        viol.append("duplicate hub slug in registry")
    for h in hubs:
        s = h.get("slug", "?")
        if not h.get("h1", {}).get("fr"):
            viol.append(f"{s}: missing h1.fr")
        members = h.get("members", [])
        if len(members) < 3:
            viol.append(f"{s}: only {len(members)} member(s) (need ≥3)")
        bucket_keys = {b["key"] for b in h.get("buckets", [])}
        for m in members:
            ms = m.get("slug")
            if not os.path.exists(os.path.join(ROOT, "Json", f"{ms}.json")):
                viol.append(f"{s}: member {ms} has no Json fiche")
            if m.get("bucket") not in bucket_keys:
                viol.append(f"{s}: member {ms} bucket {m.get('bucket')!r} not in registry buckets")
        # category hub anchor must exist (FR)
        cat = h.get("category_hub")
        if not cat or not os.path.exists(os.path.join(ROOT, cat, "index.html")):
            viol.append(f"{s}: category_hub {cat!r} has no FR hub dir")
        # pages exist in all locales + schema present
        for lang in LANGS:
            p = page_path(s, lang)
            if not os.path.exists(p):
                viol.append(f"{s}: missing {lang} page"); continue
            html = open(p, encoding="utf-8").read()
            m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
            if not m:
                viol.append(f"{s}/{lang}: no JSON-LD"); continue
            try:
                graph = json.loads(m.group(1)).get("@graph", [])
            except json.JSONDecodeError:
                viol.append(f"{s}/{lang}: JSON-LD invalid"); continue
            types = {g.get("@type") for g in graph}
            if "ItemList" not in types or "FAQPage" not in types:
                viol.append(f"{s}/{lang}: schema missing ItemList/FAQPage")
            il = next((g for g in graph if g.get("@type") == "ItemList"), {})
            if len(il.get("itemListElement", [])) < 3:
                viol.append(f"{s}/{lang}: ItemList <3 entries")

    print(f"gate_intent_hubs: {len(hubs)} hub(s), "
          f"{sum(len(h.get('members', [])) for h in hubs)} members, {len(LANGS)} locales")
    if viol:
        print(f"::error::{len(viol)} intent-hub violation(s):")
        for v in viol:
            print(f"    ✗ {v}")
        sys.exit(1)
    print("✓ registry-driven; ≥3 members each; all locales render; schema valid")




# ═══════════════════════════════════════════════════════════════════════════
# HANDOFF-intentpages — compiled-page rules (§6)
#   1. every member slug exists + published; zero orphan cards
#   2. superlative title (meilleur/best/top/…) ⇒ criteria_note rendered
#   3. determinism: rendered ItemList == selector output (no hand-inserted lieu)
#   4. min_items ≥ 6 or the page must NOT exist
#   5. protected placements untouched — proven by gate_protected_placements,
#      not re-checked here (single authority)
# ═══════════════════════════════════════════════════════════════════════════
SUPERLATIVE = re.compile(r"meilleur|plus (belle|beau|beaux|belles)|\bbest\b|\btop\b|beste|migliori|mejores", re.I)


def check_intent_pages(viol):
    import build_intent_hubs as B
    membership, fiches = B.compute_membership()
    for e in membership.values():
        built_langs = [l for l in e["title"] if e["lead"].get(l) and e["criteria_note"].get(l)]
        for lang in built_langs:
            sub = e["sub"].get(lang) or e["sub"]["fr"]
            pfx = B._qf_prefix(lang)
            p = os.path.join(ROOT, pfx, sub, "index.html") if lang == "fr" \
                else os.path.join(ROOT, lang, pfx, sub, "index.html")
            if len(e["members"]) < 6:                                   # rule 4
                if os.path.exists(p):
                    viol.append(f"{e['id']}/{lang}: <6 members but page exists")
                continue
            if not os.path.exists(p):
                viol.append(f"{e['id']}/{lang}: page missing"); continue
            html = open(p, encoding="utf-8").read()
            for s in e["members"]:                                      # rule 1
                f = fiches.get(s)
                if not f or f.get("status") != "published":
                    viol.append(f"{e['id']}: member {s} missing/unpublished")
            if SUPERLATIVE.search(e["title"][lang]):                    # rule 2
                import html as _h
                note = e["criteria_note"][lang]
                # the builder emits esc(note) == html.escape(note, quote=True)
                if _h.escape(note, quote=True) not in html and note not in html:
                    viol.append(f"{e['id']}/{lang}: superlative title without rendered criteria_note")
            m = re.search(r'"itemListElement":\s*(\[.*?\])', html, re.S)  # rule 3
            if m:
                try:
                    urls = [it["url"] for it in json.loads(m.group(1))]
                    want = [B.url_for(s, lang) + "/" for s in e["members"]]
                    if urls != want:
                        viol.append(f"{e['id']}/{lang}: ItemList != selector output (determinism)")
                except Exception:
                    viol.append(f"{e['id']}/{lang}: ItemList unparsable")
            else:
                viol.append(f"{e['id']}/{lang}: no ItemList")


_orig_main = main


def main():
    viol = []
    check_intent_pages(viol)
    if viol:
        print(f"::error::{len(viol)} intent-PAGE violation(s):")
        for v in viol:
            print(f"    ✗ {v}")
        sys.exit(1)
    print("✓ intent pages: members published, criteria law, determinism, min_items")
    _orig_main()


if __name__ == "__main__":
    main()
