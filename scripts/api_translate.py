#!/usr/bin/env python3
"""api_translate.py — finish/repair the masked segments through the Anthropic
Messages API on Eddie's Platform credit (HANDOFF-41, credit lane).

Work-list = every segment that is UNCACHED or whose cached translation fails the
XQV/digit checks (the pipeline's hard gates). Two passes:
  1. batched strict translation (JSON array in/out; parse-fail → per-segment);
  2. targeted per-segment fix for any segment still failing digit-parity, told
     the exact Western-digit multiset it must contain and nothing else.
Only translations that pass ok() are stored; a good existing cache value is kept.
Cache is written incrementally so an interruption never loses accepted work.

    ANTHROPIC_API_KEY=... python3 scripts/api_translate.py <lang>
"""
import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
SCRATCH = ROOT / "scratchpad"
MODEL = "claude-sonnet-5"
BATCH = 15
WORKERS = 8
XQV = re.compile(r"XQV[0-9]+Z")
DIGIT = re.compile(r"[0-9]")

LANG_NAME = {"ja": "Japanese", "ar": "Arabic", "he": "Hebrew"}
SCRIPT = {"ja": "kanji/hiragana/katakana", "ar": "Arabic script", "he": "Hebrew script"}

SYS = """You are a professional French/English→{lang} translator for a Haute-Savoie (France) tourism website (loisirs74.fr).

You receive a JSON array of source text segments (mostly English, some French). Translate each into natural, fluent {lang} ({script}).

RULES (non-negotiable):
- Any token XQV<number>Z (e.g. XQV0Z, XQV12Z) is a MASKED PROPER NAME: copy it VERBATIM — same characters, same number, exactly once each, natural position. Never translate, renumber, duplicate, or drop it.
- CRITICAL DIGIT RULE: the multiset of Western digits 0-9 in each output must EXACTLY equal its source. Copy real numbers (prices, years, distances, times, coordinates) verbatim. NEVER introduce a 0-9 digit absent from the source: if the source spells a number as a WORD (two, both, July, first), render it WITHOUT Western digits — use the target's number words or native numerals (Japanese 二つ/両方/七月; Arabic/Hebrew spelled words), never 2/7. Never drop a source digit.
- Keep € as € when the source has €. Keep URLs/emails/times unchanged. Preserve leading/trailing spaces, punctuation and quotes. Output in {lang}. Translate mid-sentence fragments as fragments.

OUTPUT: reply with ONLY a JSON array, same length and order as the input, each element the translation of the corresponding source segment. No commentary, no markdown fence."""

FIX = """Translate this single segment to {lang}. Reply with ONLY the translation — no quotes, no commentary.
HARD CONSTRAINT: your translation must contain exactly these Western digits (0-9) and NO others: {digits}. Spell every other number as a word or native numeral (e.g. 二つ, 七月) — never add a 0-9 digit, never drop one. Copy any XQV<number>Z token verbatim."""

_lock = threading.Lock()


def _text(msg):
    return "".join(b.text for b in msg.content
                   if getattr(b, "type", None) == "text").strip()


def ok(src, tr):
    if not isinstance(tr, str) or not tr.strip():
        return False
    if sorted(XQV.findall(src)) != sorted(XQV.findall(tr)):
        return False
    if sorted(DIGIT.findall(src)) != sorted(DIGIT.findall(tr)):
        return False
    return True


def batch_translate(client, lang, batch):
    m = client.messages.create(
        model=MODEL, max_tokens=8000,
        system=SYS.format(lang=LANG_NAME[lang], script=SCRIPT[lang]),
        messages=[{"role": "user", "content": json.dumps(batch, ensure_ascii=False)}],
    )
    txt = _text(m)
    if txt.startswith("```"):
        txt = txt.split("\n", 1)[1].rsplit("```", 1)[0]
    out = json.loads(txt)
    if not isinstance(out, list) or len(out) != len(batch):
        raise ValueError("shape")
    return out


def one_translate(client, lang, src):
    m = client.messages.create(
        model=MODEL, max_tokens=1500,
        system=SYS.format(lang=LANG_NAME[lang], script=SCRIPT[lang]),
        messages=[{"role": "user", "content": json.dumps([src], ensure_ascii=False)}])
    try:
        return json.loads(_text(m))[0]
    except Exception:
        return _text(m)


def fix_one(client, lang, src):
    digs = "".join(sorted(DIGIT.findall(src))) or "(none)"
    m = client.messages.create(
        model=MODEL, max_tokens=1500,
        system=FIX.format(lang=LANG_NAME[lang], digits=digs),
        messages=[{"role": "user", "content": src}])
    return _text(m)


def main(lang):
    segs = json.loads((SCRATCH / f"segments-{lang}.json").read_text("utf-8"))
    cf = SCRATCH / f"cache-{lang}.json"
    cache = json.loads(cf.read_text("utf-8")) if cf.exists() else {}
    todo = [s for s in segs if s not in cache or not ok(s, cache[s])]
    print(f"[{lang}] work-list {len(todo)} (uncached+failing) of {len(segs)}", flush=True)
    client = anthropic.Anthropic()
    n = {"done": 0}

    def save():
        cf.write_text(json.dumps(cache, ensure_ascii=False) + "\n", "utf-8")

    # pass 1 — batched
    batches = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]

    def do_batch(b):
        try:
            out = batch_translate(client, lang, b)
        except Exception:
            out = [one_translate(client, lang, s) for s in b]  # fallback
        return list(zip(b, out))

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for pairs in ex.map(do_batch, batches):
            with _lock:
                for s, t in pairs:
                    if ok(s, t):
                        cache[s] = t; n["done"] += 1
                if n["done"] % 500 < BATCH:
                    save()
                    print(f"  …pass1 accepted {n['done']}", flush=True)
    save()

    # pass 2 — targeted fix for still-failing
    still = [s for s in segs if s not in cache or not ok(s, cache[s])]
    print(f"[{lang}] pass2 fixing {len(still)} digit/shape holds", flush=True)

    def do_fix(s):
        for _ in range(2):
            t = fix_one(client, lang, s)
            if ok(s, t):
                return s, t
        return s, None

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for i, (s, t) in enumerate(ex.map(do_fix, still), 1):
            with _lock:
                if t is not None:
                    cache[s] = t
                if i % 300 == 0:
                    save(); print(f"  …pass2 {i}/{len(still)}", flush=True)
    save()
    final_absent = [s for s in segs if s not in cache or not ok(s, cache[s])]
    print(f"[{lang}] DONE: {len(segs)-len(final_absent)}/{len(segs)} clean "
          f"({len(final_absent)} still absent)", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
