#!/usr/bin/env python3
"""
seed_batch2_partners.py — Phase 1.5 partner-card seeding (Batch 2, 40 venues).

Source: Research Report 1 (verified own-domain partners across Haute-Savoie
lake/resort venues). For each venue this script writes a 3-slot partners
array (restaurant / commerce / hebergement, in that order) into
Json/{slug}.json, leaving slots flagged "no qualifying business found" in the
research report as tier:invite cards with venue-parameterised copy.

The script is idempotent: re-running compares the existing partners array
against the target payload and only writes when they differ.

Special tier tags:
- Le Grenier de Châtel (Châtel shop) is the ONLY chain fallback in the report
  and is therefore seeded with tier:"recommended" rather than tier:"partner".
- Karting Team Bouvier (Pringy) has no qualifying business in any of the
  three slots, so all three are tier:invite.

After the JSON pass, this script also re-renders the FR HTML for each touched
slug via build_lieu_page.build_page and re-localises the en/de/it/es variants
via localize_lieu.localize (the latter has a hard-coded ROOT pointing at the
production tree, so we monkey-patch it onto the current working tree before
invocation — this keeps the run safe inside an isolated git worktree).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
JSON_DIR = REPO / "Json"
sys.path.insert(0, str(REPO / "scripts"))


def partner(ptype: str, name: str, domain: str, fr_desc: str) -> dict:
    """Build a tier:partner card (own-domain, independent)."""
    url = f"https://{domain.strip().lstrip('/')}/"
    return {
        "tier": "partner",
        "type": ptype,
        "name": name,
        "url": url,
        "i18n_placeholder": True,
        "i18n": {
            "fr": {"description": fr_desc},
            "en": {"description": fr_desc},
            "de": {"description": fr_desc},
            "it": {"description": fr_desc},
            "es": {"description": fr_desc},
        },
    }


def recommended(ptype: str, name: str, domain: str, fr_desc: str) -> dict:
    """Build a tier:recommended card (chain fallback)."""
    card = partner(ptype, name, domain, fr_desc)
    card["tier"] = "recommended"
    return card


def invite(invite_type: str, title: str, desc: str) -> dict:
    """Build a tier:invite card for an empty slot."""
    return {
        "tier": "invite",
        "invite_type": invite_type,
        "i18n": {"fr": {"title": title, "desc": desc}},
    }


# Reusable anchor businesses (Annecy shared, Talloires shared, Sciez shared,
# Thonon shared, Morzine shared). Descriptions are factual 1–2-sentence FR.

FROMAGERIE_GAY = lambda d: partner(
    "commerce",
    "Fromagerie Gay",
    "fromagerie-gay.fr",
    "Fromagerie-affineur indépendante (Pierre Gay, MOF 2011), 47 rue Carnot "
    "à Annecy. Maison familiale 3e génération depuis 1935, caves d'affinage "
    "sous le château. " + d,
)

HOTEL_MARQUISATS = lambda d: partner(
    "hebergement",
    "Hôtel des Marquisats***",
    "hoteldesmarquisats.com",
    "Hôtel 3 étoiles indépendant au bord du lac, rue des Marquisats à "
    "Annecy. Espace bien-être avec hammam. " + d,
)

BEAU_SITE = lambda d: partner(
    "hebergement",
    "Beau Site Talloires***",
    "beausite-talloires.com",
    "Hôtel de charme indépendant avec plage privée, 118 rue André Theuriet "
    "à Talloires. " + d,
)

BEAU_SITE_REST = lambda d: partner(
    "restaurant",
    "Beau Site Talloires — La Table du B.",
    "beausite-talloires.com",
    "Restaurant Maître Restaurateur avec terrasse face au lac, 118 rue "
    "André Theuriet à Talloires. " + d,
)

COUDREE_REST = lambda d: partner(
    "restaurant",
    "Château de Coudrée — Restaurant François Ier",
    "chateau-hotel-coudree.com",
    "Restaurant gastronomique dans un château du XIIe siècle au bord du "
    "Léman, avenue de Coudrée à Sciez. 3 toques Gault&Millau. " + d,
)

COUDREE_HOTEL = lambda d: partner(
    "hebergement",
    "Château de Coudrée****",
    "chateau-hotel-coudree.com",
    "Hôtel 4 étoiles indépendant dans un château du XIIe siècle avec plage "
    "privée, avenue de Coudrée à Sciez. " + d,
)

PANORAMA_REST = lambda d: partner(
    "restaurant",
    "Hôtel Le Panorama — Restaurant",
    "hotellepanorama.com",
    "Restaurant d'hôtel indépendant à Thonon-les-Bains. " + d,
)

PANORAMA_HOTEL = lambda d: partner(
    "hebergement",
    "Hôtel Le Panorama",
    "hotellepanorama.com",
    "Hôtel indépendant à Thonon-les-Bains, proche du lac et du château de "
    "Ripaille. " + d,
)

FROMAGERIE_NOYER_THONON = lambda d: partner(
    "commerce",
    "Fromagerie du Noyer",
    "fromageriedunoyer.fr",
    "Fromagerie-affineur indépendante (depuis 1996), 8 Grande Rue à "
    "Thonon-les-Bains. Plus de 80 % de produits savoyards et suisses "
    "locaux. " + d,
)

FROMAGERIE_NOYER_MORZINE = lambda d: partner(
    "commerce",
    "Fromagerie du Noyer",
    "fromageriedunoyer.fr",
    "Fromagerie indépendante au 9 Rond-point de la Crusaz à Morzine. "
    "Fromages et produits locaux. " + d,
)

ALPEN_ROC_REST = lambda d: partner(
    "restaurant",
    "Hôtel Alpen Roc — Restaurant",
    "alpenroc.com",
    "Restaurant d'hôtel indépendant au centre de Morzine, à 300 m des "
    "remontées du Pléney. " + d,
)

ALPEN_ROC_HOTEL = lambda d: partner(
    "hebergement",
    "Hôtel Alpen Roc",
    "alpenroc.com",
    "Hôtel indépendant au centre de Morzine, à 300 m des remontées du "
    "Pléney. " + d,
)


# Per-venue payloads. Each entry is (slug, [restaurant, commerce, hebergement]).
VENUES: list[tuple[str, list[dict]]] = [
    # ---------- ANNECY (1–9) ----------
    ("base-nautique-marquisats-annecy", [
        invite("restaurant",
               "Un restaurant à Annecy ?",
               "Vous accueillez les visiteurs de la Base nautique des Marquisats ? Apparaissez ici."),
        FROMAGERIE_GAY("À 15 min dans la vieille ville."),
        HOTEL_MARQUISATS("Adjacent, sur la rive sud du lac."),
    ]),
    ("casino-imperial-palace-annecy", [
        invite("restaurant",
               "Un restaurant à Annecy ?",
               "Vous accueillez les visiteurs du Casino Impérial Palace ? Apparaissez ici."),
        FROMAGERIE_GAY("À 15 min du casino."),
        HOTEL_MARQUISATS("À 10 min le long du lac."),
    ]),
    ("musee-chateau-annecy", [
        invite("restaurant",
               "Un restaurant à Annecy ?",
               "Vous accueillez les visiteurs du Musée-Château d'Annecy ? Apparaissez ici."),
        FROMAGERIE_GAY("Adjacente, dans la vieille ville en contrebas du château."),
        HOTEL_MARQUISATS("À 10 min à pied."),
    ]),
    ("croisiere-bateaux-annecy-annecy", [
        invite("restaurant",
               "Un restaurant à Annecy ?",
               "Vous accueillez les visiteurs des croisières sur le lac ? Apparaissez ici."),
        FROMAGERIE_GAY("À 10 min de l'embarcadère."),
        HOTEL_MARQUISATS("À 10 min de l'embarcadère."),
    ]),
    ("grp-tour-lac-annecy-annecy", [
        invite("restaurant",
               "Un restaurant à Annecy ?",
               "Vous accueillez les randonneurs du Tour du Lac ? Apparaissez ici."),
        FROMAGERIE_GAY("Au point de départ annécien du sentier."),
        HOTEL_MARQUISATS("Sur la portion lacustre de la boucle."),
    ]),
    ("karting-team-bouvier-pringy", [
        invite("restaurant",
               "Un restaurant à Pringy ?",
               "Vous accueillez les visiteurs du Karting Team Bouvier ? Apparaissez ici."),
        invite("commerce",
               "Un commerce à Pringy ?",
               "Partagez horaires et spécialités avec les visiteurs du Karting Team Bouvier."),
        invite("hebergement",
               "Un hébergement proche ?",
               "Gîte, chambre d'hôtes, camping, location à Pringy."),
    ]),
    ("musee-cinema-animation-annecy", [
        invite("restaurant",
               "Un restaurant à Annecy ?",
               "Vous accueillez les visiteurs du Musée du film d'animation ? Apparaissez ici."),
        FROMAGERIE_GAY("À 10 min du musée."),
        HOTEL_MARQUISATS("À 10 min."),
    ]),
    ("plage-imperial-annecy", [
        invite("restaurant",
               "Un restaurant à Annecy ?",
               "Vous accueillez les visiteurs de la Plage de l'Impérial ? Apparaissez ici."),
        FROMAGERIE_GAY("À 15 min de la plage."),
        HOTEL_MARQUISATS("Adjacent, quelques minutes à pied."),
    ]),
    ("voie-verte-lac-annecy-annecy", [
        invite("restaurant",
               "Un restaurant à Annecy ?",
               "Vous accueillez les visiteurs de la Voie verte ? Apparaissez ici."),
        FROMAGERIE_GAY("Près de l'accès annécien de la voie verte."),
        HOTEL_MARQUISATS("La voie verte longe la rive sud à côté de l'hôtel."),
    ]),

    # ---------- DOUSSARD (10–12) ----------
    ("base-nautique-doussard-doussard", [
        partner("restaurant", "La Playa", "playa-doussard.com",
                "Restaurant de plage au bord du lac, sur la Plage de "
                "Doussard. Adjacent à la base nautique."),
        partner("commerce", "Les Halles de Doussard", "leshallesdedoussard.fr",
                "Halles indépendantes en circuit court (boucherie, "
                "fromagerie, primeur, traiteur), 98 rue de Macherine à "
                "Doussard. À environ 2 km."),
        partner("hebergement", "Camping La Ferme de la Serraz*****",
                "lafermedelaserraz.com",
                "Camping 5 étoiles indépendant à Doussard, à environ 2 km "
                "de la rive du lac."),
    ]),
    ("plage-de-doussard", [
        partner("restaurant", "La Playa", "playa-doussard.com",
                "Restaurant de plage au bord du lac, sur la Plage de "
                "Doussard. Sur place."),
        partner("commerce", "Les Halles de Doussard", "leshallesdedoussard.fr",
                "Halles indépendantes en circuit court (boucherie, "
                "fromagerie, primeur, traiteur), 98 rue de Macherine. "
                "À environ 2 km."),
        partner("hebergement", "Camping La Ferme de la Serraz*****",
                "lafermedelaserraz.com",
                "Camping 5 étoiles indépendant à Doussard, à environ 2 km."),
    ]),
    ("sentier-bout-du-lac-doussard", [
        partner("restaurant", "La Playa", "playa-doussard.com",
                "Restaurant de plage au bord du lac, près de la réserve "
                "et de la plage de Doussard."),
        partner("commerce", "Les Halles de Doussard", "leshallesdedoussard.fr",
                "Halles indépendantes en circuit court (boucherie, "
                "fromagerie, primeur, traiteur), 98 rue de Macherine. "
                "À environ 2 km."),
        partner("hebergement", "Camping La Ferme de la Serraz*****",
                "lafermedelaserraz.com",
                "Camping 5 étoiles indépendant à Doussard, à environ 2 km."),
    ]),

    # ---------- DUINGT (13) ----------
    ("plage-de-duingt", [
        partner("restaurant", "Restaurant Lisca",
                "lisca-restaurant.fr",
                "Restaurant de l'Hôtel Villa Caroline (cuisine fraîche et "
                "de saison), 624 route d'Annecy à Duingt. Au bord du lac."),
        invite("commerce",
               "Un commerce à Duingt ?",
               "Partagez horaires et spécialités avec les visiteurs de la Plage de Duingt."),
        partner("hebergement", "Hôtel Villa Caroline****",
                "villa-caroline.com",
                "Hôtel 4 étoiles indépendant au bord du lac avec plage "
                "privée, 624 route d'Annecy à Duingt."),
    ]),

    # ---------- SEVRIER (14) ----------
    ("bowling-sevrier-sevrier", [
        partner("restaurant",
                "Hôtel Beauregard — La Boussole / L'Ouvr'Boitte",
                "hotel-beauregard.com",
                "Restaurant bistronomique au bord du lac, 691 route "
                "d'Albertville à Sevrier."),
        partner("commerce", "Les Halles de Sevrier",
                "leshallesdesevrier.com",
                "Halles indépendantes en circuit court (boucherie-"
                "charcuterie, fromagerie, primeur, traiteur), 51 place de "
                "la Mairie à Sévrier."),
        partner("hebergement",
                "Hôtel Beauregard, The Originals Relais***",
                "hotel-beauregard.com",
                "Hôtel indépendant au bord du lac avec piscine et "
                "terrasse bien-être, 691 route d'Albertville à Sevrier."),
    ]),

    # ---------- TALLOIRES-MONTMIN (15–20) ----------
    ("acro-aventures-talloires", [
        BEAU_SITE_REST("Au village de Talloires."),
        invite("commerce",
               "Un commerce à Talloires ?",
               "Partagez horaires et spécialités avec les visiteurs d'Acro'Aventures Talloires."),
        BEAU_SITE("Au village."),
    ]),
    ("cascade-d-angon", [
        BEAU_SITE_REST("Près du départ du sentier de la cascade."),
        invite("commerce",
               "Un commerce à Talloires ?",
               "Partagez horaires et spécialités avec les visiteurs de la Cascade d'Angon."),
        BEAU_SITE("Près du secteur d'Angon."),
    ]),
    ("col-de-la-forclaz", [
        partner("restaurant", "Le Balcon du Lac",
                "lebalcondulac-annecy.com",
                "Brasserie-restaurant avec terrasse panoramique sur le lac "
                "au col de la Forclaz (1 147 m), à Talloires-Montmin. Sur place."),
        invite("commerce",
               "Un commerce au col de la Forclaz ?",
               "Partagez horaires et spécialités avec les visiteurs du col de la Forclaz."),
        BEAU_SITE("À environ 10 min en descendant vers le lac."),
    ]),
    ("plage-d-angon-talloires", [
        BEAU_SITE_REST("À proximité d'Angon."),
        invite("commerce",
               "Un commerce à Talloires ?",
               "Partagez horaires et spécialités avec les visiteurs de la Plage d'Angon."),
        BEAU_SITE("Près d'Angon."),
    ]),
    ("plage-de-talloires", [
        partner("restaurant", "Auberge du Père Bise — Jean Sulpice",
                "perebise.com",
                "Restaurant gastronomique 2 étoiles Michelin au bord du "
                "lac, 303 route du Port à Talloires-Montmin. Adjacent à "
                "la baie."),
        invite("commerce",
               "Un commerce à Talloires ?",
               "Partagez horaires et spécialités avec les visiteurs de la Plage de Talloires."),
        partner("hebergement", "Abbaye de Talloires****",
                "abbaye-talloires.com",
                "Hôtel 4 étoiles indépendant dans l'ancienne abbaye, "
                "ponton privé sur la baie de Talloires."),
    ]),
    ("sentier-tournette-montmin", [
        partner("restaurant", "L'Auberge de Montmin",
                "aubergedemontmin.com",
                "Maison de cuisine 2 étoiles Michelin (chef Florian "
                "Favario, ouverte en 2019), au col de la Forclaz à "
                "Talloires-Montmin. Près de l'accès Montmin/Forclaz."),
        invite("commerce",
               "Un commerce à Montmin ?",
               "Partagez horaires et spécialités avec les randonneurs de la Tournette."),
        invite("hebergement",
               "Un hébergement proche ?",
               "Gîte, chambre d'hôtes, camping, location près du sentier de la Tournette."),
    ]),

    # ---------- CHÂTEL (21) ----------
    ("telecabine-super-chatel", [
        partner("restaurant",
                "Hôtel & Restaurant L'Escale",
                "escalechatel.com",
                "Hôtel-restaurant ski-in/ski-out à l'arrivée de la "
                "télécabine, cuisine bistronomique maison. 1 Super-Châtel, "
                "74390 Châtel."),
        recommended("commerce",
                    "Le Grenier de Châtel",
                    "grenier-chatel.com",
                    "Boutique de produits régionaux (fromages, charcuterie, "
                    "vins locaux) fondée en 1972, 207 route du Linga à "
                    "Châtel. Appartient au groupe Grenier Savoyard (4 "
                    "boutiques) — recommandé en l'absence d'enseigne "
                    "indépendante locale."),
        partner("hebergement", "Hôtel Macchi****",
                "hotelmacchi.com",
                "Hôtel-chalet 4 étoiles indépendant avec spa ayurvédique, "
                "à 200 m de la télécabine de Super-Châtel."),
    ]),

    # ---------- LES GETS (22–23) ----------
    ("telecabine-des-chavannes-les-gets", [
        partner("restaurant", "La Croix Blanche",
                "croixblanchehotel.com",
                "Restaurant chalet savoyard ski-in/ski-out via le Chavannes "
                "Express, 3973 route des Chavannes aux Gets."),
        partner("commerce", "Le Traîneau",
                "letraineau-lesgets.com",
                "Épicerie fine et produits régionaux indépendante "
                "(fromages de Savoie, charcuterie, vins), 260 rue du Centre "
                "aux Gets."),
        partner("hebergement", "La Croix Blanche",
                "croixblanchehotel.com",
                "Hôtel-boutique familial indépendant sur le plateau des "
                "Chavannes, 3973 route des Chavannes aux Gets."),
    ]),
    ("telecabine-du-mont-chery-les-gets", [
        partner("restaurant", "La Fruitière des Perrières",
                "fruitiere-lesgets.com",
                "Fromagerie-restaurant proposant des spécialités savoyardes "
                "en caves voûtées, 137 route des Perrières aux Gets. "
                "Près du départ du Mont-Chéry."),
        partner("commerce", "La Fruitière des Perrières",
                "fruitiere-lesgets.com",
                "Fromagerie fermière indépendante (Abondance, Tomme des "
                "Gets, raclette) avec production sur place, 137 route des "
                "Perrières aux Gets."),
        invite("hebergement",
               "Un hébergement proche ?",
               "Gîte, chambre d'hôtes, camping, location aux Gets."),
    ]),

    # ---------- MORZINE / AVORIAZ (24–28) ----------
    ("aquariaz", [
        partner("restaurant", "Le Petit Dru",
                "lepetitdru.com",
                "Hôtel-restaurant 4 étoiles à Avoriaz, près d'Aquariaz."),
        invite("commerce",
               "Un commerce à Avoriaz ?",
               "Partagez horaires et spécialités avec les visiteurs d'Aquariaz."),
        partner("hebergement", "Le Petit Dru****",
                "lepetitdru.com",
                "Hôtel 4 étoiles indépendant à Avoriaz avec espace "
                "détente et magasin de location de skis."),
    ]),
    ("cascade-aventure", [
        ALPEN_ROC_REST("À proximité de Cascade Aventure."),
        FROMAGERIE_NOYER_MORZINE("Au village."),
        ALPEN_ROC_HOTEL(""),
    ]),
    ("cascade-de-nyon", [
        ALPEN_ROC_REST("Au village."),
        FROMAGERIE_NOYER_MORZINE("Au village."),
        partner("hebergement", "Hôtel Le Sporting",
                "hotelsporting-morzine.com",
                "Hôtel indépendant à Morzine, au pied des pistes."),
    ]),
    ("parc-des-dereches", [
        ALPEN_ROC_REST("Près du parc."),
        FROMAGERIE_NOYER_MORZINE("Au village."),
        ALPEN_ROC_HOTEL("Près des Dérêches."),
    ]),
    ("telecabine-pleney-morzine", [
        ALPEN_ROC_REST("Adjacent, à 300 m du Pléney."),
        partner("commerce", "Pleney Sports",
                "pleney-sports.com",
                "Magasin de location de ski indépendant (depuis 1938), "
                "route du téléphérique à Morzine, à 50 m de la télécabine "
                "du Pléney."),
        partner("hebergement", "Hôtel Le Sporting",
                "hotelsporting-morzine.com",
                "Hôtel indépendant à Morzine, au pied des pistes."),
    ]),

    # ---------- SCIEZ (29–33) ----------
    ("base-nautique-sciez-sciez", [
        COUDREE_REST("À proximité, sur le domaine de Coudrée."),
        invite("commerce",
               "Un commerce à Sciez ?",
               "Partagez horaires et spécialités avec les visiteurs de la base nautique de Sciez."),
        COUDREE_HOTEL("Au bord du lac."),
    ]),
    ("domaine-de-guidou", [
        COUDREE_REST("À proximité, au bord du lac."),
        invite("commerce",
               "Un commerce à Sciez ?",
               "Partagez horaires et spécialités avec les visiteurs du Domaine de Guidou."),
        COUDREE_HOTEL(""),
    ]),
    ("les-aigles-du-leman", [
        COUDREE_REST("À courte distance en voiture."),
        invite("commerce",
               "Un commerce à Sciez ?",
               "Partagez horaires et spécialités avec les visiteurs des Aigles du Léman."),
        COUDREE_HOTEL(""),
    ]),
    ("parcours-aventure-de-sciez", [
        COUDREE_REST("À proximité."),
        invite("commerce",
               "Un commerce à Sciez ?",
               "Partagez horaires et spécialités avec les visiteurs du Parcours Aventure de Sciez."),
        COUDREE_HOTEL(""),
    ]),
    ("plage-de-sciez-sur-leman", [
        COUDREE_REST("Sur le domaine de Coudrée, adjacent à la plage."),
        invite("commerce",
               "Un commerce à Sciez ?",
               "Partagez horaires et spécialités avec les visiteurs de la Plage de Sciez."),
        COUDREE_HOTEL("Adjacent à la plage."),
    ]),

    # ---------- THONON (34–40) ----------
    ("aquaparc-thonon-piscine-olympique-thonon", [
        PANORAMA_REST("Proche du lac et de Ripaille."),
        FROMAGERIE_NOYER_THONON("Au centre-ville."),
        PANORAMA_HOTEL("Proche du lac."),
    ]),
    ("chateau-bellegarde-thonon", [
        PANORAMA_REST("En ville."),
        FROMAGERIE_NOYER_THONON("Au centre-ville."),
        PANORAMA_HOTEL(""),
    ]),
    ("chateau-ripaille-thonon", [
        PANORAMA_REST("Présenté comme proche du château de Ripaille."),
        FROMAGERIE_NOYER_THONON("Au centre-ville."),
        PANORAMA_HOTEL("Proche de Ripaille."),
    ]),
    ("croisiere-cgn-thonon", [
        PANORAMA_REST("En ville, près du lac."),
        FROMAGERIE_NOYER_THONON("Au centre-ville."),
        PANORAMA_HOTEL(""),
    ]),
    ("ecomusee-peche-et-du-lac-thonon", [
        PANORAMA_REST("Près du lac et du Port de Rives."),
        FROMAGERIE_NOYER_THONON("Au centre-ville."),
        PANORAMA_HOTEL(""),
    ]),
    ("leman-kid-thonon-les-bains", [
        PANORAMA_REST("En ville."),
        FROMAGERIE_NOYER_THONON("Au centre-ville."),
        PANORAMA_HOTEL(""),
    ]),
    ("musee-du-chablais-thonon-les-bains", [
        PANORAMA_REST("En ville."),
        FROMAGERIE_NOYER_THONON("Au centre-ville, près du vieux Thonon."),
        PANORAMA_HOTEL(""),
    ]),
]


def main() -> None:
    updated_json = 0
    rerendered = 0
    skipped = 0
    seen_slugs: set[str] = set()

    # Phase 1 — write JSON
    for slug, partners in VENUES:
        if slug in seen_slugs:
            raise RuntimeError(f"Duplicate slug in VENUES: {slug}")
        seen_slugs.add(slug)
        path = JSON_DIR / f"{slug}.json"
        if not path.exists():
            raise FileNotFoundError(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        current = data.get("partners") or []
        if current == partners:
            skipped += 1
        else:
            data["partners"] = partners
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            updated_json += 1

    if len(seen_slugs) != 40:
        raise RuntimeError(
            f"Expected 40 venues, got {len(seen_slugs)} — check VENUES list."
        )

    # Phase 2 — re-render FR HTML via build_lieu_page.build_page
    from build_lieu_page import build_page  # noqa: E402

    for slug, _ in VENUES:
        data = json.loads((JSON_DIR / f"{slug}.json").read_text(encoding="utf-8"))
        html = build_page(data)
        (REPO / f"{slug}.html").write_text(html, encoding="utf-8")
        rerendered += 1

    # Phase 3 — re-localise en/de/it/es using localize_lieu, but pointed at the
    # current working tree (the script has a hard-coded production ROOT).
    import localize_lieu  # noqa: E402

    localize_lieu.ROOT = REPO
    localize_lieu._hf_cache.clear()
    relocalized = 0
    for slug, _ in VENUES:
        fr_html = (REPO / f"{slug}.html").read_text(encoding="utf-8")
        for lang in localize_lieu.LANGS:
            out = localize_lieu.localize(fr_html, lang, slug)
            (REPO / lang).mkdir(exist_ok=True)
            (REPO / lang / f"{slug}.html").write_text(out, encoding="utf-8")
        relocalized += 1

    print(
        f"seed_batch2_partners: JSON updated={updated_json} "
        f"skipped(idempotent)={skipped} FR HTML re-rendered={rerendered} "
        f"locales(en/de/it/es) re-rendered={relocalized * len(localize_lieu.LANGS)} "
        f"venues_total={len(seen_slugs)}"
    )


if __name__ == "__main__":
    main()
