#!/usr/bin/env python3
"""
Phase 1: fix the homepage Saint-Jorioz badge (Payant -> Gratuit, localized)
         on all 5 homepages (the card body is free year-round; seasonal fee
         lives on its page).
Phase 2: move the Plage de Saint-Jorioz card to FIRST in the Lac d'Annecy
         carousel of /lacs/ and /plages/ (all 5 languages).
"""
import re
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path("/home/user/Loisir-74")
SLUG = "plage-de-saint-jorioz"

# ---- Phase 1: homepage badge text ----
HOMEPAGES = {
    "index.html": ("Payant", "Gratuit"),
    "en/index.html": ("Paid", "Free"),
    "de/index.html": ("Kostenpflichtig", "Kostenlos"),
    "it/index.html": ("A pagamento", "Gratuito"),
    "es/index.html": ("De pago", "Gratis"),
}

def fix_home_badge(rel, paid, free):
    p = ROOT / rel
    t = p.read_text(encoding="utf-8")
    # anchor on the card-photo href for saint-jorioz, then its card-tag span
    rx = re.compile(
        r'(href="https://loisirs74\.fr/(?:en/|de/|it/|es/)?' + re.escape(SLUG)
        + r'"[^>]*class="card-photo">(?:(?!</a>).)*?<span class="card-tag">)'
        + re.escape(paid) + r'(</span>)',
        re.DOTALL,
    )
    t2, n = rx.subn(lambda m: m.group(1) + free + m.group(2), t, count=1)
    p.write_text(t2, encoding="utf-8")
    return n

# ---- Phase 2: reorder saint-jorioz first in the annecy carousel ----
HUBS = ["lacs/index.html", "en/lakes/index.html", "de/seen/index.html",
        "it/laghi/index.html", "es/lagos/index.html",
        "plages/index.html", "en/beaches/index.html", "de/straende/index.html",
        "it/spiagge/index.html", "es/playas/index.html"]

def reorder_first(rel):
    p = ROOT / rel
    text = p.read_text(encoding="utf-8")
    soup = BeautifulSoup(text, "html.parser")
    sec = soup.find("div", attrs={"data-lac": "annecy"})
    card = None
    for c in sec.select("article.card"):
        a = c.select_one("a.title")
        if a and a["href"].rstrip("/").split("/")[-1] == SLUG:
            card = c
            break
    card_str = str(card)
    if card_str not in text:
        raise SystemExit(f"{rel}: card_str not found verbatim")
    # already first?
    first = sec.select_one("article.card")
    if first is str and first is card:
        return 0
    # remove (with its leading newline) and reinsert right after the carousel open
    text2 = text.replace("\n" + card_str, "", 1)
    ai = text2.find('data-lac="annecy">')
    ci = text2.find('<div class="carousel">', ai) + len('<div class="carousel">')
    text2 = text2[:ci] + "\n" + card_str + text2[ci:]
    if text2 == text:
        return 0
    p.write_text(text2, encoding="utf-8")
    return 1

def main():
    print("Phase 1 — homepage badges")
    for rel, (paid, free) in HOMEPAGES.items():
        print(f"  {rel:16s} flipped={fix_home_badge(rel, paid, free)}")
    print("Phase 2 — reorder saint-jorioz first in lake hubs")
    for rel in HUBS:
        print(f"  {rel:24s} moved={reorder_first(rel)}")

if __name__ == "__main__":
    main()
