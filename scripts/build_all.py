#!/usr/bin/env python3
"""build_all.py — single canonical build entry point (JOB 3).

Renders every fiche page, the catalog index, and the placement-protection
report — all from Json/ in one idempotent pass, with no HTML mutation by
downstream scripts.

Pipeline (sequential — order is the dependency order, no cycles):

  1. Render 392 × 6 = 2352 fiche HTMLs from Json/<slug>.json via
     scripts.build_lieu_page.build_page(d, lang).  Writes:
       <ROOT>/<slug>.html              for fr
       <ROOT>/<lang>/<slug>.html       for en/de/it/es/nl
     and writes scripts/translation-coverage-report.json.
  2. Rebuild scripts/catalog-index.json from Json/.
  3. Compute the protected-placement report (chez-nous-a-la-plage,
     chalet-du-tornet) vs reports/featured-placements-baseline.md.
  4. Optional: build_site.py builds the publishable _site/ tree
     (skip with --no-site).

Idempotency: two consecutive runs produce byte-identical outputs.

Usage:
    python3 scripts/build_all.py [--no-site] [--no-coverage] [--check-only]

`--check-only` re-asserts the placement gate without rebuilding.
"""
import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import locales  # noqa: E402


def run(label, fn):
    print(f"==> {label}")
    fn()


# ---- 1. fiche pages ---------------------------------------------------------

def render_all_fiches():
    """Delegate to build_all_locales (which calls build_lieu_page.build_page
    per fiche × locale and writes the translation-coverage report)."""
    import build_all_locales  # noqa: E402
    # Re-invoke its main() via argv override so the CLI defaults apply.
    sys_argv = sys.argv[:]
    sys.argv = ["build_all_locales.py"]
    try:
        build_all_locales.main()
    finally:
        sys.argv = sys_argv


# ---- 2. catalog index -------------------------------------------------------

def rebuild_catalog_index():
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "build_catalog_index.py")],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    if out.returncode != 0:
        print(out.stdout); print(out.stderr, file=sys.stderr)
        raise RuntimeError("build_catalog_index failed")
    print(out.stdout.strip() or "(catalog rebuilt)")


def inject_analytics():
    """Cloudflare Web Analytics beacon on every published page. Wired in so a
    newly-emitted fiche/hub/intent page cannot ship without it — and so a
    foreign property's token can never sit here unnoticed."""
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "inject_analytics.py"), "--apply"],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    if out.returncode != 0:
        print(out.stdout); print(out.stderr, file=sys.stderr)
        raise RuntimeError("inject_analytics failed")
    print(out.stdout.strip().splitlines()[0] if out.stdout.strip() else "(beacon injected)")


def sync_home_cards():
    """Homepage card images derive from Json/ heroes. index.html is authored
    chrome that no builder regenerates, so without this step every photo added
    to a fiche makes the homepage staler — never fresher."""
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "sync_home_cards.py"), "--apply"],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    if out.returncode != 0:
        print(out.stdout); print(out.stderr, file=sys.stderr)
        raise RuntimeError("sync_home_cards failed")
    print(out.stdout.strip().splitlines()[-1] if out.stdout.strip() else "(home cards synced)")


def rebuild_security_txt():
    """RFC 9116 security.txt. Expires is computed at build time, never typed —
    a hardcoded date is valid the day it is written and invalid forever after."""
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "build_security_txt.py")],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    if out.returncode != 0:
        print(out.stdout); print(out.stderr, file=sys.stderr)
        raise RuntimeError("build_security_txt failed")
    print(out.stdout.strip() or "(security.txt regenerated)")


def rebuild_project_state():
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "build_project_state.py")],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    if out.returncode != 0:
        print(out.stdout); print(out.stderr, file=sys.stderr)
        raise RuntimeError("build_project_state failed")
    print(out.stdout.strip() or "(PROJECT-STATE regenerated)")


def tarif_completeness_gate():
    """Station facts.tarif must cover the full published roster (no 8-vs-12 gap)."""
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "gate_tarif_completeness.py")],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    print((out.stdout or "").strip() or (out.stderr or "").strip())
    if out.returncode != 0:
        print(out.stderr, file=sys.stderr)
        raise RuntimeError("tarif completeness gate failed")


