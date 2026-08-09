#!/usr/bin/env python3
"""locales.py — the locale roster, derived (HANDOFF-10 Job 1 + HANDOFF-16 Phase 2).

One source (data/languages.json), two ORTHOGONAL axes — never conflated again:

  status      lifecycle / visibility: published · staged-indexable · staged · held
  render_mode HOW a language is rendered: prose (the 6, full translated prose via
              build_lieu_page/communes/hubs) vs facts (everything else — facts-first
              via build_fulltree_lang / build_pilot_langs, NO prose, EVER).

The forbidden move — a facts language rendered through the prose path with FR
fallback — is made STRUCTURALLY IMPOSSIBLE: the prose builders iterate PROSE only,
and PROSE excludes every facts language by construction. There is no roster a
prose render loop can read that contains a facts language.

Derived rosters (declared order preserved):
  PROSE             published ∧ render_mode==prose  — the ONLY langs the prose path
                    may render (fr,en,de,it,es,nl). build_lieu_page/communes/hubs/
                    intent-hubs/catalog/reachability/prose-gates consume these.
  PROSE_SECONDARY   PROSE minus the root locale (en,de,it,es,nl).
  VISIBLE           status==published — appears to users + search: the language
                    picker, hreflang clusters, and the sitemap. Spans BOTH render
                    modes (fr..nl + pl). Picker/hreflang/sitemap consume these.
  VISIBLE_SECONDARY VISIBLE minus root (en,de,it,es,nl,pl).
  FACTS_PUBLISHED   published ∧ render_mode==facts — full facts-first trees owned
                    by build_fulltree_lang.
  STAGED_INDEXABLE  staged-indexable pilots. STAGED / HELD as before.
  ALL_SUBDIR_LANGS  every non-root language code — the /<lang>/ directories, used
                    to skip locale dirs during hub/commune discovery.

Members are DERIVED from data/languages.json and are never enumerated in this
comment — a typed list drifts (it once said FACTS_PUBLISHED=pl when the tuple
already returned all six). Run `python3 scripts/locales.py` to print each roster.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PATH = os.path.join(ROOT, "data", "languages.json")
_DATA = json.loads(open(_PATH, encoding="utf-8").read())

LANGUAGES = _DATA["languages"]  # insertion-ordered (declared order)


def _by_status(*statuses):
    return tuple(l for l, v in LANGUAGES.items() if v.get("status") in statuses)


def render_mode(lang):
    return LANGUAGES.get(lang, {}).get("render_mode", "prose")


def _root(l):
    return LANGUAGES[l].get("root")


VISIBLE = _by_status("published")
VISIBLE_SECONDARY = tuple(l for l in VISIBLE if not _root(l))
PROSE = tuple(l for l in VISIBLE if render_mode(l) == "prose")
PROSE_SECONDARY = tuple(l for l in PROSE if not _root(l))
FACTS_PUBLISHED = tuple(l for l in VISIBLE if render_mode(l) == "facts")
STAGED_INDEXABLE = _by_status("staged-indexable")
STAGED = _by_status("staged")
HELD = _by_status("held")
ALL_SUBDIR_LANGS = tuple(l for l in LANGUAGES if not _root(l))

ENDONYM = {l: v["endonym"] for l, v in LANGUAGES.items()}
DIR = {l: v.get("dir", "ltr") for l, v in LANGUAGES.items()}
STATUS = {l: v.get("status") for l, v in LANGUAGES.items()}


def endonyms(langs):
    """Ordered {lang: endonym} for the given roster (picker / lang_native)."""
    return {l: ENDONYM[l] for l in langs}


def status(lang):
    return STATUS.get(lang)


if __name__ == "__main__":
    # Print every roster, derived live from data/languages.json — the canonical
    # answer to "which langs are in X?", so no comment or label ever hard-codes it.
    for _name in ("VISIBLE", "VISIBLE_SECONDARY", "PROSE", "PROSE_SECONDARY",
                  "FACTS_PUBLISHED", "STAGED_INDEXABLE", "STAGED", "HELD",
                  "ALL_SUBDIR_LANGS"):
        _val = globals().get(_name)
        if _val is not None:
            print(f"{_name:18} {', '.join(_val) if _val else '(empty)'}")
