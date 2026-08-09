#!/usr/bin/env python3
"""
Integrate the 4 new beaches (Duingt, Tougues, Messery, Margencel) into the
/plages/ and /lacs/ hubs across all 5 languages: insert lake-section cards,
map PINs, refresh section counts, commune-filter options, cat-hero totals,
and the ItemList JSON-LD.
"""
import json
import re
from urllib.parse import quote
from bs4 import BeautifulSoup
from pathlib import Path

ROOT = Path("/home/user/Loisir-74")
LANGS = ["fr", "en", "de", "it", "es"]

PLAGES_HUB = {"fr": "plages/index.html", "en": "en/beaches/index.html", "de": "de/straende/index.html",
              "it": "it/spiagge/index.html", "es": "es/playas/index.html"}
LACS_HUB = {"fr": "lacs/index.html", "en": "en/lakes/index.html", "de": "de/seen/index.html",
            "it": "it/laghi/index.html", "es": "es/lagos/index.html"}

FREEWORD = {"fr": "Gratuit", "en": "Free", "de": "Kostenlos", "it": "Gratuito", "es": "Gratis"}
DIRECTIONS = {"fr": "Itinéraire", "en": "Directions", "de": "Wegbeschreibung", "it": "Itinerario", "es": "Cómo llegar"}
OFFICIAL = {"fr": "Site officiel", "en": "Official site", "de": "Offizielle Website", "it": "Sito ufficiale", "es": "Sitio oficial"}
SEC_NOUN = {
    "plages": {"fr": "plages", "en": "beaches", "de": "Strände", "it": "spiagge", "es": "playas"},
    "lacs": {"fr": "lieux", "en": "places", "de": "Orte", "it": "luoghi", "es": "lugares"},
}

