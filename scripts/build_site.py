#!/usr/bin/env python3
"""Build the publishable _site/ directory from the repo root.

JOB 2 — stop publishing the repo. Netlify.toml is repointed at _site/ instead
of the repo root. This script:

  1. Wipes and recreates _site/.
  2. Copies allowlisted paths (public HTML, locale trees, hub dirs, static
     assets, public manifests, AI discovery files, studio + DT importer).
  3. EXCLUDES scripts/, reports/, audit-report.md, dt-candidates working
     files NOT linked by studio, .zip, .csv, _README.txt, apply-images.py,
     __pycache__, .git*, .github/, anything starting with `_` (other than
     _site/, _headers, _redirects, _README.txt — README is excluded).
  4. Strips `research_log` from every Json/ + content/ + api/lieux.json
     export so internal verification notes don't ship.
  5. Patches studio.html with <meta name="robots" content="noindex,nofollow">
     and a banner.
  6. Patches robots.txt with Disallow rules for /studio*, /dt-candidates.json,
     /studio-dt-importer.js (defence-in-depth alongside noindex).

Idempotent: two consecutive runs produce identical _site/.
"""
import json
import siteconfig  # HANDOFF-73: per-site identity
import re
import shutil
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import locales  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
SITE = REPO / "_site"
LOCALES = locales.VISIBLE_SECONDARY  # isolation-ok: deploy-copy roster — pl's rendered tree must reach _site/

# Paths to copy verbatim from REPO into SITE
COPY_DIRS = [
    "Json",            # stripped of research_log below
    "api",             # stripped of research_log
    "content",         # md mirrors — review for research_log mentions
    ".well-known",
] + list(LOCALES)

# Hub directories (rendered listings) + the image tree.
# `img/` holds the canonical generic store (`img/generique/`) and per-lieu
# heros (`img/<hub>/<slug>-hero.{jpg,webp}`) — every local `<img>`/`<picture>`
# srcset on the site points into this tree. Must be copied into _site/ or
# every local hero 404s live.
HUB_DIRS = [
    "cascades", "chateaux", "musees", "points-de-vue", "sentiers",
    "telecabines", "stations-de-ski", "voies-vertes", "lacs-plages",
    "bases-de-loisirs", "baignade-nautisme", "parcs-jardins", "que-faire",
    "sensations-plein-air", "sorties-detente", "sport-jeux",
    "img",
]

# Root-level files to copy verbatim (filename match)
COPY_ROOT_FILES_GLOB = [
    "*.html",                        # fiche pages + studio + landing + hub index.html
    "*.css",
    "*.js",                          # studio-*.js, script bundles
    "*.png", "*.jpg", "*.jpeg",
    "*.svg", "*.ico", "*.webmanifest",
    "favicon*",
    "logo*",
    "generique-*",
    "og-image*",
    "apple-touch-icon*", "android-chrome-*",
    "browserconfig.xml",
    "BingSiteAuth.xml",
    "site.webmanifest",
    "sitemap.xml",
    "llms.txt", "llms-full.txt", "robots.txt", "robots-ai.txt",
    "catalog-index.json", "lieux.json", "photo-credits.json",
    "_headers", "_redirects",        # Netlify control files
    "a100618930894cd2bc77bacba5002b64.txt",  # Indeed/Bing verification
    "e8aa76cdaf4348d390571ff658e649ca.txt",  # IndexNow key (HANDOFF-33; public by protocol)
]

# Explicit exclude list — never copy these even if they match
DENY = {
    "scripts", "reports", "__pycache__", ".git", ".github",
    "audit-report.md", "_README.txt", "apply-images.py",
    "_site", "netlify.toml",
    "dt-flow-261672",                # raw DataTourisme flow dump if present
    "Json.bak", "node_modules",
    "report.csv", "email_queue.csv",
    "translations",                  # JOB 7 translation payloads (intermediate)
    "incoming-generics",             # staging folder for user-sourced générique pics
    "incoming-benedicte",            # Bénédicte originals + sources/ — never public
    # JOB 11: Studio is dev-only. Lives in repo, never deployed.
    "studio.html",
    "studio-consts.js",
    "studio-dt-importer.js",
    "studio-editor.js",
    "studio-enricher.js",
    "studio-phototheque.js",
    "studio-render.js",
    "studio-templates.js",
    "dt-candidates.json",
}
DENY_GLOB = [
    "*.zip", "*.tar.gz", "*.tgz",
    "*.csv",
    ".env*",
    "*.bak", "*.tmp",
    # Single-character filenames are accidental artefacts — never publish.
    "?",
]


def is_denied(name):
    if name in DENY:
        return True
    for pat in DENY_GLOB:
        if Path(name).match(pat):
            return True
    return False


def copy_file_with_research_log_strip(src, dst):
    """Copy a Json/<slug>.json file. JOB 2: strips research_log; JOB 6: skip
    draft fiches entirely (caller signal via return False)."""
    d = json.loads(src.read_text(encoding="utf-8"))
    # 'unverified' (source-audit) is excluded from _site exactly like draft.
    if d.get("status") in ("draft", "unverified"):
        return False
    if "research_log" in d:
        d.pop("research_log", None)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    return True


