"""M5 doğrulama: uçtan uca cevap kalitesi.

retrieval_test.py aramayı ölçer (model yok). Bu test modelin bulunan bağlamdan
DOĞRU cevap üretip üretmediğini ölçer.

KAPSAM: Yapay Zeka ve Makine Öğrenmesi Mühendisliği bölümü.

ÇALIŞTIRMA:
    python -m eval.answer_test
    python -m eval.answer_test --model qwen2.5:1.5b-instruct
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.console import setup_stdout_utf8
from bot.answer import Chatbot

# (soru, cevapta gecmesi beklenen ifade, tip)
SORULAR = [
    ("Bölümde hangi hocalar var", "YILMAZ", "kisi"),
    ("Bölüm başkanı kim", "Hakan", "kisi"),
    ("Araştırma görevlileri kimler", "Arş", "kisi"),
    ("Bölümün amacı nedir", "yapay zeka", "genel"),
    ("Staj yapmak için ne gerekiyor", "staj", "duyuru"),
    ("DC şartlı geçer ne demek", "DC", "duyuru"),
    ("Birinci dönemde hangi dersler var", "Matematik", "ders"),
    ("Bölümde kaç dönem ders var", "dönem", "ders"),
]

KAPSAM_DISI = ["makarna tarifi ver", "bitcoin fiyatı kaç"]

YONLENDIRME = [("notlarımı nereden görürüm", "obs.ktun.edu.tr")]

# Takip sorusu: ikinci soruda bölüm adı GEÇMİYOR, geçmişten taşınmalı.
HAFIZA_TESTI = [
    ("Bölümde hangi hocalar var", None),
    ("peki bölüm başkanı kim", "Hakan"),
]


def main() -> int:
    setup_stdout_utf8()
    ayr = argparse.ArgumentParser()
    ayr.add_argument("--backend", default="ollama")
    ayr.add_argument("--model", default=None)
    args = ayr.parse_args()

    bot = Chatbot(args.backend, args.model)
    print(f"Model: {bot.backend.model} | Indeks: {bot.retriever.meta['parca_sayisi']} parca\n")

    isabet = 0
    toplam_sure = 0.0
    dogrudan_sayisi = 0

    print("=" * 74)
    print("1) CEVAP DOGRULUGU")
    print("=" * 74)
    for soru, beklenen, tip in SORULAR:
        bot.gecmisi_temizle()
        basla = time.time()
        cevap = bot.sor(soru)
        sure = time.time() - basla
        toplam_sure += sure
        dogrudan_sayisi += cevap.dogrudan

        ok = beklenen.casefold() in cevap.metin.casefold()
        isabet += ok
        etiket = "dogrudan" if cevap.dogrudan else "model"
        print(f"\n{'OK  ' if ok else 'HATA'} [{tip:6}] {soru}   ({sure:.1f} sn, {etiket})")
        print(f"  {cevap.metin[:240]}")
        if not ok:
            print(f"  !! beklenen ifade yok: {beklenen!r}")

    print("\n" + "=" * 74)
    print("2) KAPSAM KURALLARI")
    print("=" * 74)
    kapsam_ok = 0
    for soru in KAPSAM_DISI:
        bot.gecmisi_temizle()
        cevap = bot.sor(soru)
        kapsam_ok += cevap.kapsam_disi
        print(f"  {'OK  ' if cevap.kapsam_disi else 'SIZDI'} {soru:32} -> {cevap.metin[:48]}")

    yon_ok = 0
    for soru, beklenen in YONLENDIRME:
        bot.gecmisi_temizle()
        cevap = bot.sor(soru)
        ok = cevap.yonlendirme and beklenen in cevap.metin
        yon_ok += ok
        print(f"  {'OK  ' if ok else 'HATA'} {soru:32} -> {cevap.metin[:48]}")

    print("\n" + "=" * 74)
    print("3) SOHBET HAFIZASI  (takip sorusu)")
    print("=" * 74)
    bot.gecmisi_temizle()
    hafiza_ok = False
    for soru, beklenen in HAFIZA_TESTI:
        cevap = bot.sor(soru)
        print(f"\n  Sen > {soru}")
        if cevap.kullanilan_soru != soru:
            print(f"  (arama sorusu: {cevap.kullanilan_soru})")
        print(f"  Bot > {cevap.metin[:180]}")
        if beklenen:
            hafiza_ok = beklenen.casefold() in cevap.metin.casefold()

    print("\n" + "=" * 74)
    print(f"Cevap dogrulugu : {isabet}/{len(SORULAR)} = %{100 * isabet / len(SORULAR):.0f}")
    print(f"Kapsam disi ret : {kapsam_ok}/{len(KAPSAM_DISI)}")
    print(f"Yonlendirme     : {yon_ok}/{len(YONLENDIRME)}")
    print(f"Hafiza          : {'OK' if hafiza_ok else 'TUTMADI'}")
    print(f"Modelsiz cevap  : {dogrudan_sayisi}/{len(SORULAR)} (yapisal cikarim)")
    print(f"Ortalama sure   : {toplam_sure / len(SORULAR):.1f} sn/soru")

    basarili = isabet >= len(SORULAR) * 0.75 and kapsam_ok == len(KAPSAM_DISI)
    print("\n" + ("SONUC: GECTI" if basarili else "SONUC: HEDEF TUTMADI"))
    return 0 if basarili else 1


if __name__ == "__main__":
    raise SystemExit(main())
