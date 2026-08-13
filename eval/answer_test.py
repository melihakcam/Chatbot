"""M5 doğrulama: uçtan uca cevap kalitesi.

retrieval_test.py aramayı ölçer (model yok). Bu test modelin bulunan bağlamdan
DOĞRU cevap üretip üretmediğini ölçer.

Otomatik kontrol: cevapta beklenen ifade geçiyor mu + kapsam kuralları tuttu mu.
Cevap akıcılığı gözle değerlendirilir (çıktı yazdırılır).

ÇALIŞTIRMA:
    python -m eval.answer_test
    python -m eval.answer_test --model gemma2:2b
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
    ("Yazılım Mühendisliğinde hangi hocalar var", "BAŞ", "kisi"),
    ("Yazılım Mühendisliği bölümünün telefonu nedir", "205", "kisi"),
    ("Bilgisayar Mühendisliği e-posta adresi nedir", "ktun.edu.tr", "kisi"),
    ("Güz yarıyılı dersleri ne zaman başlıyor", "Eylül", "tarih"),
    ("Yazılım Mühendisliği birinci dönemde hangi dersler var", "Matematik", "ders"),
    ("YAZ102 dersinin adı nedir", "Algoritma", "ders"),
    ("Yatay geçiş başvuruları hakkında bilgi ver", "geçiş", "duyuru"),
    ("Yemek listesi duyurusu var mı", "Yemek", "duyuru"),
]

KAPSAM_DISI = ["makarna tarifi ver", "bitcoin fiyatı kaç"]

YONLENDIRME = [("notlarımı nereden görürüm", "obs.ktun.edu.tr")]

HAFIZA_TESTI = [
    ("Yazılım Mühendisliğinde hangi hocalar var", None),
    ("peki bölümün telefonu ne", "205"),
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

    print("=" * 74)
    print("1) CEVAP DOGRULUGU")
    print("=" * 74)
    for soru, beklenen, tip in SORULAR:
        bot.gecmisi_temizle()
        basla = time.time()
        cevap = bot.sor(soru)
        sure = time.time() - basla
        toplam_sure += sure

        ok = beklenen.casefold() in cevap.metin.casefold()
        isabet += ok
        print(f"\n{'OK  ' if ok else 'HATA'} [{tip:6}] {soru}   ({sure:.1f} sn)")
        print(f"  {cevap.metin[:260]}")
        if not ok:
            print(f"  !! beklenen ifade yok: {beklenen!r}")

    print("\n" + "=" * 74)
    print("2) KAPSAM KURALLARI")
    print("=" * 74)
    kapsam_ok = 0
    for soru in KAPSAM_DISI:
        bot.gecmisi_temizle()
        cevap = bot.sor(soru)
        ok = cevap.kapsam_disi
        kapsam_ok += ok
        print(f"  {'OK  ' if ok else 'SIZDI'} {soru:32} -> {cevap.metin[:52]}")

    yon_ok = 0
    for soru, beklenen in YONLENDIRME:
        bot.gecmisi_temizle()
        cevap = bot.sor(soru)
        ok = cevap.yonlendirme and beklenen in cevap.metin
        yon_ok += ok
        print(f"  {'OK  ' if ok else 'HATA'} {soru:32} -> {cevap.metin[:52]}")

    print("\n" + "=" * 74)
    print("3) SOHBET HAFIZASI  (takip sorusu)")
    print("=" * 74)
    bot.gecmisi_temizle()
    hafiza_ok = False
    for soru, beklenen in HAFIZA_TESTI:
        cevap = bot.sor(soru)
        print(f"\n  Sen > {soru}")
        if cevap.kullanilan_soru != soru:
            print(f"  (yeniden yazildi: {cevap.kullanilan_soru})")
        print(f"  Bot > {cevap.metin[:200]}")
        if beklenen:
            hafiza_ok = beklenen.casefold() in cevap.metin.casefold()

    print("\n" + "=" * 74)
    print(f"Cevap dogrulugu : {isabet}/{len(SORULAR)} = %{100 * isabet / len(SORULAR):.0f}")
    print(f"Kapsam disi ret : {kapsam_ok}/{len(KAPSAM_DISI)}")
    print(f"Yonlendirme     : {yon_ok}/{len(YONLENDIRME)}")
    print(f"Hafiza          : {'OK' if hafiza_ok else 'TUTMADI'}")
    print(f"Ortalama sure   : {toplam_sure / len(SORULAR):.1f} sn/soru")

    basarili = isabet >= len(SORULAR) * 0.75 and kapsam_ok == len(KAPSAM_DISI)
    print("\n" + ("SONUC: GECTI" if basarili else "SONUC: HEDEF TUTMADI"))
    return 0 if basarili else 1


if __name__ == "__main__":
    raise SystemExit(main())
