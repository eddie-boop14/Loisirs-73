#!/usr/bin/env python3
"""audit_locale_parity.py — report-only NL-vs-FR depth audit (HANDOFF-03 C).

Dutch is the least-contested locale; this audit measures how close the rendered
NL tree is to FR so the systematic gaps can be fixed in the builder (benefiting
every locale) rather than hand-patching NL pages.

Two layers:
  1. Content depth (Json i18n): for every published fiche, which depth-bearing
     i18n.fr keys have NO i18n.nl counterpart → those render FR fallback in NL.
  2. Rendered parity (built pages): NL page carries <html lang="nl">; for beach
     fiches the L'essentiel + Plages voisines blocks are present in NL too;
     fact-grid labels are localized (not FR-leaking).

Writes reports/nl-parity.md (+ .json). Never fails — it is a report.
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_DIR = os.path.join(ROOT, "Json")
# Keys that are RENDERED per locale. Top-level keys live directly on i18n.<lang>;
# body keys live on i18n.<lang>.body (that is what build_lieu_page's L_body
# renders — the top-level practical_info/activities are vestigial legacy data
# and are NOT shown, so they must not be audited).
TOP_KEYS = ["name", "meta_title", "meta_description", "facts", "faq", "hero"]
BODY_KEYS = ["what_is", "practical_info", "activities", "when_to_visit", "how_to_get_there"]
DEPTH_KEYS = TOP_KEYS + BODY_KEYS


def _present(loc, key):
    """Is `key` populated for this locale, looked up where it is actually rendered?"""
    if key in TOP_KEYS:
        return bool(loc.get(key))
    return bool((loc.get("body") or {}).get(key))
# A few FR fact-label tokens that, if present in an NL page's facts grid, mean a
# label leaked untranslated.
FR_LABEL_LEAK = ("<div class=\"k\">Accès</div>", "<div class=\"k\">Tarif</div>",
                 "<div class=\"k\">Saison</div>", "<div class=\"k\">Durée</div>")


def published_fiches():
    for fp in sorted(glob.glob(os.path.join(JSON_DIR, "*.json"))):
        d = json.loads(open(fp, encoding="utf-8").read())
        if d.get("status") == "published":
            yield d


def beach_slugs():
    try:
        reg = json.loads(open(os.path.join(ROOT, "data", "intent-hubs.json"), encoding="utf-8").read())
    except (OSError, ValueError):
        return set()
    hubs = {"baignade-lac-annecy", "baignade-leman", "ou-se-baigner-haute-savoie"}
    return {m["slug"] for h in reg if h["slug"] in hubs for m in h.get("members", [])}


def main():
    beaches = beach_slugs()
    depth_gaps = []      # fiches missing nl depth keys
    rendered_issues = []
    n = 0
    fully_parallel = 0
    for d in published_fiches():
        n += 1
        slug = d["slug"]
        i18n = d.get("i18n", {})
        fr = i18n.get("fr", {}) or {}
        nl = i18n.get("nl", {}) or {}
        en = i18n.get("en", {}) or {}
        de = i18n.get("de", {}) or {}
        missing = [k for k in DEPTH_KEYS if _present(fr, k) and not _present(nl, k)]
        # NL-specific = a key EN or DE already carries but NL doesn't (NL behind
        # its sibling locales — the actionable parity gap). The rest are
        # cross-locale content gaps (no locale translated that section).
        nl_specific = [k for k in missing if _present(en, k) or _present(de, k)]
        if missing:
            depth_gaps.append({"slug": slug, "missing": missing,
                               "nl_specific": nl_specific,
                               "nl_present": bool(nl)})
        else:
            fully_parallel += 1
        # rendered parity
        nlp = os.path.join(ROOT, "nl", f"{slug}.html")
        if os.path.exists(nlp):
            html = open(nlp, encoding="utf-8").read()
            iss = []
            if not re.search(r'<html lang="nl"', html):
                iss.append("html-lang≠nl")
            if any(tok in html for tok in FR_LABEL_LEAK):
                iss.append("FR-fact-label-leak")
            if slug in beaches:
                if 'class="essentiel"' not in html:
                    iss.append("no-essentiel")
                if "plages-voisines" not in html:
                    iss.append("no-plages-voisines")
            if iss:
                rendered_issues.append({"slug": slug, "issues": iss})

    # write report
    out = {"published": n, "fully_nl_parallel": fully_parallel,
           "depth_gaps": depth_gaps, "rendered_issues": rendered_issues}
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, "reports", "nl-parity.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    lines = ["# NL parity audit (rendered NL vs FR)", "",
             "_© 2026 · Bleu canard édition · report-only_", "",
             f"- Published fiches: **{n}**",
             f"- Full NL content parity (no FR fallback on depth keys): **{fully_parallel}** ({100*fully_parallel//n if n else 0}%)",
             f"- Fiches with NL content gaps (render FR fallback): **{len(depth_gaps)}**",
             f"- Rendered structural issues: **{len(rendered_issues)}**", ""]
    if rendered_issues:
        lines += ["## Rendered structural issues (fix in builder)", ""]
        for r in rendered_issues:
            lines.append(f"- `{r['slug']}` — {', '.join(r['issues'])}")
        lines.append("")
    else:
        lines += ["## Rendered structural parity", "",
                  "✓ Every NL page carries `<html lang=\"nl\">`; localized fact-grid labels; "
                  "and every beach renders L'essentiel + Plages voisines in NL. "
                  "No systematic builder gap — the remaining gaps are content (untranslated fiches).", ""]
    nl_behind = [g for g in depth_gaps if g["nl_specific"]]
    cross = [g for g in depth_gaps if not g["nl_specific"]]
    lines += [f"## NL behind its siblings ({len(nl_behind)}) — EN/DE have it, NL doesn't (actionable)", ""]
    if nl_behind:
        lines.append("| fiche | NL keys to backfill |")
        lines.append("|---|---|")
        for g in nl_behind:
            lines.append(f"| `{g['slug']}` | {', '.join(g['nl_specific'])} |")
    else:
        lines.append("✓ NL is not behind any sibling locale — every key EN/DE carry, NL carries too.")
    lines += ["", f"## Cross-locale content gaps ({len(cross)}) — no locale translated these sections", ""]
    if cross:
        lines.append("| fiche | NL i18n? | missing depth keys |")
        lines.append("|---|---|---|")
        for g in cross:
            lines.append(f"| `{g['slug']}` | {'partial' if g['nl_present'] else 'absent'} | {', '.join(g['missing'])} |")
    else:
        lines.append("✓ none.")
    lines.append("")
    open(os.path.join(ROOT, "reports", "nl-parity.md"), "w", encoding="utf-8").write("\n".join(lines))

    print(f"audit_locale_parity: {n} published | NL-parallel {fully_parallel} | "
          f"content gaps {len(depth_gaps)} | rendered issues {len(rendered_issues)}")
    print("-> reports/nl-parity.md")


if __name__ == "__main__":
    main()
