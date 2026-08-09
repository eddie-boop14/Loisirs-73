#!/usr/bin/env python3
"""gate_i18n_leak.py — HANDOFF-i18n-fr-leak JOB 1. Make the FR-scaffold class extinct.

The May import cohort published non-FR pages whose deep-content fields are
byte-identical to i18n.fr — French FAQ, French activity cards, French JSON-LD
served to en/de/it/es users and to Google. This gate stops any NEW such leak
from ever merging again, while tolerating the known backlog until JOB 2 clears it.

Detector (single source of truth, must stay deterministic — the baseline is
generated FROM it):

    for every lieu × every non-FR lang, a field leaks iff
        canon(i18n.<lang>.<field>) == canon(i18n.fr.<field>)   (byte-identical)
        AND len(canon(i18n.fr.<field>)) > 60                    (skip short/date/proper-noun)
        AND field not in ALLOW                                  (frozen French, correct by law)

    canon(v) = json.dumps(v, ensure_ascii=False, sort_keys=True)   # DEFAULT separators

Ratchet, not massacre:
    baseline (reports/i18n-leak-baseline.json) = the known leak set at ship time.
    - current leak in baseline      → WARN (known debt, JOB 2 clears it)
    - current leak NOT in baseline  → FAIL (a new FR-scaffold walked in — the door)
    The baseline may only shrink. `--tighten` rewrites it = the current leak set
    (asserts current ⊆ baseline first, so a tighten can never smuggle a new leak in).
    When the baseline reaches empty the gate is strict for the whole class.

Usage:
    gate_i18n_leak.py               # CI mode: FAIL on any leak outside baseline
    gate_i18n_leak.py --emit-baseline   # write baseline = current leak set (bootstrap)
    gate_i18n_leak.py --tighten     # shrink baseline to current (run after each batch)

Read-only in CI mode. Wire AFTER gate_render_mode_isolation.
"""
import argparse
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_DIR = os.path.join(ROOT, "Json")
BASELINE = os.path.join(ROOT, "reports", "i18n-leak-baseline.json")

# Fields identical across langs BY LAW, not by leak. name_alternates carries the
# frozen French names (Mont-Blanc, Lac d'Annecy, lieu proper nouns) which must be
# verbatim in every language. Extend ONLY with Eddie's explicit go.
ALLOW = {"name_alternates"}

# Never fail the build on these regardless of state — protected partner fiches are
# translated only by explicit human go (they are not in the cohort). Listed so a
# future accidental leak here is surfaced as a WARN, never a silent CI break that
# would pressure a rushed edit to a protected page.
PROTECTED = {"chez-nous-a-la-plage", "chalet-du-tornet"}

MIN_LEN = 60


def canon(v):
    # DEFAULT separators (", " / ": ") — this is the serialization the shipped
    # audit/baseline was built with; changing it desyncs detector from baseline.
    return json.dumps(v, ensure_ascii=False, sort_keys=True)


def current_leaks():
    """Return {slug: {lang: sorted([fields])}} for the live Json tree."""
    out = {}
    for p in sorted(glob.glob(os.path.join(JSON_DIR, "*.json"))):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        slug = d.get("slug") or os.path.basename(p)[:-5]
        i = d.get("i18n") or {}
        fr = i.get("fr") or {}
        if not isinstance(fr, dict) or not fr:
            continue
        for lang, fields in i.items():
            if lang == "fr" or not isinstance(fields, dict):
                continue
            leaked = []
            for k, v in fields.items():
                if k in ALLOW or k not in fr:
                    continue
                cf = canon(fr[k])
                if len(cf) > MIN_LEN and canon(v) == cf:
                    leaked.append(k)
            if leaked:
                out.setdefault(slug, {})[lang] = sorted(leaked)
    return out


def flat(m):
    """{slug: {lang: [fields]}} -> set of (slug, lang, field) triples."""
    return {(s, l, k) for s, ld in m.items() for l, fs in ld.items() for k in fs}


def dump(m, path):
    ordered = {s: {l: m[s][l] for l in sorted(m[s])} for s in sorted(m)}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(ordered, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")


def load_baseline():
    if not os.path.exists(BASELINE):
        return {}
    return json.load(open(BASELINE, encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--emit-baseline", action="store_true",
                    help="write baseline = current leak set (bootstrap only)")
    ap.add_argument("--tighten", action="store_true",
                    help="shrink baseline to the current leak set (after a batch lands)")
    args = ap.parse_args()

    cur = current_leaks()
    cur_set = flat(cur)

    if args.emit_baseline:
        dump(cur, BASELINE)
        print(f"gate_i18n_leak: wrote baseline = {len(cur_set)} leaked lang-fields "
              f"across {len(cur)} lieux → {os.path.relpath(BASELINE, ROOT)}")
        return

    base_set = flat(load_baseline())

    if args.tighten:
        outside = cur_set - base_set
        if outside:
            print("gate_i18n_leak: --tighten REFUSED — current leaks are outside the "
                  "baseline (a new leak must be fixed, not baselined):")
            for s, l, k in sorted(outside)[:40]:
                print(f"    ✗ {s} [{l}] {k}")
            sys.exit(1)
        dump(cur, BASELINE)
        removed = len(base_set) - len(cur_set)
        print(f"gate_i18n_leak: baseline tightened {len(base_set)} → {len(cur_set)} "
              f"leaked lang-fields (−{removed}).")
        return

    # CI mode
    new = sorted((s, l, k) for (s, l, k) in (cur_set - base_set) if s not in PROTECTED)
    warn = cur_set & base_set
    prot = sorted((s, l, k) for (s, l, k) in (cur_set - base_set) if s in PROTECTED)

    print(f"gate_i18n_leak: {len(cur_set)} leaked lang-fields live "
          f"({len(warn)} known/baselined, {len(new)} NEW).")
    if prot:
        print(f"  ⚠ {len(prot)} leak(s) on PROTECTED fiches — surfaced, not failed:")
        for s, l, k in prot[:20]:
            print(f"      ⚠ {s} [{l}] {k}")
    if new:
        print(f"::error::{len(new)} NEW FR-scaffold leak(s) outside baseline — "
              f"translate them or they cannot merge:")
        for s, l, k in new[:60]:
            print(f"    ✗ {s} [{l}] {k}")
        if len(new) > 60:
            print(f"    … and {len(new) - 60} more")
        sys.exit(1)
    if warn:
        print(f"  ↳ {len(warn)} baselined leak(s) remain (JOB 2 backlog); baseline may only shrink.")
    print("OK no FR-scaffold leak outside the baseline; the door is closed.")


if __name__ == "__main__":
    main()
