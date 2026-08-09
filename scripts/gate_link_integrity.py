#!/usr/bin/env python3
"""gate_link_integrity.py — fail if any internal link in _site/ 404s.

The whole bug class behind "575 broken local heros" and "32 FR commune pages
dead": a page links to /<path> but build_site never copied <path> into _site/.
Invisible until a user (or Google) clicks it. This gate parses the ACTUALLY
SERVED tree and asserts every internal href/src resolves to a real file (or a
_redirects rule), so an allowlist omission turns the build red instead of
shipping dead links.

Resolution (mirrors the clean-URL scheme):
  /                     -> _site/index.html
  /x/   (trailing /)    -> _site/x/index.html
  /x.ext (has ext)      -> _site/x.ext
  /x    (clean, no ext) -> _site/x.html  OR  _site/x/index.html
A target also counts as valid if it matches a source in _redirects.

Skips: external hosts, mailto:/tel:/#/data:/javascript:, protocol-relative //.

Run after build_site. Read-only. Exit 1 on any broken internal link.

Usage:
    python3 scripts/gate_link_integrity.py
"""
import os
import siteconfig  # HANDOFF-73: per-site identity
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import locales  # noqa: E402
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "_site")
HOST = siteconfig.DOMAIN

LINK_RE = re.compile(r'(?:href|src)\s*=\s*"([^"]+)"', re.I)


def load_allowlist():
    """Known pre-existing broken internal targets (legal/footer/utility i18n
    debt) — allowed so the gate can ship and catch NEW (commune/img-class)
    regressions without blocking on a separate cleanup. One path per line."""
    allow = set()
    ap = os.path.join(ROOT, "reports", "link-integrity-allowlist.txt")
    if os.path.exists(ap):
        for line in open(ap, encoding="utf-8"):
            line = line.split("#", 1)[0].strip()
            if line:
                allow.add(line)
    return allow


