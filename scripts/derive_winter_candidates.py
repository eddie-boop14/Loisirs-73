#!/usr/bin/env python3
"""derive_winter_candidates.py — HANDOFF-winter JOB B (report-before-apply).

The scaffolding (JOB A) ranks nothing empty; the rung is verified winter data on
the 98 WINTER_NODES. This tool reads the EXISTING French prose (i18n.fr:
when_to_visit, body, events, activities, best_season) for winter signals and
proposes facts.winter_* values — WITH the evidence snippet that triggered each,
and verify_flags for anything inferred. It never guesses silently and never
auto-applies. Mirrors seed_dt_partners.py's --report → --apply discipline.

    --report   parse prose → reports/winter-candidates.md (+ .json). $0, no writes.
    --apply    write facts.winter_* into Json/<slug>.json ONLY for candidates
               a human confirmed (confirmed:true in the .json, or --slug S).

Controlled vocab + node set come from build_ai_content (single source). Frozen
Mont-Blanc / Loi Montagne II are never written as data — snow_view stores the
token 'mont_blanc'; the label carries the frozen string.
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import build_ai_content as B  # noqa: E402

JSON_DIR = os.path.join(ROOT, "Json")
REPORT_MD = os.path.join(ROOT, "reports", "winter-candidates.md")
REPORT_JSON = os.path.join(ROOT, "reports", "winter-candidates.json")

# signal → (field, value). Patterns run on lowercased, tag-stripped FR prose.
INFRA_SIGNALS = [
    (r"raquette", "raquettes"),
    (r"ski\s+nordique", "ski_nordique"),
    (r"ski\s+de\s+fond", "ski_fond"),
    (r"ski\s+de\s+rando|ski\s+de\s+randonn", "ski_rando"),
    (r"chiens?\s+de\s+tra[iî]neau|\btra[iî]neau", "chiens_traineau"),
    (r"\bluge\b", "luge"),
]
ACCESS_SIGNALS = [
    (r"ferm[ée]\w*\s+(?:en\s+|l['’])?hiver|route\s+ferm|fermeture\s+hivernale|"
     r"inaccessible\s+(?:en\s+)?hiver", "closed"),
    (r"d[ée]neig|ouvert\s+toute\s+l['’]ann[ée]e|accessible\s+toute\s+l['’]ann[ée]e|"
     r"accessible\s+(?:en\s+|l['’])hiver|ouvert\s+l['’]hiver", "open"),
    (r"acc[èe]s\s+partiel|partiellement\s+(?:ouvert|accessible)", "partial"),
]
VIEW_SIGNALS = [
    (r"mont[\s-]?blanc", "mont_blanc"),
    (r"panorama\s+alpin|cha[iî]ne\s+des\s+alpes|massif\s+des\s+aravis|"
     r"vue\s+sur\s+les\s+alpes|aiguilles?\s+", "alpes"),
    (r"vue\s+\w*\s*sur\s+le\s+lac|panorama\s+\w*\s*lac|surplombe?\s+le\s+lac", "lac"),
]
TAG_RE = re.compile(r"<[^>]+>")


def fr_prose(d):
    fr = (d.get("i18n") or {}).get("fr") or {}
    parts = []
    for k in ("when_to_visit", "events"):
        v = fr.get(k)
        if isinstance(v, str):
            parts.append(v)
    b = fr.get("body")
    if isinstance(b, dict):
        parts.extend(str(x) for x in b.values())
    for a in (fr.get("activities") or []):
        if isinstance(a, dict):
            parts.append(f"{a.get('title', '')} {a.get('description', '')}")
    facts = fr.get("facts") or {}
    if facts.get("best_season"):
        parts.append(str(facts["best_season"]))
    text = TAG_RE.sub(" ", " ".join(parts))
    return re.sub(r"\s+", " ", text)


def snippet(text, pat):
    m = re.search(pat, text, re.I)
    if not m:
        return None
    s = max(0, m.start() - 35)
    e = min(len(text), m.end() + 35)
    return ("…" + text[s:e].strip() + "…")


def derive(d):
    """Return a proposal dict (or None if no winter signal at all)."""
    cat = d.get("category") or ""
    if cat not in B.WINTER_NODES:
        return None
    text = fr_prose(d).lower()
    name = (B.name_of(d) or "").lower()
    prop = {"slug": d["slug"], "category": cat, "evidence": {}, "verify_flags": []}

    infra = []
    for pat, tag in INFRA_SIGNALS:
        if re.search(pat, text):
            infra.append(tag)
            prop["evidence"][f"infra:{tag}"] = snippet(text, pat)
    if infra:
        prop["winter_infra"] = infra

    for pat, val in ACCESS_SIGNALS:
        if re.search(pat, text):
            prop["winter_access"] = val
            prop["evidence"]["access"] = snippet(text, pat)
            prop["verify_flags"].append("access inferred from prose — confirm")
            break

    # snow_view: only for viewpoints, and only if a panorama word is present
    if cat == "point-de-vue":
        for pat, val in VIEW_SIGNALS:
            if re.search(pat, text) or re.search(pat, name):
                prop["snow_view"] = val
                prop["evidence"]["snow_view"] = snippet(text, pat) or f"name:{name}"
                prop["verify_flags"].append(
                    f"snow_view={val} inferred — confirm the winter panorama is real")
                break

    # col_chains: a real col (name/prose says 'col')
    if re.search(r"\bcol\s+d", name) or re.search(r"\bau\s+col\b|\ble\s+col\b", text):
        prop["col_chains"] = True
        prop["evidence"]["col_chains"] = "name/prose references a col"

    has_signal = any(k in prop for k in
                     ("winter_infra", "winter_access", "snow_view", "col_chains"))
    return prop if has_signal else None


def load_fiches():
    out = []
    import glob
    for p in sorted(glob.glob(os.path.join(JSON_DIR, "*.json"))):
        try:
            out.append(json.load(open(p, encoding="utf-8")))
        except Exception:
            pass
    return out


def cmd_report():
    props = [p for p in (derive(d) for d in load_fiches()) if p]
    # rank: richest signal first
    props.sort(key=lambda p: -(len(p.get("winter_infra", []))
                               + ("winter_access" in p) + ("snow_view" in p)
                               + ("col_chains" in p)))
    os.makedirs(os.path.dirname(REPORT_MD), exist_ok=True)
    for p in props:
        p["confirmed"] = False           # human flips this to apply
    json.dump({"candidates": props}, open(REPORT_JSON, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    L = ["# Winter candidates — HANDOFF-winter JOB B (report, NOT applied)",
         "",
         f"{len(props)} of {sum(1 for d in load_fiches() if (d.get('category') or '') in B.WINTER_NODES)} "
         "winter nodes carry a winter signal in their FR prose. Nothing is written until",
         "you confirm: set `\"confirmed\": true` in reports/winter-candidates.json (or tell me",
         "which slugs), then `derive_winter_candidates.py --apply`. Equipment (Loi Montagne II)",
         "is a verified dept constant — always shown, not part of this data.",
         "",
         "| slug | cat | infra | access | snow_view | col | evidence |",
         "|---|---|---|---|---|---|---|"]
    for p in props:
        ev = " · ".join(f"{k}: {v}" for k, v in list(p["evidence"].items())[:2])
        L.append("| {slug} | {cat} | {infra} | {acc} | {sv} | {col} | {ev} |".format(
            slug=p["slug"], cat=p["category"],
            infra=", ".join(p.get("winter_infra", [])) or "—",
            acc=p.get("winter_access", "—"), sv=p.get("snow_view", "—"),
            col="yes" if p.get("col_chains") else "—",
            ev=ev.replace("|", "\\|")[:80]))
    open(REPORT_MD, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"[winter] {len(props)} candidates → {os.path.relpath(REPORT_MD, ROOT)} "
          f"(+ .json). $0, nothing applied. Confirm rows, then --apply.")
    # console preview
    for p in props[:12]:
        print(f"  {p['slug']:52} infra={p.get('winter_infra', [])} "
              f"access={p.get('winter_access', '-')} view={p.get('snow_view', '-')} "
              f"col={'Y' if p.get('col_chains') else '-'}")


def cmd_apply(only_slug=None, infra_only=False):
    if not os.path.exists(REPORT_JSON):
        sys.exit("[winter] no winter-candidates.json — run --report first")
    cands = json.load(open(REPORT_JSON, encoding="utf-8"))["candidates"]
    wrote = 0
    for p in cands:
        if only_slug and p["slug"] != only_slug:
            continue
        # infra_only: apply the DIRECT-evidence winter_infra rows (treated as
        # confirmed) and NOTHING else. The inferred access/snow_view/col_chains
        # stay in the report for a later human-verified pass.
        if infra_only:
            if not p.get("winter_infra"):
                continue
        elif not (p.get("confirmed") or (only_slug and p["slug"] == only_slug)):
            continue
        path = os.path.join(JSON_DIR, p["slug"] + ".json")
        d = json.load(open(path, encoding="utf-8"))
        facts = d.setdefault("i18n", {}).setdefault("fr", {}).setdefault("facts", {})
        applied = {}
        if "winter_infra" in p:
            facts["winter_infra"] = p["winter_infra"]; applied["winter_infra"] = p["winter_infra"]
        if not infra_only:
            if "winter_access" in p:
                facts["winter_access"] = p["winter_access"]; applied["winter_access"] = p["winter_access"]
            if "snow_view" in p:
                facts["snow_view"] = p["snow_view"]; applied["snow_view"] = p["snow_view"]
            if p.get("col_chains"):
                facts["col_chains"] = True; applied["col_chains"] = True
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        wrote += 1
        print(f"  applied {p['slug']}: {applied}")
    print(f"[winter] applied {wrote} candidate(s){' (infra-only)' if infra_only else ''}. "
          "Re-run build_all + gates.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--slug", help="apply just this slug (treats its proposal as confirmed)")
    ap.add_argument("--infra-only", action="store_true",
                    help="apply only the direct-evidence winter_infra rows")
    args = ap.parse_args()
    if args.report:
        cmd_report()
    elif args.apply:
        cmd_apply(only_slug=args.slug, infra_only=args.infra_only)
    else:
        ap.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
