"""Alt alan yönlendirmeleri — login arkasındaki şeyler için doğru adres.

NEDEN VAR:
    "Notlarımı nereden görürüm" sorusunun cevabı sitede bir sayfada yazmıyor;
    OBS'ye giriş yapmak gerekiyor. Bot bunu bilmezse ya alakasız bir sayfa
    gösterir ya da uydurur. Bu tablo, cevabın indekste OLMADIĞI ama doğru
    adresin bilindiği durumları kapsar.

    Bu yollar crawl edilmiyor (login arkasında), sadece yönlendiriliyor.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.normalize import normalize_tr

# (anahtar kelimeler, cevap) — kelimelerden HERHANGİ biri geçerse eşleşir.
YONLENDIRMELER: list[tuple[tuple[str, ...], str]] = [
    (
        ("not", "notlar", "notum", "transkript", "ders kaydi", "ders secme",
         "kayit yenileme ekrani", "obs", "ogrenci bilgi sistemi", "vize notu", "harf notu"),
        "Not görüntüleme, ders kaydı ve transkript işlemleri Öğrenci Bilgi Sistemi "
        "üzerinden yapılıyor: https://obs.ktun.edu.tr\n"
        "Buraya öğrenci numaran ve şifrenle giriş yapman gerekiyor.",
    ),
    (
        ("uzaktan egitim", "lms", "canli ders", "ders videosu", "online ders"),
        "Uzaktan eğitim ve ders materyalleri için: https://lms.ktun.edu.tr",
    ),
    (
        ("kutuphane", "kitap", "odunc", "veritabani"),
        "Kütüphane hizmetleri, çalışma saatleri ve katalog için: "
        "https://kutuphane.ktun.edu.tr",
    ),
    (
        ("taban puan", "kontenjan", "aday ogrenci", "tercih", "siralama", "yks"),
        "Taban puanlar, kontenjanlar ve aday öğrenci bilgileri için: "
        "https://aday.ktun.edu.tr",
    ),
    (
        ("mezun", "diploma"),
        "Mezun işlemleri için: https://mezun.ktun.edu.tr",
    ),
    (
        ("sertifika programi", "kurs", "ktunsem"),
        "Sertifika programları ve kurslar için: https://ktunsem.ktun.edu.tr",
    ),
]


def yonlendirme_bul(soru: str) -> str | None:
    """Soru bir yönlendirme konusuysa hazır cevabı döndürür, değilse None.

    KELİME SINIRI ŞART: eşleşme alt dize üzerinden yapılınca özel adlar
    yönlendirmeye takılıyordu. Ölçülen vaka: "Kürşad Buğrahan Yapar kimdir"
    -> normalize edilmiş hali "kursad ..." ve içinde "kurs" geçtiği için
    soru KTÜNSEM'e yönlendiriliyordu. Yönlendirme aramadan ÖNCE çalıştığı
    için de kişi hiç aranmıyordu.
    """
    soru_norm = normalize_tr(soru)
    for anahtarlar, cevap in YONLENDIRMELER:
        for anahtar in anahtarlar:
            # Kelime BAŞI şart, sonu değil: Türkçe sondan eklemeli, "kurslar"
            # ve "notlarımı" da eşleşmeli. Sona da \b konunca bunlar kırılıyor.
            # Özel ad çakışması ("Kürşad" içinde "kurs") burada değil,
            # çağıran tarafta çözülüyor — bkz. bot/answer.py, kimlik sorusu
            # yönlendirmeye hiç sokulmuyor.
            kalip = r"\b" + r"\s+".join(re.escape(k)
                                        for k in normalize_tr(anahtar).split())
            if re.search(kalip, soru_norm):
                return cevap
    return None


if __name__ == "__main__":
    from common.console import setup_stdout_utf8

    setup_stdout_utf8()
    for soru in ["notlarımı nereden görebilirim", "kütüphane kaça kadar açık",
                 "taban puanı kaç", "yazılım mühendisliği hocaları kimler"]:
        cevap = yonlendirme_bul(soru)
        print(f"{soru[:40]:42} -> {(cevap or '(yonlendirme yok)')[:60]}")
