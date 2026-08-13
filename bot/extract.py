"""Yapısal alan çıkarımı — modele hiç sormadan cevaplanabilen sorular.

NEDEN VAR:
    Ölçüm şunu gösterdi: arama %100 isabetli, bütün hatalar modelin doğru
    bağlamı KULLANAMAMASINDAN geliyor. Telefon numarası bağlamın 1. parçasında
    apaçık dururken model "bilgi yok" diyebiliyordu.

    "Telefon numarası nedir" gibi sorularda modele yaratıcılık payı bırakmanın
    hiçbir faydası yok — cevap metinde bir alan olarak duruyor. Bu katman onu
    doğrudan çekip şablona koyar. Model devreye girmez.

SONUÇ:
    - Bu tip sorular model kalitesinden BAĞIMSIZ hale gelir (kötü model bozamaz)
    - Cevap ~20 saniye yerine anında gelir
    - Uydurma ihtimali sıfır

    Cevap bulunamazsa None döner ve normal LLM akışı devreye girer.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.normalize import normalize_tr

# --- Soru niyeti tespiti (normalize edilmiş halleriyle) ---
NIYET_ANAHTARLARI = {
    "telefon": ("telefon", "numara", "tel ", "iletisim numarasi", "santral", "dahili"),
    "eposta": ("e-posta", "eposta", "mail", "email", "elektronik posta"),
    "adres": ("adres", "nerede", "konum", "hangi binada"),
}

# Telefon: "0332 205 1425" ve "0 (332) 205 14 29" biçimlerinin ikisi de.
_TELEFON = re.compile(r"0\s*\(?\s*\d{3}\s*\)?[\s\d]{7,14}\d")
_EPOSTA = re.compile(r"[\w.\-]+@[\w.\-]+\.(?:edu\.tr|com|org|gov\.tr)")
# Ders kodu: YAZ102, BBF101, EEM3021 gibi.
_DERS_KODU = re.compile(r"\b([A-ZÇĞİÖŞÜ]{2,4}\s?\d{3,4})\b")


def _niyet_bul(soru: str) -> str | None:
    soru_norm = normalize_tr(soru)
    for niyet, anahtarlar in NIYET_ANAHTARLARI.items():
        if any(normalize_tr(a).strip() in soru_norm for a in anahtarlar):
            return niyet
    return None


def _etiketli_satir(metin: str, etiket: str) -> str | None:
    """Etiketli alanı bulur. İki biçimi de destekler:

        "Telefon (Bölüm Sekreteri) 0332 205 1425"   -> deger ayni satirda
        "Telefon:\\n0 (332) 205 14 29"               -> deger sonraki satirda
    """
    satirlar = [s.strip() for s in metin.split("\n")]
    etiket_norm = normalize_tr(etiket)

    for i, satir in enumerate(satirlar):
        if not normalize_tr(satir).startswith(etiket_norm):
            continue
        # Etiketten sonraki kısım aynı satırda mı?
        kalan = re.sub(rf"(?i)^{re.escape(etiket)}\s*(\([^)]*\))?\s*:?\s*", "", satir).strip()
        if kalan:
            return kalan
        # Değilse sonraki dolu satır.
        for sonraki in satirlar[i + 1:]:
            if sonraki:
                return sonraki
    return None


def telefon_cikar(metin: str) -> str | None:
    satir = _etiketli_satir(metin, "Telefon")
    if satir:
        eslesme = _TELEFON.search(satir)
        if eslesme:
            return " ".join(eslesme.group(0).split())
    eslesme = _TELEFON.search(metin)
    return " ".join(eslesme.group(0).split()) if eslesme else None


def eposta_cikar(metin: str) -> str | None:
    eslesme = _EPOSTA.search(metin)
    return eslesme.group(0) if eslesme else None


def adres_cikar(metin: str) -> str | None:
    satir = _etiketli_satir(metin, "Adres")
    return satir if satir and len(satir) > 15 else None


def ders_satiri_cikar(metin: str, ders_kodu: str) -> tuple[str, str, str] | None:
    """Ders kodundan (ad, AKTS, koordinatör) döndürür.

    Tablo satırı biçimi: "YAZ102 | Algoritma ve Programlama | 6 | Doç. Dr. İsmail Koç"
    """
    kod_norm = normalize_tr(ders_kodu).replace(" ", "")
    for satir in metin.split("\n"):
        if "|" not in satir:
            continue
        hucreler = [h.strip() for h in satir.split("|")]
        if normalize_tr(hucreler[0]).replace(" ", "") != kod_norm:
            continue
        ad = hucreler[1] if len(hucreler) > 1 else ""
        akts = hucreler[2] if len(hucreler) > 2 else ""
        koordinator = hucreler[3] if len(hucreler) > 3 else ""
        return ad, akts, koordinator
    return None


# Kadro listelerindeki unvanlar. Sıra ÖNEMLİ: "Dr. Öğr. Üyesi" önce denenmeli,
# yoksa "Dr." ile eşleşip yanlış unvan döner.
UNVANLAR = ("Prof. Dr.", "Doç. Dr.", "Dr. Öğr. Üyesi", "Öğr. Gör. Dr.",
            "Öğr. Gör.", "Arş. Gör. Dr.", "Arş. Gör.", "Uzm.", "Okutman")


def kisi_satiri_cikar(metin: str, ad_parcalari: list[str]) -> str | None:
    """Kadro listesinden bir kişinin TAM satırını (unvan + ad) döndürür.

    NEDEN VAR: 2B model unvanı uyduruyordu. "beyza kızıldağ kimdir" sorusunda
    kaynak sayfada "Arş. Gör. Beyza KIZILDAĞ" yazarken model "öğretim üyesi
    olarak çalışmaktadır" dedi — akademik unvanlar birbirinin yerine geçmez,
    bu düpedüz yanlış bilgi. Unvan metinde bir ALAN gibi duruyor; telefon ve
    ders kodunda olduğu gibi doğrudan okunuyor, modele yazdırılmıyor.
    """
    for satir in re.split(r"[|\n]", metin):
        satir = satir.strip()
        if not satir or len(satir) > 80:
            continue
        satir_norm = normalize_tr(satir)
        if not all(normalize_tr(p) in satir_norm for p in ad_parcalari):
            continue
        for unvan in UNVANLAR:
            if satir.startswith(unvan):
                return satir
    return None


def _ad_parcalari(soru: str) -> list[str]:
    """Sorudan ad adayı kelimeleri ayıklar (soru kelimeleri atılır)."""
    atilacak = {"kim", "kimdir", "kimler", "nedir", "ne", "hangi", "bolum",
                "bolumu", "bolumde", "hoca", "hocasi", "unvani", "unvan",
                "gorevi", "gorevli", "calisiyor", "calisir", "nerede", "kisi",
                "veriyor", "dersleri", "ders", "mi", "midir", "adli", "isimli"}
    return [k for k in re.findall(r"\w+", soru)
            if len(k) > 2 and normalize_tr(k) not in atilacak]


# Kişinin KİMLİĞİNİ soran kalıplar. Ders/telefon soruları bilerek DIŞARIDA:
# "X hangi dersleri veriyor" sorusunun cevabı unvan değil ders listesi, o soru
# modele gitmeli.
#
# NEDEN KALIP LİSTESİ: Önce yalnızca "kim/kimdir" tetikliyordu. Kullanıcı
# "Bilgisayar Mühendisliğinde bir hoca soruyorum, Yapay Zeka'da görevli diyor"
# diye bildirdi: "X hangi bölümde" gibi sorular modele düşüyordu ve 2B model
# bağlamdaki üç bölümün arasından yanlışını seçebiliyordu. Kimlik sorusunun
# cevabı kadro satırında yazılı; model bu işe hiç karışmamalı.
KIMLIK_KALIPLARI = ("kimdir", "kim", "hangi bolum", "hangi bolumde",
                    "nerede calis", "unvani", "gorevi ne", "hangi birim")


# Kimlik dalından MUAF konular: cevabı unvan değil, başka bir alan.
# "X hangi dersleri veriyor" -> ders listesi, "X'in telefonu" -> numara.
BASKA_ALAN = ("ders", "telefon", "mail", "posta", "numara", "adres")


def _baska_alan_sorusu(soru: str) -> bool:
    norm = normalize_tr(soru)
    return any(k in norm for k in BASKA_ALAN)


def _kimlik_sorusu_mu(soru: str) -> bool:
    if _baska_alan_sorusu(soru):
        return False
    norm = normalize_tr(soru)
    return any(normalize_tr(k) in norm for k in KIMLIK_KALIPLARI)


def dogrudan_cevap(soru: str, sonuclar, kimlik: bool = False) -> tuple[str, object] | None:
    """Soru yapısal olarak cevaplanabiliyorsa (cevap, kaynak) döndürür.

    Cevap bulunamazsa None -> normal LLM akisi devreye girer.
    """
    if not sonuclar:
        return None

    # --- Kişi kimliği: "X kimdir", "X hangi bölümde", "X'in unvanı ne" ---
    # kimlik=True: çağıran taraf sorunun kadrodaki bir adı içerdiğini zaten
    # doğruladı. Çıplak ad ("aybüke babadağ") hiçbir kalıba uymuyor ama
    # cevabı yine kadro satırı — modele gidince unvan uyduruluyordu.
    if (kimlik and not _baska_alan_sorusu(soru)) or _kimlik_sorusu_mu(soru):
        parcalar = _ad_parcalari(soru)
        if len(parcalar) >= 2:                       # ad + soyad
            # Kaynak önceliği: kişinin KENDİ sayfası ve bölümünün kadro listesi
            # önce gelsin. Sitede eski "Akademik Danışman" listeleri var ve
            # oralarda unvanlar güncellenmemiş (İsmail KOÇ orada hâlâ
            # "Dr. Öğr. Üyesi", kadro listesinde "Doç. Dr.").
            def oncelik(s):
                baslik = normalize_tr(s.title)
                kendi_sayfasi = all(normalize_tr(p) in baslik for p in parcalar)
                kadro = "akademik personel" in baslik
                return (0 if kendi_sayfasi else 1 if kadro else 2)

            sirali = sorted(sonuclar, key=oncelik)
            for s in sirali:
                satir = kisi_satiri_cikar(s.text, parcalar)
                if satir:
                    birim = s.unit or "KTÜN"
                    return f"{satir} — {birim} akademik kadrosunda.", s

            # İkinci yol: kişinin KENDİ sayfası. Başlık zaten "<birim> — <unvan>
            # <ad>" biçiminde, yani unvan orada bir alan gibi duruyor. Kadro
            # listesi sonuçlara girmediğinde (ölçümde 65 kişiden 3'ü) bu yol
            # devreye giriyor ve soru yine modele gitmiyor.
            for s in sirali:
                baslik = normalize_tr(s.title)
                if not all(normalize_tr(p) in baslik for p in parcalar):
                    continue
                for unvan in UNVANLAR:
                    if normalize_tr(unvan) in baslik:
                        ad = s.title.split("—")[-1].strip()
                        return f"{ad} — {s.unit or 'KTÜN'} akademik kadrosunda.", s

    # --- Ders kodu sorusu: "YAZ102 kaç kredi", "BBF101 dersinin adı ne" ---
    kod_eslesme = _DERS_KODU.search(soru)
    if kod_eslesme:
        kod = kod_eslesme.group(1)
        for s in sonuclar:
            bulunan = ders_satiri_cikar(s.text, kod)
            if not bulunan:
                continue
            ad, akts, koordinator = bulunan
            parcalar = [f"{kod.upper()} dersinin adı {ad}."]
            if akts:
                parcalar.append(f"AKTS kredisi {akts}.")
            if koordinator:
                parcalar.append(f"Dersin koordinatörü {koordinator}.")
            return " ".join(parcalar), s

    # --- İletişim sorusu: telefon / e-posta / adres ---
    niyet = _niyet_bul(soru)
    if niyet is None:
        return None

    cikaricilar = {
        "telefon": (telefon_cikar, "{birim} telefon numarası: {deger}"),
        "eposta": (eposta_cikar, "{birim} e-posta adresi: {deger}"),
        "adres": (adres_cikar, "{birim} adresi: {deger}"),
    }
    cikarici, sablon = cikaricilar[niyet]

    # Once "Iletisim" sayfalarina bak — alanlar orada duzenli duruyor.
    sirali = sorted(sonuclar, key=lambda s: "iletişim" not in s.title.casefold())

    for s in sirali:
        deger = cikarici(s.text)
        if deger:
            birim = s.unit or "KTÜN"
            return sablon.format(birim=birim, deger=deger), s

    return None


if __name__ == "__main__":
    from common.console import setup_stdout_utf8
    from bot.retriever import Retriever

    setup_stdout_utf8()
    retriever = Retriever()

    sorular = [
        "Yazılım Mühendisliği bölümünün telefonu nedir",
        "Bilgisayar Mühendisliği e-posta adresi nedir",
        "Yapay Zeka bölümünün adresi nerede",
        "YAZ102 dersi kaç kredi",
        "BBF101 dersinin koordinatörü kim",
        "yatay geçiş nasıl yapılır",          # yapisal degil -> LLM'e gitmeli
    ]
    for soru in sorular:
        sonuclar = retriever.search(soru, k=4)
        cevap = dogrudan_cevap(soru, sonuclar)
        if cevap:
            print(f"  DOGRUDAN  {soru[:44]:46} -> {cevap[0][:70]}")
        else:
            print(f"  LLM'E GIT {soru[:44]:46} -> (yapisal cevap yok)")
