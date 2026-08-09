#!/usr/bin/env python3
"""Source-existence + entity-match audit — SPECsourceexistenceaudit (S1/S2/S3).

Web-enabled, cached, idempotent, resumable. For every fiche it fetches the
official_site_url, identifies the entity behind it, and decides whether that
source is (a) reachable, (b) an *official* source per the allow/blocklist, and
(c) actually the SAME entity as the fiche — the check a keyword scan can't do.
That's what catches the dangerous class: a B&B / vacation-rental / reseller
wearing the place's exact name (balconduleman.com on a real GR trail).

Four verdicts (§3.1):
  VERIFIED              reachable + official/own-site domain + entity matches
  URL-WRONG-ENTITY      reachable but it's accommodation / reseller / aggregator
                        / a different entity than the fiche (strip → propose → confirm)
  SLUG-COMMUNE-SUSPECT  entity matches but the page's locality contradicts the
                        fiche commune (the Évian-balloon geocode error)
  UNVERIFIED            unreachable / no URL AND no official source found

No-fabrication (hard, §4): proposed_source is non-null ONLY when this job
actually fetched and validated it. It never synthesizes a plausible URL — a
fiche with no findable official source stays UNVERIFIED with proposed_source
null. Existence requires a named corroborator (which URL), recorded in evidence.

Writes (S3, gated behind --apply, OFF by default): emits status:"unverified" +
French verify_flags through apply_studio_patch (no-clobber) — never direct,
never content. Protected fiches and partner blocks are audited and reported but
NEVER flagged or written.

Outputs:
  reports/source-audit.json   machine: [{slug, verdict, evidence, proposed_source, …}]
  reports/source-audit.md     human review queue, sorted by severity

Usage:
  python3 scripts/audit_sources.py                 # audit + write reports
  python3 scripts/audit_sources.py --limit 20      # first 20 (smoke test)
  python3 scripts/audit_sources.py --only slug,slug # specific fiches
  python3 scripts/audit_sources.py --apply          # GATED: emit unverified patches
  python3 scripts/audit_sources.py --no-fetch       # use cache only (offline)
"""
import argparse
import siteconfig  # HANDOFF-73 phase 5: per-site identity
import datetime
import glob
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_DIR = os.path.join(ROOT, "Json")
CACHE_DIR = os.path.join(ROOT, "cache", "source-audit")
REPORT_MD = os.path.join(ROOT, "reports", "source-audit.md")
REPORT_JSON = os.path.join(ROOT, "reports", "source-audit.json")
TODAY = datetime.date.today().isoformat()
UA = f"Mozilla/5.0 (compatible; {siteconfig.WORDMARK}-source-audit/1.0; +{siteconfig.BASE_URL})"
TIMEOUT = 12
RATE_LIMIT_S = 0.4
# Drift (m) beyond which a name-matched entity's stored coordinate implies the
# COMMUNE is wrong (a creation-time geocode error), not just an imprecise pin.
SUSPECT_DRIFT_M = 10000

# Protected partners (§4): a fiche that HOSTS one of these cards, or is the
# protected fiche itself, is audited + reported but NEVER flagged/altered —
# flagging it status:unverified would pull it from the index and break the
# placement gate that guarantees these partners' placements.
PROTECTED_PARTNERS = [re.compile(r"Chez Nous à la Plage", re.I),
                      re.compile(r"Chalet du Tornet", re.I)]
PROTECTED_FICHE_SLUGS = {"domaine-du-tornet"}


def protected_slugs(fiches):
    out = set(PROTECTED_FICHE_SLUGS)
    for d in fiches:
        cards = (d.get("partners") or []) + (d.get("featured_businesses") or [])
        names = " ".join(str(c.get("name", "")) for c in cards)
        if any(rx.search(names) for rx in PROTECTED_PARTNERS):
            out.add(d["slug"])
    return out

# Natural / free public places: an accommodation entity here is always wrong.
NATURAL_CATEGORIES = {"sentier", "cascade", "lac", "plage", "point-de-vue",
                      "voie-verte", "jardin"}

