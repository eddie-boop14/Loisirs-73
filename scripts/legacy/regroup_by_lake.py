#!/usr/bin/env python3
"""
Regroup the lakes/beaches hubs (/lacs/ + /plages/, all 5 langs) so the
sections are keyed by LAKE instead of by commune. Pure re-bucketing of
the existing, already-restyled cards: head, style, header, breadcrumb,
hub-hero, footer and the cursor/reveal JS are left untouched. Only the
filter bar, <main>, and the bottom map/filter <script> are rebuilt.

Also enriches Json/<plage-slug>.json with a "lac" field.
"""
import re
import json
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path("/home/user/Loisir-74")

# ---- canonical slug -> lake key ----
LAKE_OF_SLUG = {
    # Lac d'Annecy
    'plage-albigny': 'annecy',
    'plage-des-marquisats': 'annecy',
    'plage-imperial-annecy': 'annecy',
    'plage-de-doussard': 'annecy',
    'plage-de-menthon-saint-bernard': 'annecy',
    'plage-de-saint-jorioz': 'annecy',
    'plage-de-sevrier': 'annecy',
    'plage-de-talloires': 'annecy',
    'plage-d-angon-talloires': 'annecy',
    'plage-de-la-brune-veyrier': 'annecy',
    # Lac Léman
    'plage-d-excenevex': 'leman',
    'plage-de-sciez-sur-leman': 'leman',
    'plage-de-la-pinede': 'leman',
    'plage-de-saint-disdille': 'leman',
    'plage-municipale-thonon': 'leman',
    'plage-d-amphion-publier': 'leman',
    'plage-de-saint-gingolph': 'leman',
    'plage-d-evian-centre-nautique': 'leman',
    # Lac de Montriond
    'plage-du-lac-de-montriond': 'montriond',
    # Petits lacs de montagne (standalone lake cards, /lacs/ only)
    'lac-de-vallon': 'petits',
    'lac-blanc': 'petits',
    'lac-cornu': 'petits',
    'lac-des-dronieres': 'petits',
    'lac-des-confins': 'petits',
    'lac-benit': 'petits',
    'lac-de-passy': 'petits',
    'lac-vert-passy': 'petits',
}

LAKE_ORDER = ['annecy', 'leman', 'montriond', 'petits']

LAKE_NAME = {
    'fr': {'annecy': "Lac d'Annecy", 'leman': "Lac Léman", 'montriond': "Lac de Montriond", 'petits': "Petits lacs de montagne"},
    'en': {'annecy': "Lake Annecy", 'leman': "Lake Geneva", 'montriond': "Lake Montriond", 'petits': "Smaller mountain lakes"},
    'de': {'annecy': "Lac d'Annecy", 'leman': "Genfersee", 'montriond': "Lac de Montriond", 'petits': "Kleine Bergseen"},
    'it': {'annecy': "Lago di Annecy", 'leman': "Lago di Ginevra", 'montriond': "Lago di Montriond", 'petits': "Piccoli laghi di montagna"},
    'es': {'annecy': "Lago de Annecy", 'leman': "Lago Lemán", 'montriond': "Lago de Montriond", 'petits': "Pequeños lagos de montaña"},
}

LAC_LABEL = {'fr': 'Lac', 'en': 'Lake', 'de': 'See', 'it': 'Lago', 'es': 'Lago'}
ALL_LAKES = {'fr': 'Tous les lacs', 'en': 'All lakes', 'de': 'Alle Seen', 'it': 'Tutti i laghi', 'es': 'Todos los lagos'}

# (singular, plural) section-count noun
COUNT_NOUN = {
    'lacs': {'fr': ('lieu', 'lieux'), 'en': ('place', 'places'), 'de': ('Ort', 'Orte'), 'it': ('luogo', 'luoghi'), 'es': ('lugar', 'lugares')},
    'plages': {'fr': ('plage', 'plages'), 'en': ('beach', 'beaches'), 'de': ('Strand', 'Strände'), 'it': ('spiaggia', 'spiagge'), 'es': ('playa', 'playas')},
}

