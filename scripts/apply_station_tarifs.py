#!/usr/bin/env python3
"""apply_station_tarifs.py — Tarifs forfaits des 28 stations (PART 1 APPLY).

Apply the harvested pass-price payload (data/station-tarifs-harvest.json) onto
the price fields of `category: station` fiches. Two modes, same doctrine as
apply_winter_facts.py:

  --report : diff payload vs current Json/<slug>.json → reports/tarifs-apply-report.md
             (état par station : PENDING / APPLIED / EMPTY). Eddie reviews THIS.
  --apply  : write ONLY price_tiers / price_from / price_currency, append the
             harvest source_url to `sources` if absent, set the short
             i18n.<lang>.facts.tarif prose for every language carried by the
             payload row, and append a per-slug research_log entry.

Payload row states (the « 3 états » contract):
  "2026-27" : next-season grid published — tiers land as-is.
  "2025-26" : only last season's grid online — every tier note AND every prose
              line MUST start with "Tarifs saison 2025-26 — " (validated here,
              refused otherwise).
  "null"    : nothing published yet — tiers stay empty, only the
              "Forfaits 2026-27 publiés à l'automne…" prose lands.

Guards: category must be "station"; tiers are copied VERBATIM from the payload
(nothing invented, no shape surgery); malformed rows are skipped and listed.
Partner blocks and every non-price field are never touched.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_DIR = os.path.join(ROOT, "Json")
PAYLOAD = os.path.join(ROOT, "data", "station-tarifs-harvest.json")
REPORT = os.path.join(ROOT, "reports", "stations-tarifs-harvest.md")
TODAY = "2026-07-20"

STATES = ("2026-27", "2025-26", "null")
PREFIX_2526 = "Tarifs saison 2025-26 — "
# Roster law: the tarif prose must cover EVERY published language, not a frozen
# literal that silently drifts from the roster. Derived from locales.VISIBLE so
# a new published lane can never again be left empty (the pl/ja/ar/he gap).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import locales as _locales  # noqa: E402
LANGS = tuple(_locales.VISIBLE)


def load_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def fiche_path(slug):
    return os.path.join(JSON_DIR, f"{slug}.json")


def tier_ok(t):
    return (isinstance(t, dict)
            and isinstance(t.get("name"), str) and t["name"].strip()
            and isinstance(t.get("price"), (int, float)) and t["price"] >= 0
            and (t.get("note") is None or isinstance(t.get("note"), str)))


def row_problems(spec):
    """Validate one payload row against the 3-états contract. [] = clean."""
    errs = []
    state = spec.get("state")
    if state not in STATES:
        errs.append(f"state={state!r} not in {STATES}")
        return errs
    tiers = spec.get("tiers")
    if not isinstance(tiers, list):
        errs.append("tiers is not a list")
        return errs
    if state == "null":
        if tiers:
            errs.append("state null but tiers non-empty")
    else:
        if not tiers:
            errs.append(f"state {state} but tiers empty")
        if not spec.get("source_url"):
            errs.append("tiers without source_url")
        if not spec.get("evidence"):
            errs.append("tiers without evidence quote")
        for t in tiers:
            if not tier_ok(t):
                errs.append(f"malformed tier {t!r}")
        if len(tiers) > 6:
            errs.append(f"{len(tiers)} tiers (max 6)")
    if state == "2025-26":
        for t in tiers:
            if not (t.get("note") or "").startswith(PREFIX_2526):
                errs.append(f"2025-26 tier note missing prefix: {t.get('name')!r}")
    prose = spec.get("tarif_i18n") or {}
    if not isinstance(prose, dict) or not prose.get("fr"):
        errs.append("tarif_i18n.fr prose missing")
    for lg, txt in prose.items():
        if lg not in LANGS:
            errs.append(f"unknown lang {lg!r} in tarif_i18n")
        elif not isinstance(txt, str) or not txt.strip():
            errs.append(f"empty tarif_i18n[{lg!r}]")
    if state == "2025-26" and prose.get("fr") and not prose["fr"].startswith(PREFIX_2526):
        errs.append("2025-26 fr prose missing prefix")
    return errs


def wanted_fields(spec):
    """The exact (field → value) writes this row asks for on the fiche root."""
    tiers = [{"name": t["name"], "price": float(t["price"]),
              "note": t.get("note") or None} for t in spec.get("tiers") or []]
    if not tiers:
        return {}
    return {
        "price_tiers": tiers,
        "price_from": min(t["price"] for t in tiers),
        "price_currency": "EUR",
    }


def plan_rows():
    """Return (rows, skips). Row: dict(slug, state, changes[(field,old,new)],
    applied[(field,val)], prose_changes[lang], source_url)."""
    payload = load_json(PAYLOAD)["payload"]
    rows, skips = [], []
    for slug, spec in sorted(payload.items()):
        p = fiche_path(slug)
        if not os.path.exists(p):
            skips.append((slug, "MISSING fiche file"))
            continue
        d = load_json(p)
        if d.get("category") != "station":
            skips.append((slug, f"non-station category [{d.get('category')}]"))
            continue
        errs = row_problems(spec)
        if errs:
            skips.append((slug, "payload row refused: " + "; ".join(errs)))
            continue
        changes, applied = [], []
        for field, new in wanted_fields(spec).items():
            old = d.get(field)
            if old != new:
                changes.append((field, old, new))
            else:
                applied.append((field, new))
        prose_changes, prose_applied = [], []
        for lg, txt in (spec.get("tarif_i18n") or {}).items():
            cur = (((d.get("i18n") or {}).get(lg) or {}).get("facts") or {}).get("tarif")
            (prose_applied if cur == txt else prose_changes).append(lg)
        src = spec.get("source_url") or ""
        rows.append({
            "slug": slug, "state": spec["state"], "changes": changes,
            "applied": applied, "prose_changes": prose_changes,
            "prose_applied": prose_applied,
            "src": src, "src_new": bool(src) and src not in (d.get("sources") or []),
        })
    return rows, skips


def row_state(r):
    if r["changes"] or r["prose_changes"]:
        return "PENDING"
    if r["applied"] or r["prose_applied"]:
        return "APPLIED"
    return "EMPTY"


def fmt(v):
    if v is None:
        return "∅"
    if isinstance(v, list):
        return f"[{len(v)} tiers]"
    return str(v)


def write_report(rows, skips):
    by_state = {s: [r for r in rows if r["state"] == s] for s in STATES}
    n_pending = sum(1 for r in rows if row_state(r) == "PENDING")
    n_applied = sum(1 for r in rows if row_state(r) == "APPLIED")
    L = []
    L.append("# Tarifs stations — harvest report (PART 1)\n")
    L.append(f"Payload: `data/station-tarifs-harvest.json` · generated {TODAY}\n")
    L.append(f"- Stations in payload: **{len(rows)}** — grille 2026-27: "
             f"**{len(by_state['2026-27'])}** · grille 2025-26 (préfixée): "
             f"**{len(by_state['2025-26'])}** · rien publié (prose automne): "
             f"**{len(by_state['null'])}**\n")
    L.append(f"- PENDING (à appliquer): **{n_pending}** · APPLIED (déjà en ligne): "
             f"**{n_applied}** · rows refused/skipped: **{len(skips)}**\n")
    L.append("\nÉtats par ligne : `∅ → value` = en attente d'apply · `= value "
             "(appliqué)` = déjà dans la fiche (post-apply). Un rapport où tout est "
             "APPLIED est un état des lieux, pas un no-op. Aucun prix n'est écrit "
             "sans source officielle + citation dans le payload.\n")
    for state, title in (("2026-27", "Grille 2026-27 publiée"),
                         ("2025-26", "Grille 2025-26 seulement (notes préfixées)"),
                         ("null", "Rien de publié — prose « à l'automne »")):
        L.append(f"\n---\n\n## {title}\n")
        L.append("\n| slug | état | field | valeur | prose langs | source |\n"
                 "|---|---|---|---|---|---|\n")
        for r in by_state[state]:
            pl = ",".join(r["prose_changes"]) or "—"
            src = r["src"] + (" *(new)*" if r["src_new"] else "") if r["src"] else "—"
            wrote_line = False
            for (f, o, n) in r["changes"]:
                L.append(f"| `{r['slug']}` | PENDING | {f} | {fmt(o)} → **{fmt(n)}** | {pl} | {src} |\n")
                wrote_line = True
            for (f, v) in r["applied"]:
                L.append(f"| `{r['slug']}` | APPLIED | {f} | = **{fmt(v)}** | {pl} | {src} |\n")
                wrote_line = True
            if not wrote_line:
                st = row_state(r)
                L.append(f"| `{r['slug']}` | {st} | (prose seule) | — | {pl} | {src} |\n")
        if not by_state[state]:
            L.append("| — | — | — | — | — | (none) |\n")
    if skips:
        L.append("\n---\n\n## Refused / skipped rows\n\n")
        for slug, why in skips:
            L.append(f"- `{slug}` — {why}\n")
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("".join(L))
    return n_pending, n_applied


def attest():
    """Count station fiches and how many already carry price_tiers."""
    n = with_tiers = 0
    for p in os.listdir(JSON_DIR):
        if not p.endswith(".json"):
            continue
        d = load_json(os.path.join(JSON_DIR, p))
        if d.get("category") == "station":
            n += 1
            if d.get("price_tiers"):
                with_tiers += 1
    return n, with_tiers


def self_check(rows, tiers_before):
    """Same lesson as winter apply: a diff claiming 0 pending against an empty
    corpus while the payload carries tiers is impossible — refuse to lie."""
    payload_tier_rows = [r for r in rows if r["state"] != "null"]
    n_pending = sum(1 for r in rows if row_state(r) == "PENDING")
    if tiers_before == 0 and n_pending == 0 and payload_tier_rows:
        print("SELF-CHECK FAIL: no station fiche carries price_tiers yet the diff "
              f"reports 0 pending against {len(payload_tier_rows)} payload rows with "
              "tiers. Impossible report — refusing to write it.", file=sys.stderr)
        sys.exit(1)


def do_apply(rows):
    payload = load_json(PAYLOAD)["payload"]
    applied = []
    for r in rows:
        if row_state(r) != "PENDING":
            continue
        slug = r["slug"]
        d = load_json(fiche_path(slug))
        spec = payload[slug]
        for field, new in wanted_fields(spec).items():
            d[field] = new
        src = spec.get("source_url")
        if src:
            srcs = d.setdefault("sources", [])
            if src not in srcs:
                srcs.append(src)
        for lg, txt in (spec.get("tarif_i18n") or {}).items():
            (d.setdefault("i18n", {}).setdefault(lg, {})
              .setdefault("facts", {}))["tarif"] = txt
        d.setdefault("research_log", []).append({
            "date": TODAY, "by": "tarifs PART 1 apply",
            "note": f"forfaits {spec['state']} — {src or 'aucune grille publiée'}",
        })
        with open(fiche_path(slug), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
            f.write("\n")
        applied.append(slug)
    return applied


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    n_stations, tiers_before = attest()
    print(f"re-attest: {n_stations} station fiches · {tiers_before} already carry price_tiers")
    rows, skips = plan_rows()
    if args.apply:
        applied = do_apply(rows)
        print(f"APPLIED {len(applied)} stations")
        if applied:
            print("  " + ", ".join(applied))
        if skips:
            print(f"skipped {len(skips)}: " + "; ".join(f"{s} ({w})" for s, w in skips))
    else:
        self_check(rows, tiers_before)
        n_pending, n_applied = write_report(rows, skips)
        print(f"REPORT → {os.path.relpath(REPORT, ROOT)}")
        print(f"  {len(rows)} stations · PENDING {n_pending} · APPLIED {n_applied} · "
              f"{len(skips)} refused/skipped")


if __name__ == "__main__":
    main()
