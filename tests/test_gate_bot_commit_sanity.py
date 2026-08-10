#!/usr/bin/env python3
"""HANDOFF-24 Job 3 — gate_bot_commit_sanity, tripped by a seeded mass-deletion.

Builds a throwaway git repo of fiches with verified google data, then:
  * bot-style damage on 25 fiches (place_id/hours/website/phone nulled the way
    the 2026-07-01 run did) → gate exits 1;
  * the same damage on 3 fiches (legitimate per-venue updates) → gate passes;
  * value CHANGES (fresh data, nothing deleted) on all fiches → gate passes.

Runs offline. pytest or standalone.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATE = os.path.join(ROOT, "scripts", "gate_bot_commit_sanity.py")


def _fiche(slug):
    return {
        "slug": slug, "status": "published",
        "google_check": {
            "checked": "2026-06-04", "match": "Verified Name",
            "place_id": f"PID-{slug}", "status": "OPERATIONAL",
            "website": "https://x.example.fr",
            "hours": ["lundi: 14:00 – 18:30"] * 7, "rating": 4.3,
        },
        "freshness": {
            "checked": "2026-06-05", "status": "OPERATIONAL",
            "google_match": "Verified Name", "place_id": f"PID-{slug}",
            "website": {"value": "https://x.example.fr", "source": "google", "verified": "2026-06-05"},
            "phone": {"value": "04 50 04 52 63", "source": "google", "verified": "2026-06-05"},
            "hours": {"value": ["lundi: 14:00 – 18:30"] * 7, "source": "google", "verified": "2026-06-05"},
        },
    }


def _bot_damage(d):
    """The exact shape the dead-key run wrote on 2026-07-01."""
    d["google_check"] = {"checked": "2026-07-01", "status": "ERROR",
                         "error": "HTTP Error 403: Forbidden", "website": None}
    d["freshness"].update({"checked": "2026-07-01", "status": "UNVERIFIED",
                           "google_match": None, "place_id": None,
                           "website": None, "phone": None, "hours": None})
    return d


def _repo(n=30):
    base = tempfile.mkdtemp(prefix="gate-sanity-")
    jd = Path(base) / "Json"; jd.mkdir()
    for i in range(n):
        (jd / f"fiche-{i:02d}.json").write_text(
            json.dumps(_fiche(f"fiche-{i:02d}"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
    run = lambda *a: subprocess.run(a, cwd=base, capture_output=True, text=True)
    run("git", "init", "-q")
    run("git", "config", "user.email", "t@t"); run("git", "config", "user.name", "t")
    run("git", "add", "-A"); run("git", "commit", "-qm", "verified state")
    return base


def _gate(base, *extra):
    return subprocess.run(
        [sys.executable, GATE, "--base", "HEAD", "--root", base, *extra],
        capture_output=True, text=True)


def test_seeded_mass_deletion_trips_the_gate():
    base = _repo(30)
    jd = Path(base) / "Json"
    for i in range(25):
        p = jd / f"fiche-{i:02d}.json"
        p.write_text(json.dumps(_bot_damage(json.loads(p.read_text())),
                                ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    r = _gate(base)
    assert r.returncode == 1, f"mass deletion passed the gate:\n{r.stdout}"
    assert "25 fiches lost verified fields" in r.stdout


def test_per_venue_deletions_pass():
    base = _repo(30)
    jd = Path(base) / "Json"
    for i in range(3):   # a real closure or two is normal
        p = jd / f"fiche-{i:02d}.json"
        p.write_text(json.dumps(_bot_damage(json.loads(p.read_text())),
                                ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    r = _gate(base)
    assert r.returncode == 0, f"3 per-venue changes must pass:\n{r.stdout}"


def test_value_changes_without_deletion_pass():
    base = _repo(30)
    jd = Path(base) / "Json"
    for p in jd.glob("*.json"):   # fresh data everywhere — nothing deleted
        d = json.loads(p.read_text())
        d["google_check"]["rating"] = 4.9
        d["google_check"]["hours"] = ["lundi: 09:00 – 19:00"] * 7
        d["freshness"]["checked"] = "2026-08-01"
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    r = _gate(base)
    assert r.returncode == 0, f"value updates tripped the gate:\n{r.stdout}"


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
