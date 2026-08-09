#!/usr/bin/env python3
"""One-shot splice: insert Phase 1 venues into attractions/musees/bases-de-loisirs hubs.

Matches current live hub markup byte-by-byte. Updates 5 sync points per hub:
1. Per-commune <span class="commune-count">N lieux</span>
2. Hero <p class="meta"><b>N lieux</b>...<span>M communes</span></p>
3. <select id="filt-commune"> options (alpha)
4. Upper JSON-LD "numberOfItems" + "description" + "itemListElement" (rebuilt)
5. Lower JSON-LD "numberOfItems"
6. const PINS = [...] JS array
"""
import json, re, sys, urllib.parse
from pathlib import Path

REPO = Path("/home/user/Loisir-74")
BASE = "https://loisirs74.fr"

GENERIC_ON_DISK = {"attraction", "cascade", "chateau", "domaine", "lac", "musee",
                   "parc", "point-de-vue", "sentier", "telecabine", "voie-verte"}

# Map venue category → target hub
HUB_FOR = {
    "attraction": "attractions",
    "musee": "musees",
    "domaine": "bases-de-loisirs",
    "parc": "attractions",
}

# Phase 1 slugs to splice
PHASE1_SLUGS = sorted([p.stem for p in (Path("/tmp/tier1-indoor/Json").glob("*.json"))]
                      + [p.stem for p in (Path("/tmp/tier1-indoor-pass2/Json").glob("*.json"))])


def load(slug):
    return json.loads((REPO / "Json" / f"{slug}.json").read_text(encoding="utf-8"))


def esc_attr(s):
    return str(s).replace("&", "&amp;").replace('"', "&quot;")

def esc_text(s):
    return str(s).replace("&", "&amp;").replace("'", "&#x27;")


def card_html(d):
    """Render one card matching current live hub markup byte-by-byte."""
    slug = d["slug"]
    fr = d["i18n"]["fr"]
    name = fr["name"]
    commune = d["commune"]
    desc = fr.get("meta_description") or fr.get("hero", {}).get("lead", "")
    is_free = bool(d.get("schema_org", {}).get("is_free", False))
    tag_text = "Gratuit" if is_free else "Payant"
    tag_class = "is-gratuit" if is_free else "is-payant"
    # image
    img = d.get("hero_image") or ""
    if img.startswith("generique-"):
        img_src = f"/{img}"
        cat = img[len("generique-"):].rsplit(".", 1)[0]
        extra = f' data-generique="true" data-generique-cat="{cat}"'
    elif img:
        img_src = f"/{img}"
        extra = ""
    else:
        cat = d.get("category") or "attraction"
        eff = cat if cat in GENERIC_ON_DISK else "attraction"
        img_src = f"/generique-{eff}.jpg"
        extra = f' data-generique="true" data-generique-cat="{eff}"'
    alt = fr.get("hero_alt") or f"{name} — {commune}, Haute-Savoie"
    q = urllib.parse.quote(f"{name}, {commune}, Haute-Savoie", safe="")
    maps_href = f"https://www.google.com/maps/dir/?api=1&amp;destination={q}"
    official = d.get("official_site_url") or ""
    official_line = ""
    if official:
        official_line = f'\n<a href="{esc_attr(official)}" rel="noopener" target="_blank">Site officiel</a>'
    return (
        '<article class="card">\n'
        f'<a class="card-photo" href="{BASE}/{slug}">\n'
        f'<img alt="{esc_attr(alt)}"{extra} loading="lazy" src="{img_src}"/>\n'
        f'<span class="card-tag {tag_class}">{tag_text}</span>\n'
        '</a>\n'
        '<div class="card-body">\n'
        f'<div class="card-commune"><span>{esc_text(commune)}</span></div><a class="title" href="{BASE}/{slug}">{esc_text(name)}</a>\n'
        '\n'
        f'<p class="card-desc">{esc_text(desc)}</p>\n'
        '<div class="card-actions">\n'
        f'<a href="{maps_href}" rel="noopener" target="_blank">Itinéraire</a>{official_line}\n'
        '</div>\n'
        '</div>\n'
        '</article>'
    )


