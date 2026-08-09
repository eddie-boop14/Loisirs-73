#!/usr/bin/env python3
"""localize_heroes.py — de-hotlink every Wikimedia-hosted hero, self-host it,
and capture a compliant, Commons-authoritative credit (HANDOFF-hero-integrity).

WHY
  79 fiche heroes are served live from `upload.wikimedia.org` on every page
  view. That is (1) against Commons re-use policy, (2) a Core-Web-Vitals /
  LCP tax (third-party DNS+TLS, unoptimised full-size JPG, no WebP), (3)
  fragile (a Commons rename silently breaks the hero in 12 languages), and
  (4) 6 of them carry no credit at all → CC-BY breach. This tool downloads a
  copy into `/img/<hub>/<slug>-hero.jpg`, emits a WebP sibling (the LCP win),
  strips EXIF, and writes the author+licence resolved from the Commons API —
  the authority, never the possibly-stale string already in the fiche.

WHAT IT WILL NOT TOUCH
  * Protected commercial placements (chez-nous-a-la-plage / chalet-du-tornet
    carrying pages, and criq-parc). Hard-coded skip set + a live assertion.
  * Wrong-subject / shared heroes — one Commons file reused across several
    unrelated lieux (5 télécabines, 3 accrobranche, …). Self-hosting a photo
    of somewhere else just entrenches a false visual fact; these are routed
    to Eddie (worklist B), never localised, unless the pair is explicitly
    whitelisted in data/hero-shared-allow.json.

USAGE
  python3 scripts/localize_heroes.py            # --report (default; writes nothing)
  python3 scripts/localize_heroes.py --report
  python3 scripts/localize_heroes.py --apply    # download + rewrite JSON (needs Pillow)

GUARDRAILS (house law — non-negotiable)
  * --report before --apply, always. --report is the default action.
  * Circuit breaker: if >10% of localisation targets fail resolution/fetch,
    --apply ABORTS with ZERO writes (systemic failure, e.g. Commons/API down).
  * Individual CHECK_FAILED → skip that fiche, leave it hotlinked, log it.
    Error ≠ data. A guessed credit is never written.
  * Idempotent: a fiche already pointing at an on-disk local hero is a no-op.
  * Attribution preserved verbatim from Commons. No invented authors.

Read-only in --report. Exit non-zero only on a hard/usage error.
"""
import argparse
import siteconfig  # HANDOFF-73 phase 5: per-site identity
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = Path(HERE).parent
JSON_DIR = ROOT / "Json"
IMG_ROOT = ROOT / "img"

sys.path.insert(0, HERE)
from migrate_to_hub_folders import CATEGORY_TO_PRIMARY_HUB  # noqa: E402  (authoritative category→hub map)

# --- compliance / house constants ------------------------------------------
CREDIT_SEP = " · "
COMMONS_TAG = "Wikimedia Commons"
SHARED_ALLOW = ROOT / "data" / "hero-shared-allow.json"
USER_AGENT = ("Loisirs74-hero-localizer/1.0 "
              f"({siteconfig.BASE_URL}; contact: {siteconfig.CONTACT_EMAIL})")
API = "https://commons.wikimedia.org/w/api.php"

# Protected — hard skip + assertion. The two partner domains mark their
# carrying pages; localising a hero there would shift the page bytes the
# protected-placements gate hashes. criq-parc carries a Chez Nous block.
PROTECTED_SLUGS = {"chez-nous-a-la-plage", "chalet-du-tornet", "criq-parc"}
PROTECTED_DOMAINS = ("cheznousalaplage.com", "chaletdutornet.com")

# Image output policy (only used by --apply).
HERO_MAX_W = 1600          # cap long-edge width; only downscale, never upscale
JPEG_Q = 85
WEBP_Q = 80

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


# --- fiche loading / classification ----------------------------------------
def load_fiches():
    out = []
    for fp in sorted(JSON_DIR.glob("*.json")):
        raw = fp.read_text(encoding="utf-8")
        out.append((fp, json.loads(raw), raw))
    return out


def is_hotlinked(d):
    hi = d.get("hero_image")
    return isinstance(hi, str) and hi.startswith(("http://", "https://", "//"))


def is_protected(slug, raw):
    if slug in PROTECTED_SLUGS:
        return True
    return any(dom in raw for dom in PROTECTED_DOMAINS)


