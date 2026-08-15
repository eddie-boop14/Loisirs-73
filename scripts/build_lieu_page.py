#!/usr/bin/env python3
"""Generate a lieu HTML page from a batch JSON, in any supported locale.

Usage:
    python3 scripts/build_lieu_page.py <batch.json> [--lang fr|en|de|it|es|nl] [--out-dir DIR]

Reads JSON shape produced by batch_activites / batch_plages
(i18n.<lang>.{name, meta_title, meta_description, hero, hero_alt, facts,
body, activities, practical_info, how_to_get_there, when_to_visit,
events, faq, schema_amenities}).

For non-FR builds, reads i18n.<lang> with field-level fallback to i18n.fr.
Chrome strings (section headings, CTA labels, breadcrumb, etc.) are
translated via the CHROME table.

Produces a single-file HTML page at <out_dir>/<slug>.html.
"""
import argparse
import siteconfig  # HANDOFF-73: per-site identity
import html as html_lib
import json
import math
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from picture_tag import picture_tag
import locales  # noqa: E402
import assets  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
BASE_URL = siteconfig.BASE_URL


# Authored inline HTML allowed in prose fields (HANDOFF-23). A string carrying
# one of these tags is trusted, repo-authored content and is emitted RAW; plain
# text keeps the escaping path (so a stray '<' or '&' in ordinary prose stays
# safe and page bytes stay stable).
AUTHORED_TAG_RE = re.compile(r"</?(p|ul|ol|li|strong|em|a|br|b|i)\b", re.I)


def emit_prose(s):
    """Raw-emit for authored-HTML prose fields (when_to_visit, events,
    how_to_get_there, practical_info, activities). Escaping this content
    printed literal '<strong>' on live pages; translations preserve the
    source's tag structure (HANDOFF-25 validators), so they flow through
    the same path."""
    if s is None:
        return ""
    s = str(s)
    return s if AUTHORED_TAG_RE.search(s) else esc(s)


def esc(s):
    """HTML-escape, treating None as empty."""
    if s is None:
        return ""
    return html_lib.escape(str(s), quote=False)


def attr(s):
    """HTML-escape for attribute values."""
    if s is None:
        return ""
    return html_lib.escape(str(s), quote=True)


def url_q(s):
    """URL-encode for query string."""
    return quote(str(s), safe="")


def load_static_blocks():
    """Read canonical CSS + trailing JS from scripts/static/*.

    Source of truth: scripts/static/style.css and scripts/static/script.html.
    These are NEVER overwritten by a build, which makes the rebuild idempotent
    across cycles (the bug they fix: when CSS was extracted from a live fiche
    page that was also a rebuild target, each cycle appended another copy of
    the partner-logo rule into the next cycle's template).
    """
    static_dir = REPO / "scripts" / "static"
    css = (static_dir / "style.css").read_text(encoding="utf-8")
    js = (static_dir / "script.html").read_text(encoding="utf-8")
    return css, js


CSS, JS = load_static_blocks()


def load_transport_index():
    """Load data/transport_index.json (built by scripts/build_transport_index.py).
    Returns (index, operators) where index maps slug -> {verified, source,
    license, stops[]} and operators maps operator-label -> {url, fare_url}
    (read verbatim from each feed's agency.txt). Empty if absent."""
    p = REPO / "data" / "transport_index.json"
    if not p.exists():
        return {}, {}
    raw = json.loads(p.read_text(encoding="utf-8"))
    operators = (raw.get("_meta", {}) or {}).get("operators", {}) or {}
    index = {k: v for k, v in raw.items() if k != "_meta"}
    return index, operators


def load_network_fares():
    """Load data/network_fares.json — manually verified, dated single-ride fares
    + official tariff URLs per operator. Maps operator-label -> {fare, tariff_url}."""
    p = REPO / "data" / "network_fares.json"
    if not p.exists():
        return {}
    raw = json.loads(p.read_text(encoding="utf-8"))
    return raw.get("operators", {}) or {}


def load_parking_index():
    """Load data/parking_index.json (built by scripts/build_parking_index.py).
    Returns (index, attribution) where index maps slug -> {verified, source,
    license, parkings[]}. Empty if absent."""
    p = REPO / "data" / "parking_index.json"
    if not p.exists():
        return {}, ""
    raw = json.loads(p.read_text(encoding="utf-8"))
    attrib = (raw.get("_meta", {}) or {}).get("attribution", "")
    index = {k: v for k, v in raw.items() if k != "_meta"}
    return index, attrib


TRANSPORT_INDEX, TRANSPORT_OPERATORS = load_transport_index()
NETWORK_FARES = load_network_fares()
PARKING_INDEX, PARKING_ATTRIB = load_parking_index()


# Map JSON fact keys → French labels for the facts grid
FACT_LABELS = {
    "type": "Type",
    "access": "Accès",
    "tarif": "Tarif",
    "commune": "Commune",
    "parking": "Parking",
    "dogs": "Animaux",
    "stroller": "Poussette / PMR",
    "duration": "Durée",
    "best_season": "Meilleure saison",
    "lac": "Lac",
    "surveillance": "Surveillance",
    "pavillon_bleu_2026": "Pavillon Bleu 2026",
}
FACT_ORDER = [
    "type", "access", "tarif", "lac", "surveillance",
    "pavillon_bleu_2026", "duration", "best_season",
    "parking", "dogs", "stroller", "commune",
]


SUPPORTED_LANGS = list(locales.PROSE)

# Per-locale chrome strings (everything outside JSON content). Keep keys terse;
# T(key) reaches into CHROME[key][_LANG].
CHROME = {
    "html_lang":       {"fr": "fr", "en": "en", "de": "de", "it": "it", "es": "es", "nl": "nl"},
    "og_locale":       {"fr": "fr_FR", "en": "en_US", "de": "de_DE", "it": "it_IT", "es": "es_ES", "nl": "nl_NL"},
    "in_lang":         {"fr": "fr-FR", "en": "en-US", "de": "de-DE", "it": "it-IT", "es": "es-ES", "nl": "nl-NL"},
    "skip":            {"fr": "Aller au contenu", "en": "Skip to content", "de": "Zum Inhalt springen", "it": "Vai al contenuto", "es": "Saltar al contenido", "nl": "Naar inhoud springen"},
    "home":            {"fr": "Accueil", "en": "Home", "de": "Startseite", "it": "Home", "es": "Inicio", "nl": "Startpagina"},
    "lang_label":      {"fr": "FR", "en": "EN", "de": "DE", "it": "IT", "es": "ES", "nl": "NL"},
    "lang_choose":     {"fr": "Choisir la langue", "en": "Choose a language", "de": "Sprache wählen", "it": "Scegli una lingua", "es": "Elegir idioma", "nl": "Kies een taal"},
    "lang_native":     locales.endonyms(locales.VISIBLE),  # isolation-ok: picker endonyms (pl in switcher)
    # Section kickers (small caps eyebrow above each h2)
    "k_glance":        {"fr": "En un coup d&#39;œil", "en": "At a glance", "de": "Auf einen Blick", "it": "In sintesi", "es": "De un vistazo", "nl": "In een oogopslag"},
    "k_activities":    {"fr": "Activités", "en": "Activities", "de": "Aktivitäten", "it": "Attività", "es": "Actividades", "nl": "Activiteiten"},
    "k_practical":     {"fr": "Pratique", "en": "Practical", "de": "Praktisches", "it": "Pratico", "es": "Práctica", "nl": "Praktisch"},
    "k_access":        {"fr": "Accès", "en": "Access", "de": "Anreise", "it": "Accesso", "es": "Acceso", "nl": "Toegang"},
    "k_when":          {"fr": "Quand venir", "en": "When to visit", "de": "Wann besuchen", "it": "Quando visitare", "es": "Cuándo visitar", "nl": "Wanneer bezoeken"},
    "k_partners":      {"fr": "À proximité", "en": "Nearby", "de": "In der Nähe", "it": "Nelle vicinanze", "es": "Cerca", "nl": "In de buurt"},
    "k_photos":        {"fr": "Photos", "en": "Photos", "de": "Fotos", "it": "Foto", "es": "Fotos", "nl": "Foto's"},
    "k_faq":           {"fr": "FAQ", "en": "FAQ", "de": "FAQ", "it": "FAQ", "es": "FAQ", "nl": "FAQ"},
    "k_sources":       {"fr": "Sources", "en": "Sources", "de": "Quellen", "it": "Fonti", "es": "Fuentes", "nl": "Bronnen"},
    "k_see_also":      {"fr": "Voir aussi", "en": "See also", "de": "Siehe auch", "it": "Vedi anche", "es": "Ver también", "nl": "Zie ook"},
    # H2 headings
    "h_whatis":        {"fr": "Qu&#39;est-ce que", "en": "What is", "de": "Was ist", "it": "Cos&#39;è", "es": "Qué es", "nl": "Wat is"},
    "h_activities":    {"fr": "Ce qu&#39;on peut y faire", "en": "What you can do here", "de": "Was man hier machen kann", "it": "Cosa si può fare", "es": "Qué se puede hacer", "nl": "Wat je hier kunt doen"},
    "h_practical":     {"fr": "Infos pratiques", "en": "Practical information", "de": "Praktische Informationen", "it": "Informazioni pratiche", "es": "Información práctica", "nl": "Praktische informatie"},
    "h_how":           {"fr": "Comment y aller", "en": "How to get there", "de": "So kommen Sie hin", "it": "Come arrivare", "es": "Cómo llegar", "nl": "Hoe te komen"},
    "h_when":          {"fr": "Quand visiter", "en": "When to visit", "de": "Wann besuchen", "it": "Quando visitare", "es": "Cuándo visitar", "nl": "Wanneer bezoeken"},
    "h_partners":      {"fr": "Où manger, boire, dormir", "en": "Where to eat, drink, stay", "de": "Essen, Trinken, Übernachten", "it": "Dove mangiare, bere, dormire", "es": "Dónde comer, beber, alojarse", "nl": "Waar eten, drinken, overnachten"},
    "h_gallery":       {"fr": "Galerie", "en": "Gallery", "de": "Galerie", "it": "Galleria", "es": "Galería", "nl": "Galerij"},
    "h_faq":           {"fr": "Questions fréquentes", "en": "Frequently asked questions", "de": "Häufige Fragen", "it": "Domande frequenti", "es": "Preguntas frecuentes", "nl": "Veelgestelde vragen"},
    "h_sources":       {"fr": "Sources &amp; vérifications", "en": "Sources &amp; verification", "de": "Quellen &amp; Prüfung", "it": "Fonti &amp; verifiche", "es": "Fuentes &amp; verificaciones", "nl": "Bronnen &amp; verificatie"},
    # Hero / CTAs
    "free_dot":        {"fr": "Gratuit · Accès libre", "en": "Free · Open access", "de": "Kostenlos · Freier Zugang", "it": "Gratis · Accesso libero", "es": "Gratis · Acceso libre", "nl": "Gratis · Vrije toegang"},
    "paid_dot":        {"fr": "Payant · Réservation en ligne", "en": "Paid · Book online", "de": "Kostenpflichtig · Online buchen", "it": "A pagamento · Prenota online", "es": "De pago · Reservar en línea", "nl": "Betaald · Online reserveren"},
    "paid_prefix":     {"fr": "Payant · ", "en": "Paid · ", "de": "Kostenpflichtig · ", "it": "A pagamento · ", "es": "De pago · ", "nl": "Betaald · "},
    "free_word":       {"fr": "Gratuit", "en": "Free", "de": "Kostenlos", "it": "Gratis", "es": "Gratis", "nl": "Gratis"},
    "book":            {"fr": "Réserver", "en": "Book", "de": "Buchen", "it": "Prenota", "es": "Reservar", "nl": "Reserveren"},
    "map_view":        {"fr": "Voir sur la carte", "en": "View on map", "de": "Auf Karte ansehen", "it": "Vedi sulla mappa", "es": "Ver en el mapa", "nl": "Bekijk op kaart"},
    "official_site":   {"fr": "Site officiel", "en": "Official site", "de": "Offizielle Website", "it": "Sito ufficiale", "es": "Sitio oficial", "nl": "Officiële site"},
    "directions":      {"fr": "Itinéraire", "en": "Directions", "de": "Wegbeschreibung", "it": "Indicazioni", "es": "Cómo llegar", "nl": "Route"},
    "maps_open":       {"fr": "Ouvrir dans Maps", "en": "Open in Maps", "de": "In Maps öffnen", "it": "Apri in Maps", "es": "Abrir en Maps", "nl": "Openen in Maps"},
    # How-to mode labels
    "how_car":         {"fr": "En voiture", "en": "By car", "de": "Mit dem Auto", "it": "In auto", "es": "En coche", "nl": "Met de auto"},
    "how_transit":     {"fr": "Transports en commun", "en": "Public transport", "de": "Öffentliche Verkehrsmittel", "it": "Trasporti pubblici", "es": "Transporte público", "nl": "Openbaar vervoer"},
    "how_bike":        {"fr": "À vélo", "en": "By bike", "de": "Mit dem Fahrrad", "it": "In bici", "es": "En bici", "nl": "Met de fiets"},
    "events_label":    {"fr": "Événements", "en": "Events", "de": "Veranstaltungen", "it": "Eventi", "es": "Eventos", "nl": "Evenementen"},
    # Generated transit block (nearest GTFS stops). Only the labels translate —
    # stop / operator / line names are proper nouns, kept verbatim in all langs.
    "transit_nearest":  {"fr": "Arrêts les plus proches", "en": "Nearest stops", "de": "Nächste Haltestellen", "it": "Fermate più vicine", "es": "Paradas más cercanas", "nl": "Dichtstbijzijnde haltes"},
    "transit_verified": {"fr": "Données transport vérifiées le", "en": "Transport data verified on", "de": "Verkehrsdaten geprüft am", "it": "Dati sui trasporti verificati il", "es": "Datos de transporte verificados el", "nl": "Vervoersgegevens geverifieerd op"},
    "transit_source":   {"fr": "source", "en": "source", "de": "Quelle", "it": "fonte", "es": "fuente", "nl": "bron"},
    "transit_official": {"fr": "Tarifs &amp; horaires officiels", "en": "Official fares &amp; timetables", "de": "Offizielle Tarife &amp; Fahrpläne", "it": "Tariffe e orari ufficiali", "es": "Tarifas y horarios oficiales", "nl": "Officiële tarieven &amp; dienstregeling"},
    "transit_fare":     {"fr": "Tarif", "en": "Fare", "de": "Tarif", "it": "Tariffa", "es": "Tarifa", "nl": "Tarief"},
    # Parking block (nearest OSM lots + honest tri-state fee badge). Labels only.
    "park_title":       {"fr": "Stationnement", "en": "Parking", "de": "Parken", "it": "Parcheggio", "es": "Aparcamiento", "nl": "Parkeren"},
    "park_free":        {"fr": "Gratuit", "en": "Free", "de": "Kostenlos", "it": "Gratis", "es": "Gratis", "nl": "Gratis"},
    "park_paid":        {"fr": "Payant", "en": "Paid", "de": "Kostenpflichtig", "it": "A pagamento", "es": "De pago", "nl": "Betaald"},
    "park_conditional": {"fr": "Sous conditions", "en": "Conditional", "de": "Bedingt", "it": "Condizionato", "es": "Con condiciones", "nl": "Voorwaardelijk"},
    "park_unknown":     {"fr": "À vérifier", "en": "To check", "de": "Zu prüfen", "it": "Da verificare", "es": "Por confirmar", "nl": "Te controleren"},
    "park_goto":        {"fr": "Y aller", "en": "Go", "de": "Hinfahren", "it": "Vai", "es": "Ir", "nl": "Erheen"},
    "park_capacity":    {"fr": "places", "en": "spaces", "de": "Plätze", "it": "posti", "es": "plazas", "nl": "plaatsen"},
    "park_verified":    {"fr": "Parkings vérifiés le", "en": "Parking checked on", "de": "Parkplätze geprüft am", "it": "Parcheggi verificati il", "es": "Aparcamientos verificados el", "nl": "Parkings geverifieerd op"},
    # Beside-facts source link (master to-do #4): authoritative page one tap away.
    "source_official":  {"fr": "Source officielle", "en": "Official source", "de": "Offizielle Quelle", "it": "Fonte ufficiale", "es": "Fuente oficial", "nl": "Officiële bron"},
    # Earn-only geo ✅ badge (derive_geo_verified.py). Gold = verified-only per
    # J4-BRAND. Label translates; the place name is frozen and not in the label.
    "geo_verified":     {"fr": f"Position vérifiée par {siteconfig.DOMAIN}", "en": f"Location verified by {siteconfig.DOMAIN}", "de": f"Standort geprüft von {siteconfig.DOMAIN}", "it": f"Posizione verificata da {siteconfig.DOMAIN}", "es": f"Ubicación verificada por {siteconfig.DOMAIN}", "nl": f"Locatie geverifieerd door {siteconfig.DOMAIN}"},
    # Event modal (per-fiche promo for the venue's own event)
    "ev_intro":  {"fr": "Le lieu de cette page organise", "en": "The venue on this page is hosting", "de": "Der Ort dieser Seite veranstaltet", "it": "Il luogo di questa pagina organizza", "es": "El lugar de esta página organiza", "nl": "De locatie op deze pagina organiseert"},
    "ev_cta":    {"fr": "Voir l&#39;événement", "en": "See the event", "de": "Zur Veranstaltung", "it": "Scopri l&#39;evento", "es": "Ver el evento", "nl": "Bekijk het evenement"},
    "ev_close":  {"fr": "Fermer", "en": "Close", "de": "Schließen", "it": "Chiudi", "es": "Cerrar", "nl": "Sluiten"},
    # Flip-card hints
    "tap_to_read":     {"fr": "Toucher pour lire", "en": "Tap to read", "de": "Tippen zum Lesen", "it": "Tocca per leggere", "es": "Toca para leer", "nl": "Tik om te lezen"},
    "hover_for_site":  {"fr": "Survoler pour voir le site", "en": "Hover to view site", "de": "Bewegen für Website", "it": "Passa sopra per il sito", "es": "Pasa para ver el sitio", "nl": "Hover voor de site"},
    "see_site":        {"fr": "Voir le site", "en": "Visit site", "de": "Website ansehen", "it": "Vedi il sito", "es": "Ver el sitio", "nl": "Bekijk site"},
    # Partner card chrome
    "partner_badge":   {"fr": "Partenaire", "en": "Partner", "de": "Partner", "it": "Partner", "es": "Socio", "nl": "Partner"},
    "partner_nearby":  {"fr": "À proximité", "en": "Nearby", "de": "In der Nähe", "it": "Nelle vicinanze", "es": "Cerca", "nl": "In de buurt"},
    "p_address":       {"fr": "Adresse", "en": "Address", "de": "Adresse", "it": "Indirizzo", "es": "Dirección", "nl": "Adres"},
    "p_phone":         {"fr": "Téléphone", "en": "Phone", "de": "Telefon", "it": "Telefono", "es": "Teléfono", "nl": "Telefoon"},
    "p_email":         {"fr": "Email", "en": "Email", "de": "E-Mail", "it": "Email", "es": "Email", "nl": "E-mail"},
    "p_hours":         {"fr": "Horaires", "en": "Hours", "de": "Öffnungszeiten", "it": "Orari", "es": "Horarios", "nl": "Openingstijden"},
    "become_partner":  {"fr": "Devenir partenaire", "en": "Become a partner", "de": "Partner werden", "it": "Diventa partner", "es": "Convertirse en socio", "nl": "Partner worden"},
    # Default-invite teasers (fall-back partner cards when none configured)
    "invite_resto_t":  {"fr": "Un restaurant", "en": "A restaurant", "de": "Ein Restaurant", "it": "Un ristorante", "es": "Un restaurante", "nl": "Een restaurant"},
    "invite_resto_d":  {"fr": "Vous accueillez les visiteurs de", "en": "Hosting visitors of", "de": "Empfangen Sie Besucher von", "it": "Accogli i visitatori di", "es": "¿Recibe a los visitantes de", "nl": "Verwelkomt u bezoekers van"},
    "invite_resto_d2": {"fr": "Apparaissez ici.", "en": "Appear here.", "de": "Zeigen Sie sich hier.", "it": "Apparite qui.", "es": "Aparezca aquí.", "nl": "Verschijn hier."},
    "invite_com_t":    {"fr": "Une boulangerie, un commerce", "en": "A bakery, a shop", "de": "Bäckerei oder Geschäft", "it": "Una panetteria, un negozio", "es": "Una panadería, un comercio", "nl": "Een bakker, een winkel"},
    "invite_com_d":    {"fr": "Partagez horaires et spécialités avec les visiteurs de", "en": "Share hours and specialties with visitors of", "de": "Teilen Sie Öffnungszeiten und Spezialitäten mit Besuchern von", "it": "Condividi orari e specialità con i visitatori di", "es": "Comparta horarios y especialidades con los visitantes de", "nl": "Deel openingstijden en specialiteiten met bezoekers van"},
    "invite_hosp_t":   {"fr": "Un hébergement proche", "en": "A nearby stay", "de": "Übernachtung in der Nähe", "it": "Un alloggio vicino", "es": "Un alojamiento cercano", "nl": "Een nabijgelegen verblijf"},
    "invite_hosp_d":   {"fr": "Gîte, chambre d&#39;hôtes, camping, location", "en": "Gîte, B&amp;B, campsite, rental", "de": "Ferienhaus, B&amp;B, Campingplatz, Vermietung", "it": "Gîte, B&amp;B, campeggio, affitto", "es": "Gîte, B&amp;B, camping, alquiler", "nl": "Gîte, B&amp;B, camping, verhuur"},
    "in_town":         {"fr": "à", "en": "in", "de": "in", "it": "a", "es": "en", "nl": "in"},
    "qmark":           {"fr": " ?", "en": "?", "de": "?", "it": "?", "es": "?", "nl": "?"},
    # Gallery invite
    "g_been_q":        {"fr": "Vous y êtes allé ?", "en": "Been there?", "de": "Schon dort gewesen?", "it": "Ci sei stato?", "es": "¿Ha estado allí?", "nl": "Bent u er geweest?"},
    "g_invite":        {"fr": f"Partagez vos photos — nous les ajoutons à cette page avec votre crédit. Tag #{siteconfig.WORDMARK} ou écrivez à", "en": f"Share your photos — we&#39;ll add them to this page with credit. Tag #{siteconfig.WORDMARK} or email", "de": f"Teilen Sie Ihre Fotos — wir fügen sie mit Bildnachweis hinzu. Tag #{siteconfig.WORDMARK} oder schreiben Sie an", "it": f"Condividi le tue foto — le aggiungiamo con il tuo credito. Tag #{siteconfig.WORDMARK} o scrivi a", "es": f"Comparta sus fotos — las añadimos con crédito. Tag #{siteconfig.WORDMARK} o escriba a", "nl": f"Deel uw foto&#39;s — wij voegen ze met credit toe. Tag #{siteconfig.WORDMARK} of mail naar"},
    # Sources caveat
    "src_caveat":      {"fr": "Vérifications multi-sources à la date de publication. Les informations peuvent évoluer — confirmez auprès du gestionnaire officiel avant un déplacement.", "en": "Multi-source verification at publication. Information may change — confirm with the official operator before travelling.", "de": "Mehrquellen-Verifizierung zum Veröffentlichungsdatum. Informationen können sich ändern — bestätigen Sie diese vor der Anreise beim offiziellen Betreiber.", "it": "Verifica multi-fonte alla data di pubblicazione. Le informazioni possono cambiare — confermare con il gestore ufficiale prima del viaggio.", "es": "Verificación multi-fuente en la fecha de publicación. La información puede cambiar — confirme con el operador oficial antes de viajar.", "nl": "Multi-bron verificatie bij publicatie. Informatie kan veranderen — bevestig bij de officiële beheerder vóór vertrek."},
    "data_partial":    {"fr": "Données partielles :", "en": "Partial data:", "de": "Teildaten:", "it": "Dati parziali:", "es": "Datos parciales:", "nl": "Gedeeltelijke gegevens:"},
    "via":             {"fr": "via", "en": "via", "de": "via", "it": "via", "es": "vía", "nl": "via"},
    # Footer dates
    "published":       {"fr": "Publié le", "en": "Published", "de": "Veröffentlicht", "it": "Pubblicato il", "es": "Publicado el", "nl": "Gepubliceerd"},
    "updated":         {"fr": "Mis à jour le", "en": "Updated", "de": "Aktualisiert", "it": "Aggiornato il", "es": "Actualizado el", "nl": "Bijgewerkt"},
    # Share button (PWA-share handoff)
    "share":           {"fr": "Partager", "en": "Share", "de": "Teilen", "it": "Condividi", "es": "Compartir", "nl": "Delen"},
    "link_copied":     {"fr": "Lien copié ✓", "en": "Link copied ✓", "de": "Link kopiert ✓", "it": "Link copiato ✓", "es": "Enlace copiado ✓", "nl": "Link gekopieerd ✓"},
    # Generic photo overlay text (CSS post-process)
    "generic":         {"fr": "Générique", "en": "Generic", "de": "Generisch", "it": "Generico", "es": "Genérico", "nl": "Algemeen"},
    # Photo email subject prefix
    "photos_subject":  {"fr": "Photos%20—%20", "en": "Photos%20—%20", "de": "Fotos%20—%20", "it": "Foto%20—%20", "es": "Fotos%20—%20", "nl": "Foto%27s%20—%20"},
    # Site footer columns
    "f_tagline":       {"fr": f"Guide indépendant des lieux de loisirs en {siteconfig.dept_name('fr')}. 100% gratuit. 100% vérifié.", "en": f"Independent guide to leisure spots in {siteconfig.dept_name('en')}. 100% free. 100% verified.", "de": f"Unabhängiger Freizeit-Guide für {siteconfig.dept_name('de')}. 100% kostenlos. 100% geprüft.", "it": f"Guida indipendente ai luoghi di svago in {siteconfig.dept_name('it')}. 100% gratis. 100% verificato.", "es": f"Guía independiente de los lugares de ocio en {siteconfig.dept_name('es')}. 100% gratis. 100% verificado.", "nl": f"Onafhankelijke gids voor vrijetijdsbestedingen in {siteconfig.dept_name('nl')}. Gratis. Geverifieerd."},
    "f_explore":       {"fr": "Explorer", "en": "Explore", "de": "Entdecken", "it": "Esplora", "es": "Explorar", "nl": "Verkennen"},
    "f_contribute":    {"fr": "Contribuer", "en": "Contribute", "de": "Beitragen", "it": "Contribuisci", "es": "Contribuir", "nl": "Bijdragen"},
    "f_send_photos":   {"fr": "Envoyer des photos", "en": "Send photos", "de": "Fotos senden", "it": "Invia foto", "es": "Enviar fotos", "nl": "Foto&#39;s sturen"},
    "f_report":        {"fr": "Signaler une info", "en": "Report info", "de": "Info melden", "it": "Segnala info", "es": "Reportar info", "nl": "Info melden"},
    "f_become_p":      {"fr": "Devenir partenaire", "en": "Become a partner", "de": "Partner werden", "it": "Diventa partner", "es": "Hacerse socio", "nl": "Partner worden"},
    "f_legal":         {"fr": "Mentions", "en": "Legal", "de": "Rechtliches", "it": "Note legali", "es": "Legal", "nl": "Juridisch"},
    "f_legal_link":    {"fr": "Mentions légales", "en": "Legal notice", "de": "Impressum", "it": "Note legali", "es": "Avisos legales", "nl": "Wettelijke vermeldingen"},
    "f_privacy":       {"fr": "Confidentialité", "en": "Privacy", "de": "Datenschutz", "it": "Privacy", "es": "Privacidad", "nl": "Privacy"},
    "f_cgv":           {"fr": "CGV", "en": "Terms", "de": "AGB", "it": "Termini", "es": "Términos", "nl": "Algemene voorwaarden"},
    "f_copyright":     {"fr": "© 2026 Bleu canard édition · Edmaster &amp; Claudius · Tous droits réservés", "en": "© 2026 Bleu canard édition · Edmaster &amp; Claudius · All rights reserved", "de": "© 2026 Bleu canard édition · Edmaster &amp; Claudius · Alle Rechte vorbehalten", "it": "© 2026 Bleu canard édition · Edmaster &amp; Claudius · Tutti i diritti riservati", "es": "© 2026 Bleu canard édition · Edmaster &amp; Claudius · Todos los derechos reservados", "nl": "© 2026 Bleu canard édition · Edmaster &amp; Claudius · Alle rechten voorbehouden"},
    # The sibling line states the SHARED STANDARD, not the mere existence of another
    # site. "Also in Haute-Savoie" is a directory entry: it gives a reader no reason
    # to click. Both sites verify every fact against an official source and disclose
    # contradictions instead of picking one — that is the thing worth carrying across
    # the link, and it is true on both sides. No hierarchy, no family metaphor, and
    # nothing that drifts. Renders as: {label} {dept} : {site}.
    "f_sister":        {"fr": "Même exigence en", "en": "Same standard in", "de": "Gleicher Anspruch in", "it": "Stesso rigore in", "es": "El mismo rigor en", "nl": "Dezelfde maatstaf in", "pl": "Ten sam standard w", "pt": "O mesmo rigor em", "cs": "Stejný standard v", "ar": "المعيار نفسه في", "he": "אותו סטנדרט ב", "ja": "同じ基準で"},
    "f_promise":       {"fr": "Sans pub. Sans tracking. Sans avis Google.", "en": "No ads. No tracking. No Google reviews.", "de": "Keine Werbung. Kein Tracking. Keine Google-Bewertungen.", "it": "Niente pubblicità. Niente tracking. Niente recensioni Google.", "es": "Sin anuncios. Sin tracking. Sin reseñas de Google.", "nl": "Geen advertenties. Geen tracking. Geen Google reviews."},
}

