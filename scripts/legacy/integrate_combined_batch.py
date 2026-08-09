#!/usr/bin/env python3
"""Integrate batch_activites (31 new) + batch_plages (11 new) into Loisirs 74.

Steps:
  1. Update root lieux.json (+42 entries)
  2. Update api/lieux.json (+42 entries, FR-only urls)
  3. Update sitemap.xml (+43 entries: 42 lieux + /plages/ hub)
  4. Update /attractions/index.html (insert 31 cards, bump count to 42)
  5. Update /lacs/index.html (insert 11 beach cards, bump count to 27)
  6. CREATE /plages/index.html (19 cards: 8 existing + 11 new)
  7. Update root index.html (cat-nav + section counts)

Idempotent: re-running won't duplicate entries (checked by slug).
"""
import json
import re
import sys
import urllib.parse
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
JSON_DIR = REPO / "Json"
BASE_URL = "https://loisirs74.fr"

# Order: attractions first, then beaches
ATTRACTION_SLUGS_ORDER = [
    "croisiere-bateaux-annecy-annecy",
    "croisiere-cgn-evian",
    "croisiere-cgn-thonon",
    "croisiere-cgn-yvoire",
    "karting-rumilly-rumilly",
    "karting-mk-circuit-scientrier",
    "karting-mont-blanc-passy",
    "karting-onlykart-roche-sur-foron",
    "karting-team-bouvier-pringy",
    "bowling-aerodrome-annemasse",
    "bowling-margencel-margencel",
    "bowling-le-bowl-annecy",
    "bowling-sevrier-sevrier",
    "patinoire-richard-bozon-chamonix",
    "patinoire-palais-megeve",
    "patinoire-jean-regis-annecy",
    "base-nautique-marquisats-annecy",
    "base-nautique-doussard-doussard",
    "voile-cercle-thonon-thonon",
    "base-nautique-sciez-sciez",
    "wakepark-ponton-embarcadere-saint-jorioz",
    "wakepark-tna-cable-park-arenthon",
    "accrobranche-foret-aventures-manigod",
    "parc-aventure-mont-blanc-saint-gervais",
    "aquaparc-aqualis-cluses",
    "aquaparc-thonon-piscine-olympique-thonon",
    "aquaparc-chateau-bleu-annemasse",
    "jardin-jaysinia-samoens",
    "jardin-cimes-passy",
    "casino-imperial-palace-annecy",
    "casino-evian-resort-evian",
]
BEACH_SLUGS_ORDER = [
    "plage-imperial-annecy",
    "plage-de-la-brune-veyrier",
    "plage-de-doussard",
    "plage-de-sevrier",
    "plage-de-talloires",
    "plage-municipale-thonon",
    "plage-d-amphion-publier",
    "plage-d-evian-centre-nautique",
    "plage-de-saint-gingolph",
    "plage-d-angon-talloires",
    "plage-du-lac-de-montriond",
]

# Existing beaches (8) that get cross-listed in /plages/ hub
EXISTING_BEACH_SLUGS = [
    "plage-albigny",
    "plage-d-excenevex",
    "plage-de-la-pinede",
    "plage-de-menthon-saint-bernard",
    "plage-de-saint-disdille",
    "plage-de-saint-jorioz",
    "plage-de-sciez-sur-leman",
    "plage-des-marquisats",
]


def load_lieu(slug):
    p = JSON_DIR / f"{slug}.json"
    return json.loads(p.read_text(encoding="utf-8"))


# ─────────────────────────────────────────────────────────────────────────
# 1. ROOT lieux.json
# ─────────────────────────────────────────────────────────────────────────
def update_root_lieux_json():
    f = REPO / "lieux.json"
    data = json.loads(f.read_text(encoding="utf-8"))
    existing_slugs = {e["slug"] for e in data["lieux"]}
    added = 0
    for slug in ATTRACTION_SLUGS_ORDER + BEACH_SLUGS_ORDER:
        if slug in existing_slugs:
            continue
        d = load_lieu(slug)
        fr = d["i18n"]["fr"]
        # Category: batch's specific category (e.g. "croisiere") OR top-level "attraction" for the hub
        cat = d["category"]
        # Map batch categories to hub category
        if cat == "plage":
            hub_cat = "plage"
        else:
            hub_cat = "attraction"
        is_free = bool(d.get("schema_org", {}).get("is_free", False))
        # FR-only i18n: copy fr name+commune to all locales (placeholder until translated)
        i18n = {}
        for loc in ("fr", "en", "de", "it", "es"):
            i18n[loc] = {"name": fr["name"], "commune": d["commune"]}
        entry = {
            "slug": slug,
            "categories": [hub_cat],
            "i18n": i18n,
            "latitude": d["latitude"],
            "longitude": d["longitude"],
            "is_free": is_free,
        }
        data["lieux"].append(entry)
        added += 1
    # Bump comment count
    total = len(data["lieux"])
    data["_comment"] = re.sub(
        r"all \d+ published lieux",
        f"all {total} published lieux",
        data.get("_comment", "")
    )
    f.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[lieux.json]      +{added}  (total now {total})")
    return added