def commune_section(commune, cards):
    """Build a new commune-section block (no transport-block — optional)."""
    return (
        f'<div class="commune-section" data-commune="{esc_attr(commune)}">\n'
        f'<div class="commune-head"><h3>{esc_text(commune)}</h3><span class="commune-count">{len(cards)} {"lieu" if len(cards)==1 else "lieux"}</span></div>\n'
        '<div class="carousel">\n'
        + '\n'.join(cards)
        + '\n'
        '</div>\n'
        '</div>'
    )


def pin_entry(d):
    fr = d["i18n"]["fr"]
    is_free = bool(d.get("schema_org", {}).get("is_free", False))
    return {
        "slug": d["slug"],
        "name": fr["name"],
        "commune": d["commune"],
        "lat": d.get("latitude") or 0,
        "lng": d.get("longitude") or 0,
        "url": f"{BASE}/{d['slug']}",
        "paid": not is_free,
    }


def update_hub(hub_dir, new_venues, hub_name, hub_label):
    """Splice new_venues (list of loaded JSON dicts) into hub_dir/index.html."""
    f = REPO / hub_dir / "index.html"
    s = f.read_text(encoding="utf-8")
    # Idempotency: skip venues whose slug href already in file
    venues_to_add = [d for d in new_venues if f'/{d["slug"]}"' not in s]
    if not venues_to_add:
        print(f"  [{hub_dir}/] +0 (idempotent)")
        return 0
    by_commune = {}
    for d in venues_to_add:
        by_commune.setdefault(d["commune"], []).append(d)

    for commune in sorted(by_commune):
        venues = sorted(by_commune[commune], key=lambda d: d["i18n"]["fr"]["name"])
        new_cards = [card_html(d) for d in venues]
        marker = f'<div class="commune-section" data-commune="{commune}">'
        if marker in s:
            # Append: bound section by start + (next commune-section | </main>), insert before carousel close
            m_start = re.search(re.escape(marker), s)
            m_next = re.search(r'<div class="commune-section"|</main>', s[m_start.end():])
            sec_end_abs = m_start.end() + m_next.start() if m_next else len(s)
            section_text = s[m_start.start():sec_end_abs]
            # Find trailing </article>\s*</div>\s*</div> (carousel close + section close)
            end_match = re.search(r'</article>\s*</div>\s*</div>\s*\Z', section_text, re.DOTALL)
            if not end_match:
                print(f"  WARN: carousel close not located for {commune} in {hub_dir}", file=sys.stderr)
                continue
            insert_pos = end_match.start() + len('</article>')
            new_section_text = section_text[:insert_pos] + '\n' + '\n'.join(new_cards) + section_text[insert_pos:]
            s = s[:m_start.start()] + new_section_text + s[sec_end_abs:]
            # Bump per-commune count
            count_pat = re.compile(
                r'(<div class="commune-head"><h3>' + re.escape(commune) + r'</h3><span class="commune-count">)(\d+)( lieux?</span>)'
            )
            m2 = count_pat.search(s)
            if m2:
                new_n = int(m2.group(2)) + len(venues)
                lbl = "lieu" if new_n == 1 else "lieux"
                s = count_pat.sub(rf'\g<1>{new_n} {lbl}</span>', s, count=1)
        else:
            # Insert new commune section alpha-ordered
            new_section = commune_section(commune, new_cards)
            inserted = False
            for m_sec in re.finditer(r'<div class="commune-section" data-commune="([^"]+)">', s):
                if m_sec.group(1) > commune:
                    s = s[:m_sec.start()] + new_section + '\n' + s[m_sec.start():]
                    inserted = True
                    break
            if not inserted:
                # Append before </main>
                s = s.replace("</main>", new_section + "\n</main>", 1)

    # Recompute hub-wide stats
    communes_all = sorted(set(re.findall(r'data-commune="([^"]+)"', s)))
    total_cards = s.count('<article class="card"')
    # Hero meta: <p class="meta"><b>N lieux</b><span class="dot">·</span><span>M communes</span></p>
    s = re.sub(
        r'<p class="meta"><b>\d+ lieux?</b><span class="dot">·</span><span>\d+ communes?</span></p>',
        f'<p class="meta"><b>{total_cards} {"lieu" if total_cards==1 else "lieux"}</b><span class="dot">·</span><span>{len(communes_all)} {"commune" if len(communes_all)==1 else "communes"}</span></p>',
        s,
    )
    # Filter <select>
    opts = ''.join(f'<option value="{esc_attr(c)}">{esc_text(c)}</option>' for c in communes_all)
    s = re.sub(
        r'(<select id="filt-commune"><option value="">Toutes les communes</option>).*?(</select>)',
        rf'\g<1>{opts}\g<2>',
        s,
        flags=re.DOTALL,
    )
    # Upper JSON-LD: description + numberOfItems + itemListElement
    s = re.sub(
        rf'"description":\s*"Liste de \d+ {hub_label}',
        f'"description": "Liste de {total_cards} {hub_label}',
        s,
    )
    s = re.sub(r'"numberOfItems":\s*\d+', f'"numberOfItems": {total_cards}', s)
    # Rebuild PINS from existing + new
    pin_pat = re.compile(r'(const PINS = )(\[.*?\])(;)', re.DOTALL)
    m_pins = pin_pat.search(s)
    if m_pins:
        existing = json.loads(m_pins.group(2))
        ex_slugs = {p["slug"] for p in existing}
        for d in venues_to_add:
            pe = pin_entry(d)
            if pe["slug"] not in ex_slugs:
                existing.append(pe)
        new_str = json.dumps(existing, ensure_ascii=False, separators=(", ", ": "))
        s = pin_pat.sub(rf'\g<1>{new_str}\g<3>', s)
    # Rebuild itemListElement from PINS (alpha by name)
    pin_pat2 = re.compile(r'const PINS = (\[.*?\]);', re.DOTALL)
    all_pins = json.loads(pin_pat2.search(s).group(1))
    items = []
    for i, p in enumerate(sorted(all_pins, key=lambda x: x["name"]), start=1):
        items.append({
            "@type": "ListItem",
            "position": i,
            "item": {
                "@type": "TouristAttraction",
                "name": p["name"],
                "url": p["url"],
                "address": {"@type": "PostalAddress", "addressLocality": p["commune"],
                            "addressRegion": "Haute-Savoie", "addressCountry": "FR"},
                "geo": {"@type": "GeoCoordinates", "latitude": p.get("lat", 0),
                        "longitude": p.get("lng", 0)},
                "image": "",
            },
        })
    items_str = json.dumps(items, indent=4, ensure_ascii=False)
    items_indented = "\n".join("    " + line for line in items_str.splitlines())
    li_pat = re.compile(
        r'("itemListElement":\s*)\[.*?\]\s*\}\s*</script>',
        re.DOTALL,
    )
    s = li_pat.sub(rf'\g<1>{items_indented}\n  }}</script>', s)

    f.write_text(s, encoding="utf-8")
    print(f"  [{hub_dir}/] +{len(venues_to_add)} cards → {total_cards} total / {len(communes_all)} communes")
    return len(venues_to_add)


def main():
    # Group Phase 1 venues by target hub
    by_hub = {"attractions": [], "musees": [], "bases-de-loisirs": []}
    skipped = []
    for slug in PHASE1_SLUGS:
        d = load(slug)
        cat = d["category"]
        if cat in HUB_FOR:
            by_hub[HUB_FOR[cat]].append(d)
        else:
            skipped.append((slug, cat, d["commune"]))
    print(f"= Splicing {sum(len(v) for v in by_hub.values())} / {len(PHASE1_SLUGS)} venues; "
          f"{len(skipped)} skipped (no hub: aquaparc/divers/patinoire/karting/bowling)")
    print()
    update_hub("attractions",      by_hub["attractions"],      "attractions", "attractions")
    update_hub("musees",           by_hub["musees"],           "musees",      "musées")
    update_hub("bases-de-loisirs", by_hub["bases-de-loisirs"], "bases-de-loisirs", "bases de loisirs")
    if skipped:
        print(f"\n= Skipped (standalone, no hub):")
        for slug, cat, commune in skipped:
            print(f"  {slug:<55} | {cat:<10} | {commune}")


if __name__ == "__main__":
    main()
