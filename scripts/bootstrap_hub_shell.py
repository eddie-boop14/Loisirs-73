#!/usr/bin/env python3
"""Create hub pages this site's engine can actually maintain.

This site's hub pages were written by hand. They carry <main> and almost
nothing else the pipeline patches — no <h1>, no ItemList, no filter chrome —
so build_hubs regenerated 0 of 18 of them and the FR hubs shipped with no
heading and no intro. 22 KB against the reference site's 102 KB.

The fix is not another hand-written page. It is to lift the engine's canonical
hub shell from the reference site, strip everything that belongs to that site,
and hand the result to the ordinary pipeline — which then fills the cards, the
head, the heading, the ItemList and the filters exactly as it does everywhere
else. About 79 KB of that shell is generic chrome (CSS, filters, nav, footer,
scripts); roughly 2.5 KB is the other site's prose, and it is removed rather
than translated; the 19 KB ItemList is regenerated from this site's members.

Run once per hub that needs bootstrapping, then let build_all take over:

    python3 scripts/bootstrap_hub_shell.py --reference /path/to/loisir-74

Like build_sister_proximity, this is an offline tool. The reference checkout is
a developer's machine detail and never exists on the deploy host, so this is
NOT part of build_all — its output is committed.

What it deliberately does not do: invent prose. The hub intro, catcher and FAQ
of the reference site describe that département's lakes and passes. They are
stripped, not reworded. A hub here ships with a heading and its cards until
someone writes an intro about Savoie.
"""
import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import siteconfig  # HANDOFF-73: per-site identity
import locales
import build_lieu_page as BLP

ROOT = Path(__file__).resolve().parent.parent

# Prose that belongs to the reference site and must not travel. Same list the
# facts-first renderer strips, for the same reason.
_PROSE_BLOCKS = [
    r'\n?<p class="hub-catcher">.*?</p>',
    r'\n?<section[^>]*class="hub-intro"[^>]*>.*?</section>',
    r'\n?<section[^>]*class="hub-faq"[^>]*>.*?</section>',
]


def _identity_swap(t, ref):
    """Reference-site identity out, this site's in."""
    for a, b in ref["swaps"]:
        t = t.replace(a, b)
    return t


def _strip_reference_prose(t):
    for pat in _PROSE_BLOCKS:
        t = re.sub(pat, "", t, flags=re.S)
    # The FAQPage graph describes the FAQ we just removed.
    t = re.sub(r'<script type="application/ld\+json">.*?</script>\n?',
               lambda m: "" if '"FAQPage"' in m.group(0) else m.group(0),
               t, flags=re.S)
    return t


def _hreflang_cluster(hub, lang):
    """This site's own cluster: its visible locales, its localized slugs."""
    slugs = BLP.HUB_LOCALE_SLUGS[hub]
    out = []
    for l in locales.PROSE:
        s = slugs.get(l) or slugs["fr"]
        url = f"{siteconfig.BASE_URL}/{s}/" if l == "fr" else f"{siteconfig.BASE_URL}/{l}/{s}/"
        out.append(f'<link rel="alternate" hreflang="{l}" href="{url}">')
    fr = slugs["fr"]
    out.append(f'<link rel="alternate" hreflang="x-default" '
               f'href="{siteconfig.BASE_URL}/{fr}/">')
    return "\n".join(out)


def _prune_to_this_site(t, roster):
    """Drop chrome that points at hubs, locales and intent pages this site
    does not have.

    The shell arrives wired for the reference site: a footer category list of
    its 15 hubs, a picker spanning its 12 locales, and links to its intent
    pages. Left alone that is 55 broken targets over 1292 links — and the
    commune builder lifts the same chrome, so it spreads well past the hubs.
    Everything here is removed by what it POINTS AT, never by position, so a
    site that later grows a hub simply stops having it pruned."""
    site = re.escape(siteconfig.BASE_URL)

    # Footer category list: keep only hubs in this site's roster.
    def _keep_li(m):
        href = m.group(1)
        slug = href.rstrip("/").rsplit("/", 1)[-1]
        return m.group(0) if slug in roster else ""
    t = re.sub(r'<li><a href="(%s/[^"]*)"[^>]*>.*?</a></li>' % site, _keep_li, t, flags=re.S)

    # Language picker: keep only locales this site renders.
    def _keep_a(m):
        return m.group(0) if m.group(1) in locales.PROSE else ""
    t = re.sub(r'<a href="%s/[^"]*"[^>]*hreflang="([a-z-]+)"[^>]*>[^<]*</a>' % site,
               _keep_a, t)

    # Intent pages live in a marker block the pipeline re-injects. Empty it
    # rather than deleting the markers — build_intent_hubs then fills it with
    # THIS site's registry. Carried over intact it advertised Annecy, Chamonix
    # and the Mont-Blanc, none of which are in this département.
    # Empty EVERY <!--name:start--> … <!--name:end--> band rather than naming
    # them. Each one is content the pipeline re-injects from this site's own
    # data, so emptying them is always safe and always complete — chasing them
    # individually meant three rounds (intent-pages, hub-bestof, hub-intent),
    # each one shipping another link to Annecy or the Mont-Blanc.
    t = re.sub(r'(<!--([a-z0-9-]+):start-->).*?(<!--\2:end-->)', r'\1\3', t, flags=re.S)
    return t


