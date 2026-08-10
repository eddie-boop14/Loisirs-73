#!/usr/bin/env python3
"""Self-generating AI content layer — SPECaicontentlayer + HANDOFF-39 facet layer.

ONE generator owns the whole machine-readable layer so it can never drift again:

  Json/<slug>.json ──▶ content/<slug>.md        (×N, FR facet canon, geo frontmatter)
                   ├──▶ content/en/<slug>.md    (×N, EN facet canon — EN only, no other langs)
                   ├──▶ api/lieu/<slug>.json    (×N, typed facts JSON, nulls preserved)
                   ├──▶ llms.txt                (the MAP: what-is · URL patterns · anchors · hubs · listing)
                   ├──▶ llms-full.txt           (all FR md concatenated, header from truth)
                   └──▶ .well-known/ai-info.json (discovery manifest, counts from truth)

HANDOFF-39 facet canon (byte-verbatim, gate-enforced by gate_facet_layer.py):
  FR: # <Name> · ## Faits · ## Horaires · ## Tarifs · ## Accès (PMR) ·
      ## Parking · ## Transport · ## Saison · ## Source officielle
  EN: # <Name> · ## Facts · ## Hours · ## Prices · ## Access (PMR) ·
      ## Parking · ## Transport · ## Season · ## Official source
Facts lines only, no prose padding. Unknown → "Non renseigné" / "Not specified"
in the md; null stays null in the JSON — a value is NEVER guessed. Frozen FR
names verbatim in both language files. LF only, UTF-8 only.

JSON contract /api/lieu/<slug>.json (gate-enforced):
  {name, commune, gps, type, hours, prices, access_pmr, parking, transport,
   season, winter, official_url, last_verified}
  — all 13 keys ALWAYS present; null allowed; absent-key forbidden; types fixed.
  winter (v2, HANDOFF-winter): null off WINTER_NODES; else {access, infrastructure,
  snow_view, equipment:"loi_montagne_ii", col_chains}.
  FR is the canonical language for prose facets (hours), per the site ai_policy.

Invariant: the layer is DERIVED, never hand-edited. `research_log` is NEVER
included. The 9 hand-curated hub dumps (content/<category>.md) are untouched —
this generator owns per-lieu md (FR + EN), the per-lieu JSON tree, the two llms
files, and ai-info.json.

Idempotent: re-run with unchanged JSON ⇒ byte-identical output (except the
llms-full "Generated:" + ai-info "last_updated" dates, today by design — §4.2).

Usage:
    python3 scripts/build_ai_content.py            # write the whole layer
    python3 scripts/build_ai_content.py --check     # write nothing; report drift
"""
import argparse
import siteconfig  # HANDOFF-73: per-site identity
import datetime
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_DIR = os.path.join(ROOT, "Json")
CONTENT_DIR = os.path.join(ROOT, "content")
BASE_URL = siteconfig.BASE_URL
TODAY = datetime.date.today().isoformat()

DEPARTMENT = siteconfig.DEPT_NAME
DEPARTMENT_CODE = siteconfig.DEPT_CODE
REGION = siteconfig.REGION
COUNTRY = "France"

MONTHS_FR = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "août": 8, "aout": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}

# Singular FR category label for frontmatter `category_label`. Seeded from the
# labels the hand-made 84 already used (Château, Cascade, Base de loisirs, …),
# extended to every category present in the corpus.
CATEGORY_LABEL_FR = {
    "attraction": "Attraction",
    "cascade": "Cascade",
    "chateau": "Château",
    "domaine": "Base de loisirs",
    "lac": "Lac & plage",
    "musee": "Musée",
    "point-de-vue": "Point de vue",
    "telecabine": "Téléphérique / Télécabine",
    "sentier": "Sentier",
    "parc": "Parc de loisirs",
    "plage": "Plage",
    "cinema": "Cinéma",
    "aquaparc": "Parc aquatique",
    "karting": "Karting",
    "casino": "Casino",
    "patinoire": "Patinoire",
    "divers": "Sortie loisir",
    "base-nautique": "Base nautique",
    "croisiere": "Croisière",
    "bowling": "Bowling",
    "wakepark": "Wakepark",
    "accrobranche": "Accrobranche",
    "jardin": "Jardin",
}

# ── HANDOFF-39 facet canon ──────────────────────────────────────────────────
# The eight H2 anchors, byte-verbatim, in this exact order (gate-enforced).
FACET_HEADINGS = {
    "fr": ["## Faits", "## Horaires", "## Tarifs", "## Accès (PMR)",
           "## Parking", "## Transport", "## Saison", "## Source officielle"],
    "en": ["## Facts", "## Hours", "## Prices", "## Access (PMR)",
           "## Parking", "## Transport", "## Season", "## Official source"],
}
UNKNOWN = {"fr": "Non renseigné", "en": "Not specified"}

# ── HANDOFF-winter · structured ## Saison scaffolding (JOB A) ────────────────
# Winter keys are BULLET lines under the existing ## Saison heading (never a new
# ##). Emitted only for WINTER_NODES categories. Values come from facts.winter_*
# (null-safe; JOB B populates). Controlled vocab — anything off-list is a build
# error (gate_winter_schema). Frozen: Mont-Blanc, Loi Montagne II verbatim.
WINTER_NODES = {"sentier", "point-de-vue", "cascade", "telecabine", "voie-verte", "station"}
WINTER_ACCESS = {
    "open": {"fr": "Ouvert (accès déneigé)", "en": "Open (cleared road)", "de": "Geöffnet (Zufahrt geräumt)", "it": "Aperto (accesso sgombrato)", "es": "Abierto (acceso despejado)", "nl": "Open (toegangsweg sneeuwvrij)"},
    "closed": {"fr": "Fermé (route fermée l'hiver)", "en": "Closed (road shut in winter)", "de": "Geschlossen (Straße im Winter gesperrt)", "it": "Chiuso (strada chiusa in inverno)", "es": "Cerrado (carretera cerrada en invierno)", "nl": "Gesloten (weg 's winters dicht)"},
    "partial": {"fr": "Accès partiel", "en": "Partial access", "de": "Teilweiser Zugang", "it": "Accesso parziale", "es": "Acceso parcial", "nl": "Gedeeltelijke toegang"},
}