PLAGES = [
    {
        "slug": "plage-de-duingt", "lake": "annecy", "commune": "Duingt",
        "name": "Plage de Duingt", "hero": "plage-de-duingt-hero.jpg",
        "official": "https://duingt.fr/mairie-de-duingt/decouvrir-duingt/les-activites-a-duingt-et-aux-alentours/plage-municipale/",
        "lat": 45.827, "lng": 6.203,
        "alt": {
            "fr": "Plage gazonnée 120 m - face au château de Duingt Plage de Duingt à Duingt Lac d'Annecy Haute-Savoie 74",
            "en": "Grassy beach 120 m facing the Château de Duingt, Plage de Duingt in Duingt, Lac d'Annecy, Haute-Savoie 74",
            "de": "Liegewiese 120 m gegenüber dem Château de Duingt, Plage de Duingt in Duingt, Lac d'Annecy, Haute-Savoie 74",
            "it": "Spiaggia erbosa 120 m di fronte allo Château de Duingt, Plage de Duingt a Duingt, Lac d'Annecy, Alta Savoia 74",
            "es": "Playa de césped 120 m frente al Château de Duingt, Plage de Duingt en Duingt, Lac d'Annecy, Alta Saboya 74",
        },
        "desc": {
            "fr": "PLAGE GAZONNÉE FACE AU CHÂTEAU DE DUINGT (Ruphy) sur la rive ouest du Lac d'Annecy. Surveillée MNS juillet-août, club nautique et guinguette.",
            "en": "GRASSY BEACH FACING THE CHÂTEAU DE DUINGT (Ruphy) on the west shore of Lake Annecy. Lifeguarded in July–August, sailing club and guinguette.",
            "de": "LIEGEWIESE GEGENÜBER DEM CHÂTEAU DE DUINGT (Ruphy) am Westufer des Lac d'Annecy. Badeaufsicht im Juli–August, Segelclub und Guinguette.",
            "it": "SPIAGGIA ERBOSA DI FRONTE ALLO CHÂTEAU DE DUINGT (Ruphy) sulla riva ovest del Lago di Annecy. Sorvegliata luglio–agosto, circolo nautico e chiosco.",
            "es": "PLAYA DE CÉSPED FRENTE AL CHÂTEAU DE DUINGT (Ruphy) en la orilla oeste del Lago de Annecy. Vigilada en julio–agosto, club náutico y merendero.",
        },
    },
    {
        "slug": "plage-de-tougues-chens", "lake": "leman", "commune": "Chens-sur-Léman",
        "name": "Plage de Tougues", "hero": "plage-de-tougues-chens-hero.jpg",
        "official": "https://chenssurleman.fr/", "lat": 46.323, "lng": 6.26,
        "alt": {
            "fr": "Plage pelouse + galets ombragée - zone barbecue Plage de Tougues à Chens-sur-Léman Lac Léman Haute-Savoie 74",
            "en": "Shaded lawn and pebble beach with barbecue area, Plage de Tougues at Chens-sur-Léman, Lake Geneva, Haute-Savoie 74",
            "de": "Schattige Liegewiese mit Kiesstrand und Grillplatz, Plage de Tougues in Chens-sur-Léman, Genfersee, Haute-Savoie 74",
            "it": "Spiaggia erbosa e di ghiaia ombreggiata con area barbecue, Plage de Tougues a Chens-sur-Léman, Lago di Ginevra, Alta Savoia 74",
            "es": "Playa de césped y guijarros sombreada con zona de barbacoa, Plage de Tougues en Chens-sur-Léman, Lago Lemán, Alta Saboya 74",
        },
        "desc": {
            "fr": "PLAGE OMBRAGÉE PELOUSE + GALETS sur le Léman à Chens-sur-Léman, près de la frontière genevoise. Arbres centenaires, zone barbecue, aires de jeux.",
            "en": "SHADED LAWN + PEBBLE BEACH on Lake Geneva at Chens-sur-Léman, near the Geneva border. Century-old trees, barbecue area, children's playgrounds.",
            "de": "SCHATTIGE LIEGEWIESE + KIESSTRAND am Genfersee in Chens-sur-Léman, nahe der Genfer Grenze. Alte Bäume, Grillplatz, Kinderspielplätze.",
            "it": "SPIAGGIA OMBREGGIATA PRATO + GHIAIA sul Lago di Ginevra a Chens-sur-Léman, vicino al confine ginevrino. Alberi secolari, area barbecue, giochi.",
            "es": "PLAYA SOMBREADA CÉSPED + GUIJARROS en el Lago Lemán en Chens-sur-Léman, cerca de la frontera ginebrina. Árboles centenarios, barbacoa, juegos.",
        },
    },
    {
        "slug": "plage-de-messery", "lake": "leman", "commune": "Messery",
        "name": "Plage de Messery", "hero": "plage-de-messery-hero.jpg",
        "official": "https://www.messery.fr/vivre-a-messery/sport-loisirs/les-plages-de-messery/",
        "lat": 46.351, "lng": 6.293,
        "alt": {
            "fr": "Plage gazonnée 400 m - presqu'île face à Nyon Plage de Messery à Messery Lac Léman Haute-Savoie 74",
            "en": "400 m grassy beach on the peninsula facing Nyon, Plage de Messery in Messery, Lake Geneva, Haute-Savoie 74",
            "de": "400 m Liegewiese auf der Halbinsel gegenüber Nyon, Plage de Messery in Messery, Genfersee, Haute-Savoie 74",
            "it": "Spiaggia erbosa di 400 m sulla penisola di fronte a Nyon, Plage de Messery a Messery, Lago di Ginevra, Alta Savoia 74",
            "es": "Playa de césped de 400 m en la península frente a Nyon, Plage de Messery en Messery, Lago Lemán, Alta Saboya 74",
        },
        "desc": {
            "fr": "PLAGE GAZONNÉE 400 M 'Sous les Prés' sur la presqu'île de Messery, face à Nyon. Pente douce, zones ombragées, snack-bar et location en saison.",
            "en": "400 M GRASSY BEACH 'Sous les Prés' on the Messery peninsula, facing Nyon. Gentle slope, shaded areas, snack bar and rentals in season.",
            "de": "400 M LIEGEWIESE 'Sous les Prés' auf der Halbinsel Messery, gegenüber Nyon. Sanfter Einstieg, Schattenzonen, Imbiss und Verleih in der Saison.",
            "it": "SPIAGGIA ERBOSA 400 M 'Sous les Prés' sulla penisola di Messery, di fronte a Nyon. Pendenza dolce, zone ombreggiate, snack-bar e noleggio in stagione.",
            "es": "PLAYA DE CÉSPED 400 M 'Sous les Prés' en la península de Messery, frente a Nyon. Pendiente suave, zonas de sombra, snack-bar y alquiler en temporada.",
        },
    },
    {
        "slug": "plage-de-margencel-sechex", "lake": "leman", "commune": "Margencel",
        "name": "Plage de Margencel - Port de Séchex", "hero": "plage-de-margencel-sechex-hero.jpg",
        "official": "https://www.mairie-margencel.fr/plage-du-redon", "lat": 46.347, "lng": 6.42,
        "alt": {
            "fr": "Plage nature gazonnée - embouchure du Redon Plage de Margencel - Port de Séchex à Margencel Lac Léman Haute-Savoie 74",
            "en": "Natural grassy beach at the mouth of the Redon, Plage de Margencel - Port de Séchex in Margencel, Lake Geneva, Haute-Savoie 74",
            "de": "Natürliche Liegewiese an der Mündung des Redon, Plage de Margencel - Port de Séchex in Margencel, Genfersee, Haute-Savoie 74",
            "it": "Spiaggia erbosa naturale alla foce del Redon, Plage de Margencel - Port de Séchex a Margencel, Lago di Ginevra, Alta Savoia 74",
            "es": "Playa de césped natural en la desembocadura del Redon, Plage de Margencel - Port de Séchex en Margencel, Lago Lemán, Alta Saboya 74",
        },
        "desc": {
            "fr": "PLAGE NATURE GAZONNÉE à l'embouchure du Redon, près du Port de Séchex sur le Léman. Vieux chênes d'ombrage, caractère sauvage et calme.",
            "en": "NATURAL GRASSY BEACH at the mouth of the Redon, near Port de Séchex on Lake Geneva. Old shade oaks, a wild and quiet feel.",
            "de": "NATÜRLICHE LIEGEWIESE an der Mündung des Redon, nahe dem Port de Séchex am Genfersee. Alte Schatteneichen, wild und ruhig.",
            "it": "SPIAGGIA NATURALE ERBOSA alla foce del Redon, vicino al Port de Séchex sul Lago di Ginevra. Vecchie querce ombrose, carattere selvaggio e tranquillo.",
            "es": "PLAYA NATURAL DE CÉSPED en la desembocadura del Redon, cerca del Port de Séchex en el Lago Lemán. Viejos robles de sombra, carácter salvaje y tranquilo.",
        },
    },
]


