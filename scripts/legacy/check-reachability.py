#!/usr/bin/env python3
"""BFS-reachability check from index.html in each language tree."""
import re, os
from collections import deque

ROOT = '.'
HUB_DIRS_BY_LANG = {
    '':    ['attractions','bases-de-loisirs','cascades','chateaux','lacs','musees',
            'plages','points-de-vue','sentiers','telecabines','voies-vertes','que-faire','divers'],
    'de/': ['attraktionen','aussichtspunkte','freizeitparks','museen','que-faire','radwege',
            'schloesser','seen','seilbahnen','sonstiges','straende','wanderwege','wasserfaelle'],
    'en/': ['attractions','beaches','cable-cars','castles','greenways','lakes','leisure-parks',
            'museums','other','que-faire','trails','viewpoints','waterfalls'],
    'es/': ['areas-de-ocio','atraciones','cascadas','castillos','lagos','miradores','museos',
            'otros','playas','que-faire','senderos','telefericos','vias-verdes'],
    'it/': ['altro','aree-recreative','attrazioni','cascate','castelli','funivie','laghi',
            'musei','punti-panoramici','que-faire','sentieri','spiagge','vie-verdi'],
}
EXCLUDE = {'index','404','cgv','signaler-info','devenir-partenaire','merci-partenaire',
           'merci-signalement','mentions-legales-loisirs74-phase1','studio',
           'politique-confidentialite-loisirs74-phase1'}


def norm(s):
    s = s.strip('/')
    s = re.sub(r'\.html$', '', s)
    return s or 'index'


ALL_LANGS = ('/de/', '/en/', '/es/', '/it/')


def links(path, prefix=''):
    h = open(path, encoding='utf-8', errors='ignore').read()
    out = set()
    cur_lang = '/' + prefix if prefix else ''
    skip_langs = tuple(p for p in ALL_LANGS if p != cur_lang)
    for href in re.findall(r'href=["\']([^"\']+)["\']', h):
        m = re.match(r'(?:https?://(?:www\.)?loisirs74\.fr)?(/[^"\']*)', href)
        if not m:
            continue
        p = m.group(1).split('#')[0].split('?')[0]
        if p.startswith(skip_langs + ('/api/', '/content/', '/scripts/')):
            continue
        if cur_lang and p.startswith(cur_lang):
            p = p[len(cur_lang) - 1:]
        out.add(norm(p))
    return out


def run(prefix=''):
    base = os.path.join(ROOT, prefix) if prefix else ROOT
    hub_dirs = HUB_DIRS_BY_LANG[prefix]
    nodes = set(norm(f) for f in os.listdir(base) if f.endswith('.html'))
    for d in hub_dirs:
        if os.path.exists(os.path.join(base, d, 'index.html')):
            nodes.add(d)

    def file_for(n):
        if n == 'index':
            return os.path.join(base, 'index.html')
        if n in hub_dirs:
            return os.path.join(base, n, 'index.html')
        f = os.path.join(base, n + '.html')
        return f if os.path.exists(f) else None

    seen = set()
    q = deque(['index'])
    while q:
        n = q.popleft()
        if n in seen:
            continue
        seen.add(n)
        f = file_for(n)
        if not f or not os.path.exists(f):
            continue
        for t in links(f, prefix):
            if t in nodes and t not in seen:
                q.append(t)
    content = nodes - EXCLUDE
    orphans = content - seen
    print(f"[{prefix or 'FR'}] content={len(content)} reachable={len(content & seen)} orphans={len(orphans)}")
    for o in sorted(orphans):
        print("   ORPHAN:", o)
    return len(orphans)


if __name__ == '__main__':
    total = 0
    for p in ['', 'de/', 'en/', 'es/', 'it/']:
        total += run(p)
    print(f"\nTOTAL ORPHANS: {total}")
