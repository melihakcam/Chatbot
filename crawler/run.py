"""KTÜN crawler — BFS ile gezer, pages.jsonl üretir.

    python -m crawler.run --seed <url> --derinlik 2 --out data/raw/pages.jsonl
    python -m crawler.run --tum-site --max-sayfa 400

NEDEN BFS:
    Site haritası ve robots.txt yok, brm parametresi sayfa başına değişiyor —
    yani URL'ler tahmin edilemiyor, sadece keşfedilebiliyor. Genişlik öncelikli
    gezinti derinliğe dalmadan önce her birimin ana sayfalarını toplar; crawl
    yarıda kesilse bile elde dengeli bir veri kalır.

ÖZEL DURUMLAR (düz BFS'in kaçıracağı üç şey):
    · Akademik takvim sayfa metninde yok, <iframe> içindeki PDF'te.
    · Ders listesi sayfada yok, /BolumDersListesiGetir?id=<n> ucunda.
    · Yan menü linkleri metinden silinen bölgede — temizlikten önce toplanıyor.
"""

import argparse
import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.console import setup_stdout_utf8
from crawler import extract, scope
from crawler.fetch import BASE, Cekici
from crawler.store import Depo, kayit_olustur

DERS_LISTESI_UCU = BASE + "/tr/Birim/BolumDersListesiGetir"

KISI_YOLU = "/tr/Universite/PersonelBilgi"

# Kişi sayfasında toplanan sekmeler. Hepsi POST /tr/Universite/<sekme>.
# Yayın listeleri (Makaleler, Kitaplar, Bildiriler…) bilerek dışarıda:
# hedef soru tipleri kişi/ders odaklı, yayın listesi kaydı onlarca kat
# büyütüp aramayı sulandırıyor.
KISI_SEKMELERI = (
    ("KisiselBilgiler", "Akademik Görevler ve Öğrenim Bilgisi"),
    ("DersListesi", "Verdiği Dersler"),
)


def kisi_sayfasi_mi(url: str) -> bool:
    return KISI_YOLU.lower() in url.lower()


TUM_SITE_TOHUMLARI = [
    BASE + "/",
    BASE + "/tr/Universite/Tanitim",
    BASE + "/tr/Universite/AkademikTakvim",
    BASE + "/tr/Universite/AkademikTakvimLEE",
    BASE + "/tr/Universite/TumDuyurular?page=1",
    BASE + "/tr/Universite/TumHaberler?page=1",
]


class Gorev:
    """Kuyruktaki tek iş. Birim/breadcrumb bilgisi ebeveynden miras alınır —
    sayfanın kendisinde bu bilgi yok, nereden gelindiğinden çıkarılıyor."""

    __slots__ = ("url", "derinlik", "unit", "breadcrumb", "menu_adi")

    def __init__(self, url, derinlik=0, unit=None, breadcrumb=None, menu_adi=None):
        self.url = url
        self.derinlik = derinlik
        self.unit = unit
        self.breadcrumb = breadcrumb or []
        self.menu_adi = menu_adi