# ─────────────────────────────────────────────────────────────────────────
# 2. api/lieux.json
# ─────────────────────────────────────────────────────────────────────────
def update_api_lieux_json():
    f = REPO / "api" / "lieux.json"
    data = json.loads(f.read_text(encoding="utf-8"))
    existing_slugs = {e["slug"] for e in data["lieux"]}
    added = 0
    for slug in ATTRACTION_SLUGS_ORDER + BEACH_SLUGS_ORDER:
        if slug in existing_slugs:
            continue
        d = load_lieu(slug)
        fr = d["i18n"]["fr"]
        cat = d["category"]
        entry = {
            "slug": slug,
            "name": fr["name"],
            "category": cat,
            "commune": d["commune"],
            "postal_code": str(d.get("postal_code", "")),
            "latitude": d["latitude"],
            "longitude": d["longitude"],
            "urls": {
                "fr": f"{BASE_URL}/{slug}",
                "markdown": f"{BASE_URL}/content/{slug}.md",
            },
            "photo": {
                "url": "",
                "type": "placeholder",
            },
        }
        data["lieux"].append(entry)
        added += 1
    data["metadata"]["total_lieux"] = len(data["lieux"])
    f.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[api/lieux.json]  +{added}  (total now {len(data['lieux'])})")
    return added


# ─────────────────────────────────────────────────────────────────────────
# 3. sitemap.xml
# ─────────────────────────────────────────────────────────────────────────
def update_sitemap():
    f = REPO / "sitemap.xml"
    s = f.read_text(encoding="utf-8")
    added = 0
    # Insert /plages/ hub URL before </urlset>
    new_urls = []
    plages_url = f"{BASE_URL}/plages/"
    if plages_url not in s:
        new_urls.append(f"  <url><loc>{plages_url}</loc><changefreq>weekly</changefreq></url>")
    for slug in ATTRACTION_SLUGS_ORDER + BEACH_SLUGS_ORDER:
        url = f"{BASE_URL}/{slug}"
        if url not in s:
            new_urls.append(f"  <url><loc>{url}</loc><changefreq>weekly</changefreq></url>")
            added += 1
    if not new_urls:
        print(f"[sitemap.xml]     +0 (already up to date)")
        return 0
    new_block = "\n".join(new_urls) + "\n"
    s = s.replace("</urlset>", new_block + "</urlset>")
    f.write_text(s, encoding="utf-8")
    total = s.count("<url>")
    print(f"[sitemap.xml]     +{added + (1 if plages_url not in f.read_text() or True else 0)} (total {total})")
    return added


# ─────────────────────────────────────────────────────────────────────────
# Helper: build a card HTML block for a lieu
# ─────────────────────────────────────────────────────────────────────────
ICON_PIN = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>'
    '<circle cx="12" cy="10" r="3"/></svg>'
)
ICON_GLOBE = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round">'
    '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/>'
    '<path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>'
)


