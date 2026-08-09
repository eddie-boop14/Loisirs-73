#!/usr/bin/env python3
"""Apply the Bénédicte photo batch (benedicte-2026-07) — HANDOFF routing.

Source of truth: incoming-benedicte/manifest.json (file → slug/role/order/
alt/credit). Routing rules (HANDOFF §1–§2):

  hero    → img/<bucket>/<slug>-hero.jpg   (longest edge ≤ 2000 px, resize-only)
  gallery → img/<bucket>/<slug>-<n>.jpg    (longest edge ≤ 1600 px)
  source  → reports/photo-sources/          (repo-internal, NEVER public img/)
  spare / parked → stay under incoming-benedicte/, no action

Json/<slug>.json gets hero_image + hero_credit set and gallery_photos
entries {src, alt, credit} in manifest order.

Flagged interpretations (report: reports/photo-audit.md §Bénédicte batch):
  * train-du-montenvers: manifest orders 1–6 collide with the freshly shipped
    Wikimedia gallery 1–3 (real, credited, NOT on the retire list). Handoff
    verb is "append" and mont-saleve's order=4 shows numbering follows
    existing files — so Bénédicte's 1–6 land as files -4…-9, appended.
  * lac-vert-passy: Mangatome hero visually verified NOT Passy (no Mont-Blanc;
    Valle Stretta look-alike) → manifest item 01 promoted to hero per §2;
    items 02–04 keep their manifest numbers as gallery files -2…-4.
  * Quarantined to reports/photo-quarantine/: lac-vert hero+gallery 1–5 (all
    wrong-subject, #5 visually a tropical quarry), pont-de-la-caille
    hero+gallery 1–4 (credit null, origin unvouched), and the orphaned
    cascade-du-rouget-1…5 / cirque-du-fer-a-cheval-1…5 files (on-disk but
    referenced by no fiche; their numbers are re-used by this batch).

Idempotent: re-running produces the same tree.
"""
import json
import shutil
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "incoming-benedicte" / "manifest.json"
QUAR = ROOT / "reports" / "photo-quarantine"
SOURCES = ROOT / "reports" / "photo-sources"

BUCKET = {
    "point-de-vue": "points-de-vue",
    "cascade": "cascades",
    "chateau": "chateaux",
    "lac": "lacs-plages",
    "sentier": "sentiers",
    "telecabine": "telecabines",
    "attraction": "que-faire",   # parc animalier precedent: grande-jeanne
}

HERO_MAX, GALLERY_MAX = 2000, 1600

# slug → offset added to manifest gallery order when numbering files
# (montenvers keeps its existing real Wikimedia gallery 1–3).
ORDER_OFFSET = {"train-du-montenvers-mer-de-glace": 3}

# lac-vert-passy item 01 is promoted hero (§2); handled explicitly below.
PROMOTED_HERO = ("lac-vert-passy", 1)

QUARANTINE = [
    "img/lacs-plages/lac-vert-passy-hero.jpg",
    "img/lacs-plages/lac-vert-passy-1.jpg",
    "img/lacs-plages/lac-vert-passy-2.jpg",
    "img/lacs-plages/lac-vert-passy-3.jpg",
    "img/lacs-plages/lac-vert-passy-4.jpg",
    "img/lacs-plages/lac-vert-passy-5.jpg",
    "img/points-de-vue/pont-de-la-caille-hero.jpg",
    "img/points-de-vue/pont-de-la-caille-1.jpg",
    "img/points-de-vue/pont-de-la-caille-2.jpg",
    "img/points-de-vue/pont-de-la-caille-3.jpg",
    "img/points-de-vue/pont-de-la-caille-4.jpg",
    "img/cascades/cascade-du-rouget-1.jpg",
    "img/cascades/cascade-du-rouget-2.jpg",
    "img/cascades/cascade-du-rouget-3.jpg",
    "img/cascades/cascade-du-rouget-4.jpg",
    "img/cascades/cascade-du-rouget-5.jpg",
    "img/cascades/cirque-du-fer-a-cheval-1.jpg",
    "img/cascades/cirque-du-fer-a-cheval-2.jpg",
    "img/cascades/cirque-du-fer-a-cheval-3.jpg",
    "img/cascades/cirque-du-fer-a-cheval-4.jpg",
    "img/cascades/cirque-du-fer-a-cheval-5.jpg",
]
# Stale derived artifacts of retired heroes — deleted, not quarantined.
DELETE = [
    "img/lacs-plages/lac-vert-passy-hero.webp",
    "img/points-de-vue/pont-de-la-caille-hero.webp",
]

