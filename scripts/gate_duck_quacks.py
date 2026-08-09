#!/usr/bin/env python3
"""gate_duck_quacks.py — every published language quacks in its own tongue.

HANDOFF-29: pl/pt/cs published while missing from duck.js's QUACK map, so
their pages silently fell back to FR "Coin coin" — the EN cache bug re-created
on three languages. This gate fails the build whenever a language in the
published roster (locales.VISIBLE) has no entry in the QUACK map, so adding a
language without teaching the duck is a red build, never a silent regression.

Read-only. Exit 1 on any violation.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import locales  # noqa: E402

DUCK = os.path.join(HERE, "duck.js")


def quack_langs():
    src = open(DUCK, encoding="utf-8").read()
    m = re.search(r"var QUACK = \{(.*?)\};", src, re.S)
    if not m:
        return None
    return set(re.findall(r"([a-z]{2}):\s*'", m.group(1)))


def main():
    langs = quack_langs()
    if langs is None:
        print("::error::QUACK map not found in scripts/duck.js")
        sys.exit(1)
    missing = [l for l in locales.VISIBLE if l not in langs]
    print(f"gate_duck_quacks: QUACK covers {sorted(langs)}; published roster {list(locales.VISIBLE)}")
    if missing:
        print(f"::error::{len(missing)} published language(s) would fall back to "
              f"'Coin coin': {missing} — teach the duck before publishing.")
        sys.exit(1)
    print("✓ every published language quacks in its own tongue")


if __name__ == "__main__":
    main()