def load_shared_allow():
    """Whitelist of hero URLs (or their Commons filename) legitimately shared
    across fiches — the pairs Eddie has explicitly signed off. Absent file =
    empty whitelist (the safe default: nothing shared is auto-localised)."""
    if not SHARED_ALLOW.exists():
        return set()
    try:
        data = json.loads(SHARED_ALLOW.read_text(encoding="utf-8"))
    except Exception:
        return set()
    keys = set()
    for entry in data.get("allow", []):
        # allow entry may be a URL, a Commons filename, or {"file": ...}
        if isinstance(entry, str):
            keys.add(entry)
        elif isinstance(entry, dict) and entry.get("file"):
            keys.add(entry["file"])
    return keys


def shared_hero_urls(fiches):
    """{normalised-hero-url: [slugs]} for every hotlinked hero used by >1
    fiche. These are the wrong-subject candidates."""
    seen = {}
    for _fp, d, _raw in fiches:
        if not is_hotlinked(d):
            continue
        seen.setdefault(d["hero_image"], []).append(d["slug"])
    return {u: slugs for u, slugs in seen.items() if len(slugs) > 1}


def commons_filename(url):
    """Commons File: title from an upload.wikimedia.org URL (URL-decoded,
    spaces normalised). Returns None if the URL is not a Commons upload."""
    if "upload.wikimedia.org" not in url and "commons" not in url:
        return None
    last = url.rstrip("/").split("/")[-1]
    # thumb URLs end with .../<file>/<width>px-<file> — take the real file
    name = urllib.parse.unquote(last)
    name = name.replace("_", " ").strip()
    return name or None


def target_path(d):
    """Canonical /img/<primary-hub>/<slug>-hero.jpg for a fiche, or None if
    the category has no hub mapping."""
    cat = (d.get("category") or "").strip()
    hub = CATEGORY_TO_PRIMARY_HUB.get(cat)
    if not hub:
        return None
    return f"/img/{hub}/{d['slug']}-hero.jpg"


# --- Commons credit resolution ---------------------------------------------
def _clean(text):
    if not text:
        return ""
    text = TAG_RE.sub("", text)
    text = html.unescape(text)
    text = WS_RE.sub(" ", text).strip()
    # trailing wiki noise ("(talk)", "(page does not exist)")
    text = re.sub(r"\s*\((talk|page does not exist|contribs)[^)]*\)$", "", text, flags=re.I)
    return text.strip()


def resolve_commons_credit(filename, timeout=25):
    """Query the Commons API extmetadata for `filename`. Returns a dict:
      {ok: bool, author, license, credit, reason}
    ok=False (CHECK_FAILED) on any resolution problem — never a guessed value.
    """
    if not filename:
        return {"ok": False, "reason": "not-a-commons-file"}
    q = urllib.parse.urlencode({
        "action": "query", "format": "json", "prop": "imageinfo",
        "iiprop": "extmetadata", "titles": f"File:{filename}",
    })
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
    except Exception as e:
        return {"ok": False, "reason": f"api-error:{type(e).__name__}"}
    pages = (data.get("query") or {}).get("pages") or {}
    if not pages:
        return {"ok": False, "reason": "no-pages"}
    page = next(iter(pages.values()))
    if "missing" in page or "imageinfo" not in page:
        return {"ok": False, "reason": "file-missing-on-commons"}
    em = page["imageinfo"][0].get("extmetadata", {})
    author = _clean((em.get("Artist") or {}).get("value", ""))
    lic = _clean((em.get("LicenseShortName") or {}).get("value", ""))
    attribution_required = str((em.get("AttributionRequired") or {}).get("value", "")).lower() == "true"
    if attribution_required and not author:
        return {"ok": False, "reason": "attribution-required-but-no-author", "license": lic}
    if not lic:
        return {"ok": False, "reason": "no-license", "author": author}
    # Build house credit: Author · Licence · Wikimedia Commons. The author is
    # present for every attribution-required file (guaranteed above) and is
    # dropped only for genuinely attribution-free public-domain files.
    parts = ([author] if author else []) + [lic, COMMONS_TAG]
    credit = CREDIT_SEP.join(parts)
    return {"ok": True, "author": author, "license": lic, "credit": credit}


