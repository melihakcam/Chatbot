"""M0 — Örnek veri üretici (tek kullanımlık).

AMAÇ:
    B (bot tarafı) A'nın crawler'ını beklemesin diye, ktun.edu.tr'den ~40 gerçek
    sayfa çekip data/sample/pages.sample.jsonl dosyasını üretir. Bu dosya repoya
    commit'lenir ve dört hedef soru tipini de kapsar:
        kişi/iletişim · tarih/takvim · ders/program · duyuru/haber

    A daha sonra bu script'teki çekme/çıkarma mantığını crawler/ altına büyütür.
    B bu dosyaya bir daha dokunmaz, sadece okur.

ÇALIŞTIRMA:
    python scripts/make_sample.py

SİTE HAKKINDA ÖĞRENİLENLER (crawler'a taşınacak):
    1. İçerik <main id="mainContent"> içinde. Üst mega-menü bu etiketin DIŞINDA,
       bölümün kendi yan menüsü İÇİNDE — birimin alt sayfalarını ayırt etmenin yolu bu.
    2. brm parametresi BİRİM BAŞINA DEĞİL, SAYFA BAŞINA. Yani URL'ler tahmin
       edilerek üretilemez; her sayfa yan menüden keşfedilmek zorunda.
    3. brm/prsnl değerleri Base64 — içinde '+' ve '=' var. '+' query string'de
       boşluğa döner. URL'ler ASLA yeniden encode edilmez (bkz. SCHEMA.md).
    4. Akademik takvim sayfa metninde yok, <iframe> içindeki PDF'te.
    5. Ders listeleri <table> içinde — düz metne çevrilirse kredi bilgisi kaybolur.
"""

import hashlib
import io
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.console import setup_stdout_utf8

BASE = "https://www.ktun.edu.tr"
OUT = Path(__file__).resolve().parent.parent / "data" / "sample" / "pages.sample.jsonl"
DELAY = 1.0  # nezaket: saniyede 1 istek

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "KTUN-Support-Bot/0.1 (KTUN ogrenci destek chatbotu; egitim projesi)"
})

# Projenin hedef fakültesi. Bu fakültenin TÜM bölümleri örneğe girer.
HEDEF_FAKULTE = "Bilgisayar ve Bilişim Bilimleri Fakültesi"

# Bölümün yan menüsünden alınacak alt sayfalar (menüdeki görünen adlarıyla)
HEDEF_ALT_SAYFALAR = [
    "Hakkımızda", "Akademik Personel", "Bölüm Dersleri",
    "Program Çıktıları", "Öğretim Planı", "Sınav Programları", "İletişim",
]

GENEL_SAYFALAR = [
    "/tr/Universite/Tanitim",
    "/tr/Universite/AkademikTakvim",
    "/tr/Universite/AkademikTakvimLEE",
]


# ---------------------------------------------------------------- çekme

def fetch(url: str) -> requests.Response | None:
    """Tek sayfa çeker. URL'i yeniden encode ETMEZ (tuzak #1)."""
    try:
        r = SESSION.get(url, timeout=30)
        r.encoding = "utf-8"
        time.sleep(DELAY)
        if r.status_code != 200:
            print(f"  ! HTTP {r.status_code}: {url[:80]}")
            return None
        return r
    except requests.RequestException as e:
        print(f"  ! {type(e).__name__}: {url[:80]}")
        return None


# ---------------------------------------------------------------- çıkarma

def table_to_markdown(table) -> str:
    """<table>'ı satır bütünlüğü korunacak şekilde metne çevirir (tuzak #4).

    Düz etiket temizliği hücreleri alt alta dizer ve 'hangi ders kaç kredi'
    ilişkisi kaybolur. Markdown satırı bunu tek satırda tutar.
    """
    satirlar = []
    for tr in table.find_all("tr"):
        hucreler = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        hucreler = [h for h in hucreler if h]
        if hucreler:
            satirlar.append(" | ".join(hucreler))
    return "\n".join(satirlar)


# Birimin yan menüsü mainContent'in İÇİNDE. Alt sayfaları keşfetmek için gerekli
# ama metne girerse her sayfa aynı 20 menü maddesiyle başlar, sayfalar birbirine
# benzer ve arama isabeti çöker. Linkler yan_menu()'de ayrı soup'tan okunduğu için
# burada gönül rahatlığıyla siliniyor.
GURULTU_SECICILER = (
    "script, style, noscript, svg, "
    ".gdlr-core-pbf-sidebar-left, .gdlr-core-pbf-sidebar-right, .kingster-sidebar-area"
)


