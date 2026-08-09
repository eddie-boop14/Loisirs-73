#!/usr/bin/env python3
"""Task 3 — generate category-diverse related-fiche carousels.

For every fiche, pick 3 nearest same-category + 3 nearest different-category
neighbours by haversine distance, render the 'À proximité' carousel in
each language, and inject into the HTML (replacing any existing one).
"""
import json, os, re, math
from pathlib import Path
from urllib.parse import quote

ROOT = Path("/home/user/Loisir-74")
LIEUX = json.loads((ROOT / "lieux.json").read_text(encoding="utf-8"))["lieux"]

# Per-lang labels
LABELS = {
    "":    {"kicker": "À proximité", "h2": "À proximité",
            "lead": "D'autres lieux à explorer dans le coin et dans la même catégorie",
            "free": "Gratuit", "paid": "Payant", "route": "Itinéraire", "site": "Site officiel"},
    "de/": {"kicker": "In der Nähe", "h2": "In der Nähe",
            "lead": "Weitere Orte in der Umgebung und in derselben Kategorie",
            "free": "Kostenlos", "paid": "Kostenpflichtig", "route": "Route", "site": "Website"},
    "en/": {"kicker": "Nearby", "h2": "Nearby",
            "lead": "Other places to explore in the area and in the same category",
            "free": "Free", "paid": "Paid", "route": "Directions", "site": "Official site"},
    "es/": {"kicker": "Cerca", "h2": "Cerca",
            "lead": "Otros lugares para explorar en la zona y en la misma categoría",
            "free": "Gratis", "paid": "De pago", "route": "Ruta", "site": "Sitio oficial"},
    "it/": {"kicker": "Nelle vicinanze", "h2": "Nelle vicinanze",
            "lead": "Altri luoghi da esplorare nei dintorni e nella stessa categoria",
            "free": "Gratis", "paid": "A pagamento", "route": "Indicazioni", "site": "Sito ufficiale"},
}

BASE = "https://loisirs74.fr"


def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(p1) * math.cos(p2) * math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def primary_category(lieu):
    cats = lieu.get("categories") or []
    return cats[0] if cats else None


def build_data_index():
    """slug → {category, name[lang], commune[lang], meta_desc[lang], hero_alt[lang],
              hero_image, is_free, lat, lon, official_url}"""
    # Compute per-category centroid (lat/lon means) for fallback when a fiche's
    # own coords are missing — keeps it in the related graph via category proximity.
    centroid = {}
    cat_pts = {}
    for L in LIEUX:
        cat = primary_category(L)
        if cat and L.get("latitude") is not None and L.get("longitude") is not None:
            cat_pts.setdefault(cat, []).append((L["latitude"], L["longitude"]))
    for cat, pts in cat_pts.items():
        centroid[cat] = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    idx = {}
    for L in LIEUX:
        slug = L["slug"]
        cat = primary_category(L)
        if cat is None:
            continue
        lat, lon = L.get("latitude"), L.get("longitude")
        if lat is None or lon is None:
            if cat not in centroid:
                continue
            lat, lon = centroid[cat]
        per_fiche_json = ROOT / "Json" / f"{slug}.json"
        pf = {}
        if per_fiche_json.exists():
            try:
                pf = json.loads(per_fiche_json.read_text(encoding="utf-8"))
            except Exception:
                pf = {}
        i18n = L.get("i18n", {})
        pf_i18n = pf.get("i18n", {})
        # Pull FR strings first so we can detect FR-mirrored locale fields.
        fr_pi = pf_i18n.get("fr", {})
        fr_name = (i18n.get("fr") or {}).get("name") or fr_pi.get("name") or slug
        fr_desc = fr_pi.get("meta_description") or ""
        fr_alt = fr_pi.get("hero_alt") or fr_name
        names, communes, descs, alts = {}, {}, {}, {}
        for lang in ("fr", "de", "en", "es", "it"):
            li = i18n.get(lang, {})
            pi = pf_i18n.get(lang, {})
            names[lang] = li.get("name") or pi.get("name") or slug
            communes[lang] = li.get("commune") or pi.get("commune") or pf.get("commune") or ""
            loc_desc = pi.get("meta_description") or ""
            loc_alt = pi.get("hero_alt") or names[lang]
            # On locale pages, suppress strings that just mirror the FR text
            # (un-translated venues). Real translations come through; FR
            # placeholder text doesn't pollute en/de/it/es cards.
            if lang != "fr":
                if loc_desc == fr_desc:
                    loc_desc = ""
                if loc_alt == fr_alt:
                    loc_alt = names[lang]
            descs[lang] = loc_desc
            alts[lang] = loc_alt
        idx[slug] = {
            "category": cat,
            "names": names,
            "communes": communes,
            "descs": descs,
            "alts": alts,
            "hero_image": pf.get("hero_image") or f"/{slug}-hero.jpg",
            "is_free": L.get("is_free", pf.get("schema_org", {}).get("is_free", False)),
            "lat": lat,
            "lon": lon,
            "official_url": pf.get("official_site_url") or "",
        }
    return idx


