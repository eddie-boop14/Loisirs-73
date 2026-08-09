#!/usr/bin/env python3
"""translate_batch.py — HANDOFF-25: the 21M-char prose job at ~1/20th the cost.

Translates every fiche's FR prose (the authored source of truth) into the facts-first languages
(pl/pt/cs/ja/ar/he) through the Anthropic Message Batches API — 50% off
input AND output vs interactive, ~2,382 requests total, machine-validated
on arrival, written back into Json/<slug>.json under i18n.<lang>.

    ONE language at a time, in sequence:  pl → pt → cs → ja → ar → he
    Each: assemble → (dry-run gate) → submit → poll → validate → write.

USAGE (manual only — NEVER a cron; 2026-07-01's lesson):
    python3 scripts/translate_batch.py --lang pl --dry-run   # count + cost, no submit
    python3 scripts/translate_batch.py --lang pl             # run one language
    python3 scripts/translate_batch.py --lang all            # whole job, language by language
    python3 scripts/translate_batch.py --lang pl --force     # redo already-populated fiches

NEEDS: ANTHROPIC_API_KEY in the environment (Eddie's Anthropic Platform
key — NOT the Google one). Model: claude-sonnet-4-6 (per HANDOFF-25).
Batch pricing $1.50/$7.50 per MTok. NOTE (HANDOFF-35): the shared
instruction block carries a cache_control marker but sits BELOW the model's
2048-token minimum cacheable prefix, so it is billed as plain input on
every request — estimate() prices it accordingly, and the >15%-over-contract
ABORT rule + the --audit reconciliation keep the meter honest.

RESUMABLE + IDEMPOTENT:
  * a submitted batch id is remembered in reports/translate-batch-state.json —
    re-running resumes polling instead of resubmitting;
  * fiche×lang pairs whose prose fields are already populated are skipped
    (use --force to redo);
  * failed results are auto-retried ONCE in a follow-up batch; still-failing
    pairs are logged to reports/translate-batch-failures.md and the fields
    stay ABSENT (null discipline — never a bad write).

EVERY result is validated before write-back (the standard-keeper):
  1. JSON parses + KEY PARITY with the FR source (no missing, no invented);
  2. FROZEN NOUNS verbatim (core glossary + every commune + the fiche's
     frozen FR name — any term present in the source must survive untouched);
  3. HTML STRUCTURE parity (same tag multiset as source; no &lt;escaped&gt;
     tags — feeds HANDOFF-23's raw-emit correctly);
  4. length ratio 0.4–2.5× source; no empty string where source non-empty.

After a language lands, render + gate it (separate steps, printed as a
reminder): build_fulltree_lang / build_lieu_page rich render (HANDOFF-22),
gate_render_verified sample, the no-escaped-tags check, then ship.
Protected fiches are data-carrying like any other — their placement blocks
are untouched (we only ADD i18n.<lang> prose fields).
"""
import argparse
import siteconfig  # HANDOFF-73 phase 5: per-site identity
import datetime
import glob
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSON_DIR = ROOT / "Json"
STATE_FILE = ROOT / "reports" / "translate-batch-state.json"
FAILURES_MD = ROOT / "reports" / "translate-batch-failures.md"
CALIBRATION_FILE = ROOT / "reports" / "translate-cost-calibration.json"
RECONCILIATION_MD = ROOT / "reports" / "translate-cost-reconciliation.md"

MODEL = "claude-sonnet-4-6"          # per HANDOFF-25 — do not silently upgrade
MAX_TOKENS = 16000
BATCH_IN_PER_MTOK = 1.50             # $ per MTok, batch (50% off $3.00)
BATCH_OUT_PER_MTOK = 7.50            # $ per MTok, batch (50% off $15.00)
BATCH_CACHE_WRITE_PER_MTOK = 1.875   # $ per MTok, batch (50% off 1.25 × $3.00)
BATCH_CACHE_READ_PER_MTOK = 0.15     # $ per MTok, batch (50% off 0.1 × $3.00)
# claude-sonnet-4-6's minimum cacheable prefix. Below it the cache_control
# marker is SILENTLY ignored — no error, no caching, every request re-bills
# the system prompt as plain input. Our system prompt is ~780 tokens, so the
# cache NEVER fired on pt/cs (HANDOFF-35 Job B, proven leak #1).
MIN_CACHEABLE_TOKENS = 2048
# HANDOFF-35 permanent rule: the dry-run is a contract — a run that exceeds
# its estimate by >15% ABORTS mid-run (before the next paid submit) and the
# workflow goes red.
ABORT_RATIO = 1.15

TARGET_LANGS = ["pl", "pt", "cs", "ja", "ar", "he"]
RTL_LANGS = {"ar", "he"}
LANG_NAMES = {"pl": "Polish", "pt": "Portuguese", "cs": "Czech",
              "ja": "Japanese", "ar": "Arabic", "he": "Hebrew"}

# The prose fields (HANDOFF-25 / HANDOFF-22). `hero` is trimmed to `lead`,
# `body` to `what_is`; facts / name / name_alternates / schema_amenities are
# NOT prose and never travel.
PROSE_FIELDS = ["meta_title", "meta_description", "hero", "hero_alt", "body",
                "activities", "practical_info", "how_to_get_there",
                "when_to_visit", "events", "faq"]

# Core frozen nouns — stay VERBATIM untranslated in every language.
# Communes + each fiche's frozen FR name are added programmatically.
CORE_FROZEN = ["Lac d'Annecy", "Léman", "Mont-Blanc", "Aiguille du Midi",
               siteconfig.DEPT_NAME, "ViaRhôna", "GR®", "Faucigny", siteconfig.SITE_NAME]

TAG_RE = re.compile(r"<\s*/?\s*([a-zA-Z][a-zA-Z0-9]*)")

# Batches API constraint on custom_id: ^[a-zA-Z0-9_-]{1,64}$
# The original "<slug>:<lang>" form violated it twice (illegal ':' + slugs up
# to 73 chars) — run #2 got a 400 BEFORE the batch was created ($0 spent).
# Uniqueness now comes from the per-batch index; the slug fragment is for
# humans reading logs. The authoritative custom_id → slug mapping travels in
# the state file so a resumed poll can still route results.
CUSTOM_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def make_custom_id(lang, i, slug):
    cid = f"{lang}-{i:04d}-{slug}"[:64]
    if not CUSTOM_ID_RE.match(cid):
        raise ValueError(f"custom_id out of spec: {cid!r}")
    return cid