# Official-source allowlist (domain regex). The venue's own genuine site and
# commune/OT sites are ALSO recognised by title/commune markers below.
ALLOW_PATTERNS = [
    r"\.gouv\.fr$", r"(^|\.)ffrandonnee\.fr$", r"(^|\.)onf\.fr$",
    r"(^|\.)wikipedia\.org$", r"(^|\.)openstreetmap\.org$",
    r"(^|\.)data\.gouv\.fr$", r"(^|\.)ign\.fr$", r"(^|\.)geoportail\.gouv\.fr$",
    r"savoie\.fr$",          # hautesavoie.fr, savoie.fr, patrimoines.savoie.fr
    r"mairie", r"office.?de.?tourisme", r"^ot-", r"-ot\.", r"natura2000",
    r"sdis\d", r"\.cci\.fr$", r"-tourisme\.", r"tourisme-",
]

# Curated HS institutional / OT / resort / public-manager domains — official
# sources per §3.2 ("commune/mairie sites, OT") even when their page title
# (covering many places) doesn't name-match a single fiche.
OFFICIAL_DOMAINS = {
    "sila.fr", "cen-haute-savoie.org", "cgn.ch", "asters.asso.fr",
    "lesgets.com", "laclusaz.com", "avoriaz.com", "chatel.com", "samoens.com",
    "leshouches.com", "legrandbornand.com", "alpesduleman.com", "lac-annecy.com",
    "destination-leman.com", "thononlesbains.com", "annecy.fr", "manigod.com",
    "morzine-avoriaz.com", "saint-gervais.com", "chamonix.com", "megeve.com",
    "lescarroz.com", "praz-de-lys-sommand.com", "valdarly-montblanc.com",
}

# Invalid-source blocklist: accommodation, reseller, aggregator, social.
# Matched by exact domain or dot-boundary suffix (so 'x.com' never matches
# 'chamonix.com', 'tiqets.' → 'tiqets.com', etc.).
BLOCK_DOMAINS = [
    "booking.com", "airbnb.com", "airbnb.fr", "abritel.fr", "expedia.com",
    "expedia.fr", "hotels.com", "agoda.com", "gites-de-france.com",
    "gite-de-france.com", "tripadvisor.com", "tripadvisor.fr", "yelp.com",
    "yelp.fr", "getyourguide.com", "getyourguide.fr", "viator.com", "tiqets.com",
    "visorando.com", "komoot.com", "komoot.fr", "alltrails.com", "facebook.com",
    "instagram.com", "twitter.com", "x.com", "youtube.com", "linktr.ee",
    "pinterest.com", "pinterest.fr",
]

# RENTAL/B&B title signals — the dangerous "wears the place's name" class. Kept
# rental-specific so a tourism/OT page that merely *mentions* hotels doesn't
# trip it. Checked against the page TITLE only.
RENTAL_TITLE_KW = [
    "chambre d'hôte", "chambres d'hôtes", "chambre d hote", "bed and breakfast",
    "location d'appartement", "locations d'appartement", "location de vacances",
    "locations de vacances", "appartement à louer", "appartements à louer",
    "location saisonnière", "meublé de tourisme", "chalet à louer",
    "gîte ", "gîtes ", "location de gîte", "résidence de tourisme",
]
# Official entity markers in the page title (commune / OT / state sites).
OFFICIAL_TITLE_KW = ["office de tourisme", "mairie de", "mairie d'", "commune de",
                     "ville de", "syndicat d'initiative", "communauté de communes",
                     "parc naturel", "réserve naturelle", "office national des forêts"]
# Broader lodging terms. A free natural place (trail/waterfall/lake/viewpoint)
# whose "official" site is a hotel/camping/auberge is a wrong-entity collision —
# even when the domain shares a word ('leman') with the place (hotel-leman.fr on
# a GR trail). Checked on the TITLE for NATURAL_CATEGORIES only.
LODGING_TITLE_KW = ["hôtel", "hotel", "camping", "auberge", "résidence de tourisme",
                    "village vacances", "club vacances", "spa & "]
RESELLER_KW = ["réservez vos billets", "comparez les prix", "meilleur prix garanti",
               "book your tickets", "réservation en ligne d'activités"]

STOP = {"de", "la", "le", "les", "du", "des", "d", "l", "a", "au", "aux", "et",
        "en", "sur", "sous", "the", "of", "and", "saint", "sainte", "st"}


# ── text utils ──────────────────────────────────────────────────────────────
def deaccent(s):
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()


def tokens(s):
    return {t for t in re.findall(r"[a-z0-9]+", deaccent(s)) if t not in STOP and len(t) > 2}


def overlap(a, b):
    ta = tokens(a)
    return len(ta & tokens(b)) / len(ta) if ta else 0.0


def fr_name(d):
    return (d.get("i18n", {}).get("fr", {}) or {}).get("name") or d["slug"]


