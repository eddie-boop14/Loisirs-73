#!/usr/bin/env python3
"""pick_generique.py — pick the best `generique-*.jpg` variant per fiche.

The repo root carries 75 `generique-*.jpg` variants (sentier-foret-alpine,
escape-game-neon, voie-verte-cyclistes-lac, atelier-poterie-mains, etc.).
The renderer (build_lieu_page.py:865) already supports per-fiche
`hero_image: "generique-<variant>.jpg"` overrides, but only 9 of the 75
variants are reachable via the default category-keyed fallback.

This script reads each fiche's `category`, `facts.type`, and `body.what_is`
(FR) and assigns the best variant. Idempotent and deterministic.

Skips fiches whose `hero_image` is a real photo URL (http/https or any
path-style string that isn't a `generique-*.jpg` filename).
"""
import datetime
import glob
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSON_DIR = ROOT / "Json"
TODAY = datetime.date.today().isoformat()


CANON = "/img/generique/"


def variants_on_disk():
    """Return the set of `generique-*.jpg` basenames at the canonical
    location.

    Post-Phase-1-consolidation: every shared generic lives at
    `img/generique/<file>`. Real per-lieu heros stay at
    `img/<hub>/<slug>-hero.jpg` and are routed by the build chain, not
    by this picker.
    """
    return {p.name for p in (ROOT / "img" / "generique").glob("generique-*.jpg")}


def _path_for(fiche, chosen):
    """Build the canonical /img/generique/<chosen> path. Shared art has
    no single 'category' to belong to, so the canonical store is flat.
    Real per-lieu heros stay at /img/<hub>/<slug>-hero.jpg and aren't
    routed through this function."""
    return f"{CANON}{chosen}"


VARIANTS = variants_on_disk()


def has(name):
    return name in VARIANTS


def slug_pick(slug, choices):
    """Deterministic round-robin pick from `choices` based on slug hash."""
    if not choices:
        return None
    h = int(hashlib.md5(slug.encode("utf-8")).hexdigest(), 16)
    return choices[h % len(choices)]


def _pool(slug, prefix, n):
    """Return the slug's deterministic pick from `{prefix}{1..n}.jpg`,
    filtered to files actually present on disk. Used by hero-pack
    routing for the new buckets (plage-lac, accrobranche, canyoning,
    reserve-zone-humide, chiens-de-traineau, alpine-coaster).
    Returns None if no files in the pool exist."""
    choices = [f"{prefix}{i}.jpg" for i in range(1, n + 1) if has(f"{prefix}{i}.jpg")]
    return slug_pick(slug, choices) if choices else None


