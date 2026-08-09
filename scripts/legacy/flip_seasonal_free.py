#!/usr/bin/env python3
"""
Re-tag the seasonally-paid Lac d'Annecy beaches (Saint-Jorioz, Menthon-
Saint-Bernard) as FREE across all hubs: access is free year-round outside
the supervised summer season, and the seasonal fee is documented in each
beach's own page. Flips the card badge (is-payant -> is-gratuit + localized
word) and the map PIN `paid` flag. Thonon municipale + Évian centre nautique
stay paid (genuine entry-fee aquatic centres, is_free:false).
Also aligns schema_org.is_free + lieux.json.
"""
import re
import json
from pathlib import Path

ROOT = Path("/home/user/Loisir-74")

FLIP_SLUGS = ["plage-de-saint-jorioz", "plage-de-menthon-saint-bernard"]

# file -> localized "free" word for the card badge
HUBS = {
    "lacs/index.html": "Gratuit",
    "en/lakes/index.html": "Free",
    "de/seen/index.html": "Kostenlos",
    "it/laghi/index.html": "Gratuito",
    "es/lagos/index.html": "Gratis",
    "plages/index.html": "Gratuit",
    "en/beaches/index.html": "Free",
    "de/straende/index.html": "Kostenlos",
    "it/spiagge/index.html": "Gratuito",
    "es/playas/index.html": "Gratis",
}


def flip_hub(rel, free_word):
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    n_tag = n_pin = 0
    for slug in FLIP_SLUGS:
        # card badge: from the card-photo href down to its card-tag span
        # bounded to the card-photo anchor (no crossing into another card via </a>)
        tag_re = re.compile(
            r'(href="https://loisirs74\.fr/(?:en/|de/|it/|es/)?' + re.escape(slug)
            + r'">(?:(?!</a>).)*?<span class="card-tag )is-payant(">)([^<]*)(</span>)',
            re.DOTALL,
        )
        text, c = tag_re.subn(lambda m: m.group(1) + "is-gratuit" + m.group(2) + free_word + m.group(4), text, count=1)
        n_tag += c
        # PIN paid flag
        pin_re = re.compile(r'("slug":\s*"' + re.escape(slug) + r'"[^}]*?"paid":\s*)true')
        text, c = pin_re.subn(lambda m: m.group(1) + "false", text, count=1)
        n_pin += c
    path.write_text(text, encoding="utf-8")
    return n_tag, n_pin


def align_registries():
    # schema_org.is_free in per-slug JSON
    for slug in FLIP_SLUGS:
        jp = ROOT / "Json" / f"{slug}.json"
        if jp.exists():
            d = json.loads(jp.read_text(encoding="utf-8"))
            if d.get("schema_org", {}).get("is_free") is not True:
                d.setdefault("schema_org", {})["is_free"] = True
                jp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print(f"  ✓ {jp.name} schema_org.is_free -> true")
    # master lieux.json
    lp = ROOT / "lieux.json"
    d = json.loads(lp.read_text(encoding="utf-8"))
    items = d if isinstance(d, list) else d.get("lieux", d.get("items", []))
    changed = 0
    for it in items:
        if it.get("slug") in FLIP_SLUGS and it.get("is_free") is not True:
            it["is_free"] = True
            changed += 1
    if changed:
        lp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"  ✓ lieux.json is_free -> true ({changed})")


def main():
    for rel, word in HUBS.items():
        t, p = flip_hub(rel, word)
        print(f"  ✓ {rel:28s} tags+={t} pins+={p}")
    align_registries()


if __name__ == "__main__":
    main()
