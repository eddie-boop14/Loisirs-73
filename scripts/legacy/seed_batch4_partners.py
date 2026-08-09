#!/usr/bin/env python3
"""Seed partner cards from Batch-4 research report.

Each entry becomes a tier:recommended partner (renders as a flip card
with the 'À proximité' badge — no engagement claim).
Replaces any existing tier:invite cards on the venue.
"""
import json
from pathlib import Path

ROOT = Path("/home/user/Loisir-74")

# Partner data per venue slug. Each list entry: (name, type, description, url).
# Empty list = venue has no qualifying partners per the report.
PARTNERS = {
    "plage-d-amphion-publier": [
        ("Le Radeau d'Alexis", "restaurant",
         "Restaurant sur pilotis sur la plage d'Amphion, l'un des derniers du Léman. Fondé en 1901, 4e génération.",
         "https://www.hotelplage74.com"),
        ("Fromagerie du Noyer", "commerce",
         "Affineur indépendant à Évian (~4 km). Fromages locaux savoyards et suisses, lundi-samedi.",
         "https://fromageriedunoyer.fr"),
        ("Hôtel de la Plage ***", "hebergement",
         "39 chambres dans un parc centenaire au bord du lac, ouvert de mars à décembre.",
         "https://www.hotelplage74.com"),
    ],
    "gr5-grande-traversee-alpes-saint-gingolph": [
        ("Aux Ducs de Savoie", "restaurant",
         "Restaurant familial à Saint-Gingolph depuis 1952. Cuisine savoyarde traditionnelle et inventive, faite maison.",
         "https://auxducsdesavoie.fr"),
        ("Fromagerie du Noyer", "commerce",
         "Fromagerie et produits du terroir, rue Nationale à Saint-Gingolph. Mardi-samedi.",
         "https://fromageriedunoyer.fr"),
        ("Hôtel Le Léman", "hebergement",
         "Hôtel familial face au lac avec plage privée, en bord de village.",
         "https://www.hotel-leman.fr"),
    ],
    "grp-littoral-leman-saint-gingolph": [
        ("Bar-restaurant de la Plage", "restaurant",
         "Restaurant panoramique de 80 couverts sur la plage municipale de Saint-Gingolph.",
         "https://www.plagedesaintgingolph.fr"),
        ("Fromagerie du Noyer", "commerce",
         "Fromagerie et produits du terroir au cœur de Saint-Gingolph.",
         "https://fromageriedunoyer.fr"),
        ("Hôtel Le Léman", "hebergement",
         "Hôtel familial face au lac avec plage privée.",
         "https://www.hotel-leman.fr"),
    ],
    "leman-forest-saint-gingolph": [
        ("Restaurant La Dame du Lac", "restaurant",
         "Restaurant et bar à tapas en bord de lac, terrasse couverte et snack adjacent.",
         "https://www.restaurant-la-dame-du-lac.fr"),
        ("Fromagerie du Noyer", "commerce",
         "Fromagerie et produits du terroir au cœur de Saint-Gingolph.",
         "https://fromageriedunoyer.fr"),
        ("Hôtel Le Léman", "hebergement",
         "Hôtel familial face au lac avec plage privée.",
         "https://www.hotel-leman.fr"),
    ],
    "plage-de-saint-gingolph": [
        ("Bar-restaurant de la Plage", "restaurant",
         "Restaurant panoramique de 80 couverts sur la plage municipale.",
         "https://www.plagedesaintgingolph.fr"),
        ("Fromagerie du Noyer", "commerce",
         "Fromagerie et produits du terroir au cœur de Saint-Gingolph.",
         "https://fromageriedunoyer.fr"),
        ("Hôtel Le Léman", "hebergement",
         "Hôtel familial face au lac avec plage privée.",
         "https://www.hotel-leman.fr"),
    ],
    "viarhona-haute-savoie-saint-gingolph-seyssel": [
        ("Aux Ducs de Savoie", "restaurant",
         "Restaurant familial à Saint-Gingolph depuis 1952, cuisine savoyarde faite maison.",
         "https://auxducsdesavoie.fr"),
        ("Fromagerie du Noyer", "commerce",
         "Fromagerie et produits du terroir au cœur de Saint-Gingolph.",
         "https://fromageriedunoyer.fr"),
        ("Hôtel Le Léman", "hebergement",
         "Hôtel familial face au lac avec plage privée.",
         "https://www.hotel-leman.fr"),
    ],
    "casino-evian-resort-evian": [
        ("Le Refuge du Lac", "restaurant",
         "Restaurant face à l'embarcadère d'Évian. Cuisine savoyarde aux produits locaux, ouverture 2023.",
         "https://lerefugedulac-evian.com"),
        ("Fromagerie du Noyer", "commerce",
         "Fromagerie centre-ville Évian, rue Nationale.",
         "https://fromageriedunoyer.fr"),
        ("Hôtel de France", "hebergement",
         "Hôtel 2★ centre-ville Évian, vue panoramique sur le lac. Bâti en 1859.",
         "https://hotel-france-evian.fr"),
    ],
    "croisiere-cgn-evian": [
        ("La Voile", "restaurant",
         "Brasserie et glacier en bord de port, plats de poissons du lac.",
         "https://www.la-voile.fr"),
        ("Fromagerie du Noyer", "commerce",
         "Fromagerie centre-ville Évian, rue Nationale.",
         "https://fromageriedunoyer.fr"),
        ("Hôtel Le Littoral ***", "hebergement",
         "Hôtel familial 30 chambres avec balcons, sauna et hammam.",
         "https://hotel-littoral-evian.fr"),
    ],
    "palais-lumiere": [
        ("Le Refuge du Lac", "restaurant",
         "Restaurant face à l'embarcadère d'Évian, cuisine savoyarde aux produits locaux.",
         "https://lerefugedulac-evian.com"),
        ("Fromagerie du Noyer", "commerce",
         "Fromagerie centre-ville Évian, rue Nationale.",
         "https://fromageriedunoyer.fr"),
        ("Hôtel le Bourgogne", "hebergement",
         "Hôtel 3★ centre-ville Évian, 30 chambres.",
         "https://hotellebourgogne.fr"),
    ],
    "plage-d-evian-centre-nautique": [
        ("Restaurant Les Cygnes", "restaurant",
         "Restaurant gastronomique et bistrot bâti sur l'eau, vue lac et spécialités savoyardes.",
         "https://www.hotellescygnes.com"),
        ("Fromagerie du Noyer", "commerce",
         "Fromagerie centre-ville Évian, rue Nationale.",
         "https://fromageriedunoyer.fr"),
        ("Hôtel Les Cygnes ***", "hebergement",
         "Le seul hôtel construit sur l'eau à Évian (depuis 1926). 36 chambres, piscine chauffée.",
         "https://www.hotellescygnes.com"),
    ],
    "thermes-evian": [
        ("La Voile", "restaurant",
         "Brasserie au port d'Évian, plats de poissons du lac.",
         "https://www.la-voile.fr"),
        ("Fromagerie du Noyer", "commerce",
         "Fromagerie centre-ville Évian, rue Nationale.",
         "https://fromageriedunoyer.fr"),
        ("Hôtel Evian Express", "hebergement",
         "Hôtel contemporain face au lac, proche centre, quais et plages.",
         "https://www.hotel-evianexpress.net"),
    ],
    # 12-14: no qualifying partners (chateaux-des-allinges, chateau-avully-brenthonne, plage-de-tougues-chens)
    "plage-d-excenevex": [
        ("Les Sables", "restaurant",
         "Restaurant et bar de plage en bord de lac avec plage privée, cuisine de marché saisonnière.",
         "https://les-sables-excenevex.fr"),
        ("Hôtel Restaurant de la Plage", "hebergement",
         "Hôtel 12 chambres avec plage privée, style Art Déco/contemporain.",
         "https://hoteldelaplagexnv.fr"),
    ],
    # 16: chateau-la-rochette-lully — no qualifying partners
    "bowling-margencel-margencel": [
        ("Séchex Nous", "restaurant",
         "Restaurant gastronomique 1 étoile Michelin (2025), poissons du lac dans une ancienne ferme rénovée.",
         "https://www.sechex-nous.com"),
        ("Séchex Nous", "hebergement",
         "3 chambres à proximité du port de Séchex, attenantes au restaurant étoilé.",
         "https://www.sechex-nous.com"),
    ],
    "plage-de-margencel-sechex": [
        ("Séchex Nous", "restaurant",
         "Restaurant gastronomique 1 étoile Michelin (2025), à quelques mètres du port de Séchex.",
         "https://www.sechex-nous.com"),
        ("Séchex Nous", "hebergement",
         "3 chambres à proximité du port de Séchex, attenantes au restaurant étoilé.",
         "https://www.sechex-nous.com"),
    ],
    # 19: plage-de-messery — no qualifying partners
    "croisiere-cgn-yvoire": [
        ("Hôtel Restaurant du Port", "restaurant",
         "Restaurant en bord d'embarcadère, cuisine de poissons du lac (famille Kung, depuis 1820).",
         "https://hdpy.fr"),
        ("Villa Cécile", "hebergement",
         "Hôtel 4★ avec spa, au cœur du village médiéval d'Yvoire.",
         "https://www.villacecile.com"),
    ],
    "domaine-de-rovoree-la-chataigniere": [
        ("La Riviera Victoria", "restaurant",
         "Hôtel-restaurant en bord du port d'Yvoire.",
         "https://www.larivieravictoria.com"),
        ("Le Pré de la Cure", "hebergement",
         "Hôtel à l'entrée d'Yvoire avec piscine, sauna, hammam et jacuzzi.",
         "https://www.hotel-restaurant-piscine-haute-savoie.com"),
    ],
    "jardin-des-cinq-sens": [
        ("Le Vieux Logis", "restaurant",
         "Hôtel-restaurant dans les remparts d'Yvoire, cuisine du terroir. Famille Jacquier-Durand depuis 1896.",
         "https://www.levieuxlogis.com"),
        ("Le Vieux Logis", "hebergement",
         "10 chambres au cœur du village médiéval d'Yvoire, dans les remparts.",
         "https://www.levieuxlogis.com"),
    ],
    "acroparc-de-bellavallis-bellevaux": [
        ("Hôtel Les Moineaux", "restaurant",
         "Hôtel-restaurant à Bellevaux, cuisine du terroir.",
         "https://www.hotel-les-moineaux.com"),
        ("Hôtel Les Moineaux", "hebergement",
         "14 chambres avec balcon ou terrasse, piscine et tennis, à Bellevaux.",
         "https://www.hotel-les-moineaux.com"),
    ],
    "cascade-de-la-diomaz": [
        ("Hôtel Les Moineaux", "restaurant",
         "Hôtel-restaurant à Bellevaux, cuisine du terroir.",
         "https://www.hotel-les-moineaux.com"),
        ("Hôtel Les Skieurs", "hebergement",
         "Hôtel ski-in/out à Hirmentaz avec spa (piscine à contre-courant, hammam, jacuzzi).",
         "https://hotellesskieurs.com"),
    ],
    "lac-de-vallon": [
        ("Hôtel Les Moineaux", "restaurant",
         "Hôtel-restaurant à Bellevaux, cuisine du terroir.",
         "https://www.hotel-les-moineaux.com"),
        ("Hôtel Les Moineaux", "hebergement",
         "14 chambres avec balcon ou terrasse, piscine et tennis, à Bellevaux.",
         "https://www.hotel-les-moineaux.com"),
    ],
    "cascade-des-brochaux": [
        ("Auberge du Bout du Lac", "restaurant",
         "Restaurant Maître Restaurateur, vue panoramique lac et Roc d'Enfer, cuisine du terroir.",
         "https://leboutdulac.com"),
        ("Fromagerie du Noyer (Morzine)", "commerce",
         "Fromagerie indépendante à Morzine, commune voisine.",
         "https://fromageriedunoyer.fr"),
        ("Hôtel du Lac", "hebergement",
         "Hôtel boutique de 20 chambres en bord du Lac de Montriond.",
         "https://lacdemontriond.com"),
    ],
    "plage-du-lac-de-montriond": [
        ("Hôtel du Lac", "restaurant",
         "Restaurant saisonnier en bord du Lac de Montriond.",
         "https://lacdemontriond.com"),
        ("L'Alpage – Fruitière de Morzine", "commerce",
         "Fromager artisanal à Morzine, commune voisine.",
         "https://alpage-morzine.com"),
        ("Hôtel du Lac", "hebergement",
         "Hôtel boutique de 20 chambres en bord du Lac de Montriond.",
         "https://lacdemontriond.com"),
    ],
    "base-de-loisirs-du-lac-bleu": [
        ("Hôtel Le Morillon ***", "restaurant",
         "Hôtel-restaurant au centre de Morillon, spécialités savoyardes.",
         "https://www.hotellemorillon.com"),
        ("Le Refuge des Saveurs", "commerce",
         "Épicerie fine et fromagerie indépendante à Samoëns (commune voisine, ~4 km).",
         "https://www.lerefugedessaveurssamoens.fr"),
        ("Hôtel Le Morillon ***", "hebergement",
         "Hôtel avec spa et piscine chauffée à Morillon.",
         "https://www.hotellemorillon.com"),
    ],
    "abbaye-d-aulps": [
        ("La Ferme du Caly", "commerce",
         "Ferme-fromagerie à Saint-Jean-d'Aulps : raclette, Abondance, tomme, fondue. Click & collect.",
         "https://lafermeducaly.fr"),
    ],
    "base-de-loisirs-du-lac-aux-dames": [
        ("Neige et Roc", "restaurant",
         "Hôtel-restaurant à Samoëns, cuisine gastronomique et sélection de poissons du lac.",
         "https://www.neigeetroc.com"),
        ("Boucherie Le Pied de Poule", "commerce",
         "Boucherie et épicerie fine indépendante à Samoëns.",
         "https://www.boucherie-lepieddepoule.fr"),
        ("Neige et Roc ****", "hebergement",
         "Hôtel-chalet 48 chambres, deux piscines chauffées, spa, parc d'un hectare à Samoëns.",
         "https://www.neigeetroc.com"),
    ],
    "jardin-jaysinia-samoens": [
        ("Hôtel Gai Soleil", "restaurant",
         "Hôtel-restaurant à Samoëns, spécialités savoyardes (Logis, Table Savoureuse).",
         "https://www.hotel-samoens.com"),
        ("Le Refuge des Saveurs", "commerce",
         "Épicerie fine et fromagerie indépendante adjacente à la place Jaÿsinia.",
         "https://www.lerefugedessaveurssamoens.fr"),
        ("Hôtel Edelweiss", "hebergement",
         "Hôtel 2★ à Samoëns, 20 chambres lambrisées, four à pain.",
         "https://www.edelweiss-samoens.com"),
    ],
    "abbaye-de-sixt": [
        ("Auberge de la Feuille d'Erable", "restaurant",
         "Restaurant à Sixt-Fer-à-Cheval, cuisine savoyarde faite maison.",
         "https://www.aubergedelafeuillederable.fr"),
        ("Sherpa Sixt-Fer-à-Cheval", "commerce",
         "Supermarché de proximité (chaîne — fallback) à Sixt-Fer-à-Cheval.",
         "https://www.sherpa.net"),
    ],
    "cascade-du-rouget": [
        ("Le Rouet", "restaurant",
         "Restaurant à Sixt-Fer-à-Cheval, cuisine savoyarde et traditionnelle, terrasse face aux cascades.",
         "https://www.lerouet.fr"),
        ("Sherpa Sixt-Fer-à-Cheval", "commerce",
         "Supermarché de proximité (chaîne — fallback) à Sixt-Fer-à-Cheval.",
         "https://www.sherpa.net"),
    ],
    "cirque-du-fer-a-cheval": [
        ("Auberge de la Feuille d'Erable", "restaurant",
         "Restaurant à Sixt-Fer-à-Cheval, cuisine savoyarde faite maison.",
         "https://www.aubergedelafeuillederable.fr"),
        ("Sherpa Sixt-Fer-à-Cheval", "commerce",
         "Supermarché de proximité (chaîne — fallback) à Sixt-Fer-à-Cheval.",
         "https://www.sherpa.net"),
    ],
    "sentier-cascades-sixt-fer-a-cheval": [
        ("Le Rouet", "restaurant",
         "Restaurant à Sixt-Fer-à-Cheval, terrasse face aux cascades.",
         "https://www.lerouet.fr"),
        ("Sherpa Sixt-Fer-à-Cheval", "commerce",
         "Supermarché de proximité (chaîne — fallback) à Sixt-Fer-à-Cheval.",
         "https://www.sherpa.net"),
    ],
    "chateau-et-donjon-des-seigneurs-de-faverges": [
        ("Boucherie Périllat & Co", "commerce",
         "Boucherie et épicerie fine à Faverges-Seythenex : Reblochon fermier, Beaufort d'alpage, crozets.",
         "https://www.boucherie-perillat-faverges.fr"),
    ],
    "grotte-et-cascade-de-seythenex": [
        ("Boucherie Périllat & Co", "commerce",
         "Boucherie et épicerie fine à Faverges-Seythenex.",
         "https://www.boucherie-perillat-faverges.fr"),
    ],
    "musee-archeologique-viuz-faverges": [
        ("Boucherie Périllat & Co", "commerce",
         "Boucherie et épicerie fine à Faverges-Seythenex.",
         "https://www.boucherie-perillat-faverges.fr"),
    ],
    "museum-des-papillons-et-insectes-faverges": [
        ("Boucherie Périllat & Co", "commerce",
         "Boucherie et épicerie fine à Faverges-Seythenex.",
         "https://www.boucherie-perillat-faverges.fr"),
    ],
    "plage-de-menthon-saint-bernard": [
        ("Restaurant du Palace de Menthon", "restaurant",
         "Cuisine créative du chef Frédéric Delormes, vue lac, plage privée.",
         "https://www.palacedementhon.com"),
        ("Les Halles de Menthon", "commerce",
         "Épicerie et produits régionaux : fromages locaux, charcuterie, poissons du lac (enseigne 8 à Huit).",
         "https://www.les-halles-de-menthon.fr"),
        ("Le Palace de Menthon *****", "hebergement",
         "Hôtel 5★ avec marina privée et accès direct à la plage, 66 chambres et suites.",
         "https://www.palacedementhon.com"),
    ],
}


def to_partner_entry(name, ptype, desc, url):
    return {
        "tier": "recommended",
        "name": name,
        "type": ptype,
        "description": desc,
        "url": url,
        "cta_text": "Voir le site →",
        "i18n": {"fr": {"description": desc}},
    }


def main():
    updated = []
    skipped = []
    for slug, items in PARTNERS.items():
        if not items:
            continue
        path = ROOT / "Json" / f"{slug}.json"
        if not path.exists():
            skipped.append(slug)
            continue
        d = json.loads(path.read_text(encoding="utf-8"))
        # Remove any existing tier:invite entries and replace with new recommended ones.
        existing = d.get("partners", [])
        keep = [p for p in existing if p.get("tier") not in ("invite", "recommended")]
        new_entries = [to_partner_entry(*it) for it in items]
        d["partners"] = keep + new_entries
        path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        updated.append(slug)
    print(f"Updated {len(updated)} venue JSONs")
    if skipped:
        print(f"Skipped (JSON missing): {skipped}")


if __name__ == "__main__":
    main()
