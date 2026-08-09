#!/usr/bin/env python3
"""leak_translate.py — HANDOFF i18n-fr-leak JOB 2 driver (FR is the reference).

Translates ONLY the leaked lang-fields listed in reports/i18n-leak-baseline.json,
straight from i18n.fr (never a pivot language), field by field, and writes the
result into i18n.<lang>.<field>. Frozen French names, communes, numbers, €, and
the winter controlled-vocab tokens are preserved verbatim; the shape/tag/frozen
validators from translate_batch are reused and extended with digit/€ + winter
guards. Nothing is applied unless it validates (null discipline).

    --lang de --extract [--limit N | --slugs a,b]  → reports/leak-work-de.json
        (work-list: {slug, name, commune, frozen[], winter_tokens[], fields})
    --lang de --apply                              → validates reports/leak-out-de.json
        and writes i18n.de.<field> for every field that passes; reports failures.

The translation itself (work-list → out-list) is produced in-session (subscription
engine), not by this script — this script only extracts, validates, and applies.
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import translate_batch as TB  # noqa: E402  (reuse validators + frozen-noun logic)

JSON_DIR = os.path.join(ROOT, "Json")
BASELINE = os.path.join(ROOT, "reports", "i18n-leak-baseline.json")
PROT_MANIFEST = os.path.join(ROOT, "reports", "protected-placements.md")


def protected_pages():
    """Set of built page paths carrying a partner domain (gate ground truth).
    A fiche whose <lang>/<slug>.html is here is byte-frozen — the leak job must
    NOT translate it (that would drift a protected page). Excluded + flagged for
    Eddie's separately-approved partner-page commit, mirroring the lastmod/share
    handoff decision."""
    pages = set()
    try:
        for line in open(PROT_MANIFEST, encoding="utf-8").read().splitlines():
            if line.startswith("| ") and ".html |" in line:
                c = line.split("|")[1].strip()
                if c and c != "page":
                    pages.add(c)
    except Exception:
        pass
    return pages


def _is_protected(slug, lang, prot):
    return (f"{lang}/{slug}.html" in prot) or (lang == "fr" and f"{slug}.html" in prot)

# facts sub-keys that are controlled tokens / frozen data, NOT prose — never
# translated (the winter gate enforces their vocab; commune is a frozen name).
FACTS_FROZEN_KEYS = {"winter_access", "winter_infra", "snow_view", "col_chains",
                     "commune"}


def _norm_thousands(text):
    """Collapse a thousands separator (space/dot/comma/nbsp) that sits between a 1-3
    digit group and a 3-digit group: '1 461' → '1461', '1.035' → '1035'. This
    normalizes FR '1 461 m' vs DE '1461 m' without over-merging two distinct
    adjacent numbers ('2026 2026' — the second group is 4 digits, not 3)."""
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"(?<!\d)(\d{1,3})[ .,  ](\d{3})(?!\d)", r"\1\2", text)
    return text


def digit_runs(text):
    """Multiset of maximal digit runs, after normalizing thousands separators.
    The apply check requires every SOURCE run to survive (drops/changes fail);
    EXTRA output digits are allowed — Roman→Arabic century conversion (XIIIe →
    '13. Jahrhundert') is a correct translation, not a fabricated number. Added
    prices are still caught by the separate € count check."""
    from collections import Counter
    return Counter(re.findall(r"\d+", _norm_thousands(text)))


def winter_tokens(fiche):
    facts = ((fiche.get("i18n") or {}).get("fr") or {}).get("facts") or {}
    toks = []
    for k in ("winter_access", "snow_view"):
        v = facts.get(k)
        if isinstance(v, str):
            toks.append(v)
    for v in (facts.get("winter_infra") or []):
        toks.append(v)
    return toks


def _translatable_letters(value, frozen):
    """Letters left after stripping frozen nouns, digits and punctuation — a
    proxy for 'is there real prose to translate here'. A meta_title like
    'Col de la Colombière · Le Reposoir (Haute-Savoie) | Loisirs 74' is entirely
    frozen names + brand, so its target is byte-identical to FR by nature: no
    point translating it (it can only leak forever or get its brand mistranslated)."""
    text = " ".join(TB.strings_of(value))
    for n in sorted(frozen, key=len, reverse=True):
        text = text.replace(n, " ")
    text = re.sub(r"[\W\d_]+", "", text, flags=re.UNICODE)
    return len(text)


def work_for(fiche, fields, frozen=None):
    """Build the FR-source payload for the leaked fields of one fiche. facts
    drops its frozen/controlled sub-keys; proper-noun-only fields (no real prose
    after removing frozen names/numbers) are dropped as untranslatable and
    returned separately so the gate can allowlist them instead of re-batching."""
    fr = (fiche.get("i18n") or {}).get("fr") or {}
    out, untranslatable = {}, []
    for f in fields:
        v = fr.get(f)
        if v in (None, "", [], {}):
            continue
        payload = ({k: val for k, val in v.items() if k not in FACTS_FROZEN_KEYS}
                   if f == "facts" and isinstance(v, dict) else v)
        if frozen is not None and _translatable_letters(payload, frozen) < 8:
            untranslatable.append(f)
            continue
        out[f] = payload
    return out, untranslatable


def load_baseline_lang(lang):
    base = json.load(open(BASELINE, encoding="utf-8"))
    return {s: d[lang] for s, d in base.items() if lang in d}


def load_fiche(slug):
    return json.load(open(os.path.join(JSON_DIR, slug + ".json"), encoding="utf-8"))


def cmd_extract(lang, limit=None, slugs=None, include_protected=False):
    work = load_baseline_lang(lang)
    if slugs:
        work = {s: work[s] for s in slugs if s in work}
    prot = protected_pages()
    excluded = [s for s in sorted(work) if _is_protected(s, lang, prot)]
    items = []
    untr = {}   # {slug: [fields]} proper-noun-only, allowlist candidates
    for slug in sorted(work):
        if _is_protected(slug, lang, prot) and not include_protected:
            continue  # partner-carrying page stays byte-frozen (flagged, not translated)
        fiche = load_fiche(slug)
        fields = work[slug]
        frozen = TB.fiche_frozen_nouns(fiche)
        payload, ut = work_for(fiche, fields, frozen)
        if ut:
            untr[slug] = ut
        if not payload:
            continue
        items.append({
            "slug": slug,
            "name": (fiche.get("i18n", {}).get("fr", {}) or {}).get("name") or slug,
            "commune": fiche.get("commune") or "",
            "frozen": frozen,
            "winter_tokens": winter_tokens(fiche),
            "fields": payload,
        })
        if limit and len(items) >= limit:
            break
    if untr:
        json.dump(untr, open(os.path.join(ROOT, "reports", f"leak-untranslatable-{lang}.json"),
                             "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    outp = os.path.join(ROOT, "reports", f"leak-work-{lang}.json")
    json.dump({"lang": lang, "items": items}, open(outp, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    nfields = sum(len(i["fields"]) for i in items)
    print(f"[leak-tr] {lang}: {len(items)} fiches · {nfields} fields → "
          f"{os.path.relpath(outp, ROOT)} (source = i18n.fr, verbatim)")
    if excluded and not include_protected:
        print(f"[leak-tr] {lang}: EXCLUDED {len(excluded)} partner-carrying fiches "
              f"(byte-frozen, flag for Eddie): {', '.join(excluded)}")
    if include_protected and excluded:
        print(f"[leak-tr] {lang}: INCLUDING {len(excluded)} partner-carrying fiches "
              f"(EDMASTER-approved run — partner block byte-diff verified separately): "
              f"{', '.join(excluded)}")
    if untr:
        nf = sum(len(v) for v in untr.values())
        print(f"[leak-tr] {lang}: {nf} proper-noun-only field(s) across {len(untr)} fiches "
              f"are UNTRANSLATABLE (byte-identical to FR by nature) → "
              f"reports/leak-untranslatable-{lang}.json for allowlist, not batched")


def validate_item(fiche, src_fields, out_fields, frozen, wtokens):
    """Return violation list for one fiche's translated fields (empty = PASS)."""
    viol = []
    # per-field shape/tag/frozen/length/empty (reuse translate_batch.validate)
    for f, src in src_fields.items():
        if f not in out_fields:
            viol.append(f"{f}: missing from output")
            continue
        viol += [f"{f}: {v}" for v in TB.validate(src, out_fields[f], frozen)]
    # digit/€ parity across the whole payload
    src_all = "\n".join(TB.strings_of(src_fields))
    out_all = "\n".join(TB.strings_of({f: out_fields.get(f) for f in src_fields}))
    # YEARS must survive verbatim — they are factual, SEO-visible, and never
    # legitimately reformatted (unlike prices/altitudes/phones/times, which cross
    # locales with different separators and idioms and which Sonnet preserves
    # reliably; over-strict digit parsing there only false-positives on good
    # translations, e.g. '24/7'→'247' or respaced phone numbers). Shape parity,
    # frozen nouns and length ratio (translate_batch.validate) guard the rest.
    # A DECADE keeps its year across locales but changes suffix — FR "années 2010",
    # EN "the 2010s", DE "2010er Jahre" all preserve 2010; the plain \b…\b form
    # misses "2010s"/"2010er" (trailing letter blocks the boundary) and false-flags
    # a drop. Require no *digit* on either side so "20100"/"12010" still don't match.
    years = lambda t: set(re.findall(r"(?<!\d)(?:19|20)\d\d(?!\d)", t))
    dropped_years = years(src_all) - years(out_all)
    if dropped_years:
        viol.append(f"year(s) dropped/changed: {sorted(dropped_years)}")
    # winter tokens must survive verbatim if they were in a translated string
    for t in wtokens:
        if t in src_all and t not in out_all:
            viol.append(f"winter token lost: {t!r}")
    return viol


