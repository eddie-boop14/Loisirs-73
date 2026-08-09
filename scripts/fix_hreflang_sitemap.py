#!/usr/bin/env python3
"""
Compute canonical hreflang blocks for every multilingual page group from
file existence (not from the existing, partly-buggy on-page blocks), then:
  --apply   normalize <link rel="alternate" hreflang> on FR + locale pages
  --sitemap rebuild sitemap.xml with xhtml:link alternates + locale URLs
Default (no flag): dry-run report + validation only.
"""
import re
import siteconfig  # HANDOFF-73: per-site identity
import sys
import glob
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import locales  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BASE = siteconfig.BASE_URL + "/"
LANGS = list(locales.VISIBLE_SECONDARY)
LINK_RE = re.compile(r'<link rel="alternate" hreflang="[^"]*" href="[^"]*">')
RUN_RE = re.compile(r'<link rel="alternate" hreflang="[^"]*" href="[^"]*">(?:\n<link rel="alternate" hreflang="[^"]*" href="[^"]*">)*')
NOIDX_RE = re.compile(r'<meta name="robots" content="[^"]*noindex')

# Sitewide head-link authority (JOB P1). Order-agnostic strip patterns + the
# stale href-first "block 2" the hubs/communes/homepage inherited by copying
# cascades' built HTML. Each block-2 / md-alt strip also eats one trailing
# newline so removals leave no blank line (keeps the pass idempotent).
CANON_ANY   = re.compile(r'<link\b[^>]*\brel=("|\')canonical\1[^>]*>')
REL_CANON   = re.compile(r'<link rel="canonical" href="[^"]*">')
MDALT_STRIP = re.compile(r'<link\b[^>]*\btype=("|\')text/markdown\1[^>]*>\n?')
B2_CANON    = re.compile(r'<link href="[^"]*" rel="canonical"\s*/?>\n?')
B2_HREFLANG = re.compile(r'<link href="[^"]*" hreflang="[^"]*" rel="alternate"\s*/?>\n?')
CONTENT = ROOT / "content"


def fr_slug_of(fr_url):
    """'…/cascades/' → 'cascades'; '…/abbaye-d-aulps' → 'abbaye-d-aulps'; BASE → ''."""
    return fr_url[len(BASE):].rstrip("/")


def normalize_head(html, self_url, hreflang_run, fr_slug, multilingual):
    """Self-referential canonical + single hreflang run + md-alt-iff-exists.
    Surgical & guarded: an already-correct page (the clean lieu pages) passes
    through byte-identical — every branch is a no-op when nothing is wrong."""
    # 1. drop the stale href-first block 2 (its canonical + duplicate hreflang).
    html = B2_CANON.sub("", html)
    html = B2_HREFLANG.sub("", html)
    # 2. exactly one rel-first self canonical.
    desired = f'<link rel="canonical" href="{self_url}">'
    rel = REL_CANON.search(html)
    if rel and len(CANON_ANY.findall(html)) == 1:
        if rel.group(0) != desired:                      # fix href in place
            html = html[:rel.start()] + desired + html[rel.end():]
    else:                                                # 0 or >1 / non-rel form
        html = CANON_ANY.sub("", html)
        m = re.search(r'<head[^>]*>', html)
        html = html[:m.end()] + "\n" + desired + html[m.end():]
    # 3. single hreflang run (multilingual groups only), in place.
    if multilingual:
        m = RUN_RE.search(html)
        if m:
            if m.group(0) != hreflang_run:
                html = html[:m.start()] + hreflang_run + html[m.end():]
        else:
            html = insert_block(html, hreflang_run)
    # 4. md-alt only if content/<fr_slug>.md exists; else drop it (never repoint).
    if not (fr_slug and (CONTENT / f"{fr_slug}.md").exists()):
        html = MDALT_STRIP.sub("", html)
    return html



def is_noindex(group):
    return bool(NOIDX_RE.search(group["pages"]["fr"][1].read_text(encoding="utf-8")))


