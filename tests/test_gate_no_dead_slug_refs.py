#!/usr/bin/env python3
"""HANDOFF-15 leftovers — gate_no_dead_slug_refs on data/*_index.json,
adversarially seeded.

  * a dead slug NESTED inside an index (the _meta.line_conflicts hiding spot
    that let chateau-des-rubins-observatoire-des-alpes linger) trips the gate;
  * top-level dead keys still trip it;
  * transport_index's _meta.feeds[].slug (GTFS dataset ids, not fiches) are
    excluded — no false positive;
  * a clean tree passes;
  * any future data/*_index.json is picked up automatically.

Runs offline. pytest or standalone.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATE = os.path.join(ROOT, "scripts", "gate_no_dead_slug_refs.py")


def _repo(base):
    jd = Path(base) / "Json"; jd.mkdir()
    for slug in ("live-one", "live-two"):
        (jd / f"{slug}.json").write_text(json.dumps({"slug": slug}), encoding="utf-8")
    (Path(base) / "data").mkdir()
    return base


def _write(base, rel, obj):
    p = Path(base) / rel
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _gate(base):
    return subprocess.run([sys.executable, GATE, "--root", base],
                          capture_output=True, text=True)


def test_nested_dead_slug_in_meta_trips_the_gate():
    with tempfile.TemporaryDirectory() as base:
        _repo(base)
        _write(base, "data/transport_index.json", {
            "_meta": {"line_conflicts": [
                {"slug": "live-one", "prose_lines": ["1"]},
                {"slug": "renamed-away-fiche", "prose_lines": ["2"]},  # the hiding spot
            ]},
            "live-one": {"stops": []},
        })
        r = _gate(base)
        assert r.returncode == 1, f"nested dead slug passed:\n{r.stdout}"
        assert "renamed-away-fiche" in r.stdout


def test_top_level_dead_key_still_trips():
    with tempfile.TemporaryDirectory() as base:
        _repo(base)
        _write(base, "data/parking_index.json",
               {"_meta": {}, "live-one": {}, "ghost-fiche": {}})
        r = _gate(base)
        assert r.returncode == 1 and "ghost-fiche" in r.stdout


def test_feed_dataset_slugs_are_not_false_positives():
    with tempfile.TemporaryDirectory() as base:
        _repo(base)
        _write(base, "data/transport_index.json", {
            "_meta": {"feeds": [{"slug": "offre-de-transports-sibra-a-annecy-gtfs"}],
                      "line_conflicts": [{"slug": "live-two"}]},
            "live-one": {},
        })
        r = _gate(base)
        assert r.returncode == 0, f"GTFS feed slug false-positived:\n{r.stdout}"


def test_future_index_files_are_covered():
    with tempfile.TemporaryDirectory() as base:
        _repo(base)
        _write(base, "data/brand_new_index.json",
               {"_meta": {}, "entries": [{"slug": "does-not-exist"}]})
        r = _gate(base)
        assert r.returncode == 1 and "brand_new_index.json" in r.stdout


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
