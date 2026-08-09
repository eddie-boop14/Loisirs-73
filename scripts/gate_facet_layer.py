#!/usr/bin/env python3
"""Facet-layer STRICT gate — HANDOFF-39A-A.

The facet layer is a PROMISE to agent parsers: byte-verbatim heading anchors
in a fixed order, and a typed JSON contract with every key always present.
This gate makes the promise structural. Read-only; any violation → exit 1.

Markdown side (content/<slug>.md FR + content/en/<slug>.md EN, per Json slug):
  - file exists, decodes as strict UTF-8, contains no CR (LF only)
  - no trailing whitespace on any line
  - optional leading YAML frontmatter block (`--- … ---`) is allowed
  - body has EXACTLY ONE H1, byte-equal to `# <i18n.fr.name>` (frozen FR name
    verbatim — both language files)
  - the eight `## ` anchors appear byte-verbatim in EXACTLY the canonical
    order — missing, reordered, typo ("## Hour"), case drift, trailing
    space, or EXTRA `##`/`###` sections are all failures
  - failure output: file + line + expected vs found

JSON side (api/lieu/<slug>.json):
  - exactly the 12 contract keys — a missing key is a failure EVEN IF the
    value would be null (null-ok, absent-key-forbidden); unknown keys too
  - fixed types per key (null allowed where the contract says so)
  - zero-fabrication spot-diff vs Json/ source: name/commune/gps/official_url
    must equal the source fields — a value the corpus doesn't know can never
    appear here

Usage:
    python3 scripts/gate_facet_layer.py [--json-dir D] [--content-dir D] [--root D]
"""
import argparse
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CANON = {
    "fr": ["## Faits", "## Horaires", "## Tarifs", "## Accès (PMR)",
           "## Parking", "## Transport", "## Saison", "## Source officielle"],
    "en": ["## Facts", "## Hours", "## Prices", "## Access (PMR)",
           "## Parking", "## Transport", "## Season", "## Official source"],
}
JSON_KEYS = ["name", "commune", "gps", "type", "hours", "prices", "access_pmr",
             "parking", "transport", "season", "winter", "official_url",
             "last_verified"]

MAX_REPORT = 40


def is_str_or_null(v):
    return v is None or isinstance(v, str)


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def check_md(path, lang, frozen_name, violations):
    rel = os.path.relpath(path, ROOT)
    if not os.path.exists(path):
        violations.append(f"{rel}: MISSING file")
        return
    raw = open(path, "rb").read()
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as e:
        violations.append(f"{rel}: not valid UTF-8 ({e})")
        return
    if b"\r" in raw:
        first = raw.split(b"\r")[0].count(b"\n") + 1
        violations.append(f"{rel}:{first}: CR found — the canon is LF only")
        return

    lines = text.split("\n")

    # trailing whitespace — any line
    for i, ln in enumerate(lines, 1):
        if ln != ln.rstrip():
            violations.append(f"{rel}:{i}: trailing whitespace: {ln!r}")

    # optional leading frontmatter
    body_start = 0
    if lines and lines[0] == "---":
        for j in range(1, len(lines)):
            if lines[j] == "---":
                body_start = j + 1
                break
        else:
            violations.append(f"{rel}:1: unterminated frontmatter block")
            return

    h1s = []          # (lineno, text)
    h2s = []          # (lineno, text) — any line starting with '##'
    for i in range(body_start, len(lines)):
        ln = lines[i]
        if ln.startswith("##"):
            h2s.append((i + 1, ln))
        elif ln.startswith("#"):
            h1s.append((i + 1, ln))

    expected_h1 = f"# {frozen_name}"
    if len(h1s) != 1:
        violations.append(f"{rel}: expected exactly one H1, found {len(h1s)}"
                          + (f" (lines {', '.join(str(n) for n, _ in h1s)})" if h1s else ""))
    else:
        n, ln = h1s[0]
        if ln != expected_h1:
            violations.append(f"{rel}:{n}: H1 drift — expected {expected_h1!r}, found {ln!r}"
                              " (frozen FR name, verbatim)")

    canon = CANON[lang]
    if len(h2s) != len(canon):
        violations.append(f"{rel}: expected {len(canon)} '## ' anchors, found {len(h2s)}")
    for idx in range(max(len(h2s), len(canon))):
        want = canon[idx] if idx < len(canon) else None
        got = h2s[idx] if idx < len(h2s) else None
        if want is None and got is not None:
            violations.append(f"{rel}:{got[0]}: extra section — found {got[1]!r} "
                              f"beyond the {len(canon)}-anchor canon")
        elif got is None and want is not None:
            violations.append(f"{rel}: missing anchor — expected {want!r} at position {idx + 1}")
        elif got[1] != want:
            violations.append(f"{rel}:{got[0]}: anchor drift at position {idx + 1} — "
                              f"expected {want!r}, found {got[1]!r}")