# ── fetch with on-disk cache ────────────────────────────────────────────────
def fetch(url, no_fetch=False):
    """Return a cached/extracted signal dict for url. Cache keyed by URL hash so
    re-runs are idempotent and don't re-hit the network."""
    key = hashlib.sha1(url.encode()).hexdigest()
    cpath = os.path.join(CACHE_DIR, f"{key}.json")
    if os.path.exists(cpath):
        with open(cpath, encoding="utf-8") as fh:
            return json.load(fh)
    if no_fetch:
        return {"url": url, "ok": False, "http": None, "error": "not cached", "title": "",
                "desc": "", "final_url": "", "text": ""}
    rec = {"url": url, "fetched": TODAY}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read(300000).decode("utf-8", "ignore")
            rec["http"] = r.getcode()
            rec["final_url"] = r.geturl()
        t = re.search(r"<title[^>]*>(.*?)</title>", raw, re.S | re.I)
        rec["title"] = html.unescape(re.sub(r"\s+", " ", t.group(1)).strip()) if t else ""
        de = re.search(r'name=["\']description["\'][^>]*content=["\']([^"\']+)', raw, re.I)
        rec["desc"] = html.unescape(de.group(1).strip()) if de else ""
        sn = re.search(r'og:site_name["\'][^>]*content=["\']([^"\']+)', raw, re.I)
        rec["site_name"] = html.unescape(sn.group(1).strip()) if sn else ""
        body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
        body = html.unescape(re.sub(r"<[^>]+>", " ", body))
        rec["text"] = re.sub(r"\s+", " ", body).lower()[:20000]
        rec["ok"] = 200 <= rec["http"] < 400
    except Exception as e:  # noqa: BLE001
        rec.update({"ok": False, "http": getattr(e, "code", None),
                    "error": type(e).__name__ + ": " + str(e)[:120],
                    "title": "", "desc": "", "site_name": "", "final_url": "", "text": ""})
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cpath, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, ensure_ascii=False)
    time.sleep(RATE_LIMIT_S)
    return rec


def domain_of(url):
    m = re.match(r"https?://([^/]+)", url or "")
    return (m.group(1).lower().replace("www.", "") if m else "")


def is_allow(dom):
    return any(re.search(p, dom) for p in ALLOW_PATTERNS)


def is_block(dom):
    return any(dom == b or dom.endswith("." + b) for b in BLOCK_DOMAINS)


def domain_name_match(name, dom):
    """A significant fiche-name token (≥4 chars) appears in the domain → the
    site is very likely the venue's own (planards.fr ↔ 'Les Planards')."""
    host = re.sub(r"[^a-z0-9]", "", dom.split(".")[0])
    return any(len(t) >= 4 and t in host for t in tokens(name))


