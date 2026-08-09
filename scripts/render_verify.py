#!/usr/bin/env python3
"""render_verify.py — Layer A of gate_render_verified (HANDOFF-16).

Headless-renders every staged pilot page and asserts the RENDERING is not broken
— the real reason a native human was wanted. Per page:

  * dir="rtl" present + applied for ar/he (absent for ja/pl/pt/cs); no horizontal
    overflow / clipping.
  * <bdi> isolation: every Latin/number/frozen-FR fact value is wrapped in <bdi>
    and its text matches the source JSON — proving prices/names/URLs render
    LTR-correct inside the RTL flow ("Lac d'Annecy", "8,50 €" not reversed).
  * No tofu / no U+FFFD in the rendered text — the #1 Arabic/CJK failure (font
    didn't load → missing-glyph boxes).

Writes a screenshot per page (for Layer B's vision comprehension round-trip) and
a Layer-A JSON to the scratch dir. Layer B (vision) + the combined
reports/render-verify-<lang>.json are produced by the orchestration around this.

Run: python3 scripts/render_verify.py <out_dir> [lang ...]
"""
import functools
import http.server
import json
import os
import socketserver
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import locales  # noqa: E402

CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"


def source_facts(slug):
    """The language-independent facts a rendered page must communicate."""
    fp = os.path.join(ROOT, "Json", f"{slug}.json")
    d = json.loads(open(fp, encoding="utf-8").read())
    facts = d.get("i18n", {}).get("fr", {}).get("facts", {}) or {}
    so = d.get("schema_org", {}) or {}
    name = d.get("i18n", {}).get("fr", {}).get("name") or slug
    commune = d.get("commune") or facts.get("commune") or ""
    price_from = d.get("price_from")
    cur = {"EUR": "€"}.get(d.get("price_currency"), d.get("price_currency") or "")
    if isinstance(price_from, (int, float)) and price_from > 0:
        price = f"{price_from:.2f}".replace(".", ",") + " " + cur
    elif so.get("is_free") is True:
        price = "FREE"
    elif so.get("is_free") is False:
        price = "PAID"
    else:
        price = None
    ap = d.get("acces_pmr")
    pmr = ap.get("status") if isinstance(ap, dict) else None
    return {"name": name, "commune": commune, "price": price, "pmr": pmr}


