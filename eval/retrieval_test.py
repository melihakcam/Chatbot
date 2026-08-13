"""M4 doğrulama: arama isabeti + kapsam kapısı ölçümü (LLM olmadan).

Bu test modelsiz çalışır — "soruya doğru sayfa geliyor mu" sorusunu cevaplar.
Cevap kalitesi değil, ARAMA kalitesi ölçülür. Model takılmadan önce burası
yeşile dönmeli, yoksa modele yanlış bağlam gider ve hata modelde sanılır.

KAPSAM: Yapay Zeka ve Makine Öğrenmesi Mühendisliği bölümü (tek bölüm).
Sorular bilerek bölüm adı GEÇMEDEN yazıldı — gerçek kullanıcı "bölümde hangi
hocalar var" der, her seferinde bölüm adını tekrarlamaz.

ÇALIŞTIRMA:
    python -m eval.retrieval_test
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.console import setup_stdout_utf8
from bot.retriever import Retriever

# (soru, beklenen kaynakta geçmesi gereken ifade, soru tipi)
KAPSAM_ICI = [
    # --- kişi / iletişim ---
    # Birim adı taşıyan sorular: kapsam üç bölüme çıkınca "bölüm başkanı kim"in
    # üç geçerli cevabı oldu ve ölçüm sistem doğru çalışırken HATA saymaya
    # başladı. Soru birimi söylemezse ölçtüğü şey doğruluk değil şans olur.
    ("bölümde hangi hocalar var", "Doç. Dr.", "kisi"),
    ("Yapay Zeka ve Makine Öğrenmesi Mühendisliği bölüm başkanı kim",
     "Hakan YILMAZ", "kisi"),
    ("Ayşe Beşkirli hangi dersleri veriyor", "BEŞKİRLİ", "kisi"),
    ("araştırma görevlileri kimler", "Arş. Gör.", "kisi"),
    ("bölümün iletişim bilgileri", "İletişim", "kisi"),

    # --- tarih / takvim ---
    ("akademik takvim", "Akademik Takvim", "tarih"),
    ("sınav programı nerede", "Sınav Program", "tarih"),
    ("ders programı ne zaman açıklanır", "Ders Program", "tarih"),

    # --- ders / program ---
    ("bölümde hangi dersler var", "Ders", "ders"),
    ("birinci dönem dersleri neler", "DÖNEM 1", "ders"),
    ("kaç AKTS kredisi var", "AKTS", "ders"),
    ("öğretim planı", "Öğretim Planı", "ders"),
    ("program çıktıları neler", "Program Çıktı", "ders"),
    ("ders içerikleri", "Ders İçerik", "ders"),

    # --- staj / duyuru ---
    ("staj nasıl yapılır", "Staj", "duyuru"),
    ("staj yönergesi", "Staj Yönergesi", "duyuru"),
    ("DC şartlı geçer nedir", "DC", "duyuru"),
    ("bölümün amacı nedir", "Amaç", "duyuru"),
]

KAPSAM_DISI = [
    "hava durumu nasıl",
    "makarna tarifi ver",
    "bitcoin fiyatı kaç",
    "futbol maçı ne zaman",
    "aşk şiiri yaz",
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
        print(f"  {isaret} [{tip:6}] {soru[:38]:40} -> {sonuclar[0].title[:34]}")

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
        print(f"  {'OK  ' if reddedildi else 'SIZDI'} {soru[:40]:42} "
              f"bm25={retriever._son_bm25_max:6.2f} kos={retriever._son_kosinus_max:.3f}")

    yanlis_ret = 0
    print("\n  Kapsam ici sorular yanlislikla reddedildi mi?")
    for soru, _, _ in KAPSAM_ICI:
        sonuclar = retriever.search(soru, k=4)
        if retriever.kapsam_disi_mi(sonuclar):
            yanlis_ret += 1
            print(f"    YANLIS RET: {soru[:38]:40} "
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
