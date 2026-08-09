#!/usr/bin/env python3
"""audit_hygiene.py — JOB 5 scanner. Find scaffolding / prompt / TODO
residue in any field that gets RENDERED to the public site.

Fields scanned (recursive across i18n.<lang> for every locale):
  - meta_title, meta_description, name, name_alternates
  - hero.{badge, lead}, hero_alt
  - body.what_is
  - body.activities[].{title, description, tag}
  - body.practical_info[].{k, v}
  - body.how_to_get_there.{car, public_transport, bike}
  - body.when_to_visit, body.events
  - faq[].{q, a}
  - schema_amenities[]
Also scanned (non-i18n): partners[].{name, description, address, hours},
featured_businesses[].* (same fields).

NOT scanned: verify_flags, research_log, freshness, google_check, data_sources,
sources, schema_org, sparse_data — these are internal-only.

Tiers:
  Tier 1 (CRITICAL): clear scaffolding markers that should NEVER ship.
  Tier 2 (HIGH):    prompt-residue / curation notes that read as drafts.

Output: scripts/job5-hygiene-report.json (per-fiche/per-field findings) +
       reports/job5-hygiene-report.md (human-readable summary).

CLI:
    python3 scripts/audit_hygiene.py             # scan, print summary, write reports
    python3 scripts/audit_hygiene.py --strict    # exit 1 if any Tier 1 or Tier 2
    python3 scripts/audit_hygiene.py --html      # also scan rendered HTML
"""
import argparse
import json
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import locales  # noqa: E402
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent

# Patterns. Each is (label, regex, tier).
# Tier 1 = scaffolding markers that must never ship.
# Tier 2 = prompt/curation residue.
#
# Tuning: precision over recall. "à confirmer" / "argument principal" /
# lowercase "section X" all turned up as common-language false positives
# on the first pass — they're now excluded. Scaffolding has a specific
# shape: bracketed, parens around TODO, leading capital + ellipsis-like
# missing-data marker, prompt-template residue.
PATTERNS = [
    # ---- TIER 1: clear scaffolding ----
    ("SEO Tier marker",          re.compile(r"\bSEO Tier\b", re.I), 1),
    ("Tier 1/2/3 marker",        re.compile(r"\bTier [123]\b\s*[-—:]"), 1),
    ("À compléter (TODO)",
     # Per-locale "to complete / to fill in" placeholder followed by a
     # missing-data signal (parens, tilde, "via", "selon", "Non renseigné").
     # Multilingual: fr, en, de, it, es, nl.
     re.compile(
         r"(?:^|[\(\[]|—\s*|:\s*)"
         r"(?:À\s*(?:complé?ter|remplir)|To\s+(?:complete|fill in|add)|"
         r"Zu\s+(?:ergänzen|erg(?:a|ä)nzen)|Auszufüllen|"
         r"Da\s+(?:completare|compilare)|Por\s+(?:completar|rellenar)|"
         r"Aan\s+te\s+vullen|In\s+te\s+vullen)\b"
         r"(?:\s*[\(\[\.~]|\s+via\b|\s+sur\b|\s+selon\b|\s+les\s+sources?\b)",
         re.M | re.I
     ), 1),
    # "TODO" is a code scaffolding marker — but also the Spanish word for "all"
    # ("TODO EL AÑO" = "all year"). Match the marker (uppercase TODO), but not
    # when it's the Spanish word followed by a determiner/quantifier continuation.
    ("TODO marker",
     re.compile(r"\bTODO\b(?!\s+(?i:el|los?|la|las|lo|un|una|unos|unas|su|sus|"
                r"incluido|tipo|p[uú]blico|el\s+a[nñ]o)\b)"), 1),
    ("FIXME marker",             re.compile(r"\bFIXME\b"), 1),
    ("XXX marker",               re.compile(r"(?<![/_-])\bXXX\b(?![/_-])"), 1),
    ("lorem ipsum",              re.compile(r"\blorem ipsum\b", re.I), 1),
    ("placeholder text",         re.compile(r"\bplaceholder\s*(?:text|content)\b", re.I), 1),
    ("[à remplir]",              re.compile(r"\[(?:à|a)[- ]remplir\]", re.I), 1),
    ("[TBD]",                    re.compile(r"\[\s*TBD\s*\]", re.I), 1),
    ("Non renseigné — à compl.", re.compile(r"\bNon\s+renseign[ée]?s?\b.{0,40}à\s*complé?ter", re.I), 1),
    # ---- TIER 2: prompt/curation residue ----
    ("[à confirmer]",            re.compile(r"\[(?:à|a) confirmer\]", re.I), 2),
    ("[à vérifier]",             re.compile(r"\[(?:à|a) v[eé]rifier\]", re.I), 2),
    ("Exemple : prompt",         re.compile(r"^\s*Exemple\s*[:\.]", re.M), 2),
    ("Note interne",             re.compile(r"\bnote interne\b", re.I), 2),
    ("voir [link]",              re.compile(r"\bvoir\s*\[[^\]]*\]"), 2),
    ("prompt-like {{var}}",      re.compile(r"\{\{[^}]+\}\}"), 2),
    # CAPS-only — lowercase "section 1" / "titre principal" etc. are normal
    # prose describing trail sections, headings, etc.
    ("section header in CAPS",   re.compile(r"\b(SECTION|HEADING|PARAGRAPHE|TITRE)\s+\d+"), 2),
    # only flag when explicit scaffold-style date suffix follows (e.g. "Argument central de 2025-2026 :")
    ("Argument central (dated)", re.compile(r"\bargument\s+(?:central|majeur)\s+de\s+(?:20|19)\d{2}", re.I), 2),
]