def check_json(path, d_src, violations):
    rel = os.path.relpath(path, ROOT)
    if not os.path.exists(path):
        violations.append(f"{rel}: MISSING file")
        return
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        violations.append(f"{rel}: not valid JSON ({e})")
        return
    if not isinstance(d, dict):
        violations.append(f"{rel}: top level must be an object")
        return

    missing = [k for k in JSON_KEYS if k not in d]
    extra = [k for k in d if k not in JSON_KEYS]
    if missing:
        violations.append(f"{rel}: missing key(s) {missing} — null-ok, absent-key-forbidden")
    if extra:
        violations.append(f"{rel}: unknown key(s) {extra} — the contract is exactly {len(JSON_KEYS)} keys")
    if missing or extra:
        return

    def bad(key, why):
        violations.append(f"{rel}: key '{key}' {why} (found {type(d[key]).__name__}: {d[key]!r:.80})")

    if not isinstance(d["name"], str) or not d["name"]:
        bad("name", "must be a non-empty string")
    for k in ("commune", "type", "hours", "parking", "season", "official_url", "last_verified"):
        if not is_str_or_null(d[k]):
            bad(k, "must be string or null")

    gps = d["gps"]
    if gps is not None:
        if (not isinstance(gps, dict) or set(gps) != {"lat", "lng"}
                or not is_num(gps.get("lat")) or not is_num(gps.get("lng"))):
            bad("gps", "must be null or {lat: number, lng: number}")

    pr = d["prices"]
    if pr is not None:
        ok = (isinstance(pr, dict) and set(pr) == {"from", "currency", "tiers", "is_free", "note"}
              and (pr["from"] is None or is_num(pr["from"]))
              and is_str_or_null(pr["currency"]) and is_str_or_null(pr["note"])
              and (pr["is_free"] is None or isinstance(pr["is_free"], bool))
              and isinstance(pr["tiers"], list)
              and all(isinstance(t, dict) and set(t) == {"name", "price", "note"}
                      for t in pr["tiers"]))
        if not ok:
            bad("prices", "must be null or {from, currency, tiers[{name,price,note}], is_free, note}")

    ap_ = d["access_pmr"]
    if ap_ is not None:
        ok = (isinstance(ap_, dict)
              and set(ap_) == {"status", "detail", "equipment", "handiplage_level",
                               "source_url", "source_name"}
              and isinstance(ap_["status"], str)
              and is_str_or_null(ap_["detail"]) and is_str_or_null(ap_["source_url"])
              and is_str_or_null(ap_["source_name"]) and isinstance(ap_["equipment"], list))
        if not ok:
            bad("access_pmr", "must be null or {status, detail, equipment, handiplage_level, source_url, source_name}")

    tr = d["transport"]
    if tr is not None:
        ok = (isinstance(tr, dict) and set(tr) == {"source", "license", "verified", "stops"}
              and isinstance(tr["stops"], list) and len(tr["stops"]) > 0
              and all(isinstance(s, dict)
                      and set(s) == {"name", "operator", "distance_m", "lines"}
                      and isinstance(s["lines"], list) for s in tr["stops"]))
        if not ok:
            bad("transport", "must be null or {source, license, verified, stops[{name,operator,distance_m,lines}]}")

    # zero-fabrication spot-diff vs the source fiche
    if d["name"] != ((d_src.get("i18n") or {}).get("fr") or {}).get("name", d_src.get("slug")):
        src_name = ((d_src.get("i18n") or {}).get("fr") or {}).get("name")
        if src_name and d["name"] != src_name:
            violations.append(f"{rel}: name {d['name']!r} ≠ source i18n.fr.name {src_name!r}")
    if d["commune"] != (d_src.get("commune") or None):
        violations.append(f"{rel}: commune {d['commune']!r} ≠ source {d_src.get('commune')!r}")
    src_gps = None
    if d_src.get("latitude") is not None and d_src.get("longitude") is not None:
        src_gps = {"lat": d_src["latitude"], "lng": d_src["longitude"]}
    if gps != src_gps and not (gps is None and src_gps is None):
        violations.append(f"{rel}: gps {gps!r} ≠ source {src_gps!r}")


def main():
    ap = argparse.ArgumentParser(description="STRICT facet-layer contract gate (HANDOFF-39A).")
    ap.add_argument("--json-dir", default=os.path.join(ROOT, "Json"))
    ap.add_argument("--content-dir", default=os.path.join(ROOT, "content"))
    ap.add_argument("--root", default=ROOT)
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.json_dir, "*.json")))
    if not files:
        print(f"::error::no fiches under {args.json_dir}/", file=sys.stderr)
        sys.exit(1)

    violations = []
    skipped = 0
    for f in files:
        d = json.load(open(f, encoding="utf-8"))
        # Corpus = published only, mirroring build_ai_content.py: a draft has
        # no HTML page, so the AI surface deliberately omits it (its advertised
        # canonical would be a live 404 — GSC coverage 2026-07-27). Same rule
        # as gate_ai_content; this gate missed the memo until build-gate
        # 2264d300 went red on the 5 draft fiches' absent surfaces.
        if d.get("status") != "published":
            skipped += 1
            continue
        slug = d.get("slug") or os.path.basename(f)[:-5]
        frozen = ((d.get("i18n") or {}).get("fr") or {}).get("name") or slug
        check_md(os.path.join(args.content_dir, f"{slug}.md"), "fr", frozen, violations)
        check_md(os.path.join(args.content_dir, "en", f"{slug}.md"), "en", frozen, violations)
        check_json(os.path.join(args.root, "api", "lieu", f"{slug}.json"), d, violations)

    print(f"gate_facet_layer: {len(files) - skipped} published fiches × (md FR + "
          f"md EN + json) checked against the byte-verbatim canon"
          + (f" ({skipped} non-published excluded)" if skipped else ""))
    if not violations:
        print("✓ facet layer strict-clean: headings byte-verbatim in order, "
              "JSON contract complete and typed, zero fabrication")
        sys.exit(0)
    print(f"::error::{len(violations)} facet-layer violation(s):")
    for v in violations[:MAX_REPORT]:
        print(f"    ✗ {v}")
    if len(violations) > MAX_REPORT:
        print(f"    … and {len(violations) - MAX_REPORT} more")
    print("\nRegenerate: python3 scripts/build_ai_content.py")
    sys.exit(1)


if __name__ == "__main__":
    main()