def pick_text_override(slug, text, cat=""):
    """Cross-category text and slug rules — fire BEFORE category dispatch
    so fiches MIS-classified (a parc aventure filed as 'domaine', a
    dog-sled kennel filed as 'attraction', a réserve sentier filed as
    'sentier' but legitimately wetland) reach the right pool.

    Slug pre-checks (FIRST — unambiguous): the slug alone identifies
    the family.

    Text-keyword rules: gated to cat ∈ {attraction, divers, ''} so a
    well-categorised fiche keeps its category-branch routing — a plage
    that name-drops an adjacent réserve doesn't get a wetland image,
    and a sentier through a réserve stays on the sentier family.
    """
    # ---- SLUG pre-checks (always run) ----
    if slug.startswith("chiens-de-traineau-"):
        return _pool(slug, "generique-chiens-de-traineau-", 2)
    if any(slug.startswith(p) for p in (
        "accrobranche-", "acroparc-", "acro-aventures-",
        "parcours-aventure-", "indiana-ventures-",
        "chatel-accrobranche-", "cote-2000-aventure-",
        "passy-accro-", "tactiq-aventure-", "leman-forest-",
    )):
        pool = _pool(slug, "generique-accrobranche-", 12)
        if pool:
            return pool
    if slug.startswith("base-de-loisirs-"):
        pool = _pool(slug, "generique-plage-lac-", 15)
        if pool:
            return pool
    # base-nautique-* and port-* (with "base nautique" in the slug)
    # paddle/voile/port pool, regardless of upstream category.
    if slug.startswith("base-nautique-") or "base-nautique-" in slug:
        choices = [v for v in ["generique-paddle-aviron-detail.jpg",
                                "generique-barque-aviron.jpg",
                                "generique-port-annecy.jpg",
                                "generique-voile-sunset-1.jpg"] if has(v)]
        pick = slug_pick(slug, choices)
        if pick:
            return pick
    # Spéléologie — cat usually 'attraction' which already calls
    # pick_attraction, but a slug check guarantees it fires.
    if slug.startswith("speleo-"):
        choices = [v for v in ["generique-grotte-cathedrale.jpg",
                                "generique-grotte-lumiere.jpg"] if has(v)]
        pick = slug_pick(slug, choices)
        if pick:
            return pick
    # Baignade biologique / biotope
    if slug.startswith("baignade-"):
        pool = _pool(slug, "generique-plage-lac-", 15)
        if pool:
            return pool
    # VR centers filed as 'parc' upstream — facts.type/name is
    # unambiguous so always-fire.
    if slug.startswith(("ereel-", "vr-")):
        choices = [v for v in ["generique-vr-immersion.jpg",
                                "generique-vr-multi-joueurs.jpg"] if has(v)]
        pick = slug_pick(slug, choices)
        if pick:
            return pick
    # Château ruins/remparts filed upstream as cat='musee' — facts.type
    # says château fort but the museum category routes to a museum
    # photo. Route on slug instead.
    if any(s in slug for s in ("ruines-chateau-", "bourg-et-ruines-chateau-",
                                "ancien-remparts-chateau-",
                                "chateau-comtal-")):
        choices = [v for v in ["generique-chateau-brume.jpg",
                                "generique-chateau.jpg",
                                "generique-chateau-toiture.jpg"] if has(v)]
        if choices:
            return slug_pick(slug, choices)
    # Vitam Neydens — multi-space leisure complex (aquaparc + spa +
    # sport). The handoff calls this out specifically: aquatique-
    # toboggan, not the generic park photo. Slug pre-check ensures the
    # rule fires regardless of category (filed as 'parc' upstream).
    if slug == "vitam-neydens" and has("generique-aquatique-toboggan.jpg"):
        return "generique-aquatique-toboggan.jpg"

    # ---- TEXT rules — only when the category is ambiguous ----
    if cat not in ("", None, "attraction", "divers"):
        return None

    # most-specific → broad
    if match_any(text, ["chiens de traîneau", "chiens de traineau",
                        "traîneau", "traineau", "mushing", "attelage de chiens"]):
        return _pool(slug, "generique-chiens-de-traineau-", 2)
    if match_any(text, ["luge sur rails", "luge sur rail", "alpine coaster",
                        "dévalkart", "devalkart", "toboggan sur rails",
                        "débaroule", "debaroule"]):
        return _pool(slug, "generique-alpine-coaster-", 2)
    if match_any(text, ["accrobranche", "parc accrobranche",
                        "parc aventure", "parcours aventure",
                        "arbre en arbre", "tyrolienne géante",
                        "parcabout"]):
        pool = _pool(slug, "generique-accrobranche-", 12)
        if pool:
            return pool
    if match_any(text, ["réserve naturelle", "reserve naturelle", "natura 2000",
                        "marais", "roselière", "roseliere", "zone humide",
                        "tourbière", "tourbiere"]):
        return _pool(slug, "generique-reserve-zone-humide-", 8)
    if "centre de loisirs multi-espaces" in text and has("generique-aquatique-toboggan.jpg"):
        return "generique-aquatique-toboggan.jpg"
    return None