def _retarget_head(t, hub, lang):
    slugs = BLP.HUB_LOCALE_SLUGS[hub]
    s = slugs.get(lang) or slugs["fr"]
    url = f"{siteconfig.BASE_URL}/{s}/" if lang == "fr" else f"{siteconfig.BASE_URL}/{lang}/{s}/"
    t = re.sub(r'<link rel="canonical" href="[^"]*">',
               f'<link rel="canonical" href="{url}">', t, count=1)
    # Drop the reference site's cluster wholesale, then write ours once.
    t = re.sub(r'[ \t]*<link rel="alternate" hreflang="[^"]*" href="[^"]*"\s*/?>\n?', "", t)
    t = t.replace("</head>", _hreflang_cluster(hub, lang) + "\n</head>", 1)
    dir_attr = ' dir="rtl"' if locales.DIR.get(lang) == "rtl" else ""
    t = re.sub(r'<html lang="[a-zA-Z-]+"[^>]*>', f'<html lang="{lang}"{dir_attr}>', t, count=1)
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reference", required=True,
                    help="path to the reference site's repo checkout")
    ap.add_argument("--hubs", help="comma-separated FR hub names (default: the roster)")
    ap.add_argument("--force", action="store_true",
                    help="overwrite hub pages that already exist")
    args = ap.parse_args()

    src_root = Path(args.reference)
    if not src_root.is_dir():
        sys.exit(f"no reference checkout at {src_root}")

    sis = getattr(siteconfig, "SISTER", None) or {}
    ref_domain = (sis.get("url") or "").replace("https://", "").rstrip("/")
    ref_name = sis.get("name") or ""
    ref_dept = sis.get("dept") or ""
    if not (ref_domain and ref_name):
        sys.exit("no `sister` block in site.config.json — cannot name the reference site")
    ref = {"swaps": [
        (ref_domain, siteconfig.DOMAIN),
        (ref_name, siteconfig.SITE_NAME),
        (ref_domain.split(".")[0], siteconfig.WORDMARK),
        (ref_dept, siteconfig.DEPT_NAME),
    ]}

    import build_hubs as H
    hubs = (args.hubs.split(",") if args.hubs else list(H.HUB_FILTERS))
    # Every slug this site actually publishes a hub at, in every locale — the
    # keep-list for the footer category block.
    roster = {s for h in H.HUB_FILTERS
              for s in (BLP.HUB_LOCALE_SLUGS.get(h) or {"fr": h}).values()}

    made, skipped, fellback = [], [], []
    for hub in hubs:
        slugs = BLP.HUB_LOCALE_SLUGS[hub]
        for lang in locales.PROSE:
            slug = slugs.get(lang) or hub
            # Take each locale's shell from the reference site's SAME locale, so
            # the filter labels, the breadcrumb and the empty-results message
            # arrive already in that language. Deriving every locale from the
            # French shell left "Aucun résultat" and "Accès" sitting in the
            # German and Spanish hubs — fix_hub_chrome covers much of that but
            # not all of it, and there is no reason to re-translate strings the
            # reference site already carries correctly.
            ref_slug = slugs.get(lang) or hub
            cand = (src_root / ref_slug if lang == "fr" else src_root / lang / ref_slug)
            shell_src = cand / "index.html"
            if not shell_src.is_file():
                shell_src = src_root / hub / "index.html"
                if not shell_src.is_file():
                    print(f"  ! no shell for {hub}/ [{lang}] on the reference site; skipping")
                    continue
                fellback.append(f"{lang}/{slug}")
            out = (ROOT / slug if lang == "fr" else ROOT / lang / slug) / "index.html"
            if out.exists() and not args.force:
                skipped.append(str(out.relative_to(ROOT))); continue
            shell = shell_src.read_text(encoding="utf-8")
            shell = _identity_swap(shell, ref)
            shell = _strip_reference_prose(shell)
            shell = _prune_to_this_site(shell, roster)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(_retarget_head(shell, hub, lang), encoding="utf-8")
            made.append(str(out.relative_to(ROOT)))
    if fellback:
        print(f"  ! {len(fellback)} shell(s) fell back to the FR shell "
              f"(chrome will need fix_hub_chrome): {', '.join(fellback)}")

    print(f"bootstrap_hub_shell: wrote {len(made)} hub shell(s), skipped {len(skipped)} existing")
    for m in made:
        print("  +", m)
    if skipped:
        print(f"  (use --force to replace the {len(skipped)} that already exist)")
    print("\nNow run build_all: the ordinary pipeline fills cards, head, h1, "
          "ItemList and filters.")


if __name__ == "__main__":
    main()
