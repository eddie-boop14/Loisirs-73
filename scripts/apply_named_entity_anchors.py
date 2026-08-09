#!/usr/bin/env python3
"""apply_named_entity_anchors.py — HANDOFF JOB 3 (named-entity anchors), careful pass.

STRUCTURAL, zero fabrication. Promotes a proprietary name that is ALREADY in a
fiche to a matchable, permanently-anchored element, and records it in
`name_alternates`. No new pages, no new facts, no content rewrite.

Two anchor kinds, chosen per entity by where its name actually lives:

  WHATIS   the name sits in body.what_is prose (the Mont-Blanc lifts, Eisstock,
           Tactiq Game, Geneva Pass, Kandahar). Insert `<h2 id>` immediately
           before the paragraph that names it. Verbatim proper nouns, so this
           works across locales. `require` markers force the RIGHT paragraph
           (Plan Joran must anchor its closure paragraph, not the domain intro —
           the non-negotiable §5 flag).

  ACTIVITY the name is an activity flip-card title (Absurd Game, Explor Games,
           Acro'Filet, Visite Découverte) and is TRANSLATED per locale
           (Acro'Filet→Acro'Net→アクロ・ネット). Anchor by activity INDEX (stable
           across locales) — add `id` to that activity; build_lieu_page renders it.

`name_alternates` gets the canonical proprietary name(s) in every locale (the
term a user searches, even on a localized page). Heading string: FR uses §5's
full string; other locales use the bare proper noun (+ numeric elevation) — no
French descriptor leaks. Idempotent. --report writes nothing.

Never a target: Hippocampe (Edmaster rule — beach wheelchair, belongs in access_pmr).
"""
import argparse
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_DIR = os.path.join(ROOT, "Json")
P_RE = re.compile(r"<p\b[^>]*>.*?</p>", re.S)

# WHATIS: slug, id, FR heading, non-FR heading, locate-token, require-marker|None, alternates
WHATIS = [
    ("telecabine-panoramic-mont-blanc", "pointe-helbronner",
     "Pointe Helbronner (3 466 m)", "Pointe Helbronner (3 466 m)", "Helbronner", None, ["Pointe Helbronner"]),
    ("telepherique-du-brevent", "planpraz",
     "Planpraz (2 000 m)", "Planpraz (2 000 m)", "Planpraz", None, ["Planpraz"]),
    ("telepherique-des-grands-montets", "plan-joran",
     "Plan Joran (2 134 m)", "Plan Joran (2 134 m)", "Plan Joran", "3S", ["Plan Joran"]),
    ("telepherique-des-grands-montets", "lognan",
     "Lognan (2 134 m)", "Lognan (2 134 m)", "Lognan", None, ["Lognan"]),
    ("tramway-du-mont-blanc", "nid-d-aigle",
     "Nid d'Aigle (2 412 m)", "Nid d'Aigle (2 412 m)", "Nid d'Aigle", None, ["Nid d'Aigle"]),
    ("patinoire-la-clusaz", "eisstock",
     "Eisstock — le curling autrichien", "Eisstock", "Eisstock", None, ["Eisstock"]),
    # Tactiq Game EXCLUDED — tactiq-aventure-cruseilles is a protected carrying page
    # (Chez Nous partner block injected by radius); §1 forbids touching it.
    ("maison-du-saleve-presilly", "geneva-pass",
     "Entrée gratuite avec le Geneva Pass", "Geneva Pass", "Geneva Pass", None, ["Geneva Pass"]),
    ("les-houches", "verte-des-houches-kandahar",
     "La Verte des Houches — la piste du Kandahar", "La Verte des Houches / Kandahar",
     "Kandahar", None, ["La Verte des Houches", "Kandahar"]),
]

# ACTIVITY: slug, id, activity index (stable across locales), alternates
ACTIVITY = [
    ("ecomusee-paysalp-viuz-en-sallaz", "absurd-game", 3, ["Absurd Game"]),
    ("ecomusee-paysalp-viuz-en-sallaz", "explor-games", 4, ["Explor Games"]),
    ("acro-aventures-reignier", "acro-filet", 3, ["Acro'Filet"]),
    ("fonderie-paccard-sevrier", "visite-decouverte", 3, ["Visite Découverte"]),
]


