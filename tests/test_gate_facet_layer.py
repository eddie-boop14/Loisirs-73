#!/usr/bin/env python3
"""Adversarial proof for gate_facet_layer (HANDOFF-39A-A3).

Builds a tiny 2-fiche corpus in a temp dir with the REAL generator
(scripts/build_ai_content.py), asserts the strict gate passes it, then seeds
ONE OF EACH defect class into a fresh copy and asserts the gate catches every
single one with a violation that names the file. Defect classes:

  md:   missing header · reordered headers · typo ("## Hour") · case drift ·
        trailing whitespace · extra ## section · CRLF · non-UTF-8 ·
        missing file · two H1s · frozen-name drift
  json: missing key (null-ok, absent-key-forbidden) · wrong type ·
        unknown extra key · fabricated value (gps ≠ source)

Any seeded disease the gate misses → this test exits 1 (and CI goes red).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "scripts", "build_ai_content.py")
GATE = os.path.join(ROOT, "scripts", "gate_facet_layer.py")

FICHES = [
    {
        "slug": "lieu-alpha",
        "commune": "Annecy",
        "postal_code": "74000",
        "category": "lac",
        "latitude": 45.9,
        "longitude": 6.12,
        "status": "published",
        "official_site_url": "https://example.org/alpha",
        "price_from": 2.5,
        "price_currency": "EUR",
        "price_tiers": [{"name": "Adulte", "price": 2.5, "note": "Unité"}],
        "schema_org": {"is_free": False},
        "acces_pmr": {"status": "accessible", "detail": "Rampe d'accès.",
                      "equipment": ["rampe"], "handiplage_level": None,
                      "source_url": "https://example.org/pmr",
                      "source_name": "Commune"},
        "freshness": {"checked": "2026-06-01"},
        "i18n": {
            "fr": {"name": "Lieu Alpha",
                   "facts": {"type": "Plage", "parking": "Gratuit",
                             "best_season": "Été", "tarif": "2,50 €"},
                   "practical_info": [{"k": "Horaires", "v": "9h–18h"}],
                   "meta_description": "Alpha au bord du lac."},
            "en": {"name": "Lieu Alpha",
                   "facts": {"type": "Beach", "parking": "Free",
                             "best_season": "Summer"},
                   "practical_info": [{"k": "Hours", "v": "9am–6pm"}]},
        },
    },
    {
        "slug": "lieu-beta",
        "commune": None,
        "category": "musee",
        "latitude": None,
        "longitude": None,
        "status": "published",
        "i18n": {"fr": {"name": "Lieu Béta", "facts": {}}},
    },
]


def build_corpus(base):
    jd = os.path.join(base, "Json")
    cd = os.path.join(base, "content")
    os.makedirs(jd)
    for d in FICHES:
        with open(os.path.join(jd, d["slug"] + ".json"), "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False)
    r = subprocess.run([sys.executable, BUILD, "--json-dir", jd,
                        "--content-dir", cd, "--root", base],
                       capture_output=True, text=True)
    assert r.returncode == 0, f"builder failed:\n{r.stdout}\n{r.stderr}"
    return jd, cd


def run_gate(base):
    return subprocess.run(
        [sys.executable, GATE, "--json-dir", os.path.join(base, "Json"),
         "--content-dir", os.path.join(base, "content"), "--root", base],
        capture_output=True, text=True)


def seed_and_expect(clean, name, mutate, needle):
    """Copy the clean corpus, apply `mutate(base)`, expect gate red with `needle`."""
    with tempfile.TemporaryDirectory(prefix="facet_seed_") as base:
        shutil.copytree(clean, base, dirs_exist_ok=True)
        mutate(base)
        r = run_gate(base)
        assert r.returncode != 0, f"[{name}] gate PASSED a seeded defect!\n{r.stdout}"
        assert needle in r.stdout, (f"[{name}] gate red but violation text lacks "
                                    f"{needle!r}:\n{r.stdout}")
        print(f"  ✓ seeded defect caught: {name}")


def md_path(base, lang, slug):
    return (os.path.join(base, "content", f"{slug}.md") if lang == "fr"
            else os.path.join(base, "content", "en", f"{slug}.md"))


def edit_text(path, fn):
    t = open(path, encoding="utf-8").read()
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(fn(t))


def main():
    with tempfile.TemporaryDirectory(prefix="facet_clean_") as clean:
        build_corpus(clean)
        r = run_gate(clean)
        assert r.returncode == 0, f"gate must pass the clean generated corpus:\n{r.stdout}"
        print("  ✓ clean generated corpus passes the strict gate")

        cases = [
            ("md missing header",
             lambda b: edit_text(md_path(b, "fr", "lieu-alpha"),
                                 lambda t: t.replace("## Parking\n\nGratuit\n\n", "")),
             "missing anchor"),
            ("md reordered headers",
             lambda b: edit_text(md_path(b, "fr", "lieu-alpha"),
                                 lambda t: t.replace("## Horaires", "@@TMP@@")
                                            .replace("## Tarifs", "## Horaires")
                                            .replace("@@TMP@@", "## Tarifs")),
             "anchor drift"),
            ("md typo '## Hour'",
             lambda b: edit_text(md_path(b, "en", "lieu-alpha"),
                                 lambda t: t.replace("## Hours", "## Hour")),
             "anchor drift"),
            ("md case drift '## facts'",
             lambda b: edit_text(md_path(b, "en", "lieu-alpha"),
                                 lambda t: t.replace("## Facts", "## facts")),
             "anchor drift"),
            ("md trailing whitespace",
             lambda b: edit_text(md_path(b, "fr", "lieu-beta"),
                                 lambda t: t.replace("## Parking\n", "## Parking \n", 1)),
             "trailing whitespace"),
            ("md extra ## section",
             lambda b: edit_text(md_path(b, "fr", "lieu-alpha"),
                                 lambda t: t + "\n## Bonus\n\nsurprise\n"),
             "extra section"),
            ("md CRLF",
             lambda b: _rewrite_bytes(md_path(b, "en", "lieu-beta"),
                                      lambda raw: raw.replace(b"\n", b"\r\n")),
             "LF only"),
            ("md non-UTF-8",
             lambda b: _rewrite_bytes(md_path(b, "fr", "lieu-beta"),
                                      lambda raw: raw + "\n<!-- café -->\n".encode("latin-1")),
             "not valid UTF-8"),
            ("md missing file",
             lambda b: os.remove(md_path(b, "en", "lieu-alpha")),
             "MISSING file"),
            ("md two H1s",
             lambda b: edit_text(md_path(b, "fr", "lieu-alpha"),
                                 lambda t: t.replace("## Faits", "# Doublon\n\n## Faits", 1)),
             "exactly one H1"),
            ("md frozen-name drift",
             lambda b: edit_text(md_path(b, "en", "lieu-alpha"),
                                 lambda t: t.replace("# Lieu Alpha", "# Place Alpha", 1)),
             "H1 drift"),
            ("json missing key (absent ≠ null)",
             lambda b: _json_mut(b, "lieu-alpha", lambda d: d.pop("hours")),
             "missing key"),
            ("json wrong type",
             lambda b: _json_mut(b, "lieu-alpha",
                                 lambda d: d.__setitem__("gps", "45.9, 6.12")),
             "gps"),
            ("json unknown extra key",
             lambda b: _json_mut(b, "lieu-beta",
                                 lambda d: d.__setitem__("bonus", 1)),
             "unknown key"),
            ("json fabricated value (gps ≠ source)",
             lambda b: _json_mut(b, "lieu-alpha",
                                 lambda d: d.__setitem__("gps", {"lat": 44.0, "lng": 5.0})),
             "≠ source"),
        ]
        for name, mutate, needle in cases:
            seed_and_expect(clean, name, mutate, needle)

    print(f"test_gate_facet_layer: all {len(cases) } seeded defect classes caught. ✓")


def _rewrite_bytes(path, fn):
    raw = open(path, "rb").read()
    with open(path, "wb") as fh:
        fh.write(fn(raw))


def _json_mut(base, slug, fn):
    p = os.path.join(base, "api", "lieu", f"{slug}.json")
    d = json.load(open(p, encoding="utf-8"))
    fn(d)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
