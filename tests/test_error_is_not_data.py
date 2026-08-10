#!/usr/bin/env python3
"""HANDOFF-24 Job 2 — error ≠ data, adversarially tested.

The 2026-07-01 incident: the Google key died, every call errored, and the
checkers overwrote 397 fiches' verified data with the error state. These
tests prove that can never happen again:

  * check_loisirs74 / sweep_loisirs74: a simulated 100%-failure run changes
    ZERO Json files and exits non-zero (mass-failure circuit breaker);
  * a sub-breaker CHECK_FAILED keeps ALL previous values — only
    last_check + check_failed are stamped;
  * reachability: one failed fetch is an observation, never a verdict —
    site_reachable=false needs a second failed fetch on a LATER day, and a
    run where >10% of fetches fail discards the whole reachability signal;
  * apply_sweep_signals: CHECK_FAILED (and legacy status=ERROR) blocks carry
    no signal; unconfirmed site-down never flags; a mass of same-run signals
    trips its own breaker before any demotion is written.

Network is monkeypatched out; runs offline. pytest or standalone.
"""
import argparse
import datetime
import hashlib
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
TODAY = datetime.date.today().isoformat()


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _check_mod():
    return _load(os.path.join(ROOT, "check_loisirs74.py"), "check_loisirs74_t")


def _sweep_mod():
    return _load(os.path.join(ROOT, "sweep_loisirs74.py"), "sweep_loisirs74_t")


def _apply_mod():
    return _load(os.path.join(ROOT, "scripts", "apply_sweep_signals.py"),
                 "apply_sweep_signals_t")


def _fiche(slug, **over):
    """A fiche with verified June data — what the July 1 bot destroyed."""
    d = {
        "slug": slug,
        "status": "published",
        "commune": "Annecy",
        "postal_code": "74000",
        "category": "musees",
        "latitude": 45.9, "longitude": 6.12,
        "official_site_url": f"https://{slug}.example.fr",
        "i18n": {"fr": {"name": slug.replace("-", " ").title()}},
        "google_check": {
            "checked": "2026-06-04", "query": f"{slug} Annecy",
            "match": "Verified Name", "place_id": f"PID-{slug}",
            "status": "OPERATIONAL", "outcome": "OK",
            "website": f"https://{slug}.example.fr", "stored_website": f"https://{slug}.example.fr",
            "rating": 4.3, "rating_count": 517,
            "hours": ["lundi: 14:00 – 18:30"] * 7,
            "google_lat": 45.9, "google_lng": 6.12, "gps_drift_m": 6,
        },
        "freshness": {
            "checked": "2026-06-05", "status": "OPERATIONAL", "confidence": "high",
            "flag_reason": "", "outcome": "OK",
            "google_match": "Verified Name", "place_id": f"PID-{slug}",
            "google_status": "OPERATIONAL",
            "website": {"value": f"https://{slug}.example.fr", "source": "google", "verified": "2026-06-05"},
            "phone": {"value": "04 50 04 52 63", "source": "google", "verified": "2026-06-05"},
            "hours": {"value": ["lundi: 14:00 – 18:30"] * 7, "source": "google", "verified": "2026-06-05"},
            "rating": 4.3, "rating_count": 517,
            "registry": {"state": "ACTIF", "siret": "88245894600010", "closure_date": None},
            "site_reachable": True, "price_candidates": [],
            "gps_drift_m": 6, "needs_price_review": False,
        },
    }
    d.update(over)
    return d