WINTER_INFRA = {
    # ski_alpin was absent while the engine served only Haute-Savoie, whose winter
    # corpus is lakes, plateaux and nordic terrain. Savoie's winter identity is the
    # linked alpine areas — Les 3 Vallées, Espace Killy, Paradiski — and without
    # this key a Val Thorens cable car had no honest way to say what it is.
    "ski_alpin": {"fr": "Ski alpin", "en": "Alpine skiing", "de": "Alpinski", "it": "Sci alpino", "es": "Esquí alpino", "nl": "Alpineskiën"},
    "raquettes": {"fr": "Raquettes", "en": "Snowshoeing", "de": "Schneeschuhwandern", "it": "Ciaspole", "es": "Raquetas de nieve", "nl": "Sneeuwschoenwandelen"},
    "ski_nordique": {"fr": "Ski nordique", "en": "Nordic skiing", "de": "Nordischer Skisport", "it": "Sci nordico", "es": "Esquí nórdico", "nl": "Noords skiën"},
    "ski_fond": {"fr": "Ski de fond", "en": "Cross-country skiing", "de": "Langlauf", "it": "Sci di fondo", "es": "Esquí de fondo", "nl": "Langlaufen"},
    "ski_rando": {"fr": "Ski de rando", "en": "Ski touring", "de": "Skitouren", "it": "Scialpinismo", "es": "Esquí de travesía", "nl": "Toerskiën"},
    "chiens_traineau": {"fr": "Chiens de traîneau", "en": "Dog sledding", "de": "Hundeschlittenfahrten", "it": "Cani da slitta", "es": "Trineo de perros", "nl": "Hondensleetochten"},
    "luge": {"fr": "Luge", "en": "Sledging", "de": "Rodeln", "it": "Slittino", "es": "Trineo", "nl": "Sleeën"},
}

SNOW_VIEW = {
    "mont_blanc": {"fr": "Vue Mont-Blanc dégagée", "en": "Clear Mont-Blanc view", "de": "Freier Blick auf den Mont-Blanc", "it": "Vista libera sul Mont-Blanc", "es": "Vista despejada del Mont-Blanc", "nl": "Vrij zicht op de Mont-Blanc"},
    "alpes": {"fr": "Panorama alpin", "en": "Alpine panorama", "de": "Alpenpanorama", "it": "Panorama alpino", "es": "Panorama alpino", "nl": "Alpenpanorama"},
    "lac": {"fr": "Vue sur le lac", "en": "Lake view", "de": "Seeblick", "it": "Vista sul lago", "es": "Vista al lago", "nl": "Uitzicht op het meer"},
    "none": {"fr": "Pas de panorama neige", "en": "No snow panorama", "de": "Kein Schneepanorama", "it": "Nessun panorama innevato", "es": "Sin panorama nevado", "nl": "Geen sneeuwpanorama"},
}

EQUIP = {"fr": "Loi Montagne II — pneus hiver ou chaînes obligatoires (1 nov – 31 mars)",
         "en": "Loi Montagne II — winter tyres or chains required (1 Nov – 31 Mar)",
         "de": "Loi Montagne II — Winterreifen oder Ketten Pflicht (1. Nov. – 31. März)",
         "it": "Loi Montagne II — pneumatici invernali o catene obbligatori (1 nov – 31 mar)",
         "es": "Loi Montagne II — neumáticos de invierno o cadenas obligatorios (1 nov – 31 mar)",
         "nl": "Loi Montagne II — winterbanden of kettingen verplicht (1 nov – 31 mrt)"}

EQUIP_COL = {"fr": " · chaînes conseillées pour l'accès au col",
         "en": " · chains advised for col access",
         "de": " · Ketten für die Passzufahrt empfohlen",
         "it": " · catene consigliate per l'accesso al colle",
         "es": " · cadenas recomendadas para el acceso al puerto de montaña",
         "nl": " · kettingen aanbevolen voor de toegang tot de pas"}

WINTER_LABELS = {
    "access": {"fr": "Fenêtre d'accès hiver", "en": "Winter access window", "de": "Zugang im Winter", "it": "Accesso invernale", "es": "Acceso en invierno", "nl": "Wintertoegang"},
    "infra": {"fr": "Infrastructure hiver", "en": "Winter infrastructure", "de": "Winterinfrastruktur", "it": "Infrastrutture invernali", "es": "Infraestructura invernal", "nl": "Winterinfrastructuur"},
    "view": {"fr": "Panorama enneigé", "en": "Snow panorama", "de": "Schneepanorama", "it": "Panorama innevato", "es": "Panorama nevado", "nl": "Sneeuwpanorama"},
    "equip": {"fr": "Équipement obligatoire", "en": "Equipment mandated", "de": "Vorgeschriebene Ausrüstung", "it": "Equipaggiamento obbligatorio", "es": "Equipamiento obligatorio", "nl": "Verplichte uitrusting"},
}

