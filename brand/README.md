# Loisirs 73 — brand

Sibling of [loisirs74.fr](https://loisirs74.fr), not a clone. Same family
grammar — rounded square, alpine silhouette, compass, water — with Savoie's
own colour and emblem.

## Sources of truth

| File | What it is |
|---|---|
| `logo.svg` | the full logo. Three summits (Vanoise / Trois Vallées), Lac du Bourget, compass rose in crimson-and-white. **Use at ≥64 px.** |
| `mark.svg` | the small mark. One bold peak + the croix de Savoie. Everything that cannot survive 16 px is removed. **Favicons, touch icons, and any header logo under ~48 px** — the full logo goes mushy there. |
| `og-image.svg` | the 1200×630 social card. |
| `theme.css` | the design tokens. |

Every raster in the repo root — `logo.png`, `favicon*.png`, `favicon.ico`,
`apple-touch-icon.png`, `android-chrome-*.png`, `mark.png`, `og-image.jpg` — is
**derived**:

```bash
python3 scripts/build_brand.py     # needs cairosvg + pillow
```

Edit an SVG, re-run, commit both. Never hand-edit a PNG — same law as the rest
of the engine.

## Why it looks like this

**The compass stays, the colour moves.** The 74's compass rose is the shared
promise: this is a guide, it helps you navigate. Keeping the silhouette keeps
the family. Recolouring it crimson-and-white makes it Savoie's — and a compass
rose's four cardinal points already draw a cross, so the *croix de Savoie* is
sitting there without having to be bolted on.

**Three summits, not one massif.** Haute-Savoie's logo is one broad Mont-Blanc
massif above a lake. Savoie's leisure map concentrates in the Trois Vallées and
the Vanoise, so the 73 carries three summits. The peaks are deliberately broad-
shouldered: a narrow peak turns any snowline into flames at small sizes.

**A real lake band.** Lac du Bourget is the largest natural lake in France. It
gets more of the frame than the 74's thin water lines.

## Palette

Neutrals are the 74's, unchanged — that is the family DNA and it makes the
engine transplant a drop-in. Only the accent family differs.

| Token | Light | Dark | Contrast on bg |
|---|---|---|---|
| `--accent` | `#0b5170` glacier blue | `#7ad9f5` ice | 8.28 / 12.11 |
| `--accent-2` | `#06344a` | `#a8e8fa` | 12.57 / 14.44 |
| `--savoie` | `#C8102E` | `#E8455E` | 5.63 / 5.04 |
| `--brand-ground` | `#15496a` (logo field, both modes) | | |

*(For comparison, the 74's accent pair measures 7.92 / 13.59 — the 73 was tuned
to the same visual weight on purpose, not picked by eye.)*

Every pair clears WCAG AA; most clear AAA. The numbers are in `theme.css`, and
they were measured, not guessed.

### The one rule about crimson

`--savoie` is an **identity** colour: the logo cross, an occasional small mark.
Never body text, never a large surface, never a button fill. Crimson at scale
reads as an error state, and it fails AA on the dark background at its light-mode
value (3.31:1) — which is why the dark mode lifts it to `#E8455E`.

## Known refinements

- The social card renders with whatever sans-serif the build machine has. The
  74's display face is Bricolage Grotesque; embedding it in `og-image.svg`
  before launch would tighten the family.
- No wordmark lockup yet (the 74 has `logo-full.png`). Add one when there is a
  header to put it in.

*2026 · Bleu canard édition · Edmaster & Claudius · Tous droits réservés* 🦆
