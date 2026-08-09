#!/usr/bin/env python3
"""translate_local.py — HANDOFF-37: the $0 translation lane (ja · ar · he · pl).

Local MT (argostranslate, offline, no API key, no per-char billing) with
scripted proofreading. Supersedes the Haiku-default of HANDOFF-36: Haiku 4.5
is the PATCH tier only, on FLAGGED SEGMENTS, never whole fiches.

The lane, per language:
  1. HTML-safe by construction — every prose string is split on tags and
     entities; only text nodes reach MT; reassembly is positional, so tag
     census and key/shape parity hold BY CONSTRUCTION.
  2. Frozen-noun masking — glossary nouns (CORE_FROZEN + every commune + the
     fiche's FR name) and bare URLs become XQV<n>Z placeholders before MT and
     are restored verbatim after. A placeholder the engine mangled or dropped
     FLAGS the segment (never shipped mangled).
  3. Scripted checks per segment — digit multiset parity (rule 4; catches
     numeral conversion), length ratio 0.3–3.0 on segments ≥ 20 chars.
  4. Whole-field validation — the UNCHANGED translate_batch.validate()
     (key parity, frozen nouns, tag census, ratio, empties). A field with any
     flagged segment stays ABSENT (null discipline) and lands, with its full
     segment table, in reports/translate-local-flags-<lang>.json.
  5. Patch tier (PAID, ≤ $2/lang hard cap) — claude-haiku-4-5 Message Batch on
     the flagged segments only; --patch-dry-run prints the contract, Eddie's
     go is the workflow click; the HANDOFF-35 meter + >15% abort apply.

USAGE (manual only — NEVER a cron):
    python3 scripts/translate_local.py --lang pl --dry-run      # counts, $0
    python3 scripts/translate_local.py --lang pl                # the MT run
    python3 scripts/translate_local.py --lang pl --patch-dry-run  # contract
    python3 scripts/translate_local.py --lang pl --patch-submit   # paid, go'd
"""
import argparse
import siteconfig  # HANDOFF-73 phase 5: per-site identity
import datetime
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import translate_batch as tb  # noqa: E402 — validators/write-back/meter reused

ROOT = Path(__file__).resolve().parent.parent
FLAGS_FILE = ROOT / "reports" / "translate-local-flags-{lang}.json"

MT_LANGS = ["pl", "ja", "ar", "he"]          # en→X argos models all exist
# FR-authored payload fields: an en→X model cannot read French — these NEVER
# enter local MT; they are flagged whole and only the LLM patch tier (which
# reads any source language) may translate them.
FR_SOURCE_FIELDS = {"acces_pmr_detail"}
PATCH_MODEL = "claude-haiku-4-5"             # PATCH tier only (HANDOFF-37)
PATCH_IN_PER_MTOK = 0.50                     # batch: 50% off $1.00
PATCH_OUT_PER_MTOK = 2.50                    # batch: 50% off $5.00
PATCH_CACHE_WRITE_PER_MTOK = 0.625           # batch: 50% off 1.25 × $1.00
PATCH_CACHE_READ_PER_MTOK = 0.05             # batch: 50% off 0.1 × $1.00
PATCH_CAP_USD = 2.00                         # hard per-lang cap, aborts submit
PATCH_MAX_TOKENS = 1000                      # segments avg 80 chars

# tags + HTML entities are frozen tokens — they NEVER enter MT
TOKEN_RE = re.compile(r"<[^>]+>|&[a-zA-Z]+;|&#[0-9]+;")
URL_RE = re.compile(r"https?://[^\s<>\"]+")
# tolerant unmask: engines sometimes add spaces or case-fold the placeholder
UNMASK_RE = re.compile(r"[Xx]\s?[Qq]\s?[Vv]\s?([0-9]+)\s?[Zz]")

