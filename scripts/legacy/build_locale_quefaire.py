#!/usr/bin/env python3
"""Build 4 locale variants of /que-faire/.

Strategy:
- Copy FR /que-faire/index.html → {loc}/que-faire/index.html
- Apply chrome translations (title, meta desc, h1, hero lede, 14 h2s + cat-subs,
  sommaire nav, action labels, footer copy)
- Rewrite venue links to /{loc}/{slug} if locale file exists, else keep root /{slug}
- Update <html lang>, canonical, hreflang self-ref, og:locale
- Add language picker (5 langs) to header — also retrofitted to FR

Card descriptions stay in FR (matches site's existing sparse-i18n convention).
Venue names + commune names stay in FR (proper nouns).
"""
import re, os
from pathlib import Path

REPO = Path("/home/user/Loisir-74")
FR_SRC = REPO / "que-faire/index.html"

LANG_NAMES = {"fr":"Français", "en":"English", "de":"Deutsch", "it":"Italiano", "es":"Español"}
OG_LOCALES = {"fr":"fr_FR", "en":"en_US", "de":"de_DE", "it":"it_IT", "es":"es_ES"}

# Replacement table per locale. Each entry: (FR_string, locale_string)
# Listed in order — applied as exact string replacements.
T = {
    "en": {
        # <title>
        "Que faire en Haute-Savoie quand il pleut — Activités indoor & toute saison · Loisirs 74":
            "What to do in Haute-Savoie when it rains — Indoor & all-season activities · Loisirs 74",
        # meta description
        "Toutes les activités indoor et par tout temps de Haute-Savoie, vérifiées une par une : escape games, escalade, bowling, karting, patinoires, centres aquatiques, spa, musées. Chaque page une source officielle.":
            "All indoor and all-weather activities in Haute-Savoie, verified one by one: escape rooms, climbing, bowling, karting, ice rinks, aquatic centres, spa, museums. Each page: one official source.",
        # hero
        "Le guide de la Haute-Savoie · par tout temps": "The Haute-Savoie guide · in any weather",
        "<span><span>Que faire</span></span>":         "<span><span>What to do</span></span>",
        "<span><span>quand il</span></span>":           "<span><span>when it</span></span>",
        "<span><span><em>pleut</em></span></span>":     "<span><span><em>rains</em></span></span>",
        'Toutes les activités <b>indoor et par tout temps</b> de Haute-Savoie, vérifiées une par une&nbsp;: escape games, escalade, bowling, karting, patinoires, centres aquatiques, spa, musées. Chaque fiche&nbsp;: une source officielle, une adresse, une carte.':
            'All <b>indoor and all-weather</b> activities in Haute-Savoie, verified one by one&nbsp;: escape rooms, climbing, bouldering, bowling, karting, ice rinks, aquatic centres, spa, museums. Each entry&nbsp;: one official source, an address, a map.',
        # Sommaire
        '<span class="cat-nav-label">Sommaire</span>': '<span class="cat-nav-label">Contents</span>',
        '<a href="#escape">Escape games</a>':                       '<a href="#escape">Escape rooms</a>',
        '<a href="#escalade">Escalade &amp; bloc</a>':              '<a href="#escalade">Climbing &amp; bouldering</a>',
        '<a href="#laser">Laser game</a>':                          '<a href="#laser">Laser tag</a>',
        '<a href="#trampoline">Trampoline parks</a>':               '<a href="#trampoline">Trampoline parks</a>',
        '<a href="#bowling">Bowling</a>':                           '<a href="#bowling">Bowling</a>',
        '<a href="#karting">Karting</a>':                           '<a href="#karting">Karting</a>',
        '<a href="#patinoire">Patinoires</a>':                      '<a href="#patinoire">Ice rinks</a>',
        '<a href="#aquatique">Centres aquatiques</a>':              '<a href="#aquatique">Aquatic centres</a>',
        '<a href="#spa">Spa &amp; bien-être</a>':                   '<a href="#spa">Spa &amp; wellness</a>',
        '<a href="#soft-play">Aires de jeux couvertes</a>':         '<a href="#soft-play">Indoor play areas</a>',
        '<a href="#science">Sciences &amp; découverte</a>':         '<a href="#science">Science &amp; discovery</a>',
        '<a href="#musee">Musées</a>':                              '<a href="#musee">Museums</a>',
        '<a href="#casino">Casinos</a>':                            '<a href="#casino">Casinos</a>',
        '<a href="#autre">Autres loisirs indoor</a>':               '<a href="#autre">Other indoor leisure</a>',
        # Section h2 + cat-subs
        '<h2>Escape games <span class="count">':         '<h2>Escape rooms <span class="count">',
        '<h2>Escalade &amp; bloc <span class="count">':  '<h2>Climbing &amp; bouldering <span class="count">',
        '<h2>Laser game <span class="count">':           '<h2>Laser tag <span class="count">',
        '<h2>Trampoline parks <span class="count">':    '<h2>Trampoline parks <span class="count">',
        '<h2>Bowling <span class="count">':              '<h2>Bowling <span class="count">',
        '<h2>Karting <span class="count">':              '<h2>Karting <span class="count">',
        '<h2>Patinoires <span class="count">':           '<h2>Ice rinks <span class="count">',
        '<h2>Centres aquatiques <span class="count">':   '<h2>Aquatic centres <span class="count">',
        '<h2>Spa &amp; bien-être <span class="count">':  '<h2>Spa &amp; wellness <span class="count">',
        '<h2>Aires de jeux couvertes <span class="count">': '<h2>Indoor play areas <span class="count">',
        '<h2>Sciences &amp; découverte <span class="count">': '<h2>Science &amp; discovery <span class="count">',
        '<h2>Musées <span class="count">':               '<h2>Museums <span class="count">',
        '<h2>Casinos <span class="count">':              '<h2>Casinos <span class="count">',
        '<h2>Autres loisirs indoor <span class="count">':'<h2>Other indoor leisure <span class="count">',
        '<span class="cat-sub">jeux d\'évasion</span>':        '<span class="cat-sub">puzzle rooms</span>',
        '<span class="cat-sub">salles indoor</span>':          '<span class="cat-sub">indoor gyms</span>',
        '<span class="cat-sub">arènes couvertes</span>':       '<span class="cat-sub">indoor arenas</span>',
        '<span class="cat-sub">indoor</span>':                 '<span class="cat-sub">indoor</span>',
        '<span class="cat-sub">pistes couvertes</span>':       '<span class="cat-sub">indoor lanes</span>',
        '<span class="cat-sub">indoor &amp; circuits</span>':  '<span class="cat-sub">indoor &amp; circuits</span>',
        '<span class="cat-sub">glace couverte</span>':         '<span class="cat-sub">covered ice</span>',
        '<span class="cat-sub">piscines couvertes</span>':     '<span class="cat-sub">indoor pools</span>',
        '<span class="cat-sub">thermes, balnéo</span>':        '<span class="cat-sub">thermal, balneo</span>',
        '<span class="cat-sub">enfants</span>':                '<span class="cat-sub">kids</span>',
        '<span class="cat-sub">interactif</span>':             '<span class="cat-sub">interactive</span>',
        "<span class=\"cat-sub\">toute l'année</span>":       '<span class="cat-sub">year-round</span>',
        '<span class="cat-sub">jeux</span>':                   '<span class="cat-sub">gaming</span>',
        '<span class="cat-sub">divers</span>':                 '<span class="cat-sub">various</span>',
        # Counts ( lieux/lieu)
        ' lieux</span>': ' places</span>',
        ' lieu</span>':  ' place</span>',
        # Tag chips
        '>Payant<':  '>Paid<',
        '>Gratuit<': '>Free<',
        '>Nouveau<': '>New<',
        # Card actions
        'Itinéraire ↗':    'Directions ↗',
        'Site officiel ↗': 'Official site ↗',
        # Header
        '· que faire':       '· what to do',
        '← Tous les lieux':  '← All places',
        # Footer
        '<h4>Que faire en Haute-Savoie</h4>': '<h4>What to do in Haute-Savoie</h4>',
        '<h4>Activités</h4>':                  '<h4>Activities</h4>',
        '<h4>Le guide</h4>':                   '<h4>The guide</h4>',
        'Le pendant «&nbsp;activités&nbsp;» du guide Loisirs 74. Quand le lac et les sentiers attendent le beau temps, voici où aller. Chaque fiche&nbsp;: une source officielle, une adresse, une carte.':
            'The "activities" counterpart to the Loisirs 74 guide. When the lake and trails wait for sunshine, here\'s where to go. Each entry: one official source, an address, a map.',
        'Tous les lieux (où aller)': 'All places (where to go)',
        'Mentions légales':          'Legal notice',
        'Signaler une info':         'Report info',
        '© 2026 bleu canard éditions · Edmaster &amp; Claudius':
            '© 2026 bleu canard editions · Edmaster &amp; Claudius',
        '79 activités vérifiées · 14 catégories':
            '79 verified activities · 14 categories',
    },
    "de": {
        "Que faire en Haute-Savoie quand il pleut — Activités indoor & toute saison · Loisirs 74":
            "Was tun in der Haute-Savoie bei Regen — Indoor- & Ganzjahresaktivitäten · Loisirs 74",
        "Toutes les activités indoor et par tout temps de Haute-Savoie, vérifiées une par une : escape games, escalade, bowling, karting, patinoires, centres aquatiques, spa, musées. Chaque page une source officielle.":
            "Alle Indoor- und Allwetter-Aktivitäten in der Haute-Savoie, einzeln geprüft: Escape Rooms, Klettern, Bowling, Karting, Eisbahnen, Schwimmbäder, Spa, Museen. Jede Seite: eine offizielle Quelle.",
        "Le guide de la Haute-Savoie · par tout temps": "Der Haute-Savoie-Guide · bei jedem Wetter",
        "<span><span>Que faire</span></span>":         "<span><span>Was tun</span></span>",
        "<span><span>quand il</span></span>":           "<span><span>wenn es</span></span>",
        "<span><span><em>pleut</em></span></span>":     "<span><span><em>regnet</em></span></span>",
        'Toutes les activités <b>indoor et par tout temps</b> de Haute-Savoie, vérifiées une par une&nbsp;: escape games, escalade, bowling, karting, patinoires, centres aquatiques, spa, musées. Chaque fiche&nbsp;: une source officielle, une adresse, une carte.':
            'Alle <b>Indoor- und Allwetter-Aktivitäten</b> der Haute-Savoie, einzeln geprüft&nbsp;: Escape Rooms, Klettern, Bouldern, Bowling, Karting, Eisbahnen, Schwimmbäder, Spa, Museen. Jeder Eintrag&nbsp;: eine offizielle Quelle, eine Adresse, eine Karte.',
        '<span class="cat-nav-label">Sommaire</span>': '<span class="cat-nav-label">Inhalt</span>',
        '<a href="#escape">Escape games</a>':           '<a href="#escape">Escape Rooms</a>',
        '<a href="#escalade">Escalade &amp; bloc</a>':  '<a href="#escalade">Klettern &amp; Bouldern</a>',
        '<a href="#laser">Laser game</a>':              '<a href="#laser">Lasertag</a>',
        '<a href="#trampoline">Trampoline parks</a>':   '<a href="#trampoline">Trampolinparks</a>',
        '<a href="#bowling">Bowling</a>':               '<a href="#bowling">Bowling</a>',
        '<a href="#karting">Karting</a>':               '<a href="#karting">Karting</a>',
        '<a href="#patinoire">Patinoires</a>':          '<a href="#patinoire">Eisbahnen</a>',
        '<a href="#aquatique">Centres aquatiques</a>':  '<a href="#aquatique">Schwimmbäder</a>',
        '<a href="#spa">Spa &amp; bien-être</a>':       '<a href="#spa">Spa &amp; Wellness</a>',
        '<a href="#soft-play">Aires de jeux couvertes</a>': '<a href="#soft-play">Indoor-Spielplätze</a>',
        '<a href="#science">Sciences &amp; découverte</a>': '<a href="#science">Wissenschaft &amp; Entdeckung</a>',
        '<a href="#musee">Musées</a>':                  '<a href="#musee">Museen</a>',
        '<a href="#casino">Casinos</a>':                '<a href="#casino">Casinos</a>',
        '<a href="#autre">Autres loisirs indoor</a>':   '<a href="#autre">Sonstige Indoor-Freizeit</a>',
        '<h2>Escape games <span class="count">':         '<h2>Escape Rooms <span class="count">',
        '<h2>Escalade &amp; bloc <span class="count">':  '<h2>Klettern &amp; Bouldern <span class="count">',
        '<h2>Laser game <span class="count">':           '<h2>Lasertag <span class="count">',
        '<h2>Trampoline parks <span class="count">':    '<h2>Trampolinparks <span class="count">',
        '<h2>Bowling <span class="count">':              '<h2>Bowling <span class="count">',
        '<h2>Karting <span class="count">':              '<h2>Karting <span class="count">',
        '<h2>Patinoires <span class="count">':           '<h2>Eisbahnen <span class="count">',
        '<h2>Centres aquatiques <span class="count">':   '<h2>Schwimmbäder <span class="count">',
        '<h2>Spa &amp; bien-être <span class="count">':  '<h2>Spa &amp; Wellness <span class="count">',
        '<h2>Aires de jeux couvertes <span class="count">': '<h2>Indoor-Spielplätze <span class="count">',
        '<h2>Sciences &amp; découverte <span class="count">': '<h2>Wissenschaft &amp; Entdeckung <span class="count">',
        '<h2>Musées <span class="count">':               '<h2>Museen <span class="count">',
        '<h2>Casinos <span class="count">':              '<h2>Casinos <span class="count">',
        '<h2>Autres loisirs indoor <span class="count">':'<h2>Sonstige Indoor-Freizeit <span class="count">',
        '<span class="cat-sub">jeux d\'évasion</span>':        '<span class="cat-sub">Rätselräume</span>',
        '<span class="cat-sub">salles indoor</span>':          '<span class="cat-sub">Indoor-Hallen</span>',
        '<span class="cat-sub">arènes couvertes</span>':       '<span class="cat-sub">Hallenarenen</span>',
        '<span class="cat-sub">indoor</span>':                 '<span class="cat-sub">Indoor</span>',
        '<span class="cat-sub">pistes couvertes</span>':       '<span class="cat-sub">Hallenbahnen</span>',
        '<span class="cat-sub">indoor &amp; circuits</span>':  '<span class="cat-sub">Indoor &amp; Pisten</span>',
        '<span class="cat-sub">glace couverte</span>':         '<span class="cat-sub">Halleneis</span>',
        '<span class="cat-sub">piscines couvertes</span>':     '<span class="cat-sub">Hallenbäder</span>',
        '<span class="cat-sub">thermes, balnéo</span>':        '<span class="cat-sub">Thermen, Balneo</span>',
        '<span class="cat-sub">enfants</span>':                '<span class="cat-sub">Kinder</span>',
        '<span class="cat-sub">interactif</span>':             '<span class="cat-sub">interaktiv</span>',
        "<span class=\"cat-sub\">toute l'année</span>":       '<span class="cat-sub">ganzjährig</span>',
        '<span class="cat-sub">jeux</span>':                   '<span class="cat-sub">Spiele</span>',
        '<span class="cat-sub">divers</span>':                 '<span class="cat-sub">Sonstiges</span>',
        ' lieux</span>': ' Orte</span>',
        ' lieu</span>':  ' Ort</span>',
        '>Payant<':  '>Kostenpflichtig<',
        '>Gratuit<': '>Kostenlos<',
        '>Nouveau<': '>Neu<',
        'Itinéraire ↗':    'Route ↗',
        'Site officiel ↗': 'Offizielle Website ↗',
        '· que faire':       '· was tun',
        '← Tous les lieux':  '← Alle Orte',
        '<h4>Que faire en Haute-Savoie</h4>': '<h4>Was tun in der Haute-Savoie</h4>',
        '<h4>Activités</h4>':                  '<h4>Aktivitäten</h4>',
        '<h4>Le guide</h4>':                   '<h4>Der Guide</h4>',
        'Le pendant «&nbsp;activités&nbsp;» du guide Loisirs 74. Quand le lac et les sentiers attendent le beau temps, voici où aller. Chaque fiche&nbsp;: une source officielle, une adresse, une carte.':
            'Das „Aktivitäten"-Pendant zum Loisirs-74-Guide. Wenn der See und die Wanderwege auf Sonnenschein warten, hier finden Sie Alternativen. Jeder Eintrag: eine offizielle Quelle, eine Adresse, eine Karte.',
        'Tous les lieux (où aller)': 'Alle Orte (wohin gehen)',
        'Mentions légales':          'Impressum',
        'Signaler une info':         'Info melden',
        '79 activités vérifiées · 14 catégories':
            '79 geprüfte Aktivitäten · 14 Kategorien',
    },
    "it": {
        "Que faire en Haute-Savoie quand il pleut — Activités indoor & toute saison · Loisirs 74":
            "Cosa fare in Alta Savoia quando piove — Attività indoor e per ogni stagione · Loisirs 74",
        "Toutes les activités indoor et par tout temps de Haute-Savoie, vérifiées une par une : escape games, escalade, bowling, karting, patinoires, centres aquatiques, spa, musées. Chaque page une source officielle.":
            "Tutte le attività indoor e per ogni tempo dell'Alta Savoia, verificate una a una: escape room, arrampicata, bowling, kart, piste di pattinaggio, centri acquatici, spa, musei. Ogni pagina: una fonte ufficiale.",
        "Le guide de la Haute-Savoie · par tout temps": "La guida dell'Alta Savoia · con ogni tempo",
        "<span><span>Que faire</span></span>":         "<span><span>Cosa fare</span></span>",
        "<span><span>quand il</span></span>":           "<span><span>quando</span></span>",
        "<span><span><em>pleut</em></span></span>":     "<span><span><em>piove</em></span></span>",
        'Toutes les activités <b>indoor et par tout temps</b> de Haute-Savoie, vérifiées une par une&nbsp;: escape games, escalade, bowling, karting, patinoires, centres aquatiques, spa, musées. Chaque fiche&nbsp;: une source officielle, une adresse, une carte.':
            'Tutte le attività <b>indoor e per ogni tempo</b> dell\'Alta Savoia, verificate una a una&nbsp;: escape room, arrampicata, bouldering, bowling, kart, piste di pattinaggio, centri acquatici, spa, musei. Ogni voce&nbsp;: una fonte ufficiale, un indirizzo, una mappa.',
        '<span class="cat-nav-label">Sommaire</span>': '<span class="cat-nav-label">Indice</span>',
        '<a href="#escape">Escape games</a>':           '<a href="#escape">Escape room</a>',
        '<a href="#escalade">Escalade &amp; bloc</a>':  '<a href="#escalade">Arrampicata &amp; bouldering</a>',
        '<a href="#laser">Laser game</a>':              '<a href="#laser">Laser game</a>',
        '<a href="#trampoline">Trampoline parks</a>':   '<a href="#trampoline">Trampoline park</a>',
        '<a href="#bowling">Bowling</a>':               '<a href="#bowling">Bowling</a>',
        '<a href="#karting">Karting</a>':               '<a href="#karting">Kart</a>',
        '<a href="#patinoire">Patinoires</a>':          '<a href="#patinoire">Piste di pattinaggio</a>',
        '<a href="#aquatique">Centres aquatiques</a>':  '<a href="#aquatique">Centri acquatici</a>',
        '<a href="#spa">Spa &amp; bien-être</a>':       '<a href="#spa">Spa &amp; benessere</a>',
        '<a href="#soft-play">Aires de jeux couvertes</a>': '<a href="#soft-play">Aree gioco coperte</a>',
        '<a href="#science">Sciences &amp; découverte</a>': '<a href="#science">Scienza &amp; scoperta</a>',
        '<a href="#musee">Musées</a>':                  '<a href="#musee">Musei</a>',
        '<a href="#casino">Casinos</a>':                '<a href="#casino">Casinò</a>',
        '<a href="#autre">Autres loisirs indoor</a>':   '<a href="#autre">Altri svaghi indoor</a>',
        '<h2>Escape games <span class="count">':         '<h2>Escape room <span class="count">',
        '<h2>Escalade &amp; bloc <span class="count">':  '<h2>Arrampicata &amp; bouldering <span class="count">',
        '<h2>Laser game <span class="count">':           '<h2>Laser game <span class="count">',
        '<h2>Trampoline parks <span class="count">':    '<h2>Trampoline park <span class="count">',
        '<h2>Bowling <span class="count">':              '<h2>Bowling <span class="count">',
        '<h2>Karting <span class="count">':              '<h2>Kart <span class="count">',
        '<h2>Patinoires <span class="count">':           '<h2>Piste di pattinaggio <span class="count">',
        '<h2>Centres aquatiques <span class="count">':   '<h2>Centri acquatici <span class="count">',
        '<h2>Spa &amp; bien-être <span class="count">':  '<h2>Spa &amp; benessere <span class="count">',
        '<h2>Aires de jeux couvertes <span class="count">': '<h2>Aree gioco coperte <span class="count">',
        '<h2>Sciences &amp; découverte <span class="count">': '<h2>Scienza &amp; scoperta <span class="count">',
        '<h2>Musées <span class="count">':               '<h2>Musei <span class="count">',
        '<h2>Casinos <span class="count">':              '<h2>Casinò <span class="count">',
        '<h2>Autres loisirs indoor <span class="count">':'<h2>Altri svaghi indoor <span class="count">',
        '<span class="cat-sub">jeux d\'évasion</span>':        '<span class="cat-sub">stanze di enigmi</span>',
        '<span class="cat-sub">salles indoor</span>':          '<span class="cat-sub">palestre indoor</span>',
        '<span class="cat-sub">arènes couvertes</span>':       '<span class="cat-sub">arene coperte</span>',
        '<span class="cat-sub">indoor</span>':                 '<span class="cat-sub">indoor</span>',
        '<span class="cat-sub">pistes couvertes</span>':       '<span class="cat-sub">piste coperte</span>',
        '<span class="cat-sub">indoor &amp; circuits</span>':  '<span class="cat-sub">indoor &amp; circuiti</span>',
        '<span class="cat-sub">glace couverte</span>':         '<span class="cat-sub">ghiaccio coperto</span>',
        '<span class="cat-sub">piscines couvertes</span>':     '<span class="cat-sub">piscine coperte</span>',
        '<span class="cat-sub">thermes, balnéo</span>':        '<span class="cat-sub">terme, balneo</span>',
        '<span class="cat-sub">enfants</span>':                '<span class="cat-sub">bambini</span>',
        '<span class="cat-sub">interactif</span>':             '<span class="cat-sub">interattivo</span>',
        "<span class=\"cat-sub\">toute l'année</span>":       '<span class="cat-sub">tutto l\'anno</span>',
        '<span class="cat-sub">jeux</span>':                   '<span class="cat-sub">gioco</span>',
        '<span class="cat-sub">divers</span>':                 '<span class="cat-sub">vari</span>',
        ' lieux</span>': ' luoghi</span>',
        ' lieu</span>':  ' luogo</span>',
        '>Payant<':  '>A pagamento<',
        '>Gratuit<': '>Gratuito<',
        '>Nouveau<': '>Novità<',
        'Itinéraire ↗':    'Itinerario ↗',
        'Site officiel ↗': 'Sito ufficiale ↗',
        '· que faire':       '· cosa fare',
        '← Tous les lieux':  '← Tutti i luoghi',
        '<h4>Que faire en Haute-Savoie</h4>': '<h4>Cosa fare in Alta Savoia</h4>',
        '<h4>Activités</h4>':                  '<h4>Attività</h4>',
        '<h4>Le guide</h4>':                   '<h4>La guida</h4>',
        'Le pendant «&nbsp;activités&nbsp;» du guide Loisirs 74. Quand le lac et les sentiers attendent le beau temps, voici où aller. Chaque fiche&nbsp;: une source officielle, une adresse, une carte.':
            'Il versante "attività" della guida Loisirs 74. Quando il lago e i sentieri aspettano il bel tempo, ecco dove andare. Ogni voce: una fonte ufficiale, un indirizzo, una mappa.',
        'Tous les lieux (où aller)': 'Tutti i luoghi (dove andare)',
        'Mentions légales':          'Note legali',
        'Signaler une info':         'Segnalare un\'informazione',
        '79 activités vérifiées · 14 catégories':
            '79 attività verificate · 14 categorie',
    },
    "es": {
        "Que faire en Haute-Savoie quand il pleut — Activités indoor & toute saison · Loisirs 74":
            "Qué hacer en Alta Saboya cuando llueve — Actividades indoor y todo el año · Loisirs 74",
        "Toutes les activités indoor et par tout temps de Haute-Savoie, vérifiées une par une : escape games, escalade, bowling, karting, patinoires, centres aquatiques, spa, musées. Chaque page une source officielle.":
            "Todas las actividades indoor y para cualquier tiempo de Alta Saboya, verificadas una a una: escape rooms, escalada, bolos, karting, pistas de patinaje, centros acuáticos, spa, museos. Cada página: una fuente oficial.",
        "Le guide de la Haute-Savoie · par tout temps": "La guía de Alta Saboya · con cualquier tiempo",
        "<span><span>Que faire</span></span>":         "<span><span>Qué hacer</span></span>",
        "<span><span>quand il</span></span>":           "<span><span>cuando</span></span>",
        "<span><span><em>pleut</em></span></span>":     "<span><span><em>llueve</em></span></span>",
        'Toutes les activités <b>indoor et par tout temps</b> de Haute-Savoie, vérifiées une par une&nbsp;: escape games, escalade, bowling, karting, patinoires, centres aquatiques, spa, musées. Chaque fiche&nbsp;: une source officielle, une adresse, une carte.':
            'Todas las actividades <b>indoor y para cualquier tiempo</b> de Alta Saboya, verificadas una a una&nbsp;: escape rooms, escalada, búlder, bolos, karting, pistas de patinaje, centros acuáticos, spa, museos. Cada entrada&nbsp;: una fuente oficial, una dirección, un mapa.',
        '<span class="cat-nav-label">Sommaire</span>': '<span class="cat-nav-label">Índice</span>',
        '<a href="#escape">Escape games</a>':           '<a href="#escape">Escape rooms</a>',
        '<a href="#escalade">Escalade &amp; bloc</a>':  '<a href="#escalade">Escalada &amp; búlder</a>',
        '<a href="#laser">Laser game</a>':              '<a href="#laser">Láser tag</a>',
        '<a href="#trampoline">Trampoline parks</a>':   '<a href="#trampoline">Parques de cama elástica</a>',
        '<a href="#bowling">Bowling</a>':               '<a href="#bowling">Bolos</a>',
        '<a href="#karting">Karting</a>':               '<a href="#karting">Karting</a>',
        '<a href="#patinoire">Patinoires</a>':          '<a href="#patinoire">Pistas de patinaje</a>',
        '<a href="#aquatique">Centres aquatiques</a>':  '<a href="#aquatique">Centros acuáticos</a>',
        '<a href="#spa">Spa &amp; bien-être</a>':       '<a href="#spa">Spa &amp; bienestar</a>',
        '<a href="#soft-play">Aires de jeux couvertes</a>': '<a href="#soft-play">Áreas de juego cubiertas</a>',
        '<a href="#science">Sciences &amp; découverte</a>': '<a href="#science">Ciencia &amp; descubrimiento</a>',
        '<a href="#musee">Musées</a>':                  '<a href="#musee">Museos</a>',
        '<a href="#casino">Casinos</a>':                '<a href="#casino">Casinos</a>',
        '<a href="#autre">Autres loisirs indoor</a>':   '<a href="#autre">Otros ocios indoor</a>',
        '<h2>Escape games <span class="count">':         '<h2>Escape rooms <span class="count">',
        '<h2>Escalade &amp; bloc <span class="count">':  '<h2>Escalada &amp; búlder <span class="count">',
        '<h2>Laser game <span class="count">':           '<h2>Láser tag <span class="count">',
        '<h2>Trampoline parks <span class="count">':    '<h2>Parques de cama elástica <span class="count">',
        '<h2>Bowling <span class="count">':              '<h2>Bolos <span class="count">',
        '<h2>Karting <span class="count">':              '<h2>Karting <span class="count">',
        '<h2>Patinoires <span class="count">':           '<h2>Pistas de patinaje <span class="count">',
        '<h2>Centres aquatiques <span class="count">':   '<h2>Centros acuáticos <span class="count">',
        '<h2>Spa &amp; bien-être <span class="count">':  '<h2>Spa &amp; bienestar <span class="count">',
        '<h2>Aires de jeux couvertes <span class="count">': '<h2>Áreas de juego cubiertas <span class="count">',
        '<h2>Sciences &amp; découverte <span class="count">': '<h2>Ciencia &amp; descubrimiento <span class="count">',
        '<h2>Musées <span class="count">':               '<h2>Museos <span class="count">',
        '<h2>Casinos <span class="count">':              '<h2>Casinos <span class="count">',
        '<h2>Autres loisirs indoor <span class="count">':'<h2>Otros ocios indoor <span class="count">',
        '<span class="cat-sub">jeux d\'évasion</span>':        '<span class="cat-sub">salas de enigmas</span>',
        '<span class="cat-sub">salles indoor</span>':          '<span class="cat-sub">salas indoor</span>',
        '<span class="cat-sub">arènes couvertes</span>':       '<span class="cat-sub">arenas cubiertas</span>',
        '<span class="cat-sub">indoor</span>':                 '<span class="cat-sub">indoor</span>',
        '<span class="cat-sub">pistes couvertes</span>':       '<span class="cat-sub">pistas cubiertas</span>',
        '<span class="cat-sub">indoor &amp; circuits</span>':  '<span class="cat-sub">indoor &amp; circuitos</span>',
        '<span class="cat-sub">glace couverte</span>':         '<span class="cat-sub">hielo cubierto</span>',
        '<span class="cat-sub">piscines couvertes</span>':     '<span class="cat-sub">piscinas cubiertas</span>',
        '<span class="cat-sub">thermes, balnéo</span>':        '<span class="cat-sub">termas, balneo</span>',
        '<span class="cat-sub">enfants</span>':                '<span class="cat-sub">niños</span>',
        '<span class="cat-sub">interactif</span>':             '<span class="cat-sub">interactivo</span>',
        "<span class=\"cat-sub\">toute l'année</span>":       '<span class="cat-sub">todo el año</span>',
        '<span class="cat-sub">jeux</span>':                   '<span class="cat-sub">juegos</span>',
        '<span class="cat-sub">divers</span>':                 '<span class="cat-sub">varios</span>',
        ' lieux</span>': ' lugares</span>',
        ' lieu</span>':  ' lugar</span>',
        '>Payant<':  '>De pago<',
        '>Gratuit<': '>Gratis<',
        '>Nouveau<': '>Nuevo<',
        'Itinéraire ↗':    'Cómo llegar ↗',
        'Site officiel ↗': 'Sitio oficial ↗',
        '· que faire':       '· qué hacer',
        '← Tous les lieux':  '← Todos los lugares',
        '<h4>Que faire en Haute-Savoie</h4>': '<h4>Qué hacer en Alta Saboya</h4>',
        '<h4>Activités</h4>':                  '<h4>Actividades</h4>',
        '<h4>Le guide</h4>':                   '<h4>La guía</h4>',
        'Le pendant «&nbsp;activités&nbsp;» du guide Loisirs 74. Quand le lac et les sentiers attendent le beau temps, voici où aller. Chaque fiche&nbsp;: une source officielle, une adresse, une carte.':
            'El "pendant" de actividades de la guía Loisirs 74. Cuando el lago y los senderos esperan el buen tiempo, aquí dónde ir. Cada entrada: una fuente oficial, una dirección, un mapa.',
        'Tous les lieux (où aller)': 'Todos los lugares (dónde ir)',
        'Mentions légales':          'Aviso legal',
        'Signaler une info':         'Notificar información',
        '79 activités vérifiées · 14 catégories':
            '79 actividades verificadas · 14 categorías',
    },
}