# Per-locale FACT_LABELS for the facts grid
FACT_LABELS_I18N = {
    "type":        {"fr": "Type", "en": "Type", "de": "Typ", "it": "Tipo", "es": "Tipo", "nl": "Type"},
    "access":      {"fr": "Accès", "en": "Access", "de": "Anreise", "it": "Accesso", "es": "Acceso", "nl": "Toegang"},
    "tarif":       {"fr": "Tarif", "en": "Price", "de": "Preis", "it": "Prezzo", "es": "Precio", "nl": "Prijs"},
    "commune":     {"fr": "Commune", "en": "Town", "de": "Ort", "it": "Comune", "es": "Comuna", "nl": "Gemeente"},
    "parking":     {"fr": "Parking", "en": "Parking", "de": "Parkplatz", "it": "Parcheggio", "es": "Aparcamiento", "nl": "Parkeren"},
    "dogs":        {"fr": "Animaux", "en": "Animals", "de": "Tiere", "it": "Animali", "es": "Animales", "nl": "Dieren"},
    "stroller":    {"fr": "Poussette / PMR", "en": "Stroller / Reduced mobility", "de": "Kinderwagen / Behinderte", "it": "Passeggino / Disabilità", "es": "Cochecito / PMR", "nl": "Kinderwagen / Mindervaliden"},
    "duration":    {"fr": "Durée", "en": "Duration", "de": "Dauer", "it": "Durata", "es": "Duración", "nl": "Duur"},
    "best_season": {"fr": "Meilleure saison", "en": "Best season", "de": "Beste Saison", "it": "Stagione migliore", "es": "Mejor temporada", "nl": "Beste seizoen"},
    "lac":         {"fr": "Lac", "en": "Lake", "de": "See", "it": "Lago", "es": "Lago", "nl": "Meer"},
    "surveillance":{"fr": "Surveillance", "en": "Lifeguarded", "de": "Bewacht", "it": "Sorvegliato", "es": "Vigilado", "nl": "Bewaakt"},
    "pavillon_bleu_2026": {"fr": "Pavillon Bleu 2026", "en": "Blue Flag 2026", "de": "Blaue Flagge 2026", "it": "Bandiera Blu 2026", "es": "Bandera Azul 2026", "nl": "Blauwe Vlag 2026"},
}

# Merge the facts→prose languages' rich chrome (HANDOFF-22) from data, so the
# rich renderer can produce pl/pt/cs/ja/ar/he pages once their per-fiche prose
# lands. Translations live in data/rich-chrome-langs.json (reviewable, like the
# roster). Until a language is in SUPPORTED_LANGS (locales.PROSE) these entries
# are dormant — present but never rendered, so this changes no current output.
_RICH_CHROME = json.loads((REPO / "data" / "rich-chrome-langs.json").read_text(encoding="utf-8"))
for _lg, _vals in _RICH_CHROME["chrome"].items():
    for _k, _v in _vals.items():
        CHROME[_k][_lg] = _v
for _sk, _codes in _RICH_CHROME["locale_codes"].items():
    CHROME[_sk].update(_codes)
for _lg, _vals in _RICH_CHROME["fact_labels"].items():
    for _k, _v in _vals.items():
        FACT_LABELS_I18N[_k][_lg] = _v

# Real per-lieu lastmod (HANDOFF lastmod). Single source: data/lastmod.json,
# derived by scripts/derive_lastmod.py from git content-commit dates (corpus-wide
# sweeps excluded). Read by three consumers — the visible jj/mm/aa stamp, the
# schema.org dateModified (ISO), and (via the manifest) the sitemap. Supersedes
# the manual date_modified_human field, kept in Json for schema stability.
try:
    _LASTMOD = json.loads((REPO / "data" / "lastmod.json").read_text(encoding="utf-8"))
except Exception:
    _LASTMOD = {}

# Protected partner domains. A page that will carry one takes the byte-frozen
# path: it keeps the old manual stamp, gets no dateModified and no share button —
# so the gate_protected_placements byte-guard stays green with no approval
# trailer. The handoff defers the new stamp/share on these to Eddie's separately
# approved commit.
_PROTECTED_PARTNER_DOMAINS = ("cheznousalaplage.com", "chaletdutornet.com")

# The authoritative set of pages that carry a protected partner domain is the
# gate's own manifest (reports/protected-placements.md) — the same set it byte-
# checks. Some placements are injected by cross-fiche promos not present in a
# fiche's own data, so a data-only heuristic under-detects; the manifest is
# ground truth. Freeze any fiche whose output path is listed here.
def _load_protected_pages():
    p = REPO / "reports" / "protected-placements.md"
    pages = set()
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.startswith("| ") and ".html |" in line:
                cell = line.split("|")[1].strip()
                if cell and cell != "page":
                    pages.add(cell)
    except Exception:
        pass
    return pages


_PROTECTED_PAGES = _load_protected_pages()

# Module-level locale state set by build_page(d, lang).
_LANG = "fr"            # current locale
_FROZEN = False         # current page carries a protected partner → byte-frozen
_LOC = None             # i18n.<lang> block, frozen-merged with FR fallback below
_FR = None              # i18n.fr block (fallback source)
_FALLBACK_FIELDS = set()  # fields where current build fell back to FR
_AVAILABLE_LANGS = ("fr",)  # langs this fiche actually has populated in i18n (for hreflang block)


def T(key):
    """Chrome string lookup with FR-fallback."""
    row = CHROME.get(key, {})
    return row.get(_LANG) or row.get("fr") or ""


def _set_lang(d, lang):
    """Wire module-level state for the current build pass."""
    global _LANG, _LOC, _FR, _FALLBACK_FIELDS, _AVAILABLE_LANGS
    _LANG = lang if lang in SUPPORTED_LANGS else "fr"
    i18n = d.get("i18n", {}) or {}
    _FR = i18n.get("fr") or {}
    _LOC = i18n.get(_LANG) or {}
    _FALLBACK_FIELDS = set()
    _AVAILABLE_LANGS = tuple(L for L in SUPPORTED_LANGS if L in i18n and i18n.get(L))


# Strict-prose mode (facts-lang rich render, HANDOFF-22/26): a missing locale
# field is OMITTED instead of FR-filled — a new language never shows FR prose.
# Only frozen-by-design fields may still fall back. The six originals render
# with fr_prose_fallback=True (the historical behavior, byte-identical).
_STRICT_PROSE = False
_STRICT_FR_OK = {"name"}   # frozen FR proper name, verbatim in every language


def L(key, default=""):
    """Locale-field lookup with FR fallback. Empty string / None / [] / {} count as missing."""
    v = _LOC.get(key) if isinstance(_LOC, dict) else None
    if v not in (None, "", [], {}):
        return v
    if _STRICT_PROSE and key not in _STRICT_FR_OK:
        return default
    v = _FR.get(key) if isinstance(_FR, dict) else None
    if v not in (None, "", [], {}):
        _FALLBACK_FIELDS.add(key)
        return v
    return default


def L_body(key, default=""):
    """Locale-body lookup: i18n.<lang>.body.<key>, fall back to i18n.<lang>.<key>,
    fall back to i18n.fr.body.<key>, then i18n.fr.<key>."""
    sources = ((_LANG, _LOC),) if _STRICT_PROSE else ((_LANG, _LOC), ("fr", _FR))
    for src_lang, src in sources:
        if not isinstance(src, dict):
            continue
        body = src.get("body") if isinstance(src.get("body"), dict) else {}
        v = body.get(key) if body else None
        if v not in (None, "", [], {}):
            if src_lang != _LANG:
                _FALLBACK_FIELDS.add(f"body.{key}")
            return v
        v = src.get(key)
        if v not in (None, "", [], {}):
            if src_lang != _LANG:
                _FALLBACK_FIELDS.add(f"body.{key}")
            return v
    return default