# --- classification into action buckets ------------------------------------
def classify(fiches, only=None):
    """only: optional set of slugs to consider. Narrows the WORK, never the
    safety checks — `shared` is still computed over every fiche, so a hero
    shared with a fiche outside the filter is still detected and skipped."""
    shared = shared_hero_urls(fiches)
    allow = load_shared_allow()
    buckets = {"localize": [], "protected": [], "shared": [], "unmapped": []}
    for fp, d, raw in fiches:
        if not is_hotlinked(d):
            continue
        slug = d["slug"]
        if only is not None and slug not in only:
            continue
        url = d["hero_image"]
        rec = {"slug": slug, "fp": fp, "url": url, "d": d,
               "credit_now": (d.get("hero_credit") or "").strip(),
               "target": target_path(d), "filename": commons_filename(url)}
        if is_protected(slug, raw):
            buckets["protected"].append(rec)
        elif url in shared and url not in allow and commons_filename(url) not in allow:
            rec["shared_with"] = shared[url]
            buckets["shared"].append(rec)
        elif rec["target"] is None:
            buckets["unmapped"].append(rec)
        else:
            buckets["localize"].append(rec)
    return buckets, shared


# --- reporting --------------------------------------------------------------
def run_report(resolve=True, only=None):
    fiches = load_fiches()
    buckets, shared = classify(fiches, only)
    n = sum(len(v) for v in buckets.values())
    print("=" * 78)
    print(f"localize_heroes --report · {n} hotlinked hero(es) across {len(fiches)} fiches")
    print("=" * 78)

    loc = buckets["localize"]
    print(f"\n▶ LOCALISE ({len(loc)}) — download, self-host, WebP, Commons credit:")
    print(f"  {'slug':<44} {'→ target':<46} credit resolution")
    fails = 0
    resolved = []
    for rec in loc:
        cr = {"ok": None}
        if resolve:
            cr = resolve_commons_credit(rec["filename"])
            time.sleep(0.15)  # be polite to the API
            if not cr["ok"]:
                fails += 1
        rec["resolved"] = cr
        resolved.append(rec)
        if cr.get("ok"):
            mism = "" if _same_credit(rec["credit_now"], cr["credit"]) else "  ⚠ differs from current"
            note = f"✓ {cr['credit']}{mism}"
        elif cr["ok"] is None:
            note = "(not resolved — pass --report with network)"
        else:
            note = f"✗ CHECK_FAILED: {cr.get('reason')}"
        print(f"  {rec['slug']:<44} {rec['target']:<46} {note}")

    if buckets["shared"]:
        print(f"\n▶ SKIP · WRONG-SUBJECT / SHARED ({len(buckets['shared'])}) — route to Eddie (worklist B):")
        by_url = {}
        for rec in buckets["shared"]:
            by_url.setdefault(rec["url"], []).append(rec["slug"])
        for url, slugs in by_url.items():
            print(f"  {commons_filename(url)}")
            print(f"      shared by {len(slugs)}: {', '.join(slugs)}")

    if buckets["protected"]:
        print(f"\n▶ SKIP · PROTECTED partner placement ({len(buckets['protected'])}) — never auto-touched:")
        for rec in buckets["protected"]:
            print(f"  {rec['slug']:<44} {rec['url']}")

    if buckets["unmapped"]:
        print(f"\n▶ SKIP · UNMAPPED category ({len(buckets['unmapped'])}) — no hub folder:")
        for rec in buckets["unmapped"]:
            print(f"  {rec['slug']:<44} category={rec['d'].get('category')!r}")

    if resolve and loc:
        rate = fails / len(loc)
        print(f"\nresolution: {len(loc) - fails}/{len(loc)} ok, {fails} CHECK_FAILED "
              f"({rate:.0%}). Circuit breaker fires at >10%: "
              f"{'WOULD ABORT --apply' if rate > 0.10 else 'ok'}.")
    print("\nnothing written (report is read-only). Review, then: "
          "python3 scripts/localize_heroes.py --apply")
    return buckets


def _same_credit(a, b):
    norm = lambda s: WS_RE.sub(" ", (s or "").lower()).strip()
    return norm(a) == norm(b)