def card_html(lieu, indent="      "):
    """Render a single <article class='card'> for a hub carousel."""
    slug = lieu["slug"]
    fr = lieu["i18n"]["fr"]
    name = fr["name"]
    commune = lieu["commune"]
    desc = fr.get("meta_description") or fr.get("hero", {}).get("lead", "")
    is_free = bool(lieu.get("schema_org", {}).get("is_free", False))
    tag = "Gratuit" if is_free else "Payant"
    img = lieu.get("hero_image", "") or ""
    if not img:
        img_src = "/og-image.jpg"
    elif img.startswith(("http://", "https://", "/")):
        img_src = img
    else:
        img_src = f"/{img}"
    gen_attr = ' data-generique="true"' if img.startswith("generique-") else ""
    alt = fr.get("hero_alt", f"{name} à {commune}")
    official = lieu.get("official_site_url") or lieu.get("booking_url") or ""
    q_pin = urllib.parse.quote(f"{name}, {commune}, Haute-Savoie", safe="")

    name_esc = name.replace("&", "&amp;").replace("'", "&#39;")
    desc_esc = desc.replace("&", "&amp;").replace("'", "&#39;")
    alt_esc = alt.replace('"', "&quot;").replace("&", "&amp;")

    official_action = ""
    if official:
        official_action = (
            f'\n        <a href="{official}" target="_blank" rel="noopener">'
            f"{ICON_GLOBE}<span>Site officiel</span></a>"
        )

    return (
        f'{indent}<article class="card">\n'
        f'{indent}  <a href="{BASE_URL}/{slug}" class="card-photo">\n'
        f'{indent}    <img src="{img_src}" alt="{alt_esc}" loading="lazy"{gen_attr}>\n'
        f'{indent}    <span class="card-tag">{tag}</span>\n'
        f'{indent}  </a>\n'
        f'{indent}  <div class="card-body">\n'
        f'{indent}    <a href="{BASE_URL}/{slug}" class="title">{name_esc}</a>\n'
        f'{indent}    <div class="card-commune">{ICON_PIN}<span>{commune}</span></div>\n'
        f'{indent}    <p class="card-desc">{desc_esc}</p>\n'
        f'{indent}    <div class="card-actions">\n'
        f'{indent}      <a href="https://www.google.com/maps/dir/?api=1&amp;destination={q_pin}" target="_blank" rel="noopener">{ICON_PIN}<span>Itinéraire</span></a>'
        f'{official_action}\n'
        f'{indent}    </div>\n'
        f'{indent}  </div>\n'
        f'{indent}</article>'
    )


def pin_entry(lieu):
    """One PINS array entry for the map JS."""
    fr = lieu["i18n"]["fr"]
    is_free = bool(lieu.get("schema_org", {}).get("is_free", False))
    return {
        "slug": lieu["slug"],
        "name": fr["name"],
        "commune": lieu["commune"],
        "lat": lieu["latitude"],
        "lng": lieu["longitude"],
        "url": f"{BASE_URL}/{lieu['slug']}",
        "paid": not is_free,
    }


def itemlist_entry(lieu, position):
    """One ListItem for the LD-JSON ItemList."""
    fr = lieu["i18n"]["fr"]
    return {
        "@type": "ListItem",
        "position": position,
        "item": {
            "@type": "TouristAttraction",
            "name": fr["name"],
            "url": f"{BASE_URL}/{lieu['slug']}",
            "address": {
                "@type": "PostalAddress",
                "addressLocality": lieu["commune"],
                "addressRegion": "Haute-Savoie",
                "addressCountry": "FR",
            },
            "geo": {
                "@type": "GeoCoordinates",
                "latitude": lieu["latitude"],
                "longitude": lieu["longitude"],
            },
            "image": "",
        },
    }