def insert_block(html, block):
    """Insert an hreflang block into <head> at a safe anchor."""
    m = re.search(r'<meta charset="[^"]*">', html)
    if m:
        return html[:m.end()] + "\n" + block + html[m.end():]
    m = re.search(r'<head[^>]*>', html)
    if m:
        return html[:m.end()] + "\n" + block + html[m.end():]
    raise RuntimeError("no <head> anchor for hreflang insertion")


def url_to_file(url):
    p = url[len(BASE):]
    if p == "":
        return ROOT / "index.html"
    if p.endswith("/"):
        return ROOT / (p + "index.html")
    return ROOT / (p + ".html")


def link(lang, url):
    return f'<link rel="alternate" hreflang="{lang}" href="{url}">'


def _parse_alternates(html):
    """Extract {lang: href} from <link rel="alternate" hreflang=".." href=".."> tags,
    tolerating any attribute order within the tag."""
    out = {}
    for tag in re.findall(r'<link[^>]*>', html):
        if 'rel="alternate"' not in tag:
            continue
        m_lang = re.search(r'hreflang="([^"]*)"', tag)
        m_href = re.search(r'href="([^"]*)"', tag)
        if m_lang and m_href:
            out[m_lang.group(1)] = m_href.group(1)
    return out


def hub_map():
    """FR hub url -> {lang: locale hub url}, from locale hub indexes' fr-href."""
    m = {}
    for L in LANGS:
        for f in glob.glob(f"{L}/*/index.html"):
            html = Path(f).read_text(encoding="utf-8")
            d = _parse_alternates(html)
            fr = d.get("fr")
            if not fr or not fr.endswith("/"):
                continue
            self_url = BASE + f[:-len("index.html")]
            m.setdefault(fr, {})[L] = self_url
    return m


def build_groups():
    """Each group: {'fr_url':..., 'pages': {lang: (url, file)}}  (lang includes 'fr')."""
    groups = []
    # homepage
    g = {"fr_url": BASE, "pages": {"fr": (BASE, ROOT / "index.html")}}
    for L in LANGS:
        f = ROOT / L / "index.html"
        if f.exists():
            g["pages"][L] = (f"{BASE}{L}/", f)
    groups.append(g)
    # hubs
    hm = hub_map()
    for fr_url, locs in sorted(hm.items()):
        frf = url_to_file(fr_url)
        if not frf.exists():
            continue
        g = {"fr_url": fr_url, "pages": {"fr": (fr_url, frf)}}
        for L in LANGS:
            if L in locs:
                lf = url_to_file(locs[L])
                if lf.exists():
                    g["pages"][L] = (locs[L], lf)
        groups.append(g)
    # lieu pages (by slug/filename)
    for fp in sorted(glob.glob("*.html")):
        if fp in ("index.html", "404.html"):
            continue
        slug = fp[:-5]
        fr_url = BASE + slug
        g = {"fr_url": fr_url, "pages": {"fr": (fr_url, ROOT / fp)}}
        for L in LANGS:
            lf = ROOT / L / fp
            if lf.exists():
                g["pages"][L] = (f"{BASE}{L}/{slug}", lf)
        groups.append(g)
    return groups


def intent_groups():
    """Class-B intent pages: que-faire/<slug>/ and its localized-locale variants
    (e.g. en/what-to-do/<slug>/, de/was-unternehmen/<slug>/). They sit one level
    deeper than the category hubs, so the depth-1 hub_map() glob never reaches
    them — which is why all 192 were silently absent from the sitemap even though
    build_all runs build_intent_hubs BEFORE this step expressly to have them
    folded in. Each FR page already carries a full, correct hreflang cluster
    (emitted by build_intent_hubs); read it to assemble the group, keeping only
    locales whose file is actually on disk.

    Sitemap-only by design: these heads stay owned by build_intent_hubs, so they
    are added to the URL set here but NOT run through normalize_head."""
    groups = []
    for fp in sorted(glob.glob("que-faire/*/index.html")):
        alts = _parse_alternates(Path(fp).read_text(encoding="utf-8"))
        fr_url = alts.get("fr") or (BASE + fp[:-len("index.html")])
        if not url_to_file(fr_url).exists():
            continue
        g = {"fr_url": fr_url, "pages": {"fr": (fr_url, url_to_file(fr_url))}}
        for L in LANGS:
            u = alts.get(L)
            if u and url_to_file(u).exists():
                g["pages"][L] = (u, url_to_file(u))
        groups.append(g)
    return groups


