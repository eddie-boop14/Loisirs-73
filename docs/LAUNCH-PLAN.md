# Loisirs 73 — launch plan

*Written 2026-08-05 · Edmaster & Claudius · revised against the real Savoie data,
not against the 74's habits.*

---

## The one decision the data already made for us

The 74 launched lake-first, because Haute-Savoie's leisure data spreads across
Annecy, the Léman and the valleys. **Savoie does not spread — it concentrates.**

From the DATAtourisme queue (3 114 POI across 225 communes), the top of the
distribution is:

| Commune | POI | |
|---|---:|---|
| 73550 Les Allues | 187 | Méribel |
| 73120 Courchevel | 140 | |
| 73440 Les Belleville | 131 | Val Thorens / Les Menuires |
| 73000 Chambéry | 75 | the *préfecture*, fourth |

Three Trois Vallées communes hold **458 of 3 114 — 14.7 % of the entire
département's queue** — and all three sit ahead of the capital. That is not a
quirk of the export; it is what Savoie tourism *is*.

*(Counts are post-deduplication. Worth knowing: 47 of the 84 duplicate source
rows came from those same three communes — the big resorts are also where
DATAtourisme's own records double up hardest. The pre-dedup figures were
204/160/141 and 15.8 %; the thesis survives the correction, slightly smaller.)*

**So: Loisirs 73 launches ski-domain-first.** Lakes (Bourget, Aiguebelette) are
the second wave, not the opening. Anyone copying the 74's playbook verbatim would
open on the department's weakest axis.

### Two consequences worth acting on

1. **The tarif watcher moves from "later" to day-one.** `watch_sources.py` (built
   for the 74, detection-only, never writes a fiche) is aimed at station tarif
   pages. The 74's highest-converting queries are already the verified-fact kind
   — `bowling annecy tarif` runs **16.9 % CTR at position 3.3**. On a
   ski-concentrated département that query class *is* the department. The Savoie
   stations go into the watcher's source list from the first render, not as an
   afterthought, and September is the tarif season.
2. **Altitude transport leads the fiche mix.** On the 74, `/en/telepherique-du-brevent`
   and `/en/tramway-du-mont-blanc` are the two most AI-cited pages of the whole
   site. Savoie's equivalent inventory (Vanoise Express, Saulire, Cime Caron,
   the Tarentaise and Maurienne lifts, the great cols — Iseran, Galibier,
   Madeleine) is deeper than the 74's, and nobody serves it as verified facts.

---

## Launch scope — the first ~80 fiches

Weighted by the above, FR + EN only at first (the 74's data is unambiguous: the
English pages out-cite the French ones, and the other ten languages are worth
adding only once the catalogue is mature).

| Bucket | Fiches | Notes |
|---|---:|---|
| Ski-domain infrastructure | ~30 | lifts, cable cars, altitude viewpoints, cols, station facts + tarifs |
| Lakes & swimming | ~20 | Bourget (largest natural lake in France), Aiguebelette, Aix beaches |
| Heritage | ~15 | Château des ducs de Savoie, Conflans, thermes d'Aix, museums |
| Trails & greenways | ~15 | Bourget loop, Vanoise approaches, the 73 stretch of the GR5 |

Plus, derived automatically once fiches exist: ~10 commune hubs (Chambéry,
Aix-les-Bains, Albertville, Le Bourget-du-Lac, Moûtiers, Bourg-Saint-Maurice,
Val-d'Isère, Courchevel, Saint-Jean-de-Maurienne, Les Allues) and 8 category hubs.

**Volume rationale:** the 74 opened at ~46 published fiches and Google followed.
80 is a deliberate step up, not a stretch — the ceiling is photos, not facts.

---

## Sequence, and what blocks what

1. **Ingest queue** — `python3 scripts/extract_dt_dept.py --dept 73`.
   *Blocked on: nothing.* One command, ~3 minutes.
2. **Engine transplant** — the `scripts/` pipeline, gates and Studio from the 74.
   *Blocked on:* the 74's **config phase 2**. Phase 1 (`site.config.json` +
   `scripts/siteconfig.py`, proven byte-identical over 10 767 rendered files) is
   done and awaiting merge on the 74. Phase 2 moves the still-74-authored content
   out of engine code: `build_hubs.py`'s ~99 per-language hub titles/metas, the
   intent-registry defaults, the commune sets. Until that lands, a copied engine
   would render "Haute-Savoie" across the Savoie site. **This is the real gate —
   do not fork the engine before it.**
3. **Content** — ~80 fiches through Studio, facts + credited hero photo each.
   *Blocked on: 2.* This is the long pole and the only genuinely manual work.
4. **Go live** — point `loisirs73.fr` at the Netlify project, flip `robots.txt`
   and remove the holding page's `noindex`, submit the sitemap to GSC + Bing,
   create the site's **own** Cloudflare Web Analytics property and paste its token
   into `site.config.json` (`cf_beacon_token` is deliberately empty until then —
   never share the 74's).

---

## Carried over from the 74 without re-litigation

These were paid for once. They apply here from the first commit:

- **Slugs are immutable from day one.** Every rename becomes a redirect rule
  across *all* languages, generated in one pass — never discovered one 404 at a
  time. (The 74 spent a week on this.)
- **`llms.txt` and the AI surface ship published-only.** A draft fiche has no
  page, so advertising its canonical URL is advertising a 404. The 74's gates
  now enforce it; the transplant brings them along.
- **Hero photo before publish, never after.** Five terroir fiches sat unpublished
  on the 74 purely for want of a photo; publishing them without one would have
  404'd the hero on ~400 pages.
- **Watchers detect, humans apply.** No bot writes a fiche. Ever.
- **Frozen French place names in every language**, verbatim: Savoie, Lac du
  Bourget, Vanoise, Tarentaise, Maurienne, Mont-Cenis, GR®, and all commune names.

---

## Open questions for Edmaster

- **Partner model on the 73?** The 74 has protected partner cards with byte-diff
  gates. Savoie has no partners yet — start clean, or port the machinery unused?
- **Cross-linking 74 ⟷ 73.** The GR5, the Route des Grandes Alpes and the
  "30 minutes away" inter-department pairs are link equity no tourism office can
  replicate. Worth designing once, before either site accumulates ad-hoc links.

*2026 · Bleu canard édition · Edmaster & Claudius · Tous droits réservés* 🦆