CAT_TO_FR_HUB = {
    # `attraction` retired in the 2026-06 hub overhaul (split across
    # sport-jeux / sensations-plein-air / baignade-nautisme / parcs-jardins /
    # sorties-detente — no 1:1 mapping from old category). Breadcrumb falls
    # back to commune-name span for these.
    "cascade": ("cascades", "Cascades"),
    "chateau": ("chateaux", "Châteaux"),
    # `divers` retired in the 2026-06 hub overhaul → no breadcrumb hub link
    "domaine": ("bases-de-loisirs", "Bases de loisirs"),
    # `lac` + `plage` merged into /lacs-plages/ in the 2026-06 hub overhaul
    "lac": ("lacs-plages", "Lacs & plages"),
    "musee": ("musees", "Musées"),
    "parc": ("bases-de-loisirs", "Bases de loisirs"),
    "plage": ("lacs-plages", "Lacs & plages"),
    "point-de-vue": ("points-de-vue", "Points de vue"),
    "sentier": ("sentiers", "Sentiers"),
    "telecabine": ("telecabines", "Télécabines"),
    "voie-verte": ("voies-vertes", "Voies vertes"),
}


# Per-locale hub-slug map: FR slug → {lang: localized slug}.
# Single source of truth for breadcrumb URL + label in non-FR locales.
# Must stay in sync with scripts/build_hubs.py hub_locale_map() output;
# audit_breadcrumbs.py also relies on these labels.
HUB_LOCALE_SLUGS = {
    "cascades":        {"fr": "cascades",        "en": "waterfalls",     "de": "wasserfaelle",      "it": "cascate",         "es": "cascadas",     "nl": "watervallen"},
    "chateaux":        {"fr": "chateaux",        "en": "castles",        "de": "schloesser",        "it": "castelli",        "es": "castillos",    "nl": "kastelen"},
    "musees":          {"fr": "musees",          "en": "museums",        "de": "museen",            "it": "musei",           "es": "museos",       "nl": "musea"},
    "points-de-vue":   {"fr": "points-de-vue",   "en": "viewpoints",     "de": "aussichtspunkte",   "it": "punti-panoramici","es": "miradores",    "nl": "uitzichtpunten"},
    "sentiers":        {"fr": "sentiers",        "en": "trails",         "de": "wanderwege",        "it": "sentieri",        "es": "senderos",     "nl": "wandelpaden"},
    "telecabines":     {"fr": "telecabines",     "en": "cable-cars",     "de": "seilbahnen",        "it": "funivie",         "es": "telefericos",  "nl": "kabelbanen"},
    "voies-vertes":    {"fr": "voies-vertes",    "en": "greenways",      "de": "radwege",           "it": "vie-verdi",       "es": "vias-verdes",  "nl": "fietsroutes"},
    "lacs-plages":     {"fr": "lacs-plages",     "en": "lakes",          "de": "seen",              "it": "laghi",           "es": "lagos",        "nl": "meren"},
    "bases-de-loisirs":{"fr": "bases-de-loisirs","en": "leisure-parks",  "de": "freizeitparks",     "it": "aree-ricreative", "es": "areas-de-ocio","nl": "recreatieparken"},
    # que-faire is a hub like any other and belongs in the same table. It was
    # missing here and its slugs were being recovered from the rendered
    # hreflang block instead — which works only on a site whose hub pages
    # already exist, and silently falls back to the FR slug on one whose
    # don't. That is how /de/points-de-vue/ and /de/que-faire/ came to be
    # linked from the German homepage.
    "que-faire":       {"fr": "que-faire",       "en": "what-to-do",     "de": "was-unternehmen",   "it": "cosa-fare",       "es": "que-hacer",    "nl": "wat-te-doen"},
}

HUB_LOCALE_LABELS = {
    "cascades":        {"fr": "Cascades",         "en": "Waterfalls",       "de": "Wasserfälle",      "it": "Cascate",          "es": "Cascadas",      "nl": "Watervallen"},
    "chateaux":        {"fr": "Châteaux",         "en": "Castles",          "de": "Schlösser",        "it": "Castelli",         "es": "Castillos",     "nl": "Kastelen"},
    "musees":          {"fr": "Musées",           "en": "Museums",          "de": "Museen",           "it": "Musei",            "es": "Museos",        "nl": "Musea"},
    "points-de-vue":   {"fr": "Points de vue",    "en": "Viewpoints",       "de": "Aussichtspunkte",  "it": "Punti panoramici", "es": "Miradores",     "nl": "Uitzichtpunten"},
    "sentiers":        {"fr": "Sentiers",         "en": "Trails",           "de": "Wanderwege",       "it": "Sentieri",         "es": "Senderos",      "nl": "Wandelpaden"},
    "telecabines":     {"fr": "Télécabines",      "en": "Cable cars",       "de": "Seilbahnen",       "it": "Funivie",          "es": "Teleféricos",   "nl": "Kabelbanen"},
    "voies-vertes":    {"fr": "Voies vertes",     "en": "Greenways",        "de": "Radwege",          "it": "Vie verdi",        "es": "Vías verdes",   "nl": "Fietsroutes"},
    "lacs-plages":     {"fr": "Lacs & plages",    "en": "Lakes",            "de": "Seen",             "it": "Laghi",            "es": "Lagos",         "nl": "Meren"},
    "bases-de-loisirs":{"fr": "Bases de loisirs", "en": "Leisure parks",    "de": "Freizeitparks",    "it": "Aree ricreative",  "es": "Áreas de ocio", "nl": "Recreatieparken"},
}


def primary_hub(d, lang=None):
    """Return (hub_slug, hub_label) for the fiche's primary hub, localized to
    `lang` (defaults to the module-level _LANG set by build_page).

    The breadcrumb URL must point to the locale-rendered hub
    (e.g. /en/castles/, /de/schloesser/), and the label must read in the
    same language as the page chrome — otherwise Googlebot sees a
    contradiction between visible breadcrumb and JSON-LD BreadcrumbList.
    """
    cats = d.get("categories") or ([d.get("category")] if d.get("category") else [])
    L = lang or _LANG
    for c in cats:
        fr_pair = CAT_TO_FR_HUB.get(c)
        if not fr_pair:
            continue
        fr_slug, fr_label = fr_pair
        slug = HUB_LOCALE_SLUGS.get(fr_slug, {}).get(L, fr_slug)
        label = HUB_LOCALE_LABELS.get(fr_slug, {}).get(L, fr_label)
        return (slug, label)
    return None


def hammer_h1(name):
    """Wrap name as hammer-animated h1 with the last word italicised."""
    parts = name.split()
    if not parts:
        return f'<h1 class="hammer">{esc(name)}</h1>'
    spans = []
    for i, w in enumerate(parts):
        if i == len(parts) - 1 and len(parts) > 1:
            spans.append(f'<span class="w"><em>{esc(w)}</em></span>')
        else:
            spans.append(f'<span class="w">{esc(w)}</span>')
    return f'<h1 class="hammer">{" ".join(spans)}</h1>'


def _fact_label(k):
    """Lookup the locale-translated fact-label for key k."""
    row = FACT_LABELS_I18N.get(k)
    if row:
        return row.get(_LANG) or row.get("fr") or FACT_LABELS.get(k, k)
    return FACT_LABELS.get(k, k.replace("_", " ").capitalize())


def first_source_url(d):
    """Resolve the authoritative page for the beside-facts source link:
    official_site_url first, else the first usable sources[] URL. Returns ""
    when the fiche has neither (link is then omitted — never fabricated)."""
    off = d.get("official_site_url")
    if off:
        return off
    for s in d.get("sources") or []:
        url = s.get("url") if isinstance(s, dict) else s
        if url:
            return url
    return ""


_ACCES_LABEL = {"fr": "Accessibilité PMR", "en": "Wheelchair access", "de": "Barrierefreiheit",
                "it": "Accessibilità", "es": "Accesibilidad PMR", "nl": "Toegankelijkheid"}
_ACCES_STATUS = {
    "accessible": {"fr": "Accessible", "en": "Accessible", "de": "Barrierefrei",
                   "it": "Accessibile", "es": "Accesible", "nl": "Toegankelijk"},
    "partiel": {"fr": "Partiellement accessible", "en": "Partially accessible",
                "de": "Teilweise barrierefrei", "it": "Parzialmente accessibile",
                "es": "Parcialmente accesible", "nl": "Gedeeltelijk toegankelijk"},
    "non_accessible": {"fr": "Non accessible", "en": "Not accessible", "de": "Nicht barrierefrei",
                       "it": "Non accessibile", "es": "No accesible", "nl": "Niet toegankelijk"},
}
# HANDOFF-35: the old connective ("per Commune Saint-Jorioz") read as broken
# English and existed for 6 langs only. A label-prefix form ("Source: X") is
# grammatical in every language; the 6 facts langs come from the reviewed
# i18n-labels lane (ui_chrome.source_prefix), never a new hardcoded dict.
_SRC_PREFIX = {"fr": "Source :", "en": "Source:", "de": "Quelle:",
               "it": "Fonte:", "es": "Fuente:", "nl": "Bron:"}
_PMR_VALUE_KEY = {"accessible": "pmr_accessible", "partiel": "pmr_partiel",
                  "non_accessible": "pmr_non"}


def _ui_label(hard, key, lang):
    """Two-lane label lookup (HANDOFF-35): the six live languages keep their
    hardcoded wording; the six facts languages come from the reviewed
    data/i18n-labels.json vocabulary; FR is the last-resort fallback."""
    row = (_I18N_LABELS.get("ui_chrome") or {}).get(key) or {}
    return hard.get(lang) or row.get(lang) or hard.get("fr") or row.get("fr") or ""


def _pmr_status_label(status, lang):
    """Localized short PMR status for ALL 12 languages (hardcoded 6 +
    reviewed fact_values.pmr_* for the facts langs; FR fallback)."""
    row = _ACCES_STATUS.get(status) or {}
    fv = (_I18N_LABELS.get("fact_values") or {}).get(_PMR_VALUE_KEY.get(status, "")) or {}
    return row.get(lang) or fv.get(lang) or row.get("fr") or status


def acces_pmr_fact(a):
    """(label, value_html) for the accessibility fact row, or None. Only renders
    a sourced status (never 'accessible' for an unsourced/null fiche).
    HANDOFF-35: `detail` here is already language-effective — build_page swaps
    in i18n.<lang>.acces_pmr_detail off-fr and suppresses the FR text (it is
    CONTENT, not a frozen name); the localized short status always shows."""
    if not isinstance(a, dict) or a.get("status") not in _ACCES_STATUS:
        return None
    st = _pmr_status_label(a["status"], _LANG)
    val = " · ".join([esc(st)] + ([esc(a["detail"])] if a.get("detail") else []))
    if a.get("handiplage_level"):
        val += f' <span class="pill pill-ok">Handiplage {esc(str(a["handiplage_level"]))}</span>'
    if a.get("source_url") and a.get("source_name"):
        pfx = _ui_label(_SRC_PREFIX, "source_prefix", _LANG)
        val += (f' <a class="inline-link" href="{attr(a["source_url"])}" target="_blank" '
                f'rel="noopener">{esc(pfx)} {esc(a["source_name"])}</a>')
    return (_ACCES_LABEL.get(_LANG) or _ACCES_LABEL["fr"], val)


def _bdi(s_esc):
    """<bdi>-isolate an (already escaped) Latin/number value inside an RTL flow
    (ar/he): prices, frozen FR place names, durations would otherwise visually
    scramble against the right-to-left text. HANDOFF-13's anti-scramble rule,
    carried onto the rich template now that ar/he render through it
    (HANDOFF-31). No-op on LTR pages — the six stay byte-identical."""
    return f"<bdi>{s_esc}</bdi>" if locales.DIR.get(_LANG) == "rtl" else s_esc


def facts_block(facts, source_url="", acces_pmr=None):
    """Render the 'At a glance' grid (locale-aware), with an optional compact
    'Source officielle →' link beside the panel (master to-do #4)."""
    items = []
    seen = set()
    for k in FACT_ORDER:
        if k in facts and facts[k]:
            v = facts[k]
            ok_class = ""
            # Mark positive parking/free as ok (FR sniff still valid — values are
            # source-side strings that we render as-is per fiche)
            if k == "parking" and re.search(r"gratuit|free|kostenlos|gratis", v, re.I):
                ok_class = " ok"
            elif k == "access" and re.search(r"libre|gratuit|free|frei|libero|libre|vrij", v, re.I):
                ok_class = " ok"
            items.append(
                f'<div class="fact"><div class="k">{esc(_fact_label(k))}</div>'
                f'<div class="v{ok_class}">{_bdi(esc(v))}</div></div>'
            )
            seen.add(k)
    for k, v in facts.items():
        if k in seen or not v:
            continue
        items.append(
            f'<div class="fact"><div class="k">{esc(_fact_label(k))}</div>'
            f'<div class="v">{_bdi(esc(v))}</div></div>'
        )
    ap = acces_pmr_fact(acces_pmr)
    if ap:
        items.append(f'<div class="fact"><div class="k">{esc(ap[0])}</div>'
                     f'<div class="v">{ap[1]}</div></div>')
    if not items:
        return ""
    source_html = ""
    if source_url:
        source_html = (
            f'<p class="fact-source reveal"><a href="{attr(source_url)}" '
            f'target="_blank" rel="noopener">{T("source_official")} →</a></p>'
        )
    return (
        '<section class="block"><div class="wrap"><div class="kicker reveal">'
        f"{T('k_glance')}</div>"
        f'<div class="facts reveal" data-stagger>{"".join(items)}</div>'
        f'{source_html}</div></section>'
    )


def body_block(name, body):
    """Render the 'What is <name>' section. body is dict with 'what_is' HTML."""
    what_is = body.get("what_is", "") if isinstance(body, dict) else str(body or "")
    if not what_is.strip():
        return ""
    return (
        '<section class="block"><div class="wrap">'
        f'<h2 class="reveal">{T("h_whatis")} {esc(name)}</h2>'
        f'<div class="reveal">{what_is}</div></div></section>'
    )


def flip_hint():
    return (
        '<span class="hint"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>'
        '<path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>'
        f'</svg> {T("tap_to_read")}</span>'
    )


def activities_block(activities):
    """Render flip-card grid."""
    if not activities:
        return ""
    cards = []
    for a in activities:
        title = a.get("title", "")
        tag = a.get("tag", "")
        desc = a.get("description", "")
        tag_html = f'<span class="activity-tag">{esc(tag)}</span>' if tag else ""
        # JOB 3 named-entity anchor: a proprietary-name activity (Absurd Game,
        # Explor Games, Acro'Filet, Visite Découverte) carries a stable id so the
        # name is a resolvable, matchable fragment. Permanent — never renamed.
        id_attr = f' id="{attr(a["id"])}"' if a.get("id") else ""
        cards.append(
            f'<button type="button" class="activity flip"{id_attr} aria-label="{attr(title)}">'
            f'<div class="flip-inner">'
            f'<div class="flip-front">'
            f'<h4>{esc(title)}{tag_html}</h4>'
            f'<p class="preview">{emit_prose(desc)}</p>'
            f'{flip_hint()}'
            f'</div>'
            f'<div class="flip-back"><h4>{esc(title)}</h4><p>{emit_prose(desc)}</p></div>'
            f'</div></button>'
        )
    return (
        '<section class="block"><div class="wrap">'
        f'<div class="kicker reveal">{T("k_activities")}</div>'
        f'<h2 class="reveal">{T("h_activities")}</h2>'
        f'<div class="activities reveal" data-stagger>{"".join(cards)}</div>'
        '</div></section>'
    )


# Labels that mean "price/tarif" across the 12 languages (singular AND plural —
# the practical_info generator used plurals like "Tarifs"/"Ceny"/"Tarifas" that
# the singular fact-label set misses). Used to suppress the stale practical_info
# "prices not listed" row once the structured tiers grid owns the price surface
# (kills the 44 € chip + "non renseigné" contradiction). Explicit vocabulary,
# not a data scan, so it never catches an adjacent row (e.g. "Ski nordique").
_TARIF_ROW_LABELS = {s.lower() for s in (
    "tarif", "tarifs", "price", "prices", "rates", "fare", "fares",
    "preis", "preise", "prezzo", "prezzi", "tariffa", "tariffe",
    "precio", "precios", "tarifa", "tarifas", "prijs", "prijzen",
    "tarief", "tarieven", "cena", "ceny", "preço", "preços",
    "料金", "السعر", "الأسعار", "מחיר", "מחירים",
)} | {str(v).strip().lower() for v in (FACT_LABELS_I18N.get("tarif") or {}).values()}


def practical_block(practical, name, commune, drop_tarif=False):
    """Render the 'Infos pratiques' info-table. drop_tarif suppresses the price
    row (the tiers grid owns it) so a stale 'prices not listed' line can't
    contradict the grid."""
    if not practical:
        return ""
    rows = []
    addr_terms = ("adresse", "address", "adres", "indirizzo", "dirección")
    for entry in practical:
        k = entry.get("k", "")
        v = entry.get("v", "")
        if drop_tarif and str(k).strip().lower() in _TARIF_ROW_LABELS:
            continue
        extra = ""
        if any(k.lower().startswith(t) for t in addr_terms):
            q = url_q(f"{name}, {commune}, {siteconfig.DEPT_NAME}, France")
            extra = (
                f' <a href="https://www.google.com/maps/search/?api=1&query={q}" '
                'target="_blank" rel="noopener" class="inline-link">'
                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>'
                f'<circle cx="12" cy="10" r="3"/></svg>{T("map_view")}</a>'
            )
        rows.append(
            f'<div class="info-row"><div class="k">{esc(k)}</div>'
            f'<div class="v"><span>{emit_prose(v)}{extra}</span></div></div>'
        )
    return (
        '<section class="block"><div class="wrap">'
        f'<div class="kicker reveal">{T("k_practical")}</div>'
        f'<h2 class="reveal">{T("h_practical")}</h2>'
        f'<div class="info-table reveal">{"".join(rows)}</div></div></section>'
    )


_PROSE_LANGS = set(locales.PROSE)  # fr,en,de,it,es,nl — free FR tier names OK here
# Tier → controlled category, derived from the FR name (case/accents-insensitive
# regex). Order matters: first match wins, defaults to 'adulte'.
_TIER_CAT_RULES = [
    ("enfant",   r"enfant|child|kind|junior 5|5[\s-]*(?:à|-)\s*1[0-5]|-\s*12 ans"),
    ("jeune",    r"jeune|youth|16[\s-]*(?:à|-)\s*2[0-9]|étudiant"),
    ("senior",   r"s[eé]nior|65[\s-]*(?:à|-)|v[eé]t[eé]ran|75 ans"),
    ("famille",  r"famille|tribu|family|pack"),
    ("saison",   r"saison|ann[eé]e|abonnement|season"),
    ("nordique", r"nordi|redevance nordique|nordic pass|ski de fond|fond"),
    ("debutant", r"d[eé]butant|lutins|espace d[eé]butant|beginner"),
    ("court",    r"\b4\s*h|4 heures|apr[eè]s-midi|matin|1/2|demi|5\s*h|5 heures|heures cons"),
]
_TIER_CAT_RX = [(cat, re.compile(rx, re.I)) for cat, rx in _TIER_CAT_RULES]


def _tier_cat(name):
    n = name or ""
    for cat, rx in _TIER_CAT_RX:
        if rx.search(n):
            return cat
    return "adulte"