def canonical_links(g):
    fr_url = g["fr_url"]
    out = [link("fr", fr_url)]
    for L in LANGS:
        if L in g["pages"]:
            out.append(link(L, g["pages"][L][0]))
    out.append(link("x-default", fr_url))
    return out


def main():
    apply = "--apply" in sys.argv
    do_sitemap = "--sitemap" in sys.argv
    groups = build_groups()

    multilingual = [g for g in groups if len(g["pages"]) > 1 and not is_noindex(g)]
    monolingual = [g for g in groups if len(g["pages"]) == 1]
    skipped_noindex = [g for g in groups if is_noindex(g)]
    print(f"skipped noindex groups: {len(skipped_noindex)}")

    # validation: every canonical href -> existing file
    broken = []
    for g in multilingual:
        for ln in canonical_links(g):
            url = re.search(r'href="([^"]*)"', ln).group(1)
            if not url_to_file(url).exists():
                broken.append((g["fr_url"], url))
    print(f"groups: {len(groups)}  multilingual: {len(multilingual)}  monolingual(FR-only): {len(monolingual)}")
    print(f"broken canonical hrefs (point to missing file): {len(broken)}")
    for fr, u in broken[:10]:
        print("   BROKEN", fr, "->", u)

    # Normalize canonical + hreflang + md-alt on EVERY indexable page (mono +
    # multilingual; noindex groups like studio are skipped). Canonical is keyed
    # to each page's OWN url; the hreflang run is group-wide.
    indexable = [g for g in groups if not is_noindex(g)]
    changed = []
    for g in indexable:
        multi = len(g["pages"]) > 1
        run = "\n".join(canonical_links(g))
        fr_slug = fr_slug_of(g["fr_url"])
        for lang, (url, f) in g["pages"].items():
            html = f.read_text(encoding="utf-8")
            new = normalize_head(html, url, run, fr_slug, multi)
            if new != html:
                changed.append(f)
                if apply:
                    f.write_text(new, encoding="utf-8")
    print(f"page files needing head-link normalization: {len(changed)}")
    if apply:
        print("  -> applied.")

    if do_sitemap:
        # Fold in the Class-B intent pages (depth-2, missed by build_groups'
        # discovery) for the sitemap only — their heads are owned by
        # build_intent_hubs and must not be re-normalized here.
        rebuild_sitemap(groups, multilingual + intent_groups())