def extract_text(html: str) -> tuple[str, BeautifulSoup]:
    """mainContent'ten temiz metin üretir; tabloları markdown olarak korur."""
    soup = BeautifulSoup(html, "lxml")
    main = soup.find("main", id="mainContent") or soup.body
    if main is None:
        return "", soup

    for etiket in main.select(GURULTU_SECICILER):
        etiket.decompose()

    for table in main.find_all("table"):
        table.replace_with(soup.new_string("\n" + table_to_markdown(table) + "\n"))

    satirlar = [s.strip() for s in main.get_text("\n").split("\n")]
    return "\n".join(s for s in satirlar if s), soup


def extract_pdf(icerik: bytes) -> str:
    from pypdf import PdfReader
    try:
        reader = PdfReader(io.BytesIO(icerik))
        return "\n".join((s.extract_text() or "") for s in reader.pages).strip()
    except Exception as e:
        print(f"  ! PDF okunamadi: {type(e).__name__}")
        return ""


# Sayfa başlık çubuğundaki jenerik başlıklar — gerçek başlık bunlardan sonra gelir.
# Duyuru sayfasında İKİ <h1> var: "Duyuru Detay" ve asıl duyuru başlığı.
JENERIK_BASLIKLAR = {"duyuru detay", "haber detay", "anasayfa", "detay", ""}


def sayfa_basligi(soup: BeautifulSoup) -> str:
    main = soup.find("main", id="mainContent")
    if main is None:
        return ""
    for etiket in ("h1", "h2", "h3"):
        for bulunan in main.find_all(etiket):
            metin = bulunan.get_text(strip=True)
            if metin.lower() not in JENERIK_BASLIKLAR:
                return metin
    return ""


