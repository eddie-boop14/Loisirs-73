#!/usr/bin/env python3
"""Photo-layer corpus audit — HANDOFF (Bénédicte batch) §3.

Sweeps every Json/<slug>.json for five confirmed defect classes:

  1. junk-author   hero_credit whose author segment is not an author name
                   (another lieu's name, a caption like "Mont Blanc panorama")
  2. null-credit   credit null/empty on a non-generic hero or any gallery photo
  3. wrong-region  filename/alt/credit referencing another region (Hautes-Alpes,
                   Vosges, Lago/valle Stretta, Pyrénées, …) — homonym-scrape risk
  4. junk-alt      alt that is a raw filename, ≤3 generic words, or just the
                   lieu name repeated
  5. dup-hero      identical non-generique hero_image shared by several lieux

--report (default) writes reports/photo-audit.md and prints a summary.
--apply is deliberately NOT implemented yet: per the handoff, Eddie reviews the
report first; the mechanical fixer (credits recoverable from the Wikimedia API)
and the gate_photo_credits.py ratchet are wired after that review.
"""
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "reports" / "photo-audit.md"

# House-law visitor credit (verbatim from the Bénédicte manifest) — never junk.
HOUSE_CREDITS = {"Photo : Bénédicte · merci ! 🦆"}

# First-token toponyms that mark an "author" as a caption, not a person.
TOPONYM_TOKENS = {
    "cascade", "mont", "lac", "pont", "col", "gorge", "gorges", "plateau",
    "belvédère", "belvedere", "panorama", "vue", "château", "chateau",
    "sentier", "cirque", "téléphérique", "telepherique", "tramway", "train",
    "aiguille", "pointe", "plage", "grotte", "source",
}

# Wrong-region markers (case-insensitive substring on filename/alt/credit).
REGION_MARKERS = [
    "hautes-alpes", "vosges", "lago", "stretta", "pyrén", "pyrene",
    "dolomit", "tyrol", "tirol", "ardèche", "ardeche", "cantal",
    "lozère", "lozere", "auvergne", "cévennes", "cevennes",
]

FILENAME_ALT = re.compile(r"\.(jpe?g|png|webp|gif)\s*$", re.I)


def is_generic(img):
    base = (img or "").rsplit("/", 1)[-1]
    return base.startswith("generique-")


def author_segment(credit):
    seg = (credit or "").split("·")[0].strip()
    return re.sub(r"^photo\s*:\s*", "", seg, flags=re.I).strip()


def junk_author(credit, lieu_names):
    if not credit or credit in HOUSE_CREDITS:
        return False
    a = author_segment(credit)
    if not a:
        return True
    first = a.split()[0].lower().strip(".,")
    if first in TOPONYM_TOKENS:
        return True
    return a.lower() in lieu_names


def wrong_region(*texts):
    blob = " ".join(t or "" for t in texts).lower()
    return sorted({m for m in REGION_MARKERS if m in blob})


def junk_alt(alt, name):
    a = (alt or "").strip()
    if not a:
        return "empty"
    if FILENAME_ALT.search(a) or "panoramio" in a.lower() or "_" in a:
        return "filename"
    if a.lower() == (name or "").strip().lower():
        return "name-echo"
    if len(a.split()) <= 3:
        return "≤3 words"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", default=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if args.apply:
        raise SystemExit("--apply is gated on Eddie's review of reports/photo-audit.md "
                         "(handoff §3). Not implemented yet on purpose.")

    fiches = {}
    for jp in sorted((ROOT / "Json").glob("*.json")):
        try:
            fiches[jp.stem] = json.loads(jp.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  ! unreadable {jp.name}: {e}")

    lieu_names = {str((d.get("i18n") or {}).get("fr", {}).get("name") or
                      d.get("name") or "").strip().lower()
                  for d in fiches.values()}
    lieu_names |= {s.replace("-", " ") for s in fiches}
    lieu_names.discard("")

    F = defaultdict(list)   # class -> lines
    hero_owners = defaultdict(list)

    for slug, d in sorted(fiches.items()):
        hero = d.get("hero_image") or ""
        credit = d.get("hero_credit")
        name = str((d.get("i18n") or {}).get("fr", {}).get("name") or "")
        gal = d.get("gallery_photos") or []

        if hero and not is_generic(hero):
            hero_owners[hero].append(slug)
            if junk_author(credit, lieu_names):
                F["junk-author"].append(f"- `{slug}` — hero_credit: `{credit}`")
            if not (credit or "").strip():
                F["null-credit"].append(f"- `{slug}` — hero ({hero.rsplit('/',1)[-1]}) credit null")
            marks = wrong_region(hero.rsplit("/", 1)[-1], credit)
            if marks:
                F["wrong-region"].append(f"- `{slug}` — hero `{hero.rsplit('/',1)[-1]}` matches {marks}")

        for i, g in enumerate(gal, 1):
            src, alt, gc = g.get("src") or "", g.get("alt") or "", g.get("credit")
            if not (gc or "").strip():
                F["null-credit"].append(f"- `{slug}` — gallery[{i}] ({src.rsplit('/',1)[-1]}) credit null")
            elif junk_author(gc, lieu_names):
                F["junk-author"].append(f"- `{slug}` — gallery[{i}] credit: `{gc}`")
            marks = wrong_region(src.rsplit("/", 1)[-1], alt, gc)
            if marks:
                F["wrong-region"].append(f"- `{slug}` — gallery[{i}] alt `{alt[:60]}` matches {marks}")
            ja = junk_alt(alt, name)
            if ja:
                F["junk-alt"].append(f"- `{slug}` — gallery[{i}] alt `{alt[:60]}` ({ja})")

    for img, owners in sorted(hero_owners.items()):
        if len(owners) > 1:
            F["dup-hero"].append(f"- {' ≡ '.join(f'`{s}`' for s in owners)} — `{img}`")

    sections = [
        ("1. Junk author field in credit", "junk-author"),
        ("2. Null/empty credit on non-generic media", "null-credit"),
        ("3. Wrong-region / homonym-risk media", "wrong-region"),
        ("4. Filename / generic alts", "junk-alt"),
        ("5. Duplicate hero across lieux", "dup-hero"),
    ]
    total = sum(len(F[k]) for _, k in sections)
    lines = ["# Photo-layer audit — corpus sweep",
             "",
             f"Fiches scanned: **{len(fiches)}** · findings: **{total}**",
             "",
             "Generated by `scripts/audit_photo_layer.py --report`. "
             "Review first; `--apply` + `gate_photo_credits.py` are wired after review (handoff §3).",
             ""]
    for title, key in sections:
        lines += [f"## {title} ({len(F[key])})", ""]
        lines += F[key] or ["- none found"]
        lines += [""]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {REPORT.relative_to(ROOT)}: {total} findings / {len(fiches)} fiches")
    for title, key in sections:
        print(f"  {title}: {len(F[key])}")


if __name__ == "__main__":
    main()