def fr_text(fiche):
    """Concatenated FR prose used for MOOD/SEASON sub-pickers only.

    DO NOT use this for theme-family selection — it includes body.what_is,
    hero.lead, etc., which mention OTHER activities the venue happens to
    name-drop (réserve naturelle on a via ferrata page, spa on a jardin
    page, escalade on a trampoline page, …). That contamination is what
    the prose-keyword bug was. Family decisions must use type_text().
    """
    fr = (fiche.get("i18n") or {}).get("fr") or {}
    body = fr.get("body") or {}
    facts = fr.get("facts") or {}
    parts = [
        str(facts.get("type") or ""),
        str(facts.get("access") or ""),
        str(facts.get("best_season") or ""),
        str(fr.get("name") or ""),
        str(body.get("what_is") or ""),
        str(fr.get("hero", {}).get("lead") if isinstance(fr.get("hero"), dict) else "") or "",
        str(fr.get("hero", {}).get("badge") if isinstance(fr.get("hero"), dict) else "") or "",
    ]
    return " ".join(parts).lower()


def type_text(fiche):
    """Family-selection text — facts.type + name only.

    The keyword-match blob used for THEME decisions (override pools,
    category-branch routing, sub-family choice). Excludes body prose
    because the prose mentions other activities the venue advertises
    or sits next to — which would route the hero to the wrong family.
    """
    fr = (fiche.get("i18n") or {}).get("fr") or {}
    facts = fr.get("facts") or {}
    return " ".join([
        str(facts.get("type") or ""),
        str(fr.get("name") or ""),
    ]).lower()


def match_any(text, words):
    return any(w in text for w in words)


def pick_sentier(slug, text, flavour=""):
    """Sentier mood sub-picker. Family is already 'sentier' (correct).
    All branches here switch MOOD/SEASON only — winter snow vs autumn
    foliage vs alpine ridge vs forest. The handoff allows prose
    (flavour) for season hints because season doesn't switch family.
    Match on flavour when present, fall back to text."""
    blob = (flavour + " " + text) if flavour else text
    if match_any(blob, ["hiver", "neige", "raquette", "ski de fond"]):
        if has("generique-sentier-hiver-neige.jpg"):
            return "generique-sentier-hiver-neige.jpg"
    if match_any(blob, ["automne", "mélèze", "melèze", "couleur"]):
        if has("generique-sentier-melezes-automne.jpg") and match_any(blob, ["mélèze", "melèze"]):
            return "generique-sentier-melezes-automne.jpg"
        for f in ("generique-sentier-automne-rouge.jpg", "generique-sentier-automne-orange.jpg"):
            if has(f):
                return slug_pick(slug, [
                    x for x in ["generique-sentier-automne-rouge.jpg",
                                "generique-sentier-automne-orange.jpg"]
                    if has(x)
                ])
    if match_any(blob, ["arête", "arete"]):
        if has("generique-sentier-arete-alpine.jpg"):
            return "generique-sentier-arete-alpine.jpg"
    if match_any(blob, ["sommet", "panorama", "vue", "belvédère", "belvedere"]):
        if has("generique-sentier-sommet-panorama.jpg"):
            return "generique-sentier-sommet-panorama.jpg"
    if match_any(blob, ["alpin", "alpine", "haute montagne", "altitude"]):
        if has("generique-sentier-foret-alpine.jpg"):
            return "generique-sentier-foret-alpine.jpg"
    if match_any(blob, ["brouillard", "brume", "fog"]):
        if has("generique-sentier-fog.jpg"):
            return "generique-sentier-fog.jpg"
    if match_any(blob, ["forêt", "foret", "bois", "sapin", "épicéa", "epicea"]):
        if has("generique-sentier-foret.jpg"):
            return "generique-sentier-foret.jpg"
    return "generique-sentier-foret.jpg" if has("generique-sentier-foret.jpg") else "generique-sentier.jpg"


