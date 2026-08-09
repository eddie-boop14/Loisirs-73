#!/usr/bin/env python3
"""Build data/dt-ara-{dept}-candidates.json from the DATAtourisme ARA export.

HANDOFF-73: the ingest queue for a new département, in one command.

Source: the daily simplified DATAtourisme regional export for Auvergne-Rhône-
Alpes, published on data.gouv.fr (~45 MB CSV, licence ouverte). The stable
resource URL below always redirects to the latest daily build.

Filter — identical to the one that produced dt-ara-74-candidates.json
(3012 rows), reverse-engineered from that file and verified at 3012/3012:
  1. `Code postal et commune` starts with the département code (74xxx, 73xxx…)
  2. the POI carries at least one leisure/heritage category among
     SportsAndLeisurePlace · CulturalSite · Tour · NaturalHeritage

Output shape is byte-compatible with the 74 file, so Studio's "Importer DT"
tab and every downstream consumer read it unchanged.

Column mapping is fuzzy (accent/case/separator-insensitive) and FAILS LOUDLY
with the observed header if a required column is missing — the export's
schema is stable but not guaranteed, and a silently mis-mapped column would
poison a whole département's queue.

Usage:
    python3 scripts/extract_dt_dept.py --dept 73
    python3 scripts/extract_dt_dept.py --dept 73 --csv /tmp/ara.csv   # reuse a download
    python3 scripts/extract_dt_dept.py --dept 73 --keep-csv          # keep it for next time

2026 · Bleu canard édition · Edmaster & Claudius 🦆
"""
import argparse
import siteconfig  # HANDOFF-73 phase 5: per-site identity
import csv
import datetime
import json
import os
import re
import sys
import tempfile
import unicodedata
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# data.gouv.fr stable resource URL — redirects to the latest daily ARA export.
ARA_CSV_URL = "https://www.data.gouv.fr/fr/datasets/r/5b3c2cee-44b7-48bd-b4e8-439a03ff6cd2"

# The leisure/heritage gate. Verified: covers 3012/3012 of the committed 74 set
# and nothing beyond it.
LEISURE_GATE = {"SportsAndLeisurePlace", "CulturalSite", "Tour", "NaturalHeritage"}

# target field -> accepted header names (normalised). First match wins.
COLUMN_CANDIDATES = {
    "name":       ["nom du poi", "nom", "label", "name"],
    "categories": ["categories de poi", "categories", "categorie"],
    "lat":        ["latitude", "lat"],
    "lon":        ["longitude", "lon", "lng"],
    "cp_commune": ["code postal et commune", "code postal commune", "cp commune",
                   "code postal et ville", "commune"],
    "maj":        ["date de mise a jour", "date maj", "mise a jour", "updated"],
    "creator":    ["createur de la donnee", "createur", "producteur", "creator"],
    "classement": ["classements du poi", "classements", "classement"],
    "contacts":   ["contacts du poi", "contacts", "contact"],
    "dt_id":      ["uri id du poi", "uri du poi", "uri", "id du poi", "identifiant"],
}
REQUIRED = ["name", "categories", "cp_commune", "dt_id"]


def norm(s):
    """Lowercase, strip accents, collapse separators — for header matching."""
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def map_columns(header):
    normalised = {norm(h): h for h in header}
    mapping, missing = {}, []
    for target, names in COLUMN_CANDIDATES.items():
        hit = next((normalised[n] for n in names if n in normalised), None)
        if hit:
            mapping[target] = hit
        elif target in REQUIRED:
            missing.append(target)
    if missing:
        print("::error::extract_dt_dept: required column(s) not found: "
              + ", ".join(missing), file=sys.stderr)
        print("Observed header:", file=sys.stderr)
        for h in header:
            print(f"    - {h}", file=sys.stderr)
        print("Fix COLUMN_CANDIDATES in this script, then re-run. Nothing written.",
              file=sys.stderr)
        sys.exit(1)
    return mapping


def leaf_categories(value):
    """'…/core#Museum|http://schema.org/Museum' -> {'Museum'}"""
    out = set()
    for uri in (value or "").split("|"):
        uri = uri.strip()
        if uri:
            out.add(uri.rsplit("#", 1)[-1].rsplit("/", 1)[-1])
    return out


_URL_RE = re.compile(r"https?://[^\s|;,]+")


def first_website(contacts):
    """The export packs phone/mail/web into one field; keep the first http(s)."""
    m = _URL_RE.search(contacts or "")
    return m.group(0).rstrip(".,;") if m else ""


def download(url, dest):
    print(f"downloading {url}")
    req = urllib.request.Request(url, headers={
        "User-Agent": f"loisirs-dt-extract/1.0 (+{siteconfig.BASE_URL})"})
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
        total = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            total += len(chunk)
            print(f"\r  {total / 1048576:.1f} MB", end="", flush=True)
    print(f"\r  {total / 1048576:.1f} MB — done")
    return dest


