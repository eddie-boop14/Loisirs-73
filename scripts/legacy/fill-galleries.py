#!/usr/bin/env python3
"""
fill-galleries.py — Loisirs 74
==============================
Populate the empty photo galleries on "v2" template place pages. Those
pages carry a 6-tile grid of `<div class="tile placeholder">` even when
real gallery photos (`<slug>-N.jpg`) exist at the repo root. This script
swaps the placeholders for the real photos, with a credit overlay where
attribution is known (from Json/<slug>.json or photo-credits.json).

Only touches galleries that are still empty; v1 and bleu-canard galleries
(already filled) are left alone. Idempotent.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).parent
LOCALES = ['de', 'en', 'es', 'it']

CREDIT_STYLE = (
    "position:absolute;left:0;right:0;bottom:0;margin:0;"
    "font-size:.58rem;line-height:1.35;padding:.25rem .45rem;"
    "background:rgba(13,26,15,.82);color:#f0dfc0;"
    "backdrop-filter:blur(3px);-webkit-backdrop-filter:blur(3px)"
)

PLACEHOLDER_RE = re.compile(r'<div class="tile placeholder">.*?</div>', re.S)
H1_RE = re.compile(r'<h1[^>]*>(.*?)</h1>', re.S)


def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def gallery_photos(slug):
    return sorted(p.name for p in ROOT.glob(f'{slug}-[1-9].jpg'))


def credit_map(slug):
    """filename -> credit text, from photo-credits.json + Json/<slug>.json."""
    m = {}
    pc = json.loads((ROOT / 'photo-credits.json').read_text(encoding='utf-8'))
    if slug in pc:
        for v in pc[slug].values():
            if isinstance(v, dict) and v.get('filename') and v.get('credit_line'):
                m[v['filename']] = re.sub(r'^Photo:\s*', '', v['credit_line']).strip()
    jp = ROOT / f'Json/{slug}.json'
    if jp.exists():
        d = json.loads(jp.read_text(encoding='utf-8'))
        for ph in d.get('gallery_photos') or []:
            if ph.get('src') and ph.get('credit'):
                m[ph['src']] = ph['credit']
    return m


def place_name(text, slug):
    mm = H1_RE.search(text)
    if mm:
        n = re.sub(r'<[^>]+>', '', mm.group(1)).strip()
        if n:
            return n
    return slug.replace('-', ' ').title()


def filled_tile(photo, alt, credit):
    img = (f'<img src="/{photo}" alt="{esc(alt)}" loading="lazy" '
           f'width="600" height="600">')
    span = ''
    if credit:
        span = (f'<span class="tile-credit" style="{CREDIT_STYLE}">'
                f'\U0001F4F7 {esc(credit)}</span>')
    return f'<div class="tile">{img}{span}</div>'


def main():
    slugs = sorted({p.name.rsplit('-', 1)[0] for p in ROOT.glob('*-[1-9].jpg')})
    n_files = n_photos = 0
    for slug in slugs:
        photos = gallery_photos(slug)
        if not photos:
            continue
        cmap = credit_map(slug)
        for loc in [''] + LOCALES:
            fp = ROOT / (f'{slug}.html' if loc == '' else f'{loc}/{slug}.html')
            if not fp.exists():
                continue
            text = fp.read_text(encoding='utf-8')
            if '<div class="tile placeholder">' not in text:
                continue
            if re.search(r'<div class="tile"><img src="/' + re.escape(slug) + r'-\d', text):
                continue                                   # already filled
            name = place_name(text, slug)
            out, last, i = [], 0, 0
            for m in PLACEHOLDER_RE.finditer(text):
                if i >= len(photos):
                    break
                out.append(text[last:m.start()])
                out.append(filled_tile(photos[i], name, cmap.get(photos[i])))
                last = m.end()
                i += 1
            out.append(text[last:])
            fp.write_text(''.join(out), encoding='utf-8')
            n_files += 1
            n_photos += i
    print(f'Galleries filled: {n_files} files, {n_photos} photos placed')


if __name__ == '__main__':
    main()
