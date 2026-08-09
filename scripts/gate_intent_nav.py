#!/usr/bin/env python3
"""gate_intent_nav.py — outbound-navigation guard for the intent layer.

Every intent page (Class A curated hubs + Class B compiled pages), in every
locale it ships, must be escapable: sticky header + home link, a visible
breadcrumb, BreadcrumbList JSON-LD, a "keep exploring" block with sibling
links, at least one link back up to a hub/que-faire (anti-sink), and a linked
footer whose copyright is byte-exact. RTL locales carry dir="rtl". The injected
reachability blocks on category hubs must sit ABOVE the footer, not below it.

Reads the rendered tree (run after build_all). Exit 1 on any violation.
"""
import glob
import json
import os
import re
import siteconfig  # HANDOFF-73 phase 4: per-site domain
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import locales  # noqa: E402
import build_intent_hubs as B  # noqa: E402

COPYRIGHT = ("© 2026 · Bleu canard édition · Edmaster &amp; Claudius · "
             "Tous droits réservés 🦆")
LTR_GLYPHS = ("›", "‹")   # crumb separators must live in CSS, not HTML text


def _class_a_pages():
    """(label, lang, path) for every curated hub page (PROSE locales)."""
    hubs = json.loads(open(B.REGISTRY, encoding="utf-8").read())
    for lang in locales.PROSE:
        for h in hubs:
            slug = h["slug"]
            path = (os.path.join(ROOT, f"{slug}.html") if lang == "fr"
                    else os.path.join(ROOT, lang, f"{slug}.html"))
            yield (f"A:{slug}", lang, path)


def _class_b_pages():
    """(label, lang, path) for every compiled page in each built locale."""
    membership, _ = B.compute_membership()
    for e in membership.values():
        if len(e["members"]) < 6:
            continue
        built = [l for l in e["title"] if e["lead"].get(l) and e["criteria_note"].get(l)]
        for lang in built:
            sub = e["sub"].get(lang) or e["sub"]["fr"]
            pfx = B._qf_prefix(lang)
            path = (os.path.join(ROOT, pfx, sub, "index.html") if lang == "fr"
                    else os.path.join(ROOT, lang, pfx, sub, "index.html"))
            yield (f"B:{e['id']}", lang, path)


def _anchors(fragment):
    return re.findall(r"<a\b[^>]*>", fragment)


def _slice(html, start_pat, end_tag):
    m = re.search(start_pat, html)
    if not m:
        return ""
    end = html.find(end_tag, m.end())
    return html[m.start(): end if end != -1 else len(html)]


def check_page(label, lang, path, viol):
    if not os.path.exists(path):
        viol.append(f"{label} [{lang}]: page missing at {os.path.relpath(path, ROOT)}")
        return
    html = open(path, encoding="utf-8").read()
    tag = f"{label} [{lang}]"

    # 1. sticky header + home link
    if 'class="topbar"' not in html:
        viol.append(f"{tag}: no <header class=\"topbar\">")
    home = B._home_url(lang)
    if f'href="{home}"' not in html:
        viol.append(f"{tag}: topbar missing home link {home}")

    # 2. visible breadcrumb: >=2 anchors, last crumb aria-current
    crumbs = _slice(html, r'<nav class="crumbs"', "</nav>")
    if not crumbs:
        viol.append(f"{tag}: no <nav class=\"crumbs\">")
    else:
        if len(_anchors(crumbs)) < 2:
            viol.append(f"{tag}: breadcrumb has <2 anchors")
        if 'aria-current="page"' not in crumbs:
            viol.append(f"{tag}: breadcrumb leaf missing aria-current")

    # 3. BreadcrumbList JSON-LD, >=3 itemListElement
    bc_ok = False
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            data = json.loads(m.group(1))
        except Exception:
            continue
        graph = data.get("@graph", [data]) if isinstance(data, dict) else data
        for node in graph:
            if isinstance(node, dict) and node.get("@type") == "BreadcrumbList":
                if len(node.get("itemListElement", [])) >= 3:
                    bc_ok = True
    if not bc_ok:
        viol.append(f"{tag}: no BreadcrumbList JSON-LD with >=3 items")

    # 4. keepgoing block, >=3 internal anchors
    keep = _slice(html, r'<section class="keepgoing"', "</section>")
    if not keep:
        viol.append(f"{tag}: no <section class=\"keepgoing\">")
    elif len(_anchors(keep)) < 3:
        viol.append(f"{tag}: keepgoing has <3 anchors")

    # 5. anti-sink: >=1 link to a category hub or que-faire
    qf = B._qf_index_url(lang)
    hub_link = (f'href="{qf}"' in html
                or bool(re.search(r'href="' + siteconfig.SITE_URL_RE + r'/(?:[a-z]{2}/)?[a-z-]+/"', keep)))
    if not hub_link:
        viol.append(f"{tag}: anti-sink — no link to a hub or que-faire")

    # 6. linked footer: >=3 links + copyright byte-exact
    foot = _slice(html, r'<footer class="site"', "</footer>")
    if not foot:
        viol.append(f"{tag}: no <footer class=\"site\">")
    elif len(_anchors(foot)) < 3:
        viol.append(f"{tag}: footer has <3 links")
    if COPYRIGHT not in html:
        viol.append(f"{tag}: copyright string not byte-exact")

    # 7. RTL locales: dir=rtl + no hardcoded LTR crumb glyph in the crumb markup
    if locales.DIR.get(lang) == "rtl":
        if 'dir="rtl"' not in html:
            viol.append(f"{tag}: RTL locale missing dir=\"rtl\"")
        if any(g in crumbs for g in LTR_GLYPHS):
            viol.append(f"{tag}: RTL crumb carries a hardcoded LTR separator glyph")