def _tier_label(cat, lang):
    tt = _I18N_LABELS.get("tarif_tiers") or {}
    row = tt.get(cat) or tt.get("autre") or {}
    return row.get(lang) or row.get("fr") or cat


def _price_str(v, cur):
    if not isinstance(v, (int, float)):
        return ""
    s = f"{v:.2f}".replace(".", ",")
    return f"{s} {cur}"


def tarifs_block(d):
    """Structured pass-price grid. PROSE langs get the rich FR tier name (+ FR
    note); FACTS langs (pl,pt,cs,ar,he,ja) get a reviewed-vocabulary category
    label + the number ONLY — never FR free-text — honouring _vocab_facts'
    facts-lang doctrine. Numbers are language-independent; heading localized."""
    tiers = [t for t in (d.get("price_tiers") or []) if isinstance(t, dict) and t.get("price") is not None]
    if not tiers:
        return ""
    cur = {"EUR": "€"}.get(d.get("price_currency"), d.get("price_currency") or "€")
    is_prose = _LANG in _PROSE_LANGS
    rows = []
    seen_cat = set()
    for t in tiers:
        price = _price_str(t.get("price"), cur)
        if is_prose:
            # PROSE langs: every tier, full FR name + FR note (context intact).
            k = esc(t.get("name") or "")
            note = t.get("note")
            note_html = (f'<span class="tier-note">{esc(note)}</span>' if note else "")
            v = f'<span class="tier-price">{_bdi(esc(price))}</span>{note_html}'
        else:
            # FACTS langs: category label + number only — no FR free-text to
            # disambiguate day/6-day/secondary-domain products, so show ONE
            # representative per category (the first = the base pass); the rest
            # would be ambiguous bare numbers. Honest subset, never invented.
            cat = _tier_cat(t.get("name"))
            if cat in seen_cat:
                continue
            seen_cat.add(cat)
            k = esc(_tier_label(cat, _LANG))
            v = f'<span class="tier-price">{_bdi(esc(price))}</span>'
        rows.append(f'<div class="info-row"><div class="k">{k}</div>'
                    f'<div class="v">{v}</div></div>')
    heading = esc(_fact_label("tarif"))
    return (
        '<section class="block"><div class="wrap">'
        f'<div class="kicker reveal">💶</div>'
        f'<h2 class="reveal">{heading}</h2>'
        f'<div class="info-table reveal">{"".join(rows)}</div></div></section>'
    )


HOW_ICONS = {
    "car": (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M5 17h14M5 17V11l2-6h10l2 6v6M5 17H3M19 17h2M7 17v2h2v-2M15 17v2h2v-2"/>'
        '<circle cx="7" cy="14" r="1"/><circle cx="17" cy="14" r="1"/></svg>'
    ),
    "public_transport": (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="4" y="3" width="16" height="14" rx="2"/>'
        '<path d="M4 11h16M8 17v2M16 17v2"/><circle cx="8" cy="14" r="1"/>'
        '<circle cx="16" cy="14" r="1"/></svg>'
    ),
    "bike": (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="6" cy="17" r="3"/><circle cx="18" cy="17" r="3"/>'
        '<path d="M6 17l4-9h4l3 9M14 8l-2-4h-2"/></svg>'
    ),
}
HOW_MODE = {
    "car": ("how_car", "driving"),
    "public_transport": ("how_transit", "transit"),
    "bike": ("how_bike", "bicycling"),
}


def maps_query(d, name, commune):
    """Maps deep-link target. Prefer the name+commune query so Maps resolves to
    the real POI in its index — a stored coord can be a commune centroid / OSM
    label point / rounded value and drops a literal pin off-venue (a
    destination=lat,lng does NOT snap to the place). Coords = last-resort
    fallback only."""
    if name and commune:
        return url_q(f"{name}, {commune}, {siteconfig.DEPT_NAME}, France")
    lat, lng = d.get("latitude"), d.get("longitude")
    if lat is not None and lng is not None:
        return f"{lat},{lng}"
    return url_q(f"{name or ''}, {commune or ''}, {siteconfig.DEPT_NAME}, France")


def maps_place_param(d, kind):
    """Maps place-id query param for a venue link, or '' if no canonical id.

    kind = 'destination' (dir/ links) or 'query' (search/ links). Google
    accepts the text destination/query *and* a *_place_id that pins to the
    canonical POI — so a stale/off-venue stored coordinate is irrelevant for
    directions. google_place_id is derived by derive_geo_verified.py and exists
    on every fiche that has a Google place_id (independent of geo_verified)."""
    pid = d.get("google_place_id")
    return f"&{kind}_place_id={url_q(pid)}" if pid else ""


def geo_verified_badge(d):
    """Earn-only ✅ badge. Renders ONLY when geo_verified is true; when false or
    absent, returns '' — silence, not a scarlet 'unverified' letter. Gold,
    rendered near the Itinéraire CTA. Label is i18n; place name frozen."""
    if d.get("geo_verified") is not True:
        return ""
    return (
        '<span class="geo-verified reveal" role="note">'
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>'
        '<circle cx="12" cy="10" r="3"/></svg>'
        f'<span>{esc(T("geo_verified"))}</span></span>'
    )


def how_to_block(how, name, commune, lat=None, lng=None, slug=None, place_id=None):
    """Render the unified transport section (locale-aware).

    One block: the car / public_transport / bike how-cards PLUS the generated
    nearest-stops panel (stops · fare · official link · Etalab line) folded in
    beneath them — no second stacked "Arrêts les plus proches" section. The
    section renders if there are how-cards OR generated stops; empty-stop lieux
    show just the curated cards, no empty box.

    The Maps deep-link destination prefers the name+commune query (resolves to
    the real POI); coords are a last-resort fallback (they can pin off-venue).
    """
    how = how or {}
    # Name+commune first so Maps resolves to the real POI; a stored coord can be
    # a centroid/label point and pins off-venue. Coords = last-resort fallback.
    if name and commune:
        dest = url_q(f"{name}, {commune}, {siteconfig.DEPT_NAME}, France")
    elif lat is not None and lng is not None:
        dest = f"{lat},{lng}"
    else:
        dest = url_q(f"{name or ''}, {commune or ''}, {siteconfig.DEPT_NAME}, France")
    # Canonical-POI pin: routes the how-card directions to the real place
    # regardless of the stored coordinate. Empty when no google_place_id.
    pid_param = f"&destination_place_id={url_q(place_id)}" if place_id else ""
    cards = []
    for key in ("car", "public_transport", "bike"):
        text = how.get(key)
        if not text:
            continue
        chrome_key, travelmode = HOW_MODE[key]
        label = T(chrome_key)
        icon = HOW_ICONS[key]
        cards.append(
            f'<a class="how-card" href="https://www.google.com/maps/dir/?api=1'
            f"&destination={dest}{pid_param}&travelmode={travelmode}" + '" '
            f'target="_blank" rel="noopener">'
            f'<div class="icon">{icon}</div>'
            f'<h3>{esc(label)}</h3>'
            f'<p>{emit_prose(text)}</p>'
            f'<span class="open">{T("maps_open")} '
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>'
            '</svg></span></a>'
        )
    transit_inner = transit_data_inner(slug) if slug else ""
    if not cards and not transit_inner:
        return ""
    cards_html = (f'<div class="how reveal" data-stagger>{"".join(cards)}</div>'
                  if cards else "")
    return (
        '<section class="block"><div class="wrap">'
        f'<div class="kicker reveal">{T("k_access")}</div>'
        f'<h2 class="reveal">{T("h_how")}</h2>'
        f'{cards_html}'
        f'{transit_inner}'
        '</div></section>'
    )


def transit_data_inner(slug):
    """Generated nearest-stops panel from the GTFS freshness index (PART B2).

    Returned as INNER markup (no own <section>/<h2>) so it folds directly into
    the unified transport section beneath the how-cards — one transport block,
    not two stacked ones. Augments, never replaces, the curated
    public_transport prose. Renders only when the index has ≥1 stop for this
    lieu. Stop / operator / line names are proper nouns kept verbatim; only the
    surrounding labels localise. Carries the verified date + Etalab attribution
    (licence requirement), relocated here from the old standalone section.
    """
    entry = TRANSPORT_INDEX.get(slug)
    if not entry or not entry.get("stops"):
        return ""
    items = []
    for s in entry["stops"]:
        bits = [f'<strong>{esc(s["name"])}</strong>', esc(s["operator"])]
        if s.get("lines"):
            bits.append(", ".join(esc(str(line)) for line in s["lines"]))
        bits.append(f'{int(s["distance_m"])} m')
        items.append(f'<li>{" · ".join(bits)}</li>')
    # Per-operator official link (+ dated fare). The link is the operator's own
    # page — the honest "get your info and go" door — preferred order: a curated
    # tariff_url, else the feed's agency_fare_url, else its agency_url. Every URL
    # comes from the feed or the manually-verified fares file; none are guessed.
    op_lines = []
    seen = []
    for s in entry["stops"]:
        for op in s["operator"].split(" / "):
            if op not in seen:
                seen.append(op)
    for op in seen:
        meta = TRANSPORT_OPERATORS.get(op, {}) or {}
        fares = NETWORK_FARES.get(op, {}) or {}
        link = fares.get("tariff_url") or meta.get("fare_url") or meta.get("url")
        parts = [f'<strong>{esc(op)}</strong>']
        if fares.get("fare"):
            parts.append(f'{T("transit_fare")} : {esc(fares["fare"])}')
        if link:
            parts.append(
                f'<a href="{attr(link)}" target="_blank" rel="noopener">'
                f'{T("transit_official")} →</a>'
            )
        if len(parts) > 1:   # skip operators we can neither link nor price
            op_lines.append(f'<li>{" · ".join(parts)}</li>')
    ops_html = (f'<ul class="transit-ops">{"".join(op_lines)}</ul>'
                if op_lines else "")

    # Etalab attribution is kept separate from the traveller link (licence != the
    # operator door) — both present.
    attribution = (
        f'{T("transit_verified")} {esc(entry.get("verified", ""))} · '
        f'{T("transit_source")} {esc(entry.get("source", ""))} '
        f'({esc(entry.get("license", ""))})'
    )
    return (
        '<div class="transit-data reveal">'
        f'<h3>{T("transit_nearest")}</h3>'
        f'<div class="sources"><ul>{"".join(items)}</ul>'
        f'{ops_html}'
        f'<p class="caveat">{attribution}</p></div></div>'
    )


PARK_BADGE = {
    "free":        ("park_free", "pill-ok"),
    "paid":        ("park_paid", "pill-paid"),
    "conditional": ("park_conditional", "pill-mute"),
    "unknown":     ("park_unknown", "pill-mute"),
}


def parking_block(slug, curated=None):
    """Nearest-parking block from data/parking_index.json (master to-do #3).

    Renders only when there are OSM lots in range. A curated `facts.parking`
    note (e.g. Saint-Jorioz "Gratuit (grand parking ombragé)") is shown
    first/prominent; the OSM lots augment beneath. The fee badge is the honest
    tri-state from the feed — never "Gratuit" without an explicit fee=no. The
    "Y aller" deep-link uses each lot's own lat,lng (Part-A coordinate pattern).
    Carries an ODbL attribution + verified date.
    """
    entry = PARKING_INDEX.get(slug)
    if not entry or not entry.get("parkings"):
        return ""
    intro = ""
    if curated:
        intro = f'<p class="reveal"><strong>{esc(curated)}</strong></p>'
    rows = []
    for p in entry["parkings"]:
        label_key, pill_cls = PARK_BADGE.get(p.get("status"), ("park_unknown", "pill-mute"))
        parts = []
        if p.get("name"):
            parts.append(f'<strong>{esc(p["name"])}</strong>')
        parts.append(f'<span class="pill {pill_cls}">{T(label_key)}</span>')
        parts.append(f'{int(p["distance_m"])} m')
        if p.get("status") == "conditional" and p.get("condition"):
            parts.append(esc(p["condition"]))
        if p.get("capacity"):
            parts.append(f'{int(p["capacity"])} {T("park_capacity")}')
        dest = f'{p["lat"]},{p["lon"]}'
        parts.append(
            f'<a class="go" href="https://www.google.com/maps/dir/?api=1'
            f'&destination={dest}&travelmode=driving" target="_blank" '
            f'rel="noopener">{T("park_goto")} →</a>'
        )
        rows.append(f'<li>{" · ".join(parts)}</li>')
    attribution = (
        f'{T("park_verified")} {esc(entry.get("verified", ""))} · '
        f'{esc(PARKING_ATTRIB)}'
    )
    return (
        '<section class="block"><div class="wrap">'
        f'<h2 class="reveal">{T("park_title")}</h2>'
        f'{intro}'
        f'<div class="sources reveal"><ul>{"".join(rows)}</ul>'
        f'<p class="caveat">{attribution}</p></div></div></section>'
    )


def when_to_visit_block(when, events):
    """Render 'When to visit' + optional events (locale-aware)."""
    if not when and not events:
        return ""
    inner = ""
    if when:
        inner += f'<div class="reveal">{emit_prose(when)}</div>'
    if events:
        inner += (
            '<div class="reveal" style="margin-top:1.25rem">'
            f'<strong>{T("events_label")}&nbsp;:</strong> {emit_prose(events)}</div>'
        )
    return (
        '<section class="block"><div class="wrap">'
        f'<div class="kicker reveal">{T("k_when")}</div>'
        f'<h2 class="reveal">{T("h_when")}</h2>'
        f"{inner}</div></section>"
    )


def season_card(d):
    """HANDOFF-winter §5 — compact structured Season card on the fiche, the
    Google-ranking surface. Emits only for WINTER_NODES categories, FR + EN
    inline (the other 10 langs route through the translation lane under the
    winter_* label keys — not hand-jammed here). Reads the SAME i18n.fr.facts
    winter_* fields as the facet md/json (one source, no divergence). All data
    null → equipment-only card (verified dept constant; HANDOFF-winter §8 default).
    Frozen Mont-Blanc / Loi Montagne II verbatim. Never touches partner blocks."""
    import build_ai_content as _bac
    if (d.get("category") or "") not in _bac.WINTER_NODES or _LANG not in ("fr", "en"):
        return ""
    lang = _LANG
    fk = (_FR.get("facts") or {}) if isinstance(_FR, dict) else {}
    L_, unk = _bac.WINTER_LABELS, ("Non renseigné" if lang == "fr" else "Not specified")
    a = fk.get("winter_access")
    av = _bac.WINTER_ACCESS[a][lang] if a in _bac.WINTER_ACCESS else unk
    infra = [_bac.WINTER_INFRA[x][lang] for x in (fk.get("winter_infra") or [])
             if x in _bac.WINTER_INFRA]
    iv = " · ".join(infra) if infra else unk
    sv = fk.get("snow_view")
    svv = _bac.SNOW_VIEW[sv][lang] if sv in _bac.SNOW_VIEW else unk
    eq = _bac.EQUIP[lang] + (_bac.EQUIP_COL[lang] if fk.get("col_chains") else "")
    # JOB B: closed/partial régime or a col → state the régime + delegate live status
    # to the Département's own road service (siteconfig.ROAD_INFO_*). Plain external
    # link. Per-site: sending a Savoie driver to Haute-Savoie's service is a wrong
    # answer dressed as a helpful one.
    acc_suffix = ""
    if _bac.winter_needs_inforoute(fk):
        acc_suffix = (f' — {esc(_bac.WINTER_LIVE[lang])} '
                      f'<a href="{_bac.INFOROUTE_URL}" target="_blank" rel="noopener">'
                      f'{_bac.INFOROUTE_HOST}</a>')
    rows = [(L_["access"][lang], av, acc_suffix), (L_["infra"][lang], iv, ""),
            (L_["view"][lang], svv, ""), (L_["equip"][lang], eq, "")]
    facts = "".join(
        f'<div class="fact"><div class="k">{esc(k)}</div>'
        f'<div class="v"><bdi>{esc(v)}{sfx}</bdi></div></div>' for k, v, sfx in rows)
    kicker = "Hiver" if lang == "fr" else "Winter"
    head = "Saison hivernale" if lang == "fr" else "Winter season"
    return (
        '<section class="block"><div class="wrap">'
        f'<div class="kicker reveal">{kicker}</div>'
        f'<h2 class="reveal">{esc(head)}</h2>'
        f'<div class="facts reveal" data-stagger>{facts}</div>'
        '</div></section>'
    )


_SELECTIONS_CACHE = None
_SELECTIONS_LABEL = {
    "fr": "Figure dans nos sélections", "en": "Featured in our selections",
    "de": "In unseren Auswahlen",       "nl": "Opgenomen in onze selecties",
    "es": "Aparece en nuestras selecciones", "it": "Presente nelle nostre selezioni",
    "pl": "W naszych zestawieniach",    "pt": "Presente nas nossas seleções",
    "cs": "V našich výběrech",          "ar": "يظهر ضمن مختاراتنا",
    "he": "מופיע במבחרים שלנו",          "ja": "掲載セレクション",
}


def selections_chips(d, lang):
    """HANDOFF-intentpages §5 upward links: chip row linking every intent page
    this fiche is compiled into (registry membership, computed — never curated).
    Rendered in every VISIBLE lang: the label above covers all 12, and the
    per-entry guard below still drops any selection that does not ship in this
    lang, so a fiche only ever links to a page that actually exists. The chip is
    a plain internal link; partner blocks untouched."""
    global _SELECTIONS_CACHE
    if lang not in _SELECTIONS_LABEL:
        return ""
    if _SELECTIONS_CACHE is None:
        import build_intent_hubs as _bih
        membership, _ = _bih.compute_membership()
        by_slug = {}
        for e in membership.values():
            if len(e["members"]) < 6:      # unbuilt pages (min_items law) — no links
                continue
            for s in e["members"]:
                by_slug.setdefault(s, []).append(e)
        _SELECTIONS_CACHE = (by_slug, _bih)
    by_slug, _bih = _SELECTIONS_CACHE
    entries = by_slug.get(d.get("slug") or "", [])
    entries = [e for e in entries if e["title"].get(lang) and e["lead"].get(lang)]
    if not entries:
        return ""
    chips = "".join(
        f'<a class="chip-sel" href="{_bih.intent_page_url(e, lang)}">{esc(e["title"][lang])}</a>'
        for e in sorted(entries, key=lambda e: e["id"]))
    return (
        '<section class="block"><div class="wrap">'
        f'<div class="kicker reveal">{esc(_SELECTIONS_LABEL[lang])}</div>'
        f'<div class="reveal" style="display:flex;flex-wrap:wrap;gap:8px">{chips}</div>'
        '</div></section>'
        '<style>.chip-sel{display:inline-block;background:var(--surface-2);'
        'border:1px solid var(--line);border-radius:999px;padding:4px 14px;'
        'font-size:13px;font-weight:600;color:var(--ink);text-decoration:none}'
        '.chip-sel:hover{border-color:var(--accent);color:var(--accent)}</style>'
    )


