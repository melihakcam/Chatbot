"""M4 doğrulama: arama isabeti + kapsam kapısı ölçümü (LLM olmadan).

Bu test modelsiz çalışır — "soruya doğru sayfa geliyor mu" sorusunu cevaplar.
Cevap kalitesi değil, ARAMA kalitesi ölçülür. Model takılmadan önce burası
yeşile dönmeli, yoksa modele yanlış bağlam gider ve hata modelde sanılır.

ÇALIŞTIRMA:
    python -m eval.retrieval_test
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.console import setup_stdout_utf8
from bot.retriever import Retriever

# (soru, beklenen kaynakta geçmesi gereken ifade, soru tipi)
# Beklenti "title veya text içinde geçmeli" olarak kontrol edilir.
KAPSAM_ICI = [
    # --- kişi / iletişim ---
    ("Yazılım Mühendisliğinde hangi hocalar var", "Yazılım Mühendisliği", "kisi"),
    ("Emine Baş hangi bölümde", "Emine BAŞ", "kisi"),
    ("Bilgisayar Mühendisliği bölüm başkanı kim", "Bilgisayar Mühendisliği", "kisi"),
    ("Yapay Zeka ve Makine Öğrenmesi bölümünde kimler var", "Yapay Zeka", "kisi"),
    ("yazılım mühendisliği bölüm telefonu", "Telefon", "kisi"),
    ("bilgisayar mühendisliği e-posta adresi", "@ktun.edu.tr", "kisi"),

    # --- tarih / takvim ---
    ("güz yarıyılı final sınavları ne zaman", "GÜZ YARIYILI", "tarih"),
    ("bahar dönemi ne zaman başlıyor", "BAHAR", "tarih"),
    ("kayıt yenileme tarihleri", "Kayıt", "tarih"),
    ("lisansüstü akademik takvim", "LİSANSÜSTÜ", "tarih"),

    # --- ders / program ---
    ("YAZ102 dersi kaç kredi", "YAZ102", "ders"),
    ("Bilgisayar Mühendisliği ders listesi", "Ders Kodu", "ders"),
    ("yazılım mühendisliği birinci dönem dersleri", "DÖNEM 1", "ders"),
    ("yapay zeka bölümü ders programı", "Yapay Zeka", "ders"),
    ("öğretim planı nerede", "Öğretim Planı", "ders"),

    # --- duyuru / haber ---
    ("yatay geçiş başvuru tarihleri", "Yatay Geçiş", "duyuru"),
    ("öğretim görevlisi ilanı sonuçları", "Öğretim Görevlisi", "duyuru"),
    ("yemek listesi", "Yemek", "duyuru"),
    ("iki aşamalı doğrulama", "Doğrulama", "duyuru"),
    ("DC şartlı geçer nedir", "DC", "duyuru"),
]

KAPSAM_DISI = [
    "hava durumu nasıl",
    "makarna tarifi ver",
    "python'da liste nasıl sıralanır",
    "bitcoin fiyatı kaç",
    "futbol maçı ne zaman",
    "aşk şiiri yaz",
    "İstanbul Teknik Üniversitesi taban puanı",
    "bugün günlerden ne",
]


def main() -> int:
    setup_stdout_utf8()
    retriever = Retriever()
    print(f"Indeks: {retriever.meta['parca_sayisi']} parca\n")

    # --- 1. Arama isabeti ---
    print("=" * 74)
    print("1) ARAMA ISABETI  (beklenen kaynak ilk 4 sonucta mi?)")
    print("=" * 74)

    tip_toplam: dict[str, int] = {}
    tip_isabet: dict[str, int] = {}

    for soru, beklenen, tip in KAPSAM_ICI:
        sonuclar = retriever.search(soru, k=4)
        havuz = " ".join(f"{s.title} {s.text}" for s in sonuclar).casefold()
        isabet = beklenen.casefold() in havuz

        tip_toplam[tip] = tip_toplam.get(tip, 0) + 1
        tip_isabet[tip] = tip_isabet.get(tip, 0) + isabet

        isaret = "OK  " if isabet else "KACIRDI"
        print(f"  {isaret} [{tip:6}] {soru[:44]:46} -> {sonuclar[0].title[:30]}")

    toplam = sum(tip_toplam.values())
    isabet_sayisi = sum(tip_isabet.values())
    print(f"\n  GENEL: {isabet_sayisi}/{toplam} = %{100 * isabet_sayisi / toplam:.0f}  (hedef: %80)")
    for tip in tip_toplam:
        oran = 100 * tip_isabet[tip] / tip_toplam[tip]
        print(f"    {tip:8} {tip_isabet[tip]}/{tip_toplam[tip]} = %{oran:.0f}  (hedef: %70)")

    # --- 2. Kapsam kapısı ---
    print("\n" + "=" * 74)
    print("2) KAPSAM KAPISI  (alakasiz soru reddediliyor mu?)")
    print("=" * 74)

    yanlis_kabul = 0
    for soru in KAPSAM_DISI:
        sonuclar = retriever.search(soru, k=4)
        reddedildi = retriever.kapsam_disi_mi(sonuclar)
        yanlis_kabul += not reddedildi
        print(f"  {'OK  ' if reddedildi else 'SIZDI'} {soru[:44]:46} "
              f"bm25={retriever._son_bm25_max:6.2f} kos={retriever._son_kosinus_max:.3f}")

    yanlis_ret = 0
    print("\n  Kapsam ici sorular yanlislikla reddedildi mi?")
    for soru, _, _ in KAPSAM_ICI:
        sonuclar = retriever.search(soru, k=4)
        if retriever.kapsam_disi_mi(sonuclar):
            yanlis_ret += 1
            print(f"    YANLIS RET: {soru[:42]:44} "
                  f"bm25={retriever._son_bm25_max:6.2f} kos={retriever._son_kosinus_max:.3f}")
    if yanlis_ret == 0:
        print("    (yok — hepsi kabul edildi)")

    print(f"\n  Kapsam disi sizinti : {yanlis_kabul}/{len(KAPSAM_DISI)}")
    print(f"  Kapsam ici yanlis ret: {yanlis_ret}/{len(KAPSAM_ICI)}")

    basarili = (isabet_sayisi / toplam >= 0.80) and yanlis_kabul == 0 and yanlis_ret == 0
    print("\n" + ("SONUC: GECTI" if basarili else "SONUC: HEDEFLER TUTMADI"))
    return 0 if basarili else 1


if __name__ == "__main__":
    raise SystemExit(main())
