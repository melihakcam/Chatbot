"""HTML/PDF -> SCHEMA.md'deki alanlar.

make_sample.py'deki çıkarma mantığının büyütülmüş hâli. Fark: orada sayfa
tipleri elle biliniyordu (hedef listeden geliyorlardı), burada sayfa nereden
geldiği bilinmeden tanınmak zorunda — doc_type URL deseninden ve içerikten
çıkarılıyor.

SİTEDEN ÖĞRENİLENLER (bu dosyadaki her tuhaflığın sebebi):
    1. İçerik <main id="mainContent"> içinde; üst mega-menü dışında.
    2. Birimin yan menüsü mainContent'in İÇİNDE. Link keşfi için gerekli,
       metne girerse tüm sayfalar birbirine benzer -> arama isabeti çöker.
       Bu yüzden linkler metin temizlenmeden ÖNCE toplanır.
    3. Duyuru sayfasında iki <h1> var; ilki jenerik ("Duyuru Detay").
    4. Tablolar düz metne çevrilirse 'hangi ders kaç kredi' ilişkisi kaybolur.
"""

import io
import re
from datetime import date, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

# Metinden silinecekler. Yan menü burada siliniyor çünkü linkleri zaten
# ayrı olarak (temizlikten önce) topluyoruz.
GURULTU_SECICILER = (
    "script, style, noscript, svg, "
    ".gdlr-core-pbf-sidebar-left, .gdlr-core-pbf-sidebar-right, .kingster-sidebar-area"
)

JENERIK_BASLIKLAR = {"duyuru detay", "haber detay", "anasayfa", "detay", ""}

