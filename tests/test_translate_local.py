#!/usr/bin/env python3
"""HANDOFF-37 — the $0 MT lane, adversarially tested offline (fake engine).

Proves the lane's construction guarantees:
  * tags / attrs / URLs / entities NEVER reach the MT engine;
  * identity translation reassembles byte-exact;
  * frozen nouns are masked, restored verbatim, and survive validate();
  * placeholder loss / digit mutation / empty output → segment FLAGGED,
    field stays ABSENT (null discipline), full segment table in the flags file;
  * patch-tier reassembly completes a field from patched segments;
  * patch contract respects the $2/lang hard cap.
"""
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# These tests load scripts by file path (spec_from_file_location), which —
# unlike running `python3 scripts/x.py` — does NOT put scripts/ on sys.path.
# A target's own `import siteconfig` would then fail. Put it there explicitly.
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def _load():
    spec = importlib.util.spec_from_file_location(
        "translate_local_t", os.path.join(ROOT, "scripts", "translate_local.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


NOUNS = ["Lac d'Annecy", "Haute-Savoie", "Annecy", "Abbaye d'Aulps"]


class SpyEngine:
    """Fake MT: records everything it is asked to translate; configurable."""

    def __init__(self, fn=None):
        self.seen = []
        self.fn = fn or (lambda t: t)          # identity by default

    def __call__(self, text):
        self.seen.append(text)
        return self.fn(text)


def test_tags_entities_urls_never_reach_engine():
    m = _load()
    eng = SpyEngine()
    s = ('<p>Visit <strong>the abbey</strong> &amp; the lake — see '
         '<a href="https://example.com/x?a=1">the site</a> today.</p>')
    records = []
    out, bad = m.translate_string(eng, {}, s, NOUNS, "body.what_is", records)
    assert bad == 0 and out == s, "identity engine must reassemble byte-exact"
    joined = "\n".join(eng.seen)
    assert "<" not in joined and ">" not in joined, "tags leaked into MT"
    assert "&amp;" not in joined, "entities leaked into MT"
    assert "https://" not in joined, "URLs must be masked before MT"


def test_frozen_nouns_masked_and_restored():
    m = _load()
    eng = SpyEngine(lambda t: t.upper())       # aggressive engine
    s = "The beach at Lac d'Annecy near Annecy is in Haute-Savoie."
    records = []
    out, bad = m.translate_string(eng, {}, s, NOUNS, "hero.lead", records)
    assert bad == 0
    for noun in ("Lac d'Annecy", "Annecy", "Haute-Savoie"):
        assert noun in out, f"{noun} not restored verbatim"
    assert "LAC D'ANNECY" not in out, "noun reached the engine unmasked"
    # longest-first: 'Lac d'Annecy' masked as ONE token, not 'Lac d''+Annecy
    assert "Lac d'ANNECY" not in out


def test_placeholder_loss_flags_segment():
    m = _load()
    eng = SpyEngine(lambda t: "totally rewritten without tokens")
    records = []
    out, bad = m.translate_string(
        eng, {}, "Visit Lac d'Annecy today.", NOUNS, "f", records)
    assert bad == 1
    assert any("placeholder lost" in r for rec in records
               for r in rec.get("reasons", []))


def test_digit_mutation_and_empty_flagged():
    m = _load()
    eng = SpyEngine(lambda t: t.replace("5", "6"))
    records = []
    _, bad = m.translate_string(
        eng, {}, "Entry costs 5,50 € per adult.", [], "f", records)
    assert bad == 1 and any("digit parity" in r for rec in records
                            for r in rec.get("reasons", []))
    eng = SpyEngine(lambda t: "")
    records = []
    _, bad = m.translate_string(eng, {}, "Some real sentence.", [], "f", records)
    assert bad == 1


def test_unmask_tolerates_spacing_and_case():
    m = _load()
    out, missing = m.unmask("go to xqv 0 z and XQV1Z", {"0": "Annecy", "1": "Léman"})
    assert out == "go to Annecy and Léman" and not missing
    out, missing = m.unmask("no tokens here", {"0": "Annecy"})
    assert missing == {"0"}


def test_mt_run_null_discipline_and_flags_file():
    m = _load()
    tbm = m.tb
    with tempfile.TemporaryDirectory() as tmp:
        jd = Path(tmp) / "Json"; jd.mkdir()
        good_src = {"meta_title": "Abbaye d'Aulps · Rates (Annecy)",
                    "body": {"what_is": "<p>An abbey in <strong>Haute-Savoie</strong>.</p>"}}
        bad_src = {"meta_title": "Beach fun for 5 € in Annecy",
                   "hero": {"lead": "A fine beach on Lac d'Annecy."}}
        for slug, src in (("ok-one", good_src), ("digit-bad", bad_src)):
            (jd / f"{slug}.json").write_text(json.dumps({
                "slug": slug, "commune": "Annecy",
                "i18n": {"fr": {**src, "name": "X"}}},
                ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tbm.JSON_DIR = jd
        m.FLAGS_FILE = Path(tmp) / "reports" / "flags-{lang}.json"
        # engine: identity EXCEPT it breaks digits (5 → 55)
        eng = SpyEngine(lambda t: t.replace("5", "55"))
        written, flagged = m.run_mt("pl", engine=eng)
        d = json.loads((jd / "ok-one.json").read_text())
        assert d["i18n"]["pl"]["meta_title"].startswith("Abbaye d'Aulps"), \
            "clean fiche must be written"
        d = json.loads((jd / "digit-bad.json").read_text())
        pl = d.get("i18n", {}).get("pl", {})
        assert "meta_title" not in pl, "flagged field must stay ABSENT"
        assert "hero" in pl, "clean field of the same fiche still ships"
        flags = json.loads((Path(tmp) / "reports" / "flags-pl.json").read_text())
        assert flags["fields"] and flags["fields"][0]["slug"] == "digit-bad"
        segs = flags["fields"][0]["segments"]
        assert any(not r.get("ok") and r["kind"] == "text" for r in segs)


def test_rebuild_field_with_patches():
    m = _load()
    src = {"what_is": "<p>Hello world &amp; more text here.</p>"}
    records = []
    eng = SpyEngine(lambda t: "")               # everything fails
    out, bad = m.translate_value(eng, {}, src, [], "body", records)
    assert bad >= 1
    assert m.rebuild_field(src, records, {}, "body") is None, \
        "unpatched failed segment → field stays absent"
    patches = {(r["path"], r["i"]): f"T<{r['i']}>".replace("<", "").replace(">", "")
               for r in records if r["kind"] == "text" and not r.get("ok")}
    patches = {k: "Bonjour le monde" for k in patches}
    rebuilt = m.rebuild_field(src, records, patches, "body")
    assert rebuilt is not None
    assert rebuilt["what_is"].startswith("<p>") and "&amp;" in rebuilt["what_is"], \
        "frozen tokens must reassemble verbatim around the patch"


def test_currency_symbol_change_flagged():
    m = _load()
    eng = SpyEngine(lambda t: t.replace("€", "EUR"))
    records = []
    _, bad = m.translate_string(
        eng, {}, "Entry costs 5,50 € per adult today.", [], "f", records)
    assert bad == 1 and any("currency" in r for rec in records
                            for r in rec.get("reasons", []))


def test_fr_source_field_never_enters_mt():
    """acces_pmr_detail is FR-authored: it must be flagged to the LLM patch
    tier without ever reaching the en→X engine, and must NOT be written.
    (A field already populated is out of scope by design: post-#37
    pairs_for_lang sends missing fields only, and going forward the patch
    tier is the ONLY writer of FR-source fields — a provenance-blind purge
    of populated fields would delete paid patch output.)"""
    m = _load()
    tbm = m.tb
    with tempfile.TemporaryDirectory() as tmp:
        jd = Path(tmp) / "Json"; jd.mkdir()
        (jd / "beach.json").write_text(json.dumps({
            "slug": "beach", "commune": "Annecy",
            "acces_pmr": {"status": "accessible",
                          "detail": "Rampe d'accès et tapis d'aide à la baignade."},
            "i18n": {"fr": {"name": "X", "meta_title": "Beach guide (Annecy)"}}},
            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tbm.JSON_DIR = jd
        m.FLAGS_FILE = Path(tmp) / "reports" / "flags-{lang}.json"
        eng = SpyEngine()
        # only provable when the payload carries the field (post-#37 main)
        src = tbm.extract_source(json.loads((jd / "beach.json").read_text()))
        if "acces_pmr_detail" not in src:
            return                       # pre-#37 base: nothing to prove yet
        m.run_mt("pl", engine=eng)
        assert not any("Rampe" in s for s in eng.seen), \
            "FR-source field reached the en→X engine"
        d = json.loads((jd / "beach.json").read_text())
        pl = d["i18n"]["pl"]
        assert "acces_pmr_detail" not in pl, "FR-source field must stay ABSENT"
        assert pl.get("meta_title"), "EN fields still ship"
        flags = json.loads((Path(tmp) / "reports" / "flags-pl.json").read_text())
        fr = [f for f in flags["fields"] if f["field"] == "acces_pmr_detail"]
        assert fr and any("LLM patch tier" in r for s in fr[0]["segments"]
                          for r in s.get("reasons", []))


def test_purge_fields_removes_stale_writes():
    """purge_fields (used when a re-run flags a field an earlier run wrote,
    e.g. a future --force lane) removes exactly the named fields."""
    m = _load()
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "beach.json"
        p.write_text(json.dumps({
            "slug": "beach",
            "i18n": {"pl": {"meta_title": "keep", "hero_alt": "stale"}}},
            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        m.purge_fields({"_path": str(p)}, "pl", ["hero_alt", "never_there"])
        d = json.loads(p.read_text())
        assert d["i18n"]["pl"] == {"meta_title": "keep"}


def test_french_source_sniff_flags_and_never_translates():
    """HANDOFF-37 Layer-B discovery: 'EN' segments that are actually French
    must never enter an en→X engine — flagged to the patch tier. Frozen
    French proper nouns must NOT trip the sniff (they are masked first)."""
    m = _load()
    eng = SpyEngine()
    records = []
    fr = "Parc accrobranche à 950 m d'altitude au pied de la cascade, avec 8 parcours et des tyroliennes."
    out, bad = m.translate_string(eng, {}, fr, [], "hero.lead", records)
    assert bad == 1 and not eng.seen, "French must never reach the engine"
    assert any(m.FR_LOOK_REASON in r for rec in records
               for r in rec.get("reasons", []))
    # EN sentence full of masked French nouns: no trip
    eng2 = SpyEngine()
    records2 = []
    en = "Visit Lac d'Annecy near Annecy and the Château de Menthon today."
    nouns = ["Lac d'Annecy", "Annecy", "Château de Menthon"]
    out2, bad2 = m.translate_string(eng2, {}, en, nouns, "f", records2)
    assert bad2 == 0 and eng2.seen, "masked-noun EN must still translate"


def test_resniff_purges_fr_poisoned_populated_fields():
    m = _load()
    tbm = m.tb
    with tempfile.TemporaryDirectory() as tmp:
        jd = Path(tmp) / "Json"; jd.mkdir()
        (jd / "poisoned.json").write_text(json.dumps({
            "slug": "poisoned", "commune": "Annecy",
            "i18n": {"fr": {"name": "X",
                            "meta_title": "Fine English title (Annecy)",
                            "hero": {"lead": "Parc accrobranche à 950 m d'altitude avec des parcours et une île aux enfants."}},
                     "pl": {"meta_title": "dobre tłumaczenie",
                            "hero": {"lead": "semi-french garbage written by MT"}}}},
            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tbm.JSON_DIR = jd
        m.FLAGS_FILE = Path(tmp) / "reports" / "flags-{lang}.json"
        purged = m.resniff("pl")
        assert purged == 1
        d = json.loads((jd / "poisoned.json").read_text())
        pl = d["i18n"]["pl"]
        assert "hero" not in pl, "FR-poisoned MT write must be purged"
        assert pl.get("meta_title") == "dobre tłumaczenie", "clean field untouched"


def test_target_script_check_flags_untranslated_passthrough():
    """Layer-B catch #3 (ar): the engine returns long segments untranslated —
    digit/ratio checks pass, but the output is not in the target script."""
    m = _load()
    ar = m.TARGET_SCRIPT["ar"]
    ok = m.check_segment("A treetop venture park with ziplines.", "حديقة مغامرات في قمم الأشجار مع انزلاقات", ar)
    assert ok == []
    bad = m.check_segment("A treetop venture park with ziplines.", "A treetop venture park with ziplines.", ar)
    assert any("target script" in r for r in bad)
    # loanwords inside majority-Arabic must NOT flag
    mixed = m.check_segment("A rope course with jumps today.", "مسار الحبال مع jumps رائع جدا هنا", ar)
    assert mixed == []
    # pl (no script entry) unaffected
    assert m.check_segment("Some sentence here today.", "Jakieś zdanie tutaj dzisiaj.", None) == []


def test_patch_contract_and_cap():
    m = _load()
    flags = {"lang": "pl", "fields": [{
        "slug": "s", "field": "body", "src": {"what_is": "x"},
        "segments": [{"path": "body.what_is", "i": 0, "kind": "text",
                      "src": "A sentence to patch.", "mt": "", "ok": False,
                      "reasons": ["empty translation"]}] * 1,
    }]}
    reqs, routing = m.patch_requests("pl", flags)
    assert len(reqs) == 1 and reqs[0]["params"]["model"] == m.PATCH_MODEL
    in_tok, out_tok, usd = m.patch_estimate(reqs)
    assert usd < 0.01, "one segment must cost well under a cent"
    # the $2 cap: 30k segments would blow it → the estimate must say so
    big = {"lang": "pl", "fields": [{
        "slug": "s", "field": "body", "src": {},
        "segments": [{"path": f"p{i}", "i": 0, "kind": "text",
                      "src": "A long sentence with many words repeated." * 3,
                      "mt": "", "ok": False, "reasons": ["x"]}
                     for i in range(30000)]}]}
    reqs2, _ = m.patch_requests("pl", big)
    _, _, usd2 = m.patch_estimate(reqs2)
    assert usd2 > m.PATCH_CAP_USD, "cap scenario must be detectable pre-submit"


def test_patch_meter_prices_at_haiku_not_sonnet():
    """Regression for the 'fails but still bills' patch-submit bug: the ACTUAL
    cost of a Haiku patch batch must be priced at Haiku rates ($0.50/$2.50),
    not the module's Sonnet batch rates ($1.50/$7.50). With the real run #17
    usage (774,187 in / 377,087 out) the Haiku price is ~$1.33 (under the
    $1.45 estimate and the $2 cap → PASS); the Sonnet mis-price was $3.99
    (phantom overspend → false RED after already billing)."""
    m = _load()
    tb = m.tb
    tot = {k: 0 for k in tb.USAGE_KEYS}
    tot["input_tokens"] = 774187
    tot["output_tokens"] = 377087

    haiku = tb.usage_cost_usd(tot,
                              in_per_mtok=m.PATCH_IN_PER_MTOK,
                              out_per_mtok=m.PATCH_OUT_PER_MTOK,
                              cache_write_per_mtok=m.PATCH_CACHE_WRITE_PER_MTOK,
                              cache_read_per_mtok=m.PATCH_CACHE_READ_PER_MTOK)
    assert abs(haiku - 1.33) < 0.02, f"Haiku patch price should be ~$1.33, got ${haiku:.2f}"

    # the DEFAULT (unchanged) rates are the Sonnet batch lane — this is the
    # mis-price the patch meter used to inherit; keep it pinned so a future
    # rate edit can't silently re-break the patch tier.
    sonnet = tb.usage_cost_usd(tot)
    assert abs(sonnet - 3.99) < 0.02, f"default rates are Sonnet (~$3.99), got ${sonnet:.2f}"

    est = 1.45  # the pl dry-run contract for this batch
    assert not tb.over_budget(haiku, est), "Haiku actual ≤ estimate must NOT trip the >15% abort"
    assert tb.over_budget(sonnet, est), "the Sonnet mis-price is what falsely tripped it"


def test_patch_recover_lands_paid_results_without_resubmit():
    """The recover path claims an already-PAID patch batch: no new submit, and
    it must NOT abort on cost (the spend is sunk — aborting would re-lose the
    paid work, which is the original bug). Feeds a fake batch result through
    run_patch_recover and asserts the field lands."""
    m = _load()
    tbm = m.tb
    with tempfile.TemporaryDirectory() as tmp:
        jd = Path(tmp) / "Json"; jd.mkdir()
        (jd / "spot.json").write_text(json.dumps({
            "slug": "spot", "commune": "Annecy",
            "i18n": {"fr": {"name": "X",
                            "hero": {"lead": "A calm spot open all year."}}}},
            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tbm.JSON_DIR = jd
        m.FLAGS_FILE = Path(tmp) / "reports" / "flags-{lang}.json"

        # base MT tier fails the segment (empty) → it is flagged, pl absent
        m.run_mt("pl", engine=SpyEngine(lambda t: ""))
        d = json.loads((jd / "spot.json").read_text())
        assert "pl" not in d["i18n"] or "hero" not in d["i18n"]["pl"], \
            "field must start absent (flagged)"

        # reconstruct the deterministic routing to know the batch custom_id
        flags = json.loads((Path(tmp) / "reports" / "flags-pl.json").read_text())
        reqs, routing = m.patch_requests("pl", flags)
        assert len(reqs) == 1
        cid = reqs[0]["custom_id"]

        # fake an already-ended, already-paid batch: a good pl translation, and
        # deliberately "expensive" usage that WOULD trip the >15% abort if the
        # recover path wrongly enforced a budget.
        good = "Spokojne miejsce otwarte cały rok."
        fake_usage = {k: 0 for k in tbm.USAGE_KEYS}
        fake_usage["input_tokens"] = 5_000_000
        fake_usage["output_tokens"] = 5_000_000
        tbm.get_client = lambda: object()
        tbm.poll_batch = lambda client, bid, **kw: None
        tbm.collect_results = lambda client, bid: ({cid: ("ok", good)},
                                                   {cid: fake_usage})

        ok = m.run_patch_recover("pl", batch_id="msgbatch_fake")  # must NOT sys.exit
        d = json.loads((jd / "spot.json").read_text())
        assert d["i18n"]["pl"]["hero"]["lead"] == good, \
            "recovered translation must be written back to the fiche"
        assert ok is True


def _all_tests():
    return [v for k, v in sorted(globals().items()) if k.startswith("test_")]


if __name__ == "__main__":
    failed = 0
    for t in _all_tests():
        try:
            t(); print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1; print(f"FAIL {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1; print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    total = len(_all_tests())
    print(f"\n{total - failed}/{total} passed")
    sys.exit(1 if failed else 0)
