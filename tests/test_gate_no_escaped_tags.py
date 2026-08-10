#!/usr/bin/env python3
"""HANDOFF-23 — no-escaped-tags gate + emit_prose, adversarially tested.

  * a seeded page rendering '&lt;strong&gt;' trips the gate (exit 1);
  * a clean tree (real tags, entities in ordinary prose) passes;
  * emit_prose: authored HTML flows raw, plain text stays escaped —
    a bare '<' comparison or '&' in plain prose must NOT go raw.

Runs offline. pytest or standalone.
"""
import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# These tests load scripts by file path (spec_from_file_location), which —
# unlike running `python3 scripts/x.py` — does NOT put scripts/ on sys.path.
# A target's own `import siteconfig` would then fail. Put it there explicitly.
sys.path.insert(0, os.path.join(ROOT, "scripts"))
GATE = os.path.join(ROOT, "scripts", "gate_no_escaped_tags.py")


def _build_mod():
    spec = importlib.util.spec_from_file_location(
        "build_lieu_page_t", os.path.join(ROOT, "scripts", "build_lieu_page.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _gate(root):
    return subprocess.run([sys.executable, GATE, "--root", root],
                          capture_output=True, text=True)


def test_seeded_escaped_tag_trips_the_gate():
    with tempfile.TemporaryDirectory() as root:
        Path(root, "ok.html").write_text(
            "<html><body><p>Vrai <strong>HTML</strong> &amp; entités.</p></body></html>",
            encoding="utf-8")
        Path(root, "bad.html").write_text(
            "<html><body>&lt;strong&gt;Défi-Foly&lt;/strong&gt; sur le lac gelé</body></html>",
            encoding="utf-8")
        r = _gate(root)
        assert r.returncode == 1, f"seeded escaped tag passed the gate:\n{r.stdout}"
        assert "bad.html" in r.stdout and "ok.html" not in r.stdout


def test_clean_tree_passes():
    with tempfile.TemporaryDirectory() as root:
        Path(root, "a.html").write_text(
            "<p>Tarif &lt; 5 € — pas une balise, juste une comparaison.</p>",
            encoding="utf-8")
        Path(root, "b.html").write_text("<ul><li>vrai html</li></ul>", encoding="utf-8")
        r = _gate(root)
        assert r.returncode == 0, r.stdout


def test_emit_prose_raw_for_authored_html_escaped_for_plain_text():
    m = _build_mod()
    html = "Fin mars : <strong>Défi-Foly</strong> sur le lac gelé."
    assert m.emit_prose(html) == html, "authored HTML must flow through raw"
    plain = "Ouvert 9h-18h & jours fériés, tarif < 5 €"
    out = m.emit_prose(plain)
    assert "&amp;" in out and "<" not in out.replace("&lt;", ""), \
        "plain text must stay on the escaping path"
    assert m.emit_prose(None) == ""


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