def rebuild_ai_content():
    """Regenerate the AI content layer (content/<slug>.md ×392 + llms.txt +
    llms-full.txt) from JSON truth, so the advertised /content/<slug>.md URLs
    always exist and the llms counts can't drift."""
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "build_ai_content.py")],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    if out.returncode != 0:
        print(out.stdout); print(out.stderr, file=sys.stderr)
        raise RuntimeError("build_ai_content failed")
    print(out.stdout.strip() or "(ai content rebuilt)")


def normalize_head_links():
    """Final HTML pass: make canonical self-referential + one hreflang set +
    md-alt-iff-exists on every indexable page, and rebuild the sitemap. Runs
    last (all HTML + content/*.md now exist) so a copy-seeded bad canonical
    can't survive a build. Idempotent."""
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "fix_hreflang_sitemap.py"), "--apply", "--sitemap"],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    if out.returncode != 0:
        print(out.stdout); print(out.stderr, file=sys.stderr)
        raise RuntimeError("fix_hreflang_sitemap (normalize head links) failed")
    print(out.stdout.strip() or "(head links normalized)")


def normalize_lang_nav():
    """Make the header language picker + footer "Langue" list read the visible
    roster on every page whose language nav is frozen chrome (hub indexes + the
    FR homepage — surfaces no builder rewrites). Reads each page's hreflang
    alternates (just normalized) and inserts any missing VISIBLE language, so a
    newly-published language appears in the nav for free. Runs AFTER
    normalize_head_links (the alternates it reads must already be present).
    Idempotent."""
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "fix_lang_nav.py")],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    if out.returncode != 0:
        print(out.stdout); print(out.stderr, file=sys.stderr)
        raise RuntimeError("fix_lang_nav (normalize language nav) failed")
    print(out.stdout.strip() or "(language nav normalized)")


def rebuild_hubs():
    """Regen 13 category hubs from Json/ + patch locale homepages for full
    hub coverage (closes the orphan gap from voies-vertes / sorties-detente
    missing from locale homepage nav)."""
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "build_hubs.py")],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    if out.returncode != 0:
        print(out.stdout); print(out.stderr, file=sys.stderr)
        raise RuntimeError("build_hubs failed")
    # only show the tail
    lines = out.stdout.strip().split("\n")
    print("\n".join(lines[-8:]) if lines else "(hubs rebuilt)")


def rebuild_communes():
    """Render the commune-layer pages and (re)inject the reciprocal "À
    <Commune>" backlinks onto the aggregated fiches. MUST run after fiche
    rendering (which wipes the marker-injected backlinks) and BEFORE the
    reachability gate — otherwise the commune pages read as orphans and the
    Netlify build (command = build_all.py) fails, freezing the deploy."""
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "build_communes.py")],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    if out.returncode != 0:
        print(out.stdout); print(out.stderr, file=sys.stderr)
        raise RuntimeError("build_communes failed")
    lines = out.stdout.strip().split("\n")
    print("\n".join(lines[-3:]) if lines else "(communes rebuilt)")


def version_runtime_assets():
    """Cache-bust every /scripts/ runtime include with its content hash. Runs
    after normalize_head_links (all HTML exists), so freshly-rendered pages and
    committed homepage chrome alike get a current ?v=<hash>. Idempotent."""
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "version_assets.py")],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    if out.returncode != 0:
        print(out.stdout); print(out.stderr, file=sys.stderr)
        raise RuntimeError("version_assets failed")
    print(out.stdout.strip() or "(runtime assets versioned)")


def rebuild_fulltree_langs():
    """Render every PUBLISHED facts-first language as a full tree (HANDOFF-16):
    all fiches + 15 localized-slug hubs + communes + homepage. Runs BEFORE
    normalize_head_links so fix_hreflang_sitemap sees the pages and folds them
    into the 6's hreflang clusters + sitemap. The prose builders never touch these
    languages (locales.PROSE excludes them — the structural no-FR-fallback guard)."""
    import locales as _loc
    for lang in _loc.FACTS_PUBLISHED:
        out = subprocess.run(
            [sys.executable, str(SCRIPTS / "build_fulltree_lang.py"), lang],
            capture_output=True, text=True, cwd=str(ROOT)
        )
        if out.returncode != 0:
            print(out.stdout); print(out.stderr, file=sys.stderr)
            raise RuntimeError(f"build_fulltree_lang {lang} failed")
        print(out.stdout.strip() or f"({lang} full tree rendered)")


