#!/usr/bin/env python3
"""derive_access_cost.py — the ONE derived access-cost model (§2 the-one-law).

SPEC (this docstring is the artifact; the code implements it, nothing else does).

Cost was smeared across three hand-varied encodings — `schema_org.is_free`
(bool, sometimes the *string* "True"/"False", sometimes null), free-text
`facts.access`/`facts.tarif`, and `price_from`/`price_tiers`. Identical
real-world patterns got different treatments, which drifted the manifest,
mis-populated the free hub, and flattened "free 9 months, paid only
9h30–17h30 in July–August" (plage de Saint-Jorioz) into a bare "paid".

This module makes cost a SINGLE, BUILD-DERIVED value. One state per fiche,
computed from the authoritative fields — never hand-set, so it cannot drift.

    STATE          meaning                                      free hub?  schema is_free
    free           free entry, year-round                          ✅         true
    free_seasonal  free entry off-season, paid in a peak window     ✅ (badge) false
    paid           paid entry (incl. seasonally-operated-but-       ❌         false
                   always-paid: canyoning, summer-only museums)

Sub-fields (data, not prose):
    paid_window  = {"from","to","hours"} | null   — the peak paid window
    extra_costs  = [ "parking"|"rental"|"guided"|"activity", … ]  — a free
                   entry may still carry OPTIONAL side costs; they are
                   disclosed, never a reason to leave the free hub.

DERIVATION (deterministic; authoritative inputs only):
  1. is_free := schema_org.is_free coerced to bool ("True"/"False" strings and
     null tolerated; null → derive from price).
  2. is_free True  → `free`. Any price_from/tiers are OPTIONAL side costs, not
     entry — classified into extra_costs (the human already asserted free entry).
  3. is_free False → paid of some kind:
        • category ∈ {plage, lac} AND the access/tarif prose shows a SEASONAL
          marker (saison estivale · hors saison · payant juil-août · libre
          sept-juin) → `free_seasonal` (+ paid_window parsed from the prose).
          A lakeshore is freely walkable off-season; only the staffed summer
          zone is ticketed.
        • else → `paid`.
  4. is_free null → price entry signal → `paid` else `free`; flagged for review.

Read-only by default (--report). --apply writes api/lieu/<slug>.json.access_cost
and is idempotent. The Json/ fiche keeps only the authoritative INPUTS; the
derived state is a build artifact, per the law.
"""
import argparse
import json
import os
import re
import sys
from glob import glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_DIR = os.path.join(ROOT, "Json")
API_DIR = os.path.join(ROOT, "api", "lieu")

SEASONAL_CATS = {"plage", "lac"}
# prose that means "paid only in the summer season" (→ free the rest of the year)
SEASONAL_RE = re.compile(
    r"saison estivale|hors[- ]saison|sept-?juin|payant[e]?\s*\(?\s*(juil|ao[uû]t|été|ete|estiv|saison)"
    r"|(juil|ao[uû]t|été|ete|estiv|haute saison)\s*[)\-–·].*payant|libre\s*\(?\s*sept",
    re.I)
# a paid window like "1er juillet – 31 août, 9h30–17h30"
WINDOW_DATES_RE = re.compile(
    r"(1\s*er\s*juillet|d[ée]but juillet|juil)[^0-9]{0,20}(31\s*ao[uû]t|fin ao[uû]t|ao[uû]t)", re.I)
WINDOW_HOURS_RE = re.compile(r"(\d{1,2}\s*h\s*\d{0,2})\s*[–\-àa]{1,3}\s*(\d{1,2}\s*h\s*\d{0,2})")
EXTRA_RE = {
    "parking": re.compile(r"parking\s*(payant|:.*€|.*payant)|payant.{0,10}parking", re.I),
    "rental":  re.compile(r"location|louer|rental", re.I),
    "guided":  re.compile(r"guid[ée]|sortie guid|encadr", re.I),
}


def coerce_bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        if v.strip().lower() == "true":
            return True
        if v.strip().lower() == "false":
            return False
    return None