AYLAR = {"ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6,
         "temmuz": 7, "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12}

_TARIH_YAZI_RE = re.compile(
    r"(\d{1,2})\s*\n?\s*(" + "|".join(AYLAR) + r")\s*\n?\s*(\d{4})", re.I)
_TARIH_NOKTA_RE = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")
# Duyuru başlığındaki tarih rozeti yılı yazmayabiliyor: sadece "30 / Ocak".
_TARIH_YILSIZ_RE = re.compile(
    r"\b(\d{1,2})\s*\n?\s*(" + "|".join(AYLAR) + r")\b(?!\s*\n?\s*\d{4})", re.I)
# Rozet sayfanın en başında. Daha aşağıda geçen "15 Eylül'e kadar" gibi ifadeler
# yayın tarihi değildir; o yüzden yılsız arama sadece bu pencerede yapılır.
YILSIZ_PENCERE = 300

# Ders listesi sayfa metninde değil; program id'si onclick içinde saklı.
DERS_PROGRAM_RE = re.compile(r"derslistegetir\((\d+)\)")


def coz(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def ana_govde(soup: BeautifulSoup):
    return soup.find("main", id="mainContent") or soup.body


# ---------------------------------------------------------------- metin

def table_to_markdown(table) -> str:
    """<table>'ı satır bütünlüğü korunacak şekilde metne çevirir.

    Her satır tek satırda `hücre | hücre` olarak kalır (SCHEMA.md kural 4).
    """
    satirlar = []
    for tr in table.find_all("tr"):
        hucreler = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        hucreler = [h for h in hucreler if h]
        if hucreler:
            satirlar.append(" | ".join(hucreler))
    return "\n".join(satirlar)


def metin_cikar(soup: BeautifulSoup) -> str:
    """mainContent'ten temiz metin. Tablolar markdown satırı olarak korunur.

    DİKKAT: soup'u yerinde değiştirir (yan menüyü siler). Link toplama bu
    çağrıdan ÖNCE yapılmalı.
    """
    main = ana_govde(soup)
    if main is None:
        return ""

    for etiket in main.select(GURULTU_SECICILER):
        etiket.decompose()

    for table in main.find_all("table"):
        table.replace_with(soup.new_string("\n" + table_to_markdown(table) + "\n"))

    satirlar = (s.strip() for s in main.get_text("\n").split("\n"))
    return "\n".join(s for s in satirlar if s)


def pdf_metni(icerik: bytes) -> str:
    """PDF'ten metin. Akademik takvim buradan geliyor (iframe içindeki PDF).

    Site PDF'leri metin tabanlı, OCR gerekmiyor. Taranmış bir PDF gelirse
    çıktı boş olur ve kayıt 20 karakter kuralına takılıp elenir — istenen
    davranış bu, boş kayıt yazmaktansa hiç yazmamak.
    """
    from pypdf import PdfReader
    try:
        reader = PdfReader(io.BytesIO(icerik))
        return "\n".join((s.extract_text() or "") for s in reader.pages).strip()
    except Exception as e:
        print(f"  ! PDF okunamadi ({type(e).__name__})")
        return ""


# ---------------------------------------------------------------- alanlar

def baslik_bul(soup: BeautifulSoup) -> str:
    """İlk anlamlı başlık. Jenerik olanları atlar (tuzak: iki <h1>)."""
    main = ana_govde(soup)
    if main is None:
        return ""
    for etiket in ("h1", "h2", "h3"):
        for bulunan in main.find_all(etiket):
            metin = bulunan.get_text(strip=True)
            if metin and metin.lower() not in JENERIK_BASLIKLAR:
                return metin
    baslik = soup.find("title")
    return baslik.get_text(strip=True) if baslik else ""


def tarih_bul(metin: str, yil_tahmin: bool = False, bugun: date | None = None) -> str | None:
    """'12 Ağustos 2026' veya '12.08.2026' -> '2026-08-12'.

    yil_tahmin=True ise yılsız rozet ("30 / Ocak") de kabul edilir ve yıl
    tahmin edilir: önce bu yıl, o tarih geleceğe düşüyorsa geçen yıl. Site
    yılı yazmadığında kastettiği hep en yakın geçmiş tarihtir. Yalnızca
    duyuru/haber için açılır — şema oralarda tarih ZORUNLU tutuyor.
    """
    m = _TARIH_YAZI_RE.search(metin)
    if m:
        return f"{m.group(3)}-{AYLAR[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    m = _TARIH_NOKTA_RE.search(metin)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    if not yil_tahmin:
        return None

    m = _TARIH_YILSIZ_RE.search(metin[:YILSIZ_PENCERE])
    if m:
        bugun = bugun or date.today()
        gun, ay = int(m.group(1)), AYLAR[m.group(2).lower()]
        for yil in (bugun.year, bugun.year - 1):
            try:
                aday = date(yil, ay, gun)
            except ValueError:
                continue  # 31 Şubat gibi bir eşleşme
            # Küçük tolerans: sunucu saati/ileri tarihli duyuru bir günlük
            # sapma yapabilir, bu yüzden "gelecek" eşiği bugün değil bugün+2.
            if aday <= bugun + timedelta(days=2):
                return aday.isoformat()
    return None


# URL deseni -> doc_type. Sıra önemli: ilk eşleşen kazanır.
_TIP_DESENLERI = [
    ("duyuru",   ("/duyurudetay/", "duyurudetay")),
    ("haber",    ("/haberdetay/", "haberdetay")),
    ("personel", ("akademikpersonel", "idaripersonel", "telefonrehberi",
                  "personeldetay", "prsnl=")),
    ("tablo",    ("bolumderslistesigetir", "bolumdersleri", "ogretimplani",
                  "dersplani", "sinavprogram")),
]


def tip_bul(url: str, metin: str, pdf: bool = False) -> str:
    """doc_type kararı: önce URL deseni, sonra içeriğin şekli.

    URL deseni tutmazsa metne bakılır: satırların çoğu '|' içeriyorsa
    (markdown tablosu) sayfanın gövdesi tablodur -> 'tablo'.
    """
    if pdf:
        return "pdf"

    kucuk = url.lower()
    for tip, desenler in _TIP_DESENLERI:
        if any(d in kucuk for d in desenler):
            return tip

    satirlar = [s for s in metin.split("\n") if s.strip()]
    if satirlar:
        boru_orani = sum("|" in s for s in satirlar) / len(satirlar)
        if boru_orani > 0.5 and len(satirlar) > 4:
            return "tablo"
    return "sayfa"


# ---------------------------------------------------------------- linkler

def linkleri_topla(soup: BeautifulSoup, taban: str) -> list[tuple[str, str]]:
    """(görünen ad, mutlak URL) listesi. Metin temizliğinden ÖNCE çağrılmalı.

    Kritik: urljoin dışında URL'e dokunulmuyor. brm/prsnl Base64 değerleri
    içindeki '+' ve '=' olduğu gibi kalmalı (tuzak #1). BeautifulSoup href'i
    zaten html.unescape edilmiş verir, ek işlem gerekmez.
    """
    main = ana_govde(soup) or soup
    cikti = []
    for a in main.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        cikti.append((a.get_text(" ", strip=True), urljoin(taban, href)))
    return cikti


def iframe_pdfleri(soup: BeautifulSoup, taban: str) -> list[str]:
    """Sayfaya gömülü PDF'ler. Akademik takvim SADECE burada bulunur."""
    cikti = []
    for iframe in soup.find_all("iframe", src=True):
        url = urljoin(taban, iframe["src"])
        if ".pdf" in url.lower():
            cikti.append(url)
    return cikti


def ders_program_idleri(html: str) -> list[str]:
    """onclick="derslistegetir(5018)" içindeki program id'leri, sırası bozulmadan."""
    return list(dict.fromkeys(DERS_PROGRAM_RE.findall(html)))
