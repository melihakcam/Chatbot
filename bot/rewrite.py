"""Takip sorularını tam soruya çevirir (sohbet hafızası).

SORUN:
    Kullanıcı: "Yazılım Mühendisliğinde hangi hocalar var?"
    Bot:       (liste)
    Kullanıcı: "peki bölümün telefonu ne?"

    İkinci soru tek başına aramaya gitmez — "bölümün" hangi bölüm belli değil.

NEDEN LLM İLE YAZDIRMIYORUZ:
    İlk sürüm soruyu modele yeniden yazdırıyordu. 1.5B model soruyu CÜMLEYE
    çeviriyordu: "peki bölümün telefonu ne" -> "Bölümün telefonu yok."
    Yani hem soru olmaktan çıkıyor hem de uydurma bilgi ekliyordu. Arama bu
    cümleyle yapılınca sonuç tamamen kayıyordu.

ÇÖZÜM:
    Deterministik konu taşıma. Önceki sorulardan KONU kelimelerini (bölüm/birim
    adları, özel isimler) çıkarıp yeni sorunun başına ekliyoruz. Model
    çağrılmıyor: hızlı, öngörülebilir, uydurma riski sıfır.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.normalize import normalize_tr

TAKIP_BASLANGICLARI = (
    "peki", "ya ", "o zaman", "ayrica", "bir de", "aynisi", "ya da", "peki ya",
)
TAKIP_ZAMIRLERI = {
    "onun", "onlarin", "bunun", "sunun", "orada", "orasi", "bunlar", "onlar",
    "bolumun", "bolumde", "orasinin", "oranin",
}
KISA_SORU_KELIME = 5

# Birim adları REGEX ile çıkarılmıyor. Sebep: Türkçe ekler.
# "Yazılım Mühendisliğinde" -> regex "Mühendisliği" arayınca tutmuyor,
# "Mühendisliğinde/Mühendisliğinin/Mühendisliğe" gibi onlarca hal var.
# Bunun yerine indeksteki GERÇEK birim adları kullanılıyor (Retriever'dan gelir)
# ve normalize edilmiş hallerinde ÖNEK araması yapılıyor:
#   "yazilim muhendisliginde".startswith("yazilim muhendisligi") -> True
# Böylece bütün ekler tek kuralla çözülüyor.


def takip_sorusu_mu(soru: str) -> bool:
    norm = normalize_tr(soru)
    kelimeler = norm.split()

    if any(norm.startswith(b.strip()) for b in TAKIP_BASLANGICLARI):
        return True
    if TAKIP_ZAMIRLERI & set(kelimeler):
        return True
    return len(kelimeler) <= KISA_SORU_KELIME


def konu_cikar(metin: str, bilinen_birimler: list[str]) -> str | None:
    """Metinde geçen birim adını bulur. Türkçe ekleri önek eşlemesiyle çözer."""
    metin_norm = normalize_tr(metin)
    # Uzun adlar önce denensin: "Yapay Zeka ve Makine Öğrenmesi" kısa bir adın
    # içinde geçiyorsa yanlış eşleşme olmasın.
    for birim in sorted(bilinen_birimler, key=len, reverse=True):
        if normalize_tr(birim) in metin_norm:
            return birim
    return None


# Sorgudan atılan takip kelimeleri.
#
# NEDEN: "peki" arama sorgusunda kalınca BM25'i sulandırıyor — indekste hiç
# geçmeyen bir kelime, eşleşen kelimelerin ağırlığını düşürüyor. Ölçülen vaka:
# "bölüm başkanı kim" kapsam içi geçerken "peki bölüm başkanı kim" kapsam dışı
# sayılıp reddediliyordu. Kelime soruya anlam katmıyor, sadece bağlaç.
_ATILAN_ONEKLER = re.compile(
    r"^(peki\s+ya|peki|ya|bir\s+de|ayrıca|o\s+zaman|e\s+)\s+", re.IGNORECASE
)


def onekleri_at(soru: str) -> str:
    """Baştaki takip bağlaçlarını siler: 'peki bölüm başkanı kim' -> 'bölüm başkanı kim'."""
    onceki = None
    while onceki != soru:
        onceki = soru
        soru = _ATILAN_ONEKLER.sub("", soru).strip()
    return soru or onceki


def yeniden_yaz(soru: str, gecmis: list[tuple[str, str]],
                bilinen_birimler: list[str] | None = None) -> str:
    """Takip sorusuna önceki konuyu ekler. Gerekmiyorsa soruyu aynen döndürür.

    gecmis: [(kullanici_sorusu, bot_cevabi), ...] — en yeniler sonda.
    bilinen_birimler: indekste geçen birim adları (Chatbot dolduruyor).
    """
    if not takip_sorusu_mu(soru):
        return soru

    # Takip bağlaçları her durumda atılır — geçmiş olmasa bile aramaya zarar veriyor.
    sade = onekleri_at(soru)

    birimler = bilinen_birimler or []
    if not gecmis or not birimler:
        return sade

    # Soru zaten bir birim adı içeriyorsa dokunma.
    if konu_cikar(sade, birimler):
        return sade

    # En yeniden geriye doğru ilk konuyu bul (soruda, yoksa cevapta).
    for onceki_soru, onceki_cevap in reversed(gecmis[-3:]):
        konu = konu_cikar(onceki_soru, birimler) or konu_cikar(onceki_cevap, birimler)
        if konu:
            return f"{konu} {sade}"

    return sade


if __name__ == "__main__":
    from common.console import setup_stdout_utf8

    setup_stdout_utf8()
    birimler = ["Yazılım Mühendisliği", "Bilgisayar Mühendisliği",
                "Yapay Zeka ve Makine Öğrenmesi"]
    gecmis = [("Yazılım Mühendisliğinde hangi hocalar var", "Doç. Dr. Emine BAŞ, ...")]
    testler = [
        "peki bölümün telefonu ne",
        "e-posta adresi nedir",
        "Bilgisayar Mühendisliği dersleri neler",   # kendi konusu var, dokunma
        "Yapay Zeka ve Makine Öğrenmesi bölümünde kimler var",
    ]
    for soru in testler:
        yeni = yeniden_yaz(soru, gecmis, birimler)
        isaret = "->" if yeni != soru else " ="
        print(f"  {soru[:46]:48} {isaret} {yeni}")