# Fiches whose gallery_photos array is replaced outright (old set retired).
GALLERY_REPLACE = {"lac-vert-passy", "pont-de-la-caille"}


def process(src: Path, dest: Path, max_edge: int):
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        w, h = im.size
        scale = max_edge / max(w, h)
        if scale < 1:
            im = im.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
        dest.parent.mkdir(parents=True, exist_ok=True)
        im.save(dest, "JPEG", quality=85, optimize=True)


def main():
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    items = m["items"]

    # 0. quarantine + retire
    QUAR.mkdir(parents=True, exist_ok=True)
    quarantined_now = set()
    for rel in QUARANTINE:
        p = ROOT / rel
        # first quarantine wins: on re-runs the path already holds this
        # batch's replacement file, which must NOT overwrite the evidence
        if p.exists() and not (QUAR / p.name).exists():
            shutil.move(str(p), str(QUAR / p.name))
            quarantined_now.add(rel)
            print(f"quarantined {rel}")
    for rel in DELETE:
        # a retired hero's stale .webp — only stale the moment its jpg was
        # quarantined; later runs must not delete the regenerated sibling
        p = ROOT / rel
        if p.exists() and rel[:-5] + ".jpg" in quarantined_now:
            p.unlink()
            print(f"deleted stale {rel}")

    # Publish items (hero/gallery) apply per-fiche atomically: if any of a
    # slug's files is missing, the whole slug is deferred to a later re-run
    # (idempotent) instead of shipping a gallery with holes.
    incomplete = {it["slug"] for it in items
                  if it["role"] in ("hero", "gallery")
                  and not (ROOT / it["file"]).exists()}
    for slug in sorted(incomplete):
        print(f"!! DEFERRED {slug}: publish file(s) missing — re-run after upload")

    # 1. route files + collect Json edits
    hero_of, gallery_of = {}, {}
    for it in items:
        src = ROOT / it["file"]
        slug, role = it["slug"], it["role"]
        if role in ("spare", "parked") or (slug in incomplete and role != "source"):
            continue
        if not src.exists():
            raise SystemExit(f"MISSING file for manifest item: {it['file']}")
        if role == "source":
            SOURCES.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, SOURCES / src.name)
            continue
        d = json.loads((ROOT / "Json" / f"{slug}.json").read_text(encoding="utf-8"))
        bucket = BUCKET[d["category"]]
        if role == "hero" or (slug, it["order"]) == PROMOTED_HERO:
            dest = ROOT / "img" / bucket / f"{slug}-hero.jpg"
            process(src, dest, HERO_MAX)
            hero_of[slug] = (f"/img/{bucket}/{slug}-hero.jpg", it["credit"])
        else:
            n = it["order"] + ORDER_OFFSET.get(slug, 0)
            dest = ROOT / "img" / bucket / f"{slug}-{n}.jpg"
            process(src, dest, GALLERY_MAX)
            gallery_of.setdefault(slug, []).append(
                {"src": f"/img/{bucket}/{slug}-{n}.jpg",
                 "alt": it["alt_fr"], "credit": it["credit"]})
        print(f"routed {it['file']} -> {dest.relative_to(ROOT)}")

    # 2. Json updates
    touched = sorted(set(hero_of) | set(gallery_of))
    for slug in touched:
        jp = ROOT / "Json" / f"{slug}.json"
        d = json.loads(jp.read_text(encoding="utf-8"))
        if slug in hero_of:
            d["hero_image"], d["hero_credit"] = hero_of[slug]
        if slug in gallery_of:
            base = [] if slug in GALLERY_REPLACE else (d.get("gallery_photos") or [])
            new_srcs = {g["src"] for g in gallery_of[slug]}
            base = [g for g in base if g.get("src") not in new_srcs]  # idempotency
            d["gallery_photos"] = base + gallery_of[slug]
        jp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
        print(f"updated Json/{slug}.json")

    print(f"done: {len(hero_of)} heroes, "
          f"{sum(len(v) for v in gallery_of.values())} gallery photos, "
          f"{len(touched)} fiches")


if __name__ == "__main__":
    main()
