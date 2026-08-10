#!/usr/bin/env python3
"""HANDOFF-25 — translate_batch validation + retry, adversarially tested offline.

Proves the standard-keeper:
  * all 4 validation checks (key parity, frozen nouns, HTML parity,
    length ratio / empty strings) reject bad results;
  * a seeded bad result is retried ONCE and a good retry is written;
  * a twice-failing result is logged to the failures report and the
    field stays ABSENT (null discipline);
  * idempotent: a populated fiche×lang pair is skipped on re-run;
  * --dry-run writes nothing and never needs an API key.

Network/SDK is mocked out; runs offline. pytest or standalone.
"""
import argparse
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
        "translate_batch_t", os.path.join(ROOT, "scripts", "translate_batch.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SRC = {
    "meta_title": "Abbaye d'Aulps · Rates and Hours (Saint-Jean-d'Aulps)",
    "hero": {"lead": "A 900-year-old abbey above the Lac d'Annecy road."},
    "body": {"what_is": "<p>A Cistercian abbey in <strong>Haute-Savoie</strong>.</p>"},
    "faq": [{"q": "Is it open?", "a": "Yes, year-round."}],
}
FROZEN = ["Lac d'Annecy", "Haute-Savoie", "Abbaye d'Aulps", "Saint-Jean-d'Aulps"]


def _good():
    return {
        "meta_title": "Abbaye d'Aulps · Ceny i godziny (Saint-Jean-d'Aulps)",
        "hero": {"lead": "Opactwo sprzed 900 lat przy drodze nad Lac d'Annecy."},
        "body": {"what_is": "<p>Opactwo cysterskie w <strong>Haute-Savoie</strong>.</p>"},
        "faq": [{"q": "Czy jest otwarte?", "a": "Tak, przez cały rok."}],
    }


# ------------------------------------------------------------------ validate()

def test_valid_translation_passes():
    m = _load()
    assert m.validate(SRC, _good(), FROZEN) == []


def test_key_parity_rejects_missing_and_invented():
    m = _load()
    out = _good(); del out["faq"]
    assert any("parity" in v for v in m.validate(SRC, out, FROZEN))
    out = _good(); out["invented_field"] = "boo"
    assert any("parity" in v for v in m.validate(SRC, out, FROZEN))


def test_frozen_noun_loss_rejected():
    m = _load()
    out = _good()
    out["hero"]["lead"] = "Opactwo nad jeziorem Annecy."  # translated the lake!
    assert any("frozen noun" in v and "Lac d'Annecy" in v
               for v in m.validate(SRC, out, FROZEN))


def test_html_parity_and_escaped_tags_rejected():
    m = _load()
    out = _good()
    out["body"]["what_is"] = "Opactwo cysterskie w Haute-Savoie."   # tags dropped
    assert any("HTML" in v for v in m.validate(SRC, out, FROZEN))
    out = _good()
    out["body"]["what_is"] = "&lt;p&gt;Opactwo w <strong>Haute-Savoie</strong>.&lt;/p&gt;"
    assert any("escaped" in v or "HTML" in v for v in m.validate(SRC, out, FROZEN))


def test_length_ratio_and_empty_strings_rejected():
    m = _load()
    out = _good()
    out["meta_title"] = "A"
    out["hero"]["lead"] = "Lac d'Annecy"
    out["body"]["what_is"] = "<p><strong>Haute-Savoie</strong></p>"
    out["faq"] = [{"q": "?", "a": "!"}]
    assert any("ratio" in v for v in m.validate(SRC, out, FROZEN))
    out = _good()
    out["faq"][0]["a"] = ""
    assert any("empty translation" in v for v in m.validate(SRC, out, FROZEN))


# -------------------------------------------------------------- custom_id spec

def test_custom_id_meets_api_spec_for_every_real_slug():
    """Run #2 regression: '<slug>:<lang>' 400'd on the colon AND on 73-char
    slugs. Every generated id must match ^[a-zA-Z0-9_-]{1,64}$ and stay unique
    even when truncation eats the distinguishing suffix."""
    m = _load()
    long_a = "musee-patrimonial-pays-thones-fondateurs-francois-et-lucien-cochat-thones"
    long_b = long_a[:-6] + "annecy"          # same 64-char prefix after truncation
    slugs = ["abbaye-d-aulps", long_a, long_b]
    ids = [m.make_custom_id("pt", i, s) for i, s in enumerate(slugs)]
    for cid in ids:
        assert API_CUSTOM_ID_RE.match(cid), cid
    assert len(set(ids)) == len(ids), "index must keep truncated ids unique"


# --------------------------------------------------------- end-to-end w/ mock