def build_lang_picker(active_lang):
    """Build language picker as a <details>/<summary>/<lang-menu> matching site convention."""
    links = []
    for l in ("fr","en","de","it","es"):
        href = f"https://loisirs74.fr/que-faire/" if l == "fr" else f"https://loisirs74.fr/{l}/que-faire/"
        cur = ' aria-current="true"' if l == active_lang else ''
        links.append(f'<a href="{href}"{cur} hreflang="{l}">{LANG_NAMES[l]}</a>')
    return ('<details class="lang-picker"><summary><b>' + active_lang.upper() + '</b> · 5 langues</summary>'
            '<div class="lang-menu">' + ''.join(links) + '</div></details>')


def rewrite_venue_links(html, loc):
    """Rewrite https://loisirs74.fr/{slug} → https://loisirs74.fr/{loc}/{slug} if locale file exists."""
    def replacer(m):
        slug = m.group(1)
        if (REPO / loc / f"{slug}.html").exists():
            return f'https://loisirs74.fr/{loc}/{slug}'
        return m.group(0)  # keep root
    return re.sub(r'https://loisirs74\.fr/([a-z][a-z0-9-]+)(?=["#])', replacer, html)


def build_locale(loc):
    """Build {loc}/que-faire/index.html."""
    out_dir = REPO / loc / "que-faire"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "index.html"
    s = FR_SRC.read_text(encoding="utf-8")

    # 1) <html lang>
    s = re.sub(r'<html lang="fr">', f'<html lang="{loc}">', s, count=1)
    # 2) Canonical: replace href to locale variant
    s = re.sub(
        r'<link rel="canonical" href="https://loisirs74\.fr/que-faire/">',
        f'<link rel="canonical" href="https://loisirs74.fr/{loc}/que-faire/">', s, count=1)
    # 3) og:locale (add if missing; first try replace, else inject after canonical)
    if '<meta property="og:locale"' in s:
        s = re.sub(r'<meta property="og:locale" content="[^"]+">',
                   f'<meta property="og:locale" content="{OG_LOCALES[loc]}">', s)
    else:
        s = s.replace(f'<link rel="canonical" href="https://loisirs74.fr/{loc}/que-faire/">',
                      f'<link rel="canonical" href="https://loisirs74.fr/{loc}/que-faire/">\n'
                      f'<meta property="og:locale" content="{OG_LOCALES[loc]}">')
    # 4) Apply chrome translations
    for fr, tr in T[loc].items():
        s = s.replace(fr, tr)
    # 5) Rewrite venue links to locale if available
    s = rewrite_venue_links(s, loc)
    # 6) Add language picker to header — replace "← Tous les lieux" link
    # The original header has a brand + back-home link. Add picker between them.
    # The "back-home" string was already translated above.
    bh_translations = {
        "en": "← All places", "de": "← Alle Orte",
        "it": "← Tutti i luoghi", "es": "← Todos los lugares"
    }
    bh = bh_translations[loc]
    picker = build_lang_picker(loc)
    s = s.replace(
        f'<a href="https://loisirs74.fr/" class="back-home">{bh}</a>',
        f'{picker}\n  <a href="https://loisirs74.fr/" class="back-home">{bh}</a>'
    )

    out_path.write_text(s, encoding="utf-8")
    return out_path