# ── classification ──────────────────────────────────────────────────────────
def classify(d, communes, no_fetch=False):
    """Return dict: verdict, evidence, proposed_source, domain, http."""
    slug = d["slug"]
    name = fr_name(d)
    cat = d.get("category", "")
    commune = d.get("commune", "")
    url = d.get("official_site_url")

    if not url:
        return _v("UNVERIFIED", f"Aucun official_site_url. Existence non corroborée "
                  f"par une source officielle.", None, "", None)

    dom = domain_of(url)
    if is_block(dom):
        return _v("URL-WRONG-ENTITY", f"Domaine sur liste noire ({dom}) — "
                  f"hébergement / revendeur / agrégateur / réseau social, pas la source officielle.",
                  None, dom, None)

    rec = fetch(url, no_fetch=no_fetch)
    http = rec.get("http")
    if not rec.get("ok"):
        return _v("UNVERIFIED", f"URL injoignable ({dom}, http={http}, "
                  f"{rec.get('error','')}). Existence non corroborée.", None, dom, http)

    title = rec.get("title", "")
    title_l = title.lower()
    blob = f"{title} {rec.get('desc','')} {rec.get('site_name','')}".lower()
    page_id = f"{title} {rec.get('site_name','')}"
    name_ov = overlap(name, page_id)

    # ---- official-source recognition (beyond the domain allowlist) ----
    commune_root = deaccent(commune).split("-")[0]
    commune_in_domain = len(commune_root) >= 4 and commune_root in re.sub(r"[^a-z0-9]", "", dom)
    official_title = any(k in title_l for k in OFFICIAL_TITLE_KW)
    official_domain = dom in OFFICIAL_DOMAINS or any(dom.endswith("." + o) for o in OFFICIAL_DOMAINS)
    official = is_allow(dom) or official_title or commune_in_domain or official_domain

    # ---- 1. the dangerous class: a RENTAL/B&B wearing the place's name ----
    # Checked on the TITLE and BEFORE any name/domain match, because the B&B's
    # domain literally contains the trail name (balconduleman.com). Skipped when
    # the page is itself an official commune/OT site.
    rental = [k for k in RENTAL_TITLE_KW if k in title_l]
    if cat in NATURAL_CATEGORIES:
        rental = rental + [k for k in LODGING_TITLE_KW if k in title_l]
    if rental and not official:
        return _v("URL-WRONG-ENTITY",
                  f"La page « {title[:70]} » est une location/hébergement (signaux: "
                  f"{', '.join(rental)}) — entité différente du lieu « {name} » ({cat}). "
                  f"URL à retirer.", None, dom, http)
    reseller = [k for k in RESELLER_KW if k in blob]
    if reseller and not official:
        return _v("URL-WRONG-ENTITY",
                  f"Page de revente/agrégateur (signaux: {', '.join(reseller)}) — pas la "
                  f"source officielle.", None, dom, http)

    # ---- 2. entity confirmation ----
    entity_ok = official or name_ov >= 0.34 or domain_name_match(name, dom)
    if not entity_ok:
        return _v("URL-WRONG-ENTITY",
                  f"Page joignable ({dom}) mais l'entité « {title[:60]} » ne correspond pas "
                  f"clairement au lieu « {name} » (recouvrement {name_ov:.2f}). À vérifier.",
                  None, dom, http)

    # ---- 3. entity confirmed → is the stored COMMUNE trustworthy? ----
    # Only the precise signal: the geo lane measured a huge drift between the
    # stored coordinate and where Google places this name-matched entity → the
    # commune is a creation-time geocode error (Évian-balloon: 65 km), not just
    # an imprecise pin. (Title-locality heuristics dropped — too noisy: a venue
    # in Poisy legitimately reads "Annecy".)
    drift = (((d.get("google_check") or {}).get("gps_drift_m"))
             or ((d.get("freshness") or {}).get("gps_drift_m")))
    commune_in_title = len(commune_root) >= 4 and commune_root in deaccent(title)
    if drift is not None and drift > SUSPECT_DRIFT_M and not commune_in_title:
        # Huge drift AND the page title does not confirm the commune. If the
        # title DOES name the commune (thononlesbains.com → "Thonon"), the drift
        # is the geo lane's wrong-match noise, not a commune error — leave it.
        return _v("SLUG-COMMUNE-SUSPECT",
                  f"L'entité correspond (« {title[:55]} ») mais la position stockée est à "
                  f"{int(drift/1000)} km de l'entité Google et le titre ne confirme pas la "
                  f"commune ({commune}) — erreur de géocodage probable. Vérifier ; ne pas "
                  f"renommer le slug automatiquement.", url, dom, http)

    if official:
        return _v("VERIFIED", f"Source officielle/propre ({dom}) joignable (http {http}), "
                  f"entité corroborée.", url, dom, http)
    return _v("VERIFIED", f"Site propre du lieu ({dom}) joignable (http {http}); l'entité "
              f"correspond à « {name} » (recouvrement {name_ov:.2f}).", url, dom, http)


def _v(verdict, evidence, proposed, domain, http):
    return {"verdict": verdict, "evidence": evidence,
            "proposed_source": proposed, "domain": domain, "http": http}


SEVERITY = {"URL-WRONG-ENTITY": 0, "SLUG-COMMUNE-SUSPECT": 1, "UNVERIFIED": 2, "VERIFIED": 3}


def emit_unverified_patch(slug, verdict, evidence):
    """Write a Studio patch (status:unverified + verify_flags) and apply it via
    apply_studio_patch (no-clobber). Only called under --apply, never for
    protected fiches."""
    flag = {"URL-WRONG-ENTITY": "Source non officielle (entité différente) — à revérifier.",
            "UNVERIFIED": "Existence non corroborée par une source officielle — à revérifier.",
            "SLUG-COMMUNE-SUSPECT": "Commune/localisation à confirmer (géocodage suspect)."}.get(verdict, "À revérifier.")
    patch = {"slug": slug, "source": "audit_sources.py",
             "patch": {"status": "unverified",
                       "verify_flags": [f"[audit {TODAY}] {flag}", evidence[:200]]}}
    ppath = os.path.join(CACHE_DIR, f"_patch-{slug}.json")
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(ppath, "w", encoding="utf-8") as fh:
        json.dump(patch, fh, ensure_ascii=False, indent=2)
    out = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "apply_studio_patch.py"), ppath],
                         capture_output=True, text=True, cwd=ROOT)
    return out.returncode == 0, (out.stdout + out.stderr).strip()