import re as _re
API_CUSTOM_ID_RE = _re.compile(r"^[a-zA-Z0-9_-]{1,64}$")   # the real API constraint


class FakeBatches:
    """Scripted batch API: each create() pops the next results dict (keyed by
    SLUG). Enforces the real custom_id constraint — the original fake was too
    permissive and let the '<slug>:<lang>' 400 (run #2) escape to production."""
    def __init__(self, rounds):
        self.rounds = rounds       # list of {slug: ('ok', text)|('error', why)}
        self.created = []          # requests of each submitted batch

    def create(self, requests):
        seen = set()
        for r in requests:
            cid = r["custom_id"]
            assert API_CUSTOM_ID_RE.match(cid), \
                f"API would 400: custom_id {cid!r} violates ^[a-zA-Z0-9_-]{{1,64}}$"
            assert cid not in seen, f"duplicate custom_id {cid!r}"
            seen.add(cid)
        self.created.append(requests)
        return type("B", (), {"id": f"batch_{len(self.created)}",
                              "processing_status": "in_progress"})()

    def retrieve(self, batch_id):
        counts = type("C", (), {"succeeded": 0, "errored": 0, "expired": 0, "processing": 0})()
        return type("B", (), {"id": batch_id, "processing_status": "ended",
                              "request_counts": counts})()

    def results(self, batch_id):
        idx = int(batch_id.rsplit("_", 1)[1]) - 1
        for req in self.created[idx]:
            cid = req["custom_id"]
            slug = cid.split("-", 2)[2]          # "<lang>-<idx>-<slug>" (untruncated in tests)
            kind, payload = self.rounds[idx][slug]
            if kind == "ok":
                blk = type("T", (), {"type": "text", "text": payload})()
                msg = type("M", (), {"content": [blk]})()
                res = type("R", (), {"type": "succeeded", "message": msg})()
            else:
                res = type("R", (), {"type": payload})()
            yield type("Row", (), {"custom_id": cid, "result": res})()


class FakeClient:
    def __init__(self, rounds):
        self.messages = type("Msgs", (), {})()
        self.messages.batches = FakeBatches(rounds)