# --- apply ------------------------------------------------------------------
def _process_and_save(img_bytes, jpg_path):
    """Downscale (cap width), strip EXIF, write optimised JPEG + WebP sibling.
    Lazy Pillow import so --report needs no image stack."""
    from io import BytesIO
    from PIL import Image
    im = Image.open(BytesIO(img_bytes))
    im = im.convert("RGB")  # also drops EXIF/ICC by not carrying it forward
    if im.width > HERO_MAX_W:
        h = round(im.height * HERO_MAX_W / im.width)
        im = im.resize((HERO_MAX_W, h), Image.LANCZOS)
    jpg_path.parent.mkdir(parents=True, exist_ok=True)
    im.save(jpg_path, "JPEG", quality=JPEG_Q, optimize=True, progressive=True)
    im.save(jpg_path.with_suffix(".webp"), "WEBP", quality=WEBP_Q, method=6)
    return im.size


def _fetch(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def run_apply(only=None):
    fiches = load_fiches()
    buckets, _shared = classify(fiches, only)
    loc = buckets["localize"]
    print(f"localize_heroes --apply · {len(loc)} localisation target(s)")

    # --- PHASE 1: resolve credit + fetch bytes for every target. No writes. --
    staged, failed = [], []
    for rec in loc:
        # assertion: the protected set must never reach here
        assert rec["slug"] not in PROTECTED_SLUGS, f"protected slug in localize bucket: {rec['slug']}"
        # idempotency: already local + on disk?
        cur = rec["d"].get("hero_image", "")
        if isinstance(cur, str) and cur.startswith("/img/") and (ROOT / cur.lstrip("/")).exists():
            continue
        cr = resolve_commons_credit(rec["filename"])
        if not cr["ok"]:
            failed.append((rec["slug"], f"credit:{cr.get('reason')}"))
            continue
        try:
            data = _fetch(rec["url"])
        except Exception as e:
            failed.append((rec["slug"], f"fetch:{type(e).__name__}"))
            continue
        rec["bytes"], rec["credit"] = data, cr["credit"]
        staged.append(rec)
        time.sleep(0.15)

    attempted = len(staged) + len(failed)
    if attempted == 0:
        print("nothing to do — every target already localised (idempotent no-op).")
        return 0

    # --- circuit breaker: systemic failure → abort with ZERO writes ---------
    rate = len(failed) / attempted
    print(f"phase 1: staged={len(staged)} failed={len(failed)} of {attempted} attempted ({rate:.0%})")
    if rate > 0.10:
        print(f"✗ CIRCUIT BREAKER: {rate:.0%} > 10% failed — aborting with ZERO writes.")
        for slug, why in failed:
            print(f"    ✗ {slug}: {why}")
        return 1

    # --- PHASE 2: write images + rewrite JSON for staged successes ----------
    written = 0
    for rec in staged:
        target = rec["target"]
        size = _process_and_save(rec["bytes"], ROOT / target.lstrip("/"))
        d = rec["d"]
        d["hero_image"] = target
        d["hero_credit"] = rec["credit"]
        rec["fp"].write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written += 1
        print(f"  ✓ {rec['slug']}: {target}  {size[0]}×{size[1]}  |  {rec['credit']}")

    if failed:
        print(f"\nskipped (left hotlinked, logged) — {len(failed)}:")
        for slug, why in failed:
            print(f"    ✗ {slug}: {why}")
    print(f"\ndone: {written} localised. next: python3 scripts/build_all.py --no-site "
          "&& python3 scripts/gate_hero_integrity.py")
    return 0


def main():
    ap = argparse.ArgumentParser(description="De-hotlink Wikimedia heroes; self-host + credit.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--report", action="store_true", help="(default) resolve + tabulate, write nothing")
    g.add_argument("--apply", action="store_true", help="download, self-host, rewrite JSON")
    ap.add_argument("--no-resolve", action="store_true", help="report without Commons API calls (offline)")
    ap.add_argument("--only", metavar="SLUG[,SLUG...]",
                    help="restrict to these fiche slugs (the shared/wrong-subject "
                         "detector still runs against the whole corpus)")
    args = ap.parse_args()
    only = {x.strip() for x in args.only.split(',') if x.strip()} if args.only else None

    if args.apply:
        return run_apply(only)
    run_report(resolve=not args.no_resolve, only=only)
    return 0


if __name__ == "__main__":
    sys.exit(main())