def _seed(jd, n=12, **over):
    for i in range(n):
        p = Path(jd) / f"fiche-{i:02d}.json"
        p.write_text(json.dumps(_fiche(f"fiche-{i:02d}", **over),
                                ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _tree_hash(jd):
    h = hashlib.md5()
    for p in sorted(Path(jd).glob("*.json")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()


GOOGLE_OK = {"place_id": "PID-new", "match": "Fresh Name", "status": "OPERATIONAL",
             "website": "https://fresh.example.fr", "phone": "04 50 00 00 00",
             "rating": 4.6, "rating_count": 600, "lat": 45.9, "lng": 6.12,
             "hours": ["lundi: 09:00 – 18:00"] * 7}
REG_OK = {"state": "ACTIF", "siret": "123", "closure_date": None}
SITE_OK = {"reachable": True, "price_candidates": []}
SITE_DOWN = {"reachable": False, "error": "timeout", "price_candidates": []}


def _no_sleep(mod):
    mod.time.sleep = lambda s: None


# --------------------------------------------------------------- check_loisirs74

def test_check_100pct_failure_writes_nothing_and_exits_nonzero():
    with tempfile.TemporaryDirectory() as jd:
        _seed(jd)
        m = _check_mod(); _no_sleep(m)
        m.API_KEY, m.JSON_DIR, m.FORCE = "test-key", jd, False
        m.REPORT = os.path.join(jd, "..", "report.csv")

        def dead_key(q):
            raise OSError("HTTP Error 403: Forbidden")
        m.query_google = dead_key

        before = _tree_hash(jd)
        try:
            m.main()
            raise AssertionError("breaker did not trip")
        except SystemExit as e:
            assert e.code == 2, f"expected exit 2, got {e.code}"
        assert _tree_hash(jd) == before, "100%-failure run modified Json files"


def test_check_sub_breaker_failure_keeps_all_previous_values():
    with tempfile.TemporaryDirectory() as jd:
        _seed(jd, n=12)
        m = _check_mod(); _no_sleep(m)
        m.API_KEY, m.JSON_DIR, m.FORCE = "test-key", jd, False
        m.REPORT = os.path.join(jd, "report.csv")

        def one_bad(q):
            if "Fiche 00" in q:
                raise OSError("HTTP Error 403: Forbidden")
            place = {"id": "PID-new", "displayName": {"text": "Fresh Name"},
                     "businessStatus": "OPERATIONAL", "websiteUri": "https://fresh.example.fr",
                     "rating": 4.6, "userRatingCount": 600,
                     "location": {"latitude": 45.9, "longitude": 6.12},
                     "regularOpeningHours": {"weekdayDescriptions": ["lundi: 09:00"] * 7}}
            return place
        m.query_google = one_bad

        m.main()
        failed = json.loads((Path(jd) / "fiche-00.json").read_text())["google_check"]
        orig = _fiche("fiche-00")["google_check"]
        for k, v in orig.items():
            if k == "outcome":
                continue    # outcome is re-stamped CHECK_FAILED
            assert failed.get(k) == v, f"CHECK_FAILED lost previous {k}: {failed.get(k)!r} != {v!r}"
        assert failed["outcome"] == "CHECK_FAILED"
        assert failed["last_check"] == TODAY
        assert "403" in failed["check_failed"]
        ok = json.loads((Path(jd) / "fiche-01.json").read_text())["google_check"]
        assert ok["outcome"] == "OK" and ok["rating"] == 4.6 and ok["checked"] == TODAY


# --------------------------------------------------------------- sweep_loisirs74

def test_sweep_100pct_failure_writes_nothing_and_exits_nonzero():
    with tempfile.TemporaryDirectory() as jd:
        _seed(jd)
        m = _sweep_mod(); _no_sleep(m)
        m.API_KEY, m.JSON_DIR, m.FORCE, m.NO_SITE = "test-key", jd, False, False

        def dead_key(name, commune):
            raise OSError("HTTP Error 403: Forbidden")
        m.google_lookup = dead_key
        m.registry_lookup = lambda *a: REG_OK
        m.site_check = lambda url: SITE_OK

        before = _tree_hash(jd)
        cwd = os.getcwd()
        os.chdir(jd)  # sweep writes report.csv in CWD — keep it in the tmp dir
        try:
            m.main()
            raise AssertionError("breaker did not trip")
        except SystemExit as e:
            assert e.code == 2, f"expected exit 2, got {e.code}"
        finally:
            os.chdir(cwd)
        assert _tree_hash(jd) == before, "100%-failure sweep modified Json files"


def test_sweep_sub_breaker_failure_is_noop_merge():
    with tempfile.TemporaryDirectory() as jd:
        _seed(jd, n=12)
        m = _sweep_mod(); _no_sleep(m)
        m.API_KEY, m.JSON_DIR, m.FORCE, m.NO_SITE = "test-key", jd, False, False

        def one_bad(name, commune):
            if name == "Fiche 00":
                raise OSError("HTTP Error 403: Forbidden")
            return dict(GOOGLE_OK)
        m.google_lookup = one_bad
        m.registry_lookup = lambda *a: dict(REG_OK)
        m.site_check = lambda url: dict(SITE_OK)

        cwd = os.getcwd(); os.chdir(jd)
        try:
            m.main()
        finally:
            os.chdir(cwd)
        failed = json.loads((Path(jd) / "fiche-00.json").read_text())["freshness"]
        orig = _fiche("fiche-00")["freshness"]
        for k, v in orig.items():
            if k == "outcome":
                continue    # outcome is re-stamped CHECK_FAILED
            assert failed.get(k) == v, f"CHECK_FAILED lost previous freshness.{k}"
        assert failed["outcome"] == "CHECK_FAILED"
        assert failed["last_check"] == TODAY and "403" in failed["check_failed"]
        assert failed["place_id"] == "PID-fiche-00", "verified place_id was lost"
        ok = json.loads((Path(jd) / "fiche-01.json").read_text())["freshness"]
        assert ok["outcome"] == "OK" and ok["rating"] == 4.6


def test_sweep_registry_error_keeps_previous_registry_block():
    with tempfile.TemporaryDirectory() as jd:
        _seed(jd, n=12)
        m = _sweep_mod(); _no_sleep(m)
        m.API_KEY, m.JSON_DIR, m.FORCE, m.NO_SITE = "test-key", jd, False, False
        m.google_lookup = lambda *a: dict(GOOGLE_OK)
        m.registry_lookup = lambda *a: {"state": "ERROR", "detail": "HTTP 500"}
        m.site_check = lambda url: dict(SITE_OK)

        cwd = os.getcwd(); os.chdir(jd)
        try:
            m.main()
        finally:
            os.chdir(cwd)
        fr = json.loads((Path(jd) / "fiche-00.json").read_text())["freshness"]
        assert fr["registry"]["state"] == "ACTIF", "registry error overwrote previous state"
        assert fr["registry"]["siret"] == "88245894600010"
        assert "registry_check_failed" in fr


def test_sweep_single_dead_fetch_is_observation_not_verdict():
    with tempfile.TemporaryDirectory() as jd:
        _seed(jd, n=12)
        m = _sweep_mod(); _no_sleep(m)
        m.API_KEY, m.JSON_DIR, m.FORCE, m.NO_SITE = "test-key", jd, False, False
        m.google_lookup = lambda *a: dict(GOOGLE_OK)
        m.registry_lookup = lambda *a: dict(REG_OK)
        m.site_check = lambda url: (dict(SITE_DOWN) if "fiche-00" in (url or "")
                                    else dict(SITE_OK))

        cwd = os.getcwd(); os.chdir(jd)
        try:
            m.main()
        finally:
            os.chdir(cwd)
        fr = json.loads((Path(jd) / "fiche-00.json").read_text())["freshness"]
        assert fr["site_reachable"] is True, "one bad fetch flipped site_reachable"
        assert fr["site_last_unreachable"] == TODAY, "observation was not recorded"
        assert not fr.get("site_unreachable_confirmed")


def test_sweep_second_dead_fetch_on_later_day_confirms():
    with tempfile.TemporaryDirectory() as jd:
        _seed(jd, n=12)
        # fiche-00 already had a failed fetch yesterday
        p = Path(jd) / "fiche-00.json"
        d = json.loads(p.read_text())
        d["freshness"]["site_last_unreachable"] = "2026-06-30"
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        m = _sweep_mod(); _no_sleep(m)
        m.API_KEY, m.JSON_DIR, m.FORCE, m.NO_SITE = "test-key", jd, False, False
        m.google_lookup = lambda *a: dict(GOOGLE_OK)
        m.registry_lookup = lambda *a: dict(REG_OK)
        m.site_check = lambda url: (dict(SITE_DOWN) if "fiche-00" in (url or "")
                                    else dict(SITE_OK))

        cwd = os.getcwd(); os.chdir(jd)
        try:
            m.main()
        finally:
            os.chdir(cwd)
        fr = json.loads((Path(jd) / "fiche-00.json").read_text())["freshness"]
        assert fr["site_reachable"] is False
        assert fr["site_unreachable_confirmed"] is True


def test_sweep_mass_site_failure_discards_reachability_signal():
    with tempfile.TemporaryDirectory() as jd:
        _seed(jd, n=12)
        m = _sweep_mod(); _no_sleep(m)
        m.API_KEY, m.JSON_DIR, m.FORCE, m.NO_SITE = "test-key", jd, False, False
        m.google_lookup = lambda *a: dict(GOOGLE_OK)
        m.registry_lookup = lambda *a: dict(REG_OK)
        m.site_check = lambda url: dict(SITE_DOWN)    # every fetch fails: checker broken

        cwd = os.getcwd(); os.chdir(jd)
        try:
            m.main()
        finally:
            os.chdir(cwd)
        for i in range(12):
            fr = json.loads((Path(jd) / f"fiche-{i:02d}.json").read_text())["freshness"]
            assert fr["site_reachable"] is True, \
                "mass same-day failure wrote site_reachable=false"
            assert not fr.get("site_unreachable_confirmed")
            assert not fr.get("site_last_unreachable"), \
                "discarded observation still recorded"
            assert "site_check_failed" in fr


# ----------------------------------------------------------- apply_sweep_signals

def _apply_env(m, jd):
    m.JSON_DIR = Path(jd) / "Json"
    m.ROOT = Path(jd)
    (Path(jd) / "reports").mkdir(exist_ok=True)


def _run_apply(m, dry_run=False):
    return m.apply(argparse.Namespace(dry_run=dry_run))


def test_apply_ignores_check_failed_and_legacy_error_blocks():
    with tempfile.TemporaryDirectory() as base:
        jd = Path(base) / "Json"; jd.mkdir()
        _seed(jd, n=12)
        # fiche-00: CHECK_FAILED stamp on an otherwise-scary CLOSED signal
        d = _fiche("fiche-00")
        d["freshness"].update({"status": "CLOSED", "confidence": "high",
                               "outcome": "CHECK_FAILED", "check_failed": "google: 403"})
        (jd / "fiche-00.json").write_text(json.dumps(d) + "\n", encoding="utf-8")
        # fiche-01: legacy poisoned shape — google_check.status == ERROR
        d = _fiche("fiche-01")
        d["google_check"].update({"status": "ERROR", "error": "HTTP Error 403"})
        d["freshness"].update({"status": "UNVERIFIED", "google_status": "ERROR",
                               "confidence": "low"})
        (jd / "fiche-01.json").write_text(json.dumps(d) + "\n", encoding="utf-8")

        m = _apply_mod(); _apply_env(m, base)
        demoted, flagged, skipped, _ = _run_apply(m)
        assert not demoted, f"demoted from a failed check: {demoted}"
        assert not flagged, f"flagged from a failed check: {flagged}"
        for i in (0, 1):
            d = json.loads((jd / f"fiche-{i:02d}.json").read_text())
            assert d["status"] == "published", "a failed check demoted a fiche"


def test_apply_unconfirmed_site_down_never_flags():
    with tempfile.TemporaryDirectory() as base:
        jd = Path(base) / "Json"; jd.mkdir()
        _seed(jd, n=12)
        d = _fiche("fiche-00")
        d["freshness"].update({"site_reachable": False,
                               "site_last_unreachable": TODAY})   # first sighting only
        (jd / "fiche-00.json").write_text(json.dumps(d) + "\n", encoding="utf-8")
        m = _apply_mod(); _apply_env(m, base)
        demoted, flagged, skipped, _ = _run_apply(m)
        assert not flagged, f"unconfirmed site-down flagged: {flagged}"

        # now confirmed on a later day → flag (still never demote)
        d["freshness"]["site_unreachable_confirmed"] = True
        (jd / "fiche-00.json").write_text(json.dumps(d) + "\n", encoding="utf-8")
        demoted, flagged, skipped, _ = _run_apply(m)
        assert len(flagged) == 1 and not demoted


def test_apply_valid_closed_signal_still_demotes():
    with tempfile.TemporaryDirectory() as base:
        jd = Path(base) / "Json"; jd.mkdir()
        _seed(jd, n=12)
        d = _fiche("fiche-00")
        d["freshness"].update({"status": "CLOSED", "confidence": "high",
                               "flag_reason": "Google + registry agree (fermé 2026-05-01)"})
        (jd / "fiche-00.json").write_text(json.dumps(d) + "\n", encoding="utf-8")
        m = _apply_mod(); _apply_env(m, base)
        demoted, flagged, skipped, _ = _run_apply(m)
        assert len(demoted) == 1, "a genuine high-confidence CLOSED must still demote"
        d = json.loads((jd / "fiche-00.json").read_text())
        assert d["status"] == "draft"


def test_apply_mass_signal_breaker_blocks_the_run():
    with tempfile.TemporaryDirectory() as base:
        jd = Path(base) / "Json"; jd.mkdir()
        _seed(jd, n=12)
        # 3/12 fiches (25%) suddenly CLOSED high-confidence → checker broken
        for i in range(3):
            d = _fiche(f"fiche-{i:02d}")
            d["freshness"].update({"status": "CLOSED", "confidence": "high"})
            (jd / f"fiche-{i:02d}.json").write_text(json.dumps(d) + "\n", encoding="utf-8")
        m = _apply_mod(); _apply_env(m, base)
        before = _tree_hash(jd)
        try:
            _run_apply(m)
            raise AssertionError("mass-signal breaker did not trip")
        except SystemExit as e:
            assert e.code == 2
        assert _tree_hash(jd) == before, "breaker tripped but fiches were written"


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
