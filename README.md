# Loisirs 73

An independent leisure guide for **Savoie**, France — the second département built
on the Loisirs engine. Sister site of [loisirs74.fr](https://loisirs74.fr)
(Haute-Savoie), and cross-linked with it both ways.

🌐 **[loisirs73.fr](https://loisirs73.fr) — live.**

---

## Status: launched and growing

| Piece | State |
|---|---|
| Site | ✅ live on Netlify, indexed, ~1 100 static pages |
| Fiches (`Json/`) | ✅ **113 published lieux**, every one verified against official sources |
| Languages | ✅ 6 — fr · en · de · it · es · nl, full coverage, zero fallback |
| Category hubs | ✅ 10 — points de vue 15 · lacs 15 · télécabines 15 · cascades 12 · musées 12 · châteaux 12 · plages 12 · sentiers 12 · bases de loisirs · voies vertes |
| Intent pages | ✅ 5 — où se baigner, cascades & gorges, quand il pleut, sorties famille, cols de Savoie |
| Commune pages | ✅ one per commune with published places |
| CI | ✅ `build-gate.yml` — the full 33-gate battery + byte-stable double build on every push |
| Photos | 🚧 generic heroes on most fiches; the 30 cols/lifts carry real photos — see `reports/PHOTOS-WIKIMEDIA.md` for the fetch list |

---

## The rule everything else follows

Same law as the 74: **JSON is the source of truth.** Every page, hub, sitemap and
machine surface is *derived* from `Json/<slug>.json` by the Python pipeline
(`scripts/build_all.py`). Nothing in a rendered page is written by hand — a wrong
comma is fixed at the source and re-rendered, never patched in the HTML. Two
consecutive builds must be byte-identical; CI checks it.

And the honesty rule that makes the guide worth citing: if a fact cannot be
verified against an official source, it stays `null` and is flagged. **When two
official sources contradict each other, the page quotes both instead of picking
one** — supervision dates, lake surfaces, difficulty ratings, even a swimming
ban one mairie tolerates and one tourist office forbids. Never guessed, never
inferred, never taken from a reseller.

Working rules learned the hard way, now house law:
- **French official pages only** — the English twins of tourist-office fiches
  run a year late or scramble their own figures.
- Bathing-water quality is cited from the **department-level ARS listing** only;
  per-site URLs return soft errors.
- Proper names stay **frozen French** in every language — a German reader
  searches « Plage du Sougey », not "Le Sougey beach".

Tripadvisor, GetYourGuide, Visorando and blogs are not valid sources and never
enter the corpus.

---

## How content gets made

1. **Research** — parallel agents against official sources (offices de tourisme,
   mairies, préfecture, ARS, EDF, fishing federation, national registers like
   Mérimée and the DRAC Musée-de-France list), quotes captured verbatim, every
   URL logged in the fiche's `research_log`.
2. **Author** — FR + EN written by the editor; the four other locales come from
   the **$0 machine-translation lane** (offline argos, frozen-noun masking,
   sentence-splitting, digit-parity checks, English fallback on any flagged
   segment) — no per-word translation billing.
3. **Gate** — 33 gates: schema, vocabulary, duplicate/centroid, canonical,
   phantom-slash, i18n-leak, hero integrity, winter rules, link integrity,
   reachability, byte-stability… red blocks the deploy.
4. **Ship** — Netlify redeploys from `main`; sitemap, hreflang, JSON-LD, the
   API mirror (`api/`) and the AI discovery layer (`llms.txt`, per-lieu
   markdown) all regenerate with the build.

`PROJECT-STATE.md` is regenerated on every build and is the machine-readable
status of record.

---

## For a new département

`site.config.json` carries the whole per-site identity — name, domain, dept,
sister-site block (count + top picks on the homepage card), hub roster
(`data/hub-titles.json`). The engine is the same as the 74's; a new category is
one roster line plus a hub shell. `scripts/extract_dt_dept.py --dept XX` builds
the DATAtourisme candidate queue for any département.

---

## License

Source-available, not open source: read and learn freely; redeploying the engine,
republishing the editorial corpus, or reusing photos needs written permission —
see [LICENSE.md](LICENSE.md). The facts about public places belong to everyone;
the machine that serves them belongs to us. 🦆

*2026 · Bleu canard édition · Edmaster & Claudius · Tous droits réservés*
