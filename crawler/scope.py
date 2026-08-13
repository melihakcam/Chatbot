"""Hangi URL taranır, hangisi taranmaz — ve iki URL ne zaman "aynı"dır.

Site haritası ve robots.txt YOK. Yani sınırı biz çizmek zorundayız; çizmezsek
BFS takvim widget'ında, sayfalama zincirinde veya galeri resimlerinde
sonsuza kadar dolaşır.

TUZAK #1 BURADA DA GEÇERLİ:
    anahtar() iki URL'in aynı sayfa olup olmadığına karar verir ama URL'i
    DEĞİŞTİRMEZ — sadece karşılaştırma için bir kopya üretir. Kaydedilen URL
    her zaman sayfadan çıkarıldığı hâlidir. Buradaki fonksiyonlardan hiçbiri
    quote/urlencode kullanmaz.
"""

from urllib.parse import urlsplit, urlunsplit

IZINLI_HOSTLAR = {"www.ktun.edu.tr", "ktun.edu.tr"}

# Kapsam dışı (README): alt alan adları yalnızca yönlendirme hedefi,
# içerikleri login arkasında veya ayrı sistemde.
DISLANAN_HOSTLAR = {"obs.ktun.edu.tr", "lms.ktun.edu.tr", "kutuphane.ktun.edu.tr",
                    "webmail.ktun.edu.tr"}

# İçeriği metne çevrilemeyen dosyalar. .pdf listede YOK — o çekiliyor.
DISLANAN_UZANTILAR = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".bmp",
    ".zip", ".rar", ".7z", ".exe", ".mp3", ".mp4", ".avi", ".wmv",
    ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx",
)

# Sonsuz gezinti üreten yollar: takvim widget'ı her tıklamada yeni ay üretir,
# galeri her resim için ayrı sayfa açar.
DISLANAN_PARCALAR = (
    "/en/",           # İngilizce sayfalar kapsam dışı
    "takvimgetir", "ay=", "yil=",
    "galeri", "fotogaleri", "videogaleri",
    "?print", "print=1",
    "logout", "cikis",
)


def _bolumler(url: str):
    p = urlsplit(url)
    return p, p.netloc.lower(), p.path.lower()


def kapsamda_mi(url: str) -> bool:
    """URL taranmalı mı?"""
    if not url.startswith(("http://", "https://")):
        return False
    p, host, yol = _bolumler(url)

    if host in DISLANAN_HOSTLAR or host not in IZINLI_HOSTLAR:
        return False
    if yol.endswith(DISLANAN_UZANTILAR):
        return False

    tam = (yol + "?" + p.query).lower()
    if any(parca in tam for parca in DISLANAN_PARCALAR):
        return False
    return True


def anahtar(url: str) -> str:
    """Aynılık anahtarı: fragment atılır, host küçültülür, sondaki '/' silinir.

    Query'ye DOKUNULMAZ — brm=...== ve prsnl=...+ değerleri sayfayı belirleyen
    şeyin ta kendisi; sıralamak veya yeniden yazmak ya farklı sayfaları
    birleştirir ya da aynı sayfayı ikiye böler.
    """
    p = urlsplit(url)
    yol = p.path.rstrip("/") or "/"
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), yol, p.query, ""))


def pdf_mi(url: str) -> bool:
    return urlsplit(url).path.lower().endswith(".pdf")
