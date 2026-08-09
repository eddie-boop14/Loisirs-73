#!/usr/bin/env python3
"""
Localize a FR lieu page (output of build_lieu_page.py) into en/de/it/es,
reproducing the deployed convention: fully-translated chrome + French body.

Header and footer are page-independent chrome and are lifted verbatim from a
known-good locale page (TEMPLATE_SLUG), with the lang-menu slug swapped.
Everything else is deterministic string/URL rewriting.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LANGS = ["en", "de", "it", "es", "nl"]
LI = {"en": 0, "de": 1, "it": 2, "es": 3, "nl": 4}
TEMPLATE_SLUG = "plage-de-doussard"  # has known-good locale pages to lift header/footer from

OG_LOCALE = {"en": "en_US", "de": "de_DE", "it": "it_IT", "es": "es_ES", "nl": "nl_NL"}
INLANG = {"en": "en-US", "de": "de-DE", "it": "it-IT", "es": "es-ES", "nl": "nl-NL"}
HOME = {"en": "Home", "de": "Startseite", "it": "Home", "es": "Inicio", "nl": "Startpagina"}
SKIP = {"en": "Skip to content", "de": "Zum Inhalt springen", "it": "Vai al contenuto", "es": "Saltar al contenido", "nl": "Naar inhoud springen"}
GENERIC = {"en": "Generic", "de": "Generisch", "it": "Generico", "es": "Genérico", "nl": "Algemeen"}
PUBLISHED = {"en": "Published", "de": "Veröffentlicht", "it": "Pubblicato il", "es": "Publicado el", "nl": "Gepubliceerd"}
UPDATED = {"en": "Updated", "de": "Aktualisiert", "it": "Aggiornato il", "es": "Actualizado el", "nl": "Bijgewerkt"}
FREEWORD = {"en": "Free", "de": "Kostenlos", "it": "Gratis", "es": "Gratis", "nl": "Gratis"}
PAIDWORD = {"en": "Paid", "de": "Kostenpflichtig", "it": "A pagamento", "es": "De pago", "nl": "Betaald"}

KICKER = {
    "Activités": ["Activities", "Aktivitäten", "Attività", "Actividades", "Activiteiten"],
    "Pratique": ["Practical", "Praktisches", "Pratico", "Práctica", "Praktisch"],
    "Accès": ["Access", "Anreise", "Accesso", "Acceso", "Toegang"],
    "Quand venir": ["When to visit", "Wann besuchen", "Quando visitare", "Cuándo visitar", "Wanneer bezoeken"],
    "À proximité": ["Nearby", "In der Nähe", "Nelle vicinanze", "Cerca", "In de buurt"],
    "Photos": ["Photos", "Fotos", "Foto", "Fotos", "Foto's"],
    "Sources": ["Sources", "Quellen", "Fonti", "Fuentes", "Bronnen"],
    "En un coup d&#39;œil": ["At a glance", "Auf einen Blick", "In sintesi", "De un vistazo", "In een oogopslag"],
}
# Partner-card badge translations (À proximité tier:recommended).
BADGE_PROXIMITY = {"en": "Nearby", "de": "In der Nähe", "it": "Nelle vicinanze", "es": "Cerca", "nl": "In de buurt"}
H2 = {
    "Ce qu&#39;on peut y faire": ["What you can do here", "Was man hier machen kann", "Cosa si può fare", "Qué se puede hacer", "Wat je hier kunt doen"],
    "Infos pratiques": ["Practical information", "Praktische Informationen", "Informazioni pratiche", "Información práctica", "Praktische informatie"],
    "Comment y aller": ["How to get there", "So kommen Sie hin", "Come arrivare", "Cómo llegar", "Hoe te komen"],
    "Quand visiter": ["When to visit", "Wann besuchen", "Quando visitare", "Cuándo visitar", "Wanneer bezoeken"],
    "Où manger, boire, dormir": ["Where to eat, drink, stay", "Essen, Trinken, Übernachten", "Dove mangiare, bere, dormire", "Dónde comer, beber, alojarse", "Waar eten, drinken, overnachten"],
    "Galerie": ["Gallery", "Galerie", "Galleria", "Galería", "Galerij"],
    "Questions fréquentes": ["Frequently asked questions", "Häufige Fragen", "Domande frequenti", "Preguntas frecuentes", "Veelgestelde vragen"],
    "Sources &amp; vérifications": ["Sources &amp; verification", "Quellen &amp; Prüfung", "Fonti &amp; verifiche", "Fuentes &amp; verificaciones", "Bronnen &amp; verificatie"],
}
WHATIS = ["What is ", "Was ist ", "Cos&#39;è ", "Qué es ", "Wat is "]
LABELS = {
    "Type": ["Type", "Typ", "Tipo", "Tipo", "Type"],
    "Accès": ["Access", "Anreise", "Accesso", "Acceso", "Toegang"],
    "Tarif": ["Price", "Preis", "Prezzo", "Precio", "Prijs"],
    "Tarifs": ["Rates", "Preise", "Prezzi", "Precios", "Tarieven"],
    "Durée": ["Duration", "Dauer", "Durata", "Duración", "Duur"],
    "Meilleure saison": ["Best season", "Beste Saison", "Stagione migliore", "Mejor temporada", "Beste seizoen"],
    "Parking": ["Parking", "Parkplatz", "Parcheggio", "Aparcamiento", "Parkeren"],
    "Animaux": ["Animals", "Tiere", "Animali", "Animales", "Dieren"],
    "Poussette / PMR": ["Stroller / Reduced mobility", "Kinderwagen / Behinderte", "Passeggino / Disabilità", "Cochecito / PMR", "Kinderwagen / Mindervaliden"],
    "Commune": ["Town", "Ort", "Comune", "Comuna", "Gemeente"],
    "Adresse": ["Address", "Adresse", "Indirizzo", "Dirección", "Adres"],
    "Coordonnées": ["Coordinates", "Koordinaten", "Coordinate", "Coordenadas", "Coördinaten"],
    "Saison": ["Season", "Saison", "Stagione", "Temporada", "Seizoen"],
    "Horaires": ["Hours", "Öffnungszeiten", "Orari", "Horarios", "Openingstijden"],
    "Réservation": ["Booking", "Reservierung", "Prenotazione", "Reserva", "Reservering"],
    "Accessibilité": ["Accessibility", "Barrierefreiheit", "Accessibilità", "Accesibilidad", "Toegankelijkheid"],
    "Contact": ["Contact", "Kontakt", "Contatti", "Contacto", "Contact"],
    # stay FR: Lac, Lac / Plan d'eau, Surveillance, Surveillance MNS, Pavillon Bleu 2026
}

# NL chrome (synthesized — no NL fiche template exists yet). Uses TEMPLATE_SLUG
# as the canonical link target; localize() will swap in the actual slug at use.
NL_HEADER = '''<header class="site"><div class="wrap">
  <a class="brand" href="https://loisirs74.fr/nl/" aria-label="Loisirs 74"><span class="mark" aria-hidden="true"><img src="/logo.png" alt="" width="30" height="30" style="border-radius:7px;display:block;"></span><span>Loisirs 74</span></a>
  <nav><details class="lang-picker"><summary aria-label="Kies een taal"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15 15 0 010 20M12 2a15 15 0 000 20"/></svg>NL</summary><div class="lang-menu"><a href="https://loisirs74.fr/''' + TEMPLATE_SLUG + '''" hreflang="fr">Français</a>
<a href="https://loisirs74.fr/en/''' + TEMPLATE_SLUG + '''" hreflang="en">English</a>
<a href="https://loisirs74.fr/de/''' + TEMPLATE_SLUG + '''" hreflang="de">Deutsch</a>
<a href="https://loisirs74.fr/it/''' + TEMPLATE_SLUG + '''" hreflang="it">Italiano</a>
<a href="https://loisirs74.fr/es/''' + TEMPLATE_SLUG + '''" hreflang="es">Español</a>
<a href="https://loisirs74.fr/nl/''' + TEMPLATE_SLUG + '''" aria-current="true" hreflang="nl">Nederlands</a></div></details></nav>
</div></header>'''

NL_FOOTER = '<footer class="site"><div class="wrap"><div class="foot-grid"><div class="foot-col"><a class="brand" href="https://loisirs74.fr/nl/" style="margin-bottom:.85rem"><span class="mark" aria-hidden="true"><img src="/logo.png" alt="" width="30" height="30" style="border-radius:7px;display:block;"></span><span>Loisirs 74</span></a><p>Onafhankelijke gids voor vrijetijdsbestedingen in Haute-Savoie. Gratis. Geverifieerd.</p></div><div class="foot-col"><h4>Verkennen</h4><ul><li><a href="https://loisirs74.fr/nl/">Startpagina</a></li></ul></div><div class="foot-col"><h4>Bijdragen</h4><ul><li><a href="mailto:photos@loisirs74.fr">Foto&#39;s sturen</a></li><li><a href="https://loisirs74.fr/nl/signaler">Info melden</a></li><li><a href="https://loisirs74.fr/nl/devenir-partenaire">Partner worden</a></li></ul></div><div class="foot-col"><h4>Juridisch</h4><ul><li><a href="https://loisirs74.fr/nl/mentions-legales">Wettelijke vermeldingen</a></li><li><a href="https://loisirs74.fr/nl/confidentialite">Privacy</a></li><li><a href="https://loisirs74.fr/nl/cgv">Algemene voorwaarden</a></li></ul></div></div><div class="foot-bottom"><span class="credit">© 2026 Bleu canard édition · Edmaster &amp; Claudius · Alle rechten voorbehouden</span><span>Geen advertenties. Geen tracking. Geen Google reviews.</span></div></div></footer>'

_hf_cache = {}
def header_footer(lang):
    if lang in _hf_cache:
        return _hf_cache[lang]
    if lang == "nl":
        # Synthesized — no NL fiche template file yet. Uses TEMPLATE_SLUG everywhere;
        # localize() swaps in the actual slug.
        _hf_cache[lang] = (NL_HEADER, NL_FOOTER)
        return _hf_cache[lang]
    src = (ROOT / lang / f"{TEMPLATE_SLUG}.html").read_text(encoding="utf-8")
    header = re.search(r"<header class=\"site\">.*?</header>", src, re.DOTALL).group(0)
    footer = re.search(r"<footer class=\"site\">.*?</footer>", src, re.DOTALL).group(0)
    _hf_cache[lang] = (header, footer)
    return header, footer


def localize(fr_html, lang, slug):
    i = LI[lang]
    t = fr_html
    # 1. global internal-URL prefix
    t = t.replace("https://loisirs74.fr/", f"https://loisirs74.fr/{lang}/")
    # mailto unaffected (no https:// prefix)
    # 2. fix hreflang block (was mangled by global prefix)
    hreflang_block = "\n".join([
        f'<link rel="alternate" hreflang="fr" href="https://loisirs74.fr/{slug}">',
        f'<link rel="alternate" hreflang="en" href="https://loisirs74.fr/en/{slug}">',
        f'<link rel="alternate" hreflang="de" href="https://loisirs74.fr/de/{slug}">',
        f'<link rel="alternate" hreflang="it" href="https://loisirs74.fr/it/{slug}">',
        f'<link rel="alternate" hreflang="es" href="https://loisirs74.fr/es/{slug}">',
        f'<link rel="alternate" hreflang="nl" href="https://loisirs74.fr/nl/{slug}">',
        f'<link rel="alternate" hreflang="x-default" href="https://loisirs74.fr/{slug}">',
    ])
    t = re.sub(
        r'<link rel="alternate" hreflang="fr" href="[^"]*">\s*<link rel="alternate" hreflang="x-default" href="[^"]*">',
        hreflang_block, t, count=1)
    # 3. lang attr, og:locale, jsonld inLanguage
    t = t.replace('<html lang="fr"', f'<html lang="{lang}"', 1)
    t = t.replace('<meta property="og:locale" content="fr_FR">', f'<meta property="og:locale" content="{OG_LOCALE[lang]}">', 1)
    t = t.replace('"inLanguage": "fr-FR"', f'"inLanguage": "{INLANG[lang]}"')
    # 4. header + footer block-swap (page-independent chrome, slug-swapped)
    header, footer = header_footer(lang)
    header = header.replace(TEMPLATE_SLUG, slug)
    t = re.sub(r"<header class=\"site\">.*?</header>", lambda m: header, t, count=1, flags=re.DOTALL)
    t = re.sub(r"<footer class=\"site\">.*?</footer>", lambda m: footer, t, count=1, flags=re.DOTALL)
    # 5. skip link (outside header)
    t = t.replace(">Aller au contenu<", f">{SKIP[lang]}<", 1)
    # 6. breadcrumb home text + jsonld home name
    t = t.replace(">Accueil</a>", f">{HOME[lang]}</a>", 1)
    t = t.replace('"name": "Accueil"', f'"name": "{HOME[lang]}"')
    # 7. section chrome
    for fr, locs in KICKER.items():
        t = t.replace(f'<div class="kicker reveal">{fr}</div>', f'<div class="kicker reveal">{locs[i]}</div>')
    for fr, locs in H2.items():
        t = t.replace(f'<h2 class="reveal">{fr}<', f'<h2 class="reveal">{locs[i]}<')
    t = t.replace('<h2 class="reveal">Qu&#39;est-ce que ', f'<h2 class="reveal">{WHATIS[i]}')
    for fr, locs in LABELS.items():
        t = t.replace(f'<div class="k">{fr}</div>', f'<div class="k">{locs[i]}</div>')
    # 8. eyebrow free/paid word
    t = t.replace(f'· Gratuit</span>', f'· {FREEWORD[lang]}</span>')
    t = t.replace(f'· Payant</span>', f'· {PAIDWORD[lang]}</span>')
    # 9. dates + CSS label
    t = t.replace("Publié le ", f"{PUBLISHED[lang]} ")
    t = t.replace("Mis à jour le ", f"{UPDATED[lang]} ")
    t = t.replace('content: "Générique"', f'content: "{GENERIC[lang]}"')
    # 10. partner-card badge "À proximité" → localized
    t = t.replace('<span class="badge"> À proximité</span>', f'<span class="badge"> {BADGE_PROXIMITY[lang]}</span>')
    return t


def main():
    slugs = sys.argv[1:]
    for slug in slugs:
        fr = (ROOT / f"{slug}.html").read_text(encoding="utf-8")
        for lang in LANGS:
            out = localize(fr, lang, slug)
            (ROOT / lang).mkdir(exist_ok=True)
            (ROOT / lang / f"{slug}.html").write_text(out, encoding="utf-8")
        print(f"  ✓ {slug}: en/de/it/es/nl")


if __name__ == "__main__":
    main()