def pick_voie_verte(slug, text):
    if match_any(text, ["famille", "enfant", "kids", "poussette"]):
        if has("generique-voie-verte-famille-kids.jpg"):
            return "generique-voie-verte-famille-kids.jpg"
    if match_any(text, ["lac"]):
        if has("generique-voie-verte-cyclistes-lac.jpg"):
            return "generique-voie-verte-cyclistes-lac.jpg"
    if match_any(text, ["rivière", "riviere", "fleuve", "torrent", "arve", "giffre"]):
        if has("generique-voie-verte-cyclistes-riviere.jpg"):
            return "generique-voie-verte-cyclistes-riviere.jpg"
    if match_any(text, ["ville", "urbain"]):
        if has("generique-voie-verte-urbaine.jpg"):
            return "generique-voie-verte-urbaine.jpg"
    if match_any(text, ["forêt", "foret", "bois"]):
        if has("generique-voie-verte-foret.jpg"):
            return "generique-voie-verte-foret.jpg"
    return "generique-voie-verte.jpg"


def pick_musee(slug, text):
    if match_any(text, ["art moderne", "art contemporain", "contemporain"]):
        if has("generique-musee-moderne.jpg"):
            return "generique-musee-moderne.jpg"
    if match_any(text, ["grande galerie", "beaux-arts", "beaux arts", "paysages alpins"]):
        if has("generique-musee-grande-galerie.jpg"):
            return "generique-musee-grande-galerie.jpg"
    if match_any(text, ["histoire", "régional", "regional", "folklore",
                        "ethnographie", "ethnographique", "patrimoine local"]):
        if has("generique-musee-classique.jpg"):
            return "generique-musee-classique.jpg"
    # round-robin across the 4 musee variants for diversity
    choices = [v for v in ["generique-musee.jpg", "generique-musee-classique.jpg",
                            "generique-musee-grande-galerie.jpg", "generique-musee-moderne.jpg"]
               if has(v)]
    return slug_pick(slug, choices) or "generique-musee.jpg"


def pick_chateau(slug, text):
    if match_any(text, ["ruine", "vestige", "ancien château", "brume"]):
        if has("generique-chateau-brume.jpg"):
            return "generique-chateau-brume.jpg"
    choices = [v for v in ["generique-chateau.jpg", "generique-chateau-toiture.jpg",
                            "generique-chateau-brume.jpg"] if has(v)]
    return slug_pick(slug, choices) or "generique-chateau.jpg"


def pick_lac(slug, text, flavour=""):
    """Family already 'lac'. Sunset vs default is a mood choice — prose
    (flavour) is allowed for that sub-pick."""
    choices = [v for v in ["generique-lac.jpg", "generique-lac-coucher-soleil.jpg"]
               if has(v)]
    blob = (flavour + " " + text) if flavour else text
    if match_any(blob, ["coucher", "couchant", "crépuscule", "crepuscule"]):
        if has("generique-lac-coucher-soleil.jpg"):
            return "generique-lac-coucher-soleil.jpg"
    return slug_pick(slug, choices) or "generique-lac.jpg"


def pick_aquaparc(slug, text):
    if match_any(text, ["toboggan", "glisse"]):
        if has("generique-aquatique-toboggan.jpg"):
            return "generique-aquatique-toboggan.jpg"
    if match_any(text, ["couvert", "intérieur", "interieur", "indoor"]):
        if has("generique-aquatique-piscine-couverte.jpg"):
            return "generique-aquatique-piscine-couverte.jpg"
    if match_any(text, ["extérieur", "exterieur", "plein air", "outdoor"]):
        if has("generique-aquatique-piscine-exterieur.jpg"):
            return "generique-aquatique-piscine-exterieur.jpg"
    choices = [v for v in ["generique-aquatique-bassin-natation.jpg",
                            "generique-aquatique-piscine-couverte.jpg",
                            "generique-aquatique-piscine-exterieur.jpg",
                            "generique-aquatique-toboggan.jpg"] if has(v)]
    return slug_pick(slug, choices) or "generique-attraction.jpg"