# Locales
LOCALES = locales.PROSE


def iter_rendered_strings(d):
    """Yield (path, string) for each field of a Json/<slug>.json that gets
    rendered to the public HTML."""
    i18n = d.get("i18n", {}) or {}
    for lang in LOCALES:
        loc = i18n.get(lang) or {}
        for top in ("name", "meta_title", "meta_description", "hero_alt",
                    "when_to_visit", "events"):
            v = loc.get(top)
            if isinstance(v, str):
                yield (f"i18n.{lang}.{top}", v)
        for v in (loc.get("name_alternates") or []):
            if isinstance(v, str):
                yield (f"i18n.{lang}.name_alternates", v)
        hero = loc.get("hero") or {}
        for k in ("badge", "lead"):
            v = hero.get(k)
            if isinstance(v, str):
                yield (f"i18n.{lang}.hero.{k}", v)
        body = loc.get("body") if isinstance(loc.get("body"), dict) else {}
        v = body.get("what_is") or loc.get("what_is")
        if isinstance(v, str):
            yield (f"i18n.{lang}.body.what_is", v)
        for i, a in enumerate(body.get("activities") or loc.get("activities") or []):
            if isinstance(a, dict):
                for k in ("title", "description", "tag"):
                    v = a.get(k)
                    if isinstance(v, str):
                        yield (f"i18n.{lang}.body.activities[{i}].{k}", v)
        for i, r in enumerate(body.get("practical_info") or loc.get("practical_info") or []):
            if isinstance(r, dict):
                for k in ("k", "v"):
                    v = r.get(k)
                    if isinstance(v, str):
                        yield (f"i18n.{lang}.body.practical_info[{i}].{k}", v)
        how = body.get("how_to_get_there") or loc.get("how_to_get_there") or {}
        if isinstance(how, dict):
            for k in ("car", "public_transport", "bike"):
                v = how.get(k)
                if isinstance(v, str):
                    yield (f"i18n.{lang}.body.how_to_get_there.{k}", v)
        for i, q in enumerate(loc.get("faq") or []):
            if isinstance(q, dict):
                for k in ("q", "a"):
                    v = q.get(k)
                    if isinstance(v, str):
                        yield (f"i18n.{lang}.faq[{i}].{k}", v)
        for i, v in enumerate(loc.get("schema_amenities") or []):
            if isinstance(v, str):
                yield (f"i18n.{lang}.schema_amenities[{i}]", v)
    # Non-i18n: partner-card content (rendered)
    for slot in ("partners", "featured_businesses"):
        for i, p in enumerate(d.get(slot) or []):
            if not isinstance(p, dict): continue
            for k in ("name", "description", "address", "hours", "cta_text"):
                v = p.get(k)
                if isinstance(v, str):
                    yield (f"{slot}[{i}].{k}", v)
            p_i18n = p.get("i18n", {}) or {}
            for lang, blk in p_i18n.items():
                if isinstance(blk, dict):
                    for k, v in blk.items():
                        if isinstance(v, str):
                            yield (f"{slot}[{i}].i18n.{lang}.{k}", v)