# HANDOFF-37 Layer-B discovery: ~12% of the "EN" source segments are actually
# FRENCH (the EN block mirrors FR on ~214 fiches). An en→X engine cannot read
# French — it ships the text back nearly verbatim and the digit/ratio checks
# see nothing wrong. Judged on the MASKED core so frozen French proper nouns
# (Lac d'Annecy, communes…) never trip it.
FR_DIACRITICS = re.compile(r"[àâéèêëîïôùûçœÀÂÉÈÊËÎÏÔÙÛÇŒ]")
# case-insensitive + the short function words: the second Layer-B catch was
# an ALL-CAPS, diacritic-free French lead ("PARC LOCAL DU MASSIF DES ARAVIS -
# col de la Croix Fry") that the first regex missed. False positives (English
# sentences quoting a French title) only cost patch-tier cents; false
# negatives ship French — asymmetric, so we widen.
FR_STOPWORDS = re.compile(
    r"\b(des|avec|dès|aux|pour|sur|une|du|et|les|ou|est|sont|chez|vers"
    r"|entre|depuis|de|la|le|au)\b", re.IGNORECASE)
FR_LOOK_REASON = "FR-looking source — LLM patch tier only"

# Layer-B catch #3 (ar): the engine sometimes returns long segments WHOLLY
# UNTRANSLATED — English text that sails through digit/ratio checks. For
# script-target languages the tell is deterministic: the output of a real
# translation is majority target-script. <30% target-script letters on a
# >=20-char segment = untranslated → patch tier.
TARGET_SCRIPT = {
    "ar": re.compile(r"[\u0600-\u06FF]"),
    "he": re.compile(r"[\u0590-\u05FF]"),
    "ja": re.compile(r"[\u3040-\u30FF\u4E00-\u9FFF]"),
}


def script_share(text, script_re):
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 1.0
    return sum(1 for c in letters if script_re.match(c)) / len(letters)


def looks_french(masked_core):
    return (len(FR_DIACRITICS.findall(masked_core)) >= 2
            or len(FR_STOPWORDS.findall(masked_core)) >= 3)


# ------------------------------------------------------------- segmentation
def split_parts(s):
    """[(kind, text)] with kind ∈ {frozen, text}; ''.join(texts) == s exactly.
    Tags/entities are frozen; whitespace-only text is frozen too (MT would
    eat the spacing between adjacent tags)."""
    parts, last = [], 0
    for m in TOKEN_RE.finditer(s):
        if m.start() > last:
            parts.append(("text", s[last:m.start()]))
        parts.append(("frozen", m.group(0)))
        last = m.end()
    if last < len(s):
        parts.append(("text", s[last:]))
    return [("frozen" if k == "text" and not t.strip() else k, t)
            for k, t in parts]


def mask_nouns(text, nouns):
    """Frozen nouns (longest first, so 'Lac d'Annecy' wins over 'Annecy')
    and bare URLs → XQV<n>Z placeholders. Returns (masked, {n: original})."""
    mapping = {}
    counter = [0]

    def sub(m):
        n = str(counter[0])
        counter[0] += 1
        mapping[n] = m.group(0)
        return f"XQV{n}Z"

    pats = [URL_RE.pattern] + [re.escape(n) for n in
                               sorted(set(nouns), key=len, reverse=True)]
    return re.compile("|".join(pats)).sub(sub, text), mapping


def unmask(mt, mapping):
    """Restore placeholders verbatim. Returns (text, missing_ids)."""
    seen = set()

    def sub(m):
        n = m.group(1)
        seen.add(n)
        return mapping.get(n, m.group(0))

    out = UNMASK_RE.sub(sub, mt)
    return out, set(mapping) - seen


def digits_of(s):
    return sorted(re.findall(r"[0-9]", s))


def check_segment(src, out, script_re=None):
    """Scripted proofreading — reasons list, empty = OK."""
    reasons = []
    if script_re is not None and len(src.strip()) >= 20 \
            and script_share(out, script_re) < 0.3:
        reasons.append("output not in target script (untranslated)")
    if digits_of(src) != digits_of(out):
        reasons.append("digit parity broken")
    if ("€" in src) != ("€" in out):
        # rule 4: prices unchanged — the engine likes rewriting € as 'EUR'
        reasons.append("currency symbol changed")
    ss, os_ = len(src.strip()), len(out.strip())
    if ss >= 20 and not (0.3 <= os_ / max(1, ss) <= 3.0):
        reasons.append(f"segment ratio {os_ / max(1, ss):.2f} outside 0.3-3.0")
    if ss and not os_:
        reasons.append("empty translation")
    return reasons