def pick_patinoire(slug, text):
    if match_any(text, ["hockey"]):
        if has("generique-patinoire-hockey.jpg"):
            return "generique-patinoire-hockey.jpg"
    if match_any(text, ["patinage artistique", "danse", "spectacle"]):
        if has("generique-patinoire-patins-blancs.jpg"):
            return "generique-patinoire-patins-blancs.jpg"
    choices = [v for v in ["generique-patinoire-hockey.jpg",
                            "generique-patinoire-patins-blancs.jpg",
                            "generique-patinoire-skater.jpg"] if has(v)]
    return slug_pick(slug, choices) or "generique-attraction.jpg"


def pick_karting(slug, text):
    if match_any(text, ["indoor", "intérieur", "interieur", "couvert"]):
        choices = [v for v in ["generique-karting-indoor.jpg",
                                "generique-karting-indoor-motion.jpg"] if has(v)]
        return slug_pick(slug, choices) or "generique-karting-indoor.jpg"
    choices = [v for v in ["generique-karting-outdoor-track.jpg",
                            "generique-karting-outdoor-3kids.jpg",
                            "generique-karting-outdoor-aerial.jpg"] if has(v)]
    return slug_pick(slug, choices) or "generique-attraction.jpg"


def pick_bowling(slug, text):
    choices = [v for v in ["generique-bowling-lanes.jpg",
                            "generique-bowling-strike.jpg"] if has(v)]
    return slug_pick(slug, choices) or "generique-attraction.jpg"


def pick_attraction(slug, text):
    """The catch-all bucket. Disambiguate by facts.type / body keywords."""
    # Escape game (3 variants)
    if match_any(text, ["escape game", "escape-game"]):
        choices = [v for v in ["generique-escape-game-neon.jpg",
                                "generique-escape-game-exit.jpg",
                                "generique-escape-game-cadenas.jpg"] if has(v)]
        return slug_pick(slug, choices)

    # Atelier poterie / céramique
    if match_any(text, ["atelier poterie", "céramique", "ceramique", "tournage"]):
        if has("generique-atelier-poterie-mains.jpg"):
            return "generique-atelier-poterie-mains.jpg"

    # Via ferrata + salle d'escalade
    if match_any(text, ["via ferrata", "salle d'escalade", "salle de bloc",
                        "escalade indoor", "escalade outdoor", "bloc indoor"]):
        choices = [v for v in ["generique-escalade-bouldering.jpg",
                                "generique-escalade-wall.jpg",
                                "generique-escalade-outdoor-falaise.jpg",
                                "generique-escalade-bloc-outdoor.jpg"] if has(v)]
        return slug_pick(slug, choices)

    # Trampoline
    if match_any(text, ["trampoline"]):
        if has("generique-trampoline-park-saut.jpg"):
            return "generique-trampoline-park-saut.jpg"

    # Laser game
    if match_any(text, ["laser game", "laser-game"]):
        if has("generique-laser-game.jpg"):
            return "generique-laser-game.jpg"

    # Bar à jeux / bar ludique
    if match_any(text, ["bar à jeux", "bar ludique", "bar a jeux"]):
        if has("generique-bar-jeux.jpg"):
            return "generique-bar-jeux.jpg"

    # Lancer de hache
    if match_any(text, ["lancer de hache", "lancer de haches", "hachez"]):
        if has("generique-lancer-de-hache.jpg"):
            return "generique-lancer-de-hache.jpg"

    # Canyoning — new pool from the hero pack
    if match_any(text, ["canyoning", "canyon", "descente de canyon"]):
        return _pool(slug, "generique-canyoning-", 6)

    # Montgolfière / aérostation — must come BEFORE parapente because
    # both can hit "baptême de l'air" in facts.type.
    if match_any(text, ["montgolf", "aérostation", "aerostation", "ballon captif"]):
        return "generique-montgolfiere.jpg" if has("generique-montgolfiere.jpg") else None

    # Parapente / ULM
    if match_any(text, ["parapente", "ulm", "baptême de l'air", "baptême air"]):
        choices = [v for v in ["generique-parapente-decollage.jpg",
                                "generique-parapente-vol.jpg"] if has(v)]
        return slug_pick(slug, choices)

    # VR / réalité virtuelle
    if match_any(text, ["réalité virtuelle", "realite virtuelle", "vr ", " vr"]):
        choices = [v for v in ["generique-vr-immersion.jpg",
                                "generique-vr-multi-joueurs.jpg"] if has(v)]
        return slug_pick(slug, choices)

    # Spa / thermes / bien-être
    if match_any(text, ["spa", "thermes", "bien-être", "bien etre",
                        "sauna", "hammam"]):
        choices = [v for v in ["generique-spa-bien-etre.jpg",
                                "generique-spa-bols-tibetains.jpg",
                                "generique-spa-huile-essentielle.jpg",
                                "generique-spa-jardin-tropical.jpg",
                                "generique-thermes-hammam.jpg"] if has(v)]
        return slug_pick(slug, choices)

    # Jardin remarquable / jardin botanique — cross-bucket for fiches
    # filed as 'attraction' with a clear jardin facts.type
    if match_any(text, ["jardin remarquable", "jardin botanique",
                        "arboretum", "jardin alpin"]):
        choices = [v for v in ["generique-parc.jpg",
                                "generique-jardin-detente-1.jpg"] if has(v)]
        if choices:
            return slug_pick(slug, choices)

    # Family-flavoured outdoor (ferme pédagogique, jeux de piste familiaux)
    if match_any(text, ["ferme pédagogique", "ferme pedagogique",
                        "jeu de piste", "détective nature", "detective nature"]):
        choices = [v for v in ["generique-famille-balade.jpg",
                                "generique-famille-foret.jpg"] if has(v)]
        if choices:
            return slug_pick(slug, choices)

    return None  # unmatched — caller keeps generique-attraction.jpg