def esc_h(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def add_alts(blk, alts, counter):
    na = blk.get("name_alternates")
    if isinstance(na, list):
        for a in alts:
            if a not in na:
                na.append(a); counter[0] += 1
    elif na is None and blk.get("name"):
        blk["name_alternates"] = list(alts); counter[0] += len(alts)


def inject_whatis(wi, aid, heading, token, require):
    if not isinstance(wi, str) or not wi.strip():
        return wi, "no-body"
    if f'id="{aid}"' in wi:
        return wi, "already"
    for m in P_RE.finditer(wi):
        blk = m.group(0)
        if token in blk and (require is None or require in blk):
            h2 = f'<h2 id="{aid}">{esc_h(heading)}</h2>'
            return wi[:m.start()] + h2 + wi[m.start():], "injected"
    return wi, "token-not-found"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    tot = {"whatis": 0, "activity": 0, "alt": [0], "tnf": 0, "already": 0}
    dirty = {}

    def load(slug):
        if slug not in dirty:
            dirty[slug] = json.load(open(os.path.join(JSON_DIR, f"{slug}.json"), encoding="utf-8"))
        return dirty[slug]

    print("== WHATIS anchors ==")
    for slug, aid, frh, nfh, tok, req, alts in WHATIS:
        d = load(slug); i18n = d.get("i18n") or {}
        inj, tnf, alr = [], [], []
        for lang, blk in i18n.items():
            if not isinstance(blk, dict):
                continue
            add_alts(blk, alts, tot["alt"])
            body = blk.get("body")
            wi = body.get("what_is") if isinstance(body, dict) else None
            new, st = inject_whatis(wi, aid, frh if lang == "fr" else nfh, tok, req)
            if st == "injected":
                inj.append(lang); tot["whatis"] += 1
                if args.apply:
                    body["what_is"] = new
            elif st == "already":
                alr.append(lang); tot["already"] += 1
            elif st == "token-not-found":
                tnf.append(lang); tot["tnf"] += 1
        print(f"  #{aid:26} inj={len(inj)} [{','.join(inj)}]"
              + (f" already=[{','.join(alr)}]" if alr else "")
              + (f"  ⚠tnf=[{','.join(tnf)}]" if tnf else ""))

    print("\n== ACTIVITY anchors (by index) ==")
    for slug, aid, idx, alts in ACTIVITY:
        d = load(slug); i18n = d.get("i18n") or {}
        done, miss = [], []
        for lang, blk in i18n.items():
            if not isinstance(blk, dict):
                continue
            add_alts(blk, alts, tot["alt"])
            acts = blk.get("activities")
            if isinstance(acts, list) and len(acts) > idx and isinstance(acts[idx], dict):
                if acts[idx].get("id") == aid:
                    continue
                done.append(lang); tot["activity"] += 1
                if args.apply:
                    acts[idx]["id"] = aid
            else:
                miss.append(lang)
        print(f"  #{aid:26} id-set={len(done)} [{','.join(done)}]"
              + (f"  no-activity=[{','.join(miss)}]" if miss else ""))

    if args.apply:
        for slug, d in dirty.items():
            fp = os.path.join(JSON_DIR, f"{slug}.json")
            json.dump(d, open(fp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            if not open(fp, encoding="utf-8").read().endswith("\n"):
                open(fp, "a", encoding="utf-8").write("\n")
        # Keep the translation payloads in sync — else the revert-guard
        # (ingest_translations --check) sees the fiche's new what_is diverge from
        # translations/<lang>.json and blocks CI (a stale payload would revert it).
        sync_payloads(dirty)


def sync_payloads(dirty):
    """Mirror each edited fiche's body.what_is into translations/<lang>.json for
    the payload locales (de/en/es/it/nl) so ingest stays idempotent/revert-safe."""
    n = 0
    for lang in ("de", "en", "es", "it", "nl"):
        p = os.path.join(ROOT, "translations", f"{lang}.json")
        if not os.path.exists(p):
            continue
        pay = json.load(open(p, encoding="utf-8"))
        changed = False
        for slug, d in dirty.items():
            body = ((d.get("i18n") or {}).get(lang) or {}).get("body")
            wi = body.get("what_is") if isinstance(body, dict) else None
            entry = pay.get(slug)
            if wi and isinstance(entry, dict) and entry.get("body.what_is") not in (None, wi):
                entry["body.what_is"] = wi
                changed = True; n += 1
        if changed:
            json.dump(pay, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            if not open(p, encoding="utf-8").read().endswith("\n"):
                open(p, "a", encoding="utf-8").write("\n")
    print(f"payload sync: {n} translations/<lang>.json entries updated")

    print(f"\ntotals: whatis-h2={tot['whatis']} activity-id={tot['activity']} "
          f"name_alternates+={tot['alt'][0]} token-not-found={tot['tnf']} already={tot['already']}")
    print("APPLIED" if args.apply else "(report only — nothing written)")


if __name__ == "__main__":
    main()