def translate_segment(engine, cache, text, nouns, script_re=None):
    """One text node through mask → MT → unmask → checks.
    Leading/trailing whitespace is OURS, not the engine's — MT engines trim
    it, which would weld text onto the neighbouring tag (`</strong>jest`).
    Returns (translated, reasons)."""
    lead = text[:len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()):]
    core = text.strip()
    masked, mapping = mask_nouns(core, nouns)
    if looks_french(masked):
        # never feed French to an en→X engine — straight to the patch tier
        return text, [FR_LOOK_REASON]
    if masked in cache:
        mt = cache[masked]
    else:
        mt = engine(masked)
        cache[masked] = mt
    out, missing = unmask(mt, mapping)
    reasons = [f"placeholder lost: {mapping[n][:40]!r}" for n in sorted(missing)]
    reasons += check_segment(core, out, script_re)
    return lead + out + trail, reasons


def translate_string(engine, cache, s, nouns, path, records, script_re=None):
    """Whole string value: frozen parts verbatim, text parts through MT.
    Appends one record per part to `records` (the flags-file segment table —
    self-contained for patch-tier reassembly). Returns (translated, n_bad)."""
    out, n_bad = [], 0
    for i, (kind, part) in enumerate(split_parts(s)):
        if kind == "frozen":
            records.append({"path": path, "i": i, "kind": "frozen", "src": part})
            out.append(part)
            continue
        mt, reasons = translate_segment(engine, cache, part, nouns, script_re)
        records.append({"path": path, "i": i, "kind": "text", "src": part,
                        "mt": mt, "ok": not reasons, "reasons": reasons})
        if reasons:
            n_bad += 1
        out.append(mt)
    return "".join(out), n_bad


def translate_value(engine, cache, v, nouns, path, records, script_re=None):
    """Mirror the source structure exactly (shape parity by construction)."""
    if isinstance(v, str):
        return translate_string(engine, cache, v, nouns, path, records, script_re)
    if isinstance(v, dict):
        out, bad = {}, 0
        for k, x in v.items():
            out[k], b = translate_value(engine, cache, x, nouns,
                                        f"{path}.{k}", records, script_re)
            bad += b
        return out, bad
    if isinstance(v, list):
        out, bad = [], 0
        for i, x in enumerate(v):
            t, b = translate_value(engine, cache, x, nouns,
                                   f"{path}[{i}]", records, script_re)
            out.append(t)
            bad += b
        return out, bad
    return v, 0                                  # numbers/bools/null verbatim


def rebuild_field(src_value, records, patches, path):
    """Recursively rebuild the translated field from the segment table."""
    if isinstance(src_value, str):
        parts = [r for r in records if r["path"] == path]
        out = []
        for r in sorted(parts, key=lambda r: r["i"]):
            if r["kind"] == "frozen":
                out.append(r["src"])
            elif r.get("ok"):
                out.append(r["mt"])
            elif (r["path"], r["i"]) in patches:
                out.append(patches[(r["path"], r["i"])])
            else:
                return None
        return "".join(out)
    if isinstance(src_value, dict):
        out = {}
        for k, x in src_value.items():
            t = rebuild_field(x, records, patches, f"{path}.{k}")
            if t is None:
                return None
            out[k] = t
        return out
    if isinstance(src_value, list):
        out = []
        for i, x in enumerate(src_value):
            t = rebuild_field(x, records, patches, f"{path}[{i}]")
            if t is None:
                return None
            out.append(t)
        return out
    return src_value


# ------------------------------------------------------------------- engine
class ArgosEngine:
    """argostranslate en→<lang>; downloads/installs the model on first use."""

    def __init__(self, lang):
        import argostranslate.package as pkg
        import argostranslate.translate as trans
        self.lang = lang
        installed = {(p.from_code, p.to_code) for p in pkg.get_installed_packages()}
        if ("en", lang) not in installed:
            print(f"  downloading argos model en→{lang} …")
            pkg.update_package_index()
            target = next(p for p in pkg.get_available_packages()
                          if p.from_code == "en" and p.to_code == lang)
            pkg.install_from_path(target.download())
        self._translate = trans.translate

    def __call__(self, text):
        return self._translate(text, "en", self.lang)