def pick_plage_or_baignade(slug, text):
    """`plage` category — no dedicated variant on disk yet. Use the lac
    variants as best-available; flag for Part 2 sourcing."""
    choices = [v for v in ["generique-lac-coucher-soleil.jpg",
                            "generique-lac.jpg"] if has(v)]
    return slug_pick(slug, choices) or "generique-attraction.jpg"


def pick_base_nautique(slug, text):
    if match_any(text, ["aviron", "paddle", "sup", "stand-up paddle"]):
        if has("generique-paddle-aviron-detail.jpg"):
            return "generique-paddle-aviron-detail.jpg"
        if has("generique-barque-aviron.jpg"):
            return "generique-barque-aviron.jpg"
    choices = [v for v in ["generique-paddle-aviron-detail.jpg",
                            "generique-barque-aviron.jpg",
                            "generique-port-annecy.jpg",
                            "generique-voile-sunset-1.jpg"] if has(v)]
    return slug_pick(slug, choices) or "generique-lac.jpg"


def pick_croisiere(slug, text):
    choices = [v for v in ["generique-croisiere.jpg",
                            "generique-port-annecy.jpg",
                            "generique-voile-sunset-1.jpg"] if has(v)]
    return slug_pick(slug, choices) or "generique-lac.jpg"


def pick_jardin(slug, text):
    """jardin pool — includes the detente seating shot for diversity."""
    choices = [v for v in ["generique-parc.jpg",
                            "generique-jardin-detente-1.jpg"] if has(v)]
    return slug_pick(slug, choices) or "generique-attraction.jpg"


def pick_cinema(slug, text):
    return "generique-cinema.jpg" if has("generique-cinema.jpg") else "generique-attraction.jpg"


