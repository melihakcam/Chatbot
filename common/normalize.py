"""Türkçe metin normalizasyonu — projenin en kritik ortak parçası.

NEDEN VAR:
    Python'un standart .lower() metodu Türkçe'yi bozar:

        "İ".lower()  ->  'i' + U+0307   (i ve AYRI bir birleşen nokta! tek karakter değil)
        "I".lower()  ->  'i'            (Türkçe'de 'ı' olmalıydı)

    Sonuç: kullanıcı "bilgisayar" yazdığında, indekste "BİLGİSAYAR" olarak geçen
    kayıt BULUNAMAZ. Hata mesajı vermez, sistem çalışıyor görünür, sadece yanlış
    cevap verir. BM25 aramasını sessizce çökerten hata budur.

KULLANIM KURALI:
    Indeksleme (index/build_index.py) ve sorgu (bot/retriever.py) **aynı**
    fonksiyonu kullanmak zorunda. Biri normalize edip diğeri etmezse arama tutmaz.

    Ham metin (pages.jsonl'deki "text") ASLA normalize edilmiş halde saklanmaz —
    kullanıcıya orijinal haliyle gösterilir. Normalizasyon sadece arama anında.
"""

import re
import unicodedata

# Büyük harfler küçültülmeden ÖNCE elle eşlenir; .lower()'a bırakılmaz.
# İ ve I burada çözülür, gerisi tutarlılık için.
_UPPER_MAP = str.maketrans({
    "İ": "i", "I": "ı",
    "Ş": "ş", "Ğ": "ğ", "Ü": "ü", "Ö": "ö", "Ç": "ç",
})

# Şapkasız/klavyesiz yazım toleransı: "muhendisligi" -> "mühendisliği" ile eşleşsin.
_FOLD_MAP = str.maketrans({
    "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c", "ı": "i",
    "â": "a", "î": "i", "û": "u",
})

_WS_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def lower_tr(text: str) -> str:
    """Türkçe'ye doğru küçük harfe çevirir. İ->i, I->ı."""
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_UPPER_MAP)
    text = text.lower()
    # Savunma: metinde zaten "i + birleşen nokta" varsa (kopyala-yapıştır içerikte olur)
    text = text.replace("̇", "")
    return text


def fold_tr(text: str) -> str:
    """Türkçe'ye özel harfleri ASCII karşılığına indirger. Sadece arama için."""
    return text.translate(_FOLD_MAP)


def normalize_tr(text: str) -> str:
    """Arama için tam normalizasyon: küçük harf + ASCII katlama + boşluk sadeleştirme."""
    return _WS_RE.sub(" ", fold_tr(lower_tr(text))).strip()


def tokenize_tr(text: str) -> list[str]:
    """BM25 için kelime listesi üretir."""
    return _TOKEN_RE.findall(normalize_tr(text))


if __name__ == "__main__":
    from console import setup_stdout_utf8

    setup_stdout_utf8()

    # Bu testler tuzağın gerçekten kapandığını gösterir.
    cases = [
        ("BİLGİSAYAR MÜHENDİSLİĞİ", "bilgisayar muhendisligi"),
        ("bilgisayar muhendisligi", "bilgisayar muhendisligi"),  # şapkasız yazım da aynı yere düşer
        ("Yazılım Mühendisliği", "yazilim muhendisligi"),
        ("IŞIK ÇAĞLAR", "isik caglar"),
        ("Doç. Dr.   Emine   BAŞ", "doc. dr. emine bas"),
    ]
    hata = 0
    for girdi, beklenen in cases:
        cikti = normalize_tr(girdi)
        ok = cikti == beklenen
        hata += not ok
        print(f"{'OK ' if ok else 'HATA'} {girdi!r:32} -> {cikti!r}")

    # Asıl kanıt: farklı yazımlar aynı normal forma düşüyor mu?
    grup = ["BİLGİSAYAR MÜHENDİSLİĞİ", "Bilgisayar Mühendisliği", "bilgisayar muhendisligi"]
    formlar = {normalize_tr(x) for x in grup}
    print(f"\n3 farklı yazım -> {len(formlar)} normal form: {formlar}")
    assert len(formlar) == 1, "Normalizasyon tutmuyor!"

    # Standart .lower() ile karşılaştırma (tuzağın kendisi).
    # Karakterleri kod noktası olarak yazdırıyoruz, çünkü gizli nokta gözle görünmüyor.
    bozuk = "Bİ".lower()
    duzgun = lower_tr("Bİ")
    kod = lambda s: " ".join(f"U+{ord(c):04X}" for c in s)
    print(f"\nStandart .lower('Bİ') -> {len(bozuk)} karakter: {kod(bozuk)}   <- fazladan U+0307!")
    print(f"lower_tr('Bİ')        -> {len(duzgun)} karakter: {kod(duzgun)}")

    print("\nTUM TESTLER GECTI" if hata == 0 else f"\n{hata} TEST BASARISIZ")