def faq_block(faq):
    if not faq:
        return ""
    items = []
    for entry in faq:
        q = entry.get("q", "")
        a = entry.get("a", "")
        items.append(
            f"<details class=\"faq\"><summary>{esc(q)}</summary><p>{esc(a)}</p></details>"
        )
    return (
        '<section class="block"><div class="wrap">'
        f'<div class="kicker reveal">{T("k_faq")}</div>'
        f'<h2 class="reveal">{T("h_faq")}</h2>'
        f'<div class="faq-grid reveal" data-stagger>{"".join(items)}</div>'
        '</div></section>'
    )


LINK_ICON = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>'
    '<polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>'
)


def sources_block(sources):
    if not sources:
        return ""
    items = []
    for src in sources:
        if isinstance(src, dict):
            url = src.get("url", "")
            label = src.get("name") or re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
        else:
            url = src
            label = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
        items.append(
            f'<li>{LINK_ICON}<a href="{attr(url)}" target="_blank" rel="noopener">'
            f"{esc(label)}</a></li>"
        )
    return (
        '<section class="block"><div class="wrap">'
        f'<div class="kicker reveal">{T("k_sources")}</div>'
        f'<h2 class="reveal">{T("h_sources")}</h2>'
        f'<div class="sources reveal"><ul>{"".join(items)}</ul>'
        f'<p class="caveat">{T("src_caveat")}</p></div></div></section>'
    )


def data_credits_block(data_sources):
    """Per-fiche attribution line for content lifted from licensed third-party feeds
    (DataTourisme et al.). Required by Licence Ouverte 2.0 / Etalab."""
    if not data_sources:
        return ""
    captions = []
    for ds in data_sources:
        creator = ds.get("creator") or ""
        creator_url = ds.get("creator_url") or ""
        platform = ds.get("platform") or ""
        publisher = ds.get("publisher") or ""
        license_name = ds.get("license") or ""
        license_url = ds.get("license_url") or ""
        creator_html = (
            f'<a href="{attr(creator_url)}" target="_blank" rel="noopener">{esc(creator)}</a>'
            if creator_url else esc(creator)
        )
        license_html = (
            f'<a href="{attr(license_url)}" target="_blank" rel="noopener">{esc(license_name)}</a>'
            if license_url else esc(license_name)
        )
        via_parts = [p for p in (platform, publisher) if p]
        via = " · ".join(esc(p) for p in via_parts)
        captions.append(
            f'{T("data_partial")} {creator_html} {T("via")} {via} · {license_html}'
        )
    return (
        '<aside class="data-credits reveal"><div class="wrap">'
        '<p class="data-credits-line">'
        + " — ".join(captions)
        + "</p></div></aside>"
    )


PARTNER_TYPE_ICON = {
    "restaurant": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 2v7c0 1.1.9 2 2 2h2c1.1 0 2-.9 2-2V2M5 2v20M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3zm0 0v7"/></svg>',
    "commerce":   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/><path d="M16 10a4 4 0 0 1-8 0"/></svg>',
    "hebergement":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>',
}
SVG_ARROW = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
             'stroke-linecap="round" stroke-linejoin="round">'
             '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>')
SVG_EXT = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
           'stroke-linecap="round" stroke-linejoin="round">'
           '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>'
           '<polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>')
SVG_ROTATE = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
              'stroke-linecap="round" stroke-linejoin="round">'
              '<polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>'
              '<path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>')
SVG_CHECK = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" '
             'stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>')

def _filled_partner_card(p):
    """Render a partner card.

    tier:partner / tier:recommended → flip card (compact, 3-col grid fit).
    tier:featured → static rich card with always-visible contact info (no flip).
    """
    tier = p.get("tier", "partner")
    badge_text = T("partner_nearby") if tier == "recommended" else T("partner_badge")
    badge_icon = "" if tier == "recommended" else SVG_CHECK
    name = p.get("name", "")
    p_i18n = p.get("i18n", {}) or {}
    desc = (p_i18n.get(_LANG, {}) or {}).get("description") \
        or (p_i18n.get("fr", {}) or {}).get("description") \
        or p.get("description", "")
    url = p.get("url", "#")
    cta = p.get("cta_text") or T("see_site")

    if tier == "featured":
        address = p.get("address", "")
        phone = p.get("phone", "")
        phone_tel = p.get("phone_tel") or (re.sub(r"[^\d+]", "", phone) if phone else "")
        email = p.get("email", "")
        hours = p.get("hours", "")
        logo = p.get("logo", "")
        extras = []
        if address:
            extras.append(f'<div class="partner-row"><span class="label">{T("p_address")}</span><span>{esc(address)}</span></div>')
        if phone:
            href = f"tel:{phone_tel}" if phone_tel else f"tel:{phone.replace(' ', '')}"
            extras.append(f'<div class="partner-row"><span class="label">{T("p_phone")}</span><a href="{attr(href)}">{esc(phone)}</a></div>')
        if email:
            extras.append(f'<div class="partner-row"><span class="label">{T("p_email")}</span><a href="mailto:{attr(email)}">{esc(email)}</a></div>')
        if hours:
            extras.append(f'<div class="partner-row"><span class="label">{T("p_hours")}</span><span>{esc(hours)}</span></div>')
        extras_html = f'<div class="partner-extras">{"".join(extras)}</div>' if extras else ""
        cta_html = (
            f'<a class="cta" href="{attr(url)}" target="_blank" rel="noopener">{esc(cta)} {SVG_EXT}</a>'
            if url and url != "#" else ""
        )
        logo_html = (
            f'<img class="partner-logo" src="{attr(logo)}" alt="Logo {attr(name)}" loading="lazy">'
            if logo else ""
        )
        return (
            f'<article class="partner static tier-featured">'
            f'<span class="badge">{badge_icon} {esc(badge_text)}</span>'
            f'{logo_html}'
            f'<h4>{esc(name)}</h4>'
            f'<p class="desc">{esc(desc)}</p>'
            f'{extras_html}'
            f'{cta_html}'
            f'</article>'
        )

    return (
        f'<button type="button" class="partner flip tier-{attr(tier)}" aria-label="{attr(name)}">'
        '<div class="flip-inner">'
        '<div class="flip-front">'
        f'<span class="badge">{badge_icon} {esc(badge_text)}</span>'
        f'<h4>{esc(name)}</h4>'
        f'<p class="preview">{esc(desc)}</p>'
        f'<span class="hint">{SVG_ROTATE} {T("hover_for_site")}</span>'
        '</div>'
        '<div class="flip-back">'
        f'<h4>{esc(name)}</h4>'
        f'<p>{esc(desc)}</p>'
        f'<a class="cta" href="{attr(url)}" target="_blank" rel="noopener">{esc(cta)} {SVG_EXT}</a>'
        '</div>'
        '</div>'
        '</button>'
    )

def _invite_card(p, slug):
    """Render a tier:invite partner card (locale-aware)."""
    invite_type = p.get("invite_type", "restaurant")
    icon = PARTNER_TYPE_ICON.get(invite_type, PARTNER_TYPE_ICON["restaurant"])
    p_i18n = p.get("i18n", {}) or {}
    loc = p_i18n.get(_LANG) or p_i18n.get("fr") or {}
    title = loc.get("title") or p.get("invite_title", "")
    desc = loc.get("desc") or p.get("invite_desc", "")
    lang_prefix = f"/{_LANG}" if _LANG != "fr" else ""
    return (
        '<article class="partner-invite">'
        f'<div class="invite-icon" aria-hidden="true">{icon}</div>'
        f'<h4>{esc(title)}</h4><p>{esc(desc)}</p>'
        f'<a class="cta" href="{BASE_URL}{lang_prefix}/devenir-partenaire?lieu={attr(slug)}">'
        f'{T("become_partner")} {SVG_ARROW}</a>'
        '</article>'
    )

def _default_invites(d):
    """Venue-parameterized invite tiers when JSON has no partners block."""
    name = L("name", "")
    commune = d.get("commune", "")
    in_ = T("in_town")
    here = f"{in_} {commune}" if commune else ""
    q = T("qmark")
    return [
        {"tier":"invite","invite_type":"restaurant","i18n":{_LANG:{
            "title": f"{T('invite_resto_t')} {here}{q}".strip(),
            "desc":  f"{T('invite_resto_d')} {name} ? {T('invite_resto_d2')}"}}},
        {"tier":"invite","invite_type":"commerce","i18n":{_LANG:{
            "title": f"{T('invite_com_t')} {here}{q}".strip(),
            "desc":  f"{T('invite_com_d')} {name}."}}},
        {"tier":"invite","invite_type":"hebergement","i18n":{_LANG:{
            "title": f"{T('invite_hosp_t')}{q}".strip(),
            "desc":  f"{T('invite_hosp_d')} {here}.".strip()}}},
    ]

def partners_block(d):
    """Render the 'À proximité' section. Reads featured_businesses + partners; falls back to venue-parameterized invites."""
    slug = d["slug"]
    featured = d.get("featured_businesses") or []
    partners = d.get("partners") or []
    if not featured and not partners:
        partners = _default_invites(d)
    cards = []
    for p in featured + partners:
        tier = p.get("tier", "invite")
        if tier in ("partner", "recommended", "featured"):
            cards.append(_filled_partner_card(p))
        else:
            cards.append(_invite_card(p, slug))
    return (
        '<section class="block"><div class="wrap">'
        f'<div class="kicker reveal">{T("k_partners")}</div>'
        f'<h2 class="reveal">{T("h_partners")}</h2>'
        f'<div class="partners reveal" data-stagger>{"".join(cards)}</div>'
        '</div></section>'
    )


def gallery_block(name, photos=None):
    """Real-photo tiles when `photos` provided (list of {src, alt, credit}); else 6 placeholders."""
    placeholder = (
        '<div class="tile placeholder"><svg viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" '
        'height="18" rx="2"/><circle cx="9" cy="9" r="2"/>'
        '<path d="M21 15l-5-5L5 21"/></svg></div>'
    )
    if photos:
        parts = []
        for p in photos:
            src = p.get("src", "")
            if not src:
                continue
            url = src if src.startswith(("http://", "https://", "/")) else f"/{src}"
            alt = p.get("alt") or name
            credit = p.get("credit")
            cred_html = (f'<span class="tile-credit">{esc(credit)}</span>'
                         if credit else "")
            parts.append(
                f'<div class="tile"><img src="{attr(url)}" alt="{attr(alt)}" '
                f'loading="lazy" width="600" height="600">{cred_html}</div>'
            )
        tiles = "".join(parts) if parts else placeholder * 6
    else:
        tiles = placeholder * 6
    return (
        '<section class="block"><div class="wrap">'
        f'<div class="kicker reveal">{T("k_photos")}</div>'
        f'<h2 class="reveal">{T("h_gallery")}</h2>'
        f'<div class="gallery reveal" data-stagger>{tiles}</div>'
        '<div class="gallery-invite reveal"><div class="icn">'
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>'
        '<circle cx="12" cy="13" r="4"/></svg></div>'
        f'<p><strong>{T("g_been_q")}</strong> {T("g_invite")} '
        f'<a href="mailto:{siteconfig.PHOTOS_EMAIL}?subject={T("photos_subject")}{url_q(name)}">'
        f'{siteconfig.PHOTOS_EMAIL}</a></p></div></div></section>'
    )


def clean_eyebrow(badge, is_free):
    """Pick a clean eyebrow label (locale-aware)."""
    if badge:
        if "Pavillon Bleu" in badge:
            return badge
        if "Plage surveillée" in badge:
            return badge
        b = badge.strip()
        if b.upper().startswith("GRATUIT") or b.upper().startswith("FREE"):
            return T("free_dot")
        if len(b) <= 28 and "€" in b and not b.rstrip().endswith(("si", "i", ",", "·")):
            return (T("paid_prefix") if not is_free else "") + b
    return T("free_dot") if is_free else T("paid_dot")


def hero_block(d):
    """Render the hero section (locale-aware)."""
    name = L("name", "")
    hero = L("hero", {}) or {}
    badge = hero.get("badge", "") if isinstance(hero, dict) else ""
    lead = hero.get("lead", "") if isinstance(hero, dict) else ""
    alt = L("hero_alt", name)
    is_free = d.get("schema_org", {}).get("is_free", False)
    booking_url = d.get("booking_url") or d.get("official_site_url") or "#"
    official = d.get("official_site_url") or ""
    commune = d["commune"]

    # Post-Phase-1: shared generics live at /img/generique/<file>; real
    # per-lieu heros at /img/<hub>/<slug>-hero.jpg. hero_image in Json/
    # is always either a full URL, a /img/-prefixed path, or empty.
    GENERIC_ON_DISK = {"attraction", "cascade", "chateau", "domaine", "lac",
                       "musee", "parc", "point-de-vue", "sentier", "telecabine", "voie-verte"}
    img = d.get("hero_image") or ""
    if img.startswith(("http://", "https://", "//")):
        img_src = img
        gen_attr = ""
    elif img.startswith("/img/"):
        img_src = img
        basename = img.rsplit("/", 1)[-1]
        if basename.startswith("generique-"):
            gen_cat = basename[len("generique-"):].rsplit(".", 1)[0]
            gen_attr = f' data-generique="true" data-generique-cat="{gen_cat}"'
        else:
            gen_attr = ""
    elif img.startswith("/"):
        # Legacy absolute path — pass through (safety net)
        img_src = img
        gen_attr = ""
    elif img.startswith("generique-"):
        img_src = f"/img/generique/{img}"
        gen_cat = img[len("generique-"):].rsplit(".", 1)[0]
        gen_attr = f' data-generique="true" data-generique-cat="{gen_cat}"'
    elif img:
        # Legacy bare local non-generic filename — pass through at root
        img_src = f"/{img}"
        gen_attr = ""
    else:
        cat = d.get("category") or "attraction"
        eff_cat = cat if cat in GENERIC_ON_DISK else "attraction"
        img_src = f"/img/generique/generique-{eff_cat}.jpg"
        gen_attr = f' data-generique="true" data-generique-cat="{eff_cat}"'

    # Visible photo attribution (CC BY/BY-SA require it). Shown only for real
    # credited photos — skip generic placeholders / empty.
    cred = (d.get("hero_credit") or "").strip()
    if cred and not re.search(r"g[ée]n[ée]rique|à remplacer|placeholder", cred, re.I):
        hero_credit_html = (
            '<div class="hero-credit">'
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>'
            '<circle cx="12" cy="13" r="4"/></svg>'
            f'{esc(cred)}</div>'
        )
    else:
        hero_credit_html = ""

    eyebrow_text = clean_eyebrow(badge, is_free)
    cta_buttons = []
    if not is_free and booking_url and booking_url != "#":
        cta_buttons.append(
            f'<a href="{attr(booking_url)}" class="btn btn-primary" target="_blank" rel="noopener">'
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M3 7v3a3 3 0 0 0 0 6v3a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-3a3 3 0 0 0 0-6V7a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2z"/>'
            '<line x1="13" y1="5" x2="13" y2="7"/><line x1="13" y1="11" x2="13" y2="13"/>'
            f'<line x1="13" y1="17" x2="13" y2="19"/></svg>{T("book")}</a>'
        )
    cta_buttons.append(
        f'<a href="https://www.google.com/maps/search/?api=1&query={maps_query(d, name, commune)}{maps_place_param(d, "query")}" class="btn btn-ghost" '
        'target="_blank" rel="noopener">'
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>'
        f'<circle cx="12" cy="10" r="3"/></svg>{T("map_view")}</a>'
    )
    if official:
        cta_buttons.append(
            f'<a href="{attr(official)}" class="btn btn-ghost" target="_blank" rel="noopener">'
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/>'
            '<path d="M12 2a15 15 0 0 1 4 10 15 15 0 0 1-4 10 15 15 0 0 1-4-10 15 15 0 0 1 4-10z"/>'
            f'</svg>{T("official_site")}</a>'
        )

    return (
        '<section class="hero"><div class="wrap"><div class="grid">'
        '<div>'
        f'<span class="eyebrow reveal"><span class="dot"></span>{esc(eyebrow_text)}</span>'
        f'{hammer_h1(name)}'
        f'<p class="lede reveal">{esc(lead)}</p>'
        f'<div class="cta-row reveal">{"".join(cta_buttons)}</div>'
        f'{geo_verified_badge(d)}'
        '</div>'
        '<div class="reveal"><div class="hero-img">'
        f'{picture_tag(img_src, alt, eager=True, extra=gen_attr)}'
        '</div>'
        f'{hero_credit_html}'
        '</div>'
        '</div></div></section>'
    )


def action_bar(d, frozen=False):
    """Sticky bottom action bar (Book / Directions / Official site / Share) —
    locale-aware. `frozen` (protected partner page) drops the Share button so the
    page stays byte-identical."""
    name = L("name", "")
    commune = d["commune"]
    is_free = d.get("schema_org", {}).get("is_free", False)
    booking_url = d.get("booking_url") or d.get("official_site_url")
    official = d.get("official_site_url") or ""

    actions = []
    if not is_free and booking_url:
        actions.append(
            f'<a class="primary" href="{attr(booking_url)}" target="_blank" rel="noopener">'
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M3 7v3a3 3 0 0 0 0 6v3a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-3a3 3 0 0 0 0-6V7a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2z"/>'
            '<line x1="13" y1="5" x2="13" y2="7"/><line x1="13" y1="11" x2="13" y2="13"/>'
            f'<line x1="13" y1="17" x2="13" y2="19"/></svg><span>{T("book")}</span></a>'
        )
    actions.append(
        f'<a href="https://www.google.com/maps/dir/?api=1&destination={maps_query(d, name, commune)}{maps_place_param(d, "destination")}" '
        'target="_blank" rel="noopener">'
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>'
        f'<circle cx="12" cy="10" r="3"/></svg><span>{T("directions")}</span></a>'
    )
    if official:
        actions.append(
            f'<a href="{attr(official)}" target="_blank" rel="noopener">'
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/>'
            '<path d="M12 2a15 15 0 0 1 4 10 15 15 0 0 1-4 10 15 15 0 0 1-4-10 15 15 0 0 1 4-10z"/>'
            f'</svg><span>{T("official_site")}</span></a>'
        )
    # Share (PWA-share handoff): native share sheet where available, clipboard
    # fallback otherwise — never a dead button. Dropped on byte-frozen partner
    # pages. Each language shares its OWN canonical URL.
    share = ""
    if not frozen:
        actions.append(
            f'<button type="button" class="share-btn" onclick="shareLieu(this)" '
            f'data-copied="{attr(T("link_copied"))}">'
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/>'
            '<circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/>'
            '<line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>'
            f'<span class="share-label">{T("share")}</span></button>'
        )
        share = (
            # Inlined here (not in style.css) so protected partner pages — which
            # never receive this block — stay byte-identical without an approval
            # trailer. style.css is inlined per page, so editing it would touch
            # every page including the frozen ones.
            '<style>.action-bar .share-btn{flex:1;display:inline-flex;flex-direction:column;'
            'align-items:center;justify-content:center;gap:.15rem;padding:.55rem .5rem;'
            'border-radius:10px;background:var(--surface);border:1px solid var(--line);'
            'color:var(--ink);font-size:.7rem;font-weight:600;line-height:1.2;text-align:center;'
            'cursor:pointer;font-family:inherit}.action-bar .share-btn:hover{background:var(--accent);'
            'color:var(--accent-ink);border-color:var(--accent);transform:translateY(-2px)}'
            '.action-bar .share-btn svg{width:18px;height:18px;margin-bottom:.1rem}'
            '.action-bar .share-btn[data-done]{background:var(--good);color:var(--accent-ink);'
            'border-color:var(--good)}.action-bar .share-btn[data-done] .share-label{display:none}'
            '.action-bar .share-btn[data-done]::after{content:attr(data-copied)}'
            '@media (min-width:720px){.action-bar .share-btn{flex-direction:row;font-size:.8125rem;'
            'padding:.7rem 1rem}.action-bar .share-btn svg{margin:0}}</style>'
            '<script>function shareLieu(b){'
            'var u=(document.querySelector(\'link[rel=canonical]\')||{}).href||location.href,'
            't=document.title;'
            'if(navigator.share){navigator.share({title:t,url:u}).catch(function(){});return;}'
            'if(navigator.clipboard){navigator.clipboard.writeText(u).then(function(){'
            'b.dataset.done="1";setTimeout(function(){delete b.dataset.done;},2000);'
            '}).catch(function(){window.prompt(b.getAttribute("data-copied"),u);});}'
            'else{window.prompt(b.getAttribute("data-copied"),u);}}</script>'
        )
    return (
        '<div class="action-bar" id="actionBar"><div class="wrap">'
        + "".join(actions)
        + '</div></div>' + share
    )