class Crawler:
    def __init__(self, cekici: Cekici, depo: Depo, max_sayfa: int, max_derinlik: int,
                 sadece_birim: bool = False, birimsiz: bool = False):
        self.cekici = cekici
        self.depo = depo
        self.max_sayfa = max_sayfa
        self.max_derinlik = max_derinlik
        self.sadece_birim = sadece_birim
        self.birimsiz = birimsiz
        self.gorulen: set[str] = set()
        self.kuyruk: deque[Gorev] = deque()
        self.islenen = 0

    # ------------------------------------------------------------ kuyruk

    def ekle(self, gorev: Gorev) -> bool:
        anahtar = scope.anahtar(gorev.url)
        if anahtar in self.gorulen or not scope.kapsamda_mi(gorev.url):
            return False
        # İki muafiyet — ikisi de /tr/Birim/ dışında durur ama içerikleri
        # bölümün ta kendisidir:
        #   · PDF     : ders/sınav programı, öğretim planı, staj belgeleri
        #   · kişi     : hocaların /tr/Universite/PersonelBilgi/ sayfaları
        if self.sadece_birim and "/tr/Birim/" not in gorev.url \
                and not scope.pdf_mi(gorev.url) and not kisi_sayfasi_mi(gorev.url):
            return False

        # Simetriği: duyuru/haber/takvim taranırken birim sayfalarına girme.
        # Duyuru listeleri her birime link veriyor; filtresiz gezinti kapsam
        # dışı bölümleri (Mimarlık, Teknik Bilimler MYO…) içeri sızdırıyor.
        if self.birimsiz and "/tr/Birim/" in gorev.url:
            return False
        self.gorulen.add(anahtar)
        self.kuyruk.append(gorev)
        return True

    def calistir(self) -> None:
        while self.kuyruk and self.islenen < self.max_sayfa:
            self.isle(self.kuyruk.popleft())

    # ------------------------------------------------------------ işleme

    def isle(self, gorev: Gorev) -> None:
        self.islenen += 1
        cevap = self.cekici.get(gorev.url)
        if cevap is None:
            return

        if cevap.pdf_mi or scope.pdf_mi(gorev.url):
            self.pdf_isle(gorev, cevap)
            return
        if not cevap.html_mi:
            return

        html = cevap.html
        soup = extract.coz(html)

        # SIRALAMA KRİTİK: linkler metin temizliğinden ÖNCE toplanmalı,
        # çünkü temizlik yan menüyü (= alt sayfaların tek kaynağı) siliyor.
        linkler = extract.linkleri_topla(soup, gorev.url)
        pdfler = extract.iframe_pdfleri(soup, gorev.url)
        program_idleri = extract.ders_program_idleri(html)

        sayfa_basligi = extract.baslik_bul(soup)
        metin = extract.metin_cikar(soup)

        if kisi_sayfasi_mi(gorev.url):
            sayfa_basligi, metin = self.kisi_sayfasi(soup, html, metin)

        # Birim sayfalarında h1 her zaman birimin adını verir, hangi alt sayfada
        # olduğumuzu değil. Bu yüzden h1 -> unit, menü adı -> başlık.
        unit = gorev.unit
        if "/tr/Birim/" in gorev.url and sayfa_basligi:
            unit = unit or sayfa_basligi

        if gorev.menu_adi and unit:
            baslik = f"{unit} — {gorev.menu_adi}"
        else:
            baslik = sayfa_basligi

        tip = extract.tip_bul(gorev.url, metin)
        # Yılsız tarih rozeti sadece duyuru/haber'de kabul ediliyor; başka
        # sayfalarda metindeki rastgele bir gün-ay ikilisi yayın tarihi sanılır.
        breadcrumb = gorev.breadcrumb or (["Akademik", unit] if unit else [])

        kayit = kayit_olustur(
            gorev.url, baslik, breadcrumb, unit, tip, metin,
            published_at=extract.tarih_bul(metin, yil_tahmin=tip in ("duyuru", "haber")),
        )
        durum = self.depo.ekle(kayit)
        self.rapor(durum, baslik or gorev.url, tip, len(metin))

        alt_breadcrumb = (breadcrumb + [gorev.menu_adi])[-4:] if gorev.menu_adi \
            else breadcrumb

        for pdf_url in pdfler:
            self.ekle(Gorev(pdf_url, gorev.derinlik, unit, alt_breadcrumb,
                            menu_adi=(gorev.menu_adi or sayfa_basligi)))

        for program_id in program_idleri:
            self.ders_listesi(program_id, unit, alt_breadcrumb)

        if gorev.derinlik >= self.max_derinlik:
            return
        for ad, url in linkler:
            self.ekle(Gorev(url, gorev.derinlik + 1, unit, alt_breadcrumb,
                            menu_adi=ad or None))

    def pdf_isle(self, gorev: Gorev, cevap) -> None:
        metin = extract.pdf_metni(cevap.icerik)
        ad = gorev.menu_adi or gorev.url.rsplit("/", 1)[-1]
        kayit = kayit_olustur(
            gorev.url, f"{ad} (PDF)", gorev.breadcrumb, gorev.unit, "pdf", metin,
        )
        self.rapor(self.depo.ekle(kayit), f"{ad} (PDF)", "pdf", len(metin))

    def kisi_sayfasi(self, soup, html: str, metin: str) -> tuple[str, str]:
        """Hocanın sekmelerini toplayıp tek metne katar.

        Kişi sayfasının kendi metni sadece ad + fakülte + bölüm; akademik
        geçmiş ve verdiği dersler POST uçlarından geliyor (`Sayfa_Getir`).
        Her sekme ayrı kayıt olsaydı URL'leri aynı olurdu — POST'un kendi
        adresi yok — ve depo hepsini tek satıra ezerdi. Bu yüzden bir hoca =
        bir kayıt: kaynak linki de gerçekten açılabilen kişi sayfası oluyor.
        """
        token = extract.personel_token(html)
        if not token:
            return extract.kisi_adi(soup) or "", metin

        parcalar = [metin]
        for sekme, baslik in KISI_SEKMELERI:
            cevap = self.cekici.post(f"{BASE}/tr/Universite/{sekme}", {"id": token})
            if cevap is None or not cevap.html_mi:
                continue
            govde = extract.metin_cikar(extract.coz(cevap.html)).strip()
            if govde:
                parcalar.append(f"{baslik}\n{govde}")

        return extract.kisi_adi(soup) or "", "\n\n".join(parcalar)

    def ders_listesi(self, program_id: str, unit: str | None, breadcrumb: list[str]) -> None:
        """Ders listesi sayfa metninde YOK, AJAX ucunda.

        'Bölüm Dersleri' sayfası boş görünür; asıl liste tıklanınca
        /BolumDersListesiGetir?id=<program_id> ucundan gelir. 'Kaç kredi',
        'hangi dönem hangi ders' sorularının tek kaynağı bu.
        """
        url = f"{DERS_LISTESI_UCU}?id={program_id}"
        if scope.anahtar(url) in self.gorulen:
            return
        self.gorulen.add(scope.anahtar(url))

        cevap = self.cekici.get(url)
        if cevap is None or not cevap.html_mi:
            return
        soup = extract.coz(cevap.html)
        metin = "\n".join(
            p for p in (extract.table_to_markdown(t) for t in soup.find_all("table")) if p
        )
        baslik = f"{unit or 'Bölüm'} — Ders Listesi (AKTS)"
        kayit = kayit_olustur(url, baslik, breadcrumb, unit, "tablo", metin)
        self.rapor(self.depo.ekle(kayit), f"{baslik} [id={program_id}]", "tablo", len(metin))

    # ------------------------------------------------------------ çıktı

    ISARET = {"yeni": "+", "guncellenen": "~", "degismeyen": "=", "elenen": "-"}

    def rapor(self, durum: str, baslik: str, tip: str, uzunluk: int) -> None:
        if self.cekici.sessiz:
            return
        print(f"  {self.ISARET[durum]} [{tip:8}] {uzunluk:>7} chr  {baslik[:58]}")


