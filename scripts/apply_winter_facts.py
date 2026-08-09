#!/usr/bin/env python3
"""apply_winter_facts.py — HANDOFF JOB B APPLY.

Apply the verified winter payload (data/winter-facts-verified.json) onto the
four winter schema fields of WINTER_NODES fiches. Two modes:

  --report : diff payload vs current Json/<slug>.json facts → reports/winter-apply-report.md
             (sensitive closed/partial access rows first). Eddie reviews THIS.
  --apply  : write ONLY winter_access / snow_view / winter_infra / col_chains from
             the payload (fields absent from a row are left untouched), validate
             against the controlled vocab, append a per-slug research_log entry, and
             flip matching reports/winter-candidates.json rows to confirmed:true.

Category guard: writes only where category ∈ WINTER_NODES; other rows are skipped
and listed. Partner blocks are never touched. Re-attests node counts before acting.
"""
import argparse
import datetime
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import build_ai_content as B  # single source of vocab + WINTER_NODES

JSON_DIR = os.path.join(ROOT, "Json")
PAYLOAD = os.path.join(ROOT, "data", "winter-facts-verified.json")
CANDIDATES = os.path.join(ROOT, "reports", "winter-candidates.json")
REPORT = os.path.join(ROOT, "reports", "winter-apply-report.md")
FIELDS = ("winter_access", "snow_view", "winter_infra", "col_chains")
TODAY = "2026-07-16"


def load_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def fiche_path(slug):
    return os.path.join(JSON_DIR, f"{slug}.json")


def vocab_ok(field, value):
    if field == "winter_access":
        return value in B.WINTER_ACCESS
    if field == "snow_view":
        return value in B.SNOW_VIEW
    if field == "winter_infra":
        return isinstance(value, list) and all(x in B.WINTER_INFRA for x in value)
    if field == "col_chains":
        return isinstance(value, bool)
    return False


def current_facts(d):
    return ((d.get("i18n") or {}).get("fr") or {}).get("facts") or {}


def plan_rows():
    """Return (rows, skips). Each row: dict(slug, category, changes[(field,old,new)],
    src, stage, sensitive, winter_node)."""
    payload = load_json(PAYLOAD)["payload"]
    rows, skips = [], []
    for slug, spec in payload.items():
        p = fiche_path(slug)
        if not os.path.exists(p):
            skips.append((slug, "MISSING fiche file"))
            continue
        d = load_json(p)
        cat = d.get("category")
        if cat not in B.WINTER_NODES:
            skips.append((slug, f"non-WINTER_NODES category [{cat}]"))
            continue
        fk = current_facts(d)
        changes, applied = [], []
        for field in FIELDS:
            if field not in spec:
                continue
            new = spec[field]
            if not vocab_ok(field, new):
                skips.append((slug, f"{field}={new!r} OFF controlled vocab"))
                changes = None
                break
            old = fk.get(field)
            if old != new:
                changes.append((field, old, new))
            else:
                # payload value already sits in the fiche — the row is DONE,
                # not a no-op. Post-apply reports must say so explicitly
                # (WORK-ORDER v3 lesson: ambiguity here read as fake success).
                applied.append((field, new))
        if changes is None:
            continue
        acc = spec.get("winter_access")
        rows.append({
            "slug": slug, "category": cat, "changes": changes, "applied": applied,
            "src": spec.get("src", ""), "stage": spec.get("stage"),
            "sensitive": acc in ("closed", "partial"),
        })
    return rows, skips


def fmt(v):
    if v is None:
        return "∅"
    if isinstance(v, list):
        return "[" + ", ".join(v) + "]" if v else "[]"
    return str(v)


def row_state(r):
    """PENDING (has un-applied changes) · APPLIED (all payload fields live) · EMPTY."""
    if r["changes"]:
        return "PENDING"
    if r["applied"]:
        return "APPLIED"
    return "EMPTY"