# Pool worker plumbing — each worker loads the model once and stays
# single-threaded (OMP_NUM_THREADS=1) so N workers are truly parallel
# instead of fighting over the same cores.
_POOL_LANG = None


def _pool_init(lang):
    global _POOL_LANG
    import os as _os
    _os.environ.setdefault("OMP_NUM_THREADS", "1")
    _POOL_LANG = lang


def _pool_translate(text):
    import argostranslate.translate as trans
    return text, trans.translate(text, "en", _POOL_LANG)


def collect_unique_masked(pairs, communes):
    """Pass 1 of the pooled run: every unique MASKED text core across the
    corpus (same masking translate_segment applies — the cache key)."""
    uniq = set()
    for fiche, src in pairs:
        nouns = tb.fiche_frozen_nouns(fiche) + communes
        for v in src.values():
            for s in tb.strings_of(v):
                for kind, part in split_parts(s):
                    if kind != "text":
                        continue
                    core = part.strip()
                    if not core:
                        continue
                    masked = mask_nouns(core, nouns)[0]
                    if not looks_french(masked):
                        uniq.add(masked)
    return sorted(uniq)


def pooled_cache(lang, pairs, communes, workers=None):
    """Pass 2: translate the unique masked segments on a process pool.
    Returns the preloaded {masked: mt} cache for the assembly pass."""
    import multiprocessing as mp
    import os as _os
    uniq = collect_unique_masked(pairs, communes)
    workers = workers or max(1, (_os.cpu_count() or 2) - 1)
    print(f"[{lang}] {len(uniq)} unique masked segments → "
          f"{workers} worker(s), model loads once per worker")
    cache = {}
    ctx = mp.get_context("spawn")       # safe with torch/ctranslate2 threads
    with ctx.Pool(workers, initializer=_pool_init, initargs=(lang,)) as pool:
        for i, (src_txt, mt) in enumerate(
                pool.imap_unordered(_pool_translate, uniq, chunksize=8), 1):
            cache[src_txt] = mt
            if i % 500 == 0 or i == len(uniq):
                print(f"  …MT {i}/{len(uniq)}", flush=True)
    return cache


# ------------------------------------------------------------------ MT run
def flags_path(lang):
    return Path(str(FLAGS_FILE).format(lang=lang))


def purge_fields(fiche, lang, fields):
    """Remove stale i18n.<lang> fields (a held field must be ABSENT even if a
    previous run wrote it). Fresh read, same discipline as write_back."""
    p = fiche["_path"]
    d = json.load(open(p, encoding="utf-8"))
    blk = (d.get("i18n") or {}).get(lang)
    if not blk:
        return
    changed = False
    for f in fields:
        if f in blk:
            del blk[f]
            changed = True
    if changed:
        with open(p, "w", encoding="utf-8") as fp:
            json.dump(d, fp, ensure_ascii=False, indent=2)
            fp.write("\n")


