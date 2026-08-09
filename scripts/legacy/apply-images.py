#!/usr/bin/env python3
"""
apply-images.py — Loisirs 74  (supersedes apply-generique.py)
============================================================
Resolve one canonical hero image per place by priority and propagate it
to every place page, hub card, "à proximité" card and homepage card — in
all 5 locales.

    priority 1  /<slug>-hero.jpg exists at root   -> use the local photo
    priority 2  a Wikimedia image can be recovered -> use the Wikimedia URL
    priority 3  neither                            -> /generique-<cat>.jpg

Wikimedia URLs are recovered from the pre-`apply-generique` snapshot
extracted to /tmp/oldzip, with photo-credits.json (md5-derived URL) as a
fallback. Real photos get an honest <div class="hero-credit">; génériques
keep the data-generique tagging.

Idempotent.
"""

import glob
import hashlib
import json
import re
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).parent
ZIP = Path('/tmp/oldzip')
LOCALES = ['de', 'en', 'es', 'it']

UTIL = {'index', '404', 'studio', 'cgv', 'devenir-partenaire', 'merci-partenaire',
        'merci-signalement', 'signaler-info', 'mentions-legales-loisirs74-phase1',
        'politique-confidentialite-loisirs74-phase1'}

GENERIQUE = {
    'lac': '/generique-lac.jpg', 'cascade': '/generique-cascade.jpg',
    'chateau': '/generique-chateau.jpg', 'musee': '/generique-musee.jpg',
    'point-de-vue': '/generique-point-de-vue.jpg', 'domaine': '/generique-domaine.jpg',
    'attraction': '/generique-attraction.jpg', 'parc': '/generique-parc.jpg',
    'telecabine': '/generique-telecabine.jpg',
}

CAMERA_SVG = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
              'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
              '<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>'
              '<circle cx="12" cy="13" r="4"/></svg>')

HERO_IMG_RE = re.compile(r'<img\b[^>]*\bfetchpriority="high"[^>]*>')
HERO_SVG_RE = re.compile(
    r'(<div class="hero-img">(?:\s*<div class="hero-badge">.*?</div>)?\s*)'
    r'<svg\b.*?</svg>(\s*</div>)', re.S)
HERO_CREDIT_RE = re.compile(r'<div class="hero-credit">.*?</div>', re.S)
CARD_RE = re.compile(r'(<a href="([^"]+)" class="card-photo">)(.*?)(</a>)', re.S)
IMG_RE = re.compile(r'<img\b[^>]*>')


def attr(tag, name):
    m = re.search(r'\b' + name + r'="([^"]*)"', tag)
    return m.group(1) if m else None


# ---------------------------------------------------------------- inventory
def place_slugs():
    return sorted(p.stem for p in ROOT.glob('*.html') if p.stem not in UTIL)


def categories():
    cat, name = {}, {}
    for l in json.load(open(ROOT / 'lieux.json', encoding='utf-8'))['lieux']:
        cat[l['slug']] = (l.get('categories') or ['domaine'])[0]
        fr = l.get('i18n', {}).get('fr', {})
        if fr.get('name'):
            name[l['slug']] = fr['name']
    for jf in glob.glob('Json/*.json'):
        try:
            d = json.load(open(jf, encoding='utf-8'))
        except json.JSONDecodeError:
            continue
        if d.get('slug'):
            cat.setdefault(d['slug'], d.get('category') or 'domaine')
            if d.get('name'):
                name.setdefault(d['slug'], d['name'])
    return cat, name


# ---------------------------------------------------------------- credits
def credit_div(text):
    return f'<div class="hero-credit">{CAMERA_SVG} {text}</div>'


def wikimedia_url(original_filename):
    fn = original_filename.replace(' ', '_')
    h = hashlib.md5(fn.encode('utf-8')).hexdigest()
    return (f'https://upload.wikimedia.org/wikipedia/commons/'
            f'{h[0]}/{h[0:2]}/{urllib.parse.quote(fn)}')


def zip_hero(slug):
    """(wikimedia_src_or_None, hero_credit_div_or_None) from the old snapshot."""
    p = ZIP / f'{slug}.html'
    if not p.exists():
        return None, None
    t = p.read_text(encoding='utf-8', errors='replace')
    src = None
    m = HERO_IMG_RE.search(t)
    if m:
        s = attr(m.group(0), 'src')
        if s and 'upload.wikimedia.org' in s:
            src = s
    cm = HERO_CREDIT_RE.search(t)
    return src, (cm.group(0) if cm else None)


# ---------------------------------------------------------------- resolve
def resolve(slugs, cat):
    pc = json.load(open(ROOT / 'photo-credits.json', encoding='utf-8'))
    R = {}
    for s in slugs:
        wiki, credit = zip_hero(s)
        if (ROOT / f'{s}-hero.jpg').exists():                       # tier 1
            R[s] = {'tier': 'root', 'src': f'/{s}-hero.jpg', 'credit': credit}
            continue
        if not wiki and s in pc:                                    # tier 2 fallback
            of = pc[s].get('hero', {}).get('original_filename')
            if of:
                wiki = wikimedia_url(of)
            cl = pc[s].get('hero', {}).get('credit_line')
            if cl and not credit:
                credit = credit_div(cl)
        if wiki:                                                    # tier 2
            R[s] = {'tier': 'wiki', 'src': wiki, 'credit': credit}
            continue
        c = cat.get(s, 'domaine')                                   # tier 3
        R[s] = {'tier': 'gen', 'src': GENERIQUE.get(c, GENERIQUE['domaine']), 'cat': c}
    return R