# --------------------------------------------------------------------- source
def extract_source(fiche):
    """The FR prose payload for one fiche — FR is the authored source of truth
    (HANDOFF amendment: was i18n.en, a derivative; EN is now a target like any
    other langue). Only fields present in source travel; fields absent stay
    absent (the model is told never to invent)."""
    fr = (fiche.get("i18n") or {}).get("fr") or {}
    src = {}
    for f in PROSE_FIELDS:
        v = fr.get(f)
        if v in (None, "", [], {}):
            continue
        if f == "hero":
            lead = (v or {}).get("lead")
            if lead:
                src["hero"] = {"lead": lead}
        elif f == "body":
            wi = (v or {}).get("what_is")
            if wi:
                src["body"] = {"what_is": wi}
        else:
            src[f] = v
    # HANDOFF-35 Job A: acces_pmr.detail is FR-authored CONTENT (not a frozen
    # name) at fiche["acces_pmr"]["detail"], outside the i18n block — the
    # renderer suppresses it off-fr until a translation exists, so it travels in
    # the payload and lands as i18n.<lang>.acces_pmr_detail.
    det = (fiche.get("acces_pmr") or {}).get("detail")
    if isinstance(det, str) and det.strip():
        src["acces_pmr_detail"] = det.strip()
    return src


def all_communes():
    out = set()
    for p in sorted(glob.glob(str(JSON_DIR / "*.json"))):
        c = (json.load(open(p, encoding="utf-8")).get("commune") or "").strip()
        if c:
            out.add(c)
    return sorted(out)


def fiche_frozen_nouns(fiche):
    nouns = list(CORE_FROZEN)
    name = ((fiche.get("i18n") or {}).get("fr") or {}).get("name")
    if name:
        nouns.append(name.strip())
    commune = (fiche.get("commune") or "").strip()
    if commune:
        nouns.append(commune)
    return nouns


def system_prompt(lang, communes):
    """The shared, prompt-cached instruction block (identical across the
    whole batch — keep it byte-stable; per-fiche content goes in the user
    message AFTER the cache breakpoint)."""
    rtl = ("\nThe target language is written right-to-left. Keep Latin-script "
           "proper names and all numbers exactly as-is — the renderer handles "
           "bidi isolation; do not add RLM/LRM marks.") if lang in RTL_LANGS else ""
    return (
        f"You translate tourism prose for {siteconfig.DOMAIN} from French to "
        f"{LANG_NAMES[lang]}.\n"
        "You receive a JSON object; return ONLY the same JSON object with every "
        "string value translated. Rules:\n"
        "1. Keys stay IDENTICAL. Arrays keep the same length and order. Fields "
        "absent in the input stay absent — never invent content.\n"
        "2. These proper nouns stay VERBATIM untranslated wherever they appear: "
        + ", ".join(CORE_FROZEN) + "; every Haute-Savoie commune name ("
        + ", ".join(communes) + "); and the venue's own proper name given with "
        "the input.\n"
        "3. Keep inline HTML tags (<p>, <ul>, <li>, <strong>, <em>, <a>, <br>) "
        "exactly as structured — same tags, same nesting, translate only the "
        "text between them. Never escape tags as &lt;…&gt;.\n"
        "4. Keep numbers, prices (€), times, phone numbers and URLs unchanged.\n"
        "5. Natural, idiomatic prose for travellers — not word-for-word.\n"
        "6. The output must be VALID JSON: any literal double quote inside a "
        "string value must be escaped as \\\" — better, use the target "
        "language's own typographic quotation marks („…“, »…«, «…», 「…」) "
        "for quoted phrases instead of straight quotes.\n"
        "Return ONLY the translated JSON. No markdown fences, no commentary."
        + rtl
    )


def user_prompt(fiche, src):
    name = ((fiche.get("i18n") or {}).get("fr") or {}).get("name") or fiche.get("slug")
    return (f"Venue proper name (verbatim, never translate): {name}\n"
            f"Commune: {fiche.get('commune') or '—'}\n\n"
            + json.dumps(src, ensure_ascii=False, indent=1))


