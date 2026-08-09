#!/usr/bin/env python3
"""apply_job3_faq_closeout.py — HANDOFF-faq-closeout §3/§4.

Appends the two deferred FAQ answers (Acro'Filet, Explor Games) as the last FAQ
entry in both fiches, all 12 locales, VERBATIM from the handoff §3 tables.
Content is copied from the fiches' own activities blocks — nothing sourced,
translated or fabricated.

Rules honored: no price in the Acro'Filet answer (§3 A); no Paysalp site count in
the Explor Games answer (§3 B); faq[0..7] untouched; tactiq never touched;
no new pages/URLs/sitemap. Idempotent. --report writes nothing.
"""
import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_DIR = os.path.join(ROOT, "Json")

ACRO = {
    "fr": ("Qu'est-ce que l'Acro'Filet à Acro'Aventures Reignier ?",
           "L'Acro'Filet est une structure de 12 m de haut composée de deux étages de filets suspendus : zones de ballons géants, piscine à balles, trampolines et toboggan. L'activité se pratique sans harnais, s'adresse à tout âge et dure de 1 à 2 h."),
    "en": ("What is the Acro'Filet at Acro'Aventures Reignier?",
           "The Acro'Filet is a 12 m high structure with two levels of suspended nets: giant ball zones, a ball pit, trampolines and a slide. It is done without a harness, is open to all ages and lasts 1 to 2 hours."),
    "de": ("Was ist das Acro'Filet bei Acro'Aventures Reignier?",
           "Das Acro'Filet ist eine 12 m hohe Konstruktion mit zwei Ebenen hängender Netze: Bereiche mit Riesenbällen, ein Bällebad, Trampoline und eine Rutsche. Die Aktivität wird ohne Klettergurt ausgeübt, ist für jedes Alter geeignet und dauert 1 bis 2 Stunden."),
    "it": ("Che cos'è l'Acro'Filet ad Acro'Aventures Reignier?",
           "L'Acro'Filet è una struttura alta 12 m con due piani di reti sospese: zone con palloni giganti, piscina di palline, trampolini e scivolo. L'attività si svolge senza imbracatura, è aperta a tutte le età e dura da 1 a 2 ore."),
    "es": ("¿Qué es el Acro'Filet en Acro'Aventures Reignier?",
           "El Acro'Filet es una estructura de 12 m de altura con dos pisos de redes suspendidas: zonas de balones gigantes, piscina de bolas, camas elásticas y tobogán. La actividad se practica sin arnés, está abierta a todas las edades y dura de 1 a 2 h."),
    "nl": ("Wat is het Acro'Filet bij Acro'Aventures Reignier?",
           "Het Acro'Filet is een 12 m hoge constructie met twee verdiepingen hangende netten: zones met reuzenballen, een ballenbak, trampolines en een glijbaan. De activiteit gebeurt zonder harnas, is geschikt voor alle leeftijden en duurt 1 tot 2 uur."),
    "pl": ("Czym jest Acro'Filet w Acro'Aventures Reignier?",
           "Acro'Filet to konstrukcja o wysokości 12 m z dwoma poziomami wiszących siatek: strefy z gigantycznymi piłkami, basen z kulkami, trampoliny i zjeżdżalnia. Aktywność odbywa się bez uprzęży, jest dostępna dla każdego wieku i trwa od 1 do 2 godzin."),
    "pt": ("O que é o Acro'Filet no Acro'Aventures Reignier?",
           "O Acro'Filet é uma estrutura de 12 m de altura com dois andares de redes suspensas: zonas de bolas gigantes, piscina de bolas, trampolins e escorrega. A atividade é praticada sem arnês, é aberta a todas as idades e dura de 1 a 2 h."),
    "cs": ("Co je Acro'Filet v Acro'Aventures Reignier?",
           "Acro'Filet je 12 m vysoká konstrukce se dvěma patry zavěšených sítí: zóny s obřími míči, bazén s míčky, trampolíny a skluzavka. Aktivita se provádí bez úvazku, je určena pro všechny věkové kategorie a trvá 1 až 2 hodiny."),
    "ja": ("Acro'Aventures Reignier の Acro'Filet とは何ですか？",
           "Acro'Filet は高さ12メートルの構造物で、吊り下げられたネットが2層になっています。巨大ボールのゾーン、ボールプール、トランポリン、滑り台があります。ハーネスなしで楽しめ、年齢を問わず参加でき、所要時間は1〜2時間です。"),
    "ar": ("ما هو Acro'Filet في Acro'Aventures Reignier؟",
           "Acro'Filet هو هيكل بارتفاع 12 مترًا يضم طابقين من الشِّباك المعلَّقة: مناطق كرات عملاقة، وحوض كرات، وترامبولين، وزحليقة. يُمارَس النشاط دون حزام أمان، وهو متاح لجميع الأعمار، وتتراوح مدته بين ساعة وساعتين."),
    "he": ("מהו ה-Acro'Filet ב-Acro'Aventures Reignier?",
           "ה-Acro'Filet הוא מבנה בגובה 12 מטר ובו שתי קומות של רשתות תלויות: אזורי כדורים ענקיים, בריכת כדורים, טרמפולינות ומגלשה. הפעילות מתבצעת ללא רתמה, מתאימה לכל הגילים ונמשכת שעה עד שעתיים."),
}

