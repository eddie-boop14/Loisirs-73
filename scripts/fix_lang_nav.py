#!/usr/bin/env python3
"""fix_lang_nav.py — make the header language picker and the footer "Langue"
list read the VISIBLE roster on every page whose language nav is frozen chrome.

THE PROBLEM
-----------
Three surfaces emit the language switcher:
  - fiches   → build_lieu_page, iterates the visible roster  (correct, pl present)
  - communes → build_communes,  iterates the visible roster  (correct after fix)
  - hubs + locale homepages → NOBODY. The picker/footer were baked once when the
    site had six languages and no builder rewrites them. build_hubs splices
    <main>; fix_hub_chrome localizes filter/breadcrumb *strings*; neither touches
    the <div class="lang-menu"> or the footer <ul> under <h*>Langue</h*>. So when
    pl flipped to published its endonym never appeared in those lists — and the
    FR homepage footer was additionally missing Nederlands (an older drop).

THE FIX (one principle: the picker + footer read the roster)
-----------------------------------------------------------
For every page that carries a language picker, insert any visible-roster
language that the page's own <link rel="alternate" hreflang> head block already
vouches for but the picker / footer list does not yet show. We *insert* (never
regenerate) so the existing six anchors stay byte-for-byte identical — the live
trees change only by *added* endonym lines, which is the acceptance bar. The
per-page target URL is the hreflang alternate itself, so every added entry
resolves (zero blind /xx/ 404s). Idempotent: a language already listed is
skipped, so re-runs and already-correct pages (fiches, communes) are no-ops.

When the five staged/held languages publish, fix_hreflang_sitemap adds their
alternates and this normalizer lists them automatically — twelve languages in
the nav for free.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import locales  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# Facts-language trees (pl, pt, cs, ar, he, ja) are owned by build_fulltree_lang
# and carry their own roster-complete picker — never touched here.
FACTS_DIRS = set(locales.ALL_SUBDIR_LANGS) - set(locales.PROSE_SECONDARY)
# Non-page trees: source, exports, build output, reports.
SKIP_TOP = {"_site", "scripts", "reports", "Json", "api", "content",
            ".well-known", ".git", "data", "node_modules", "img"}

ALT_RE = re.compile(r'<link rel="alternate" hreflang="([a-z-]+)" href="([^"]+)"')
ANCHOR_RE = re.compile(r'<a\b[^>]*?\bhreflang="([a-z-]+)"[^>]*?>.*?</a>', re.S)
LI_RE = re.compile(r'<li>\s*<a\b[^>]*?\bhreflang="([a-z-]+)"[^>]*?>.*?</a>\s*</li>', re.S)
PICKER_RE = re.compile(r'(<div class="lang-menu">)(.*?)(</div>)', re.S)
FOOTER_RE = re.compile(r'(<(h[34])>\s*Langue\s*</\2>\s*<ul>)(.*?)(</ul>)', re.S)


def alt_map(html):
    """{lang: url} from the head hreflang alternates (x-default excluded)."""
    return {l: u for l, u in ALT_RE.findall(html) if l != "x-default"}


def _missing(present, altmap):
    """VISIBLE languages, in roster order, that have an alternate URL but are
    not yet listed."""
    return [l for l in locales.VISIBLE  # isolation-ok: nav lists the visible roster
            if l in altmap and l not in present]


def _insert(inner, item_re, build_item, altmap):
    """Append the missing languages' items after the last existing item,
    replicating the inter-item separator so formatting matches the neighbours.
    Returns (new_inner, added_langs)."""
    items = list(item_re.finditer(inner))
    if not items:
        return inner, []
    present = [m.group(1) for m in items]
    missing = _missing(present, altmap)
    if not missing:
        return inner, []
    # Separator between existing items (e.g. "" for adjacent, "\n" for newline
    # lists). With >=2 items this is exact; fall back to none otherwise.
    sep = inner[items[0].end():items[1].start()] if len(items) >= 2 else ""
    end = items[-1].end()
    addition = "".join(sep + build_item(l, altmap[l]) for l in missing)
    return inner[:end] + addition + inner[end:], missing


def _anchor(lang, url):
    return f'<a href="{url}" hreflang="{lang}">{locales.ENDONYM[lang]}</a>'


def _li(lang, url):
    return f'<li><a href="{url}" hreflang="{lang}">{locales.ENDONYM[lang]}</a></li>'


def patch_html(html):
    """Return (new_html, added_langs_sorted_set)."""
    altmap = alt_map(html)
    if not altmap:
        return html, set()
    added = set()

    def picker_sub(m):
        new_inner, miss = _insert(m.group(2), ANCHOR_RE, _anchor, altmap)
        added.update(miss)
        return m.group(1) + new_inner + m.group(3)

    def footer_sub(m):
        new_inner, miss = _insert(m.group(3), LI_RE, _li, altmap)
        added.update(miss)
        return m.group(1) + new_inner + m.group(4)

    html = PICKER_RE.sub(picker_sub, html, count=1)
    html = FOOTER_RE.sub(footer_sub, html, count=1)
    return html, added


def iter_pages():
    """Every prose-tree HTML page (root + en/de/it/es/nl), skipping source,
    exports, build output and the facts-language trees."""
    for p in ROOT.rglob("*.html"):
        parts = p.relative_to(ROOT).parts
        if parts[0] in SKIP_TOP or parts[0] in FACTS_DIRS:
            continue
        yield p


def main():
    files = 0
    tally = {}
    for p in iter_pages():
        html = p.read_text(encoding="utf-8")
        new_html, added = patch_html(html)
        if added and new_html != html:
            p.write_text(new_html, encoding="utf-8")
            files += 1
            for l in added:
                tally[l] = tally.get(l, 0) + 1
    print(f"fix_lang_nav: {files} pages updated")
    for l in sorted(tally):
        print(f"  +{locales.ENDONYM[l]} ({l}): {tally[l]} pages")
    if not files:
        print("  (nothing to add — every picker/footer already lists the visible roster)")


if __name__ == "__main__":
    main()