def copy_lieux_index_strip(src, dst):
    """Strip research_log from the API/catalog index if it's an array of fiches."""
    d = json.loads(src.read_text(encoding="utf-8"))
    def _strip(obj):
        if isinstance(obj, dict):
            obj.pop("research_log", None)
            for v in obj.values():
                _strip(v)
        elif isinstance(obj, list):
            for v in obj:
                _strip(v)
    _strip(d)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")


def copy_md_strip_research_log(src, dst):
    """Markdown fiche mirrors: remove any Research log section if present.
    JOB 6: skip if the corresponding fiche is draft."""
    slug = src.stem
    jp = REPO / "Json" / f"{slug}.json"
    if jp.exists():
        try:
            d = json.loads(jp.read_text(encoding="utf-8"))
            if d.get("status") in ("draft", "unverified"):
                return
        except Exception:
            pass
    text = src.read_text(encoding="utf-8")
    text = re.sub(r"## Research log.*?(?=\n## |\Z)", "", text, flags=re.DOTALL)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text, encoding="utf-8")


NOINDEX_BLOCK = (
    '<meta name="robots" content="noindex,nofollow">\n'
    '<meta name="googlebot" content="noindex,nofollow">\n'
)

def patch_studio_html(path):
    """Inject noindex meta into <head> of studio.html (idempotent)."""
    h = path.read_text(encoding="utf-8")
    if 'name="robots" content="noindex' in h:
        return
    h = h.replace("<head>", "<head>\n" + NOINDEX_BLOCK, 1)
    path.write_text(h, encoding="utf-8")


ROBOTS_BLOCK = """
# Studio (internal editor + DataTourisme importer) — not for crawl/index
Disallow: /studio
Disallow: /studio.html
Disallow: /studio-editor.js
Disallow: /studio-enricher.js
Disallow: /studio-phototheque.js
Disallow: /studio-dt-importer.js
Disallow: /studio-consts.js
Disallow: /studio-render.js
Disallow: /studio-templates.js
Disallow: /dt-candidates.json
"""

def filter_sitemap(path, site_root):
    """JOB 6: drop <url> blocks whose <loc> points to a file no longer in
    _site/ (e.g. fiche demoted to status=draft). Idempotent."""
    txt = path.read_text(encoding="utf-8")
    blocks = re.findall(r"<url>.*?</url>", txt, re.DOTALL)
    kept_blocks = []
    dropped = 0
    for blk in blocks:
        m = re.search(r"<loc>(" + siteconfig.SITE_URL_RE + r"/[^<]*)</loc>", blk)
        if not m:
            kept_blocks.append(blk); continue
        url = m.group(1)
        p = url[len(siteconfig.BASE_URL + "/"):]
        if not p:
            target = site_root / "index.html"
        elif p.endswith("/"):
            target = site_root / (p + "index.html")
        else:
            target = site_root / (p + ".html")
        if target.exists():
            kept_blocks.append(blk)
        else:
            dropped += 1
    if dropped == 0:
        return 0
    # Rebuild file: keep <?xml…?> and <urlset…> declaration, replace inner
    head_m = re.search(r"(<\?xml.*?\?>\s*<urlset[^>]*>)", txt, re.DOTALL)
    head = head_m.group(1) if head_m else '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    new = head + "\n" + "\n".join("  " + b for b in kept_blocks) + "\n</urlset>\n"
    path.write_text(new, encoding="utf-8")
    return dropped


def patch_robots_txt(path):
    """Append Disallow rules for the Studio + DT importer (idempotent)."""
    txt = path.read_text(encoding="utf-8")
    if "Disallow: /studio.html" in txt:
        return
    # Insert the new block immediately after the existing Disallow group
    insertion_marker = "Disallow: /merci-partenaire.html"
    if insertion_marker in txt:
        txt = txt.replace(
            insertion_marker,
            insertion_marker + "\n" + ROBOTS_BLOCK.rstrip() + "\n",
            1
        )
    else:
        txt = txt.rstrip() + "\n" + ROBOTS_BLOCK
    path.write_text(txt, encoding="utf-8")


def copy_dir(src, dst, json_strip=False, md_strip=False):
    """Copy a directory tree, applying research_log strip where requested."""
    for p in src.rglob("*"):
        if is_denied(p.name):
            continue
        rel = p.relative_to(src)
        out = dst / rel
        if p.is_dir():
            out.mkdir(parents=True, exist_ok=True)
            continue
        if json_strip and p.suffix == ".json":
            copy_file_with_research_log_strip(p, out)
        elif md_strip and p.suffix == ".md":
            copy_md_strip_research_log(p, out)
        else:
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, out)


