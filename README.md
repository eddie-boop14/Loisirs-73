# Loisirs 73

An independent leisure guide for **Savoie**, France — the second département built
on the Loisirs engine. Sister site of [loisirs74.fr](https://loisirs74.fr)
(Haute-Savoie, 434 places, 12 languages, ~6 100 static pages).

🌐 loisirs73.fr — **not live yet.**

---

## Status: foundation laid, no content

| Piece | State |
|---|---|
| Domain `loisirs73.fr` | bought, active until Aug 2027, **not pointed at Netlify yet** |
| Netlify project | connected to this repo, serving the holding page |
| `site.config.json` | ✅ written — the whole per-site identity |
| Engine (`scripts/`) | ❌ not transplanted — see `docs/LAUNCH-PLAN.md` |
| Fiches (`Json/`) | ❌ empty — 0 of a target ~80 to launch |
| Ingest queue (`data/`) | ❌ one command away, see below |
| Indexing | 🔒 blocked on purpose (`robots.txt` + `noindex`) until launch |

Nothing here renders a page yet. `netlify.toml` has **no build command** on
purpose: the repo root is published, which serves `index.html`, and that is all.

---

## The rule everything else will follow

Same law as the 74: **JSON is the source of truth.** Every page, hub, sitemap and
machine surface is *derived* from `Json/<slug>.json` by the Python pipeline.
Nothing in a rendered page is written by hand — a wrong comma is fixed at the
source and re-rendered, never patched in the HTML.

And the honesty rule that makes the guide worth citing: if a fact cannot be
verified against an official source, it stays `null` and is flagged. Never
guessed, never inferred, never taken from a reseller. A missing opening time is
a gap; a wrong one sends someone to a locked door.

Tripadvisor, GetYourGuide, Visorando and blogs are not valid sources and never
enter the corpus.

---

## Build the ingest queue (first real command)

`scripts/extract_dt_dept.py` downloads the daily DATAtourisme Auvergne-Rhône-Alpes
export (~45 MB, licence ouverte) and keeps the Savoie POI that carry a
leisure/heritage category:

```bash
python3 scripts/extract_dt_dept.py --dept 73
# -> data/dt-ara-73-candidates.json   (~3 100 candidates, ~2 MB)
```

Expect roughly 3 100 rows. That is a queue of **candidates**, not fiches:
nothing is published from it until it goes through Studio with verified facts
and a hero photo.

The filter (postcode prefix + `SportsAndLeisurePlace | CulturalSite | Tour |
NaturalHeritage`) is the one that produced the 74's queue — reverse-engineered
from that file and verified at 3012/3012, with a round-trip test that reproduces
the committed 74 rows exactly. The script also works for any future département:
`--dept 38`, `--dept 01`.

---

## What launch needs

Read `docs/LAUNCH-PLAN.md`. Short version: the engine transplant (blocked on the
74's config phase 2), then ~80 fiches in FR + EN, ski-domain-first — because the
Savoie data concentrates in the Trois Vallées, unlike the 74's lake-and-valley
spread.

---

## License

Source-available, not open source: read and learn freely; redeploying the engine,
republishing the editorial corpus, or reusing photos needs written permission —
see [LICENSE.md](LICENSE.md). The facts about public places belong to everyone;
the machine that serves them belongs to us. 🦆

*2026 · Bleu canard édition · Edmaster & Claudius · Tous droits réservés*