# NOTE: rebuild_pilot_langs (the staged-indexable ~20-page pilot) was retired in
# HANDOFF-20 when pt/cs/ja/ar/he flipped to published. They now render as full
# facts-first trees via rebuild_fulltree_langs (FACTS_PUBLISHED). No language is
# staged-indexable anymore, so there is nothing to pilot. build_pilot_langs.py is
# kept only as the rendering library that build_fulltree_lang imports (V, esc,
# fact_rows, CSS) — it is no longer invoked as a build step.


def rebuild_facet_hub_pages():
    """HANDOFF-facet-hubs: render the 5 HTML facet hubs (FR+PROSE) + 8 md mirrors.
    Runs BEFORE normalize_head_links so fix_hreflang_sitemap folds the new pages
    into canonical/hreflang/sitemap."""
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "build_facet_hubs.py"), "--pages"],
        cwd=str(ROOT), capture_output=True, text=True)
    print(out.stdout.strip())
    if out.returncode != 0:
        print(out.stderr, file=sys.stderr)
        raise RuntimeError("build_facet_hubs --pages failed")


def rebuild_facet_hub_links():
    """Inject the facet-hub 0-orphan nav into each locale homepage — AFTER
    normalize_lang_nav so a later homepage rewrite can't strip the block."""
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "build_facet_hubs.py"), "--links"],
        cwd=str(ROOT), capture_output=True, text=True)
    print(out.stdout.strip())
    if out.returncode != 0:
        print(out.stderr, file=sys.stderr)
        raise RuntimeError("build_facet_hubs --links failed")


def rebuild_intent_hubs():
    """Render registry-driven intent-hub pages (data/intent-hubs.json) FR + 5
    locales and link each from its category hub. Runs after hubs/communes (so
    member fiches + category hubs exist) and before normalize_head_links (so
    canonicals/hreflang/sitemap pick the new pages up)."""
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "build_intent_hubs.py")],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    if out.returncode != 0:
        print(out.stdout); print(out.stderr, file=sys.stderr)
        raise RuntimeError("build_intent_hubs failed")
    print(out.stdout.strip() or "(intent hubs rebuilt)")


def inject_home_selections():
    """FIX D: late homepage 'Nos sélections' strip (after facet-hub links so it
    is not stripped by a later homepage rewrite)."""
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "build_intent_hubs.py"), "--home-selections"],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    if out.returncode != 0:
        print(out.stdout); print(out.stderr, file=sys.stderr)
        raise RuntimeError("inject_home_selections failed")
    print(out.stdout.strip() or "(home selections injected)")


def status_gate():
    """JOB 6 gate: every fiche must have an explicit status (draft|verified|
    published). Print the distribution. Block if any fiche has status=None."""
    import json as _json, glob as _glob
    from collections import Counter as _Counter
    dist = _Counter()
    missing = []
    for jp in sorted(_glob.glob(str(ROOT / "Json" / "*.json"))):
        d = _json.loads(open(jp).read())
        s = d.get("status")
        if s is None:
            missing.append(jp.split("/")[-1][:-5])
        else:
            dist[s] += 1
    total = sum(dist.values()) + len(missing)
    print(f"  total fiches: {total}")
    for s, n in dist.most_common():
        print(f"    {s}: {n}")
    if missing:
        print(f"  missing status: {len(missing)} fiches")
        for m in missing[:5]:
            print(f"    - {m}")
        raise SystemExit("status gate FAILED — fiches without explicit status field")


def hygiene_gate():
    """Strict hygiene scan: 0 Tier 1/2 findings across all rendered fields."""
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "audit_hygiene.py"), "--strict"],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    print(out.stdout.strip())
    if out.returncode != 0:
        raise SystemExit("hygiene gate FAILED")


def reachability_gate():
    """Strict reachability: 0 orphans across all 6 locales."""
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "check_reachability.py"), "--strict"],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    print(out.stdout.strip())
    if out.returncode != 0:
        raise SystemExit("reachability gate FAILED")


# ---- 3. protected-placement gate --------------------------------------------