def retrofit_fr_picker():
    """Add the same language picker to the FR /que-faire/ now that locale variants exist."""
    fr_path = REPO / "que-faire/index.html"
    s = fr_path.read_text(encoding="utf-8")
    if 'lang-picker' in s:
        print("  FR: picker already present")
        return
    picker = build_lang_picker("fr")
    s = s.replace(
        '<a href="https://loisirs74.fr/" class="back-home">← Tous les lieux</a>',
        f'{picker}\n  <a href="https://loisirs74.fr/" class="back-home">← Tous les lieux</a>'
    )
    fr_path.write_text(s, encoding="utf-8")
    print(f"  FR: picker added")


def update_sitemap():
    """Update the hub entry for /que-faire/ to include the new locale variants."""
    sm = REPO / "sitemap.xml"
    s = sm.read_text(encoding="utf-8")
    # The existing entry already references /en/what-to-do/ etc. as hreflang alternates.
    # Now add full <url> entries for each locale variant.
    added = 0
    new_entries = []
    for loc in ("en","de","it","es"):
        url = f"https://loisirs74.fr/{loc}/que-faire/"
        if f'<loc>{url}</loc>' in s:
            continue
        entry = (f'  <url><loc>{url}</loc><changefreq>weekly</changefreq>'
                 f'<xhtml:link rel="alternate" hreflang="fr" href="https://loisirs74.fr/que-faire/"/>'
                 f'<xhtml:link rel="alternate" hreflang="en" href="https://loisirs74.fr/en/what-to-do/"/>'
                 f'<xhtml:link rel="alternate" hreflang="de" href="https://loisirs74.fr/de/was-unternehmen/"/>'
                 f'<xhtml:link rel="alternate" hreflang="it" href="https://loisirs74.fr/it/cosa-fare/"/>'
                 f'<xhtml:link rel="alternate" hreflang="es" href="https://loisirs74.fr/es/que-hacer/"/>'
                 f'<xhtml:link rel="alternate" hreflang="x-default" href="https://loisirs74.fr/que-faire/"/></url>')
        new_entries.append(entry)
        added += 1
    if new_entries:
        s = s.replace('</urlset>', '\n'.join(new_entries) + '\n</urlset>')
        sm.write_text(s, encoding="utf-8")
    print(f"  sitemap: +{added} locale /que-faire/ entries")


def main():
    for loc in ("en","de","it","es"):
        p = build_locale(loc)
        size = p.stat().st_size
        print(f"  built {p}  ({size:,} bytes)")
    retrofit_fr_picker()
    update_sitemap()


if __name__ == "__main__":
    main()