# JOB B — the road-service escape hatch. When the access régime is closed/partial or
# the node carries a col, the fiche STATES THE SEASONAL RÉGIME with its source and
# delegates live status to the Département. We never assert today's road state.
# The operator is per-site (HANDOFF-73): Haute-Savoie delegates to inforoute74.fr,
# Savoie to savoie-route.fr. Label localized (the winter card itself renders fr/en,
# so those two are what surface — the six PROSE forms are kept for the facet layer
# + parity).
INFOROUTE_URL = siteconfig.ROAD_INFO_URL
INFOROUTE_HOST = siteconfig.ROAD_INFO_HOST
WINTER_LIVE = {"fr": "État en temps réel :", "en": "Live status:", "de": "Echtzeit-Status:",
               "it": "Stato in tempo reale:", "es": "Estado en tiempo real:", "nl": "Realtime status:"}


def winter_needs_inforoute(fk):
    """True when the access line must carry the road-service delegation link:
    winter_access ∈ {closed, partial} OR col_chains true — and only when this
    site has an operator configured. A site with no road_info block delegates
    to nobody rather than to its neighbour."""
    if not INFOROUTE_HOST:
        return False
    return fk.get("winter_access") in ("closed", "partial") or bool(fk.get("col_chains"))


def winter_inforoute_md(fk, lang):
    """Plain-text suffix for the facet md / text surfaces ('' when not needed)."""
    if not winter_needs_inforoute(fk):
        return ""
    return f" — {WINTER_LIVE.get(lang, WINTER_LIVE['en'])} {INFOROUTE_HOST}"


def winter_bullets(d, lang):
    """The `- Key: value` winter lines under ## Saison, or [] for non-winter
    nodes / non-fr-en. Equipment is a verified dept-wide constant (always known
    for a qualifying Haute-Savoie node); access/infra/view are null → UNKNOWN."""
    if (d.get("category") or "") not in WINTER_NODES or lang not in ("fr", "en"):
        return []
    fk = (fr(d).get("facts") or {})
    L, unk = WINTER_LABELS, UNKNOWN[lang]
    a = fk.get("winter_access")
    av = WINTER_ACCESS[a][lang] if a in WINTER_ACCESS else unk
    infra = [WINTER_INFRA[x][lang] for x in (fk.get("winter_infra") or [])
             if x in WINTER_INFRA]
    sv = fk.get("snow_view")
    svv = SNOW_VIEW[sv][lang] if sv in SNOW_VIEW else unk
    eq = EQUIP[lang] + (EQUIP_COL[lang] if fk.get("col_chains") else "")
    return [
        f"- {L['access'][lang]}: {av}{winter_inforoute_md(fk, lang)}",
        f"- {L['infra'][lang]}: {' · '.join(infra) if infra else unk}",
        f"- {L['view'][lang]}: {svv}",
        f"- {L['equip'][lang]}: {eq}",
    ]
# Reviewed PMR status labels — copied verbatim from the fr/en rows of
# build_lieu_page._ACCES_STATUS (the vocabulary the HTML pages render).
PMR_STATUS_LABEL = {
    "accessible": {"fr": "Accessible", "en": "Accessible"},
    "partiel": {"fr": "Partiellement accessible", "en": "Partially accessible"},
    "non_accessible": {"fr": "Non accessible", "en": "Not accessible"},
}

# llms.txt hub buckets: (label, [categories], hub_md_slug). The last bucket is a
# computed catch-all for any category not claimed above, so a new category can
# never silently vanish from the index.
HUBS = [
    ("Lacs & plages", ["lac", "plage"], "lacs"),
    ("Cascades", ["cascade"], "cascades"),
    ("Bases de loisirs", ["domaine", "parc"], "bases-de-loisirs"),
    ("Points de vue", ["point-de-vue"], "points-de-vue"),
    ("Téléphériques & télécabines", ["telecabine"], "telecabines"),
    ("Châteaux", ["chateau"], "chateaux"),
    ("Sentiers", ["sentier"], "sentiers"),
    ("Voies vertes", ["voie-verte"], "voies-vertes"),
    ("Musées", ["musee"], "musees"),
    ("Attractions & loisirs", None, "attractions"),  # None = catch-all
]


# ── helpers ─────────────────────────────────────────────────────────────────
def fr(d):
    return (d.get("i18n", {}) or {}).get("fr", {}) or {}


def lang_block(d, lang):
    return (d.get("i18n", {}) or {}).get(lang, {}) or {}


def name_of(d):
    return fr(d).get("name") or (d.get("i18n", {}).get("en", {}) or {}).get("name") or d["slug"]


def yq(v):
    """YAML double-quoted scalar (the text fields the template quotes)."""
    if v is None:
        return "null"
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def iso_date(human):
    """'14 mai 2026' / '1er juin 2026' → '2026-05-14'. None on failure."""
    if not human:
        return None
    m = re.match(r"\s*(\d{1,2})(?:er)?\s+([^\s]+)\s+(\d{4})", str(human))
    if not m:
        return None
    day, mon, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
    if mon not in MONTHS_FR:
        return None
    return f"{year:04d}-{MONTHS_FR[mon]:02d}-{day:02d}"


def photo_fields(d):
    """(photo_type, author, license, source) from hero_image + hero_credit.
    Generic placeholder images carry no real attribution → author/license/source
    are null."""
    img = d.get("hero_image") or ""
    credit = d.get("hero_credit") or ""
    base = img.rsplit("/", 1)[-1]
    is_generic = base.startswith("generique-") or "génér" in credit.lower()
    if is_generic or not credit:
        return ("generic" if is_generic else "real"), None, None, None
    parts = [p.strip() for p in credit.split("·") if p.strip()]
    author = parts[0] if parts else None
    if author:
        # visitor credits read "Photo : <Name>" — the label isn't the author
        author = re.sub(r"^photo\s*:\s*", "", author, flags=re.I) or None
    source = parts[-1] if len(parts) >= 2 else None
    license_ = parts[1] if len(parts) >= 3 else None
    # a trailing courtesy segment ("merci ! 🦆") is not a source
    if source and not re.search(r"(wikimedia|commons|flickr|cc|©|http)", source, re.I):
        source = None
    return "real", author, license_, source