# ---------------------------------------------------------------------------
# HANDOFF-32 — facts-derived title/meta fallbacks. When a language's own
# meta_title / meta_description is absent, the page must NEVER ship the FR
# string verbatim (508 duplicate titles across 2,369 pages — Bing was flagging
# them) nor a bare shared "<commune> (Haute-Savoie)." (×120). Instead: derive
# from data we already hold in that language — the reviewed vocabulary
# (descriptors / category labels / price words / the per-language meta_tail
# sentence) + the frozen FR name and commune. Unique per (fiche, language) by
# construction: the name separates fiches, the meta_tail separates languages.
# Translated prose, when it lands, overrides the fallback (floor, not ceiling).
# ---------------------------------------------------------------------------

_SITE_CHROME = json.loads((REPO / "data" / "site-chrome-langs.json").read_text(encoding="utf-8"))
_I18N_LABELS = json.loads((REPO / "data" / "i18n-labels.json").read_text(encoding="utf-8"))


def _type_label(d):
    """Localized type for this fiche: singular descriptor where the vocabulary
    has one (8 langs), else the category label (all 12). Reviewed sources only."""
    from build_pilot_langs import CATEGORY_DESCRIPTOR
    cat = d.get("category") or ""
    desc_key = CATEGORY_DESCRIPTOR.get(cat)
    if desc_key:
        v = _I18N_LABELS["descriptors_by_type"].get(desc_key, {}).get(_LANG)
        if v:
            return v
    return _SITE_CHROME["category_labels"].get(_LANG, {}).get(cat, "")


def _facts_price(d):
    """Language-clean price string: a real price, or the localized
    Gratuit/Payant word. None when the tariff is unknown (never invented)."""
    so = d.get("schema_org") or {}
    price_from = d.get("price_from")
    if isinstance(price_from, (int, float)) and price_from > 0:
        cur = {"EUR": "€"}.get(d.get("price_currency"), d.get("price_currency") or "€")
        return f"{price_from:.2f}".replace(".", ",") + f" {cur}"
    pw = _SITE_CHROME["price_words"].get(_LANG) or {}
    if so.get("is_free") is True:
        return pw.get("gratuit")
    if so.get("is_free") is False:
        return pw.get("payant")
    return None


def facts_title(d):
    """`{localized type} {frozen name} · {commune} | Loisirs 74` — the type is
    dropped when the name already starts with it (no 'Karting Karting de
    Rumilly'). Unique per fiche (name + commune); cross-language alternates of
    the SAME fiche may coincide where the type word coincides — that is the
    hreflang cluster, not a SERP duplicate."""
    fr = (d.get("i18n") or {}).get("fr") or {}
    name = fr.get("name") or d.get("slug", "")
    commune = d.get("commune") or ""
    t = _type_label(d)
    if t and name.lower().startswith(t.lower()):
        t = ""
    core = f"{t} {name}".strip()
    return f"{core} · {commune} | {siteconfig.SITE_NAME}" if commune else f"{core} | {siteconfig.SITE_NAME}"


def facts_meta(d):
    """`{type} — {name}, {commune} (Haute-Savoie). {price}. {meta_tail}` —
    every component from reviewed vocabulary or frozen facts; the per-language
    meta_tail sentence guarantees cross-language uniqueness."""
    fr = (d.get("i18n") or {}).get("fr") or {}
    name = fr.get("name") or d.get("slug", "")
    commune = d.get("commune") or ""
    t = _type_label(d)
    place = f"{name}, {commune} ({siteconfig.DEPT_NAME})." if commune else f"{name} ({siteconfig.DEPT_NAME})."
    parts = [f"{t} — {place}" if t else place]
    price = _facts_price(d)
    if price:
        parts.append(f"{price}.")
    tail = _SITE_CHROME["commune_chrome"].get(_LANG, {}).get("meta_tail")
    if tail:
        parts.append(tail)
    return " ".join(parts)


def build_ldjson(d, desc_override=""):
    """Build the WebSite + BreadcrumbList + (TouristAttraction|Place) + FAQPage graph (locale-aware)."""
    slug = d["slug"]
    name = L("name", "")
    commune = d["commune"]
    lat = d.get("latitude")
    lon = d.get("longitude")
    postal = d.get("postal_code", "")
    sch = d.get("schema_org", {})
    is_free = sch.get("is_free", False)
    place_type = sch.get("type") or "TouristAttraction"
    amenities = L("schema_amenities", None) or sch.get("amenities") or []
    faq = L("faq", []) or []
    in_lang = CHROME["in_lang"][_LANG]
    lang_prefix = f"/{_LANG}" if _LANG != "fr" else ""

    page_url = f"{BASE_URL}{lang_prefix}/{slug}"
    site_url = f"{BASE_URL}{lang_prefix}/"
    graph = [
        {
            "@type": "WebSite",
            "@id": f"{BASE_URL}/#website",
            "url": site_url,
            "name": siteconfig.SITE_NAME,
            "inLanguage": in_lang,
        },
        {
            "@type": "BreadcrumbList",
            "@id": f"{page_url}#breadcrumb",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": T("home"), "item": site_url},
                (
                    {"@type": "ListItem", "position": 2,
                     "name": primary_hub(d, _LANG)[1],
                     "item": f"{BASE_URL}{lang_prefix}/{primary_hub(d, _LANG)[0]}/"}
                    if primary_hub(d, _LANG) else
                    {"@type": "ListItem", "position": 2, "name": commune,
                     "item": f"{BASE_URL}{lang_prefix}/#{commune.lower().replace(' ', '-')}"}
                ),
                {"@type": "ListItem", "position": 3, "name": name},
            ],
        },
    ]
    place = {
        "@type": place_type,
        "@id": f"{page_url}#place",
        "name": name,
        "alternateName": L("name_alternates", []),
        "description": desc_override or L("meta_description", ""),
        "url": page_url,
        "address": {
            "@type": "PostalAddress",
            "addressLocality": commune,
            "postalCode": str(postal),
            "addressRegion": siteconfig.DEPT_NAME,
            "addressCountry": "FR",
        },
        "isAccessibleForFree": bool(is_free),
        "publicAccess": bool(sch.get("public_access", True)),
        "image": "",
    }
    # schema.org dateModified: ISO from the lastmod manifest. Byte-frozen partner
    # pages are left untouched (keeps gate_protected_placements green).
    if not _FROZEN:
        _lm = _lastmod_iso(d)
        if _lm:
            place["dateModified"] = _lm
    if lat is not None and lon is not None:
        place["geo"] = {"@type": "GeoCoordinates", "latitude": lat, "longitude": lon}
    if amenities:
        place["amenityFeature"] = [
            {"@type": "LocationFeatureSpecification", "name": str(a), "value": True}
            for a in amenities
        ]
    # NO `offers` here (JOB 5). `offers` is not a schema.org property of Place —
    # it belongs to Product/Service/Event. Nesting an Offer inside a Place node
    # made Google reclassify these fiches into its product-snippets system, which
    # is what surfaced as the "Extraits de produits" report in Search Console.
    # The price stays where it belongs: visible in the facts table and the FAQ,
    # with isAccessibleForFree as the machine-readable cost signal.
    graph.append(place)

    if faq:
        graph.append({
            "@type": "FAQPage",
            "@id": f"{page_url}#faq",
            "mainEntity": [
                {"@type": "Question", "name": q.get("q", ""),
                 "acceptedAnswer": {"@type": "Answer", "text": q.get("a", "")}}
                for q in faq
            ],
        })

    return json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False)


def build_head(d):
    """Render the <head> section (locale-aware)."""
    slug = d["slug"]
    name = L("name", "")
    # HANDOFF-32: the page's OWN language strings, or the facts-derived
    # fallback — never the FR meta_title/meta_description verbatim on a non-FR
    # page (the 508-duplicate-titles disease), never a bare shared commune
    # string. Two leak paths are closed: the FR *fallback* (absent locale
    # field) AND the FR *mirror* (locale field present but byte-equal to the
    # FR string — untranslated Json copies, same class the related-carousel
    # already suppresses). Translated prose overrides the fallback.
    def _own(key):
        v = _LOC.get(key) if isinstance(_LOC, dict) else None
        if v and _LANG != "fr" and isinstance(_FR, dict) and v == _FR.get(key):
            return None   # FR-mirrored, untranslated
        return v

    title = _own("meta_title") or facts_title(d)
    desc = _own("meta_description") or facts_meta(d)
    lat = d.get("latitude") or 0
    lon = d.get("longitude") or 0
    commune = d["commune"]
    lang_prefix = f"/{_LANG}" if _LANG != "fr" else ""
    page_url = f"{BASE_URL}{lang_prefix}/{slug}"
    fr_url = f"{BASE_URL}/{slug}"
    html_lang = CHROME["html_lang"][_LANG]
    og_loc = CHROME["og_locale"][_LANG]
    # dir attribute emitted ONLY for RTL langs (ar/he) so LTR pages — the live 6
    # and pl/pt/cs/ja — stay byte-identical (no dir="ltr" added).
    dir_attr = ' dir="rtl"' if locales.DIR.get(_LANG) == "rtl" else ''

    # Emit the full 7-lang hreflang cluster (the 6 + pl). The 6's pages are
    # produced for every fiche by build_all_locales (with FR-fallback content
    # when a lang block is absent), so the cluster matches what's on disk.
    hreflang_lines = [f'<link rel="alternate" hreflang="fr" href="{fr_url}">']
    for lg in locales.VISIBLE_SECONDARY:  # isolation-ok: hreflang alternates cluster
        hreflang_lines.append(f'<link rel="alternate" hreflang="{lg}" href="{BASE_URL}/{lg}/{slug}">')
    hreflang_lines.append(f'<link rel="alternate" hreflang="x-default" href="{fr_url}">')
    hreflang_block = "\n".join(hreflang_lines)

    # Localize CSS "Générique" overlay
    css = CSS.replace('content: "Générique"', f'content: "{T("generic")}"')
    if dir_attr:
        # RTL-only fixups appended to the page CSS (LTR pages byte-identical):
        # the skip link is parked at left:-9999px, which in an RTL document
        # EXPANDS the scrollable area leftward (10 000px horizontal overflow —
        # the Layer A failure class). Park it inline-start instead.
        css += ("\n[dir=rtl] a.skip{left:auto;inset-inline-start:-9999px}"
                "\n[dir=rtl] a.skip:focus{inset-inline-start:0}"
                # the hammer h1 wraps each word of the frozen FR name in an
                # inline-block span; atomic boxes follow paragraph direction, so
                # RTL reversed the words ("Rouget du Cascade"). Keep the Latin
                # name LTR inside the right-aligned RTL hero.
                "\n[dir=rtl] h1.hammer{direction:ltr;text-align:right}")

    ldjson = build_ldjson(d, desc_override=desc)
    hero_alt = L("hero_alt", name)

    return f"""<!doctype html>
<html lang="{html_lang}"{dir_attr} data-theme="auto">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#0b0d10" media="(prefers-color-scheme: dark)">
<meta name="theme-color" content="#fafaf7" media="(prefers-color-scheme: light)">
<title>{esc(title)}</title>
<link rel="icon" type="image/x-icon" href="/favicon.ico">
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png">
<link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png">
<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<meta name="theme-color" content="#1c4f62">
<meta name="description" content="{attr(desc)}">
<link rel="canonical" href="{page_url}">
{hreflang_block}
<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1">
<meta name="referrer" content="strict-origin-when-cross-origin">
<meta property="og:type" content="article">
<meta property="og:title" content="{attr(name)}">
<meta property="og:description" content="{attr(desc)}">
<meta property="og:url" content="{page_url}">
<meta property="og:locale" content="{og_loc}">
<meta property="og:site_name" content="{siteconfig.SITE_NAME}">
<meta property="og:image:alt" content="{attr(hero_alt)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{attr(name)}">
<meta name="twitter:description" content="{attr(desc)}">
<meta name="geo.region" content="FR-73">
<meta name="geo.placename" content="{attr(commune)}">
<meta name="geo.position" content="{lat};{lon}">
<meta name="ICBM" content="{lat}, {lon}">
<style>{css}</style>
<script type="application/ld+json">{ldjson}</script>
<meta property="og:image" content="{BASE_URL}/og-image.jpg">
<meta name="twitter:image" content="{BASE_URL}/og-image.jpg">
<!-- AI discovery: per-lieu markdown mirror -->
<link rel="alternate" type="text/markdown" href="/content/{slug}.md" title="Markdown version">
<meta name="ai:content-url" content="{BASE_URL}/content/{slug}.md">
<meta name="ai:policy-url" content="{BASE_URL}/.well-known/ai-info.json">
</head>"""


def build_header(d):
    """Sticky site header with brand + lang picker (locale-aware)."""
    slug = d["slug"]
    lang_prefix = f"/{_LANG}" if _LANG != "fr" else ""
    site_url = f"{BASE_URL}{lang_prefix}/"
    hub = primary_hub(d, _LANG)
    if hub:
        hub_slug, hub_label = hub
        crumb_mid = f'<a href="{BASE_URL}{lang_prefix}/{hub_slug}/">{esc(hub_label)}</a>'
    else:
        crumb_mid = f'<span>{esc(d["commune"])}</span>'

    # Lang picker: full 7-lang menu (the 6 + pl facts tree). aria-current on active.
    pick_links = []
    for lg in locales.VISIBLE:  # isolation-ok: picker links
        prefix = f"/{lg}" if lg != "fr" else ""
        href = f"{BASE_URL}{prefix}/{slug}"
        cur = ' aria-current="true"' if lg == _LANG else ''
        pick_links.append(f'<a href="{href}"{cur} hreflang="{lg}">{CHROME["lang_native"][lg]}</a>')
    pick_html = "\n".join(pick_links)
    name = L("name", "")

    return f"""<body>
<a class="skip" href="#main">{T("skip")}</a>
<header class="site"><div class="wrap">
  <a class="brand" href="{site_url}" aria-label="{siteconfig.SITE_NAME}"><span class="mark" aria-hidden="true"><img src="/logo.png" alt="" width="38" height="38" style="border-radius:8px;display:block;"></span><span>{siteconfig.SITE_NAME}</span></a>
  <nav><details class="lang-picker"><summary aria-label="{T("lang_choose")}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15 15 0 010 20M12 2a15 15 0 000 20"/></svg>{T("lang_label")}</summary><div class="lang-menu">{pick_html}</div></details></nav>
</div></header>
<main id="main">
<div class="wrap"><nav class="crumb" aria-label="Breadcrumb"><a href="{site_url}">{T("home")}</a><span class="sep">/</span>{crumb_mid}<span class="sep">/</span><span aria-current="page">{esc(name)}</span></nav></div>"""


def build_footer_block(date_pub, date_mod):
    return (
        '<div class="wrap"><p class="meta">'
        f'<span>{T("published")} {esc(date_pub)}</span><span class="sep">·</span>'
        f'<span>{T("updated")} {esc(date_mod)}</span></p></div>'
        '</main>'
    )


# Per-fiche event modals: a venue promoting its OWN event on its own page.
# `end`: the modal stops showing client-side after this date (no rebuild needed).
EVENT_MODALS = {
    "domaine-du-tornet": {
        "id": "ev-tornet-fm26",
        "affiche": "/img/events/fete-musique-tornet-2026.jpg",
        "url": "http://chaletdutornet.com/",
        "alt": "Affiche Fête de la Musique au Chalet du Tornet — dimanche 21 juin",
        "end": "2026-06-22",
    },
}


def event_modal_block(d):
    """Render a branded, dismissible event modal — only on the fiche of the
    venue that hosts the event (master to-do: Tornet Fête de la Musique).
    Shows once per session and auto-disappears (client-side) after `end`. The
    eyebrow ties it to this exact page so it reads as part of the fiche, not a
    third-party ad."""
    ev = EVENT_MODALS.get(d.get("slug"))
    if not ev:
        return ""
    name = L("name", d.get("slug"))
    img = picture_tag(ev["affiche"], ev["alt"], eager=False)
    return (
        f'<div class="event-modal-overlay" id="{ev["id"]}" role="dialog" aria-modal="true" '
        f'aria-label="{attr(name)}">'
        '<div class="event-modal">'
        f'<button class="event-modal-close" type="button" aria-label="{attr(T("ev_close"))}">&times;</button>'
        f'<div class="event-modal-eyebrow">{T("ev_intro")} · {esc(name)}</div>'
        f'<a class="event-modal-affiche" href="{attr(ev["url"])}" target="_blank" rel="noopener">{img}</a>'
        f'<a class="event-modal-cta" href="{attr(ev["url"])}" target="_blank" rel="noopener">{T("ev_cta")} &rarr;</a>'
        '</div></div>'
        '<script>(function(){'
        f'var END=new Date("{ev["end"]}T00:00:00"),KEY="{ev["id"]}";'
        'if(new Date()>=END)return;try{if(sessionStorage.getItem(KEY))return;}catch(e){}'
        f'var ov=document.getElementById("{ev["id"]}");if(!ov)return;'
        'function close(){ov.classList.remove("in");try{sessionStorage.setItem(KEY,"1");}catch(e){}'
        'setTimeout(function(){ov.style.display="none";},300);}'
        'setTimeout(function(){ov.style.display="flex";requestAnimationFrame(function(){ov.classList.add("in");});},900);'
        'ov.querySelector(".event-modal-close").addEventListener("click",close);'
        'ov.addEventListener("click",function(e){if(e.target===ov)close();});'
        'document.addEventListener("keydown",function(e){if(e.key==="Escape")close();});'
        '})();</script>'
    )