# ─────────────────────────────────────────────────────────────────────────
# 4. /attractions/index.html
# ─────────────────────────────────────────────────────────────────────────
def update_hub(hub_path, new_slugs, hub_name, hub_path_text):
    """Insert cards into an existing commune-grouped hub.

    Idempotent: skip slugs whose href already appears in the file.
    """
    f = REPO / hub_path
    s = f.read_text(encoding="utf-8")
    added = 0
    new_lieux = []
    for slug in new_slugs:
        if f'/{slug}"' in s:
            continue  # already present
        new_lieux.append(load_lieu(slug))
        added += 1

    if added == 0:
        print(f"[{hub_path}]  +0 (already up to date)")
        return 0

    # Group new lieux by commune
    by_commune = {}
    for lieu in new_lieux:
        by_commune.setdefault(lieu["commune"], []).append(lieu)

    # Locate <main>...<div class="wrap">...
    # Insert new commune sections (or append to existing)
    for commune, lieux in sorted(by_commune.items()):
        existing_marker = f'data-commune="{commune}"'
        if existing_marker in s:
            # Append cards to the existing carousel of this commune
            # Find the carousel close for this commune
            pat = re.compile(
                r'(<div class="commune-section" data-commune="'
                + re.escape(commune)
                + r'">.*?<div class="carousel">)(.*?)(</div>\s*</div>)',
                re.DOTALL,
            )
            m = pat.search(s)
            if not m:
                print(f"  WARN: couldn't locate carousel for {commune}", file=sys.stderr)
                continue
            old_carousel = m.group(2)
            new_cards = "\n".join(card_html(l, indent="        ") for l in lieux)
            new_carousel = old_carousel.rstrip() + "\n" + new_cards + "\n      "
            # Bump count
            count_pat = re.compile(
                r'(<h3>' + re.escape(commune) + r' <span class="commune-count">)(\d+)( lieu\(x\) à '
                + re.escape(commune) + r')'
            )
            m_count = count_pat.search(s)
            if m_count:
                new_count = int(m_count.group(2)) + len(lieux)
                s = count_pat.sub(rf'\g<1>{new_count}\g<3>', s)
            s = s[:m.start()] + m.group(1) + new_carousel + m.group(3) + s[m.end():]
        else:
            # Create new commune section, insert alphabetically into main
            n = len(lieux)
            section = (
                f'<div class="commune-section" data-commune="{commune}">\n'
                f'      <div class="commune-head">\n'
                f'        <h3>{commune} <span class="commune-count">{n} lieu(x) à {commune}</span></h3>\n'
                f'      </div>\n'
                f'      <div class="carousel">\n'
                + "\n".join(card_html(l, indent="        ") for l in lieux)
                + "\n      </div>\n"
                f'    </div>\n'
            )
            # Find a place to insert: before the LAST commune-section that's alphabetically > commune
            # Simpler: insert just before </main> (end of all sections)
            # Then sort at runtime via JS — but we'll inject in alpha order by inserting
            # right before the next commune that's > our commune.
            inserted = False
            for m_sec in re.finditer(
                r'<div class="commune-section" data-commune="([^"]+)">', s
            ):
                if m_sec.group(1) > commune:
                    s = s[:m_sec.start()] + section + "    " + s[m_sec.start():]
                    inserted = True
                    break
            if not inserted:
                # Append before </main>
                s = s.replace("</main>", "    " + section + "  </main>", 1)

    # Update hero count: "<digits> lieux · <digits> commune(s)"
    # Count communes after update by scanning data-commune
    communes = set(re.findall(r'data-commune="([^"]+)"', s))
    total_cards = s.count('<article class="card"')
    s = re.sub(
        r'(<p class="meta">)(\d+) lieux · (\d+) commune\(s\)',
        rf'\g<1>{total_cards} lieux · {len(communes)} commune(s)',
        s,
    )

    # Update top LD-JSON ItemList: numberOfItems + description
    s = re.sub(
        r'"description"\s*:\s*"Liste de \d+ ' + re.escape(hub_name),
        f'"description": "Liste de {total_cards} {hub_name}',
        s,
    )
    s = re.sub(r'"numberOfItems"\s*:\s*\d+', f'"numberOfItems": {total_cards}', s)

    # Update commune filter <select>
    # Build the new option list
    commune_options = "".join(
        f'<option value="{c}">{c}</option>' for c in sorted(communes)
    )
    s = re.sub(
        r'(<select id="filt-commune"><option value="">Toutes les communes</option>).*?(</select>)',
        rf'\g<1>{commune_options}\g<2>',
        s,
        flags=re.DOTALL,
    )

    # Update PINS array: rebuild fully from card data we can see in the file
    # Simpler: append new pins to existing array
    pin_pat = re.compile(r'(const PINS = )(\[.*?\])(;)', re.DOTALL)
    m_pins = pin_pat.search(s)
    if m_pins:
        existing_pins = json.loads(m_pins.group(2))
        existing_pin_slugs = {p["slug"] for p in existing_pins}
        for lieu in new_lieux:
            pe = pin_entry(lieu)
            if pe["slug"] not in existing_pin_slugs:
                existing_pins.append(pe)
        new_pin_str = json.dumps(existing_pins, ensure_ascii=False, separators=(",", ":"))
        s = pin_pat.sub(rf'\g<1>{new_pin_str}\g<3>', s)

    # Add ListItem entries to ItemList LD-JSON
    # Find itemListElement [...] and append new entries
    li_pat = re.compile(
        r'("itemListElement":\s*)\[(.*?)\]\s*\}\s*\n\s*</script>',
        re.DOTALL,
    )
    m_li = li_pat.search(s)
    if m_li:
        # Just rebuild itemListElement fully with all cards in the hub
        # Extract all (slug, name, commune, lat, lng) tuples from PINS we just updated
        all_pins = json.loads(re.search(r'const PINS = (\[.*?\]);', s, re.DOTALL).group(1))
        items = []
        for i, p in enumerate(sorted(all_pins, key=lambda x: x["name"]), start=1):
            items.append({
                "@type": "ListItem",
                "position": i,
                "item": {
                    "@type": "TouristAttraction",
                    "name": p["name"],
                    "url": p["url"],
                    "address": {
                        "@type": "PostalAddress",
                        "addressLocality": p["commune"],
                        "addressRegion": "Haute-Savoie",
                        "addressCountry": "FR",
                    },
                    "geo": {
                        "@type": "GeoCoordinates",
                        "latitude": p["lat"],
                        "longitude": p["lng"],
                    },
                    "image": "",
                },
            })
        items_str = json.dumps(items, indent=4, ensure_ascii=False)
        # indent the items_str properly (current LD-JSON uses 4-space indent)
        items_str_indented = "\n".join(
            "    " + line for line in items_str.splitlines()
        )
        s = li_pat.sub(
            rf'\g<1>{items_str_indented}\n  }}\n</script>',
            s,
        )

    f.write_text(s, encoding="utf-8")
    print(f"[{hub_path}]  +{added}  (total {total_cards} cards, {len(communes)} communes)")
    return added