def truncate(text, limit=150):
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut + "…"


def load_transport_index():
    path = os.path.join(ROOT, "data", "transport_index.json")
    if not os.path.exists(path):
        return {}, {}
    t = json.load(open(path, encoding="utf-8"))
    meta = t.get("_meta") or {}
    return t, meta


TRANSPORT, TRANSPORT_META = load_transport_index()


def practical_value(block, prefixes):
    """First practical_info value whose key starts with one of `prefixes`
    (case-insensitive), else None. Facts lane only — no synthesis."""
    for e in (block.get("practical_info") or []):
        k = (e.get("k") or "").strip().lower()
        if k and e.get("v") and any(k.startswith(p) for p in prefixes):
            return str(e["v"]).strip()
    return None


HOURS_KEYS = {"fr": ("horaire",), "en": ("hours", "opening hours")}


def hours_prose(d, lang):
    """The honest hours lane: the language's own practical_info prose, FR
    canonical fallback (facts are facts), else None. No machine hours field
    exists in the corpus — flagged as the weakest facet, never synthesized."""
    v = practical_value(lang_block(d, lang), HOURS_KEYS.get(lang, ()))
    if v is None and lang != "fr":
        v = practical_value(fr(d), HOURS_KEYS["fr"])
    return v


def lang_fact(d, lang, key):
    """facts.<key> in the file's own language, FR fallback, else None."""
    v = (lang_block(d, lang).get("facts") or {}).get(key)
    if not v and lang != "fr":
        v = (fr(d).get("facts") or {}).get(key)
    return str(v).strip() if v else None


def official_url_of(d):
    if d.get("official_site_url"):
        return d["official_site_url"]
    for s in (d.get("sources") or []):
        if isinstance(s, str) and s.startswith(("http://", "https://")):
            return s
        if isinstance(s, dict) and s.get("url"):
            return s["url"]
    return None


# ── the shared facet mapping (feeds BOTH the md renderer and the JSON) ──────
def lieu_facets(d):
    """Language-independent typed facet dict — the single source both surfaces
    render from, so md and JSON can never drift. Null discipline: a facet the
    corpus doesn't know stays None; nothing is guessed."""
    slug = d["slug"]
    facts = fr(d).get("facts") or {}

    gps = None
    if d.get("latitude") is not None and d.get("longitude") is not None:
        gps = {"lat": d["latitude"], "lng": d["longitude"]}

    tiers = [{"name": t.get("name"), "price": t.get("price"), "note": t.get("note")}
             for t in (d.get("price_tiers") or []) if isinstance(t, dict)]
    is_free = (d.get("schema_org") or {}).get("is_free")
    if d.get("price_from") is not None or tiers or is_free is not None or facts.get("tarif"):
        prices = {
            "from": d.get("price_from"),
            "currency": d.get("price_currency"),
            "tiers": tiers,
            "is_free": is_free if isinstance(is_free, bool) else None,
            "note": facts.get("tarif") or None,
        }
    else:
        prices = None

    a = d.get("acces_pmr")
    if isinstance(a, dict) and a.get("status") in PMR_STATUS_LABEL:
        access_pmr = {
            "status": a["status"],
            "detail": a.get("detail") or None,
            "equipment": a.get("equipment") or [],
            "handiplage_level": a.get("handiplage_level"),
            "source_url": a.get("source_url") or None,
            "source_name": a.get("source_name") or None,
        }
    else:
        access_pmr = None

    t = TRANSPORT.get(slug) or {}
    stops = t.get("stops") or []
    if stops:
        transport = {
            "source": t.get("source"),
            "license": t.get("license"),
            "verified": t.get("verified"),
            "stops": [{"name": s.get("name"), "operator": s.get("operator"),
                       "distance_m": s.get("distance_m"),
                       "lines": s.get("lines") or []} for s in stops],
        }
    else:
        transport = None

    last_verified = ((d.get("freshness") or {}).get("checked")
                     or (d.get("google_check") or {}).get("checked") or None)

    return {
        "name": name_of(d),
        "commune": d.get("commune") or None,
        "gps": gps,
        "type": d.get("category") or None,
        "hours": hours_prose(d, "fr"),
        "prices": prices,
        "access_pmr": access_pmr,
        "parking": facts.get("parking") or None,
        "transport": transport,
        "season": facts.get("best_season") or None,
        "winter": None if (d.get("category") or "") not in WINTER_NODES else {
            "access":         facts.get("winter_access"),       # enum|null
            "infrastructure": facts.get("winter_infra") or [],
            "snow_view":      facts.get("snow_view"),           # enum|null
            "equipment":      "loi_montagne_ii",                # constant token, HS
            "col_chains":     bool(facts.get("col_chains")),
            "inforoute":      INFOROUTE_URL if winter_needs_inforoute(facts) else None,
        },
        "official_url": official_url_of(d),
        "last_verified": last_verified,
    }


def flat(v):
    """One clean facts line: collapse internal whitespace/newlines, no trailing
    space — the md canon is line-oriented and the strict gate forbids trailing
    whitespace and stray heading-like lines. JSON keeps values verbatim."""
    return " ".join(str(v).split()) if v is not None else None


def fmt_price(p, currency):
    if p is None:
        return None
    n = f"{p:g}" if isinstance(p, (int, float)) else str(p)
    return f"{n} {currency}" if currency else n