PROT = {
    "chez-nous-a-la-plage": re.compile(r"Chez Nous à la Plage", re.I),
    "chalet-du-tornet":     re.compile(r"Chalet du Tornet", re.I),
}


def parse_baseline_hosts():
    """Read reports/featured-placements-baseline.md, return {slug: set(hosts)}."""
    md = (ROOT / "reports" / "featured-placements-baseline.md").read_text(encoding="utf-8")
    out = {n: set() for n in PROT}
    cur = None
    for line in md.split("\n"):
        if line.startswith("## chez-nous"): cur = "chez-nous-a-la-plage"; continue
        if line.startswith("## chalet"):    cur = "chalet-du-tornet"; continue
        if cur and line.startswith("| ") and "|---|" not in line and "host fiche" not in line:
            host = line.split("|")[1].strip()
            if host:
                out[cur].add(host)
    return out


def scan_current_placements():
    """Return {slug: set(host_slugs_with_card)} for the protected fiches."""
    hits = {n: set() for n in PROT}
    for p in list(ROOT.glob("*.html")) + [f for L in locales.PROSE_SECONDARY for f in (ROOT / L).glob("*.html") if (ROOT / L).exists()]:
        slug = p.stem
        try:
            html = p.read_text(encoding="utf-8")
        except Exception:
            continue
        for name, pat in PROT.items():
            if name == "chalet-du-tornet" and slug == "domaine-du-tornet":
                continue
            if pat.search(html):
                hits[name].add(slug)
    return hits


def placement_gate(strict=True):
    """Compare baseline vs current. If any baseline host lost the card → FAIL."""
    baseline = parse_baseline_hosts()
    current = scan_current_placements()
    failed = False
    for name, base_hosts in baseline.items():
        cur_hosts = current[name]
        lost = base_hosts - cur_hosts
        gained = cur_hosts - base_hosts
        status = "OK" if not lost else "FAIL"
        if lost: failed = True
        print(f"  {name:<28} baseline={len(base_hosts):<3} current={len(cur_hosts):<3} -{len(lost)} +{len(gained)}   {status}")
        if lost:
            for h in sorted(lost):
                print(f"      LOST: {h}")
    if failed and strict:
        raise SystemExit("placement gate FAILED — protected fiche dropped a host")
    return not failed


# ---- 4. snapshot byte-faithfulness ------------------------------------------

CARD_RE = re.compile(
    r'(<article[^>]*class="partner[^"]*"[^>]*>.*?</article>)',
    re.DOTALL,
)


def card_diff_gate(strict=True):
    """Compare each rebuilt card against reports/protected-cards/<slug>/<lang>.html.
    Verifies byte-faithfulness across all 12 (slug × locale) snapshots."""
    snaps = ROOT / "reports" / "protected-cards"
    failed = False
    for slug in PROT:
        for lang in locales.PROSE:
            snap = snaps / slug / f"{lang}.html"
            if not snap.exists():
                continue
            wanted = re.sub(r"^<!--.*?-->\n", "", snap.read_text(encoding="utf-8")).strip()
            # Find a representative host with the card in the relevant locale
            search_dirs = [ROOT] if lang == "fr" else [ROOT / lang]
            sample = None
            for d in search_dirs:
                if not d.exists():
                    continue
                for p in sorted(d.glob("*.html")):
                    if p.stem == "domaine-du-tornet" and slug == "chalet-du-tornet":
                        continue
                    html = p.read_text(encoding="utf-8")
                    if PROT[slug].search(html):
                        for card in CARD_RE.findall(html):
                            if PROT[slug].search(card):
                                sample = card.strip()
                                break
                        if sample:
                            break
                if sample:
                    break
            if sample is None:
                print(f"  {slug}/{lang}: no rebuilt card to compare")
                continue
            match = (sample == wanted)
            verdict = "byte-faithful" if match else f"DRIFT ({len(sample)} vs {len(wanted)} bytes)"
            print(f"  {slug:<22} {lang}: {verdict}")
            if not match:
                failed = True
    if failed and strict:
        raise SystemExit("card-diff gate FAILED — protected card drifted from snapshot")
    return not failed


# ---- 5. idempotency assertion (optional, --check-only) ----------------------