def check_token_completeness(viol):
    """No half-shipped language: every nav/footer string covers all 12."""
    for name, d in (("NAV_UI", B.NAV_UI), ("FOOTER_UI", B.FOOTER_UI)):
        for key, val in d.items():
            missing = [l for l in locales.VISIBLE if not val.get(l)]
            if missing:
                viol.append(f"{name}[{key}] missing locales: {missing}")


def _hub_path(slug, lang):
    return (os.path.join(ROOT, slug, "index.html") if lang == "fr"
            else os.path.join(ROOT, lang, slug, "index.html"))


def _qf_path(lang):
    pfx = B._qf_prefix(lang)
    return (os.path.join(ROOT, pfx, "index.html") if lang == "fr"
            else os.path.join(ROOT, lang, pfx, "index.html"))


def check_hub_placement(viol):
    """Blocks the intent injectors write must sit ABOVE the footer. Scoped to
    the exact pages the injectors target (not every index.html): stale
    below-footer blocks on facts-lang category hubs / commune pages are a
    separate pre-existing layer (FIX C coverage), out of this guard's scope."""
    hubs = json.loads(open(B.REGISTRY, encoding="utf-8").read())
    cats = {h["category_hub"] for h in hubs}
    membership, _ = B.compute_membership()
    built_any = sorted({l for e in membership.values() for l in e["title"]
                        if len(e["members"]) >= 6})
    targets = []
    # inject_category_links — PROSE langs × category hubs (its actual loop)
    for lang in locales.PROSE:
        for cat in cats:
            slug = (B.hub_locale_map(cat).get(lang) or cat) if lang != "fr" else cat
            targets.append((B.MARK_A, _hub_path(slug, lang)))
    # _inject_qf_links — every built lang × que-faire index
    for lang in built_any:
        targets.append((B.MARK2_A, _qf_path(lang)))
    # _inject_hub_bestof — built langs × hub_anchor hubs
    for e in membership.values():
        if len(e["members"]) < 6 or not e.get("hub_anchor"):
            continue
        for lang in [l for l in e["title"] if e["lead"].get(l) and e["criteria_note"].get(l)]:
            targets.append((B.MARK3_A, _hub_path(B._hub_dir(e["hub_anchor"], lang), lang)))
    # _inject_hub_intent (FIX C) — built langs × HUB_INTENT_MAP hubs
    for lang in built_any:
        for hub_dir in B.HUB_INTENT_MAP:
            targets.append((B.MARK4_A, _hub_path(B._hub_dir(hub_dir, lang), lang)))
    for mk, path in targets:
        if not os.path.exists(path):
            continue
        html = open(path, encoding="utf-8").read()
        i = html.find(mk)
        if i == -1:
            continue
        foot = html.rfind("<footer")
        if foot != -1 and i > foot:
            viol.append(f"placement: {os.path.relpath(path, ROOT)} has {mk} AFTER <footer>")


def main():
    viol = []
    check_token_completeness(viol)
    n = 0
    for label, lang, path in list(_class_a_pages()) + list(_class_b_pages()):
        n += 1
        check_page(label, lang, path, viol)
    check_hub_placement(viol)
    print(f"gate_intent_nav: {n} intent page(s) checked across published locales")
    if not viol:
        print("✓ every intent page escapes: topbar+breadcrumb+keepgoing+footer, "
              "RTL clean, no block below the footer")
        sys.exit(0)
    print(f"::error::{len(viol)} intent-nav violation(s):")
    for v in viol[:60]:
        print(f"    ✗ {v}")
    sys.exit(1)


if __name__ == "__main__":
    main()