def write_report(rows, skips):
    sens = [r for r in rows if r["sensitive"]]
    rest = [r for r in rows if not r["sensitive"]]
    n_pending = sum(1 for r in rows if row_state(r) == "PENDING")
    n_applied = sum(1 for r in rows if row_state(r) == "APPLIED")
    n_change = n_pending
    L = []
    L.append("# Winter facts — APPLY report (JOB B)\n")
    L.append(f"Payload: `data/winter-facts-verified.json` · generated {TODAY}\n")
    L.append(f"- Winter nodes touched: **{len(rows)}** · PENDING (à appliquer): **{n_pending}** "
             f"· APPLIED (déjà en ligne): **{n_applied}** · category/vocab skips: **{len(skips)}**\n")
    L.append("\nÉtats par ligne : `∅ → value` = en attente d'apply · `= value (appliqué)` = "
             "la valeur du payload est déjà dans la fiche (post-apply). Un rapport où tout "
             "est APPLIED est un état des lieux, pas un no-op.\n")
    L.append("\n---\n")
    L.append("\n## ⚑ SENSITIVE — access = closed / partial (signature Eddie)\n")
    L.append("Les lignes les plus lourdes du site. PENDING = rien ne part sans signature ; "
             "APPLIED = déjà en ligne, la signature confirme l'état publié.\n")
    L.append("\n| slug | état | field | valeur | source |\n|---|---|---|---|---|\n")
    for r in sens:
        for (f, o, n) in r["changes"]:
            L.append(f"| `{r['slug']}` | PENDING | {f} | {fmt(o)} → **{fmt(n)}** | {r['src']} |\n")
        for (f, v) in r["applied"]:
            L.append(f"| `{r['slug']}` | APPLIED | {f} | = **{fmt(v)}** | {r['src']} |\n")
    if not sens:
        L.append("| — | — | — | — | (none) |\n")
    L.append("\n---\n")
    L.append("\n## CONFIRM-grade rows (official sourcing)\n")
    L.append("\n| slug | stage | état | field | valeur | source |\n|---|---|---|---|---|---|\n")
    for r in rest:
        for (f, o, n) in r["changes"]:
            L.append(f"| `{r['slug']}` | {r['stage']} | PENDING | {f} | {fmt(o)} → **{fmt(n)}** | {r['src']} |\n")
        for (f, v) in r["applied"]:
            L.append(f"| `{r['slug']}` | {r['stage']} | APPLIED | {f} | = **{fmt(v)}** | {r['src']} |\n")
        if not r["changes"] and not r["applied"]:
            L.append(f"| `{r['slug']}` | {r['stage']} | EMPTY | — | payload sans champ winter | {r['src']} |\n")
    if skips:
        L.append("\n---\n\n## Skipped (category guard / vocab)\n\n")
        for slug, why in skips:
            L.append(f"- `{slug}` — {why}\n")
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("".join(L))
    return sens, rest, n_change


def self_check(rows, applied_before):
    """LESSON (WORK-ORDER v3): a report that can claim success against an empty
    target is a liar with a green checkmark. If the corpus carries NO applied
    winter values AND the diff claims nothing is pending while the payload has
    winter fields, the report is impossible — exit loudly."""
    payload_winter_rows = [r for r in rows if r["changes"] or r["applied"]]
    n_pending = sum(1 for r in rows if row_state(r) == "PENDING")
    if applied_before == 0 and n_pending == 0 and payload_winter_rows:
        print("SELF-CHECK FAIL: corpus targets are EMPTY yet the diff reports 0 pending "
              f"changes against {len(payload_winter_rows)} payload rows carrying winter "
              "fields. This report is impossible — the differ is comparing the wrong "
              "thing. Refusing to write a lying report.", file=sys.stderr)
        sys.exit(1)


def do_apply(rows):
    payload = load_json(PAYLOAD)["payload"]
    applied = []
    for r in rows:
        slug = r["slug"]
        d = load_json(fiche_path(slug))
        spec = payload[slug]
        facts = d.setdefault("i18n", {}).setdefault("fr", {}).setdefault("facts", {})
        for field in FIELDS:
            if field in spec:
                facts[field] = spec[field]
        d.setdefault("research_log", []).append({
            "date": TODAY, "by": "JOB B apply", "note": spec.get("src", ""),
        })
        with open(fiche_path(slug), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
            f.write("\n")
        applied.append(slug)
    # flip winter-candidates confirmed flags
    flipped = 0
    if os.path.exists(CANDIDATES):
        cand = load_json(CANDIDATES)
        aset = set(applied)
        for row in cand.get("candidates", []):
            want = row.get("slug") in aset
            if row.get("confirmed") != want:
                row["confirmed"] = want
                if want:
                    flipped += 1
            elif "confirmed" not in row:
                row["confirmed"] = want
                if want:
                    flipped += 1
        with open(CANDIDATES, "w", encoding="utf-8") as f:
            json.dump(cand, f, ensure_ascii=False, indent=2)
            f.write("\n")
    return applied, flipped


def attest():
    n = 0
    applied_vals = 0
    for p in os.listdir(JSON_DIR):
        if not p.endswith(".json"):
            continue
        d = load_json(os.path.join(JSON_DIR, p))
        if d.get("category") in B.WINTER_NODES:
            n += 1
            fk = current_facts(d)
            if any(fk.get(f) not in (None, [], False) for f in
                   ("winter_access", "snow_view", "winter_infra")):
                applied_vals += 1
    return n, applied_vals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    nodes, applied_before = attest()
    print(f"re-attest: {nodes} winter nodes · {applied_before} already carry applied values")
    rows, skips = plan_rows()
    if args.apply:
        applied, flipped = do_apply(rows)
        print(f"APPLIED {len(applied)} slugs · flipped {flipped} winter-candidates rows to confirmed")
        print("  " + ", ".join(applied))
        if skips:
            print(f"skipped {len(skips)}: " + "; ".join(f"{s} ({w})" for s, w in skips))
    else:
        self_check(rows, applied_before)
        sens, rest, n_change = write_report(rows, skips)
        n_applied = sum(1 for r in rows if row_state(r) == "APPLIED")
        print(f"REPORT → {os.path.relpath(REPORT, ROOT)}")
        print(f"  {len(rows)} winter-node rows · PENDING {n_change} · APPLIED {n_applied} · "
              f"{len(sens)} SENSITIVE (closed/partial) · {len(skips)} skips")


if __name__ == "__main__":
    main()