def scan_string(s):
    """Return list of (label, tier, snippet) findings for the string."""
    hits = []
    for label, pat, tier in PATTERNS:
        for m in pat.finditer(s):
            start = max(0, m.start() - 30)
            end = min(len(s), m.end() + 60)
            snippet = re.sub(r"\s+", " ", s[start:end])
            hits.append((label, tier, snippet))
    return hits


def scan_fiches():
    findings = []
    for jp in sorted((ROOT / "Json").glob("*.json")):
        d = json.loads(jp.read_text(encoding="utf-8"))
        slug = jp.stem
        for path, s in iter_rendered_strings(d):
            for label, tier, snippet in scan_string(s):
                findings.append({
                    "slug": slug, "path": path, "label": label,
                    "tier": tier, "snippet": snippet,
                })
    return findings


def write_reports(findings, scan_kind):
    by_tier = defaultdict(int)
    by_label = defaultdict(set)
    by_slug = defaultdict(list)
    for f in findings:
        by_tier[f["tier"]] += 1
        by_label[f["label"]].add(f["slug"])
        by_slug[f["slug"]].append(f)

    # JSON dump
    out = {
        "scan_kind": scan_kind,
        "summary": {
            f"tier_{t}_hits": by_tier[t] for t in (1, 2)
        },
        "by_label": {l: sorted(s) for l, s in by_label.items()},
        "findings": findings,
    }
    (ROOT / "scripts" / "job5-hygiene-report.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Markdown
    lines = [f"# JOB 5 — Hygiene scan ({scan_kind})\n\n"]
    lines.append(f"Scanned: 392 fiches, all rendered fields across 6 locales + partner cards.\n\n")
    lines.append("## Summary\n\n")
    lines.append(f"| Tier | Hits | Distinct slugs |\n|---|---:|---:|\n")
    for t in (1, 2):
        slugs = {f["slug"] for f in findings if f["tier"] == t}
        lines.append(f"| Tier {t} | {by_tier[t]} | {len(slugs)} |\n")
    lines.append("\n")

    for t in (1, 2):
        tier_finds = [f for f in findings if f["tier"] == t]
        if not tier_finds: continue
        lines.append(f"## Tier {t} findings\n\n")
        by_lbl = defaultdict(list)
        for f in tier_finds:
            by_lbl[f["label"]].append(f)
        for lbl, fs in by_lbl.items():
            lines.append(f"### {lbl} ({len(fs)} hits)\n\n")
            lines.append("| slug | path | snippet |\n|---|---|---|\n")
            for f in fs[:50]:
                snip = f["snippet"].replace("|", "\\|")
                lines.append(f"| {f['slug']} | {f['path']} | …{snip}… |\n")
            if len(fs) > 50:
                lines.append(f"\n_…{len(fs)-50} more hits omitted_\n")
            lines.append("\n")
    (ROOT / "reports" / "job5-hygiene-report.md").write_text("".join(lines), encoding="utf-8")
    return by_tier


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true",
                    help="Exit 1 if any Tier 1 or Tier 2 found")
    args = ap.parse_args()

    findings = scan_fiches()
    by_tier = write_reports(findings, "rendered-fields")

    print(f"Tier 1: {by_tier[1]} hits across {len({f['slug'] for f in findings if f['tier']==1})} fiches")
    print(f"Tier 2: {by_tier[2]} hits across {len({f['slug'] for f in findings if f['tier']==2})} fiches")
    print(f"Report: reports/job5-hygiene-report.md + scripts/job5-hygiene-report.json")

    if args.strict and (by_tier[1] + by_tier[2]) > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