def load_redirect_sources():
    srcs = set()
    rp = os.path.join(ROOT, "_redirects")
    if os.path.exists(rp):
        for line in open(rp, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if parts:
                srcs.add(parts[0].rstrip("/") or "/")
                # also the splat/base form
                srcs.add(parts[0].split("*")[0].rstrip("/") or "/")
    return srcs


def to_path(url):
    """Internal URL -> normalized path, or None if external/non-navigational."""
    u = url.strip()
    if not u or u[0] == "#":
        return None
    if u.startswith(("mailto:", "tel:", "data:", "javascript:", "//")):
        return None
    if u.startswith("http://") or u.startswith("https://"):
        m = re.match(r"https?://([^/]+)(/.*)?$", u)
        if not m or m.group(1).replace("www.", "") != HOST:
            return None  # external
        u = m.group(2) or "/"
    if not u.startswith("/"):
        return None  # relative asset (rare); skip
    return u.split("#")[0].split("?")[0]


def candidates(path):
    p = path
    if p == "/" or p == "":
        return [os.path.join(SITE, "index.html")]
    rel = p.lstrip("/")
    if rel.endswith("/"):
        return [os.path.join(SITE, rel, "index.html")]
    last = rel.rsplit("/", 1)[-1]
    if "." in last:
        return [os.path.join(SITE, rel)]
    return [os.path.join(SITE, rel + ".html"),
            os.path.join(SITE, rel, "index.html")]


def check_carousels():
    """Tripwire: every published fiche page in _site must carry the proximity
    carousel (id="related" + ≥1 card). Catches a rebuild that drops it — the
    exact regression that wiped update_related.py's output for good."""
    import glob
    pub = []
    for fp in glob.glob(os.path.join(ROOT, "Json", "*.json")):
        try:
            d = json.loads(open(fp, encoding="utf-8").read())
        except Exception:
            continue
        if d.get("status") == "published":
            pub.append(d["slug"])
    bad = []
    for slug in pub:
        for pre in ("",) + locales.PROSE_SECONDARY:
            rel = f"{slug}.html" if not pre else f"{pre}/{slug}.html"
            fp = os.path.join(SITE, rel)
            if not os.path.exists(fp):
                bad.append(rel + " (missing)")
                continue
            html = open(fp, encoding="utf-8", errors="ignore").read()
            if 'id="related"' not in html or '<article class="card"' not in html:
                bad.append(rel + " (no carousel)")
    return bad


def check_homepage_hubs():
    """Every hub must be linked from its OWN locale homepage (footer or body).
    Catches a strip/refactor that orphans a hub from the homepage — the
    que-faire / voies-vertes regression class — at PR time."""
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from build_hubs import ALL_BASE_HUBS, hub_locale_map  # noqa: E402
    bad = []
    for lang in locales.PROSE:
        rel = "index.html" if lang == "fr" else f"{lang}/index.html"
        home = os.path.join(SITE, rel)
        if not os.path.exists(home):
            continue
        html = open(home, encoding="utf-8", errors="ignore").read()
        prefix = "" if lang == "fr" else f"/{lang}"
        for hub in ALL_BASE_HUBS:
            slug = hub_locale_map(hub).get(lang) or hub
            hub_file = os.path.join(SITE, *(([lang] if lang != "fr" else []) + [slug, "index.html"]))
            if not os.path.exists(hub_file):
                continue   # hub not built for this locale → not expected on homepage
            if f"{siteconfig.BASE_URL}{prefix}/{slug}/" not in html:
                bad.append(f"{lang} homepage does not link hub /{slug}/")
    return bad


def main():
    if not os.path.isdir(SITE):
        print("::error::_site/ not built — run build_site.py first")
        sys.exit(1)
    redirects = load_redirect_sources()
    allow = load_allowlist()

    missing = defaultdict(list)   # target_path -> [pages linking it]
    checked = 0
    pages = 0
    for dirpath, _, files in os.walk(SITE):
        for fn in files:
            if not fn.endswith(".html"):
                continue
            pages += 1
            fp = os.path.join(dirpath, fn)
            page_rel = os.path.relpath(fp, SITE)
            html = open(fp, encoding="utf-8", errors="ignore").read()
            seen = set()
            for raw in LINK_RE.findall(html):
                path = to_path(raw)
                if path is None or path in seen:
                    continue
                seen.add(path)
                checked += 1
                if path.rstrip("/") in redirects or (path.rstrip("/") or "/") in redirects:
                    continue
                if path in allow or path.rstrip("/") in allow:
                    continue
                if not any(os.path.exists(c) for c in candidates(path)):
                    missing[path].append(page_rel)

    bad_carousels = check_carousels()
    bad_hubs = check_homepage_hubs()

    print(f"gate_link_integrity: {pages} pages, {checked} internal links checked; "
          f"carousel + homepage-hub tripwires")
    if not missing and not bad_carousels and not bad_hubs:
        print("✓ links resolve; every fiche has its carousel; every hub linked from its homepage")
        sys.exit(0)

    if bad_hubs:
        print(f"::error::{len(bad_hubs)} hub(s) orphaned from their locale homepage:")
        for b in bad_hubs:
            print(f"    ✗ {b}")
        if not missing and not bad_carousels:
            sys.exit(1)

    if bad_carousels:
        print(f"::error::{len(bad_carousels)} fiche page(s) missing the proximity "
              f'carousel (id="related" + cards) — a rebuild dropped it:')
        for b in bad_carousels[:20]:
            print(f"    ✗ {b}")
        if len(bad_carousels) > 20:
            print(f"    … and {len(bad_carousels) - 20} more")
        if not missing:
            sys.exit(1)

    total = sum(len(v) for v in missing.values())
    print(f"::error::{len(missing)} broken internal target(s) across {total} link(s):")
    for tgt, pglist in sorted(missing.items(), key=lambda kv: -len(kv[1]))[:40]:
        ex = ", ".join(sorted(set(pglist))[:3])
        print(f"    ✗ {tgt}   ({len(pglist)} pages, e.g. {ex})")
    if len(missing) > 40:
        print(f"    … and {len(missing) - 40} more targets")
    print("\nFix the build_site copy allowlist (or the link). This is the "
          "img-404 / commune-404 bug class.")
    sys.exit(1)


if __name__ == "__main__":
    main()