def sniff_dialect(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        sample = f.read(64 * 1024)
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        return csv.excel  # comma is the documented default


def main():
    ap = argparse.ArgumentParser(description="DATAtourisme ARA -> per-département candidate queue.")
    ap.add_argument("--dept", required=True,
                    help="département code, e.g. 73 (matches the postcode prefix)")
    ap.add_argument("--csv", help="path to an already-downloaded ARA export (skips the download)")
    ap.add_argument("--keep-csv", action="store_true", help="keep the downloaded CSV on disk")
    ap.add_argument("--out", help="output path (default: data/dt-ara-{dept}-candidates.json)")
    args = ap.parse_args()

    dept = args.dept.strip()
    if not re.fullmatch(r"\d{2,3}", dept):
        sys.exit(f"::error::--dept must be a 2-3 digit code, got {dept!r}")

    tmp = None
    if args.csv:
        csv_path = Path(args.csv)
        if not csv_path.is_file():
            sys.exit(f"::error::--csv {csv_path} not found")
    else:
        tmp = Path(tempfile.gettempdir()) / "datatourisme-reg-ara.csv"
        csv_path = download(ARA_CSV_URL, tmp)

    dialect = sniff_dialect(csv_path)
    rows, scanned, in_dept = [], 0, 0
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, dialect=dialect)
        if not reader.fieldnames:
            sys.exit("::error::empty CSV — nothing to read")
        col = map_columns(reader.fieldnames)
        print("column mapping: " + ", ".join(f"{k}<-{v}" for k, v in col.items()))
        for rec in reader:
            scanned += 1
            cp = (rec.get(col["cp_commune"]) or "").strip()
            if not cp.startswith(dept):
                continue
            in_dept += 1
            cats = rec.get(col["categories"]) or ""
            if not (leaf_categories(cats) & LEISURE_GATE):
                continue
            rows.append({
                "dt_id": (rec.get(col["dt_id"]) or "").strip(),
                "name": (rec.get(col["name"]) or "").strip(),
                "cp_commune": cp,
                "lat": (rec.get(col.get("lat", "")) or "").strip() if "lat" in col else "",
                "lon": (rec.get(col.get("lon", "")) or "").strip() if "lon" in col else "",
                "website": first_website(rec.get(col["contacts"]) if "contacts" in col else ""),
                "maj": (rec.get(col.get("maj", "")) or "").strip() if "maj" in col else "",
                "classement": (rec.get(col.get("classement", "")) or "").strip() if "classement" in col else "",
                "categories": cats.strip(),
                "creator": (rec.get(col.get("creator", "")) or "").strip() if "creator" in col else "",
            })

    # One row per POI. `dt_id` is the DATAtourisme URI — the record's primary
    # key — so two rows sharing it are the same POI emitted twice by the source,
    # not two places. Savoie's export does this ~84 times (Haute-Savoie's does
    # not). Dropping the repeat is an output-integrity fix, NOT a filter change:
    # the SET of POI kept is identical, and the 74 output is byte-for-byte
    # unchanged (verified: 3012 rows, 3012 unique URIs, 0 dropped). Left in, the
    # duplicates would feed an editor the same place twice and manufacture the
    # exact "twin" defect gate_no_duplicate_lieux.py exists to prevent.
    # Never silent: the count is always printed.
    seen, deduped, dropped = set(), [], 0
    for r in rows:
        key = r["dt_id"] or f'{r["name"]}#{r["cp_commune"]}'
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        deduped.append(r)
    rows = deduped

    rows.sort(key=lambda r: (r["cp_commune"], r["name"]))
    out_path = Path(args.out) if args.out else REPO / "data" / f"dt-ara-{dept}-candidates.json"
    payload = {
        "source": "DATAtourisme ARA export",
        "filter": f"{dept}xxx + leisure categories",
        "generated": datetime.date.today().isoformat(),
        "count": len(rows),
        "rows": rows,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")

    communes = {}
    for r in rows:
        communes[r["cp_commune"]] = communes.get(r["cp_commune"], 0) + 1
    print(f"\nscanned {scanned} POI · {in_dept} in dept {dept} · {len(rows)} kept "
          f"(leisure/heritage gate)")
    print(f"duplicate source rows dropped (same dt_id): {dropped}")
    try:
        shown = out_path.relative_to(REPO)
    except ValueError:
        shown = out_path
    print(f"wrote {shown} ({out_path.stat().st_size // 1024} KB)")
    print("top communes:")
    for cp, n in sorted(communes.items(), key=lambda kv: -kv[1])[:12]:
        print(f"  {n:5d}  {cp}")

    if tmp and not args.keep_csv:
        os.unlink(tmp)
        print("(temporary CSV removed; --keep-csv to keep it)")


if __name__ == "__main__":
    main()
