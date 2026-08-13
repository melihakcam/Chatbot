"""HTTP katmanı — nezaketli, tekrar denemeli, URL'i BOZMAYAN çekici.

NEDEN AYRI DOSYA:
    Tuzak #1 (URL yeniden encode edilmez) tek bir yerde çözülmeli. Çekim
    tek kapıdan geçerse, kod başka yerde yanlışlıkla quote/urlencode
    uygulayamaz. Buradaki get() URL'i aldığı gibi gönderir.

NEZAKET:
    ktun.edu.tr'de robots.txt YOK. "Kural yok" demek "istediğin kadar bas"
    demek değil — sunucu üniversitenin kendi sunucusu. Varsayılan saniyede
    1 istek, tek iş parçacığı. Bu sınır isteğe bağlı değil, projenin kuralı.
"""

import time

import requests

BASE = "https://www.ktun.edu.tr"

VARSAYILAN_UA = (
    "KTUN-Support-Bot/0.1 (KTUN ogrenci destek chatbotu; egitim projesi)"
)


class Cevap:
    """Çekilen tek kaynak. HTML mi PDF mi olduğunu content-type söyler."""

    def __init__(self, url: str, r: requests.Response):
        self.url = url
        self.son_url = r.url          # yönlendirme olduysa varılan yer
        self.durum = r.status_code
        self.tur = (r.headers.get("Content-Type") or "").lower()
        self.icerik = r.content
        self._r = r

    @property
    def pdf_mi(self) -> bool:
        return "pdf" in self.tur or self.son_url.lower().split("?")[0].endswith(".pdf")

    @property
    def html_mi(self) -> bool:
        return "html" in self.tur

    @property
    def html(self) -> str:
        self._r.encoding = "utf-8"
        return self._r.text


class Cekici:
    """Tek oturum + hız sınırı + tekrar deneme.

    Hız sınırı 'her istekten sonra uyu' değil, 'son istekten bu yana X saniye
    geçmediyse bekle' biçiminde. Yavaş cevap veren sayfa zaten beklemiş olur,
    üstüne bir de uyumak crawl'ı gereksiz uzatır.
    """

    def __init__(self, gecikme: float = 1.0, deneme: int = 3, zaman_asimi: int = 30,
                 sessiz: bool = False):
        self.gecikme = gecikme
        self.deneme = deneme
        self.zaman_asimi = zaman_asimi
        self.sessiz = sessiz
        self.son_istek = 0.0
        self.sayac = {"istek": 0, "basarili": 0, "hata": 0}

        self.oturum = requests.Session()
        self.oturum.headers.update({"User-Agent": VARSAYILAN_UA})

    def _bekle(self) -> None:
        kalan = self.gecikme - (time.monotonic() - self.son_istek)
        if kalan > 0:
            time.sleep(kalan)

    def _log(self, mesaj: str) -> None:
        if not self.sessiz:
            print(mesaj)

    def get(self, url: str) -> Cevap | None:
        """Tek kaynağı çeker. URL'e DOKUNMAZ (tuzak #1).

        5xx ve bağlantı hatalarında tekrar dener; 4xx'te denemez (tekrar
        denemek aynı 404'ü getirir, sadece sunucuyu meşgul eder).
        """
        for sira in range(1, self.deneme + 1):
            self._bekle()
            self.sayac["istek"] += 1
            try:
                r = self.oturum.get(url, timeout=self.zaman_asimi)
                self.son_istek = time.monotonic()
            except requests.RequestException as e:
                self.son_istek = time.monotonic()
                if sira == self.deneme:
                    self.sayac["hata"] += 1
                    self._log(f"  ! {type(e).__name__}: {url[:90]}")
                    return None
                time.sleep(self.gecikme * sira)  # artan bekleme
                continue

            if r.status_code >= 500 and sira < self.deneme:
                time.sleep(self.gecikme * sira)
                continue
            if r.status_code != 200:
                self.sayac["hata"] += 1
                self._log(f"  ! HTTP {r.status_code}: {url[:90]}")
                return None

            self.sayac["basarili"] += 1
            return Cevap(url, r)
        return None