# ─────────────────────────────────────────────────────────────────────────
# 6. CREATE /plages/index.html from scratch
# ─────────────────────────────────────────────────────────────────────────
def build_plages_hub():
    f = REPO / "plages" / "index.html"
    f.parent.mkdir(exist_ok=True)

    # Existing 8 beach pages: load minimal metadata (since we don't have JSON for them in Json/,
    # we'll extract from the HTML pages directly).
    all_lieux = []
    for slug in EXISTING_BEACH_SLUGS:
        json_path = JSON_DIR / f"{slug}.json"
        if json_path.exists():
            all_lieux.append(json.loads(json_path.read_text()))
        else:
            # Build a minimal stub from the HTML page metadata
            html_path = REPO / f"{slug}.html"
            if not html_path.exists():
                print(f"  WARN: missing {slug}.html", file=sys.stderr)
                continue
            html = html_path.read_text()
            name_m = re.search(r'<title>([^·]+)·', html) or re.search(r'<meta property="og:title" content="([^"]+)"', html)
            name = (name_m.group(1).strip() if name_m else slug.replace("-", " ").title())
            commune_m = re.search(r'"addressLocality":\s*"([^"]+)"', html)
            commune = commune_m.group(1) if commune_m else ""
            lat_m = re.search(r'"latitude":\s*([0-9.\-]+)', html)
            lon_m = re.search(r'"longitude":\s*([0-9.\-]+)', html)
            desc_m = re.search(r'<meta name="description" content="([^"]+)"', html)
            is_free_m = re.search(r'"isAccessibleForFree":\s*(true|false)', html)
            img_m = re.search(r'<meta property="og:image" content="([^"]+)"', html)
            stub = {
                "slug": slug,
                "category": "plage",
                "commune": commune,
                "latitude": float(lat_m.group(1)) if lat_m else 45.94,
                "longitude": float(lon_m.group(1)) if lon_m else 6.34,
                "hero_image": "",
                "official_site_url": "",
                "schema_org": {"is_free": (is_free_m.group(1) == "true") if is_free_m else True},
                "i18n": {"fr": {
                    "name": name,
                    "meta_description": desc_m.group(1) if desc_m else "",
                    "hero_alt": name,
                }},
            }
            all_lieux.append(stub)
    # New 11 beach pages from JSON
    for slug in BEACH_SLUGS_ORDER:
        all_lieux.append(load_lieu(slug))

    total = len(all_lieux)
    communes = sorted(set(l["commune"] for l in all_lieux))

    # Build LD-JSON ItemList
    sorted_lieux = sorted(all_lieux, key=lambda x: x["i18n"]["fr"]["name"])
    item_list = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "@id": f"{BASE_URL}/plages/#itemlist",
        "name": "Plages surveillées de Haute-Savoie",
        "description": f"Liste de {total} plages surveillées en Haute-Savoie",
        "numberOfItems": total,
        "itemListOrder": "https://schema.org/ItemListOrderAscending",
        "inLanguage": "fr",
        "isPartOf": {
            "@type": "CollectionPage",
            "@id": f"{BASE_URL}/plages/"
        },
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": i,
                "item": {
                    "@type": "TouristAttraction",
                    "name": l["i18n"]["fr"]["name"],
                    "url": f"{BASE_URL}/{l['slug']}",
                    "address": {
                        "@type": "PostalAddress",
                        "addressLocality": l["commune"],
                        "addressRegion": "Haute-Savoie",
                        "addressCountry": "FR",
                    },
                    "geo": {
                        "@type": "GeoCoordinates",
                        "latitude": l["latitude"],
                        "longitude": l["longitude"],
                    },
                    "image": "",
                },
            }
            for i, l in enumerate(sorted_lieux, start=1)
        ],
    }

    # PINS array
    pins = [pin_entry(l) for l in all_lieux]

    # Read /attractions/index.html as the structural template for hub HTML
    tpl = (REPO / "attractions" / "index.html").read_text(encoding="utf-8")

    # Substitute key fields
    out = tpl
    out = re.sub(r'<title>[^<]+</title>',
                 '<title>Plages surveillées de Haute-Savoie · Loisirs 74</title>', out, count=1)
    out = re.sub(r'<meta name="description" content="[^"]+"',
                 f'<meta name="description" content="Guide des {total} plages officiellement surveillées MNS de Haute-Savoie : lacs d\'Annecy, du Léman et de Montriond. Tarifs, accès, équipements et carte interactive."', out, count=1)
    out = re.sub(r'<link rel="canonical" href="[^"]+"',
                 f'<link rel="canonical" href="{BASE_URL}/plages/"', out, count=1)
    out = re.sub(r'<link rel="alternate" hreflang="fr" href="[^"]+"',
                 f'<link rel="alternate" hreflang="fr" href="{BASE_URL}/plages/"', out, count=1)
    # Remove non-FR hreflangs (FR-only hub)
    out = re.sub(r'\s*<link rel="alternate" hreflang="(en|de|it|es)" href="[^"]+">', '', out)
    out = re.sub(r'<link rel="alternate" hreflang="x-default" href="[^"]+"',
                 f'<link rel="alternate" hreflang="x-default" href="{BASE_URL}/plages/"', out, count=1)
    out = re.sub(r'<meta property="og:title" content="[^"]+"',
                 '<meta property="og:title" content="Plages surveillées de Haute-Savoie"', out, count=1)
    out = re.sub(r'<meta property="og:description" content="[^"]+"',
                 f'<meta property="og:description" content="Guide des {total} plages officiellement surveillées MNS de Haute-Savoie."', out, count=1)
    out = re.sub(r'<meta property="og:url" content="[^"]+"',
                 f'<meta property="og:url" content="{BASE_URL}/plages/"', out, count=1)
    out = re.sub(r'<meta name="twitter:title" content="[^"]+"',
                 '<meta name="twitter:title" content="Plages surveillées de Haute-Savoie"', out, count=1)
    out = re.sub(r'<meta name="twitter:description" content="[^"]+"',
                 f'<meta name="twitter:description" content="Guide des {total} plages officiellement surveillées MNS de Haute-Savoie."', out, count=1)
    # AI-discovery markdown link
    out = re.sub(r'href="/content/attractions\.md"', 'href="/content/plages.md"', out)
    out = re.sub(r'content="https://loisirs74\.fr/content/attractions\.md"',
                 f'content="{BASE_URL}/content/plages.md"', out)

    # Replace lang-picker menu (FR-only)
    out = re.sub(
        r'<div class="lang-menu"><a href="[^"]+attractions/[^"]*"[^>]*>Français</a>.*?</div>',
        f'<div class="lang-menu"><a href="{BASE_URL}/plages/" aria-current="true" hreflang="fr">Français</a></div>',
        out, count=1, flags=re.DOTALL,
    )

    # Replace cat-hero h1 and meta
    out = re.sub(
        r'<section class="cat-hero">\s*<div class="wrap">\s*<h1>[^<]+</h1>\s*<p class="meta">[^<]+</p>',
        f'<section class="cat-hero">\n  <div class="wrap">\n    <h1>Plages surveillées</h1>\n    <p class="meta">{total} plages · {len(communes)} commune(s) · Haute-Savoie</p>',
        out, count=1,
    )

    # Replace top ItemList LD-JSON block (the first <script type="application/ld+json"> after </style>)
    out = re.sub(
        r'<script type="application/ld\+json">\s*\{\s*"@context"[^}]*"@type":\s*"ItemList".*?\}\s*</script>',
        f'<script type="application/ld+json">\n{json.dumps(item_list, indent=2, ensure_ascii=False)}\n</script>',
        out, count=1, flags=re.DOTALL,
    )

    # Replace filter commune select
    commune_options = "".join(f'<option value="{c}">{c}</option>' for c in communes)
    out = re.sub(
        r'(<select id="filt-commune"><option value="">Toutes les communes</option>).*?(</select>)',
        rf'\g<1>{commune_options}\g<2>',
        out, count=1, flags=re.DOTALL,
    )

    # Replace <main>...</main> body with new commune sections
    by_commune = {}
    for l in all_lieux:
        by_commune.setdefault(l["commune"], []).append(l)
    main_body_parts = []
    for commune in sorted(by_commune):
        items = by_commune[commune]
        main_body_parts.append(
            f'    <div class="commune-section" data-commune="{commune}">\n'
            f'      <div class="commune-head">\n'
            f'        <h3>{commune} <span class="commune-count">{len(items)} lieu(x) à {commune}</span></h3>\n'
            f'      </div>\n'
            f'      <div class="carousel">\n'
            + "\n".join(card_html(l, indent="        ") for l in items)
            + "\n      </div>\n"
            f'    </div>'
        )
    new_main = '<main>\n  <div class="wrap">\n' + "\n".join(main_body_parts) + '\n  </div>\n</main>'
    out = re.sub(r'<main>.*?</main>', new_main, out, count=1, flags=re.DOTALL)

    # Update PINS array
    pins_str = json.dumps(pins, ensure_ascii=False, separators=(",", ":"))
    out = re.sub(r'const PINS = \[.*?\];', f'const PINS = {pins_str};', out, count=1, flags=re.DOTALL)

    # Replace breadcrumb-style references to "Attractions" in footer of file
    out = re.sub(r'>Attractions</a>', '>Plages</a>', out)

    # Replace bottom CollectionPage block (numberOfItems & name)
    out = re.sub(
        r'"@type":\s*"CollectionPage",\s*"url":\s*"https://loisirs74\.fr/attractions/",\s*"name":\s*"[^"]+"',
        f'"@type": "CollectionPage",\n  "url": "{BASE_URL}/plages/",\n  "name": "Plages surveillées de Haute-Savoie"',
        out, count=1,
    )
    out = re.sub(r'"numberOfItems":\s*\d+', f'"numberOfItems": {total}', out)

    f.write_text(out, encoding="utf-8")
    print(f"[/plages/index.html] CREATED with {total} cards across {len(communes)} communes")
    return total