# ── per-lieu facet markdown (FR + EN canon) ─────────────────────────────────
def render_md(d, lang="fr"):
    """HANDOFF-39 facet md: YAML frontmatter + the byte-verbatim heading canon.
    Facts lines only. Unknown facet → the language's UNKNOWN token; the value
    itself is never invented. Frozen FR name verbatim in BOTH language files."""
    slug = d["slug"]
    name = name_of(d)                      # frozen FR name, verbatim
    cat = d.get("category", "")
    label = CATEGORY_LABEL_FR.get(cat, cat.replace("-", " ").capitalize())
    ptype, pauthor, plicense, psource = photo_fields(d)
    fx = lieu_facets(d)
    unk = UNKNOWN[lang]
    lb = lang_block(d, lang)

    canonical = f"{BASE_URL}/{slug}" if lang == "fr" else f"{BASE_URL}/{lang}/{slug}"
    fm = [
        ("slug", slug, False),
        ("name", name, True),
        ("category", cat, False),
        ("category_label", label, True),
        ("commune", d.get("commune"), True),
        ("postal_code", d.get("postal_code"), True),
        ("department", DEPARTMENT, True),
        ("department_code", DEPARTMENT_CODE, True),
        ("region", REGION, True),
        ("country", COUNTRY, False),
        ("latitude", d.get("latitude"), False),
        ("longitude", d.get("longitude"), False),
        ("geo_verified", "true" if d.get("geo_verified") is True else "false", False),
        ("google_place_id", d.get("google_place_id"), True),
        ("canonical_url", canonical, False),
        ("language", lang, False),
        ("facet_json", f"{BASE_URL}/api/lieu/{slug}.json", False),
        ("photo_url", d.get("hero_image"), False),
        ("photo_type", ptype, False),
        ("photo_author", pauthor, True),
        ("photo_license", plicense, True),
        ("photo_source", psource, False),
        ("last_updated", iso_date(d.get("date_modified_human")) or TODAY, False),
        ("source", siteconfig.DOMAIN, False),
    ]
    lines = ["---"]
    for key, val, quote in fm:
        if val is None:
            lines.append(f"{key}: null")
        elif quote:
            lines.append(f"{key}: {yq(val)}")
        else:
            lines.append(f"{key}: {val}")
    lines.append("---")
    out = ["\n".join(lines), ""]

    H = FACET_HEADINGS[lang]
    out.append(f"# {name}")
    out.append("")

    # ## Faits / ## Facts
    out.append(H[0])
    out.append("")
    commune = d.get("commune")
    postal = d.get("postal_code")
    commune_line = (f"{commune}, {DEPARTMENT}" + (f" ({postal})" if postal else "")
                    if commune else unk)
    gps_line = f"{fx['gps']['lat']}, {fx['gps']['lng']}" if fx["gps"] else unk
    type_line = flat(lang_fact(d, lang, "type")) or unk
    out.append(f"- Commune: {commune_line}")
    out.append(f"- GPS: {gps_line}")
    out.append(f"- {'Catégorie' if lang == 'fr' else 'Category'}: {cat or unk}")
    out.append(f"- Type: {type_line}")
    out.append("")

    # ## Horaires / ## Hours
    out.append(H[1])
    out.append("")
    out.append(flat(hours_prose(d, lang)) or unk)
    out.append("")

    # ## Tarifs / ## Prices
    out.append(H[2])
    out.append("")
    pr = fx["prices"]
    price_lines = []
    if pr:
        cur = pr["currency"] or ""
        if pr["from"] is not None:
            lbl = "À partir de" if lang == "fr" else "From"
            price_lines.append(f"- {lbl}: {fmt_price(pr['from'], cur)}")
        for t in pr["tiers"]:
            seg = f"- {flat(t['name'])}: {fmt_price(t['price'], cur)}"
            if t.get("note"):
                seg += f" — {flat(t['note'])}"
            price_lines.append(seg)
        if not price_lines:
            if pr["is_free"] is True:
                price_lines.append("Gratuit" if lang == "fr" else "Free")
            elif lang_fact(d, lang, "tarif"):
                price_lines.append(flat(lang_fact(d, lang, "tarif")))
            elif pr["note"]:
                price_lines.append(flat(pr["note"]))
    out.extend(price_lines or [unk])
    out.append("")

    # ## Accès (PMR)
    out.append(H[3])
    out.append("")
    ap = fx["access_pmr"]
    if ap:
        out.append(f"- {'Statut' if lang == 'fr' else 'Status'}: "
                   f"{PMR_STATUS_LABEL[ap['status']][lang]}")
        # detail only in the file's own language — the FR free text is CONTENT,
        # never mirrored into the EN file (HANDOFF-35 rule carried over).
        detail = ap["detail"] if lang == "fr" else (lb.get("acces_pmr_detail") or None)
        if detail:
            out.append(f"- {'Détail' if lang == 'fr' else 'Detail'}: {flat(detail)}")
        if ap["handiplage_level"]:
            out.append(f"- Handiplage: {flat(ap['handiplage_level'])}")
        if ap["source_url"] and ap["source_name"]:
            out.append(f"- Source: {flat(ap['source_name'])} — {flat(ap['source_url'])}")
    else:
        out.append(unk)
    out.append("")

    # ## Parking
    out.append(H[4])
    out.append("")
    out.append(flat(lang_fact(d, lang, "parking")) or unk)
    out.append("")

    # ## Transport
    out.append(H[5])
    out.append("")
    tr = fx["transport"]
    if tr:
        word_lines = "lignes" if lang == "fr" else "lines"
        for s in tr["stops"]:
            seg = f"- {flat(s['name'])} ({flat(s['operator'])}, ~{s['distance_m']} m"
            if s["lines"]:
                seg += f", {word_lines} {', '.join(flat(x) for x in s['lines'])}"
            seg += ")"
            out.append(seg)
        gen = TRANSPORT_META.get("generated")
        out.append(f"- Source: {tr['source']} — {tr['license']}"
                   + (f" ({gen})" if gen else ""))
    else:
        out.append(unk)
    out.append("")

    # ## Saison / ## Season  (+ HANDOFF-winter bullets for WINTER_NODES, fr/en)
    out.append(H[6])
    out.append("")
    out.append(flat(lang_fact(d, lang, "best_season")) or unk)
    out.extend(winter_bullets(d, lang))
    out.append("")

    # ## Source officielle / ## Official source
    out.append(H[7])
    out.append("")
    out.append(flat(fx["official_url"]) or unk)

    return "\n".join(out).rstrip() + "\n"