def _fixture_repo(m, tmp):
    jd = Path(tmp) / "Json"; jd.mkdir()
    for slug in ("good-one", "bad-then-good", "bad-twice"):
        # FR is the translation source (HANDOFF amendment: was i18n.en). The
        # source prose lives in fr now; en is just another target language.
        fiche = {"slug": slug, "commune": "Annecy",
                 "i18n": {"fr": {**dict(SRC), "name": "Abbaye d'Aulps"}}}
        (jd / f"{slug}.json").write_text(
            json.dumps(fiche, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    m.JSON_DIR = jd
    m.STATE_FILE = Path(tmp) / "reports" / "state.json"
    m.FAILURES_MD = Path(tmp) / "reports" / "failures.md"
    m.CALIBRATION_FILE = Path(tmp) / "reports" / "calibration.json"  # hermetic
    m.time.sleep = lambda s: None
    return jd


def test_seeded_bad_result_retried_once_then_logged():
    m = _load()
    with tempfile.TemporaryDirectory() as tmp:
        jd = _fixture_repo(m, tmp)
        good = json.dumps(_good(), ensure_ascii=False)
        bad = json.dumps({"meta_title": "tylko tytuł"}, ensure_ascii=False)  # parity fail
        rounds = [
            {   # round 1: one good, two seeded-bad
                "good-one": ("ok", good),
                "bad-then-good": ("ok", bad),
                "bad-twice": ("ok", bad),
            },
            {   # retry round: one recovers, one fails again
                "bad-then-good": ("ok", good),
                "bad-twice": ("ok", bad),
            },
        ]
        client = FakeClient(rounds)
        args = argparse.Namespace(dry_run=False, force=False)
        ok = m.run_language("pl", args, client)
        assert not ok, "run must report failure when a pair fails twice"

        batches = client.messages.batches
        assert len(batches.created) == 2, "exactly one retry batch"
        retry_slugs = sorted(r["custom_id"].split("-", 2)[2] for r in batches.created[1])
        assert retry_slugs == ["bad-then-good", "bad-twice"]

        d = json.loads((jd / "good-one.json").read_text())
        assert d["i18n"]["pl"]["meta_title"].startswith("Abbaye d'Aulps")
        d = json.loads((jd / "bad-then-good.json").read_text())
        assert "faq" in d["i18n"]["pl"], "recovered retry must be written"
        d = json.loads((jd / "bad-twice.json").read_text())
        assert "pl" not in d.get("i18n", {}), \
            "twice-failed pair must stay ABSENT (null discipline)"
        assert "bad-twice" in m.FAILURES_MD.read_text(encoding="utf-8")


def test_idempotent_rerun_skips_populated_pairs():
    m = _load()
    with tempfile.TemporaryDirectory() as tmp:
        jd = _fixture_repo(m, tmp)
        # populate good-one fully
        p = jd / "good-one.json"
        d = json.loads(p.read_text()); d["i18n"]["pl"] = _good()
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        pairs = m.pairs_for_lang("pl")
        slugs = [f["slug"] for f, _ in pairs]
        assert "good-one" not in slugs and len(slugs) == 2
        assert len(m.pairs_for_lang("pl", force=True)) == 3


def test_missing_fields_only_payload_and_pmr_detail_travels():
    """HANDOFF-35 Job A: acces_pmr.detail joins the payload (FR-authored
    content, rendered off-fr only once translated) — and a fiche missing ONLY
    that field must be re-billed for that field alone, never the whole prose."""
    m = _load()
    with tempfile.TemporaryDirectory() as tmp:
        jd = _fixture_repo(m, tmp)
        p = jd / "good-one.json"
        d = json.loads(p.read_text())
        d["acces_pmr"] = {"status": "accessible",
                          "detail": "Rampe d'accès et main courante."}
        d["i18n"]["pl"] = _good()          # full prose already translated…
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        pairs = {f["slug"]: src for f, src in m.pairs_for_lang("pl")}
        assert pairs["good-one"] == {"acces_pmr_detail": "Rampe d'accès et main courante."}, \
            "only the missing field may travel — a mop-up costs cents, not $19"
        # untranslated fiches still carry the full payload incl. the detail? no —
        # they have no acces_pmr, so payload is the EN prose exactly as before
        assert set(pairs["bad-twice"]) == set(SRC)


def test_dry_run_writes_nothing_and_needs_no_key():
    m = _load()
    with tempfile.TemporaryDirectory() as tmp:
        jd = _fixture_repo(m, tmp)
        before = {p.name: p.read_bytes() for p in jd.glob("*.json")}
        args = argparse.Namespace(dry_run=True, force=False)
        assert m.run_language("pl", args, client=None) is True
        assert {p.name: p.read_bytes() for p in jd.glob("*.json")} == before
        assert not m.STATE_FILE.exists()


# ------------------------------------------------- HANDOFF-35: the honest meter

class UsageFakeBatches(FakeBatches):
    """FakeBatches whose succeeded messages carry API usage — per-request
    token counts scripted via self.usage_per_req."""
    def __init__(self, rounds, usage_per_req):
        super().__init__(rounds)
        self.usage_per_req = usage_per_req

    def results(self, batch_id):
        for row in super().results(batch_id):
            if row.result.type == "succeeded":
                u = type("U", (), dict(self.usage_per_req))()
                row.result.message.usage = u
            yield row


def test_estimate_calibration_and_uncached_system():
    m = _load()
    with tempfile.TemporaryDirectory() as tmp:
        jd = _fixture_repo(m, tmp)
        m.CALIBRATION_FILE = Path(tmp) / "reports" / "calibration.json"
        pairs = m.pairs_for_lang("pl")
        communes = m.all_communes()
        n, in_tok, out_tok, usd, calibrated = m.estimate(pairs, communes, "pl")
        assert n == 3 and not calibrated, "no calibration file → uncalibrated"
        # the system prompt is below MIN_CACHEABLE_TOKENS → billed uncached on
        # every request: in_tok must include ~n full system blocks, far more
        # than the old cached model's 1.25 + 0.1(n-1)
        sys_tok = int(len(m.system_prompt("pl", communes)) * m.DEFAULT_IN_PER_CHAR) + 1
        assert sys_tok < m.MIN_CACHEABLE_TOKENS
        body_tok = sum(int(len(m.user_prompt(f, s)) * m.DEFAULT_IN_PER_CHAR) + 1
                       for f, s in pairs)
        assert in_tok == body_tok + sys_tok * n, "system must be priced per request"
        # calibration file wins over the default assumptions
        m.CALIBRATION_FILE.parent.mkdir(exist_ok=True)
        m.CALIBRATION_FILE.write_text(json.dumps({
            "input_tokens_per_char": 0.5,
            "output_tokens_per_source_char": {"pl": 1.0}}), encoding="utf-8")
        n2, in2, out2, usd2, calibrated2 = m.estimate(pairs, communes, "pl")
        assert calibrated2 and in2 > in_tok and out2 > out_tok and usd2 > usd


def test_usage_cost_and_over_budget_rule():
    m = _load()
    tot = m.sum_usage([
        {"input_tokens": 1_000_000, "output_tokens": 0,
         "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
        {"input_tokens": 0, "output_tokens": 2_000_000,
         "cache_creation_input_tokens": 1_000_000, "cache_read_input_tokens": 1_000_000},
    ])
    # 1.50 + 2×7.50 + 1.875 + 0.15 = 18.525 — exact arithmetic, no drift
    assert abs(m.usage_cost_usd(tot) - 18.525) < 1e-9
    assert not m.over_budget(1.15, 1.0), "exactly 15% over is the ceiling, not a trip"
    assert m.over_budget(1.16, 1.0)
    assert not m.over_budget(5.0, 0.0), "no contract → no trip (dry-run handles it)"


def test_budget_abort_skips_retry_submit():
    """A retry is a SECOND PAID submit — over the >15% contract ceiling it
    must be SKIPPED, logged, and the run must exit red (HANDOFF-35 rule)."""
    m = _load()
    with tempfile.TemporaryDirectory() as tmp:
        jd = _fixture_repo(m, tmp)
        good = json.dumps(_good(), ensure_ascii=False)
        bad = json.dumps({"meta_title": "tylko tytuł"}, ensure_ascii=False)
        rounds = [{"good-one": ("ok", good), "bad-then-good": ("ok", bad),
                   "bad-twice": ("ok", bad)},
                  {}]      # a retry round must never be reached
        client = FakeClient(rounds)
        # huge per-request usage → main batch alone busts the tiny contract
        client.messages.batches = UsageFakeBatches(rounds, {
            "input_tokens": 500_000, "output_tokens": 500_000,
            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0})
        args = argparse.Namespace(dry_run=False, force=False)
        code = None
        try:
            m.run_language("pl", args, client)
        except SystemExit as e:
            code = e.code
        assert code == 2, f"budget abort must exit 2, got {code!r}"
        assert len(client.messages.batches.created) == 1, \
            "the retry batch must NOT be submitted after a budget abort"
        assert "budget abort" in m.FAILURES_MD.read_text(encoding="utf-8")
        state = json.loads(m.STATE_FILE.read_text(encoding="utf-8"))
        assert state["pl"].get("budget_abort") is True
        assert state["pl"]["usage_main"]["output_tokens"] == 1_500_000
        # the good result arrived and was paid for — it stays written
        d = json.loads((jd / "good-one.json").read_text())
        assert "pl" in d["i18n"]


def test_final_overrun_goes_red_but_keeps_paid_results():
    m = _load()
    with tempfile.TemporaryDirectory() as tmp:
        jd = _fixture_repo(m, tmp)
        good = json.dumps(_good(), ensure_ascii=False)
        rounds = [{"good-one": ("ok", good), "bad-then-good": ("ok", good),
                   "bad-twice": ("ok", good)}]
        client = FakeClient(rounds)
        client.messages.batches = UsageFakeBatches(rounds, {
            "input_tokens": 500_000, "output_tokens": 500_000,
            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0})
        args = argparse.Namespace(dry_run=False, force=False)
        code = None
        try:
            m.run_language("pl", args, client)
        except SystemExit as e:
            code = e.code
        assert code == 3, f"final >15% overrun must exit 3, got {code!r}"
        for slug in ("good-one", "bad-then-good", "bad-twice"):
            d = json.loads((jd / f"{slug}.json").read_text())
            assert "pl" in d["i18n"], "paid results must be written before going red"


def test_audit_batch_sums_usage_and_maps_slugs():
    m = _load()
    with tempfile.TemporaryDirectory() as tmp:
        jd = _fixture_repo(m, tmp)
        good = json.dumps(_good(), ensure_ascii=False)
        rounds = [{"good-one": ("ok", good), "bad-then-good": ("ok", good),
                   "bad-twice": ("error", "errored")}]
        batches = UsageFakeBatches(rounds, {
            "input_tokens": 1000, "output_tokens": 2000,
            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0})
        # submit through build_requests so custom_ids are the real shape
        pairs = m.pairs_for_lang("pl")
        reqs, id_map = m.build_requests(pairs, ["Annecy"], "pl")
        batches.create(reqs)
        client = FakeClient([]); client.messages.batches = batches
        corpus = m.all_source_pairs()
        chars = {s: len(m.user_prompt(f, src)) for s, (f, src) in corpus.items()}
        rec = m.audit_batch(client, "batch_1", {}, chars, set(corpus))  # empty id_map → prefix mapping
        assert rec["ok"] == 2 and rec["err"] == 1 and rec["lang"] == "pl"
        assert rec["usage"]["input_tokens"] == 2000
        assert rec["usage"]["output_tokens"] == 4000
        assert rec["n_mapped"] == 2, "slugs must map back via the cid fragment"
        assert abs(rec["usd"] - (2000 * 1.50 + 4000 * 7.50) / 1e6) < 1e-9


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