def pick_for_fiche(fiche, slug):
    """Return (chosen_variant, reason). Returns (None, reason) if real photo."""
    img = fiche.get("hero_image") or ""

    # Normalize: strip leading slash + take basename. Post-2026-06-15
    # the path is "/img/<hub>/<file>", but we still want to recognise a
    # legacy bare "generique-X.jpg" as a generic. Detection runs on the
    # basename, not the full path.
    normalized = img.lstrip("/") if img else ""
    basename = normalized.rsplit("/", 1)[-1] if normalized else ""

    # Real photo URL — never touch
    if img.startswith(("http://", "https://")) or img.startswith("//"):
        return None, "real-photo-url"
    # Local non-generique path — keep only if the file actually exists on disk
    if basename and not basename.startswith("generique-"):
        if (ROOT / normalized).exists():
            return None, "real-photo-path"
        # Missing local hero — re-pick a generique fallback so the page doesn't 404

    cat = (fiche.get("category") or "").strip()
    cats = fiche.get("categories") or ([cat] if cat else [])
    # text  = family-selection (facts.type + name only — no body prose)
    # flavour = MOOD/SEASON variation inside an already-correct family.
    # Family deciders ALWAYS receive text. flavour goes only to the few
    # sub-pickers where mood is the choice (pick_sentier season,
    # plage/lac sunset-vs-misty).
    text    = type_text(fiche)
    flavour = fr_text(fiche)

    # Cross-category overrides — réserves/marais are filed as sentier,
    # mushing as divers/attraction, alpine coaster as attraction.
    # type_text-gated now, so prose mentions of "réserve naturelle"
    # on a via ferrata page no longer fire the wetland pool.
    ov = pick_text_override(slug, text, cat)
    if ov:
        return ov, "text-override"

    chosen = None
    reason = f"category={cat!r}"

    if cat == "sentier":
        chosen = pick_sentier(slug, text, flavour)
    elif cat == "voie-verte":
        chosen = pick_voie_verte(slug, text)
    elif cat == "musee":
        chosen = pick_musee(slug, text)
    elif cat == "chateau":
        chosen = pick_chateau(slug, text)
    elif cat == "cascade":
        chosen = "generique-cascade.jpg" if has("generique-cascade.jpg") else None
    elif cat == "lac":
        chosen = pick_lac(slug, text, flavour)
        # Diversity blend: when the lac picker would return the bare
        # generique-lac.jpg, mix in plage-lac-* shots so the same image
        # doesn't repeat across every mountain lake card.
        if chosen == "generique-lac.jpg":
            blend = _pool(slug, "generique-plage-lac-", 15)
            if blend:
                chosen = slug_pick(slug, [chosen, blend])
    elif cat == "domaine":
        chosen = "generique-domaine.jpg" if has("generique-domaine.jpg") else None
    elif cat == "parc":
        chosen = "generique-parc.jpg" if has("generique-parc.jpg") else None
    elif cat == "point-de-vue":
        chosen = "generique-point-de-vue.jpg" if has("generique-point-de-vue.jpg") else None
    elif cat == "telecabine":
        chosen = "generique-telecabine.jpg" if has("generique-telecabine.jpg") else None
    elif cat == "plage":
        chosen = _pool(slug, "generique-plage-lac-", 15) or pick_plage_or_baignade(slug, text)
    elif cat == "aquaparc":
        chosen = pick_aquaparc(slug, text)
    elif cat == "cinema":
        chosen = pick_cinema(slug, text)
    elif cat == "karting":
        chosen = pick_karting(slug, text)
    elif cat == "patinoire":
        chosen = pick_patinoire(slug, text)
    elif cat == "bowling":
        chosen = pick_bowling(slug, text)
    elif cat == "casino":
        chosen = "generique-attraction.jpg"  # no casino variant on disk yet
    elif cat == "base-nautique":
        chosen = pick_base_nautique(slug, text)
    elif cat == "croisiere":
        chosen = pick_croisiere(slug, text)
    elif cat == "accrobranche":
        chosen = _pool(slug, "generique-accrobranche-", 12) or "generique-attraction.jpg"
    elif cat == "jardin":
        chosen = pick_jardin(slug, text)
    elif cat == "wakepark":
        chosen = (_pool(slug, "generique-wakeboard-", 1)
                  or ("generique-wakeboard.jpg" if has("generique-wakeboard.jpg")
                      else "generique-attraction.jpg"))
    elif cat == "divers":
        # divers is a residual bucket; route through pick_attraction so
        # spa/thermes/centre-aquatique with a clear facts.type still
        # hit their sub-family rule.
        chosen = pick_attraction(slug, text)
        if chosen is None:
            chosen = "generique-attraction.jpg"
            reason += " · divers unmatched"
        else:
            reason += " · type/name match"
    elif cat == "attraction":
        chosen = pick_attraction(slug, text)
        if chosen is None:
            chosen = "generique-attraction.jpg"
            reason += " · unmatched-attraction → flagged for Part 2"
        else:
            reason += f" · type/name match"
    else:
        # unknown category — keep attraction fallback
        chosen = "generique-attraction.jpg"
        reason += " · unknown-category"

    if chosen and not has(chosen):
        # safety net — variant we picked doesn't exist on disk
        reason += f" · MISSING({chosen})"
        chosen = "generique-attraction.jpg"

    return chosen, reason