def tarih_bul(metin: str) -> str | None:
    """Duyuru/haber sayfasındaki '12 Ağustos 2026' veya '12.08.2026' formatını yakalar."""
    AYLAR = {"ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6,
             "temmuz": 7, "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12}
    m = re.search(r"(\d{1,2})\s*\n?\s*(" + "|".join(AYLAR) + r")\s*\n?\s*(\d{4})", metin, re.I)
    if m:
        return f"{m.group(3)}-{AYLAR[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    m = re.search(r"\b(\d{2})\.(\d{2})\.(\d{4})\b", metin)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return None


# ---------------------------------------------------------------- kayıt

def kayit_olustur(url, title, breadcrumb, unit, doc_type, text, published_at=None) -> dict | None:
    text = text.strip()
    if len(text) < 20:
        return None
    return {
        "url": url,
        "title": title or (unit or url.rsplit("/", 1)[-1]),
        "breadcrumb": breadcrumb,
        "unit": unit,
        "doc_type": doc_type,
        "text": text,
        "published_at": published_at,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "content_hash": hashlib.sha1(text.encode("utf-8")).hexdigest(),
    }


# ---------------------------------------------------------------- toplama

def birimleri_kesfet() -> dict[str, str]:
    """Ana sayfadaki mega-menüden bölüm adı -> giriş URL'i eşlemesi çıkarır."""
    r = fetch(BASE + "/")
    if r is None:
        return {}
    soup = BeautifulSoup(r.text, "lxml")
    birimler = {}
    for a in soup.find_all("a", href=True):
        if "/tr/Birim/" in a["href"]:
            ad = a.get_text(strip=True)
            if ad and len(ad) > 3:
                birimler.setdefault(ad, urljoin(BASE, a["href"]))
    return birimler


def yan_menu(html: str) -> dict[str, str]:
    """Birimin KENDİ alt sayfalarını verir.

    Üst mega-menü mainContent'in dışında, birimin yan menüsü içinde —
    ayrım noktası bu. brm sayfa başına değiştiği için URL'ler tahmin edilemez,
    buradan keşfedilmek zorunda.
    """
    soup = BeautifulSoup(html, "lxml")
    main = soup.find("main", id="mainContent")
    if main is None:
        return {}
    return {
        a.get_text(strip=True): urljoin(BASE, a["href"])
        for a in main.find_all("a", href=True)
        if "/tr/Birim/" in a["href"] and a.get_text(strip=True)
    }


DERS_LISTESI_UCU = BASE + "/tr/Birim/BolumDersListesiGetir"


def ders_listeleri(bolum_adi: str, bolum_dersleri_html: str, kaynak_url: str) -> list[dict]:
    """Ders listesini AJAX ucundan çeker.

    'Bölüm Dersleri' sayfası boş görünür (57 karakter) — içinde sadece bir
    "Program Seçiniz" tablosu vardır. Asıl ders listesi tıklanınca
    /tr/Birim/BolumDersListesiGetir?id=<program_id> ucundan gelir. Program id'si
    sayfadaki onclick="derslistegetir(5018)" içinde duruyor.

    Bu liste ders kodu / ad / AKTS / koordinatör içerir; "kaç kredi", "hangi
    dönemde hangi ders" sorularının tek kaynağı budur.
    """
    kayitlar = []
    programlar = re.findall(r"derslistegetir\((\d+)\)", bolum_dersleri_html)
    for program_id in dict.fromkeys(programlar):
        r = fetch(f"{DERS_LISTESI_UCU}?id={program_id}")
        if r is None:
            continue
        soup = BeautifulSoup(r.text, "lxml")
        parcalar = []
        for table in soup.find_all("table"):
            parcalar.append(table_to_markdown(table))
        metin = "\n".join(p for p in parcalar if p)
        kayit = kayit_olustur(
            f"{DERS_LISTESI_UCU}?id={program_id}",
            f"{bolum_adi} — Ders Listesi (AKTS)",
            ["Akademik", bolum_adi, "Bölüm Dersleri"], bolum_adi, "tablo", metin,
        )
        if kayit:
            kayitlar.append(kayit)
            satir = metin.count("\n") + 1
            print(f"    -> ders listesi (id={program_id}): {satir} satir, {len(metin)} chr")
    return kayitlar


def bolumleri_kesfet(fakulte_url: str) -> dict[str, str]:
    """Fakültenin 'Bölümler' sayfasından bölüm adı -> URL eşlemesi çıkarır.

    Bölümler ana menüde YOK, iki kademe derinde: ana menü -> fakülte -> Bölümler.
    'Bölümler' sayfasının mainContent'i hem fakültenin yan menüsünü hem de bölüm
    listesini içerir. Ayırmak için küme farkı alıyoruz: fakülte sayfasında da olan
    linkler yan menüdür, sadece Bölümler sayfasında olanlar gerçek bölümlerdir.
    """
    r = fetch(fakulte_url)
    if r is None:
        return {}
    yan_menu_linkleri = yan_menu(r.text)

    bolumler_url = next((u for ad, u in yan_menu_linkleri.items() if ad.startswith("Bölümler")), None)
    if bolumler_url is None:
        return {}

    rr = fetch(bolumler_url)
    if rr is None:
        return {}

    hepsi = yan_menu(rr.text)
    return {ad: url for ad, url in hepsi.items() if ad not in yan_menu_linkleri}


def bolum_sayfalari(bolum_adi: str, giris_url: str) -> list[dict]:
    print(f"\n[BOLUM] {bolum_adi}")
    kayitlar = []
    r = fetch(giris_url)
    if r is None:
        return kayitlar

    menu = yan_menu(r.text)
    print(f"  yan menude {len(menu)} alt sayfa bulundu")

    for menu_adi in HEDEF_ALT_SAYFALAR:
        url = next((u for ad, u in menu.items() if ad.startswith(menu_adi)), None)
        if url is None:
            continue
        rr = fetch(url)
        if rr is None:
            continue
        metin, _ = extract_text(rr.text)
        tip = ("personel" if "Personel" in menu_adi else
               "tablo" if "Ders" in menu_adi or "Plan" in menu_adi else "sayfa")
        # Başlık olarak sayfanın <h1>'i kullanılmıyor: bölüm alt sayfalarında h1
        # hep bölüm adını veriyor, hangi sayfa olduğu kayboluyor.
        kayit = kayit_olustur(
            url, f"{bolum_adi} — {menu_adi}",
            ["Akademik", bolum_adi, menu_adi], bolum_adi, tip, metin,
        )
        if kayit:
            kayitlar.append(kayit)
            print(f"  + {menu_adi:22} {len(metin):>6} chr  [{tip}]")
        else:
            print(f"  - {menu_adi:22} (bos, atlandi)")

        # Ders listesi sayfa metninde değil, AJAX ucunda.
        if menu_adi == "Bölüm Dersleri":
            kayitlar += ders_listeleri(bolum_adi, rr.text, url)
    return kayitlar


def liste_sayfalari(liste_yolu: str, detay_deseni: str, doc_type: str, adet: int) -> list[dict]:
    print(f"\n[{doc_type.upper()}]")
    kayitlar = []
    r = fetch(f"{BASE}{liste_yolu}?page=1")
    if r is None:
        return kayitlar

    soup = BeautifulSoup(r.text, "lxml")
    linkler = list(dict.fromkeys(
        urljoin(BASE, a["href"]) for a in soup.find_all("a", href=True)
        if detay_deseni in a["href"]
    ))[:adet]

    for url in linkler:
        rr = fetch(url)
        if rr is None:
            continue
        metin, ssoup = extract_text(rr.text)
        kayit = kayit_olustur(
            url, sayfa_basligi(ssoup), ["Üniversitemiz", doc_type.capitalize()],
            None, doc_type, metin, published_at=tarih_bul(metin),
        )
        if kayit:
            kayitlar.append(kayit)
            print(f"  + {kayit['published_at']}  {kayit['title'][:52]}")
    return kayitlar


def genel_sayfalar() -> list[dict]:
    print("\n[GENEL SAYFALAR + IFRAME PDF]")
    kayitlar = []
    for yol in GENEL_SAYFALAR:
        url = BASE + yol
        r = fetch(url)
        if r is None:
            continue
        metin, soup = extract_text(r.text)
        baslik = sayfa_basligi(soup) or yol.rsplit("/", 1)[-1]

        kayit = kayit_olustur(url, baslik, ["Üniversitemiz"], None, "sayfa", metin)
        if kayit:
            kayitlar.append(kayit)
            print(f"  + {baslik[:45]:47} {len(metin):>6} chr")

        # Kritik: akademik takvim sayfa metninde YOK, iframe içindeki PDF'te (tuzak #3)
        for iframe in soup.find_all("iframe", src=True):
            pdf_url = urljoin(BASE, iframe["src"])
            if ".pdf" not in pdf_url.lower():
                continue
            pr = fetch(pdf_url)
            if pr is None:
                continue
            pdf_metin = extract_pdf(pr.content)
            pkayit = kayit_olustur(
                pdf_url, baslik + " (PDF)", ["Üniversitemiz", baslik], None, "pdf", pdf_metin,
            )
            if pkayit:
                kayitlar.append(pkayit)
                print(f"    -> iframe PDF: {len(pdf_metin):>6} chr  {pdf_url.rsplit('/', 1)[-1][:40]}")
    return kayitlar


# ---------------------------------------------------------------- main

def main() -> int:
    setup_stdout_utf8()
    print("KTUN ornek veri uretici — data/sample/pages.sample.jsonl\n" + "=" * 62)

    kayitlar: list[dict] = []
    kayitlar += genel_sayfalar()

    birimler = birimleri_kesfet()
    print(f"\nMega-menude {len(birimler)} birim linki bulundu")

    # Bölümler ana menüde değil, fakültenin altında (2 kademe derinde).
    fakulte_url = next((u for ad, u in birimler.items() if ad.startswith(HEDEF_FAKULTE)), None)
    if fakulte_url is None:
        print(f"HATA: '{HEDEF_FAKULTE}' menude bulunamadi")
        return 1

    bolumler = bolumleri_kesfet(fakulte_url)
    print(f"{HEDEF_FAKULTE}: {len(bolumler)} bolum")
    for ad in bolumler:
        print(f"  - {ad}")

    for bolum_adi, bolum_url in bolumler.items():
        kayitlar += bolum_sayfalari(bolum_adi, bolum_url)

    kayitlar += liste_sayfalari("/tr/Universite/TumDuyurular", "/DuyuruDetay/", "duyuru", 8)
    kayitlar += liste_sayfalari("/tr/Universite/TumHaberler", "/HaberDetay/", "haber", 4)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for k in kayitlar:
            f.write(json.dumps(k, ensure_ascii=False) + "\n")

    print("\n" + "=" * 62)
    print(f"YAZILDI: {OUT}  ({len(kayitlar)} kayit)")
    dagilim: dict[str, int] = {}
    for k in kayitlar:
        dagilim[k["doc_type"]] = dagilim.get(k["doc_type"], 0) + 1
    print("Tip dagilimi:", dagilim)
    return 0 if kayitlar else 1


if __name__ == "__main__":
    raise SystemExit(main())