def main():
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True)

    print("Copying root files...")
    seen = set()
    for pattern in COPY_ROOT_FILES_GLOB:
        for src in sorted(REPO.glob(pattern)):
            if not src.is_file() or is_denied(src.name) or src.name in seen:
                continue
            seen.add(src.name)
            shutil.copy2(src, SITE / src.name)

    print("Copying hub directories...")
    for d in HUB_DIRS:
        src = REPO / d
        if not src.exists():
            continue
        dst = SITE / d
        dst.mkdir(parents=True, exist_ok=True)
        for p in src.rglob("*"):
            if is_denied(p.name): continue
            if p.is_file():
                rel = p.relative_to(src)
                (dst / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dst / rel)

    # FR commune pages: build_communes.py writes them to repo ROOT
    # (bellevaux/index.html, …) but they're in neither COPY_DIRS nor HUB_DIRS,
    # so they never reached _site/ → every FR "À <commune>" link 404'd live
    # (the EN/DE/… copies deploy via the recursive LOCALES copy). Derive the
    # list from the commune layer so new communes auto-publish and this can't
    # drift again — same omission class as the img/ one guarded below.
    print("Copying FR commune pages...")
    commune_slugs = [c["slug"] for c in json.loads(
        (REPO / "data" / "commune-layer.json").read_text(encoding="utf-8"))["communes"]]
    n_comm = 0
    for slug in commune_slugs:
        src = REPO / slug
        if (src / "index.html").exists():
            copy_dir(src, SITE / slug)
            n_comm += 1
    print(f"  copied {n_comm} commune dirs")

    print("Copying Json/ with research_log stripped...")
    copy_dir(REPO / "Json", SITE / "Json", json_strip=True)

    print("Copying api/ with research_log stripped...")
    api_src = REPO / "api"
    if api_src.exists():
        for p in api_src.rglob("*"):
            if is_denied(p.name) or not p.is_file(): continue
            rel = p.relative_to(api_src)
            out = SITE / "api" / rel
            if p.suffix == ".json":
                copy_lieux_index_strip(p, out)
            else:
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, out)

    print("Copying content/ markdown mirrors with research_log scrubbed...")
    copy_dir(REPO / "content", SITE / "content", md_strip=True)

    print("Copying .well-known/...")
    copy_dir(REPO / ".well-known", SITE / ".well-known")

    # Runtime client JS is referenced as /scripts/<file> by the pages but the
    # scripts/ dir is otherwise excluded from the publish. Allowlist-copy the
    # few files that must ship (l74sort: homepage sort/near; nearme: sitewide
    # proximity component).
    print("Copying runtime scripts to _site/scripts/...")
    RUNTIME_JS = ["l74sort.js", "nearme.js", "duck.js"]
    sdst = SITE / "scripts"
    sdst.mkdir(parents=True, exist_ok=True)
    for _name in RUNTIME_JS:
        _sp = REPO / "scripts" / _name
        if _sp.exists():
            # Runtime JS cannot import siteconfig, so the origin is a
            # placeholder in source and is substituted here at publish time.
            _txt = _sp.read_text(encoding="utf-8")
            _n = _txt.count("__SITE_ORIGIN__")
            if _n:
                _txt = _txt.replace("__SITE_ORIGIN__", siteconfig.BASE_URL)
                (sdst / _name).write_text(_txt, encoding="utf-8")
                shutil.copystat(_sp, sdst / _name)
            else:
                shutil.copy2(_sp, sdst / _name)
            print(f"  + scripts/{_name}" + (f" (origin substituted x{_n})" if _n else ""))

    print("Copying locale trees (en/de/it/es/nl/pl)...")
    for L in LOCALES:
        src = REPO / L
        if not src.exists(): continue
        copy_dir(src, SITE / L)

    # Staged-indexable Latin pilot (HANDOFF-11): deploy pl/pt/cs so their
    # in-sitemap URLs resolve. They carry self-canonical + index,follow but are
    # NOT in any hreflang cluster. RTL (ar/he) stay undeployed (render-held).
    print("Copying staged-indexable pilot trees (pl/pt/cs)...")
    for L in locales.STAGED_INDEXABLE:
        src = REPO / L
        if not src.exists(): continue
        copy_dir(src, SITE / L)

    print("Patching _site/studio.html with noindex...")
    studio = SITE / "studio.html"
    if studio.exists():
        patch_studio_html(studio)

    print("Patching _site/robots.txt with Studio Disallow rules...")
    robots = SITE / "robots.txt"
    if robots.exists():
        patch_robots_txt(robots)

    print("Filtering _site/sitemap.xml (drop URLs whose target no longer exists)...")
    sm = SITE / "sitemap.xml"
    if sm.exists():
        dropped = filter_sitemap(sm, SITE)
        if dropped:
            print(f"  dropped {dropped} stale <url> entries")

    # Regression guard — fail loudly if the image tree didn't get copied.
    # (Previously a quiet HUB_DIRS omission shipped 575 broken local heros live.)
    assert (SITE / "img" / "generique").is_dir(), \
        "img/ not published into _site/ — check HUB_DIRS in build_site.py"

    # Final stats
    total = sum(1 for _ in SITE.rglob("*") if _.is_file())
    size_mb = sum(p.stat().st_size for p in SITE.rglob("*") if p.is_file()) / (1024 * 1024)
    print(f"\n_site/ contains {total} files, {size_mb:.1f} MB")


if __name__ == "__main__":
    main()
