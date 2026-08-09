#!/usr/bin/env python3
"""
merge-duplicates.py — Loisirs 74
================================
Merge 3 duplicate place pages, keeping the fresher copy each time:

    cascade-d-arpenaz   -> cascade-de-l-arpenaz
    plaine-de-joux      -> aire-de-decollage-parapente-plaine-joux
    lac-vert            -> lac-vert-passy

For every merge it: deletes the dead page (all locales) + its Json/content,
repoints inbound links, collapses the now-duplicate cards / JSON-LD list
items / map pins, removes self-referencing cards, drops the dead slug from
the data files, appends 301 redirects, and fixes llms*.txt.

Idempotent: re-running on an already-merged tree is a no-op.
"""

import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).parent
LOCALES = ['de', 'en', 'es', 'it']

# (dead slug, keeper slug, locales where the dead .html exists incl. '' for root)
MERGES = [
    ('lac-des-ilettes', 'base-de-loisirs-des-ilettes', [''] + LOCALES),
]
DEAD = {d: k for d, k, _ in MERGES}          # dead -> keeper
KEEPERS = set(DEAD.values())

# Image files belonging to a dead slug.
IMG_RENAME = {}
IMG_DELETE = []

DEAD_FILES = set()
for d, _, locs in MERGES:
    for loc in locs:
        DEAD_FILES.add((ROOT / (f'{d}.html' if loc == '' else f'{loc}/{d}.html')).resolve())


# ---------------------------------------------------------------- JSON-LD
def _clean_jsonld(obj):
    """Drop ListItems whose item.url ends in a dead slug; renumber positions."""
    changed = False
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            obj[k], c = _clean_jsonld(v)
            changed |= c
        return obj, changed
    if isinstance(obj, list):
        is_list = any(isinstance(x, dict) and x.get('@type') == 'ListItem' for x in obj)
        new = []
        for x in obj:
            x, c = _clean_jsonld(x)
            changed |= c
            if isinstance(x, dict) and x.get('@type') == 'ListItem':
                item = x.get('item')
                url = item.get('url', '') if isinstance(item, dict) else ''
                if any(url.rstrip('/').endswith('/' + d) for d in DEAD):
                    changed = True
                    continue
            new.append(x)
        if is_list:
            pos = 1
            for x in new:
                if isinstance(x, dict) and x.get('@type') == 'ListItem' and 'position' in x:
                    if x['position'] != pos:
                        changed = True
                    x['position'] = pos
                    pos += 1
        return new, changed
    return obj, changed


JSONLD_RE = re.compile(r'(<script type="application/ld\+json">)(.*?)(</script>)', re.S)


def clean_jsonld(text):
    def repl(m):
        try:
            obj = json.loads(m.group(2))
        except json.JSONDecodeError:
            return m.group(0)
        new, changed = _clean_jsonld(obj)
        if not changed:
            return m.group(0)
        return m.group(1) + json.dumps(new, ensure_ascii=False, indent=2) + m.group(3)
    return JSONLD_RE.sub(repl, text)


# ---------------------------------------------------------------- PINS
PINS_RE = re.compile(r'(const PINS\s*=\s*)(\[.*?\])(\s*;)', re.S)


def clean_pins(text):
    def repl(m):
        try:
            arr = json.loads(m.group(2))
        except json.JSONDecodeError:
            return m.group(0)
        new = [p for p in arr
               if p.get('slug') not in DEAD
               and not any(str(p.get('url', '')).rstrip('/').endswith('/' + d) for d in DEAD)]
        if len(new) == len(arr):
            return m.group(0)
        return m.group(1) + json.dumps(new, ensure_ascii=False, separators=(',', ':')) + m.group(3)
    return PINS_RE.sub(repl, text)


# ---------------------------------------------------------------- repoint
def repoint_urls(text):
    """Rewrite /<dead> path segments (href, JSON-LD url, etc.) to the keeper."""
    for dead, keeper in DEAD.items():
        text = re.sub(r'(/)' + re.escape(dead) + r'(?=["/?#<]|\.md)', r'\1' + keeper, text)
    return text


def repoint_images(text):
    for old, new in IMG_RENAME.items():
        text = text.replace(old, new)
    return text


# ---------------------------------------------------------------- cards
CARD_RE = re.compile(r'<article class="card">.*?</article>', re.S)
CARD_HREF_RE = re.compile(r'<a\s+href="([^"]+)"\s+class="card-photo"')


def card_slug(card):
    m = CARD_HREF_RE.search(card)
    return m.group(1).rstrip('/').split('/')[-1] if m else None


def collapse_cards(text, path):
    """Drop duplicate keeper cards (keep first) and self-referencing cards."""
    own = path.stem if path.name != 'index.html' else None
    seen, out, last = set(), [], 0
    for m in CARD_RE.finditer(text):
        slug = card_slug(m.group(0))
        drop = False
        if slug in KEEPERS:
            if slug in seen:
                drop = True
            seen.add(slug)
        if own in KEEPERS and slug == own:
            drop = True
        if drop:
            out.append(text[last:m.start()])
            last = m.end()
            while last < len(text) and text[last] in ' \t\r\n':
                last += 1
    out.append(text[last:])
    return ''.join(out)


# ---------------------------------------------------------------- per file
def process_html(path):
    original = path.read_text(encoding='utf-8')
    text = clean_jsonld(original)
    text = clean_pins(text)
    text = repoint_urls(text)
    text = repoint_images(text)
    text = collapse_cards(text, path)
    if text != original:
        path.write_text(text, encoding='utf-8')
        return True
    return False