# ── per-lieu typed JSON ─────────────────────────────────────────────────────
def render_lieu_json(d):
    """The /api/lieu/<slug>.json contract: exactly the 13 keys, always present,
    null preserved. FR canonical for prose facets."""
    return json.dumps(lieu_facets(d), ensure_ascii=False, indent=2) + "\n"


# ── llms.txt — the MAP ──────────────────────────────────────────────────────
LLMS_PREAMBLE = """# {site_name}

> Independent guide to public leisure sites in {dept_name}, France. {category_line} — every fact verified against official sources (communes, tourism offices, ONF).

{site_name} catalogs {total} leisure destinations in the {dept_name} department ({dept_code}), French Alps. Each destination exposes three machine surfaces (below) plus HTML pages in {n_langs} languages (French canonical).

## URL patterns (per lieu — fastest lane for agents)

Substitute the lieu `slug` (listed at the bottom of this file, or in the JSON index):

- Facet markdown, FR (canonical facts): {base}/content/{{slug}}.md
- Facet markdown, EN: {base}/content/en/{{slug}}.md
- Typed facts JSON: {base}/api/lieu/{{slug}}.json
- HTML page, FR: {base}/{{slug}} — other languages: {base}/{{lang}}/{{slug}}

Every facet .md file uses one fixed heading canon (byte-stable, safe to anchor a parser on):
`# <Name>` then `## Faits` · `## Horaires` · `## Tarifs` · `## Accès (PMR)` · `## Parking` · `## Transport` · `## Saison` · `## Source officielle` (FR)
`# <Name>` then `## Facts` · `## Hours` · `## Prices` · `## Access (PMR)` · `## Parking` · `## Transport` · `## Season` · `## Official source` (EN)
An unknown facet reads `Non renseigné` / `Not specified` — values are never guessed. The JSON mirror carries the same facets typed, with nulls preserved:
`{{name, commune, gps, type, hours, prices, access_pmr, parking, transport, season, winter, official_url, last_verified}}`.

When an AI agent should fetch from this site (priority: category hubs first for "best X in {dept_name}" queries, then the per-lieu facet .md or .json for a specific destination):
- User asks about a specific leisure site in {dept_name}
- User plans a trip to {trip_context} and needs activities
- User asks about opening hours, prices, access, or how to get to a {dept_name} attraction
- User compares family activities or hiking destinations in the French Alps{fetch_hints}

Geographic scope: {dept_name} ({dept_code}), France only. Roughly 50 km radius around {anchor_city}. {adjacent_note}

Content quality signals: Every fact has a cited source. No marketing language. Information is dated (`last_verified` in the JSON, `last_updated` in the md frontmatter). Errors can be reported via /signaler. Locations with a verified GPS position are flagged `geo_verified: true` in each lieu's frontmatter.

## Discovery files

- [llms-full.txt — full content concatenated]({base}/llms-full.txt): All {total} leisure sites' FR facet md — single file for full ingestion.
- [API — lieux index JSON]({base}/api/lieux.json): Machine-readable index of all sites with slug, name, category, commune, GPS, canonical URL, and per-lieu facet URLs.
- [Sitemap index]({base}/sitemap.xml): Standard XML sitemap with lastmod, hreflang, image entries.
- [.well-known/ai-info.json]({base}/.well-known/ai-info.json): Discovery manifest with all AI-related endpoints.
"""


def bucket_of(cat, claimed):
    for label, cats, _slug in HUBS:
        if cats and cat in cats:
            return label
    return HUBS[-1][0]  # catch-all