def assert_idempotent():
    """Render twice into a temp dir, byte-compare. (~20s on the 392 corpus.)"""
    import shutil, tempfile
    tmp1 = Path(tempfile.mkdtemp(prefix="build_all_idem_"))
    tmp2 = Path(tempfile.mkdtemp(prefix="build_all_idem_"))
    try:
        import build_all_locales
        for tmp in (tmp1, tmp2):
            sys_argv = sys.argv[:]
            sys.argv = ["build_all_locales.py", "--out-dir", str(tmp)]
            try:
                build_all_locales.main()
            finally:
                sys.argv = sys_argv
        # diff
        diffs = list(subprocess.run(
            ["diff", "-r", str(tmp1), str(tmp2)],
            capture_output=True, text=True
        ).stdout.split("\n"))
        diffs = [d for d in diffs if d.strip()]
        if diffs:
            print(f"NOT IDEMPOTENT: {len(diffs)} differences:")
            for d in diffs[:5]:
                print(f"  {d}")
            raise SystemExit(1)
        print("  idempotent (two runs byte-identical)")
    finally:
        shutil.rmtree(tmp1, ignore_errors=True)
        shutil.rmtree(tmp2, ignore_errors=True)


# ---- main -------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-site", action="store_true",
                    help="Skip the build_site step")
    ap.add_argument("--check-only", action="store_true",
                    help="Re-run gates against the current tree (no rebuild)")
    ap.add_argument("--idempotency", action="store_true",
                    help="Build twice into temp dirs and assert byte-identical")
    args = ap.parse_args()

    if args.check_only:
        run("placement gate (no rebuild)", placement_gate)
        run("card-diff gate (no rebuild)", card_diff_gate)
        return

    if args.idempotency:
        run("idempotency assertion", assert_idempotent)
        return

    run("status gate (state machine)", status_gate)
    run("hygiene gate (Tier 1/2 scan)", hygiene_gate)
    run("tarif roster-completeness gate", tarif_completeness_gate)
    run("render fiche pages", render_all_fiches)
    run("rebuild catalog index", rebuild_catalog_index)
    run("regenerate hubs + homepage nav", rebuild_hubs)
    run("render commune pages + reciprocal backlinks", rebuild_communes)
    run(f"render facts-first full trees (published facts langs: {', '.join(locales.FACTS_PUBLISHED)})",
        rebuild_fulltree_langs)
    # Intent hubs render AFTER the facts-first trees: build_fulltree_lang
    # clean-slates each facts-lang subtree (shutil.rmtree), so intent pages
    # written into /pl/ /ar/ … must come afterwards or they'd be wiped. Running
    # last also lets the que-faire-index + category-hub link injection target
    # the freshly built localized hubs.
    run("render intent hubs (registry-driven)", rebuild_intent_hubs)
    run("placement gate vs baseline", placement_gate)
    run("card-diff gate vs snapshot", card_diff_gate)
    run("reachability gate (strict)", reachability_gate)
    run("regenerate AI content layer (content/*.md + llms)", rebuild_ai_content)
    run("render facet hubs + mirrors (HANDOFF-facet-hubs)", rebuild_facet_hub_pages)
    run("normalize head links (canonical + hreflang + md-alt)", normalize_head_links)
    run("normalize language nav (picker + footer read the visible roster)", normalize_lang_nav)
    run("inject facet-hub homepage links (0-orphan, after lang-nav)", rebuild_facet_hub_links)
    run("inject intent 'Nos sélections' homepage strip (FIX D, after facet links)",
        inject_home_selections)
    run("cache-bust runtime /scripts/ includes (content-hash ?v=)", version_runtime_assets)
    run("sync homepage card images from Json/ heroes (derived, never authored)",
        sync_home_cards)
    run("emit .well-known/security.txt (RFC 9116 — Expires must never lapse)",
        rebuild_security_txt)
    run("inject Cloudflare Web Analytics beacon (every published page)", inject_analytics)
    run("regenerate PROJECT-STATE.md (JOB 8 — derived, never authored)", rebuild_project_state)
    if not args.no_site:
        run("build _site/", lambda: subprocess.check_call(
            [sys.executable, str(SCRIPTS / "build_site.py")], cwd=str(ROOT)))


if __name__ == "__main__":
    main()