# ---------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    setup_stdout_utf8()
    ap = argparse.ArgumentParser(description="KTÜN crawler -> pages.jsonl")
    ap.add_argument("--seed", action="append", default=[],
                    help="Başlangıç URL'i (birden fazla verilebilir)")
    ap.add_argument("--tum-site", action="store_true", help="Sitenin tamamını gez")
    ap.add_argument("--unit", default=None, help="Kayıtlara yazılacak birim adı")
    ap.add_argument("--out", default="data/raw/pages.jsonl")
    ap.add_argument("--derinlik", type=int, default=2)
    ap.add_argument("--max-sayfa", type=int, default=200)
    ap.add_argument("--gecikme", type=float, default=1.0, help="İstekler arası saniye")
    ap.add_argument("--sadece-birim", action="store_true",
                    help="Yalnızca /tr/Birim/ altını gez (tek bölüm çekerken)")
    ap.add_argument("--birimsiz", action="store_true",
                    help="/tr/Birim/ altına hiç girme (duyuru/haber/takvim çekerken)")
    ap.add_argument("--sifirdan", action="store_true",
                    help="Mevcut dosyayı okumadan baştan yaz")
    ap.add_argument("--sessiz", action="store_true")
    a = ap.parse_args(argv)

    tohumlar = a.seed or (TUM_SITE_TOHUMLARI if a.tum_site else [])
    if not tohumlar:
        ap.error("--seed veya --tum-site vermelisin")

    cikti = Path(a.out)
    if not cikti.is_absolute():
        cikti = Path(__file__).resolve().parent.parent / cikti

    depo = Depo(cikti, devam=not a.sifirdan)
    cekici = Cekici(gecikme=a.gecikme, sessiz=a.sessiz)
    crawler = Crawler(cekici, depo, a.max_sayfa, a.derinlik, a.sadece_birim,
                      a.birimsiz)

    print(f"KTUN crawler — {len(tohumlar)} tohum, derinlik {a.derinlik}, "
          f"en fazla {a.max_sayfa} sayfa, {a.gecikme}s gecikme")
    print(f"Cikti: {cikti}  (dosyada {len(depo.kayitlar)} kayit var)")
    print("=" * 72)

    breadcrumb = ["Akademik", a.unit] if a.unit else []
    for url in tohumlar:
        crawler.ekle(Gorev(url, 0, a.unit, breadcrumb))

    try:
        crawler.calistir()
    except KeyboardInterrupt:
        print("\n! Kesildi — o ana kadarki kayitlar yaziliyor")

    toplam = depo.yaz()
    s, c = depo.sayac, cekici.sayac
    print("=" * 72)
    print(f"Istek: {c['istek']} ({c['basarili']} basarili, {c['hata']} hata)")
    print(f"Kayit: +{s['yeni']} yeni  ~{s['guncellenen']} guncellenen  "
          f"={s['degismeyen']} degismeyen  -{s['elenen']} elenen (kisa/bos)")
    print(f"YAZILDI: {cikti}  ({toplam} kayit)")
    print(f"\nDogrulamak icin:\n  python scripts/validate_jsonl.py {a.out}")
    return 0 if toplam else 1


if __name__ == "__main__":
    raise SystemExit(main())
