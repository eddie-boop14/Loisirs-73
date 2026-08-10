#!/usr/bin/env python3
"""Mutation proof for the protected-placements byte-guard (HANDOFF-39A-B3).

Builds a tiny fake built-tree in a temp dir (NOT a git repo, so the
EDMASTER-APPROVED trailer bypass can never fire here), writes the manifest,
proves the gate green, then flips ONE byte on a carrying page and proves the
gate red. Also proves: page added → red, page removed → red, and a non-carrying
page can change freely.
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATE = os.path.join(ROOT, "scripts", "gate_protected_placements.py")

CARRIER = ("<html><body><article class=\"partner\">Chez Nous à la Plage — "
           "<a href=\"https://cheznousalaplage.com\">réserver</a></article>"
           "</body></html>")
CARRIER2 = ("<html><body><article class=\"partner\">Chalet du Tornet — "
            "<a href=\"https://chaletdutornet.com\">réserver</a></article>"
            "</body></html>")
PLAIN = "<html><body>rien à voir ici</body></html>"


def write(base, rel, text):
    p = os.path.join(base, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)


def run_gate(base, *extra):
    manifest = os.path.join(base, "manifest.md")
    return subprocess.run(
        [sys.executable, GATE, "--tree", base, "--manifest", manifest, *extra],
        capture_output=True, text=True)


def expect(name, result, want_red, needle=None):
    if want_red:
        assert result.returncode != 0, f"[{name}] gate PASSED, expected red:\n{result.stdout}"
    else:
        assert result.returncode == 0, f"[{name}] gate RED, expected green:\n{result.stdout}{result.stderr}"
    if needle:
        assert needle in result.stdout, f"[{name}] output lacks {needle!r}:\n{result.stdout}"
    print(f"  ✓ {name}")


def fresh_tree():
    base = tempfile.mkdtemp(prefix="protplace_")
    write(base, "plage-alpha.html", CARRIER)
    write(base, "en/plage-alpha.html", CARRIER)
    write(base, "chalet-beta.html", CARRIER2)
    write(base, "libre.html", PLAIN)
    r = run_gate(base, "--write-manifest")
    assert r.returncode == 0, r.stdout + r.stderr
    return base


def main():
    # green on a faithful tree
    base = fresh_tree()
    expect("faithful tree green", run_gate(base), want_red=False)

    # ONE byte flipped on a carrying page → red (no git repo → no trailer bypass)
    base = fresh_tree()
    p = os.path.join(base, "plage-alpha.html")
    raw = bytearray(open(p, "rb").read())
    raw[raw.find(b"partner")] ^= 0x01  # flip one byte in place
    open(p, "wb").write(bytes(raw))
    expect("one-byte mutation red", run_gate(base), want_red=True,
           needle="WITHOUT an EDMASTER-APPROVED trailer")

    # a page GAINING the placement → red
    base = fresh_tree()
    write(base, "nouveau.html", CARRIER)
    expect("gained carrying page red", run_gate(base), want_red=True, needle="ADDED")

    # a carrying page LOSING the placement → red
    base = fresh_tree()
    write(base, "chalet-beta.html", PLAIN)
    expect("lost carrying page red", run_gate(base), want_red=True, needle="REMOVED")

    # a NON-carrying page may change freely → green
    base = fresh_tree()
    write(base, "libre.html", PLAIN + "<!-- edit libre -->")
    expect("non-carrying page free", run_gate(base), want_red=False)

    print("test_gate_protected_placements: mutation trips the byte-guard. ✓")


if __name__ == "__main__":
    main()