def compute_related(target_slug, idx):
    """Return list of 6 slugs: 3 nearest diff-category + 3 nearest same-category."""
    t = idx[target_slug]
    same, diff = [], []
    for slug, d in idx.items():
        if slug == target_slug:
            continue
        dist = haversine(t["lat"], t["lon"], d["lat"], d["lon"])
        bucket = same if d["category"] == t["category"] else diff
        bucket.append((dist, slug))
    same.sort(); diff.sort()
    diff_pick = [s for _, s in diff[:3]]
    same_pick = [s for _, s in same[:3]]
    out = diff_pick + same_pick
    # Backfill if either side is short
    while len(out) < 6:
        if len(diff_pick) < 3 and len(diff) > len(diff_pick):
            extra = diff[len(diff_pick)][1]; diff_pick.append(extra); out.append(extra)
        elif len(same_pick) < 3 and len(same) > len(same_pick):
            extra = same[len(same_pick)][1]; same_pick.append(extra); out.append(extra)
        else:
            break
    return out[:6]


RELATED_CSS = """.related{padding:clamp(2rem,4vw,3.5rem) 0;border-top:1px solid var(--line);margin-bottom:5rem}
.related .wrap{max-width:64rem;margin-inline:auto;padding-inline:clamp(1rem,3vw,2rem)}
.related .kicker{font-size:.8125rem;font-weight:700;color:var(--accent);text-transform:uppercase;letter-spacing:.08em;margin-bottom:.65rem}
.related h2{font-size:clamp(1.3rem,1.1rem + .8vw,1.85rem);line-height:1.15;letter-spacing:-.015em;font-weight:800;margin:0 0 .4rem;color:var(--ink)}
.related .lead{color:var(--ink-soft);max-width:42rem;margin-bottom:1.5rem;font-size:1rem;line-height:1.55}
.related .carousel{display:grid;grid-template-columns:repeat(auto-fill,minmax(15rem,1fr));gap:1rem}
@media(max-width:680px){.related .carousel{display:flex;gap:.85rem;overflow-x:auto;scroll-snap-type:x mandatory;padding-bottom:.5rem;-webkit-overflow-scrolling:touch;scrollbar-width:none}.related .carousel::-webkit-scrollbar{display:none}.related .carousel > .card{flex:0 0 75vw;max-width:18rem;scroll-snap-align:start}}
.related .card{background:var(--surface);border:1px solid var(--line);border-radius:14px;overflow:hidden;display:flex;flex-direction:column;transition:transform .2s,border-color .2s,box-shadow .2s;text-decoration:none;color:inherit}
.related .card:hover{transform:translateY(-3px);border-color:color-mix(in srgb,var(--accent) 30%,var(--line));box-shadow:0 8px 24px -12px rgba(11,13,16,.18)}
.related .card-photo{display:block;aspect-ratio:4/3;background:var(--surface-2);overflow:hidden;position:relative;flex-shrink:0}
.related .card-photo img{width:100%;height:100%;object-fit:cover;display:block;transition:transform .35s}
.related .card:hover .card-photo img{transform:scale(1.03)}
.related .card-tag{position:absolute;top:.6rem;left:.6rem;background:color-mix(in srgb,var(--bg) 85%,transparent);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);color:var(--ink);padding:.2rem .55rem;border-radius:999px;font-size:.7rem;font-weight:700;letter-spacing:.02em}
.related .card-body{padding:.85rem 1rem 1rem;display:flex;flex-direction:column;gap:.35rem;flex:1}
.related .card-body a.title{font-weight:700;font-size:1rem;color:var(--ink);line-height:1.3;letter-spacing:-.005em;text-decoration:none}
.related .card-body a.title:hover{color:var(--accent)}
.related .card-commune{font-size:.78rem;color:var(--ink-mute);display:flex;align-items:center;gap:.3rem}
.related .card-commune svg{width:11px !important;height:11px !important;flex-shrink:0}
.related .card-desc{font-size:.85rem;color:var(--ink-soft);line-height:1.45;margin:.15rem 0 .65rem;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.related .card-actions{display:flex;gap:.4rem;margin-top:auto}
.related .card-actions a{flex:1;display:inline-flex;align-items:center;justify-content:center;gap:.3rem;padding:.5rem .6rem;border-radius:8px;font-size:.78rem;font-weight:600;border:1px solid var(--line);background:var(--bg);color:var(--ink-soft);text-decoration:none;transition:all .2s}
.related .card-actions a:hover{background:var(--accent);color:var(--accent-ink);border-color:var(--accent)}
.related .card-actions a svg{width:13px !important;height:13px !important}"""

PIN_SVG = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
           'stroke-linecap="round" stroke-linejoin="round">'
           '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>'
           '<circle cx="12" cy="10" r="3"/></svg>')
GLOBE_SVG = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
             'stroke-linecap="round" stroke-linejoin="round">'
             '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/>'
             '<path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>')


def _img_src(hero):
    """Normalize hero image src for the card."""
    if not hero:
        return "/og-image.jpg"
    if hero.startswith(("http://", "https://", "/")):
        return hero
    return f"/{hero}"


