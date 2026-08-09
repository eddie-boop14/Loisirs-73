#!/usr/bin/env python3
"""Salvage richer content from the pre-force-push feature branch tip
(85621b30) into the current main tree. Idempotent additive merge:

Rules per fiche × lang:
  - body.what_is: keep main's, unless feature's is ≥1.15× longer (then use feature's).
  - activities[]: keep main's; append any feature activity whose title isn't
    already present (case-insensitive substring match either direction).
  - practical_info[]: keep main's; append any feature row whose `k` isn't
    already present.

Top-level metadata (lat/lon, hero_image, official_site_url, data_sources,
sources, verify_flags, schema_org, partners, gallery_photos, freshness,
google_check, research_log, price_*, date_*) is NEVER touched — those
changes on main are intentional fixes.

Writes a per-fiche audit log to scripts/salvage-audit-report.json.
"""
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FEATURE_TIP = "85621b30"  # pre-force-push remote tip (saved in object store)
LANGS = ["fr", "en", "de", "it", "es", "nl"]


def at_rev(rev, path):
    out = subprocess.run(["git", "show", f"{rev}:{path}"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        return None
    return json.loads(out.stdout)


def feature_only_paths():
    out = subprocess.run(
        ["git", "log", "--name-only", "--format=", FEATURE_TIP, "^origin/main"],
        capture_output=True, text=True, check=True
    ).stdout
    return sorted({p for p in out.split("\n")
                   if p.startswith("Json/") and p.endswith(".json")})


def s(x): return x or ""


import re as _re
_STOPWORDS = set("a an the and or of in on at de la le les un une des du d à to for with et y est ce en pour sur sous par dans".split())

def _wordset(s):
    return {w for w in _re.findall(r"[a-zA-Zàâäéèêëîïôöùûüç]+", (s or "").lower())
            if w not in _STOPWORDS and len(w) > 2}

def title_present(title, existing):
    """Match if any existing title shares ≥50% significant-word overlap (Jaccard)."""
    t = _wordset(title)
    if not t:
        return True
    for e in existing:
        et = _wordset(e.get("title", ""))
        if not et:
            continue
        common = t & et
        union = t | et
        if union and len(common) / len(union) >= 0.5:
            return True
        # Also catch when one is fully contained in the other
        if t.issubset(et) or et.issubset(t):
            return True
    return False


def k_present(k, existing):
    kk = (k or "").strip().lower()
    if not kk:
        return True
    return any((r.get("k", "") or "").strip().lower() == kk for r in existing)


def merge_lang_block(main_blk, feat_blk):
    """Return (new_blk, change_log_for_this_lang)."""
    if not isinstance(main_blk, dict) or not isinstance(feat_blk, dict):
        return main_blk, {}
    new = dict(main_blk)
    changes = {}

    main_body = main_blk.get("body", {}) if isinstance(main_blk.get("body"), dict) else {}
    feat_body = feat_blk.get("body", {}) if isinstance(feat_blk.get("body"), dict) else {}
    new_body = dict(main_body)

    # what_is
    mw = main_body.get("what_is", "") or main_blk.get("what_is", "")
    fw = feat_body.get("what_is", "") or feat_blk.get("what_is", "")
    if fw and len(fw) >= 1.15 * len(s(mw)) and len(fw) > len(s(mw)) + 200:
        new_body["what_is"] = fw
        changes["what_is"] = {"from": len(s(mw)), "to": len(fw)}

    # activities — only salvage when main looks derived from feature (not a rewrite).
    # We test that the average max-Jaccard of main's activities vs feature's is ≥ 0.4.
    # That means most of main's activities resemble feature ones → feature was the source.
    # If main has wholly different titles, trust main.
    main_acts = main_body.get("activities") or main_blk.get("activities") or []
    feat_acts = feat_body.get("activities") or feat_blk.get("activities") or []
    if feat_acts and main_acts:
        def best_jacc(a_words, others):
            best = 0.0
            for o_words in others:
                if not a_words or not o_words:
                    continue
                inter = len(a_words & o_words)
                union = len(a_words | o_words)
                if union:
                    best = max(best, inter / union)
            return best
        feat_wordsets = [_wordset(a.get("title", "")) for a in feat_acts]
        main_wordsets = [_wordset(a.get("title", "")) for a in main_acts]
        # average best-match of main's activities into feature's
        scores = [best_jacc(mw, feat_wordsets) for mw in main_wordsets if mw]
        derivative_score = sum(scores) / len(scores) if scores else 0
        derived_from_feature = derivative_score >= 0.4
    else:
        derived_from_feature = bool(feat_acts) and not main_acts  # main has nothing, feature has → take feature

    new_acts = list(main_acts)
    appended = []
    if derived_from_feature:
        for fa in feat_acts:
            if not title_present(fa.get("title", ""), new_acts):
                new_acts.append(fa)
                appended.append(fa.get("title", "")[:60])
    if appended:
        new_body["activities"] = new_acts
        changes["activities_appended"] = appended

    # practical_info — same derivative check: only salvage if main's `k` set
    # overlaps feature's. If main has wholly different keys, it's a rewrite.
    main_pi = main_body.get("practical_info") or main_blk.get("practical_info") or []
    feat_pi = feat_body.get("practical_info") or feat_blk.get("practical_info") or []
    if main_pi and feat_pi:
        main_keys = {(r.get("k", "") or "").strip().lower() for r in main_pi}
        feat_keys = {(r.get("k", "") or "").strip().lower() for r in feat_pi}
        overlap = len(main_keys & feat_keys) / max(len(main_keys), 1)
        derived_pi = overlap >= 0.4
    else:
        derived_pi = bool(feat_pi) and not main_pi

    new_pi = list(main_pi)
    appended_pi = []
    if derived_pi:
        for fr in feat_pi:
            if not k_present(fr.get("k", ""), new_pi):
                new_pi.append(fr)
                appended_pi.append(fr.get("k", "")[:40])
    if appended_pi:
        new_body["practical_info"] = new_pi
        changes["practical_info_appended"] = appended_pi

    if changes:
        new["body"] = new_body
    return new, changes


def main():
    paths = feature_only_paths()
    print(f"Inspecting {len(paths)} JSONs for richer feature content...")
    audit = {"feature_tip": FEATURE_TIP, "per_fiche": {}, "summary": {}}

    fiches_changed = 0
    total_body_chars_recovered = 0
    total_acts_appended = 0
    total_pi_appended = 0

    for p in paths:
        main_doc = at_rev("HEAD", p)
        feat_doc = at_rev(FEATURE_TIP, p)
        if not main_doc or not feat_doc:
            continue
        new_doc = dict(main_doc)
        new_i18n = dict(main_doc.get("i18n", {}))
        fiche_changes = {}
        for lang in LANGS:
            main_blk = new_i18n.get(lang, {}) or {}
            feat_blk = (feat_doc.get("i18n", {}) or {}).get(lang)
            if not feat_blk:
                continue
            merged, changes = merge_lang_block(main_blk, feat_blk)
            if changes:
                new_i18n[lang] = merged
                fiche_changes[lang] = changes
                if "what_is" in changes:
                    total_body_chars_recovered += changes["what_is"]["to"] - changes["what_is"]["from"]
                if "activities_appended" in changes:
                    total_acts_appended += len(changes["activities_appended"])
                if "practical_info_appended" in changes:
                    total_pi_appended += len(changes["practical_info_appended"])
        if fiche_changes:
            new_doc["i18n"] = new_i18n
            (REPO / p).write_text(
                json.dumps(new_doc, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8"
            )
            audit["per_fiche"][p[5:-5]] = fiche_changes
            fiches_changed += 1

    audit["summary"] = {
        "fiches_changed": fiches_changed,
        "body_chars_recovered": total_body_chars_recovered,
        "activities_appended": total_acts_appended,
        "practical_info_rows_appended": total_pi_appended,
        "fiches_scanned": len(paths),
    }
    (REPO / "scripts" / "salvage-audit-report.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  fiches updated:       {fiches_changed}/{len(paths)}")
    print(f"  body chars recovered: {total_body_chars_recovered}")
    print(f"  activities appended:  {total_acts_appended}")
    print(f"  practical_info rows:  {total_pi_appended}")
    print(f"\nAudit: scripts/salvage-audit-report.json")


if __name__ == "__main__":
    main()