def base_url(lang):
    return "https://loisirs74.fr" if lang == "fr" else f"https://loisirs74.fr/{lang}"


def amp(s):
    return s.replace("&", "&amp;")


def maps_url(name, commune):
    dest = quote(f"{name}, {commune}, Haute-Savoie")
    return f"https://www.google.com/maps/dir/?api=1&amp;destination={dest}"


def card_html(p, lang):
    b = base_url(lang)
    href = f"{b}/{p['slug']}"
    return (
        f'<article class="card" data-commune="{p["commune"]}">\n'
        f'<a class="card-photo" href="{href}">\n'
        f'<img alt="{amp(p["alt"][lang])}" loading="lazy" src="/{p["hero"]}"/>\n'
        f'<span class="card-tag is-gratuit">{FREEWORD[lang]}</span>\n'
        f'</a>\n'
        f'<div class="card-body">\n'
        f'<div class="card-commune"><span>{p["commune"]}</span></div>'
        f'<a class="title" href="{href}">{p["name"]}</a>\n'
        f'<p class="card-desc">{amp(p["desc"][lang])}</p>\n'
        f'<div class="card-actions">\n'
        f'<a href="{maps_url(p["name"], p["commune"])}" rel="noopener" target="_blank">{DIRECTIONS[lang]}</a>\n'
        f'<a href="{p["official"]}" rel="noopener" target="_blank">{OFFICIAL[lang]}</a>\n'
        f'</div>\n</div>\n</article>'
    )


def pin_obj(p, lang):
    b = base_url(lang)
    return json.dumps({"slug": p["slug"], "name": p["name"], "commune": p["commune"],
                       "lat": p["lat"], "lng": p["lng"], "url": f"{b}/{p['slug']}", "paid": False},
                      ensure_ascii=False)


def insert_card(text, lake, card):
    start = text.index(f'data-lac="{lake}"')
    cands = [text.find('<div class="commune-section"', start + 10),
             text.find('<div class="empty-state"', start),
             text.find('</main>', start)]
    end = min(c for c in cands if c != -1)
    block = text[start:end]
    li = block.rfind('</article>') + len('</article>')
    block = block[:li] + '\n' + card + block[li:]
    return text[:start] + block + text[end:]


