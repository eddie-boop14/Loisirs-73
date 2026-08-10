#!/usr/bin/env python3
"""Regression for the patch-submit push bug (translate-loisirs74.yml).

The "Push results to a review branch" step used a single
`git add Json/ reports/A reports/B reports/translate-cost-calibration.json …`.
git add is ATOMIC: one missing literal pathspec (calibration.json only exists
after mode=audit, which never ran) makes it FATAL and stage NOTHING — silently
discarding the paid Json patch, so every patch-submit landed 0 commits while
still billing.

The fix stages Json/ unconditionally, then each optional report file only if it
exists. This test proves BOTH: the old monolithic add drops the paid Json when
a listed file is absent, and the new pattern keeps it. It also asserts the
workflow no longer contains the monolithic form.
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "translate-loisirs74.yml")


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def _init_repo():
    d = tempfile.mkdtemp(prefix="pushadd_")
    _git(d, "init", "-q")
    _git(d, "config", "user.email", "x@x")
    _git(d, "config", "user.name", "x")
    os.makedirs(os.path.join(d, "Json"))
    os.makedirs(os.path.join(d, "reports"))
    with open(os.path.join(d, "Json", "a.json"), "w") as fh:
        fh.write('{"v":0}\n')
    with open(os.path.join(d, "reports", "translate-local-flags-pl.json"), "w") as fh:
        fh.write("{}\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "init")
    # a "paid" run: run_patch rewrites both the Json fiche and the flags file
    with open(os.path.join(d, "Json", "a.json"), "w") as fh:
        fh.write('{"v":1,"patched":true}\n')
    with open(os.path.join(d, "reports", "translate-local-flags-pl.json"), "w") as fh:
        fh.write('{"patched":true}\n')
    return d


def _staged(d):
    return set(_git(d, "diff", "--cached", "--name-only").stdout.split())


def test_old_monolithic_add_drops_paid_json():
    """The OLD form fatals on the missing calibration.json and stages nothing."""
    d = _init_repo()
    # translate-cost-calibration.json intentionally absent (mode=audit never ran)
    _git(d, "add", "Json/",
         "reports/translate-batch-state.json",
         "reports/translate-cost-calibration.json",
         "reports/translate-local-flags-pl.json")
    assert "Json/a.json" not in _staged(d), \
        "a missing literal pathspec must (reproduce the bug) stage NOTHING"


def test_new_pattern_keeps_paid_json():
    """The NEW form: add Json/ always, optional reports only if present."""
    d = _init_repo()
    _git(d, "add", "Json/")
    for f in ["reports/translate-batch-state.json",
              "reports/translate-cost-calibration.json",   # absent
              "reports/translate-local-flags-pl.json"]:     # present
        if os.path.exists(os.path.join(d, f)):
            _git(d, "add", f)
    staged = _staged(d)
    assert "Json/a.json" in staged, "the paid Json patch must be staged"
    assert "reports/translate-local-flags-pl.json" in staged, "existing flags file staged"
    r = _git(d, "commit", "-qm", "patch")
    assert r.returncode == 0, f"commit must succeed: {r.stderr}"


def test_workflow_uses_resilient_add():
    """The shipped workflow must NOT carry the monolithic multi-file git add."""
    txt = open(WORKFLOW, encoding="utf-8").read()
    assert "for f in reports/translate-batch-state.json" in txt, \
        "push step must loop optional report files"
    assert "git add Json/ reports/translate-batch-state.json" not in txt, \
        "the monolithic (fatal-prone) git add must be gone"


def _all():
    return [v for k, v in sorted(globals().items()) if k.startswith("test_")]


if __name__ == "__main__":
    failed = 0
    for t in _all():
        try:
            t(); print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1; print(f"FAIL {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1; print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(_all()) - failed}/{len(_all())} passed")
    sys.exit(1 if failed else 0)
