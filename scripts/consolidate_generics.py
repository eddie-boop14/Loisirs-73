#!/usr/bin/env python3
"""Phase 1 of the hero handoff (5bae41e baseline) — move every
`generique-*.{jpg,webp}` out of per-hub `img/<hub>/` folders into the
canonical `img/generique/`. Asserts content equality when a basename
already exists at the canonical location (safety check). Removes the
per-hub copies after the canonical copy is in place.

Also rewrites every stale `/img/<hub>/generique-*.{jpg,webp}` reference
in HTML + api/lieux.json + data/image-hub-map.json to the canonical
`/img/generique/<file>` path. The homepage extracts cards verbatim
from its existing HTML, so any stale per-hub generic URLs there must
be patched explicitly — JSON edits alone aren't enough.
"""
import glob
import hashlib
import json
import os
import re
import shutil
from pathlib import Path

CANON = "img/generique"


def md5(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()


def main():
    os.makedirs(CANON, exist_ok=True)
    # --- jpg ---
    seen = {}
    for f in glob.glob("img/*/generique-*.jpg"):
        if Path(f).parent.name == "generique":
            continue
        name = os.path.basename(f)
        dest = os.path.join(CANON, name)
        if os.path.exists(dest):
            assert md5(f) == md5(dest), f"CONTENT CONFLICT {name}"
        elif name in seen:
            assert md5(f) == md5(seen[name]), f"CONTENT CONFLICT {name}"
        else:
            shutil.copy2(f, dest)
            seen[name] = dest
    for f in glob.glob("img/*/generique-*.jpg"):
        if Path(f).parent.name != "generique":
            os.remove(f)
    # --- webp ---
    for f in glob.glob("img/*/generique-*.webp"):
        if Path(f).parent.name == "generique":
            continue
        name = os.path.basename(f)
        dest = os.path.join(CANON, name)
        if os.path.exists(dest):
            assert md5(f) == md5(dest), f"CONTENT CONFLICT {name}"
        else:
            shutil.copy2(f, dest)
        os.remove(f)
    n_jpg = len(glob.glob(f"{CANON}/generique-*.jpg"))
    n_webp = len(glob.glob(f"{CANON}/generique-*.webp"))
    stray_jpg = [f for f in glob.glob("img/*/generique-*.jpg") if Path(f).parent.name != "generique"]
    stray_webp = [f for f in glob.glob("img/*/generique-*.webp") if Path(f).parent.name != "generique"]
    real_heroes = [f for f in glob.glob("img/*/*-hero.jpg") if Path(f).parent.name != "generique" and "generique-" not in Path(f).name]
    print(f"canonical generics: {n_jpg} jpg + {n_webp} webp")
    print(f"stray per-hub generics remaining: {len(stray_jpg)} jpg, {len(stray_webp)} webp")
    print(f"real per-lieu heros still in place: {len(real_heroes)}")

    # ---- Rewrite stale /img/<hub>/generique-* refs everywhere ----
    # Pattern matches both URL-form ("https://loisirs74.fr/img/x/generique-y.jpg")
    # and root-relative ("/img/x/generique-y.jpg").
    pat = re.compile(r"(/img/)[a-z][a-z0-9-]+(/generique-[a-z0-9_-]+\.(?:jpg|jpeg|webp))")
    repl = r"\1generique\2"
    repo = Path(".")
    rewrites = 0
    touched = 0
    for p in repo.rglob("*"):
        if not p.is_file():
            continue
        if any(x in p.parts for x in ("_site", ".claude", "node_modules", "img")):
            continue
        if p.suffix.lower() not in (".html", ".json", ".js", ".xml", ".txt"):
            continue
        try:
            txt = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, IsADirectoryError):
            continue
        new = pat.sub(repl, txt)
        if new != txt:
            n_here = len(pat.findall(txt))
            rewrites += n_here
            touched += 1
            p.write_text(new, encoding="utf-8")
    print(f"stale per-hub generic-path rewrites: {rewrites} refs across {touched} files")

    # data/image-hub-map.json: drop generique-*.* entries (canonical-only now)
    mpath = Path("data/image-hub-map.json")
    if mpath.exists():
        m = json.loads(mpath.read_text(encoding="utf-8"))
        cleaned = {k: v for k, v in m.items() if not k.startswith("generique-")}
        if cleaned != m:
            mpath.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(f"data/image-hub-map.json: pruned {len(m) - len(cleaned)} generique entries")


if __name__ == "__main__":
    main()