# (singular, plural) live-count label e.g. "3 plages affichées"
SHOWN = {
    'lacs': {
        'fr': ('lieu affiché', 'lieux affichés'), 'en': ('place shown', 'places shown'),
        'de': ('Ort angezeigt', 'Orte angezeigt'), 'it': ('luogo mostrato', 'luoghi mostrati'),
        'es': ('lugar mostrado', 'lugares mostrados'),
    },
    'plages': {
        'fr': ('plage affichée', 'plages affichées'), 'en': ('beach shown', 'beaches shown'),
        'de': ('Strand angezeigt', 'Strände angezeigt'), 'it': ('spiaggia mostrata', 'spiagge mostrate'),
        'es': ('playa mostrada', 'playas mostradas'),
    },
}

# path -> (family, lang)
TARGETS = {
    'lacs/index.html': ('lacs', 'fr'),
    'en/lakes/index.html': ('lacs', 'en'),
    'de/seen/index.html': ('lacs', 'de'),
    'it/laghi/index.html': ('lacs', 'it'),
    'es/lagos/index.html': ('lacs', 'es'),
    'plages/index.html': ('plages', 'fr'),
    'en/beaches/index.html': ('plages', 'en'),
    'de/straende/index.html': ('plages', 'de'),
    'it/spiagge/index.html': ('plages', 'it'),
    'es/playas/index.html': ('plages', 'es'),
}


def slug_of_card(card):
    t = card.select_one('a.title')
    if not t or not t.has_attr('href'):
        return None
    return t['href'].rstrip('/').split('/')[-1]


def commune_of_card(card, sec):
    # idempotent: prefer the card's own data, fall back to section
    if card.has_attr('data-commune'):
        return card['data-commune']
    cc = card.select_one('.card-commune span') or card.select_one('.card-commune')
    if cc and cc.get_text(strip=True):
        return cc.get_text(strip=True)
    return sec.get('data-commune', '')