def run_mt(lang, engine=None, dry_run=False):
    """The $0 base tier. Returns (written, flagged_fields)."""
    pairs = tb.pairs_for_lang(lang)
    communes = tb.all_communes()
    n_fields = sum(len(src) for _, src in pairs)
    print(f"[{lang}] {len(pairs)} fiches · {n_fields} prose fields · "
          f"engine=argostranslate en→{lang} · cost $0.00")
    if dry_run:
        print(f"[{lang}] --dry-run: stopping before MT. Nothing billed either way.")
        return 0, 0
    if not pairs:
        print(f"[{lang}] nothing to do — already populated")
        return 0, 0

    if engine is None:
        engine = ArgosEngine(lang)      # ensures the model is installed
        cache = pooled_cache(lang, pairs, communes)   # two-phase, parallel
    else:
        cache = {}                      # test path: serial, injected engine
    written = 0
    flagged_fields = []
    for k, (fiche, src) in enumerate(pairs, 1):
        nouns = tb.fiche_frozen_nouns(fiche) + communes
        out, bad_fields = {}, {}
        for field, v in src.items():
            if field in FR_SOURCE_FIELDS:
                # never through en→X MT — whole field to the patch tier
                records = [dict({"path": f"{field}", "i": i, "kind": k,
                                 "src": t}, **({} if k == "frozen" else
                                {"mt": "", "ok": False,
                                 "reasons": ["FR-source field — LLM patch tier only"]}))
                           for s in tb.strings_of(v)
                           for i, (k, t) in enumerate(split_parts(s))]
                bad_fields[field] = {"src": v, "segments": records,
                                     "n_flagged": sum(1 for r in records
                                                      if r["kind"] == "text")}
                continue
            records = []
            tv, n_bad = translate_value(engine, cache, v, nouns, field, records,
                                        TARGET_SCRIPT.get(lang))
            if n_bad:
                bad_fields[field] = {"src": v, "segments": records,
                                     "n_flagged": n_bad}
            else:
                out[field] = tv
        if out:
            sub_src = {f: src[f] for f in out}
            viol = tb.validate(sub_src, out, tb.fiche_frozen_nouns(fiche))
            if viol:
                # construction should make this unreachable — honesty first
                for f in list(out):
                    bad_fields.setdefault(f, {"src": src[f], "segments": [],
                                              "n_flagged": 0})
                    bad_fields[f]["validate_viol"] = viol
                out = {}
        if out:
            tb.write_back(fiche, lang, out)
            written += 1
        if bad_fields:
            # a re-run may hold a field an EARLIER run wrote — purge the stale
            # write so null discipline holds across runs, not just within one
            purge_fields(fiche, lang, bad_fields.keys())
        for field, rec in bad_fields.items():
            flagged_fields.append({"slug": fiche["slug"], "field": field, **rec})
        if k % 50 == 0:
            print(f"  …{k}/{len(pairs)} fiches ({written} written, "
                  f"{len(flagged_fields)} flagged fields, "
                  f"{len(cache)} cached segments)")

    fp = flags_path(lang)
    fp.parent.mkdir(exist_ok=True)
    fp.write_text(json.dumps({
        "lang": lang, "date": datetime.date.today().isoformat(),
        "engine": f"argostranslate en->{lang}",
        "fields": flagged_fields,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    n_segs = sum(len(f["segments"]) for f in flagged_fields)
    n_flagged_segs = sum(f["n_flagged"] for f in flagged_fields)
    print(f"[{lang}] MT DONE: {written} fiches written · "
          f"{len(flagged_fields)} fields held back "
          f"({n_flagged_segs} flagged of {n_segs} segments in them) → {fp.name}")
    print(f"[{lang}] spend: $0.00. Patch contract: --patch-dry-run.")
    return written, len(flagged_fields)


# -------------------------------------------------------------- patch tier
# Cap-fit priority (HANDOFF-37: <=$2/lang is a HARD rule -- when the full need
# exceeds it, the highest-value segments go first and the rest are DEFERRED
# LOUDLY, never silently): meta_title flips a fiche rich, then the SERP pair,
# hero, accessibility, body, the long tail.
PATCH_PRIORITY = ["meta_title", "meta_description", "hero", "acces_pmr_detail",
                  "hero_alt", "body", "faq", "practical_info", "activities",
                  "how_to_get_there", "when_to_visit", "events"]


def resniff(lang):
    """One-time maintenance (Layer-B FR-poison discovery): purge every
    POPULATED i18n.<lang> field whose SOURCE contains FR-looking segments (or
    is an FR-source field). SAFE only while every populated field is
    MT-provenance — run BEFORE any patch tier write. The next MT run re-flags
    the purged fields into the flags file for the patch tier."""
    communes = tb.all_communes()
    purged_fields = purged_fiches = 0
    for fiche, src in tb.pairs_for_lang(lang, force=True):
        blk = (fiche.get("i18n") or {}).get(lang) or {}
        nouns = tb.fiche_frozen_nouns(fiche) + communes
        bad = []
        script_re = TARGET_SCRIPT.get(lang)
        for field, v in src.items():
            if field not in blk:
                continue
            if field in FR_SOURCE_FIELDS:
                bad.append(field)
                continue
            hit = any(kind == "text" and part.strip()
                      and looks_french(mask_nouns(part.strip(), nouns)[0])
                      for s in tb.strings_of(v)
                      for kind, part in split_parts(s))
            if not hit and script_re is not None:
                # written value must be majority target-script (untranslated
                # pass-through sweep — Layer-B catch #3)
                hit = any(len(w.strip()) >= 20 and script_share(w, script_re) < 0.3
                          for w in tb.strings_of(blk.get(field)))
            if hit:
                bad.append(field)
        if bad:
            purge_fields(fiche, lang, bad)
            purged_fields += len(bad)
            purged_fiches += 1
    print(f"[{lang}] resniff: purged {purged_fields} MT-written field(s) on "
          f"{purged_fiches} fiche(s) whose source is FR-looking — the next MT "
          f"run routes them to the patch tier")
    return purged_fields


def patch_requests(lang, flags):
    """One Haiku request per FLAGGED segment (masked source travels — the
    model keeps XQV<n>Z placeholders and numbers verbatim)."""
    reqs, routing = [], {}
    i = 0
    sysblock = (f"You translate short tourism text segments into "
                f"{tb.LANG_NAMES[lang]} for {siteconfig.DOMAIN} (source segments are "
                "English or French). Reply with ONLY the translated segment - "
                "no quotes, no commentary. Any token of the form XQV<number>Z "
                "is a masked proper name: copy every one through VERBATIM, "
                "exactly once, in natural position. Keep all digits, prices "
                "(€ stays €), times and URLs unchanged.")
    order = {k: i for i, k in enumerate(PATCH_PRIORITY)}
    indexed = sorted(enumerate(flags["fields"]),
                     key=lambda kv: order.get(kv[1]["field"], 99))
    for fi, f in indexed:
        for r in f["segments"]:
            if r["kind"] != "text" or r.get("ok"):
                continue
            # Haiku receives the RAW source segment (no masking needed — the
            # whole-field validate() after reassembly proves frozen nouns
            # survived; the scripted digit/ratio checks gate each segment).
            cid = f"{lang}-p{i:05d}"
            routing[cid] = {"fi": fi, "path": r["path"], "i": r["i"]}
            reqs.append({
                "custom_id": cid,
                "params": {
                    "model": PATCH_MODEL,
                    "max_tokens": PATCH_MAX_TOKENS,
                    "system": sysblock,
                    "messages": [{"role": "user", "content": r["src"]}],
                },
            })
            i += 1
    return reqs, routing


def patch_estimate(reqs):
    cal = tb.load_calibration()
    in_per_char = cal.get("input_tokens_per_char") or tb.DEFAULT_IN_PER_CHAR
    sys_chars = len(reqs[0]["params"]["system"]) if reqs else 0
    in_tok = out_tok = 0
    for r in reqs:
        chars = len(r["params"]["messages"][0]["content"])
        in_tok += int((chars + sys_chars) * in_per_char) + 1
        out_tok += int(chars * 0.5) + 1     # short segments; ceiling factor
    usd = (in_tok * PATCH_IN_PER_MTOK + out_tok * PATCH_OUT_PER_MTOK) / 1e6
    return in_tok, out_tok, usd


def run_patch(lang, submit=False):
    fp = flags_path(lang)
    if not fp.exists():
        sys.exit(f"[{lang}] no flags file ({fp.name}) — run the MT tier first")
    flags = json.loads(fp.read_text(encoding="utf-8"))
    reqs, routing = patch_requests(lang, flags)
    in_tok, out_tok, usd = patch_estimate(reqs)
    dropped = 0
    if usd > PATCH_CAP_USD:
        # cap-fit: requests are already priority-ordered — keep the prefix
        # that fits, DEFER the rest loudly (they stay absent + flagged; a
        # later run patches them once the earlier spend proves out)
        full_need, full_count = usd, len(reqs)
        lo = 0
        while lo < len(reqs):
            _, _, u = patch_estimate(reqs[:lo + 1])
            if u > PATCH_CAP_USD:
                break
            lo += 1
        dropped = len(reqs) - lo
        reqs = reqs[:lo]
        routing = {r["custom_id"]: routing[r["custom_id"]] for r in reqs}
        in_tok, out_tok, usd = patch_estimate(reqs)
        print(f"[{lang}] CAP-FIT: full need {full_count} segments ≈ "
              f"${full_need:.2f} > ${PATCH_CAP_USD:.2f} cap → patching the "
              f"{lo} highest-priority segments, DEFERRING {dropped} "
              f"(they stay absent + flagged — nothing silent, nothing mangled)")
    print(f"[{lang}] PATCH contract: {len(reqs)} flagged segment(s) on "
          f"{PATCH_MODEL} batch · est ~{in_tok/1000:.1f}k in / "
          f"~{out_tok/1000:.1f}k out tok · est ~${usd:.2f} "
          f"(hard cap ${PATCH_CAP_USD:.2f})")
    if not reqs:
        print(f"[{lang}] nothing flagged — no patch needed.")
        return True
    if not submit:
        print(f"[{lang}] --patch-dry-run: stopping before submit. "
              "Eddie sees the bill first.")
        return True
    if usd > PATCH_CAP_USD:
        sys.exit(f"[{lang}] ABORT: contract ${usd:.2f} exceeds the "
                 f"${PATCH_CAP_USD:.2f}/lang patch cap (HANDOFF-37).")

    client = tb.get_client()
    bid = tb.submit_batch(client, reqs)
    flags["patch_batch_id"] = bid
    fp.write_text(json.dumps(flags, ensure_ascii=False, indent=1) + "\n",
                  encoding="utf-8")
    tb.poll_batch(client, bid)
    results, usage = tb.collect_results(client, bid)
    return _apply_patch_results(lang, flags, routing, results, usage, fp,
                                contract_usd=usd)


def _apply_patch_results(lang, flags, routing, results, usage, fp,
                         contract_usd=None):
    """Route a (already-paid) Haiku patch batch's results back into the flags
    table, reassemble + validate every now-complete field, write it back, and
    persist the flags file. Shared by the submit path (run_patch) and the FREE
    recover path (run_patch_recover) so a batch that already billed is never
    re-paid to be claimed.

    `contract_usd` is the dry-run contract for the >15% abort (submit only). On
    recover it is None — the spend is already sunk, so the results ALWAYS land;
    aborting there would just re-lose paid work (the original bug)."""
    tot = tb.sum_usage(usage.values())
    # HANDOFF-37 patch tier is Haiku ($0.50/$2.50), NOT the module's Sonnet
    # batch rates — price it with the patch rates or a Haiku batch reads 3× too
    # high, trips the $2 cap on a phantom overspend, and the run goes RED after
    # already billing (the 'fails but takes my credit' bug).
    actual = tb.usage_cost_usd(tot,
                               in_per_mtok=PATCH_IN_PER_MTOK,
                               out_per_mtok=PATCH_OUT_PER_MTOK,
                               cache_write_per_mtok=PATCH_CACHE_WRITE_PER_MTOK,
                               cache_read_per_mtok=PATCH_CACHE_READ_PER_MTOK)
    if any(tot.values()):
        vs = f" vs ${contract_usd:.2f} contract" if contract_usd is not None else " (recover)"
        print(f"[{lang}] METER patch batch: {tot['input_tokens']:,} in / "
              f"{tot['output_tokens']:,} out tok → ${actual:.2f} actual{vs}")

    # route results back into the segment tables
    patched_segs = 0
    for cid, (kind, payload) in results.items():
        route = routing.get(cid)
        if not route or kind != "ok":
            continue
        f = flags["fields"][route["fi"]]
        rec = next(r for r in f["segments"]
                   if r["path"] == route["path"] and r["i"] == route["i"])
        out = payload.strip()
        reasons = check_segment(rec["src"], out, TARGET_SCRIPT.get(lang))
        # placeholders: Haiku got the raw source, so nouns are plain text —
        # only the scripted checks gate here; frozen-noun survival is proven
        # by the whole-field validate() below.
        if reasons:
            rec["patch_reasons"] = reasons
            continue
        rec["mt"] = out
        rec["ok"] = True
        rec["patched"] = True
        patched_segs += 1

    # reassemble + validate + write every field that is now complete
    by_slug = {}
    for f in flags["fields"]:
        by_slug.setdefault(f["slug"], []).append(f)
    all_pairs = {fc["slug"]: (fc, sc)
                 for fc, sc in tb.pairs_for_lang(lang, force=True)}
    written_fields = still = 0
    for slug, fields in by_slug.items():
        pair = all_pairs.get(slug)
        if not pair:
            continue
        fiche, _src = pair
        out = {}
        for f in fields:
            if f.get("written"):
                continue
            rebuilt = rebuild_field(f["src"], f["segments"], {}, f["field"])
            if rebuilt is None:
                still += 1
                continue
            viol = tb.validate({f["field"]: f["src"]}, {f["field"]: rebuilt},
                               tb.fiche_frozen_nouns(fiche))
            if viol:
                f["patch_viol"] = viol
                still += 1
                continue
            out[f["field"]] = rebuilt
            f["written"] = True
            written_fields += 1
        if out:
            tb.write_back(fiche, lang, out)
    fp.write_text(json.dumps(flags, ensure_ascii=False, indent=1) + "\n",
                  encoding="utf-8")
    print(f"[{lang}] PATCH DONE: {patched_segs} segments patched · "
          f"{written_fields} fields completed+written · {still} still held "
          f"(absent, logged in {fp.name})")
    if contract_usd is not None and any(tot.values()) and tb.over_budget(actual, contract_usd):
        print(f"[{lang}] BUDGET OVERRUN >15% on the patch — RED (HANDOFF-35 rule).")
        sys.exit(3)
    return still == 0


def run_patch_recover(lang, batch_id=None):
    """FREE: re-read an already-PAID Haiku patch batch and land its results —
    no new submit. Anthropic keeps batch results ~29 days; when a patch-submit
    billed but its results were discarded (the meter/git-add bugs), this claims
    them instead of paying again. Rebuilds the routing from the SAME flags file
    (custom_ids are deterministic — {lang}-p<NNNNN> over the priority order), so
    the batch's results map back exactly. Batch id: --batch-id, else the flags
    file's patch_batch_id."""
    fp = flags_path(lang)
    if not fp.exists():
        sys.exit(f"[{lang}] no flags file ({fp.name}) — nothing to recover")
    flags = json.loads(fp.read_text(encoding="utf-8"))
    _reqs, routing = patch_requests(lang, flags)
    bid = batch_id or flags.get("patch_batch_id")
    if not bid:
        sys.exit(f"[{lang}] no batch id — pass --batch-id <msgbatch_…> (from the "
                 "run log) or ensure the flags file carries patch_batch_id")
    print(f"[{lang}] RECOVER: re-reading already-paid batch {bid} "
          "(retrieval is FREE — no new submit, no new charge)")
    client = tb.get_client()
    tb.poll_batch(client, bid)          # returns at once if already ended
    results, usage = tb.collect_results(client, bid)
    return _apply_patch_results(lang, flags, routing, results, usage, fp,
                                contract_usd=None)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lang", required=True, help=f"one of {'/'.join(MT_LANGS)}")
    ap.add_argument("--dry-run", action="store_true",
                    help="counts only, no MT, no writes (still $0 either way)")
    ap.add_argument("--patch-dry-run", action="store_true",
                    help="print the Haiku patch contract from the flags file")
    ap.add_argument("--resniff", action="store_true",
                    help="purge populated fields whose SOURCE is FR-looking "
                         "(one-time maintenance; run before any patch write)")
    ap.add_argument("--patch-submit", action="store_true",
                    help="PAID (≤$2 cap): Haiku-patch the flagged segments — "
                         "only after Eddie saw the contract")
    ap.add_argument("--patch-recover", action="store_true",
                    help="FREE: re-read an already-PAID patch batch and land its "
                         "results (no new submit). Use --batch-id or the flags "
                         "file's patch_batch_id.")
    ap.add_argument("--batch-id", default=None,
                    help="msgbatch_… id for --patch-recover (from the run log)")
    args = ap.parse_args()
    if args.lang not in MT_LANGS:
        sys.exit(f"ERROR: unknown MT lang {args.lang!r} (expected {MT_LANGS})")
    if args.resniff:
        resniff(args.lang)
    elif args.patch_recover:
        run_patch_recover(args.lang, batch_id=args.batch_id)
    elif args.patch_dry_run or args.patch_submit:
        run_patch(args.lang, submit=args.patch_submit)
    else:
        run_mt(args.lang, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