def main():
    files = sorted(glob.glob(str(JSON_DIR / "*.json")))
    written = 0
    skipped_real = 0
    no_change = 0
    flagged = []
    diversity = {}

    for fp in files:
        d = json.loads(Path(fp).read_text(encoding="utf-8"))
        slug = Path(fp).stem
        chosen, reason = pick_for_fiche(d, slug)
        if chosen is None:
            skipped_real += 1
            continue
        diversity[chosen] = diversity.get(chosen, 0) + 1
        if chosen == "generique-attraction.jpg" and "Part 2" in reason:
            flagged.append((slug, (d.get("i18n", {}).get("fr") or {}).get("facts", {}).get("type", "")))
        # Compose the canonical /img/<hub>/<file> path. The hub is the
        # fiche's primary hub when the variant lives there, otherwise the
        # first hub in the variant's hub list. See _path_for() for the
        # selection logic.
        new_hero = _path_for(d, chosen)
        cur = d.get("hero_image") or ""
        if cur == new_hero:
            no_change += 1
            continue
        d["hero_image"] = new_hero
        rl = d.setdefault("research_log", [])
        # dedupe within same day
        already = any(
            isinstance(r, dict)
            and r.get("by") == "scripts/pick_generique.py"
            and r.get("date") == TODAY
            for r in rl
        )
        if not already:
            rl.append({
                "date": TODAY,
                "by": "scripts/pick_generique.py",
                "note": f"hero_image → {new_hero} ({reason}).",
            })
        Path(fp).write_text(
            json.dumps(d, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written += 1

    print(f"\nfiles processed: {len(files)}")
    print(f"  skipped (real photo)   : {skipped_real}")
    print(f"  unchanged              : {no_change}")
    print(f"  hero_image written     : {written}")
    print(f"\ndiversity — variants assigned (top 30):")
    for variant, n in sorted(diversity.items(), key=lambda x: -x[1])[:30]:
        bar = "█" * min(n, 30)
        print(f"  {n:4d}  {variant:50s} {bar}")
    print(f"\ndistinct variants used: {len(diversity)}")
    print(f"\nfiches still on generique-attraction.jpg (Part 2 targets): {len(flagged)}")
    if flagged:
        print(f"  (top 20 by facts.type)")
        by_type = {}
        for slug, ftype in flagged:
            by_type.setdefault(ftype or "(no facts.type)", []).append(slug)
        for ftype, slugs in sorted(by_type.items(), key=lambda x: -len(x[1]))[:20]:
            print(f"  {len(slugs):3d}  {ftype[:60]:60s}")


if __name__ == "__main__":
    main()