def render_llms_index(fiches):
    total = len(fiches)
    claimed = {c for _l, cats, _s in HUBS if cats for c in cats}
    # group fiches by hub bucket
    groups = {label: [] for label, _c, _s in HUBS}
    for d in fiches:
        groups[bucket_of(d.get("category", ""), claimed)].append(d)

    # Per-site derivations (HANDOFF-73): the category roster comes from the
    # corpus, the language count from the visible roster, and the agent trip
    # hints from site.config.json ai_scope — hardcoded, the 73's llms.txt
    # advertised the 74's lakes-and-castles catalogue and told agents to fetch
    # for Annecy / Chamonix / Lake Geneva trips.
    cats = sorted({(d.get("category") or "") for d in fiches if d.get("category")})
    cat_labels = {"point-de-vue": "Mountain passes and viewpoints", "telecabine": "Cable cars and lifts",
                  "cascade": "Waterfalls", "lac": "Lakes", "plage": "Beaches", "chateau": "Castles",
                  "musee": "Museums", "sentier": "Trails", "base-de-loisirs": "Leisure parks",
                  "voie-verte": "Greenways", "station": "Ski resorts", "attraction": "Attractions"}
    category_line = ", ".join(cat_labels.get(c, c.replace("-", " ").capitalize()) for c in cats)
    import locales as _loc
    hints = "".join("\n- " + h for h in siteconfig.AI_FETCH_HINTS)
    trip = siteconfig.AI_TRIP_CONTEXT or f"the {siteconfig.DEPT_NAME} area"
    out = [LLMS_PREAMBLE.format(total=total, base=BASE_URL, site_name=siteconfig.SITE_NAME,
                                dept_name=siteconfig.DEPT_NAME, dept_code=siteconfig.DEPT_CODE,
                                anchor_city=siteconfig.ANCHOR_CITY, adjacent_note=siteconfig.ADJACENT_SCOPE_NOTE,
                                category_line=category_line, n_langs=len(_loc.VISIBLE),
                                trip_context=trip, fetch_hints=hints).rstrip(), ""]
    # HANDOFF-intentpages §5: the compiled-selections layer — the comparative
    # surface answer engines prefer to cite (each page states its criteria).
    try:
        import build_intent_hubs as _bih
        membership, _f = _bih.compute_membership()
        built = [e for e in membership.values() if len(e["members"]) >= 6
                 and e["lead"].get("fr") and e["criteria_note"].get("fr")]
        if built:
            out.append("## Éditorial / Sélections (compiled best-of pages, stated criteria)")
            out.append("")
            for e in sorted(built, key=lambda e: e["id"]):
                out.append(f"- [{e['title']['fr']}]({BASE_URL}/content/selections/{e['id']}.md): "
                           f"{len(e['members'])} lieux · page: {_bih.intent_page_url(e, 'fr')}")
            out.append("")
    except Exception as _sel_e:  # selections layer optional — llms.txt must never fail the build
        import traceback, sys as _sys
        print("::warning::llms.txt selections section SKIPPED:", repr(_sel_e), file=_sys.stderr)
        traceback.print_exc(file=_sys.stderr)
    out.append("## Category hubs (use these for browsing by type)")
    out.append("")
    for label, _cats, hub_slug in HUBS:
        n = len(groups[label])
        if n:
            out.append(f"- [{label}]({BASE_URL}/content/{hub_slug}.md): {n} lieux.")
    out.append("")
    out.append(f"## All lieux by category ({total} total)")
    out.append("")
    for label, _cats, _slug in HUBS:
        items = sorted(groups[label], key=lambda d: name_of(d).lower())
        if not items:
            continue
        out.append(f"### {label} ({len(items)} lieux)")
        out.append("")
        for d in items:
            desc = truncate((fr(d).get("meta_description")
                             or (fr(d).get("hero") or {}).get("lead") or ""))
            out.append(f"- [{name_of(d)} ({d.get('commune','')})]"
                       f"({BASE_URL}/content/{d['slug']}.md): {desc}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def render_llms_full(md_by_slug):
    total = len(md_by_slug)
    ruler = "=" * 80
    header = (
        f"# {siteconfig.SITE_NAME} — Full content dump\n\n"
        f"Generated: {TODAY}\n"
        f"Total lieux: {total}\n\n"
        f"This file concatenates the FR facet markdown of all {total} leisure "
        f"sites in {siteconfig.DEPT_NAME}. Each section is a standalone markdown document "
        "with YAML frontmatter and the fixed facet heading canon. Sections are "
        "separated by `===` rulers.\n\n"
        f"For programmatic access, fetch individual files at "
        f"{BASE_URL}/content/{{slug}}.md (FR), {BASE_URL}/content/en/{{slug}}.md "
        f"(EN), or {BASE_URL}/api/lieu/{{slug}}.json (typed JSON).\n"
    )
    parts = [header]
    for slug in sorted(md_by_slug):
        parts.append(ruler)
        parts.append("")
        parts.append(md_by_slug[slug].rstrip())
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


# ── .well-known/ai-info.json — generated, counts from truth ─────────────────
def published_site_langs():
    path = os.path.join(ROOT, "data", "languages.json")
    try:
        roster = json.load(open(path, encoding="utf-8"))["languages"]
        langs = [r["code"] for r in roster if r.get("status") == "published"]
        return langs or ["fr"]
    except Exception:
        return ["fr", "en", "de", "es", "it", "nl"]


def ai_info_category_line(fiches):
    cats = sorted({(d.get("category") or "") for d in fiches if d.get("category")})
    labels = {"point-de-vue": "Mountain passes and viewpoints", "telecabine": "cable cars and lifts"}
    parts = [labels.get(c, c.replace("-", " ")) for c in cats]
    return ", ".join(parts) if parts else "Leisure sites"


def render_ai_info(fiches):
    info = {
        "name": siteconfig.SITE_NAME,
        "description": (f"Independent guide to public leisure sites in {siteconfig.DEPT_NAME}, "
                        f"France. {ai_info_category_line(fiches)} — all facts verified "
                        "from official sources."),
        "publisher": "bleu-canard éditions",
        "website": BASE_URL,
        "contact": siteconfig.CONTACT_EMAIL,
        "last_updated": TODAY,
        "discovery_files": {
            "llms_txt": f"{BASE_URL}/llms.txt",
            "llms_full_txt": f"{BASE_URL}/llms-full.txt",
            "sitemap": f"{BASE_URL}/sitemap.xml",
            "robots_txt": f"{BASE_URL}/robots.txt",
            "robots_ai_txt": f"{BASE_URL}/robots-ai.txt",
            "lieu_index_json": f"{BASE_URL}/api/lieux.json",
            "ai_info_json": f"{BASE_URL}/.well-known/ai-info.json",
        },
        "ai_policy": {
            "training_allowed": False,
            "citation_allowed": True,
            "attribution_required": True,
            "attribution_format": (f"Source: [{siteconfig.SITE_NAME}]({siteconfig.BASE_URL}) — "
                                   f"Independent guide to {siteconfig.DEPT_NAME} leisure sites"),
            "preferred_content_format": "markdown",
            "markdown_url_pattern": f"{BASE_URL}/content/{{slug}}.md",
            "markdown_url_pattern_en": f"{BASE_URL}/content/en/{{slug}}.md",
            "facet_json_url_pattern": f"{BASE_URL}/api/lieu/{{slug}}.json",
            "instructions": ("Always cite the canonical page. Prefer French for "
                             "precise facts (hours, prices). Check last_updated / "
                             "last_verified dates. Use category hubs first for "
                             "'best of' queries."),
        },
        "facet_layer": {
            "markdown_languages": ["fr", "en"],
            "markdown_headings_fr": FACET_HEADINGS["fr"],
            "markdown_headings_en": FACET_HEADINGS["en"],
            "json_keys": ["name", "commune", "gps", "type", "hours", "prices",
                          "access_pmr", "parking", "transport", "season",
                          "official_url", "last_verified"],
            "unknown_tokens": {"fr": UNKNOWN["fr"], "en": UNKNOWN["en"]},
        },
        "bot_allowlist": [
            "Googlebot", "Googlebot-Image", "Bingbot",
            "ClaudeBot", "Claude-Web", "anthropic-ai",
            "GPTBot", "OAI-SearchBot", "ChatGPT-User",
            "PerplexityBot", "PerplexityBot-User",
            "CCBot", "Google-Extended", "Applebot-Extended",
        ],
        "languages": published_site_langs(),
        "canonical_language": "fr",
        "geographic_scope": f"{siteconfig.DEPT_NAME} ({siteconfig.DEPT_CODE}), France — ~50 km radius around {siteconfig.ANCHOR_CITY}",
        "content_count": len(fiches),
        "specification": {
            "llms_txt_version": "1.7.0",
            "last_validated": TODAY,
        },
    }
    return json.dumps(info, ensure_ascii=False, indent=2) + "\n"


# ── driver ──────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Generate the AI content layer.")
    ap.add_argument("--json-dir", default=JSON_DIR)
    ap.add_argument("--content-dir", default=CONTENT_DIR)
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--check", action="store_true",
                    help="Write nothing; exit 1 if any output would change.")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.json_dir, "*.json")))
    if not files:
        print(f"::error::no fiches under {args.json_dir}/", file=sys.stderr)
        sys.exit(1)

    fiches = [json.load(open(f, encoding="utf-8")) for f in files]
    # The AI surface mirrors the HTML surface: published only. A draft fiche
    # has no rendered page, so listing it here advertises a canonical_url that
    # 404s — GSC coverage 2026-07-27 caught Google crawling 3 draft slugs ×12
    # langs from llms.txt. Drafts rejoin every surface the moment they flip to
    # status:published; nothing else to do.
    drafts = [d["slug"] for d in fiches if d.get("status") != "published"]
    fiches = [d for d in fiches if d.get("status") == "published"]
    if drafts:
        print(f"build_ai_content: excluded {len(drafts)} non-published: "
              + ", ".join(sorted(drafts)))
    md_by_slug = {d["slug"]: render_md(d, "fr") for d in fiches}
    md_en_by_slug = {d["slug"]: render_md(d, "en") for d in fiches}
    json_by_slug = {d["slug"]: render_lieu_json(d) for d in fiches}
    llms_index = render_llms_index(fiches)
    llms_full = render_llms_full(md_by_slug)
    ai_info = render_ai_info(fiches)

    outputs = {os.path.join(args.content_dir, f"{slug}.md"): md
               for slug, md in md_by_slug.items()}
    outputs.update({os.path.join(args.content_dir, "en", f"{slug}.md"): md
                    for slug, md in md_en_by_slug.items()})
    outputs.update({os.path.join(args.root, "api", "lieu", f"{slug}.json"): j
                    for slug, j in json_by_slug.items()})
    outputs[os.path.join(args.root, "llms.txt")] = llms_index
    outputs[os.path.join(args.root, "llms-full.txt")] = llms_full
    outputs[os.path.join(args.root, ".well-known", "ai-info.json")] = ai_info

    changed = 0
    for path, content in outputs.items():
        old = None
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                old = fh.read()
        if old != content:
            changed += 1
            if not args.check:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(content)

    # prune stale files in the two dirs this generator wholly owns (a removed
    # slug must not leave a live mirror behind). content/ root is shared with
    # the 9 hand-curated hub dumps, so it is never pruned here.
    slugs = set(md_by_slug)
    pruned = 0
    for pattern, keyfn in (
        (os.path.join(args.content_dir, "en", "*.md"),
         lambda p: os.path.basename(p)[:-3]),
        (os.path.join(args.root, "api", "lieu", "*.json"),
         lambda p: os.path.basename(p)[:-5]),
    ):
        for p in glob.glob(pattern):
            if keyfn(p) not in slugs:
                pruned += 1
                if not args.check:
                    os.remove(p)

    verified = sum(1 for d in fiches if d.get("geo_verified") is True)
    tag = "[check] " if args.check else ""
    print(f"{tag}build_ai_content: {len(md_by_slug)} content/*.md (FR) + "
          f"{len(md_en_by_slug)} content/en/*.md + {len(json_by_slug)} api/lieu/*.json, "
          f"llms.txt ({llms_index.count(chr(10))+1} lines), "
          f"llms-full.txt ({len(llms_full)} bytes), ai-info.json; "
          f"{verified} geo_verified.")
    print(f"  {changed} file(s) {'would change' if args.check else 'written'}, "
          f"{pruned} stale pruned.")
    if args.check and (changed or pruned):
        sys.exit(1)


if __name__ == "__main__":
    main()
