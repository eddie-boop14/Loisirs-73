#!/usr/bin/env python3
"""Seed partner cards from Batch-5 research report (Thonon remainder /
Genevois-Salève / Annemasse / Glières-Fillière, 40 venues).

Each entry becomes a tier:recommended partner (À proximité grey card).
Empty venues per the report (Filenvol, Mont Salève, Tropicaland) are skipped.
"""
import json
from pathlib import Path

ROOT = Path("/home/user/Loisir-74")


PARTNERS = {
    # 1. Plage de la Pinède — Thonon
    "plage-de-la-pinede": [
        ("Le Naviot", "restaurant",
         "Restaurant/brasserie lacustre au Port de Rives, filets de perches et spécialités du Léman, terrasse panoramique.",
         "https://restaurant-lenaviot.com/"),
        ("Fromagerie Boujon", "commerce",
         "Maître fromager affineur depuis 1974, vieille ville de Thonon. 250-300 variétés, principalement au lait cru.",
         "https://fromagerie-boujon.com/"),
    ],
    # 2. Plage de Saint-Disdille — Thonon
    "plage-de-saint-disdille": [
        ("Bar-Restaurant du Camping Saint-Disdille", "restaurant",
         "Restaurant-bar de terrasse au camping, grillades, pizzas au feu de bois et perches grillées. Ouvert d'avril à septembre.",
         "https://www.disdille.com/"),
        ("Camping Saint-Disdille", "hebergement",
         "Camping 3★ familial 12 ha boisé, mobile-homes et emplacements 100-140 m² à 200 m du lac. Labels Camping Qualité / Famille Plus.",
         "https://www.disdille.com/"),
    ],
    # 3. Plage municipale Thonon
    "plage-municipale-thonon": [
        ("Les Rives du Léman", "restaurant",
         "Brasserie traditionnelle en bord de lac, poissons frais et cuisine française.",
         "https://www.restaurant-brasserie-thonon.fr/"),
        ("Buttay Affineur", "commerce",
         "Affineur indépendant, avenue de la Font Couverte. Lun-sam 8h30-12h et 14h-18h30.",
         "https://buttay-affineur.fr/"),
    ],
    # 4. Tour des Langues — Thonon
    "tour-des-langues-thonon": [
        ("Le Naviot", "restaurant",
         "Restaurant/brasserie lacustre au Port de Rives, sous la vieille ville. Spécialités du Léman.",
         "https://restaurant-lenaviot.com/"),
        ("Fromagerie Boujon", "commerce",
         "Affineur de la vieille ville, 250-300 variétés au lait cru. À courte distance à pied.",
         "https://fromagerie-boujon.com/"),
    ],
    # 5. ViaRhôna EV17 Bas-Chablais
    "viarhona-ev17-bas-chablais-thonon": [
        ("Bar-Restaurant du Camping Saint-Disdille", "restaurant",
         "Restaurant-bar sur l'itinéraire cyclable près du delta de la Dranse. Avril à septembre.",
         "https://www.disdille.com/"),
        ("Camping Saint-Disdille", "hebergement",
         "Camping 3★ sur l'itinéraire cyclable, près du delta de la Dranse.",
         "https://www.disdille.com/"),
    ],
    # 6. Cercle Voile Thonon
    "voile-cercle-thonon-thonon": [
        ("Le Naviot", "restaurant",
         "Restaurant/brasserie au port de plaisance, à côté du club de voile.",
         "https://restaurant-lenaviot.com/"),
        ("Buttay Affineur", "commerce",
         "Affineur indépendant, avenue de la Font Couverte.",
         "https://buttay-affineur.fr/"),
    ],
    # 7. Grand Parc d'Andilly
    "grand-parc-d-andilly": [
        ("Fruitière du Mont-Salève (Fruitières Chabert)", "commerce",
         "Fromagerie coopérative, route des Dronières à Cruseilles (~5 km). Domaine multi-sites.",
         "https://www.fruitieres-chabert.com"),
        ("L'Arborescence", "hebergement",
         "Hôtel-restaurant indépendant 10 chambres style montagne, vue sur le Lac des Dronières (~6 km).",
         "https://www.arborescence-restaurant.fr/"),
    ],
    # 8. Château de Clermont
    "chateau-clermont-genevois": [
        ("Auberge du Château de Clermont", "restaurant",
         "Cuisine française régionale saisonnière, à côté du château Renaissance. Mer-dim.",
         "https://auberge-chateauclermont.fr/"),
    ],
    # 9. Col / Pitons du Salève (Collonges)
    "col-des-pitons-saleve": [
        ("Namasté", "restaurant",
         "Restaurant indien indépendant à Collonges-sous-Salève, en contrebas des falaises.",
         "https://www.restaurant-indien-collonges.com/"),
    ],
    # 10. Lac des Dronières
    "lac-des-dronieres": [
        ("L'Arborescence", "restaurant",
         "Restaurant gastronomique en bord du Lac des Dronières (successeur de L'Ancolie).",
         "https://www.arborescence-restaurant.fr/"),
        ("Fruitière du Mont-Salève (Fruitières Chabert)", "commerce",
         "Fromagerie coopérative, route des Dronières à Cruseilles.",
         "https://www.fruitieres-chabert.com"),
        ("L'Arborescence", "hebergement",
         "Hôtel 10 chambres indépendant en bord de lac.",
         "https://www.arborescence-restaurant.fr/"),
    ],
    # 11. Parc des Dronières
    "parc-des-dronieres": [
        ("L'Arborescence", "restaurant",
         "Restaurant gastronomique en bord du Lac des Dronières.",
         "https://www.arborescence-restaurant.fr/"),
        ("Fruitière du Mont-Salève (Fruitières Chabert)", "commerce",
         "Fromagerie coopérative, route des Dronières à Cruseilles.",
         "https://www.fruitieres-chabert.com"),
        ("L'Arborescence", "hebergement",
         "Hôtel 10 chambres en bord du Lac des Dronières.",
         "https://www.arborescence-restaurant.fr/"),
    ],
    # 12. Pont de la Caille
    "pont-de-la-caille": [
        ("La 99ème", "restaurant",
         "Bar à tapas et restaurant au pied des ponts historiques. Mer-dim.",
         "https://www.la99eme.com/"),
        ("Fruitière du Mont-Salève (Fruitières Chabert)", "commerce",
         "Fromagerie coopérative, route des Dronières à Cruseilles.",
         "https://www.fruitieres-chabert.com"),
    ],
    # 13. Sentier Balcon du Léman
    "sentier-balcon-leman-saleve": [
        ("L'Arborescence", "restaurant",
         "Hôtel-restaurant gastronomique en bord du Lac des Dronières.",
         "https://www.arborescence-restaurant.fr/"),
        ("Fruitière du Mont-Salève (Fruitières Chabert)", "commerce",
         "Fromagerie coopérative, route des Dronières à Cruseilles.",
         "https://www.fruitieres-chabert.com"),
        ("L'Arborescence", "hebergement",
         "Hôtel 10 chambres indépendant en bord de lac.",
         "https://www.arborescence-restaurant.fr/"),
    ],
    # 14, 15 → empty (Filenvol, Mont Salève summit)
    # 16. Vitam Parc — Neydens
    "vitam-neydens": [
        ("Le San Juliano", "restaurant",
         "Pizzeria-savoyard indépendant à 5 min de Vitam. Mer-dim.",
         "https://www.sanjuliano.com/"),
    ],
    # 17. Maison du Salève — Présilly
    "maison-du-saleve-presilly": [
        ("Chartreuse de Pomier", "restaurant",
         "Ancienne maison de réception et restaurant historique au pied du Salève.",
         "https://www.chartreuse-de-pomier.fr/"),
    ],
    # 18. Sentier Maison du Salève / Pomier
    "sentier-maison-saleve-pomier-presilly": [
        ("Chartreuse de Pomier", "restaurant",
         "Ancienne maison de réception et restaurant historique au pied du Salève.",
         "https://www.chartreuse-de-pomier.fr/"),
    ],
    # 19. Téléphérique du Salève
    "telepherique-du-saleve": [
        ("Vertiges", "restaurant",
         "Restaurant bistronomique panoramique à 1 097 m d'altitude (sommet, 108 couverts, ouvert oct. 2025). Réservation obligatoire + billet téléphérique.",
         "https://www.telepherique-du-saleve.com/"),
        ("Boutique du Téléphérique du Salève", "commerce",
         "Boutique souvenirs sur place, à la gare d'arrivée du téléphérique.",
         "https://www.telepherique-du-saleve.com/"),
    ],
    # 20. Aquaparc Château Bleu — Annemasse
    "aquaparc-chateau-bleu-annemasse": [
        ("Le Paul Bert", "restaurant",
         "Restaurant indépendant fusion asiatique/française au centre d'Annemasse. Mar-sam midi et soir.",
         "https://le-paul-bert.fr/"),
        ("Pâtisserie-Chocolaterie Lesage", "commerce",
         "Pâtissier-chocolatier familial indépendant, place Jean-Jacques Rousseau. Macarons, chocolats, glaces.",
         "https://www.patisserie-lesage.com/"),
    ],
    # 21. Bowling Aérodrome — Annemasse
    "bowling-aerodrome-annemasse": [
        ("Il Vesuvio", "restaurant",
         "Restaurant italien indépendant utilisant des produits locaux de saison, rue Marc Courriard.",
         "https://www.restaurant-il-vesuvio-annemasse.fr/"),
        ("Pâtisserie-Chocolaterie Lesage", "commerce",
         "Pâtissier-chocolatier familial, place Jean-Jacques Rousseau à Annemasse.",
         "https://www.patisserie-lesage.com/"),
    ],
    # 22. Villa du Parc — Annemasse
    "villa-du-parc-annemasse": [
        ("Le Paul Bert", "restaurant",
         "Restaurant indépendant fusion asiatique/française au centre d'Annemasse.",
         "https://le-paul-bert.fr/"),
        ("Pâtisserie-Chocolaterie Lesage", "commerce",
         "Pâtissier-chocolatier familial, place Jean-Jacques Rousseau.",
         "https://www.patisserie-lesage.com/"),
    ],
    # 23. Wakepark TNA — Arenthon
    "wakepark-tna-cable-park-arenthon": [
        ("Snack P2", "restaurant",
         "Snack sur place au TNA Cable Park, ouvert d'avril à septembre.",
         "https://www.tnacablepark.com/"),
        ("Hôtel-Restaurant Baud", "hebergement",
         "Hôtel-restaurant gastronomique 4★ indépendant à Bonne (~4-5 km), plus proche hébergement avec son propre site.",
         "https://hotel-baud.com/"),
    ],
    # 24. Acro'Aventures Reignier
    "acro-aventures-reignier": [
        ("La Table d'Angèle", "restaurant",
         "Restaurant bistronomique indépendant à Reignier-Ésery.",
         "https://www.tabledangele.com/"),
        ("Hôtel-Restaurant La Tour d'Ivoire", "hebergement",
         "Hôtel-restaurant indépendant près de la gare de Reignier et du Golf d'Esery.",
         "https://latourdivoire.com/"),
    ],
    # 25. Tour de Bellecombe — Reignier
    "tour-bellecombe-reignier": [
        ("La Table d'Angèle", "restaurant",
         "Restaurant bistronomique indépendant à Reignier-Ésery.",
         "https://www.tabledangele.com/"),
        ("Hôtel-Restaurant La Tour d'Ivoire", "hebergement",
         "Hôtel-restaurant indépendant à Reignier-Ésery.",
         "https://latourdivoire.com/"),
    ],
    # 26. Karting MK Circuit — Scientrier
    "karting-mk-circuit-scientrier": [
        ("MK Circuit (traiteur sur place)", "restaurant",
         "Traiteur sur place pour groupes 15+, route de l'Arve.",
         "https://www.mk-circuit.com/"),
        ("Hôtel-Restaurant Baud", "hebergement",
         "Hôtel-restaurant gastronomique 4★ indépendant à Bonne, plus proche hébergement avec son propre site.",
         "https://hotel-baud.com/"),
    ],
    # 27. C5 Kids Party — Ville-la-Grand
    "c5-kids-party-ville-la-grand": [
        ("Il Vesuvio", "restaurant",
         "Restaurant italien indépendant à Annemasse (commune adjacente).",
         "https://www.restaurant-il-vesuvio-annemasse.fr/"),
        ("Pâtisserie-Chocolaterie Lesage", "commerce",
         "Pâtissier-chocolatier familial à Annemasse (commune adjacente).",
         "https://www.patisserie-lesage.com/"),
    ],
    # 28. Musée du Bâtiment — Ville-la-Grand
    "musee-du-batiment-ville-la-grand": [
        ("Le Paul Bert", "restaurant",
         "Restaurant indépendant fusion à Annemasse (commune adjacente).",
         "https://le-paul-bert.fr/"),
        ("Pâtisserie-Chocolaterie Lesage", "commerce",
         "Pâtissier-chocolatier familial à Annemasse (commune adjacente).",
         "https://www.patisserie-lesage.com/"),
    ],
    # 29 → empty (Tropicaland)
    # 30. Île de Tortuga — Vétraz-Monthoux
    "ile-de-tortuga-vetraz-monthoux": [
        ("Taverne de la Tortue", "restaurant",
         "Restaurant-bar sur place dans le parc couvert, allée des Chênes.",
         "https://parctortuga.fr/"),
        ("Pâtisserie-Chocolaterie Lesage", "commerce",
         "Pâtissier-chocolatier familial à Annemasse (commune voisine).",
         "https://www.patisserie-lesage.com/"),
    ],
    # 31. Tête du Parmelan — Dingy-Saint-Clair
    "tete-du-parmelan": [
        ("Auberge du Marmiton", "restaurant",
         "Bar-restaurant de village avec terrasse face au Parmelan, à Dingy-Saint-Clair.",
         "https://www.restaurant-thones.fr/"),
        ("Épicerie–dépôt de pain de l'Auberge du Marmiton", "commerce",
         "Petite épicerie et dépôt de pain avec produits locaux à l'auberge.",
         "https://www.restaurant-thones.fr/"),
    ],
    # 32. Base de loisirs du Vuaz — Fillière
    "base-de-loisirs-du-vuaz-filliere": [
        ("La Chaumière Saint-Maurice", "restaurant",
         "Restaurant et hôtel de village à Thorens-Glières.",
         "https://www.chaumiere-saintmaurice.com"),
        ("Fruitière de Thorens-Glières (Fruitières Chabert)", "commerce",
         "Fromagerie coopérative Abondance AOP à Thorens-Glières.",
         "https://www.fruitieres-chabert.com"),
        ("Château de Thorens", "hebergement",
         "Hôtel 4★ confidentiel dans le château historique, chemin du Château.",
         "https://chateaudethorens.com/"),
    ],
    # 33. Château de Thorens
    "chateau-de-thorens": [
        ("La Chaumière Saint-Maurice", "restaurant",
         "Restaurant et hôtel de village à Thorens-Glières.",
         "https://www.chaumiere-saintmaurice.com"),
        ("Fruitière de Thorens-Glières (Fruitières Chabert)", "commerce",
         "Fromagerie coopérative Abondance AOP, sur la route du château.",
         "https://www.fruitieres-chabert.com"),
        ("Château de Thorens", "hebergement",
         "Hôtel 4★ confidentiel sur place dans le château historique.",
         "https://chateaudethorens.com/"),
    ],
    # 34. Col des Glières
    "col-des-glieres": [
        ("Auberge des Glières", "restaurant",
         "Auberge de montagne avec restaurant et spa sur le plateau.",
         "https://www.aubergedesglieres.fr/"),
        ("Fruitière de Thorens-Glières (Fruitières Chabert)", "commerce",
         "Fromagerie coopérative Abondance AOP à Thorens-Glières.",
         "https://www.fruitieres-chabert.com"),
        ("Auberge des Glières", "hebergement",
         "Hôtel 3★ sur le plateau des Glières.",
         "https://www.aubergedesglieres.fr/"),
    ],
    # 35. Plateau des Glières
    "plateau-des-glieres": [
        ("Chez Constance", "restaurant",
         "Restaurant d'alpage familial ouvert en 1974, célèbre pour ses crozets et galettes de pommes de terre. Menu 26 €.",
         "https://chez-constance.fr/"),
        ("Fruitière de Thorens-Glières (Fruitières Chabert)", "commerce",
         "Fromagerie coopérative Abondance AOP à Thorens-Glières.",
         "https://www.fruitieres-chabert.com"),
        ("Chez Constance", "hebergement",
         "Gîte-refuge familial sur le plateau, chambres et dortoirs (~70 lits).",
         "https://chez-constance.fr/"),
    ],
    # 36. Sentier des roselières — Saint-Jorioz
    "sentier-roselieres-saint-jorioz": [
        ("Chez Nous à la Plage", "restaurant",
         "Restaurant en bord de lac sur la piste cyclable à Saint-Jorioz, terrasse panoramique. Fév-1er nov.",
         "https://www.cheznousalaplage.com/"),
        ("Auberge Le Semnoz", "hebergement",
         "Hôtel-restaurant familial dans le parc des Bauges, route de Montagny à Saint-Jorioz.",
         "https://www.aubergelesemnoz.com/"),
    ],
    # 37. Wakepark Saint-Jorioz
    "wakepark-ponton-embarcadere-saint-jorioz": [
        ("Lac et Montagne", "restaurant",
         "Restaurant traditionnel en bord de lac près du port et de l'embarcadère.",
         "https://restaurant-lacetmontagne.com/"),
        ("Auberge Le Semnoz", "hebergement",
         "Hôtel-restaurant familial à Saint-Jorioz, route de Montagny.",
         "https://www.aubergelesemnoz.com/"),
    ],
    # 38. Sentier découverte plateau des Glières
    "sentier-decouverte-plateau-glieres-thorens-glieres": [
        ("Restaurant Gautard (chez Nathalie et Jean-Claude)", "restaurant",
         "Restaurant savoyard d'alpage accessible en voiture sur le plateau des Glières.",
         "https://restaurantgautard.fr/"),
        ("Fruitière de Thorens-Glières (Fruitières Chabert)", "commerce",
         "Fromagerie coopérative Abondance AOP à Thorens-Glières.",
         "https://www.fruitieres-chabert.com"),
        ("Gîte Chez Merlin", "hebergement",
         "Chalet-restaurant et gîte sur les pistes de ski de fond du plateau.",
         "https://www.gite-merlin-glieres.fr/"),
    ],
    # 39. Sentier des Espagnols — Glières
    "sentier-espagnols-pas-du-roc-glieres": [
        ("Chez Régina (Chalet l'Amandière)", "restaurant",
         "Bar-restaurant-gîte d'alpage ouvert été et hiver sur le plateau des Glières.",
         "https://www.chezregina.fr/"),
        ("Fruitière de Thorens-Glières (Fruitières Chabert)", "commerce",
         "Fromagerie coopérative Abondance AOP à Thorens-Glières.",
         "https://www.fruitieres-chabert.com"),
        ("Notre Dame des Neiges", "hebergement",
         "Chalet-refuge avec spécialités savoyardes, sur l'itinéraire ski de fond.",
         "https://www.gite-refuge-les-glieres.fr/"),
    ],
    # 40. Belvédère du Mont Baron
    "belvedere-du-mont-baron": [
        ("L'Auberge du Lac", "restaurant",
         "Restaurant en bord de lac à Veyrier-du-Lac, cuisine terroir et méditerranéenne.",
         "https://restaurant-aubergedulac.com/"),
        ("Maison Bleue – Yoann Conte", "hebergement",
         "Hôtel 5★ Relais & Châteaux indépendant, 11 chambres avec vue lac. Restaurant 2 étoiles Michelin sur place.",
         "https://yoann-conte.com/"),
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