def main():
    ap = argparse.ArgumentParser(description="Audit fiche sources for existence + entity match.")
    ap.add_argument("--json-dir", default=JSON_DIR)
    ap.add_argument("--limit", type=int, default=0, help="Audit only the first N fiches.")
    ap.add_argument("--only", default="", help="Comma-separated slugs to audit.")
    ap.add_argument("--no-fetch", action="store_true", help="Use cache only (no network).")
    ap.add_argument("--apply", action="store_true",
                    help="GATED: write status:unverified patches via apply_studio_patch.")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.json_dir, "*.json")))
    fiches = [json.load(open(f, encoding="utf-8")) for f in files]
    communes = sorted({d.get("commune") for d in fiches if d.get("commune")})

    protected = protected_slugs(fiches)
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    sel = [d for d in fiches if (not only or d["slug"] in only)]
    if args.limit:
        sel = sel[:args.limit]

    results = []
    for i, d in enumerate(sel, 1):
        r = classify(d, communes, no_fetch=args.no_fetch)
        r["slug"] = d["slug"]
        r["name"] = fr_name(d)
        r["commune"] = d.get("commune", "")
        r["category"] = d.get("category", "")
        r["url"] = d.get("official_site_url")
        r["protected"] = d["slug"] in protected
        results.append(r)
        if i % 25 == 0 or i == len(sel):
            print(f"  …{i}/{len(sel)} audited", file=sys.stderr)

    results.sort(key=lambda r: (SEVERITY.get(r["verdict"], 9), r["slug"]))
    counts = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1

    # ---- write reports ----
    os.makedirs(os.path.dirname(REPORT_JSON), exist_ok=True)
    with open(REPORT_JSON, "w", encoding="utf-8") as fh:
        json.dump({"generated": TODAY, "total": len(results), "counts": counts,
                   "results": results}, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    lines = ["# Source-existence + entity-match audit", "",
             f"_Generated by `scripts/audit_sources.py` · {len(results)} fiches audited._", "",
             "| verdict | count |", "|---|---|"]
    for v in ("URL-WRONG-ENTITY", "SLUG-COMMUNE-SUSPECT", "UNVERIFIED", "VERIFIED"):
        lines.append(f"| {v} | {counts.get(v, 0)} |")
    lines += ["", "> `--apply` is OFF: no fiche has been flagged. Proposed sources are non-null "
              "only where the job fetched and validated one (no-fabrication).", ""]
    for v in ("URL-WRONG-ENTITY", "SLUG-COMMUNE-SUSPECT", "UNVERIFIED"):
        bucket = [r for r in results if r["verdict"] == v]
        lines.append(f"## {v} ({len(bucket)})")
        lines.append("")
        if not bucket:
            lines.append("_none_\n"); continue
        lines.append("| slug | commune | url | evidence | proposed |")
        lines.append("|---|---|---|---|---|")
        for r in bucket:
            tag = " 🛡️" if r["protected"] else ""
            lines.append(f"| {r['slug']}{tag} | {r['commune']} | {r['domain'] or '—'} | "
                         f"{r['evidence']} | {r['proposed_source'] or '—'} |")
        lines.append("")
    lines.append(f"## VERIFIED ({counts.get('VERIFIED', 0)})\n\n_Listed in source-audit.json._\n")
    with open(REPORT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    print(f"audit_sources: {len(results)} fiches → " +
          " · ".join(f"{v}={counts.get(v,0)}" for v in
                     ("VERIFIED", "URL-WRONG-ENTITY", "SLUG-COMMUNE-SUSPECT", "UNVERIFIED")))
    print(f"  reports/source-audit.md + .json written.")

    if args.apply:
        flaggable = [r for r in results if r["verdict"] != "VERIFIED" and not r["protected"]]
        print(f"\n  --apply: flagging {len(flaggable)} fiche(s) status:unverified "
              f"({sum(r['protected'] for r in results)} protected skipped)…")
        for r in flaggable:
            ok, msg = emit_unverified_patch(r["slug"], r["verdict"], r["evidence"])
            print(f"    {'✓' if ok else '✗'} {r['slug']}: {msg.splitlines()[-1] if msg else ''}")


if __name__ == "__main__":
    main()
