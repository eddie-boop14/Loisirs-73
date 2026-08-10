#!/usr/bin/env python3
"""Seeded-proof tests for gate_meta_uniqueness (HANDOFF-32).

Proves the gate actually trips: a clean tree passes; a title shared by >3
DIFFERENT pages fails; an indexable page without a meta fails; while the two
legitimate patterns stay green — the same-content hreflang cluster (one fiche,
many language trees, coinciding fallback strings) and noindex chrome pages.
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(HERE, "..", "scripts", "gate_meta_uniqueness.py")


def page(title, meta=None, noindex=False):
    metas = f'<meta name="description" content="{meta}">' if meta else ""
    robots = '<meta name="robots" content="noindex, nofollow">' if noindex else ""
    return (f"<!doctype html><html lang=\"fr\"><head><title>{title}</title>"
            f"{robots}{metas}</head><body>x</body></html>")


def write(root, rel, html):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w", encoding="utf-8").write(html)


def run(root):
    r = subprocess.run([sys.executable, GATE, "--root", root],
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def clean_tree(root):
    # unique pages + a same-content cluster across 5 language trees (allowed)
    write(root, "a.html", page("Fiche A · X | Loisirs 74", "Meta A"))
    write(root, "b.html", page("Fiche B · Y | Loisirs 74", "Meta B"))
    for lg in ("en", "de", "it", "es", "nl"):
        write(root, f"{lg}/karting.html",
              page("Karting de Rumilly · Rumilly | Loisirs 74", f"Karting meta {lg}"))
    # noindex chrome page without a meta (allowed)
    write(root, "merci.html", page("Merci", noindex=True))


def main():
    fails = []

    with tempfile.TemporaryDirectory() as root:
        clean_tree(root)
        code, out = run(root)
        if code != 0:
            fails.append(f"clean tree should PASS, got exit {code}:\n{out}")

    with tempfile.TemporaryDirectory() as root:
        clean_tree(root)
        # seeded disease: one title on 4 DIFFERENT fiches
        for i in range(4):
            write(root, f"dup-{i}.html", page("Annecy | Loisirs 74", f"m{i}"))
        code, out = run(root)
        if code == 0 or "title string" not in out:
            fails.append(f"seeded cross-content title dup should FAIL:\n{out}")

    with tempfile.TemporaryDirectory() as root:
        clean_tree(root)
        # seeded disease: one meta on 4 different pages
        for i in range(4):
            write(root, f"m-{i}.html", page(f"T{i}", "Annecy (Haute-Savoie)."))
        code, out = run(root)
        if code == 0 or "meta string" not in out:
            fails.append(f"seeded cross-content meta dup should FAIL:\n{out}")

    with tempfile.TemporaryDirectory() as root:
        clean_tree(root)
        write(root, "naked.html", page("Naked page"))   # indexable, no meta
        code, out = run(root)
        if code == 0 or "WITHOUT a meta" not in out:
            fails.append(f"indexable no-meta page should FAIL:\n{out}")

    if fails:
        print("test_gate_meta_uniqueness: FAIL")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_gate_meta_uniqueness: OK — clean passes; seeded title-dup, "
          "meta-dup and no-meta all trip; cluster + noindex exemptions hold")


if __name__ == "__main__":
    main()