# ---------------------------------------------------------------- builders
def build_img(res, alt, hero, w='1600', h='1200'):
    a = [f'src="{res["src"]}"', f'alt="{alt}"']
    a += [f'width="{w}"', f'height="{h}"', 'fetchpriority="high"'] if hero else ['loading="lazy"']
    if res['tier'] == 'wiki':
        a.append('referrerpolicy="no-referrer"')
    if res['tier'] == 'gen':
        a += ['data-generique="true"', f'data-generique-cat="{res["cat"]}"']
    return '<img ' + ' '.join(a) + '>'


# ---------------------------------------------------------------- hero
def rewrite_hero(text, slug, R, names):
    res = R.get(slug)
    if not res:
        return text
    m = HERO_IMG_RE.search(text)
    if m:
        old = m.group(0)
        alt = attr(old, 'alt') or names.get(slug, slug)
        w = attr(old, 'width') or '1600'
        h = attr(old, 'height') or '1200'
        text = text[:m.start()] + build_img(res, alt, True, w, h) + text[m.end():]
    else:
        sm = HERO_SVG_RE.search(text)
        if not sm:
            return text
        alt = names.get(slug, slug)
        new = sm.group(1) + build_img(res, alt, True) + sm.group(2)
        text = text[:sm.start()] + new + text[sm.end():]
    return fix_hero_credit(text, res)


def fix_hero_credit(text, res):
    m = HERO_IMG_RE.search(text)
    if not m:
        return text
    close = text.find('</div>', m.end())
    if close == -1:
        return text
    after = close + len('</div>')
    mc = re.match(r'\s*<div class="hero-credit">.*?</div>', text[after:], re.S)
    existing = mc.group(0) if mc else None
    if res['tier'] == 'gen':
        desired = ''
    elif res.get('credit'):
        desired = res['credit']
    else:
        return text                                  # real photo, unknown credit: leave as is
    if existing is not None:
        return text[:after] + desired + text[after + len(existing):]
    if desired:
        return text[:after] + desired + text[after:]
    return text


# ---------------------------------------------------------------- cards
def rewrite_cards(text, R, alts):
    def repl(m):
        slug = m.group(2).rstrip('/').split('/')[-1]
        res = R.get(slug)
        if not res:
            return m.group(0)
        inner = m.group(3)
        im = IMG_RE.search(inner)
        if not im:
            return m.group(0)
        old = im.group(0)
        alt = attr(old, 'alt')
        if not alt or ('data-generique' in old and res['tier'] != 'gen'):
            alt = alts.get(slug) or alt or slug
        new = build_img(res, alt, False)
        return m.group(1) + inner[:im.start()] + new + inner[im.end():] + m.group(4)
    return CARD_RE.sub(repl, text)


# ---------------------------------------------------------------- main
def main():
    slugs = place_slugs()
    cat, names = categories()
    R = resolve(slugs, cat)
    tiers = {'root': 0, 'wiki': 0, 'gen': 0}
    for s in slugs:
        tiers[R[s]['tier']] += 1
    print(f'Resolved {len(slugs)} places — root:{tiers["root"]} '
          f'wiki:{tiers["wiki"]} generique:{tiers["gen"]}')

    # descriptive alt per place = its root page hero alt
    alts = {}
    for s in slugs:
        p = ROOT / f'{s}.html'
        if p.exists():
            m = HERO_IMG_RE.search(p.read_text(encoding='utf-8'))
            if m:
                alts[s] = attr(m.group(0), 'alt')

    slugset = set(slugs)
    n_hero = n_cards = 0
    for path in sorted(ROOT.rglob('*.html')):
        if path.name == 'studio.html' or any(p == 'node_modules' for p in path.parts):
            continue
        text = original = path.read_text(encoding='utf-8')
        if path.name != 'index.html' and path.stem in slugset:
            text = rewrite_hero(text, path.stem, R, names)
            if text != original:
                n_hero += 1
        before_cards = text
        text = rewrite_cards(text, R, alts)
        if text != before_cards:
            n_cards += 1
        if text != original:
            path.write_text(text, encoding='utf-8')
    print(f'Hero blocks rewritten:  {n_hero}')
    print(f'Files with cards fixed: {n_cards}')

    # data layer: Json/<slug>.json hero_image
    n_json = 0
    for s in slugs:
        jp = ROOT / f'Json/{s}.json'
        if not jp.exists():
            continue
        d = json.loads(jp.read_text(encoding='utf-8'))
        if d.get('hero_image') != R[s]['src']:
            d['hero_image'] = R[s]['src']
            jp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            n_json += 1
    print(f'Json/ hero_image updated: {n_json}')
    print('\nDone.')


if __name__ == '__main__':
    main()