def rebuild_sitemap(groups, multilingual):
    sm = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    current_set = set(re.findall(r"<loc>([^<]+)</loc>", sm))
    # urls belonging to noindex groups must never be in the sitemap
    noindex_urls = set()
    for g in groups:
        if is_noindex(g):
            for lang, (url, f) in g["pages"].items():
                noindex_urls.add(url)
    # alternates only for indexable multilingual groups
    url_group = {}
    for g in multilingual:
        for lang, (url, f) in g["pages"].items():
            url_group[url] = g
    # preserve existing sitemap urls, add locale variants of indexable groups,
    # drop any noindex urls
    all_urls = set(current_set)
    for g in multilingual:
        for lang, (url, f) in g["pages"].items():
            all_urls.add(url)
    all_urls -= noindex_urls
    # drop stale entries whose target file no longer exists
    stale = {u for u in all_urls if not url_to_file(u).exists()}
    if stale:
        print(f"dropping {len(stale)} stale sitemap urls: {sorted(stale)}")
    all_urls -= stale
    # drop non-canonical duplicates (page canonical points to a different url)
    canon_re = re.compile(r'<link rel="canonical" href="([^"]+)">')
    dupes = set()
    for u in all_urls:
        m = canon_re.search(url_to_file(u).read_text(encoding="utf-8"))
        if m and m.group(1).rstrip("/") != u.rstrip("/"):
            dupes.add(u)
    if dupes:
        print(f"dropping {len(dupes)} non-self-canonical urls: {sorted(dupes)}")
    all_urls -= dupes

    def sort_key(u):
        return (u.count("/"), u)

    # Per-URL <lastmod> from the git commit date of each URL's underlying
    # SOURCE — never a uniform stamp. Source mapping:
    #   /<slug>           → Json/<slug>.json
    #   /<lang>/<slug>    → Json/<slug>.json   (all locales share JSON)
    #   /<hub>/           → max(commit dates of fiches in that hub,
    #                            scripts/build_hubs.py)
    #   /<lang>/<hub>/    → same
    #   /, /<lang>/       → scripts/build_homepage.py + content sources
    #
    # No batch stamps, no blanket "today" (HANDOFF-15):
    #   * On a SHALLOW clone (Netlify deploys) git treats the shallow-boundary
    #     commit as a root commit that "adds" the whole tree — attributing
    #     every file to one date: a blanket stamp in disguise. Boundary
    #     commits are therefore excluded from date attribution; on a depth-1
    #     clone that leaves every file unresolved.
    #   * A URL whose source can't be resolved carries its previously
    #     committed <lastmod> forward — never the rendered HTML's mtime
    #     (that's just checkout time).
    #   * Only a URL that has never been in the sitemap gets stamped today —
    #     for a genuinely new page, that's the truth.
    import datetime, subprocess, json as _json, re as _re
    from collections import defaultdict

    def _shallow_boundary_shas():
        """SHAs recorded in .git/shallow — commits whose parents are absent."""
        try:
            r = subprocess.run(["git", "rev-parse", "--git-dir"],
                               cwd=str(ROOT), capture_output=True, text=True, check=True)
            shallow_file = Path(r.stdout.strip())
            if not shallow_file.is_absolute():
                shallow_file = ROOT / shallow_file
            shallow_file = shallow_file / "shallow"
            if shallow_file.exists():
                return {l.strip() for l in shallow_file.read_text().splitlines() if l.strip()}
        except Exception:
            pass
        return set()

    def _prev_lastmods():
        """{url: lastmod} from the sitemap as previously committed."""
        p = ROOT / "sitemap.xml"
        if not p.exists():
            return {}
        txt = p.read_text(encoding="utf-8", errors="ignore")
        return dict(_re.findall(
            r"<url><loc>(.*?)</loc><lastmod>(\d{4}-\d{2}-\d{2})</lastmod>", txt))

    def _git_dates(paths):
        """{path: 'YYYY-MM-DD'} for each path's most recent NON-BOUNDARY
        commit. Shallow-boundary commits falsely 'add' the whole tree, so a
        file whose only visible history is the boundary stays unresolved
        (→ carry-forward) instead of inheriting a blanket date."""
        if not paths:
            return {}
        boundary = _shallow_boundary_shas()
        out = {}
        try:
            res = subprocess.run(
                ["git", "log", "--name-only", "--format=COMMIT %H %cs", "--"] + list(paths),
                cwd=str(ROOT), capture_output=True, text=True, check=True,
            )
        except Exception:
            return {}
        current = None
        for line in res.stdout.splitlines():
            if line.startswith("COMMIT "):
                sha, date = line[len("COMMIT "):].strip().split(" ", 1)
                current = None if sha in boundary else date
            elif line.strip() and current:
                out.setdefault(line.strip(), current)
        return out

    # Source-paths: every Json/ file + the two build scripts we treat as
    # "structural source" for hubs/homepages.
    json_paths = [str(p.relative_to(ROOT)) for p in (ROOT / "Json").glob("*.json")]
    structural_paths = [
        "scripts/build_hubs.py",
        "scripts/build_homepage.py",
        "scripts/build_all_locales.py",
    ]
    _prev = _prev_lastmods()
    date_map = _git_dates(json_paths + structural_paths)
    # Prefer the committed lastmod manifest (scripts/derive_lastmod.py) for every
    # Json source. Raw git credits a corpus-wide sweep (e.g. a 389-file i18n
    # backfill) as each lieu's change — the uniform-stamp trap this sitemap is
    # meant to avoid. The manifest excludes those sweeps, so per-URL and hub-max
    # dates stay honest. Structural paths (hubs/homepage) keep their git date.
    try:
        _lm_manifest = _json.loads((ROOT / "data" / "lastmod.json").read_text(encoding="utf-8"))
        for _jp in json_paths:
            _slug = Path(_jp).stem
            if _lm_manifest.get(_slug):
                date_map[_jp] = _lm_manifest[_slug]
    except Exception:
        pass
    _unresolved = sum(1 for p in json_paths if not date_map.get(p))
    if _unresolved:
        print(f"sitemap lastmod: {_unresolved}/{len(json_paths)} sources have no "
              "usable (non-boundary) git date — carrying previous lastmod forward")

    # Build hub → list of fiche source paths to take the max over.
    HUB_FILTERS_CAT = {
        "cascades":         ("cascade",),
        "chateaux":         ("chateau",),
        "musees":           ("musee",),
        "points-de-vue":    ("point-de-vue",),
        "sentiers":         ("sentier",),
        "telecabines":      ("telecabine",),
        "voies-vertes":     ("voie-verte",),
        "lacs-plages":      ("lac","plage"),
        "bases-de-loisirs": ("domaine","parc","base-nautique","wakepark","accrobranche"),
        "parcs-jardins":    ("parc","jardin"),
        "baignade-nautisme":("aquaparc","croisiere","base-nautique","wakepark"),
        "sorties-detente":  ("cinema","casino"),
        "sport-jeux":       ("bowling","karting","patinoire"),
    }
    HUB_SLUGS_PER_LANG = {
        "cascades":{"fr":"cascades","en":"waterfalls","de":"wasserfaelle","it":"cascate","es":"cascadas","nl":"watervallen"},
        "chateaux":{"fr":"chateaux","en":"castles","de":"schloesser","it":"castelli","es":"castillos","nl":"kastelen"},
        "musees":{"fr":"musees","en":"museums","de":"museen","it":"musei","es":"museos","nl":"musea"},
        "points-de-vue":{"fr":"points-de-vue","en":"viewpoints","de":"aussichtspunkte","it":"punti-panoramici","es":"miradores","nl":"uitzichtpunten"},
        "sentiers":{"fr":"sentiers","en":"trails","de":"wanderwege","it":"sentieri","es":"senderos","nl":"wandelpaden"},
        "telecabines":{"fr":"telecabines","en":"cable-cars","de":"seilbahnen","it":"funivie","es":"telefericos","nl":"kabelbanen"},
        "voies-vertes":{"fr":"voies-vertes","en":"greenways","de":"radwege","it":"vie-verdi","es":"vias-verdes","nl":"fietsroutes"},
        "lacs-plages":{"fr":"lacs-plages","en":"lakes","de":"seen","it":"laghi","es":"lagos","nl":"meren"},
        "bases-de-loisirs":{"fr":"bases-de-loisirs","en":"leisure-parks","de":"freizeitparks","it":"aree-ricreative","es":"areas-de-ocio","nl":"recreatieparken"},
        "parcs-jardins":{"fr":"parcs-jardins","en":"parks-gardens","de":"parks-gaerten","it":"parchi-giardini","es":"parques-jardines","nl":"parken-tuinen"},
        "baignade-nautisme":{"fr":"baignade-nautisme","en":"swimming-watersports","de":"baden-wassersport","it":"nuoto-sport-acquatici","es":"bano-deportes-acuaticos","nl":"zwemmen-watersport"},
        "sorties-detente":{"fr":"sorties-detente","en":"outings-relax","de":"ausfluege-erholung","it":"uscite-relax","es":"salidas-relax","nl":"uitstapjes-ontspanning"},
        "sport-jeux":{"fr":"sport-jeux","en":"sport-games","de":"sport-spiele","it":"sport-giochi","es":"deporte-juegos","nl":"sport-spelen"},
        "que-faire":{"fr":"que-faire","en":"what-to-do","de":"was-unternehmen","it":"cosa-fare","es":"que-hacer","nl":"wat-te-doen"},
        "sensations-plein-air":{"fr":"sensations-plein-air","en":"outdoor-thrills","de":"outdoor-nervenkitzel","it":"brividi-aria-aperta","es":"sensaciones-aire-libre","nl":"buitenavontuur"},
    }

    # Pre-compute hub URL → date
    hub_date = {}
    for canon, cats in HUB_FILTERS_CAT.items():
        # collect fiche slugs matching this hub
        member_dates = []
        for jp in json_paths:
            try:
                d = _json.loads((ROOT / jp).read_text(encoding="utf-8"))
            except Exception:
                continue
            if d.get("status") in ("draft", "unverified"): continue
            if d.get("category") in cats:
                dt = date_map.get(jp)
                if dt: member_dates.append(dt)
        member_dates.append(date_map.get("scripts/build_hubs.py") or "")
        hub_max = max(d for d in member_dates if d) if any(member_dates) else None
        for lang, slug in HUB_SLUGS_PER_LANG[canon].items():
            url = f"{BASE}/{slug}/" if lang == "fr" else f"{BASE}/{lang}/{slug}/"
            hub_date[url] = hub_max
    # Curated hubs (que-faire, sensations-plein-air): take build_hubs date as proxy
    for canon in ("que-faire", "sensations-plein-air"):
        for lang, slug in HUB_SLUGS_PER_LANG[canon].items():
            url = f"{BASE}/{slug}/" if lang == "fr" else f"{BASE}/{lang}/{slug}/"
            hub_date[url] = date_map.get("scripts/build_hubs.py")

    homepage_dates = [date_map.get(p) for p in structural_paths]
    homepage_max = max(d for d in homepage_dates if d) if any(homepage_dates) else None

    def lastmod_for(u):
        # Strip protocol/host
        tail = u.replace(BASE, "").lstrip("/").rstrip("/")
        # 1) Real (non-boundary) git date of the URL's source
        if tail == "" or tail in set(locales.VISIBLE_SECONDARY):
            if homepage_max:
                return homepage_max
        elif u in hub_date and hub_date[u]:
            return hub_date[u]
        else:
            parts = tail.split("/")
            if parts[0] in set(locales.VISIBLE_SECONDARY) and len(parts) >= 2:
                slug = parts[1]
            else:
                slug = parts[0]
            src = f"Json/{slug}.json"
            if date_map.get(src):
                return date_map[src]
        # 2) Carry the previously committed lastmod forward — never mtime,
        #    never a blanket stamp.
        if u in _prev:
            return _prev[u]
        # 3) Genuinely new URL: today is the truth.
        return datetime.date.today().isoformat()

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
             'xmlns:xhtml="http://www.w3.org/1999/xhtml">']
    for u in sorted(all_urls, key=sort_key):
        lm = lastmod_for(u)
        g = url_group.get(u)
        if g and len(g["pages"]) > 1:
            alts = "".join(
                f'<xhtml:link rel="alternate" hreflang="{l}" href="{g["pages"][l][0]}"/>'
                for l in (["fr"] + LANGS) if l in g["pages"]
            )
            alts += f'<xhtml:link rel="alternate" hreflang="x-default" href="{g["fr_url"]}"/>'
            lines.append(f"  <url><loc>{u}</loc><lastmod>{lm}</lastmod><changefreq>weekly</changefreq>{alts}</url>")
        else:
            lines.append(f"  <url><loc>{u}</loc><lastmod>{lm}</lastmod><changefreq>weekly</changefreq></url>")
    lines.append("</urlset>")
    out = "\n".join(lines) + "\n"
    (ROOT / "sitemap.xml").write_text(out, encoding="utf-8")
    print(f"sitemap rebuilt: {len(all_urls)} urls (was {len(current_set)})")


if __name__ == "__main__":
    main()