# ── footer "Explorer" column: the intent-guide layer ────────────────────────
# GSC coverage 2026-07-27: the five practical guides (PMR, parking, gratuit,
# hiver, transports) each had exactly ONE internal link (homepage) — near-
# orphans that Google crawls and declines to index. The footer is the honest
# place for them: sitewide reach, zero per-fiche authoring. Labels are DERIVED
# from each guide's own rendered <h1> (text before the first " :"), per locale
# — never authored here, so they can't rot when a guide is retitled.
FOOTER_GUIDE_SLUGS = (
    "sorties-gratuites-haute-savoie",
    "sorties-famille-enfants-haute-savoie",
    "acces-pmr-haute-savoie",
    "parking-sites-loisirs-74",
    "acces-transports-en-commun-74",
    "infos-hiver-haute-savoie",
)
_FOOTER_GUIDES_CACHE = {}   # lang -> [(href, label)]


def _footer_guides(lang):
    """(href, label) pairs for the guide links, derived from the built pages.
    A guide exists per-locale for the six prose langs only; facts langs link
    the FR original (same fallback rule as the legal links). A guide whose
    HTML is missing renders nothing — the footer never links a 404."""
    if lang in _FOOTER_GUIDES_CACHE:
        return _FOOTER_GUIDES_CACHE[lang]
    out = []
    for slug in FOOTER_GUIDE_SLUGS:
        for lp_try in ([f"/{lang}", ""] if lang != "fr" else [""]):
            p = REPO / lp_try.lstrip("/") / f"{slug}.html"
            if not p.is_file():
                continue
            m = re.search(r"<h1[^>]*>(.*?)</h1>",
                          p.read_text(encoding="utf-8"), re.S)
            if not m:
                continue
            label = re.sub(r"<[^>]+>", "", m.group(1))
            label = html_lib.unescape(label).split(":")[0].split(" — ")[0].strip()
            if label:
                out.append((f"{BASE_URL}{lp_try}/{slug}", label))
            break
    _FOOTER_GUIDES_CACHE[lang] = out
    return out


def sister_link_html():
    """One line in the footer pointing at the sibling département's site.

    Config-driven and OFF unless site.config.json carries a `sister` block, on
    purpose: a sitewide footer link is ~6 100 links from this site: pointing
    that at a domain that does not resolve yet would be 6 100 dead links, and
    switching it on before the sibling has content buys nothing. Add the block
    the day the sibling goes live — that is the whole flip.

        "sister": {"name": "Loisirs 73", "url": "https://loisirs73.fr",
                   "dept": "Savoie"}

    Deliberately NOT rel="nofollow": this is a genuine same-publisher
    relationship, disclosed as such, not a link scheme. Deliberately ONE line,
    not a column: the honest value between the two sites is contextual
    page-to-page linking (shared GR®, cols, "30 min away"), not footer bulk.
    """
    sis = getattr(siteconfig, "SISTER", None)
    if not sis or not sis.get("url") or not sis.get("name"):
        return ""
    dept = esc(sis.get("dept") or "")
    # French puts a space before a colon; English and the rest do not. Japanese
    # takes no space around the label either.
    lead = "" if _LANG == "ja" else " "
    colon = " : " if _LANG == "fr" else ": "
    return (f'<span class="sister">{T("f_sister")}{lead}{dept}{colon}'
            f'<a href="{attr(sis["url"])}">{esc(sis["name"])}</a></span>')


def site_footer():
    """Locale-aware <footer class='site'>. URLs prefixed by current locale."""
    lp = f"/{_LANG}" if _LANG != "fr" else ""
    # signaler / devenir-partenaire / mentions-legales / confidentialite / cgv
    # exist per-locale for the six only; a facts-lang rich tree links the FR
    # originals instead of 404ing on /<lang>/… (link-integrity gate).
    legal_lp = "" if _STRICT_PROSE else lp
    guide_lis = "".join(f'<li><a href="{attr(h)}">{esc(t)}</a></li>'
                        for h, t in _footer_guides(_LANG))
    return (
        '<footer class="site"><div class="wrap"><div class="foot-grid">'
        f'<div class="foot-col"><a class="brand" href="{BASE_URL}{lp}/" style="margin-bottom:.85rem"><span class="mark" aria-hidden="true"><img src="/logo.png" alt="" width="30" height="30" style="border-radius:7px;display:block;"></span><span>{siteconfig.SITE_NAME}</span></a><p>{T("f_tagline")}</p></div>'
        f'<div class="foot-col"><h4>{T("f_explore")}</h4><ul><li><a href="{BASE_URL}{lp}/">{T("home")}</a></li>{guide_lis}</ul></div>'
        f'<div class="foot-col"><h4>{T("f_contribute")}</h4><ul><li><a href="mailto:{siteconfig.PHOTOS_EMAIL}">{T("f_send_photos")}</a></li><li><a href="{BASE_URL}{legal_lp}/signaler">{T("f_report")}</a></li><li><a href="{BASE_URL}{legal_lp}/devenir-partenaire">{T("f_become_p")}</a></li></ul></div>'
        f'<div class="foot-col"><h4>{T("f_legal")}</h4><ul><li><a href="{BASE_URL}{legal_lp}/mentions-legales">{T("f_legal_link")}</a></li><li><a href="{BASE_URL}{legal_lp}/confidentialite">{T("f_privacy")}</a></li><li><a href="{BASE_URL}{legal_lp}/cgv">{T("f_cgv")}</a></li></ul></div>'
        f'</div><div class="foot-bottom"><span class="credit">{T("f_copyright")}</span>{sister_link_html()}<span>{T("f_promise")}</span></div></div></footer>'
    )


LAST_FALLBACK_FIELDS = set()  # populated by build_page() for callers wanting coverage info


_RELATED_CACHE = {}


def _related_name(slug, lang):
    """Localized name of a related fiche (read once, cached). None if the fiche
    is missing or not renderable — so a dangling related slug renders nothing."""
    if slug not in _RELATED_CACHE:
        p = REPO / "Json" / f"{slug}.json"
        try:
            _RELATED_CACHE[slug] = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            _RELATED_CACHE[slug] = None
    d = _RELATED_CACHE[slug]
    if not d or d.get("status") not in ("published", "verified"):
        return None
    i18n = d.get("i18n", {}) or {}
    return ((i18n.get(lang) or {}).get("name")
            or (i18n.get("fr") or {}).get("name") or slug)


def related_lieux_block(related, lang):
    """'Voir aussi' — sibling-lieu cross-links (e.g. two distinct points on one
    ridge). Reads top-level related_lieux: [slug]. Renders nothing if empty or
    all targets are unrenderable."""
    if not related:
        return ""
    prefix = "" if lang == "fr" else f"/{lang}"
    items = []
    for slug in related:
        nm = _related_name(slug, lang)
        if not nm:
            continue
        url = f"{BASE_URL}{prefix}/{slug}"
        items.append(f'<li><a href="{attr(url)}">{esc(nm)}</a></li>')
    if not items:
        return ""
    return (
        '<section class="block"><div class="wrap">'
        f'<div class="kicker reveal">{T("k_see_also")}</div>'
        f'<h2 class="reveal">{T("k_see_also")}</h2>'
        f'<ul class="related-lieux reveal">{"".join(items)}</ul>'
        '</div></section>'
    )


# ---------------------------------------------------------------------------
# "À proximité" proximity carousel (native port of the old update_related.py,
# which lived OUTSIDE the builder and was wiped by a full rebuild). Now it's
# emitted by build_page so it can never be clobbered again. Built once per
# process from published Json/, then reused for every fiche × locale.
# ---------------------------------------------------------------------------
_REL_LABELS = {
    "fr": {"kicker": "À proximité", "h2": "À proximité",
           "lead": "D'autres lieux à explorer dans le coin et dans la même catégorie",
           "free": "Gratuit", "paid": "Payant", "route": "Itinéraire", "site": "Site officiel"},
    "de": {"kicker": "In der Nähe", "h2": "In der Nähe",
           "lead": "Weitere Orte in der Umgebung und in derselben Kategorie",
           "free": "Kostenlos", "paid": "Kostenpflichtig", "route": "Route", "site": "Website"},
    "en": {"kicker": "Nearby", "h2": "Nearby",
           "lead": "Other places to explore in the area and in the same category",
           "free": "Free", "paid": "Paid", "route": "Directions", "site": "Official site"},
    "es": {"kicker": "Cerca", "h2": "Cerca",
           "lead": "Otros lugares para explorar en la zona y en la misma categoría",
           "free": "Gratis", "paid": "De pago", "route": "Ruta", "site": "Sitio oficial"},
    "it": {"kicker": "Nelle vicinanze", "h2": "Nelle vicinanze",
           "lead": "Altri luoghi da esplorare nei dintorni e nella stessa categoria",
           "free": "Gratis", "paid": "A pagamento", "route": "Indicazioni", "site": "Sito ufficiale"},
    "nl": {"kicker": "In de buurt", "h2": "In de buurt",
           "lead": "Andere plekken om te ontdekken in de buurt en in dezelfde categorie",
           "free": "Gratis", "paid": "Betaald", "route": "Route", "site": "Officiële website"},
}
_REL_LANGS = tuple(locales.VISIBLE)  # isolation-ok: carousel name/commune index spans the visible roster (new langs fall back to FR until their prose lands)
# Cross-department cards are rare by design (see _sister_rel_cards): only the
# handful of fiches within sister_proximity_km of the border get one. Keep
# their rules out of _REL_CSS so the other pages don't carry dead selectors.
_SIS_CSS = """
.sister-card{position:relative}
.sis-badge{position:absolute;top:.5rem;left:.5rem;z-index:2;background:rgba(11,81,112,.94);color:#fff;font-size:.68rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase;padding:.2rem .5rem;border-radius:999px}
"""
_REL_CSS = """
.related{padding:clamp(2rem,4vw,3.5rem) 0;border-top:1px solid var(--line);margin-bottom:5rem}
.related .wrap{max-width:64rem;margin-inline:auto;padding-inline:clamp(1rem,3vw,2rem)}
.related .kicker{font-size:.8125rem;font-weight:700;color:var(--accent);text-transform:uppercase;letter-spacing:.08em;margin-bottom:.65rem}
.related h2{font-size:clamp(1.3rem,1.1rem + .8vw,1.85rem);line-height:1.15;letter-spacing:-.015em;font-weight:800;margin:0 0 .4rem;color:var(--ink)}
.related .lead{color:var(--ink-soft);max-width:42rem;margin-bottom:1.5rem;font-size:1rem;line-height:1.55}
.related .carousel{display:grid;grid-template-columns:repeat(auto-fill,minmax(15rem,1fr));gap:1rem}
@media(max-width:680px){.related .carousel{display:flex;gap:.85rem;overflow-x:auto;scroll-snap-type:x mandatory;padding-bottom:.5rem;-webkit-overflow-scrolling:touch;scrollbar-width:none}.related .carousel::-webkit-scrollbar{display:none}.related .carousel > .card{flex:0 0 75vw;max-width:18rem;scroll-snap-align:start}}
.related .card{background:var(--surface);border:1px solid var(--line);border-radius:14px;overflow:hidden;display:flex;flex-direction:column;transition:transform .2s,border-color .2s,box-shadow .2s;text-decoration:none;color:inherit}
.related .card:hover{transform:translateY(-3px);border-color:color-mix(in srgb,var(--accent) 30%,var(--line));box-shadow:0 8px 24px -12px rgba(11,13,16,.18)}
.related .card-photo{display:block;aspect-ratio:4/3;background:var(--surface-2);overflow:hidden;position:relative;flex-shrink:0}
.related .card-photo img{width:100%;height:100%;object-fit:cover;display:block;transition:transform .35s}
.related .card:hover .card-photo img{transform:scale(1.03)}
.related .card-tag{position:absolute;top:.6rem;left:.6rem;background:color-mix(in srgb,var(--bg) 85%,transparent);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);color:var(--ink);padding:.2rem .55rem;border-radius:999px;font-size:.7rem;font-weight:700;letter-spacing:.02em}
.related .card-body{padding:.85rem 1rem 1rem;display:flex;flex-direction:column;gap:.35rem;flex:1}
.related .card-body a.title{font-weight:700;font-size:1rem;color:var(--ink);line-height:1.3;letter-spacing:-.005em;text-decoration:none}
.related .card-body a.title:hover{color:var(--accent)}
.related .card-commune{font-size:.78rem;color:var(--ink-mute);display:flex;align-items:center;gap:.3rem}
.related .card-commune svg{width:11px !important;height:11px !important;flex-shrink:0}
.related .card-desc{font-size:.85rem;color:var(--ink-soft);line-height:1.45;margin:.15rem 0 .65rem;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.related .card-actions{display:flex;gap:.4rem;margin-top:auto}
.related .card-actions a{flex:1;display:inline-flex;align-items:center;justify-content:center;gap:.3rem;padding:.5rem .6rem;border-radius:8px;font-size:.78rem;font-weight:600;border:1px solid var(--line);background:var(--bg);color:var(--ink-soft);text-decoration:none;transition:all .2s}
.related .card-actions a:hover{background:var(--accent);color:var(--accent-ink);border-color:var(--accent)}
.related .card-actions a svg{width:13px !important;height:13px !important}"""
_REL_PIN = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>'
            '<circle cx="12" cy="10" r="3"/></svg>')
_REL_GLOBE = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
              'stroke-linecap="round" stroke-linejoin="round">'
              '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/>'
              '<path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>')

_REL_INDEX = None   # slug -> data dict
_REL_MAP = None     # slug -> [≤6 related slugs]


def _haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _compute_related(target, idx):
    """3 nearest diff-category + 3 nearest same-category, diff first, with
    top-up from the other bucket. Deterministic (ties broken by slug)."""
    t = idx[target]
    same, diff = [], []
    for slug, d in idx.items():
        if slug == target:
            continue
        dist = _haversine(t["lat"], t["lon"], d["lat"], d["lon"])
        (same if d["category"] == t["category"] else diff).append((dist, slug))
    same.sort(); diff.sort()
    diff_pick = [s for _, s in diff[:3]]
    same_pick = [s for _, s in same[:3]]
    out = diff_pick + same_pick
    while len(out) < 6:
        if len(diff_pick) < 3 and len(diff) > len(diff_pick):
            out.append(diff[len(diff_pick)][1]); diff_pick.append(out[-1])
        elif len(same_pick) < 3 and len(same) > len(same_pick):
            out.append(same[len(same_pick)][1]); same_pick.append(out[-1])
        else:
            break
    return out[:6]