# ---------------------------------------------------------------- data files
def edit_lieux(rel):
    p = ROOT / rel
    d = json.loads(p.read_text(encoding='utf-8'))
    before = len(d['lieux'])
    d['lieux'] = [l for l in d['lieux'] if l.get('slug') not in DEAD]
    removed = before - len(d['lieux'])
    meta = d.get('metadata')
    if isinstance(meta, dict):
        for k in ('count', 'total', 'total_lieux', 'lieux_count'):
            if isinstance(meta.get(k), int):
                meta[k] = len(d['lieux'])
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return removed


def edit_sitemap():
    p = ROOT / 'sitemap.xml'
    text = p.read_text(encoding='utf-8')
    def drop(m):
        block = m.group(0)
        if any(re.search(r'/' + re.escape(d) + r'(?=["<])', block) for d in DEAD):
            return ''
        return block
    new = re.sub(r'\s*<url>(?:(?!</url>).)*?</url>', drop, text, flags=re.S)
    if new != text:
        p.write_text(new, encoding='utf-8')
        return True
    return False


def append_redirects():
    p = ROOT / '_redirects'
    text = p.read_text(encoding='utf-8')
    lines = []
    for dead, keeper, locs in MERGES:
        for loc in locs:
            pre = '' if loc == '' else f'/{loc}'
            src, dst = f'{pre}/{dead}', f'{pre}/{keeper}'
            if re.search(r'^' + re.escape(src) + r'\s', text, re.M):
                continue
            lines.append(f'{src:<48}{dst:<58}301')
    if not lines:
        return 0
    block = '\n# Merged duplicate pages -> canonical\n' + '\n'.join(lines) + '\n'
    p.write_text(text.rstrip('\n') + '\n' + block, encoding='utf-8')
    return len(lines)


def fix_llms():
    p = ROOT / 'llms.txt'
    lines = p.read_text(encoding='utf-8').splitlines(keepends=True)
    keeper_present = {k: any(f'/content/{k}.md' in l for l in lines) for k in KEEPERS}
    out, dropped = [], 0
    for l in lines:
        drop = False
        for dead, keeper in DEAD.items():
            if f'/content/{dead}.md' in l:
                if keeper_present.get(keeper):
                    drop = True
                else:
                    l = l.replace(f'/content/{dead}.md', f'/content/{keeper}.md')
        if drop:
            dropped += 1
        else:
            out.append(l)
    p.write_text(''.join(out), encoding='utf-8')

    pf = ROOT / 'llms-full.txt'
    t = pf.read_text(encoding='utf-8')
    nt = repoint_urls(t)
    if nt != t:
        pf.write_text(nt, encoding='utf-8')
    return dropped


def carry_lac_vert_gallery():
    """Copy lac-vert's gallery photo credits onto the keeper, with renamed files."""
    src = ROOT / 'Json/lac-vert.json'
    dst = ROOT / 'Json/lac-vert-passy.json'
    if not src.exists() or not dst.exists():
        return
    sd = json.loads(src.read_text(encoding='utf-8'))
    dd = json.loads(dst.read_text(encoding='utf-8'))
    gallery = []
    for ph in sd.get('gallery_photos') or []:
        ph = dict(ph)
        if 'src' in ph:
            ph['src'] = ph['src'].replace('lac-vert-', 'lac-vert-passy-')
        gallery.append(ph)
    if gallery:
        dd['gallery_photos'] = gallery
    dd['hero_image'] = '/lac-vert-passy-hero.jpg'
    dst.write_text(json.dumps(dd, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


# ---------------------------------------------------------------- main
def main():
    print('== merge-duplicates ==')
    for d, k, _ in MERGES:
        print(f'  {d}  ->  {k}')
    print()

    # 1. carry photo credits before anything is deleted
    carry_lac_vert_gallery()

    # 2. rewrite every surviving HTML file
    n_files = 0
    for path in sorted(ROOT.rglob('*.html')):
        if path.resolve() in DEAD_FILES:
            continue
        if path.name == 'studio.html' or any(part == 'node_modules' for part in path.parts):
            continue
        if process_html(path):
            n_files += 1
    print(f'HTML files rewritten:      {n_files}')

    # 3. data files
    for rel in ('lieux.json', 'api/lieux.json'):
        if (ROOT / rel).exists():
            print(f'{rel}: removed {edit_lieux(rel)} lieu(x)')
    print(f'sitemap.xml changed:       {edit_sitemap()}')
    print(f'_redirects lines added:    {append_redirects()}')
    print(f'llms.txt lines dropped:    {fix_llms()}')

    # 4. filesystem: rename / delete images
    for old, new in IMG_RENAME.items():
        op, np = ROOT / old, ROOT / new
        if op.exists():
            os.rename(op, np)
            print(f'  renamed image  {old} -> {new}')
    for img in IMG_DELETE:
        ip = ROOT / img
        if ip.exists():
            ip.unlink()
            print(f'  deleted image  {img}')

    # 5. filesystem: delete dead pages + data
    for dead, _, locs in MERGES:
        for loc in locs:
            fp = ROOT / (f'{dead}.html' if loc == '' else f'{loc}/{dead}.html')
            if fp.exists():
                fp.unlink()
                print(f'  deleted page   {fp.relative_to(ROOT)}')
        for rel in (f'Json/{dead}.json', f'content/{dead}.md'):
            fp = ROOT / rel
            if fp.exists():
                fp.unlink()
                print(f'  deleted data   {rel}')

    print('\nDone.')


if __name__ == '__main__':
    main()