def cmd_apply(lang, include_protected=False):
    workp = os.path.join(ROOT, "reports", f"leak-work-{lang}.json")
    outp = os.path.join(ROOT, "reports", f"leak-out-{lang}.json")
    if not os.path.exists(outp):
        sys.exit(f"[leak-tr] no {os.path.relpath(outp, ROOT)} — translate the work-list first")
    work = {i["slug"]: i for i in json.load(open(workp, encoding="utf-8"))["items"]}
    outs = json.load(open(outp, encoding="utf-8"))
    outs = outs.get("items", outs) if isinstance(outs, dict) else outs
    prot = protected_pages()
    applied = failed = skipped = 0
    fail_log = []
    for slug, out_fields in (outs.items() if isinstance(outs, dict) else
                             ((o["slug"], o["fields"]) for o in outs)):
        if _is_protected(slug, lang, prot) and not include_protected:
            skipped += 1; continue  # partner-carrying page stays byte-frozen
        if slug not in work:
            fail_log.append((slug, ["not in work-list"])); failed += 1; continue
        w = work[slug]
        viol = validate_item(load_fiche(slug), w["fields"], out_fields,
                             w["frozen"], w["winter_tokens"])
        if viol:
            fail_log.append((slug, viol)); failed += 1; continue
        # write into i18n.<lang>.<field>, re-attaching frozen facts sub-keys
        fiche = load_fiche(slug)
        loc = fiche.setdefault("i18n", {}).setdefault(lang, {})
        fr = fiche["i18n"]["fr"]
        for f, val in out_fields.items():
            if f == "facts" and isinstance(val, dict):
                merged = dict(val)
                for k in FACTS_FROZEN_KEYS:
                    if k in (fr.get("facts") or {}):
                        merged[k] = fr["facts"][k]
                loc[f] = {k: merged[k] for k in fr["facts"]} if isinstance(fr.get("facts"), dict) else merged
            else:
                loc[f] = val
        with open(os.path.join(JSON_DIR, slug + ".json"), "w", encoding="utf-8") as fh:
            json.dump(fiche, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        applied += 1
    print(f"[leak-tr] {lang}: applied {applied} fiches, {failed} failed validation, "
          f"{skipped} skipped (protected/byte-frozen)")
    for slug, viol in fail_log[:30]:
        print(f"    ✗ {slug}: {viol[0]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lang", required=True)
    ap.add_argument("--extract", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--slugs", help="comma-separated slug subset")
    ap.add_argument("--include-protected", action="store_true",
                    help="INCLUDE partner-carrying fiches (EDMASTER-approved runs "
                         "only; partner block byte-stability is verified separately). "
                         "Default excludes them, keeping the carrying page byte-frozen.")
    args = ap.parse_args()
    slugs = args.slugs.split(",") if args.slugs else None
    if args.extract:
        cmd_extract(args.lang, limit=args.limit, slugs=slugs,
                    include_protected=args.include_protected)
    elif args.apply:
        cmd_apply(args.lang, include_protected=args.include_protected)
    else:
        ap.print_help(); sys.exit(1)


if __name__ == "__main__":
    main()