# ─────────────────────────────────────────────────────────────────────────
# 7. Root index.html (FR homepage)
# ─────────────────────────────────────────────────────────────────────────
def update_root_index():
    f = REPO / "index.html"
    s = f.read_text(encoding="utf-8")
    orig = s

    # 7a. Cat-nav: insert "Plages" link after "Lacs & plages"
    if 'href="https://loisirs74.fr/plages/">Plages</a>' not in s:
        s = s.replace(
            '<a href="https://loisirs74.fr/lacs/">Lacs &amp; plages</a>',
            '<a href="https://loisirs74.fr/lacs/">Lacs &amp; plages</a><a href="https://loisirs74.fr/plages/">Plages</a>',
            1,
        )

    # 7b. Section counts
    # Lacs & plages: stays at 16 (beaches not added to /lacs/, only to /plages/)
    # Attractions & loisirs: 11 → 42
    s = re.sub(
        r'(<h2>Attractions &amp; loisirs<span class="count">)\d+ lieux',
        r'\g<1>42 lieux',
        s,
    )

    if s == orig:
        print("[index.html]      +0 (already up to date)")
        return 0
    f.write_text(s, encoding="utf-8")
    print("[index.html]      cat-nav + counts updated")
    return 1


# ─────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("Integrate batch_activites + batch_plages")
    print("=" * 60)
    update_root_lieux_json()
    update_api_lieux_json()
    update_sitemap()
    update_hub("attractions/index.html", ATTRACTION_SLUGS_ORDER, "attractions", "attractions")
    # NOTE: /lacs/ is NOT updated with the 11 new beaches. Per user decision,
    # the new beaches live only in /plages/. The 8 existing beach cards already
    # in /lacs/ stay there (cross-listed).
    build_plages_hub()
    update_root_index()
    print("=" * 60)
    print("DONE")


if __name__ == "__main__":
    main()