def _build_related_index():
    """Build the proximity index + related map ONCE from published Json/."""
    global _REL_INDEX, _REL_MAP
    fiches = []
    for fp in sorted((REPO / "Json").glob("*.json")):
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if d.get("status") in ("published", "verified") and d.get("category"):
            fiches.append(d)
    # per-category centroid for coord fallback (keeps coord-less fiches in the graph)
    cat_pts = {}
    for d in fiches:
        if d.get("latitude") is not None and d.get("longitude") is not None:
            cat_pts.setdefault(d["category"], []).append((d["latitude"], d["longitude"]))
    centroid = {c: (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
                for c, pts in cat_pts.items()}
    idx = {}
    for d in fiches:
        slug, cat = d["slug"], d["category"]
        lat, lon = d.get("latitude"), d.get("longitude")
        if lat is None or lon is None:
            if cat not in centroid:
                continue
            lat, lon = centroid[cat]
        i18n = d.get("i18n", {}) or {}
        fr = i18n.get("fr", {}) or {}
        fr_name = fr.get("name") or slug
        fr_desc = fr.get("meta_description") or ""
        fr_alt = fr.get("hero_alt") or fr_name
        names, communes, descs, alts = {}, {}, {}, {}
        for lg in _REL_LANGS:
            li = i18n.get(lg, {}) or {}
            names[lg] = li.get("name") or fr_name
            communes[lg] = li.get("commune") or d.get("commune") or ""
            loc_desc = li.get("meta_description") or ""
            loc_alt = li.get("hero_alt") or names[lg]
            if lg != "fr":   # suppress FR-mirrored (untranslated) strings on locale cards
                if loc_desc == fr_desc:
                    loc_desc = ""
                if loc_alt == fr_alt:
                    loc_alt = names[lg]
            descs[lg] = loc_desc
            alts[lg] = loc_alt
        idx[slug] = {
            "category": cat, "names": names, "communes": communes, "descs": descs,
            "alts": alts, "hero_image": d.get("hero_image") or f"/{slug}-hero.jpg",
            "is_free": (d.get("schema_org", {}) or {}).get("is_free", False),
            "lat": lat, "lon": lon, "official_url": d.get("official_site_url") or "",
        }
    rel = {s: _compute_related(s, idx) for s in idx}
    # Reciprocity floor: every fiche appears in ≥ _REL_FLOOR carousels, not
    # just ≥1. GSC coverage 2026-07-27: the crawled-not-indexed tail is the
    # weakly-linked tail (p10 = 7 inlinks vs median 12) — pure nearest-3
    # geometry starves fiches on the edge of a dense cluster, because their
    # neighbours' nearest-3 are always someone else. Fix: fiches below the
    # floor are placed into the carousels of their nearest hosts, replacing
    # the host's 6th slot — but never a slot held by another below-floor
    # fiche (we don't rob the poor to pay the poor). Deterministic; loops to
    # a fixed point (bounded — each pass only raises the minimum).
    _REL_FLOOR = 3
    for _ in range(8):
        inbound = {s: 0 for s in idx}
        for rels in rel.values():
            for r in rels:
                if r in inbound:
                    inbound[r] += 1
        starved = sorted(s for s, n in inbound.items() if n < _REL_FLOOR)
        if not starved:
            break
        moved = False
        for s in starved:
            need = _REL_FLOOR - inbound[s]
            hosts = sorted(
                (o for o in idx if o != s and s not in rel[o]),
                key=lambda o: (_haversine(idx[s]["lat"], idx[s]["lon"],
                                          idx[o]["lat"], idx[o]["lon"]), o))
            for o in hosts:
                if need <= 0:
                    break
                victim = rel[o][5] if len(rel[o]) == 6 else None
                if victim is not None and inbound.get(victim, 0) <= _REL_FLOOR:
                    continue    # would re-starve someone at/below the floor
                rel[o] = rel[o][:5] + [s]
                if victim is not None:
                    inbound[victim] -= 1
                inbound[s] += 1
                need -= 1
                moved = True
        if not moved:
            break
    _REL_INDEX, _REL_MAP = idx, rel


def _rel_img_src(hero):
    if not hero:
        return "/og-image.jpg"
    return hero if hero.startswith(("http://", "https://", "/")) else f"/{hero}"


def _render_rel_card(slug, lang, labels):
    d = _REL_INDEX[slug]
    name, commune = d["names"][lang], d["communes"][lang]
    desc, alt = d["descs"][lang], d["alts"][lang]
    tag = labels["free"] if d["is_free"] else labels["paid"]
    img = _rel_img_src(d["hero_image"])
    ref = ' referrerpolicy="no-referrer"' if img.startswith(("http://", "https://")) else ""
    prefix = "" if lang == "fr" else f"/{lang}"
    fiche_url = f"{BASE_URL}{prefix}/{slug}"
    maps_q = quote(f"{name}, {commune}, {siteconfig.DEPT_NAME}".strip(", "), safe="")
    maps_url = f"https://www.google.com/maps/dir/?api=1&destination={maps_q}"
    desc_html = f'<p class="card-desc">{esc(desc)}</p>' if desc else ""
    actions = [f'<a href="{maps_url}" target="_blank" rel="noopener">{_REL_PIN}<span>{labels["route"]}</span></a>']
    if d["official_url"]:
        actions.append(f'<a href="{attr(d["official_url"])}" target="_blank" rel="noopener">'
                       f'{_REL_GLOBE}<span>{labels["site"]}</span></a>')
    return (
        f'<article class="card">\n'
        f'    <a href="{fiche_url}" class="card-photo">\n'
        f'      <img src="{attr(img)}" alt="{attr(alt)}" loading="lazy"{ref}>\n'
        f'      <span class="card-tag">{tag}</span>\n'
        f'    </a>\n'
        f'    <div class="card-body">\n'
        f'      <a href="{fiche_url}" class="title">{esc(name)}</a>\n'
        f'      <div class="card-commune">{_REL_PIN}<span>{esc(commune)}</span></div>\n'
        f'      {desc_html}\n'
        f'      <div class="card-actions">\n'
        f'        {"".join(actions)}\n'
        f'      </div>\n'
        f'    </div>\n'
        f'  </article>'
    )


def related_carousel(d, lang):
    """The 6-card proximity carousel. Empty for draft/coord-less fiches."""
    if _REL_INDEX is None:
        _build_related_index()
    slug = d.get("slug")
    rels = _REL_MAP.get(slug) if _REL_MAP else None
    if not rels:
        return ""
    labels = _REL_LABELS.get(lang, _REL_LABELS["fr"])
    cards = "\n".join(_render_rel_card(s, lang, labels) for s in rels if s in _REL_INDEX)
    sis = _sister_rel_cards(d, lang)
    cards += sis
    if not cards:
        return ""
    css = _REL_CSS + (_SIS_CSS if sis else "")
    return (f'<section class="block related" id="related">\n  <style>\n{css}\n</style>\n'
            f'  <div class="wrap">\n    <p class="kicker">{labels["kicker"]}</p>\n'
            f'    <h2>{labels["h2"]}</h2>\n    <p class="lead">{labels["lead"]}</p>\n'
            f'    <div class="carousel">{cards}</div>\n  </div>\n</section>')



# --- cross-department proximity -------------------------------------------
# The sibling site covers the next departement, and near a shared border the
# genuinely closest place is often on the other side of it. Those cards come
# from data/sister-proximity.json and are ALWAYS badged as the sibling site:
# an unmarked external card would read as our own content, and the reader
# would not know they are about to leave.
#
# The radius is deliberately tight (site.config.json: sister_proximity_km).
# Measured on this catalogue, 25 km yields a handful of honest pairs and 60 km
# yields four figures — but 60 km on an alpine road is ninety minutes, and
# calling that "a proximite" would be a lie told by arithmetic.
_SIS_IDX = None


def _sister_places():
    global _SIS_IDX
    if _SIS_IDX is None:
        try:
            _SIS_IDX = json.loads((REPO / "data" / "sister-proximity.json")
                                  .read_text(encoding="utf-8")).get("places", [])
        except Exception:
            _SIS_IDX = []
    return _SIS_IDX


def _sister_rel_cards(d, lang, limit=2):
    sis = getattr(siteconfig, "SISTER", None)
    radius = float(getattr(siteconfig, "SISTER_PROXIMITY_KM", 0) or 0)
    lat, lon = d.get("latitude"), d.get("longitude")
    if not sis or not radius or lat is None or lon is None:
        return ""
    near = []
    for pl in _sister_places():
        dist = _haversine(lat, lon, pl["lat"], pl["lon"])
        if dist <= radius:
            near.append((dist, pl))
    if not near:
        return ""
    near.sort(key=lambda t: t[0])
    lbl = {"fr": "Sur", "en": "On", "de": "Auf", "it": "Su", "es": "En", "nl": "Op"}.get(lang, "Sur")
    out = []
    for dist, pl in near[:limit]:
        img = (f'<img src="{attr(pl["hero"])}" alt="" loading="lazy">' if pl.get("hero")
               else '<span class="ph"></span>')
        # Send the reader to the sibling's page in the language they are
        # already reading — its locale trees mirror ours (/en/<slug>).
        url = pl["url"] if lang == "fr" else f'{sis["url"].rstrip("/")}/{lang}/{pl["slug"]}'
        name = (pl.get("names") or {}).get(lang) or pl["name"]
        out.append(
            f'<a class="rel-card sister-card" href="{attr(url)}" rel="noopener">'
            f'<span class="sis-badge">{esc(lbl)} {esc(sis["name"])}</span>{img}'
            f'<span class="rc-t">{esc(name)}</span>'
            f'<span class="rc-c">{esc(pl.get("commune") or "")} · {dist:.0f} km</span></a>')
    return "\n" + "\n".join(out)

# ---------------------------------------------------------------------------
# Baignade cluster (HANDOFF 01): "L'essentiel" facts block + "Plages voisines"
# adjacency mesh. The beach set + its lake groups are the curated members of
# the three baignade intent hubs — the registry is the single source of truth.
# ---------------------------------------------------------------------------
_BAIGNADE_HUBS = {
    "baignade-lac-annecy": "annecy",
    "baignade-leman": "leman",
    "ou-se-baigner-haute-savoie": "montagne",
}
_MASTER_HUB = "ou-se-baigner-haute-savoie"
_LAKE_HUB = {"annecy": "baignade-lac-annecy", "leman": "baignade-leman",
             "montagne": "ou-se-baigner-haute-savoie"}
_BAIGNADE_IDX = None  # {slug: {"group","hub","lat","lng"}}

_ESS = {"fr": "L'essentiel", "en": "The essentials", "de": "Das Wichtigste",
        "it": "L'essenziale", "es": "Lo esencial", "nl": "In het kort"}
_VOIS = {"fr": "Plages voisines", "en": "Nearby beaches", "de": "Strände in der Nähe",
         "it": "Spiagge vicine", "es": "Playas cercanas", "nl": "Stranden in de buurt"}
_GUIDE = {"fr": "Voir le guide baignade", "en": "Swimming guide", "de": "Bade-Guide",
          "it": "Guida balneazione", "es": "Guía de baño", "nl": "Zwemgids"}
_ALLSPOTS = {"fr": f"Où se baigner en {siteconfig.dept_name('fr')}", "en": f"Where to swim in {siteconfig.dept_name('en')}",
             "de": f"Baden in {siteconfig.dept_name('de')}", "it": f"Dove fare il bagno in {siteconfig.dept_name('it')}",
             "es": f"Dónde bañarse en {siteconfig.dept_name('es')}", "nl": f"Zwemmen in {siteconfig.dept_name('nl')}"}
_CH_SURV = {"fr": "Surveillance", "en": "Lifeguard", "de": "Aufsicht", "it": "Sorveglianza",
            "es": "Vigilancia", "nl": "Toezicht"}
_CH_VOIRFICHE = {"fr": "voir fiche", "en": "see details", "de": "siehe Steckbrief",
                 "it": "vedi scheda", "es": "ver ficha", "nl": "zie fiche"}
_REG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "data", "intent-hubs.json")


def _baignade_index():
    global _BAIGNADE_IDX
    if _BAIGNADE_IDX is not None:
        return _BAIGNADE_IDX
    idx = {}
    try:
        reg = json.loads(open(_REG_PATH, encoding="utf-8").read())
    except (OSError, ValueError):
        reg = []
    json_dir = os.path.join(os.path.dirname(_REG_PATH), "..", "Json")
    for h in reg:
        grp = _BAIGNADE_HUBS.get(h.get("slug"))
        if not grp:
            continue
        for m in h.get("members", []):
            fp = os.path.join(json_dir, f"{m['slug']}.json")
            try:
                md = json.loads(open(fp, encoding="utf-8").read())
            except (OSError, ValueError):
                continue
            idx[m["slug"]] = {"group": grp, "hub": h["slug"],
                              "lat": md.get("latitude"), "lng": md.get("longitude")}
    _BAIGNADE_IDX = idx
    return idx


def _haversine_km(a, b, c, e):
    import math
    if None in (a, b, c, e):
        return float("inf")
    R = 6371.0
    p1, p2 = math.radians(a), math.radians(c)
    dp = math.radians(c - a); dl = math.radians(e - b)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def essentiel_block(d, lang):
    """Beach-only answer-first highlight strip — swimming-critical curated facts.
    Every value comes verbatim from i18n.<lang>.facts / acces_pmr; null ⇒ voir fiche.
    HANDOFF-35: theme-aware shared classes (.essentiel/.chip in style.css, CSS
    variables → readable on light AND dark; the old inline background:#fff
    ghosted the chips on the dark theme), labels via the two-lane lookup so all
    12 languages get native wording (PT showed FR 'L'essentiel')."""
    if d.get("slug") not in _baignade_index():
        return ""
    facts = (d.get("i18n", {}).get(lang, {}) or {}).get("facts") \
        or (d.get("i18n", {}).get("fr", {}) or {}).get("facts") or {}
    chips = []
    tarif = facts.get("tarif") or facts.get("access")
    voir = _ui_label(_CH_VOIRFICHE, "voir_fiche", lang) or "voir fiche"
    chips.append('<span class="chip">'
                 f'💶 {html_lib.escape(str(tarif) if tarif else voir, quote=True)}</span>')
    surv = facts.get("surveillance")
    if surv:
        chips.append(f'<span class="chip">🛟 {html_lib.escape(str(surv), quote=True)}</span>')
    if str(facts.get("pavillon_bleu_2026", "")).strip().upper() == "OUI":
        chips.append('<span class="chip chip-pb">🏅 Pavillon Bleu 2026</span>')
    ap = d.get("acces_pmr")
    if isinstance(ap, dict) and ap.get("status"):
        st = _pmr_status_label(ap["status"], lang)
        chips.append(f'<span class="chip">♿ {html_lib.escape(str(st), quote=True)}</span>')
    title = html_lib.escape(_ui_label(_ESS, "l_essentiel", lang), quote=True)
    return ('<section class="essentiel">'
            f'<strong class="ess-title">{title}</strong>'
            + "".join(chips) + '</section>')


def plages_voisines_block(d, lang):
    """Same-lake nearest-neighbour mesh + a link up to the lake's baignade hub
    and the master 'où se baigner' hub. Pure link equity, generated not placed."""
    idx = _baignade_index()
    slug = d.get("slug")
    if slug not in idx:
        return ""
    me = idx[slug]
    lang_prefix = f"/{lang}" if lang != "fr" else ""
    # nearest same-group siblings
    sibs = [(s, info) for s, info in idx.items()
            if s != slug and info["group"] == me["group"]]
    sibs.sort(key=lambda si: _haversine_km(me["lat"], me["lng"], si[1]["lat"], si[1]["lng"]))
    sibs = sibs[:4]
    links = []
    # up to the lake hub (or the master hub for the mountain group).
    # Strict-prose (facts-lang rich) pages skip the intent-hub links: those
    # pages exist only for the six prose languages — a /pt/baignade-lac-annecy
    # link would 404 (link-integrity gate).
    hub_slug = me["hub"]
    if not _STRICT_PROSE:
        links.append(f'<a class="fiche" '
                     f'href="{BASE_URL}{lang_prefix}/{hub_slug}">{html_lib.escape(_GUIDE.get(lang) or _GUIDE["fr"], quote=True)} →</a>')
    for s, _info in sibs:
        nm = _related_name(s, lang)
        links.append(f'<a class="fiche" '
                     f'href="{BASE_URL}{lang_prefix}/{s}">{html_lib.escape(nm, quote=True)}</a>')
    # always link the master hub too (cross-lake discovery)
    if hub_slug != _MASTER_HUB and not _STRICT_PROSE:
        links.append(f'<a class="fiche" '
                     f'href="{BASE_URL}{lang_prefix}/{_MASTER_HUB}">{html_lib.escape(_ALLSPOTS.get(lang) or _ALLSPOTS["fr"], quote=True)} →</a>')
    title = html_lib.escape(_ui_label(_VOIS, "plages_voisines", lang), quote=True)
    # HANDOFF-35: same background:#fff disease as the essentiel block, on the
    # same beach pages — themed via the shared .plages-voisines class.
    return ('<section class="plages-voisines">'
            f'<h2>{title}</h2>'
            f'<div>{"".join(links)}</div></section>')


def _lastmod_iso(d):
    """ISO YYYY-MM-DD for this fiche from the manifest, or '' if absent."""
    return _LASTMOD.get(d.get("slug"), "")


def _lastmod_display(d):
    """Visible stamp date `jj/mm/aa`, derived from the manifest; falls back to
    the manual date_modified_human when the manifest has no entry."""
    iso = _lastmod_iso(d)
    if iso:
        y, m, day = iso.split("-")
        return f"{day}/{m}/{y[2:]}"
    return d.get("date_modified_human", "")


def _carries_protected_partner(d, lang, include_partners):
    """True if this render will emit a protected partner domain, so the
    byte-frozen path applies (keeps gate_protected_placements green with no
    approval trailer). Primary signal: the page's output path is in the gate
    manifest (ground truth — covers cross-fiche promo injections). Belt-and-
    suspenders data heuristic for anything the manifest hasn't captured yet."""
    slug = d.get("slug") or ""
    relpath = f"{slug}.html" if lang == "fr" else f"{lang}/{slug}.html"
    if relpath in _PROTECTED_PAGES:
        return True
    ev = EVENT_MODALS.get(slug)
    if ev and any(dom in ev.get("url", "") for dom in _PROTECTED_PARTNER_DOMAINS):
        return True
    if include_partners:
        blob = (json.dumps(d.get("featured_businesses") or [], ensure_ascii=False)
                + json.dumps(d.get("partners") or [], ensure_ascii=False))
        if any(dom in blob for dom in _PROTECTED_PARTNER_DOMAINS):
            return True
    return False


def build_page(d, lang="fr", include_partners=True, fr_prose_fallback=True):
    """Render the full HTML for fiche `d` in `lang`. Returns html string.
    Fallback-field info (which keys fell back to FR) is exposed via
    module attribute LAST_FALLBACK_FIELDS after each call.

    include_partners=False keeps protected partner placements OUT of the
    page — used by the facts-lang rich render (HANDOFF-22/26): partner cards
    are commercial content under a byte-faithful snapshot contract that only
    covers the six live languages; a new language ships without them until
    that contract is explicitly extended."""
    global LAST_FALLBACK_FIELDS, _STRICT_PROSE, _FROZEN
    _set_lang(d, lang)
    _STRICT_PROSE = not fr_prose_fallback
    _FROZEN = _carries_protected_partner(d, lang, include_partners)
    name = L("name", "")

    # HANDOFF-35: acces_pmr.detail is FR-authored CONTENT (not a frozen name).
    # fr renders it verbatim; every other language shows its own translation
    # (i18n.<lang>.acces_pmr_detail, populated by the batch lane) or NOTHING —
    # the localized short status still renders, the FR sentence never leaks.
    ap_eff = d.get("acces_pmr")
    if isinstance(ap_eff, dict) and lang != "fr":
        ap_eff = dict(ap_eff)
        det = ((d.get("i18n") or {}).get(lang) or {}).get("acces_pmr_detail")
        ap_eff["detail"] = det if isinstance(det, str) and det.strip() else None

    out = []
    out.append(build_head(d))
    out.append(build_header(d))
    out.append(hero_block(d))
    out.append(facts_block(L("facts", {}) or {}, first_source_url(d), ap_eff))
    out.append(essentiel_block(d, lang))
    out.append(tarifs_block(d))
    body_dict = L("body", {}) if isinstance(L("body", {}), dict) else {}
    if not body_dict:
        body_dict = {"what_is": L_body("what_is", "")}
    out.append(body_block(name, body_dict))
    out.append(activities_block(L_body("activities", []) or []))
    out.append(practical_block(L_body("practical_info", []) or [], name, d["commune"],
                               drop_tarif=bool(d.get("price_tiers"))))
    out.append(how_to_block(L_body("how_to_get_there", {}) or {}, name, d["commune"],
                            d.get("latitude"), d.get("longitude"), d["slug"],
                            d.get("google_place_id")))
    out.append(parking_block(d["slug"], (L("facts", {}) or {}).get("parking")))
    out.append(when_to_visit_block(L_body("when_to_visit", "") or "",
                                   L_body("events", "") or ""))
    out.append(season_card(d))
    if include_partners:
        out.append(partners_block(d))
    out.append(gallery_block(name, d.get("gallery_photos")))
    out.append(faq_block(L("faq", []) or []))
    out.append(selections_chips(d, lang))
    _related = related_lieux_block(d.get("related_lieux", []), lang)
    if _related:
        out.append(_related)
    out.append(plages_voisines_block(d, lang))
    out.append(sources_block(d.get("sources", [])))
    out.append(data_credits_block(d.get("data_sources", [])))
    _carousel = related_carousel(d, lang)
    if _carousel:
        out.append(_carousel)
    out.append(build_footer_block(
        d.get("date_published_human", ""),
        d.get("date_modified_human", "") if _FROZEN else _lastmod_display(d)
    ))
    out.append(action_bar(d, frozen=_FROZEN))
    out.append(site_footer())
    out.append(event_modal_block(d))
    out.append(JS)
    # Sitewide duck easter egg — skip the two protected partner fiches so their
    # bytes don't change (duck.js also self-disables on those paths).
    if d.get("slug") not in ("chez-nous-a-la-plage", "chalet-du-tornet"):
        out.append(assets.script_tag("duck.js"))
    out.append("</body></html>")
    LAST_FALLBACK_FIELDS = set(_FALLBACK_FIELDS)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json_path")
    ap.add_argument("--lang", default="fr", choices=SUPPORTED_LANGS)
    ap.add_argument("--out-dir", default=None,
                    help="Output dir. Defaults to REPO for fr, REPO/<lang> otherwise.")
    args = ap.parse_args()

    d = json.loads(Path(args.json_path).read_text(encoding="utf-8"))
    html = build_page(d, lang=args.lang)
    out_dir = Path(args.out_dir) if args.out_dir else (
        REPO if args.lang == "fr" else REPO / args.lang
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{d['slug']}.html"
    out_path.write_text(html, encoding="utf-8")
    try:
        rel = out_path.relative_to(REPO)
    except ValueError:
        rel = out_path
    fb = f" [fallback:{','.join(sorted(LAST_FALLBACK_FIELDS))}]" if LAST_FALLBACK_FIELDS else ""
    print(f"  {rel}  ({len(html):,} chars){fb}")


if __name__ == "__main__":
    main()