EXPLOR = {
    "fr": ("Qu'est-ce que les Explor Games à l'Écomusée Paysalp ?",
           "Les Explor Games sont une activité de découverte ludique par équipes, à 10 €/pers : énigmes et exploration des sites Paysalp. La réservation en ligne est obligatoire sur paysalp.fr."),
    "en": ("What are the Explor Games at the Écomusée Paysalp?",
           "The Explor Games are a team-based discovery activity costing €10 per person: riddles and exploration across the Paysalp sites. Online booking is compulsory at paysalp.fr."),
    "de": ("Was sind die Explor Games im Écomusée Paysalp?",
           "Die Explor Games sind eine spielerische Entdeckungsaktivität für Teams zu 10 € pro Person: Rätsel und Erkundung der Paysalp-Standorte. Eine Online-Reservierung auf paysalp.fr ist erforderlich."),
    "it": ("Che cosa sono gli Explor Games all'Écomusée Paysalp?",
           "Gli Explor Games sono un'attività di scoperta ludica a squadre, a 10 € a persona: enigmi ed esplorazione dei siti Paysalp. La prenotazione online su paysalp.fr è obbligatoria."),
    "es": ("¿Qué son los Explor Games en el Écomusée Paysalp?",
           "Los Explor Games son una actividad de descubrimiento lúdica por equipos, a 10 € por persona: enigmas y exploración de los sitios Paysalp. La reserva en línea en paysalp.fr es obligatoria."),
    "nl": ("Wat zijn de Explor Games in het Écomusée Paysalp?",
           "De Explor Games zijn een speelse ontdekkingsactiviteit in teams, voor 10 € per persoon: raadsels en verkenning van de Paysalp-locaties. Online reserveren via paysalp.fr is verplicht."),
    "pl": ("Czym są Explor Games w Écomusée Paysalp?",
           "Explor Games to zabawna aktywność odkrywcza dla zespołów, w cenie 10 € od osoby: zagadki i eksploracja obiektów Paysalp. Rezerwacja online na paysalp.fr jest obowiązkowa."),
    "pt": ("O que são os Explor Games no Écomusée Paysalp?",
           "Os Explor Games são uma atividade lúdica de descoberta em equipa, a 10 € por pessoa: enigmas e exploração dos sítios Paysalp. A reserva online em paysalp.fr é obrigatória."),
    "cs": ("Co jsou Explor Games v Écomusée Paysalp?",
           "Explor Games jsou zábavná objevitelská aktivita pro týmy za 10 € na osobu: hádanky a průzkum areálů Paysalp. Online rezervace na paysalp.fr je povinná."),
    "ja": ("Écomusée Paysalp の Explor Games とは何ですか？",
           "Explor Games は、チームで楽しむ探索型アクティビティです（1人10ユーロ）。謎解きをしながら Paysalp の各施設を巡ります。paysalp.fr でのオンライン予約が必要です。"),
    "ar": ("ما هي Explor Games في Écomusée Paysalp؟",
           "Explor Games نشاط استكشافي ترفيهي يُمارَس ضمن فرق، بسعر 10 يورو للشخص: ألغاز واستكشاف لمواقع Paysalp. الحجز الإلكتروني عبر paysalp.fr إلزامي."),
    "he": ("מהם ה-Explor Games ב-Écomusée Paysalp?",
           "ה-Explor Games הם פעילות גילוי משחקית בקבוצות, בעלות 10 יורו לאדם: חידות וסיור באתרי Paysalp. הזמנה מקוונת באתר paysalp.fr היא חובה."),
}

JOBS = [("acro-aventures-reignier", ACRO), ("ecomusee-paysalp-viuz-en-sallaz", EXPLOR)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    for slug, data in JOBS:
        fp = os.path.join(JSON_DIR, f"{slug}.json")
        d = json.load(open(fp, encoding="utf-8"))
        i18n = d.get("i18n") or {}
        appended, skipped, missing = [], [], []
        for lang, (q, a) in data.items():
            blk = i18n.get(lang)
            if not isinstance(blk, dict):
                missing.append(lang); continue
            faq = blk.get("faq")
            if faq is None:
                faq = blk["faq"] = []
            if any(isinstance(e, dict) and e.get("q") == q for e in faq):
                skipped.append(lang); continue
            if args.apply:
                faq.append({"q": q, "a": a})
            appended.append(f"{lang}({len(faq)})")
        print(f"{slug}: appended={len(appended)} [{','.join(appended)}]"
              + (f" already=[{','.join(skipped)}]" if skipped else "")
              + (f" no-locale-block=[{','.join(missing)}]" if missing else ""))
        if args.apply:
            json.dump(d, open(fp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            if not open(fp, encoding="utf-8").read().endswith("\n"):
                open(fp, "a", encoding="utf-8").write("\n")
    print("APPLIED" if args.apply else "(report only — nothing written)")


if __name__ == "__main__":
    main()