def render_card(slug, lang_prefix, idx, labels):
    d = idx[slug]
    lang = lang_prefix.rstrip("/") or "fr"
    name = d["names"][lang]
    commune = d["communes"][lang]
    desc = d["descs"][lang]
    alt = d["alts"][lang]
    tag = labels["free"] if d["is_free"] else labels["paid"]
    img_src = _img_src(d["hero_image"])
    referrer = ' referrerpolicy="no-referrer"' if img_src.startswith(("http://", "https://")) else ""
    fiche_url = f"{BASE}/{lang_prefix}{slug}"
    maps_q = quote(f"{name}, {commune}, Haute-Savoie".strip(", "), safe="")
    maps_url = f"https://www.google.com/maps/dir/?api=1&destination={maps_q}"
    desc_html = f'<p class="card-desc">{html_escape(desc)}</p>' if desc else ""
    official = d.get("official_url")
    actions = [
        f'<a href="{maps_url}" target="_blank" rel="noopener">{PIN_SVG}<span>{labels["route"]}</span></a>'
    ]
    if official:
        actions.append(
            f'<a href="{html_attr(official)}" target="_blank" rel="noopener">{GLOBE_SVG}<span>{labels["site"]}</span></a>'
        )
    return (
        f'<article class="card">\n'
        f'    <a href="{fiche_url}" class="card-photo">\n'
        f'      <img src="{html_attr(img_src)}" alt="{html_attr(alt)}" loading="lazy"{referrer}>\n'
        f'      <span class="card-tag">{tag}</span>\n'
        f'    </a>\n'
        f'    <div class="card-body">\n'
        f'      <a href="{fiche_url}" class="title">{html_escape(name)}</a>\n'
        f'      <div class="card-commune">{PIN_SVG}<span>{html_escape(commune)}</span></div>\n'
        f'      {desc_html}\n'
        f'      <div class="card-actions">\n'
        f'        {"".join(actions)}\n'
        f'      </div>\n'
        f'    </div>\n'
        f'  </article>'
    )


def render_related(target_slug, related_slugs, lang_prefix, idx):
    labels = LABELS[lang_prefix]
    cards = "\n".join(render_card(s, lang_prefix, idx, labels) for s in related_slugs)
    return f'''<section class="block related" id="related">
  <style>
{RELATED_CSS}
</style>
  <div class="wrap">
    <p class="kicker">{labels["kicker"]}</p>
    <h2>{labels["h2"]}</h2>
    <p class="lead">{labels["lead"]}</p>
    <div class="carousel">{cards}</div>
  </div>
</section>'''


def html_escape(s):
    import html as h
    return h.escape(str(s or ""), quote=False)


def html_attr(s):
    import html as h
    return h.escape(str(s or ""), quote=True)


RELATED_RE = re.compile(r'<section class="block related".*?</section>', re.DOTALL)
FOOTER_RE = re.compile(r'<footer class="site"')


def patch_file(path, block):
    s = path.read_text(encoding="utf-8")
    if RELATED_RE.search(s):
        s2 = RELATED_RE.sub(lambda m: block, s, count=1)
    else:
        s2, n = FOOTER_RE.subn(block + "\n<footer class=\"site\"", s, count=1)
        if n == 0:
            return False
    path.write_text(s2, encoding="utf-8")
    return True


def main():
    idx = build_data_index()
    print(f"Data index: {len(idx)} fiches with category + lat/lon")
    # Compute related for each
    related_map = {slug: compute_related(slug, idx) for slug in idx}
    # Sanity: bidirectional — each fiche should appear in ≥1 other's related.
    # Loop until stable, since bumping a card off can re-orphan another fiche.
    for iteration in range(6):
        inbound = {s: 0 for s in idx}
        for s, rels in related_map.items():
            for r in rels:
                if r in inbound:
                    inbound[r] += 1
        zero_inbound = [s for s, n in inbound.items() if n == 0]
        if not zero_inbound:
            break
        print(f"  iteration {iteration}: zero-inbound fiches: {len(zero_inbound)}")
        for s in zero_inbound:
            d = idx[s]
            closest, best_dist = None, float("inf")
            for other_slug, other in idx.items():
                if other_slug == s or s in related_map[other_slug]:
                    continue
                dist = haversine(d["lat"], d["lon"], other["lat"], other["lon"])
                if dist < best_dist:
                    best_dist, closest = dist, other_slug
            if closest:
                # append rather than bump-off to preserve other fiches' inbound counts.
                if s not in related_map[closest]:
                    related_map[closest] = related_map[closest][:5] + [s]
    print(f"  final zero-inbound fiches: {len([s for s,n in inbound.items() if n==0])}")
    total_patched = 0
    for slug, rels in related_map.items():
        for lang_prefix in ("", "de/", "en/", "es/", "it/"):
            path = ROOT / f"{lang_prefix}{slug}.html"
            if not path.exists():
                continue
            block = render_related(slug, rels, lang_prefix, idx)
            if patch_file(path, block):
                total_patched += 1
    print(f"Patched: {total_patched} files")


if __name__ == "__main__":
    main()