def refresh_section_counts(text, family, lang):
    soup = BeautifulSoup(text, "html.parser")
    for sec in soup.select(".commune-section"):
        n = len(sec.select("article.card"))
        noun = SEC_NOUN[family][lang]
        head = sec.select_one(".commune-head")
        # rebuild the count span text within the raw text
    # do raw replacement per section using data-lac anchors
    for sec in soup.select(".commune-section"):
        lake = sec.get("data-lac")
        n = len(sec.select("article.card"))
        noun = SEC_NOUN[family][lang]
        # replace the count span that follows this section's head
        pat = re.compile(r'(data-lac="' + re.escape(lake) + r'">\s*<div class="commune-head"><h3>[^<]*</h3><span class="commune-count">)\d+ [^<]+(</span>)')
        text = pat.sub(lambda m: m.group(1) + f"{n} {noun}" + m.group(2), text, count=1)
    return text


def add_commune_options(text, new_communes):
    m = re.search(r'(<select id="filt-commune">)(.*?)(</select>)', text, re.S)
    head, body, tail = m.group(1), m.group(2), m.group(3)
    existing = set(re.findall(r'<option value="([^"]*)">', body))
    opts = re.findall(r'<option value="[^"]*">[^<]*</option>', body)
    first = opts[0]  # the "all communes" option (value="")
    rest = opts[1:]
    pairs = [(re.search(r'value="([^"]*)"', o).group(1), o) for o in rest]
    for c in new_communes:
        if c not in existing:
            pairs.append((c, f'<option value="{c}">{c}</option>'))
    pairs.sort(key=lambda x: x[0].lower())
    newbody = first + "".join(o for _, o in pairs)
    return text[:m.start()] + head + newbody + tail + text[m.end():]


def update_cat_hero(text, total, communes):
    return re.sub(
        r'(<p class="meta"><b>)\d+( \w+</b><span class="dot">·</span><span>)\d+( [^<]+</span></p>)',
        lambda m: m.group(1) + str(total) + m.group(2) + str(communes) + m.group(3),
        text, count=1)


def update_itemlist(text, hub_plages, lang):
    m = re.search(r'<script type="application/ld\+json">(\{(?:[^<]*"@type": "ItemList"[^<]*)\})</script>', text, re.S)
    if not m:
        # find the ld+json script containing ItemList
        for sm in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', text, re.S):
            if '"@type": "ItemList"' in sm.group(1):
                m = sm
                break
    if not m:
        return text
    data = json.loads(m.group(1))
    items = data.get("itemListElement", [])
    pos = len(items)
    b = base_url(lang)
    for p in hub_plages:
        pos += 1
        items.append({
            "@type": "ListItem", "position": pos,
            "item": {
                "@type": "TouristAttraction", "name": p["name"], "url": f"{b}/{p['slug']}",
                "address": {"@type": "PostalAddress", "addressLocality": p["commune"],
                            "addressRegion": "Haute-Savoie", "addressCountry": "FR"},
            },
        })
    data["itemListElement"] = items
    data["numberOfItems"] = len(items)
    if "description" in data:
        data["description"] = re.sub(r'\d+', str(len(items)), data["description"], count=1)
    newjson = json.dumps(data, ensure_ascii=False, indent=2)
    return text[:m.start(1)] + newjson + text[m.end(1):]


def process(hub_map, family):
    for lang in LANGS:
        path = ROOT / hub_map[lang]
        text = path.read_text(encoding="utf-8")
        new_communes = []
        for p in PLAGES:
            text = insert_card(text, p["lake"], card_html(p, lang))
            new_communes.append(p["commune"])
            # insert pin before the PINS array close
            pi = text.index("];", text.index("const PINS"))
            text = text[:pi] + ", " + pin_obj(p, lang) + text[pi:]
        text = refresh_section_counts(text, family, lang)
        text = add_commune_options(text, new_communes)
        # totals
        soup = BeautifulSoup(text, "html.parser")
        total = len(soup.select("article.card"))
        communes = len({c.get("data-commune") for c in soup.select("article.card")})
        text = update_cat_hero(text, total, communes)
        text = update_itemlist(text, PLAGES, lang)
        path.write_text(text, encoding="utf-8")
        print(f"  ✓ {hub_map[lang]:24s} cards={total} communes={communes}")


def main():
    print("Integrating into /plages/ family")
    process(PLAGES_HUB, "plages")
    print("Integrating into /lacs/ family")
    process(LACS_HUB, "lacs")


if __name__ == "__main__":
    main()