def entry_price_present(d):
    try:
        if d.get("price_from") is not None and float(d["price_from"]) > 0:
            return True
    except (TypeError, ValueError):
        pass
    for t in (d.get("price_tiers") or []):
        amt = t.get("amount", t.get("price"))
        try:
            if amt is not None and float(amt) > 0:
                return True
        except (TypeError, ValueError):
            pass
    return False


def prose_of(d):
    fa = ((d.get("i18n") or {}).get("fr") or {}).get("facts") or {}
    return " · ".join(str(fa.get(k) or "") for k in ("access", "tarif", "parking"))


def parse_window(prose):
    hours = WINDOW_HOURS_RE.search(prose)
    dates = WINDOW_DATES_RE.search(prose)
    if not (hours or dates):
        return None
    norm = lambda s: re.sub(r"\s+", "", s).replace("h", "h")
    return {
        "from": "01-07" if dates else None,
        "to": "31-08" if dates else None,
        "hours": f"{norm(hours.group(1))}–{norm(hours.group(2))}" if hours else None,
    }


def extras_of(d, prose):
    out = []
    for name, rx in EXTRA_RE.items():
        if rx.search(prose):
            out.append(name)
    return out


def derive(d):
    """Return (state, paid_window, extra_costs, note)."""
    cat = (d.get("category") or "").strip()
    isf = coerce_bool((d.get("schema_org") or {}).get("is_free"))
    prose = prose_of(d)

    if isf is True:
        return "free", None, extras_of(d, prose), ""
    if isf is False:
        if cat in SEASONAL_CATS and SEASONAL_RE.search(prose):
            return "free_seasonal", parse_window(prose), extras_of(d, prose), ""
        return "paid", None, [], ""
    # is_free null — derive from price, flag
    if entry_price_present(d):
        return "paid", None, [], "is_free=null → derived from price"
    return "free", None, extras_of(d, prose), "is_free=null → derived free (no price)"


def load_published():
    out = {}
    for fp in sorted(glob(os.path.join(JSON_DIR, "*.json"))):
        d = json.load(open(fp, encoding="utf-8"))
        if d.get("status") in ("draft", "unverified"):
            continue
        out[d["slug"]] = (fp, d)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write access_cost into api/lieu/*.json")
    args = ap.parse_args()

    pub = load_published()
    from collections import Counter
    states = Counter()
    seasonal, flagged, extras_rows = [], [], []
    written = 0
    for slug, (fp, d) in pub.items():
        state, window, extras, note = derive(d)
        states[state] += 1
        if state == "free_seasonal":
            seasonal.append((slug, d.get("category"), window, prose_of(d)[:70]))
        if note:
            flagged.append((slug, note))
        if extras:
            extras_rows.append((slug, state, extras))
        if args.apply:
            ap_fp = os.path.join(API_DIR, f"{slug}.json")
            if os.path.exists(ap_fp):
                a = json.load(open(ap_fp, encoding="utf-8"))
                a["access_cost"] = {"state": state, "paid_window": window, "extra_costs": extras}
                json.dump(a, open(ap_fp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
                open(ap_fp, "a").write("")  # keep trailing shape stable
                written += 1

    print(f"derive_access_cost: {len(pub)} published fiches")
    for st in ("free", "free_seasonal", "paid"):
        print(f"  {st:14} {states[st]}")
    print(f"\nfree_seasonal ({len(seasonal)}) — enter free hub with a 'gratuit hors saison · payant en été' badge:")
    for slug, cat, window, prose in seasonal:
        print(f"  {slug:44} [{cat}]  window={window}  | {prose}")
    if extras_rows:
        print(f"\nfree/paid fiches carrying OPTIONAL extra_costs ({len(extras_rows)}):")
        for slug, st, ex in extras_rows[:40]:
            print(f"  {slug:44} [{st}]  {ex}")
    if flagged:
        print(f"\nflagged for review ({len(flagged)}):")
        for slug, note in flagged:
            print(f"  {slug:44} {note}")
    if args.apply:
        print(f"\napplied: wrote access_cost to {written} api/lieu/*.json")
    else:
        print("\n(report only — nothing written; run --apply to emit into api/lieu/*.json)")


if __name__ == "__main__":
    main()