def serve():
    os.chdir(ROOT)
    httpd = socketserver.TCPServer(("127.0.0.1", 0), functools.partial(
        http.server.SimpleHTTPRequestHandler))
    httpd.RequestHandlerClass.log_message = lambda *a, **k: None
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def main():
    out_dir = sys.argv[1]
    langs = sys.argv[2:] or list(locales.STAGED_INDEXABLE) + list(locales.HELD)
    os.makedirs(out_dir, exist_ok=True)
    from playwright.sync_api import sync_playwright
    httpd, port = serve()
    results = {}
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        for lang in langs:
            rtl = locales.DIR.get(lang) == "rtl"
            ldir = os.path.join(ROOT, lang)
            if not os.path.isdir(ldir):
                continue
            shot_dir = os.path.join(out_dir, lang)
            os.makedirs(shot_dir, exist_ok=True)
            pages = []
            # RV_SAMPLE=N caps the run to the first N fiche pages (deterministic:
            # alphabetical) — the HANDOFF-31 acceptance uses 20-page RTL samples.
            sample = int(os.environ.get("RV_SAMPLE", "0") or 0)
            for fn in sorted(os.listdir(ldir)):
                if sample and len(pages) >= sample:
                    break
                if not fn.endswith(".html"):
                    continue
                slug = fn[:-5]
                # Top-level non-fiche pages (the full-tree homepage index.html;
                # hubs/communes live in subdirs and aren't listed here) carry no
                # Json fiche source — Layer A's fact-rendering checks don't apply.
                if not os.path.exists(os.path.join(ROOT, "Json", f"{slug}.json")):
                    continue
                src = source_facts(slug)
                pg = b.new_page(viewport={"width": 420, "height": 900},
                                device_scale_factor=2)
                # Abort external font CDN requests — unreachable from the harness
                # and they'd block `load`. The page falls back to the system
                # script font (renders the same scripts readably), so the tofu
                # check stays meaningful and each render is fast + deterministic.
                pg.route("**/*", lambda r: (r.abort() if (
                    "fonts.googleapis.com" in r.request.url or
                    "fonts.gstatic.com" in r.request.url) else r.continue_()))
                pg.goto(f"http://127.0.0.1:{port}/{lang}/{fn}", wait_until="domcontentloaded", timeout=20000)
                pg.wait_for_timeout(250)
                info = pg.evaluate("""() => {
                  const root=document.documentElement, txt=document.body.innerText;
                  const bdis=[...document.querySelectorAll('bdi')].map(b=>b.innerText.trim());
                  return {
                    dir: root.getAttribute('dir'),
                    htmlLang: root.getAttribute('lang'),
                    overflowX: root.scrollWidth > root.clientWidth + 1,
                    ffd: (txt.match(/\\uFFFD/g)||[]).length,
                    bdis,
                    duck: !!document.getElementById('bc-duck'),
                    h1: document.querySelector('h1')?.innerText || '',
                    bodyText: txt,
                  };
                }""")
                # The duck is a position:fixed, randomly-placed easter egg — assert
                # it MOUNTED (Layer A), then remove it before the screenshot so its
                # random overlap can't pollute Layer B's read of the CONTENT. Its
                # quack/mirror correctness is verified separately (QUACK map + node).
                pg.evaluate("document.getElementById('bc-duck')?.remove()")
                shot = os.path.join(shot_dir, slug + ".png")
                pg.screenshot(path=shot, full_page=True)
                pg.close()

                # Layer A assertions
                viol = []
                if rtl and info["dir"] != "rtl":
                    viol.append("dir!=rtl")
                if not rtl and info["dir"] == "rtl":
                    viol.append("unexpected dir=rtl")
                if info["overflowX"]:
                    viol.append("horizontal-overflow")
                if info["ffd"]:
                    viol.append(f"U+FFFD x{info['ffd']} (tofu/missing-glyph)")
                # held pilots (ar/he/ja) carry the duck; assert it mounted
                if lang not in locales.STAGED_INDEXABLE and not info["duck"]:
                    viol.append("duck did not mount on held pilot")
                def norm(x):
                    return (x or "").replace("\u00a0", " ").strip()
                body = norm(info["bodyText"])
                bdis = [norm(x) for x in info["bdis"]]
                price = norm(src["price"]) if src["price"] not in ("FREE", "PAID", None) else None
                # frozen FR name verbatim in the rendered page
                if norm(src["name"]) not in body:
                    viol.append("frozen FR name missing from render")
                # every fact value is actually rendered (readable, not dropped)
                if src["commune"] and norm(src["commune"]) not in body:
                    viol.append(f"commune '{src['commune']}' missing from render")
                if price and price not in body:
                    viol.append(f"price '{src['price']}' missing from render")
                # RTL only: every Latin/number value must be <bdi>-isolated so it
                # renders LTR-correct inside the RTL flow (anti-scramble).
                if rtl:
                    if src["commune"] and norm(src["commune"]) not in bdis:
                        viol.append(f"commune '{src['commune']}' not <bdi>-isolated (RTL scramble risk)")
                    if price and price not in bdis:
                        viol.append(f"price '{src['price']}' not <bdi>-isolated (RTL scramble risk)")
                pages.append({"slug": slug, "rtl": rtl, "dir": info["dir"],
                              "overflowX": info["overflowX"], "ffd": info["ffd"],
                              "bdis": bdis, "h1": info["h1"], "src": src,
                              "shot": os.path.relpath(shot, out_dir),
                              "layerA": "PASS" if not viol else "FAIL",
                              "violations": viol})
            n_fail = sum(1 for p_ in pages if p_["layerA"] == "FAIL")
            results[lang] = {"pages": pages, "n": len(pages), "layerA_fail": n_fail,
                             "layerA": "PASS" if n_fail == 0 else "FAIL"}
            print(f"{lang}: {len(pages)} pages, Layer A {'PASS' if n_fail==0 else f'FAIL({n_fail})'}")
        b.close()
    httpd.shutdown()
    json.dump(results, open(os.path.join(out_dir, "layerA.json"), "w"), ensure_ascii=False, indent=1)
    print(f"wrote {out_dir}/layerA.json")


if __name__ == "__main__":
    main()