# ----------------------------------------------------------------- validation
def strings_of(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from strings_of(x)
    elif isinstance(v, list):
        for x in v:
            yield from strings_of(x)


def shape_of(v, path=""):
    """Comparable structural signature: dict key-sets, list lengths, leaf types."""
    if isinstance(v, dict):
        return {k: shape_of(x, f"{path}.{k}") for k, x in sorted(v.items())}
    if isinstance(v, list):
        return [shape_of(x, f"{path}[{i}]") for i, x in enumerate(v)]
    return type(v).__name__


def tag_census(text):
    from collections import Counter
    return Counter(t.lower() for t in TAG_RE.findall(text))


def validate(src, out, frozen_nouns):
    """Returns a list of violations; empty list = PASS."""
    viol = []
    if shape_of(src) != shape_of(out):
        viol.append("key/structure parity: translated JSON does not mirror the source "
                    "(missing, invented, reordered-list or retyped fields)")
    src_all = "\n".join(strings_of(src))
    out_all = "\n".join(strings_of(out))
    for noun in frozen_nouns:
        if noun in src_all and noun not in out_all:
            viol.append(f"frozen noun lost: {noun!r}")
    if tag_census(src_all) != tag_census(out_all):
        viol.append("HTML structure parity: tag multiset differs from source")
    if "&lt;" in out_all and "&lt;" not in src_all:
        viol.append("escaped HTML tags (&lt;…&gt;) in output — breaks raw-emit (HANDOFF-23)")
    if src_all:
        ratio = len(out_all) / len(src_all)
        if not (0.4 <= ratio <= 2.5):
            viol.append(f"length ratio {ratio:.2f} outside 0.4–2.5 (truncation/runaway)")
    # no empty string where source non-empty (walk in parallel where shapes match)
    def walk(a, b, path):
        if isinstance(a, dict) and isinstance(b, dict):
            for k in a:
                if k in b:
                    walk(a[k], b[k], f"{path}.{k}")
        elif isinstance(a, list) and isinstance(b, list):
            for i, (x, y) in enumerate(zip(a, b)):
                walk(x, y, f"{path}[{i}]")
        elif isinstance(a, str) and isinstance(b, str):
            if a.strip() and not b.strip():
                viol.append(f"empty translation at {path}")
    walk(src, out, "")
    return viol


def repair_json_quotes(t):
    """Escape unescaped double quotes INSIDE JSON string values.

    The cs run's disease (140/389 rejected twice): Czech prose is full of
    quoted phrases and the model emitted them as literal '"' inside string
    values — invalid JSON. Heuristic: while inside a string, a '"' only ends
    it if the next non-whitespace char is a JSON delimiter (, } ] :) or EOF;
    any other '"' is content and gets escaped. Conservative by design — if a
    payload still doesn't parse, it fails exactly as before (validators and
    the absent-field discipline are untouched)."""
    out = []
    i, n = 0, len(t)
    in_str = False
    while i < n:
        c = t[i]
        if not in_str:
            if c == '"':
                in_str = True
            out.append(c)
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            out.append(t[i:i + 2])
            i += 2
            continue
        if c == '"':
            j = i + 1
            while j < n and t[j] in " \t\r\n":
                j += 1
            if j >= n or t[j] in ",}]:":
                in_str = False
                out.append(c)
            else:
                out.append('\\"')       # interior quote → escape
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def parse_result_text(text):
    """The model is told to return bare JSON; strip fences defensively, and
    repair unescaped in-string quotes before giving up (the cs failure class
    — the content is fine, the quoting isn't)."""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        return json.loads(repair_json_quotes(t))


# ------------------------------------------------------------------ estimate
def est_tokens(text):
    """Rough chars/3.5 heuristic — the pre-audit fallback only."""
    return int(len(text) / 3.5) + 1


def load_calibration():
    """Audit-derived cost factors (reports/translate-cost-calibration.json,
    written by --audit from the PAID batches' real per-request usage).
    Absent/unreadable → {} and estimate() falls back to the documented
    assumptions below."""
    if CALIBRATION_FILE.exists():
        try:
            return json.loads(CALIBRATION_FILE.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {}


# Output model: out_tokens ≈ source_chars × factor. These are UNCALIBRATED
# assumptions, deliberately set HIGH from the observed pt/cs overrun scale
# (~$19 actual vs $7.61 contract back-computes to ~0.7 out-tok per source
# char) so the pre-audit contract is a ceiling, not a floor. --audit replaces
# them with measured per-language values; ja/ar/he keep an assumption flag
# until their own first audited run.
DEFAULT_OUT_PER_CHAR = {"pl": 0.70, "pt": 0.70, "cs": 0.75,
                        "ja": 0.85, "ar": 0.80, "he": 0.80}
DEFAULT_IN_PER_CHAR = 1 / 3.5


def estimate(pairs, communes, lang):
    """Pre-submit bill — the CONTRACT (HANDOFF-35 Job B).

    Honest where the old model leaked:
      * caching — the system prompt sits below MIN_CACHEABLE_TOKENS, so it is
        priced as plain uncached input on EVERY request (that is what the API
        actually billed on pt/cs; the old model priced 388/389 requests' system
        block at 0.1×);
      * output — per-language out-tokens-per-source-char factor (audited or
        conservative default), instead of assuming translation ≈ source size.
    Returns (n_requests, in_tok, out_tok, usd, calibrated)."""
    cal = load_calibration()
    in_per_char = cal.get("input_tokens_per_char") or DEFAULT_IN_PER_CHAR
    out_per_char = ((cal.get("output_tokens_per_source_char") or {}).get(lang)
                    or DEFAULT_OUT_PER_CHAR.get(lang, 0.75))
    calibrated = bool(cal.get("input_tokens_per_char"))
    n = len(pairs)
    sys_tok = int(len(system_prompt(lang, communes)) * in_per_char) + 1
    in_tok = out_tok = 0
    for fiche, src in pairs:
        chars = len(user_prompt(fiche, src))
        in_tok += int(chars * in_per_char) + 1
        out_tok += int(chars * out_per_char) + 1
    if sys_tok >= MIN_CACHEABLE_TOKENS:
        # cache real: first request writes (1.25×), the rest read (0.1×)
        sys_usd = (sys_tok * BATCH_CACHE_WRITE_PER_MTOK
                   + sys_tok * max(0, n - 1) * BATCH_CACHE_READ_PER_MTOK) / 1e6
        sys_tok_total = int(sys_tok * (1.25 + 0.1 * max(0, n - 1)))
    else:
        # below the minimum cacheable prefix the marker is silently ignored:
        # every request re-bills the system prompt as plain input
        sys_usd = sys_tok * n * BATCH_IN_PER_MTOK / 1e6
        sys_tok_total = sys_tok * n
    usd = (in_tok * BATCH_IN_PER_MTOK + out_tok * BATCH_OUT_PER_MTOK) / 1e6 + sys_usd
    return n, in_tok + sys_tok_total, out_tok, usd, calibrated


def legacy_estimate(pairs, communes, lang):
    """The pre-HANDOFF-35 model, verbatim — what the pt/cs dry-run contracts
    were computed with ($7.61). Kept ONLY so --audit can decompose the
    contract-vs-actual delta to the cent. Never used for a new contract."""
    sys_tok = est_tokens(system_prompt(lang, communes))
    in_tok = out_tok = 0
    for fiche, src in pairs:
        body = est_tokens(user_prompt(fiche, src))
        in_tok += body
        out_tok += body          # translation ≈ source size (the leak)
    n = len(pairs)
    sys_cost_tok = sys_tok * (1.25 + 0.1 * max(0, n - 1))
    usd = ((in_tok + sys_cost_tok) * BATCH_IN_PER_MTOK + out_tok * BATCH_OUT_PER_MTOK) / 1e6
    return n, in_tok + int(sys_cost_tok), out_tok, usd


# ------------------------------------------------------------ the honest meter
USAGE_KEYS = ("input_tokens", "output_tokens",
              "cache_creation_input_tokens", "cache_read_input_tokens")


def usage_of(msg):
    """Per-request token counts straight from the API result (or None)."""
    u = getattr(msg, "usage", None)
    if u is None:
        return None
    return {k: int(getattr(u, k, 0) or 0) for k in USAGE_KEYS}


def sum_usage(rows):
    tot = {k: 0 for k in USAGE_KEYS}
    for r in rows:
        for k in USAGE_KEYS:
            tot[k] += int(r.get(k, 0) or 0)
    return tot


def usage_cost_usd(tot, in_per_mtok=BATCH_IN_PER_MTOK,
                   out_per_mtok=BATCH_OUT_PER_MTOK,
                   cache_write_per_mtok=BATCH_CACHE_WRITE_PER_MTOK,
                   cache_read_per_mtok=BATCH_CACHE_READ_PER_MTOK):
    """Actual $ at Message Batches prices — what the Console will show.

    The rates DEFAULT to this module's Sonnet batch lane (claude-sonnet-4-6),
    unchanged. The Haiku PATCH tier (translate_local.run_patch) must pass its
    own $0.50/$2.50 rates — otherwise a Haiku batch is priced at Sonnet rates
    (3× too high), the phantom overspend trips the $2 cap, and the run goes RED
    even though the batch was cheap and fine (the bug behind the 'fails but
    still bills' patch-submit runs)."""
    return (tot["input_tokens"] * in_per_mtok
            + tot["cache_creation_input_tokens"] * cache_write_per_mtok
            + tot["cache_read_input_tokens"] * cache_read_per_mtok
            + tot["output_tokens"] * out_per_mtok) / 1e6


def over_budget(actual_usd, est_usd):
    """The permanent >15% rule: the dry-run number is a contract."""
    return est_usd > 0 and actual_usd > ABORT_RATIO * est_usd


# --------------------------------------------------------------------- state
def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state):
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")


# ----------------------------------------------------------------- batch I/O
def get_client():
    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        sys.exit("ERROR: set ANTHROPIC_API_KEY (Eddie's Anthropic Platform key).")
    import anthropic
    return anthropic.Anthropic()


def build_requests(pairs, communes, lang):
    """Returns (requests, {custom_id: slug}) — the id_map is the only way to
    route results back to fiches (results arrive in any order)."""
    sys_block = [{"type": "text", "text": system_prompt(lang, communes),
                  "cache_control": {"type": "ephemeral"}}]
    reqs, id_map = [], {}
    for i, (fiche, src) in enumerate(pairs):
        cid = make_custom_id(lang, i, fiche["slug"])
        id_map[cid] = fiche["slug"]
        reqs.append({
            "custom_id": cid,
            "params": {
                "model": MODEL,
                "max_tokens": MAX_TOKENS,
                "system": sys_block,
                "messages": [{"role": "user", "content": user_prompt(fiche, src)}],
            },
        })
    return reqs, id_map


def submit_batch(client, reqs):
    batch = client.messages.batches.create(requests=reqs)
    print(f"  submitted batch {batch.id} ({len(reqs)} requests)")
    return batch.id


def poll_batch(client, batch_id, interval=60):
    while True:
        b = client.messages.batches.retrieve(batch_id)
        if b.processing_status == "ended":
            print(f"  batch {batch_id} ended: {b.request_counts.succeeded} ok, "
                  f"{b.request_counts.errored} errored, {b.request_counts.expired} expired")
            return b
        print(f"  …{b.processing_status}: {b.request_counts.processing} processing")
        time.sleep(interval)


def collect_results(client, batch_id):
    """({custom_id: ('ok', text) | ('error', reason)}, {custom_id: usage})
    — keyed by custom_id, NEVER by position (results arrive in any order).
    usage carries the API's own per-request token counts (the honest meter,
    HANDOFF-35); absent on mocks/old results → simply not in the dict."""
    out, usage = {}, {}
    for r in client.messages.batches.results(batch_id):
        rt = r.result.type
        if rt == "succeeded":
            msg = r.result.message
            text = next((b.text for b in msg.content if b.type == "text"), "")
            out[r.custom_id] = ("ok", text)
            u = usage_of(msg)
            if u:
                usage[r.custom_id] = u
        else:
            out[r.custom_id] = ("error", rt)
    return out, usage


# ------------------------------------------------------------------ pipeline
def pairs_for_lang(lang, force=False):
    """(fiche, source) for every fiche missing this language's prose."""
    pairs = []
    for p in sorted(glob.glob(str(JSON_DIR / "*.json"))):
        fiche = json.load(open(p, encoding="utf-8"))
        fiche["_path"] = p
        src = extract_source(fiche)
        if not src:
            continue                     # no FR prose to translate
        blk = (fiche.get("i18n") or {}).get(lang) or {}
        if force:
            pairs.append((fiche, src))
            continue
        # HANDOFF-35: send ONLY the still-missing fields. Adding a field to
        # the payload (acces_pmr_detail) must never re-bill the whole prose of
        # an already-translated fiche — a pt/cs mop-up costs cents, not $19.
        missing = {f: v for f, v in src.items() if f not in blk}
        if not missing:
            continue                     # already populated + validated → skip
        pairs.append((fiche, missing))
    return pairs


def write_back(fiche, lang, out):
    p = fiche["_path"]
    d = json.load(open(p, encoding="utf-8"))     # fresh read — never stale state
    d.setdefault("i18n", {}).setdefault(lang, {}).update(out)
    with open(p, "w", encoding="utf-8") as fp:
        json.dump(d, fp, ensure_ascii=False, indent=2)
        fp.write("\n")


def log_failures(lang, failures):
    FAILURES_MD.parent.mkdir(exist_ok=True)
    today = datetime.date.today().isoformat()
    lines = []
    if not FAILURES_MD.exists():
        lines.append("# translate_batch — validation failures (fields left absent)\n\n")
    lines.append(f"## {lang} — run {today}\n\n| fiche | violations |\n|---|---|\n")
    for slug, viol in failures:
        lines.append(f"| {slug} | {'; '.join(viol)} |\n")
    lines.append("\n")
    with open(FAILURES_MD, "a", encoding="utf-8") as fp:
        fp.writelines(lines)


def run_language(lang, args, client=None):
    communes = all_communes()
    pairs = pairs_for_lang(lang, force=args.force)
    n, in_tok, out_tok, usd, calibrated = estimate(pairs, communes, lang)
    cal_note = ("audit-calibrated" if calibrated
                else "UNCALIBRATED — assumed factors; run the audit mode first (HANDOFF-35)")
    print(f"[{lang}] {n} fiche×lang requests · est ~{in_tok/1000:.0f}k in / "
          f"~{out_tok/1000:.0f}k out tokens · est ~${usd:.2f} on {MODEL} batch "
          f"({cal_note})")
    if not pairs:
        print(f"[{lang}] nothing to do — already populated (use --force to redo)")
        return True
    if args.dry_run:
        print(f"[{lang}] --dry-run: stopping before submit. Eddie sees the bill first.")
        return True

    client = client or get_client()
    state = load_state()
    lang_state = state.get(lang) or {}

    # submit (or resume a pending batch)
    if lang_state.get("batch_id") and not lang_state.get("done"):
        batch_id = lang_state["batch_id"]
        id_map = lang_state.get("id_map") or {}
        print(f"[{lang}] resuming pending batch {batch_id} ({len(id_map)} routed ids)")
    else:
        reqs, id_map = build_requests(pairs, communes, lang)
        batch_id = submit_batch(client, reqs)
        state[lang] = {"batch_id": batch_id, "id_map": id_map,
                       "submitted": datetime.date.today().isoformat()}
        save_state(state)

    poll_batch(client, batch_id)
    results, usage = collect_results(client, batch_id)

    # THE METER (HANDOFF-35): reconcile actual spend against the contract as
    # soon as the API tells us what it billed — before any further paid step.
    tot_main = sum_usage(usage.values())
    actual = usage_cost_usd(tot_main)
    if any(tot_main.values()):
        print(f"[{lang}] METER main batch: {tot_main['input_tokens']:,} in / "
              f"{tot_main['output_tokens']:,} out / "
              f"{tot_main['cache_read_input_tokens']:,} cache-read tok "
              f"→ ${actual:.2f} actual vs ${usd:.2f} contract "
              f"({(actual / usd * 100) if usd else 0:.0f}%)")
        state = load_state()
        state.setdefault(lang, {})["usage_main"] = tot_main
        state[lang]["actual_usd_main"] = round(actual, 4)
        state[lang]["contract_usd"] = round(usd, 4)
        save_state(state)

    by_slug = {f["slug"]: (f, s) for f, s in pairs}
    written, retry, failed = 0, [], []
    for cid, (kind, payload) in results.items():
        slug = id_map.get(cid)
        if slug not in by_slug:
            continue
        fiche, src = by_slug[slug]
        viol = None
        if kind == "ok":
            try:
                out = parse_result_text(payload)
                viol = validate(src, out, fiche_frozen_nouns(fiche))
            except Exception as e:
                viol = [f"JSON parse: {e}"]
        else:
            viol = [f"batch result: {payload}"]
        if viol:
            retry.append((fiche, src, viol))
        else:
            write_back(fiche, lang, out)
            written += 1

    # one retry round, fresh requests — GATED by the >15% rule: a retry is a
    # SECOND PAID submit (the cs retry was +153 requests ≈ +$3). Project its
    # cost from the main batch's ACTUAL per-request average; over budget →
    # abort before spending, log, red exit. Fields stay absent (recoverable
    # later via --recover or an approved --force re-run).
    if retry and any(tot_main.values()):
        per_req = actual / max(1, len(usage))
        projected = actual + per_req * len(retry)
        if over_budget(projected, usd):
            print(f"[{lang}] BUDGET ABORT: main batch ${actual:.2f} + projected retry "
                  f"${per_req * len(retry):.2f} > {ABORT_RATIO:.2f}× contract ${usd:.2f} "
                  f"— retry submit SKIPPED (HANDOFF-35 rule).")
            log_failures(lang, [(f["slug"], v + ["retry skipped: >15% budget abort"])
                                for f, s, v in retry])
            state = load_state()
            state.setdefault(lang, {})["done"] = True
            state[lang]["written"] = written
            state[lang]["budget_abort"] = True
            save_state(state)
            sys.exit(2)

    if retry:
        print(f"[{lang}] retrying {len(retry)} failed result(s) once…")
        retry_pairs = [(f, s) for f, s, _ in retry]
        rreqs, rid_map = build_requests(retry_pairs, communes, lang)
        cid_of = {slug: cid for cid, slug in rid_map.items()}
        rid = submit_batch(client, rreqs)
        # persist the retry batch id + routing so a later --recover can re-read
        # BOTH batches' results for free (results live ~29 days server-side)
        state = load_state()
        state.setdefault(lang, {})["retry_batch_id"] = rid
        state[lang]["retry_id_map"] = rid_map
        save_state(state)
        poll_batch(client, rid)
        rres, rusage = collect_results(client, rid)
        tot_retry = sum_usage(rusage.values())
        if any(tot_retry.values()):
            print(f"[{lang}] METER retry batch: {tot_retry['input_tokens']:,} in / "
                  f"{tot_retry['output_tokens']:,} out tok "
                  f"→ ${usage_cost_usd(tot_retry):.2f} actual (on top of the contract)")
            state = load_state()
            state.setdefault(lang, {})["usage_retry"] = tot_retry
            state[lang]["actual_usd_retry"] = round(usage_cost_usd(tot_retry), 4)
            save_state(state)
        for fiche, src, first_viol in retry:
            kind, payload = rres.get(cid_of.get(fiche["slug"], ""), ("error", "missing"))
            viol = None
            if kind == "ok":
                try:
                    out = parse_result_text(payload)
                    viol = validate(src, out, fiche_frozen_nouns(fiche))
                except Exception as e:
                    viol = [f"JSON parse: {e}"]
            else:
                viol = [f"batch result: {payload}"]
            if viol:
                failed.append((fiche["slug"], first_viol + viol))
            else:
                write_back(fiche, lang, out)
                written += 1

    if failed:
        log_failures(lang, failed)
        print(f"[{lang}] {len(failed)} pair(s) failed twice → logged to "
              f"{FAILURES_MD}, fields left ABSENT")

    state = load_state()
    state.setdefault(lang, {})["done"] = True
    state[lang]["written"] = written
    save_state(state)

    # final reconciliation — always printed; >15% over contract = red run
    lang_state = load_state().get(lang) or {}
    final_actual = usage_cost_usd(sum_usage(
        [u for u in (lang_state.get("usage_main"), lang_state.get("usage_retry")) if u]))
    if final_actual:
        pct = (final_actual / usd * 100) if usd else 0
        print(f"[{lang}] METER final: ${final_actual:.2f} actual vs ${usd:.2f} contract ({pct:.0f}%)")
        if over_budget(final_actual, usd):
            print(f"[{lang}] BUDGET OVERRUN >15% — results are written (already paid), "
                  f"but this run is RED. Audit before the next language (HANDOFF-35).")
            print(f"[{lang}] DONE: {written}/{len(pairs)} written, {len(failed)} logged failures")
            sys.exit(3)

    print(f"[{lang}] DONE: {written}/{len(pairs)} written, {len(failed)} logged failures")
    print(f"[{lang}] next (separate steps): rich render (HANDOFF-22) + gates —")
    print(f"    python3 scripts/build_fulltree_lang.py --lang {lang}")
    print(f"    python3 scripts/gate_render_verified.py")
    return not failed


def recover_language(lang, client):
    """ZERO-SPEND recovery (HANDOFF GO-CS follow-up): re-read the batches this
    language already PAID for (results stay retrievable ~29 days) and re-parse
    every still-missing fiche with the hardened parser. No submit ever happens
    here — only results retrieval, which is free. Validation and the
    absent-field discipline are exactly the ones the live run applies."""
    state = load_state()
    lang_state = state.get(lang) or {}
    batches = []          # (batch_id, {custom_id: slug})
    if lang_state.get("retry_batch_id"):
        batches.append((lang_state["retry_batch_id"],
                        {c: s for c, s in (lang_state.get("retry_id_map") or {}).items()}))
    if lang_state.get("batch_id"):
        batches.append((lang_state["batch_id"], lang_state.get("id_map") or {}))
    if not batches:
        sys.exit(f"[{lang}] nothing to recover — no batch ids in state")

    pairs = pairs_for_lang(lang)                 # exactly the still-missing fiches
    by_slug = {f["slug"]: (f, s) for f, s in pairs}
    print(f"[{lang}] recover: {len(by_slug)} fiche(s) still missing; "
          f"re-reading {len(batches)} paid batch(es)")

    def slug_of(cid, id_map):
        if cid in id_map:
            return id_map[cid]
        # the retry batch of the original cs run predates retry_id_map
        # persistence — reconstruct from the custom_id's slug fragment
        # (f"{lang}-{i:04d}-{slug}"[:64]); match by prefix against the
        # missing set, unique or nothing.
        frag = cid.split("-", 2)[-1] if cid.count("-") >= 2 else ""
        hits = [s for s in by_slug if s.startswith(frag) or frag.startswith(s)]
        return hits[0] if len(hits) == 1 else None

    recovered, still = 0, dict(by_slug)
    for batch_id, id_map in batches:
        if not still:
            break
        print(f"  reading results of {batch_id} …")
        results, _usage = collect_results(client, batch_id)
        for cid, (kind, payload) in results.items():
            if kind != "ok":
                continue
            slug = slug_of(cid, id_map)
            if slug not in still:
                continue
            fiche, src = still[slug]
            try:
                out = parse_result_text(payload)
            except Exception:
                continue                          # still unparsable — next batch
            if validate(src, out, fiche_frozen_nouns(fiche)):
                continue                          # content violations → stays absent
            write_back(fiche, lang, out)
            del still[slug]
            recovered += 1

    state = load_state()
    state.setdefault(lang, {})["written"] = (lang_state.get("written") or 0) + recovered
    state[lang]["recovered"] = recovered
    save_state(state)
    if still:
        log_failures(lang, [(s, ["unrecoverable after quote-repair (recovery run)"])
                            for s in sorted(still)])
    print(f"[{lang}] RECOVERED {recovered} fiche(s) for $0; "
          f"{len(still)} remain absent: {sorted(still)[:10]}{'…' if len(still) > 10 else ''}")
    return recovered


# --------------------------------------------------------------------- audit
def all_source_pairs():
    """{slug: (fiche, src)} for EVERY fiche with FR prose — the full corpus,
    independent of what's already translated (the audit must reconstruct the
    contract-time request set, and user_prompt() is language-independent)."""
    out = {}
    for p in sorted(glob.glob(str(JSON_DIR / "*.json"))):
        fiche = json.load(open(p, encoding="utf-8"))
        fiche["_path"] = p
        src = extract_source(fiche)
        if src:
            out[fiche["slug"]] = (fiche, src)
    return out


def _slug_from_cid(cid, id_map, slugs):
    """custom_id → slug: state-file id_map first, else the slug fragment of
    f'{lang}-{i:04d}-{slug}'[:64] prefix-matched against the corpus (the pt
    retry batch predates id-map persistence)."""
    if cid in id_map:
        return id_map[cid]
    frag = cid.split("-", 2)[-1] if cid.count("-") >= 2 else ""
    if not frag:
        return None
    hits = [s for s in slugs if s == frag or s.startswith(frag)]
    return hits[0] if len(hits) == 1 else None


def audit_batch(client, bid, id_map, chars_by_slug, slugs):
    """Read one paid batch's results ($0) and sum its real usage.
    Returns a record with token totals, actual $, and — for the requests we
    can map back to fiches — the source-char base for calibration."""
    rows, n_ok, n_err = [], 0, 0
    langs_seen = {}
    mapped_src_chars = mapped_in_tok = mapped_out_tok = n_mapped = 0
    out_chars = 0
    for r in client.messages.batches.results(bid):
        cid = r.custom_id
        langs_seen[cid.split("-", 1)[0]] = langs_seen.get(cid.split("-", 1)[0], 0) + 1
        if r.result.type != "succeeded":
            n_err += 1
            continue
        n_ok += 1
        msg = r.result.message
        text = next((b.text for b in msg.content if b.type == "text"), "")
        out_chars += len(text)
        u = usage_of(msg)
        if not u:
            continue
        rows.append(u)
        slug = _slug_from_cid(cid, id_map, slugs)
        if slug in chars_by_slug:
            n_mapped += 1
            mapped_src_chars += chars_by_slug[slug]
            mapped_in_tok += u["input_tokens"] + u["cache_creation_input_tokens"] \
                + u["cache_read_input_tokens"]
            mapped_out_tok += u["output_tokens"]
    tot = sum_usage(rows)
    lang = max(langs_seen, key=langs_seen.get) if langs_seen else "?"
    return {"id": bid, "lang": lang, "ok": n_ok, "err": n_err,
            "usage": tot, "usd": usage_cost_usd(tot), "out_chars": out_chars,
            "n_mapped": n_mapped, "mapped_src_chars": mapped_src_chars,
            "mapped_in_tok": mapped_in_tok, "mapped_out_tok": mapped_out_tok}


def audit_workspace(client):
    """HANDOFF-35 Job B: ZERO-SPEND reconciliation. Enumerate every batch in
    the workspace (results stay readable ~29 days; retrieval is FREE — nothing
    is ever submitted here), sum the API's own per-request usage, price it at
    batch rates, and write:
      reports/translate-cost-reconciliation.md  — line-item actuals vs contract
      reports/translate-cost-calibration.json   — measured factors estimate() uses
    batches.list() also catches batches whose ids never made the state file
    (the pt retry round)."""
    state = load_state()
    known = {}                    # batch_id -> (lang, role, id_map)
    for lang, ls in state.items():
        if not isinstance(ls, dict):
            continue
        if ls.get("batch_id"):
            known[ls["batch_id"]] = (lang, "main", ls.get("id_map") or {})
        if ls.get("retry_batch_id"):
            known[ls["retry_batch_id"]] = (lang, "retry", ls.get("retry_id_map") or {})
    batch_ids = list(known)
    try:
        for b in client.messages.batches.list():
            if b.id not in known and b.id not in batch_ids:
                batch_ids.append(b.id)
    except Exception as e:  # noqa: BLE001 — list is a convenience, ids in state suffice
        print(f"  (batches.list unavailable — auditing state-file ids only: {e})")

    corpus = all_source_pairs()
    slugs = set(corpus)
    chars_by_slug = {s: len(user_prompt(f, src)) for s, (f, src) in corpus.items()}
    communes = all_communes()

    records = []
    for bid in batch_ids:
        try:
            b = client.messages.batches.retrieve(bid)
        except Exception as e:  # noqa: BLE001
            print(f"  skip {bid}: {e}")
            continue
        if getattr(b, "processing_status", "") != "ended":
            print(f"  skip {bid}: processing_status={b.processing_status}")
            continue
        lang_known, role, id_map = known.get(bid, (None, None, {}))
        print(f"  reading {bid} …")
        rec = audit_batch(client, bid, id_map, chars_by_slug, slugs)
        rec["lang"] = lang_known or rec["lang"]
        # an unrecorded batch for a lang that already has a recorded main
        # batch can only be its retry round (the pt case)
        rec["role"] = role or ("retry" if any(
            k for k, (lg, rl, _) in known.items() if lg == rec["lang"] and rl == "main")
            else "main")
        records.append(rec)
        u = rec["usage"]
        print(f"    {rec['lang']}/{rec['role']}: {rec['ok']} ok, {rec['err']} err · "
              f"{u['input_tokens']:,} in / {u['output_tokens']:,} out / "
              f"{u['cache_creation_input_tokens']:,} cache-write / "
              f"{u['cache_read_input_tokens']:,} cache-read tok → ${rec['usd']:.2f}")

    if not records:
        sys.exit("audit: no ended batches found — nothing to reconcile")

    # ---- calibration from the mapped requests (real tokens per real chars)
    tot_req_chars = sum((r["mapped_src_chars"]
                         + r["n_mapped"] * len(system_prompt(r["lang"], communes)))
                        for r in records if r["n_mapped"])
    tot_in_tok = sum(r["mapped_in_tok"] for r in records)
    in_per_char = (tot_in_tok / tot_req_chars) if tot_req_chars else None
    out_per_char = {}
    for lang in sorted({r["lang"] for r in records}):
        sc = sum(r["mapped_src_chars"] for r in records if r["lang"] == lang)
        ot = sum(r["mapped_out_tok"] for r in records if r["lang"] == lang)
        if sc:
            out_per_char[lang] = round(ot / sc, 4)
    tot_all = sum_usage([r["usage"] for r in records])
    cache_read_share = (tot_all["cache_read_input_tokens"]
                        / max(1, tot_all["input_tokens"]
                              + tot_all["cache_creation_input_tokens"]
                              + tot_all["cache_read_input_tokens"]))
    calibration = {
        "_meta": {"written_by": "translate_batch.py --audit",
                  "date": datetime.date.today().isoformat(),
                  "batches": [r["id"] for r in records],
                  "note": "measured from PAID batch results; estimate() prefers "
                          "these over its documented default assumptions"},
        "input_tokens_per_char": round(in_per_char, 4) if in_per_char else None,
        "output_tokens_per_source_char": out_per_char,
        "cache_read_share_observed": round(cache_read_share, 4),
    }
    CALIBRATION_FILE.parent.mkdir(exist_ok=True)
    CALIBRATION_FILE.write_text(
        json.dumps(calibration, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  calibration → {CALIBRATION_FILE}")

    write_reconciliation(records, calibration, corpus, communes)
    print(f"  reconciliation → {RECONCILIATION_MD}")


def write_reconciliation(records, calibration, corpus, communes):
    """The HANDOFF-35 deliverable: line-item actuals vs the contract, the
    identified leaks, and the corrected model — explained to the cent."""
    pairs = list(corpus.values())
    lines = ["# Translation cost reconciliation — HANDOFF-35 Job B",
             "",
             f"_Written by `translate_batch.py --audit` on "
             f"{datetime.date.today().isoformat()} from the paid batches' own "
             f"per-request usage (retrieval is free; nothing was submitted)._",
             "",
             "## Verified before the audit",
             "",
             "1. **Endpoint ✓** — `client.messages.batches.create` "
             "(`/v1/messages/batches`): the 50% batch discount applies. "
             "Constants $1.50/$7.50 per MTok match claude-sonnet-4-6 batch pricing.",
             "2. **Prompt caching ✗** — the shared system prompt (~780 est. tokens) "
             "sits **below Sonnet 4.6's 2048-token minimum cacheable prefix**, so "
             "the `cache_control` marker was silently ignored: every request "
             "re-billed the system block as plain input. The cache-read column "
             "below is the proof.",
             "",
             "## Line items (actuals from usage)",
             "",
             "| batch | lang | role | ok | err | in tok | cache-write | cache-read | out tok | actual $ |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in records:
        u = r["usage"]
        lines.append(f"| `{r['id']}` | {r['lang']} | {r['role']} | {r['ok']} | {r['err']} "
                     f"| {u['input_tokens']:,} | {u['cache_creation_input_tokens']:,} "
                     f"| {u['cache_read_input_tokens']:,} | {u['output_tokens']:,} "
                     f"| ${r['usd']:.2f} |")
    lines += ["", "## Contract vs actual, to the cent", ""]
    for lang in sorted({r["lang"] for r in records}):
        recs = [r for r in records if r["lang"] == lang]
        main = [r for r in recs if r["role"] == "main"]
        rets = [r for r in recs if r["role"] != "main"]
        _, c_in, c_out, c_usd = legacy_estimate(pairs, communes, lang)
        main_usd = sum(r["usd"] for r in main)
        retry_usd = sum(r["usd"] for r in rets)
        act = main_usd + retry_usd
        u_main = sum_usage([r["usage"] for r in main])
        sys_tok_est = est_tokens(system_prompt(lang, communes))
        n_main = sum(r["ok"] + r["err"] for r in main)
        # decomposition of the main-batch delta vs the contract
        in_actual_usd = (u_main["input_tokens"] * BATCH_IN_PER_MTOK
                         + u_main["cache_creation_input_tokens"] * BATCH_CACHE_WRITE_PER_MTOK
                         + u_main["cache_read_input_tokens"] * BATCH_CACHE_READ_PER_MTOK) / 1e6
        in_contract_usd = (c_in * BATCH_IN_PER_MTOK) / 1e6
        out_actual_usd = u_main["output_tokens"] * BATCH_OUT_PER_MTOK / 1e6
        out_contract_usd = c_out * BATCH_OUT_PER_MTOK / 1e6
        cache_leak_usd = (sys_tok_est * max(0, n_main - 1)
                          * (BATCH_IN_PER_MTOK - BATCH_CACHE_READ_PER_MTOK)) / 1e6
        lines += [f"### {lang}", "",
                  f"| item | contract | actual | delta |",
                  f"|---|---|---|---|",
                  f"| input (incl. system block) | ${in_contract_usd:.2f} | ${in_actual_usd:.2f} "
                  f"| {in_actual_usd - in_contract_usd:+.2f} |",
                  f"| output | ${out_contract_usd:.2f} | ${out_actual_usd:.2f} "
                  f"| {out_actual_usd - out_contract_usd:+.2f} |",
                  f"| **main batch** | **${c_usd:.2f}** | **${main_usd:.2f}** "
                  f"| **{main_usd - c_usd:+.2f}** |",
                  f"| retry round(s) (outside the contract) | $0.00 | ${retry_usd:.2f} "
                  f"| {retry_usd:+.2f} |",
                  f"| **total** | **${c_usd:.2f}** | **${act:.2f}** | **{act - c_usd:+.2f}** |",
                  "",
                  f"- of the input delta, the never-firing cache accounts for "
                  f"≈ ${cache_leak_usd:.2f} (system block re-billed at 1× on "
                  f"{max(0, n_main - 1)} requests instead of 0.1×).",
                  f"- measured output: "
                  f"{(calibration['output_tokens_per_source_char'] or {}).get(lang, '—')} "
                  f"tok per source char vs the old model's implicit "
                  f"{round(1 / 3.5, 4)} (out ≈ in assumption).",
                  ""]
    ipc = calibration.get("input_tokens_per_char")
    lines += ["## Corrected model (now live in `estimate()`)", "",
              f"- input: **{ipc} tok/char** measured "
              f"(was chars/3.5 ≈ {round(1 / 3.5, 4)})",
              f"- output: per-language measured factors "
              f"{json.dumps(calibration.get('output_tokens_per_source_char'))} "
              f"(was out ≈ in)",
              "- system block priced **uncached** below the 2048-token minimum "
              "cacheable prefix (was: cached for 388/389 requests)",
              f"- observed cache-read share: "
              f"{calibration.get('cache_read_share_observed')}",
              "",
              "## Permanent rule now enforced in code",
              "",
              "The dry-run number is a contract. A run that exceeds it by >15% "
              "ABORTS before the next paid submit (retry round / next language) "
              "and exits red; the final meter line always prints actual vs "
              "contract. No `go <lang>` until its calibrated dry-run lands and "
              "the previous languages' deltas are explained above.",
              ""]
    RECONCILIATION_MD.parent.mkdir(exist_ok=True)
    RECONCILIATION_MD.write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lang", required=True,
                    help=f"one of {'/'.join(TARGET_LANGS)}, or 'all' (sequence: {' → '.join(TARGET_LANGS)})")
    ap.add_argument("--dry-run", action="store_true",
                    help="print request count + token/cost estimate and stop (no submit)")
    ap.add_argument("--force", action="store_true",
                    help="redo fiche×lang pairs that are already populated")
    ap.add_argument("--recover", action="store_true",
                    help="ZERO-SPEND: re-read this language's already-paid batch results "
                         "and re-parse the missing fiches with the hardened parser (no submit)")
    ap.add_argument("--audit", action="store_true",
                    help="ZERO-SPEND (HANDOFF-35): re-read every paid batch's usage, "
                         "reconcile actual $ vs the dry-run contracts, write the "
                         "reconciliation report + estimator calibration (no submit; "
                         "--lang is ignored — the audit covers the whole workspace)")
    args = ap.parse_args()

    langs = TARGET_LANGS if args.lang == "all" else [args.lang]
    for lang in langs:
        if lang not in TARGET_LANGS:
            sys.exit(f"ERROR: unknown target language {lang!r} (expected {TARGET_LANGS})")

    if args.audit:
        audit_workspace(get_client())
        return

    if args.recover:
        client = get_client()
        for lang in langs:
            recover_language(lang, client)
        return

    client = None if args.dry_run else get_client()
    for lang in langs:
        ok = run_language(lang, args, client)
        if not ok and args.lang == "all":
            print(f"stopping the sequence at {lang} — review the failure log first.")
            sys.exit(1)


if __name__ == "__main__":
    main()