def regroup_file(rel_path, family, lang):
    path = ROOT / rel_path
    text = path.read_text(encoding='utf-8')
    soup = BeautifulSoup(text, 'html.parser')

    # --- collect cards into lake buckets ---
    buckets = {k: [] for k in LAKE_ORDER}
    total = 0
    unknown = []
    for sec in soup.select('.commune-section'):
        commune = sec.get('data-commune', '')
        for card in sec.select('article.card'):
            slug = slug_of_card(card)
            lake = LAKE_OF_SLUG.get(slug)
            if lake is None:
                unknown.append(slug)
                continue
            # tag card with its commune for the commune filter
            card['data-commune'] = commune_of_card(card, sec)
            buckets[lake].append(str(card))
            total += 1

    if unknown:
        raise SystemExit(f"{rel_path}: unmapped slugs {unknown}")

    sing, plur = COUNT_NOUN[family][lang]
    names = LAKE_NAME[lang]

    # --- build new <main> ---
    sec_html = []
    present_lakes = []
    for key in LAKE_ORDER:
        cards = buckets[key]
        if not cards:
            continue
        present_lakes.append(key)
        n = len(cards)
        noun = sing if n == 1 else plur
        cards_joined = "\n".join(cards)
        sec_html.append(
            f'<div class="commune-section" data-lac="{key}">\n'
            f'<div class="commune-head"><h3>{names[key]}</h3>'
            f'<span class="commune-count">{n} {noun}</span></div>\n'
            f'<div class="carousel">\n{cards_joined}\n</div>\n'
            f'</div>'
        )

    # preserve the existing empty-state node verbatim
    empty = soup.select_one('#empty-state')
    empty_html = str(empty) if empty else ''

    new_main = (
        "<main>\n  <div class=\"wrap\">\n\n"
        + "\n".join(sec_html)
        + "\n\n" + empty_html
        + "\n\n  </div>\n</main>"
    )

    # --- build new filter bar (reuse existing commune/access/sort markup) ---
    fb = soup.select_one('.filter-bar')
    commune_select = str(fb.select_one('#filt-commune'))
    access_group = str(fb.select_one('#filt-access'))
    sort_select = str(fb.select_one('#filt-sort'))
    # existing label texts
    labels = {}
    for lb in fb.select('label'):
        span = lb.find('span')
        if not span:
            continue
        if lb.find('select', id='filt-commune'):
            labels['commune'] = span.get_text(strip=True)
        elif lb.find('select', id='filt-sort'):
            labels['sort'] = span.get_text(strip=True)
        elif lb.find(id='filt-access'):
            labels['access'] = span.get_text(strip=True)
    shown_sg, shown_pl = SHOWN[family][lang]
    count_label_txt = shown_pl

    # Lac select options (only lakes present in this hub)
    lac_opts = [f'<option value="">{ALL_LAKES[lang]}</option>']
    for key in present_lakes:
        lac_opts.append(f'<option value="{key}">{names[key]}</option>')
    lac_select = f'<select id="filt-lac">{"".join(lac_opts)}</select>'

    new_filter = f'''<div class="filter-bar">
  <div class="wrap">
    <label>
      <span>{LAC_LABEL[lang]}</span>
      {lac_select}
    </label>
    <label>
      <span>{labels.get('commune','Commune')}</span>
      {commune_select}
    </label>
    <label>
      <span>{labels.get('access','Accès')}</span>
      {access_group}
    </label>
    <label>
      <span>{labels.get('sort','Tri')}</span>
      {sort_select}
    </label>
    <div class="count-live"><b id="count-n">0</b> <span id="count-label">{count_label_txt}</span></div>
  </div>
</div>'''

    # --- extract existing PINS for the new script ---
    pins_match = re.search(r'const\s+PINS\s*=\s*(\[.*?\]);', text, re.DOTALL)
    pins_literal = pins_match.group(1) if pins_match else '[]'

    new_scripts = '''<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<script>
// Cursor halo
(function(){
  if (matchMedia('(hover:none)').matches) return;
  const glow = document.getElementById('cursorGlow');
  if (!glow) return;
  let mx = innerWidth/2, my = innerHeight/2, gx = mx, gy = my;
  window.addEventListener('pointermove', e=>{ mx = e.clientX; my = e.clientY; }, {passive:true});
  function tick(){
    gx += (mx-gx)*0.08; gy += (my-gy)*0.08;
    glow.style.transform = 'translate(' + gx + 'px,' + gy + 'px) translate(-50%,-50%)';
    requestAnimationFrame(tick);
  }
  tick();
})();

// Reveal on scroll
(function(){
  const els = document.querySelectorAll('.commune-section, .card');
  els.forEach(el => el.classList.add('reveal'));
  const io = new IntersectionObserver((entries)=>{
    entries.forEach(e=>{
      if (e.isIntersecting){ e.target.classList.add('in'); io.unobserve(e.target); }
    });
  }, {threshold:.08, rootMargin:'0px 0px -6% 0px'});
  els.forEach(el => io.observe(el));
})();

// MAP + FILTERS (lake + commune + access)
(function(){
  const PINS = __PINS__;
  const SHOWN_SG = __SG__;
  const SHOWN_PL = __PL__;
  if (typeof L === 'undefined' || PINS.length === 0) return;
  const map = L.map('cat-map', { scrollWheelZoom: false });
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 18,
    attribution: '© <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>'
  }).addTo(map);

  function makeIcon(paid){
    const color = paid ? '#e07a3f' : '#2e4a3a';
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="36" viewBox="0 0 28 36"><path d="M14 0C6.3 0 0 6.3 0 14c0 10.5 14 22 14 22s14-11.5 14-22C28 6.3 21.7 0 14 0z" fill="'+color+'"/><circle cx="14" cy="14" r="5" fill="#fdfaf3"/></svg>';
    return L.divIcon({ className:'l74-pin', html: svg, iconSize:[28,36], iconAnchor:[14,36], popupAnchor:[0,-32] });
  }

  const layers = {};
  const markers = [];
  for (const p of PINS) {
    const m = L.marker([p.lat, p.lng], {icon: makeIcon(!!p.paid)}).addTo(map);
    m.bindPopup('<a href="'+p.url+'">'+p.name+'</a><span class="commune-pop">'+p.commune+'</span>');
    layers[p.slug] = m;
    markers.push(m);
  }
  const group = L.featureGroup(markers);
  map.fitBounds(group.getBounds().pad(0.15));

  const lacSel = document.getElementById('filt-lac');
  const communeSel = document.getElementById('filt-commune');
  const accessGroup = document.getElementById('filt-access');
  const sortSel = document.getElementById('filt-sort');
  const countN = document.getElementById('count-n');
  const countLabel = document.getElementById('count-label');
  const emptyState = document.getElementById('empty-state');

  let curLac = '';
  let curCommune = '';
  let curAccess = 'all';
  let curSort = 'commune';

  function pinPaid(slug){ const p = PINS.find(x => x.slug === slug); return p ? !!p.paid : false; }

  function applyFilters(){
    const sections = document.querySelectorAll('.commune-section');
    let visibleMarkers = [];
    let total = 0;
    sections.forEach(sec => {
      const lacMatch = !curLac || sec.dataset.lac === curLac;
      let visibleCards = 0;
      sec.querySelectorAll('.card').forEach(card => {
        const communeMatch = !curCommune || card.dataset.commune === curCommune;
        const titleLink = card.querySelector('a.title');
        const href = titleLink ? titleLink.getAttribute('href') : '';
        const slug = href.replace(/\\/$/, '').split('/').pop();
        const isPaid = pinPaid(slug);
        const accessMatch = curAccess === 'all' || (curAccess === 'free' && !isPaid) || (curAccess === 'paid' && isPaid);
        const show = lacMatch && communeMatch && accessMatch;
        card.classList.toggle('hidden', !show);
        if (show){ visibleCards++; total++; if (layers[slug]) visibleMarkers.push(layers[slug]); }
      });
      sec.classList.toggle('hidden', visibleCards === 0);
    });
    if (countN) countN.textContent = total;
    if (countLabel) countLabel.textContent = total === 1 ? SHOWN_SG : SHOWN_PL;
    if (emptyState) emptyState.style.display = total === 0 ? 'block' : 'none';
    if (visibleMarkers.length){ const fg = L.featureGroup(visibleMarkers); map.fitBounds(fg.getBounds().pad(0.15)); }
  }

  function applySort(){
    const sections = Array.from(document.querySelectorAll('.commune-section'));
    if (curSort === 'alpha'){
      sections.forEach(sec => {
        const carousel = sec.querySelector('.carousel');
        const cards = Array.from(carousel.querySelectorAll('.card'));
        cards.sort((a, b) => {
          const na = a.querySelector('a.title')?.textContent || '';
          const nb = b.querySelector('a.title')?.textContent || '';
          return na.localeCompare(nb);
        });
        cards.forEach(c => carousel.appendChild(c));
      });
    }
  }

  if (lacSel) lacSel.addEventListener('change', e => { curLac = e.target.value; applyFilters(); });
  if (communeSel) communeSel.addEventListener('change', e => { curCommune = e.target.value; applyFilters(); });
  if (accessGroup) accessGroup.addEventListener('click', e => {
    if (e.target.tagName === 'BUTTON'){
      accessGroup.querySelectorAll('button').forEach(b => b.classList.remove('active'));
      e.target.classList.add('active');
      curAccess = e.target.dataset.v;
      applyFilters();
    }
  });
  if (sortSel) sortSel.addEventListener('change', e => { curSort = e.target.value; applySort(); });

  applyFilters();
})();
</script>'''

    new_scripts = (new_scripts
                   .replace('__PINS__', pins_literal)
                   .replace('__SG__', json.dumps(shown_sg, ensure_ascii=False))
                   .replace('__PL__', json.dumps(shown_pl, ensure_ascii=False)))

    # --- splice the three regions back into the raw text ---
    text = re.sub(r'<div class="filter-bar">.*?(?=<main>)', new_filter + '\n\n', text, count=1, flags=re.DOTALL)
    text = re.sub(r'<main>.*?</main>', lambda m: new_main, text, count=1, flags=re.DOTALL)
    text = re.sub(r'<script src="https://unpkg\.com/leaflet.*</script>\s*</body>',
                  lambda m: new_scripts + '\n\n</body>', text, count=1, flags=re.DOTALL)

    path.write_text(text, encoding='utf-8')
    return total, {k: len(v) for k, v in buckets.items() if v}


def enrich_json():
    """Add a French "lac" name to each plage's Json/<slug>.json."""
    changed = 0
    for slug, key in LAKE_OF_SLUG.items():
        if key == 'petits':
            continue  # standalone lakes are not beaches-on-a-lake
        jp = ROOT / 'Json' / f'{slug}.json'
        if not jp.exists():
            continue
        data = json.loads(jp.read_text(encoding='utf-8'))
        lac_name = LAKE_NAME['fr'][key]
        if data.get('lac') != lac_name:
            data['lac'] = lac_name
            jp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            changed += 1
    return changed


def main():
    for rel, (family, lang) in TARGETS.items():
        total, dist = regroup_file(rel, family, lang)
        print(f"  ✓ {rel:30s} {total:3d} cards  {dist}")
    n = enrich_json()
    print(f"  ✓ enriched {n} plage JSON files with 'lac'")


if __name__ == '__main__':
    main()
