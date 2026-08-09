#!/usr/bin/env python3
"""Split scratchpad/segments-<lang>.json into fixed-size chunk files for the
translator fan-out, and assemble the per-chunk outputs back into
scratchpad/cache-<lang>.json. Usage:

    llm_chunk.py split   <lang> [size]   # → scratchpad/chunks/<lang>/chunk-NNN.json
    llm_chunk.py assemble <lang>          # out/<lang>/chunk-*.json → cache-<lang>.json
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRATCH = ROOT / "scratchpad"


def split(lang, size):
    segs = json.loads((SCRATCH / f"segments-{lang}.json").read_text("utf-8"))
    d = SCRATCH / "chunks" / lang
    d.mkdir(parents=True, exist_ok=True)
    n = 0
    for i in range(0, len(segs), size):
        chunk = segs[i:i + size]
        (d / f"chunk-{n:03d}.json").write_text(
            json.dumps(chunk, ensure_ascii=False, indent=0) + "\n", "utf-8")
        n += 1
    print(f"[{lang}] {len(segs)} segments → {n} chunk(s) of {size} in {d}")
    return n


def assemble(lang):
    outdir = SCRATCH / "out" / lang
    # MERGE into the existing cache — never rebuild from scratch, or good
    # translations outside the current work-list chunks would be lost.
    cf = SCRATCH / f"cache-{lang}.json"
    cache = json.loads(cf.read_text("utf-8")) if cf.exists() else {}
    missing_files = []
    seg_files = sorted((SCRATCH / "chunks" / lang).glob("chunk-*.json"))
    for cf in seg_files:
        of = outdir / cf.name
        if not of.exists():
            missing_files.append(cf.name)
            continue
        pairs = json.loads(of.read_text("utf-8"))
        # each out file is {masked_src: translation}
        cache.update(pairs)
    (SCRATCH / f"cache-{lang}.json").write_text(
        json.dumps(cache, ensure_ascii=False) + "\n", "utf-8")
    print(f"[{lang}] assembled {len(cache)} translations from "
          f"{len(seg_files) - len(missing_files)}/{len(seg_files)} chunks "
          f"→ cache-{lang}.json")
    if missing_files:
        print(f"[{lang}] MISSING {len(missing_files)} chunk output(s): "
              f"{', '.join(missing_files[:10])}{' …' if len(missing_files) > 10 else ''}")


if __name__ == "__main__":
    cmd, lang = sys.argv[1], sys.argv[2]
    if cmd == "split":
        split(lang, int(sys.argv[3]) if len(sys.argv) > 3 else 120)
    elif cmd == "assemble":
        assemble(lang)
