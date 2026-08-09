#!/usr/bin/env python3
"""llm_tier.py — the in-session LLM translation lane (HANDOFF-41).

The paid Anthropic Batch lane (translate_local.py --patch-submit) runs only in
the Translate GitHub Action, keyed by the repo secret. When that lane cannot be
reached, this driver lets a capable LLM (the session model / subagents) BE the
translation engine while reusing every guarantee of the local lane:

  * segmentation, HTML-safe splitting and frozen-noun masking are UNCHANGED
    (imported straight from translate_local) — the LLM only ever sees masked
    English text cores and must return them translated, XQV<n>Z tokens verbatim;
  * write-back goes through run_mt(engine=...), so translate_batch.validate()
    (key parity, frozen nouns, tag census, digit/ratio) gates every field
    exactly as the argos/Haiku lanes — a field with any bad segment stays
    ABSENT (null discipline), logged to reports/translate-local-flags-<lang>.json.

Three subcommands, all $0 to the Anthropic Platform (the LLM is the session):

  extract <lang>   collect_unique_masked → scratchpad/segments-<lang>.json
                   (the work-list handed to the translator subagents)
  purge-he         drop the 281 garbled argos he prose fields so they re-enter
                   pairs_for_lang (HANDOFF-41: he shipped scrambled, re-do it)
  apply <lang>     replay scratchpad/cache-<lang>.json {masked: translated}
                   through run_mt → validate + write i18n.<lang> back
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import translate_local as tl          # noqa: E402
import translate_batch as tb          # noqa: E402

# HANDOFF-41: the pipeline's looks_french() short-circuit exists to keep FRENCH
# text out of the argos en→X engine (it would ship French back verbatim). But
# the in-session LLM tier reads French natively, so we DISABLE the short-circuit:
# French source segments are masked, translated, and validated like any other.
# This pulls the ~4,100 FR-source segments/lang (EN-mirrors-FR fiches) into scope.
tl.looks_french = lambda _masked: False

# HANDOFF-41: the "output not in target script" check runs on the UNMASKED
# output, where restored proper nouns (French place names — Abbaye d'Aulps,
# Saint-Jean-d'Aulps) are Latin and drag the target-script share below 0.3 even
# when the translatable text was translated correctly (料金と営業時間 = "rates and
# hours"). The pipeline already MASKS those nouns before translating, so the
# script test belongs on the MASKED output with the XQV placeholders stripped —
# that excludes proper nouns from the denominator. A genuinely untranslated
# segment still has its translatable words in Latin after stripping → still
# flagged. Only correct, name-dense translations are unblocked.
import re as _re            # noqa: E402
_XQV_STRIP = _re.compile(r"XQV[0-9]+Z")
# CJK compresses hard vs English/French ("Stroll through the medieval gardens"
# → "中世の庭園を散策", 0.23×). The 0.3 ratio floor is Euro-calibrated; use a
# lower floor for Japanese so legit-compact prose passes while true content
# drops (<0.15) still flag. ar/he track source length → keep 0.3.
_RATIO_FLOOR = {"ja": 0.15}
_APPLY_LANG = None


def _llm_translate_segment(engine, cache, text, nouns, script_re=None):
    lead = text[:len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()):]
    core = text.strip()
    masked, mapping = tl.mask_nouns(core, nouns)
    mt = cache[masked] if masked in cache else engine(masked)
    cache.setdefault(masked, mt)
    out, missing = tl.unmask(mt, mapping)
    reasons = [f"placeholder lost: {mapping[n][:40]!r}" for n in sorted(missing)]
    # digit / currency / empty (unmasked pair) + lang-aware length ratio
    if tl.digits_of(core) != tl.digits_of(out):
        reasons.append("digit parity broken")
    if ("€" in core) != ("€" in out):
        reasons.append("currency symbol changed")
    ss, os_ = len(core.strip()), len(out.strip())
    floor = _RATIO_FLOOR.get(_APPLY_LANG, 0.3)
    if ss >= 20 and not (floor <= os_ / max(1, ss) <= 3.0):
        reasons.append(f"segment ratio {os_ / max(1, ss):.2f} outside {floor}-3.0")
    if ss and not os_:
        reasons.append("empty translation")
    # target-script check on the MASKED output, proper nouns removed
    if script_re is not None and len(core) >= 20:
        stripped = _XQV_STRIP.sub("", mt)
        if tl.script_share(stripped, script_re) < 0.3:
            reasons.append("output not in target script (untranslated)")
    return lead + out + trail, reasons


tl.translate_segment = _llm_translate_segment

ROOT = Path(__file__).resolve().parent.parent
SCRATCH = ROOT / "scratchpad"
SCRATCH.mkdir(exist_ok=True)

# he prose keys written by the argos lane that must be purged before re-translate
HE_PURGE_FIELDS = ["meta_title", "meta_description", "hero", "hero_alt", "body",
                   "activities", "practical_info", "how_to_get_there",
                   "when_to_visit", "events", "faq", "acces_pmr_detail"]


def cmd_extract(lang):
    pairs = tb.pairs_for_lang(lang)
    communes = tb.all_communes()
    uniq = tl.collect_unique_masked(pairs, communes)
    out = SCRATCH / f"segments-{lang}.json"
    out.write_text(json.dumps(uniq, ensure_ascii=False, indent=0) + "\n",
                   encoding="utf-8")
    n_fields = sum(len(src) for _, src in pairs)
    print(f"[{lang}] {len(pairs)} fiches · {n_fields} missing prose fields · "
          f"{len(uniq)} unique masked segments → {out.name}")


def cmd_purge_he():
    pairs = tb.pairs_for_lang("he", force=True)   # every fiche, populated or not
    purged = 0
    for fiche, _src in pairs:
        blk = (fiche.get("i18n") or {}).get("he") or {}
        present = [f for f in HE_PURGE_FIELDS if f in blk]
        if present:
            tl.purge_fields(fiche, "he", present)
            purged += 1
    print(f"[he] purged garbled argos prose from {purged} fiche(s) "
          f"(fields: {', '.join(HE_PURGE_FIELDS)})")


def cmd_apply(lang):
    global _APPLY_LANG
    _APPLY_LANG = lang
    cache_file = SCRATCH / f"cache-{lang}.json"
    if not cache_file.exists():
        sys.exit(f"[{lang}] no cache file {cache_file.name} — translate first")
    cache = json.loads(cache_file.read_text(encoding="utf-8"))
    misses = {"n": 0}

    def engine(masked):
        v = cache.get(masked)
        if v is None:
            misses["n"] += 1
            return masked        # miss → English core; fails script check → held
        return v

    tl.run_mt(lang, engine=engine)
    if misses["n"]:
        print(f"[{lang}] WARNING: {misses['n']} segment(s) had no cached "
              f"translation — held as absent (extend the cache and re-apply).")


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: llm_tier.py <extract|purge-he|apply> [lang]")
    cmd = sys.argv[1]
    if cmd == "extract":
        cmd_extract(sys.argv[2])
    elif cmd == "purge-he":
        cmd_purge_he()
    elif cmd == "apply":
        cmd_apply(sys.argv[2])
    else:
        sys.exit(f"unknown command {cmd!r}")


if __name__ == "__main__":
    main()
