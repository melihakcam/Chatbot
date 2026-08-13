"""pages.jsonl yazıcı — şemayı üreten ve tekrarı önleyen tek yer.

SCHEMA.md kural 2: aynı url iki kez yazılmaz; tekrar çalıştırmada
content_hash aynıysa satır atlanır.

Bunu yapmanın iki yolu var: dosyaya ekleyerek yazmak (ama o zaman değişen
sayfa iki satır olur) veya mevcut dosyayı okuyup birleştirip baştan yazmak.
İkincisi seçildi — dosya birkaç bin satır, bellekte rahat durur; karşılığında
"her url için tam bir satır" garantisi bedavaya gelir.
"""

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

GECERLI_TIPLER = {"personel", "duyuru", "haber", "sayfa", "pdf", "tablo"}
MIN_METIN = 20


def kayit_olustur(url: str, title: str, breadcrumb: list[str], unit: str | None,
                  doc_type: str, text: str, published_at: str | None = None) -> dict | None:
    """SCHEMA.md'deki 9 alanlı kaydı üretir. Çöp girdide None döner.

    published_at yalnızca duyuru/haber'de dolu tutulur: doğrulayıcı diğer
    tiplerde tarih beklemiyor ve sayfa metnindeki rastgele bir tarihi
    'yayın tarihi' diye kaydetmek B tarafını yanıltır.
    """
    text = (text or "").strip()
    if len(text) < MIN_METIN:
        return None
    if doc_type not in GECERLI_TIPLER:
        doc_type = "sayfa"
    if doc_type not in {"duyuru", "haber"}:
        published_at = None
    elif published_at is None:
        # Şema duyuru/haber'de tarihi ZORUNLU tutuyor. Tarih hiç bulunamadıysa
        # uydurmak yerine tipi 'sayfa'ya düşürüyoruz: metin korunur, sadece
        # "bu bir duyurudur" iddiası geri çekilir. Doğrulayıcı temiz kalır.
        doc_type = "sayfa"

    return {
        "url": url,
        "title": (title or "").strip() or (unit or url.rstrip("/").rsplit("/", 1)[-1]),
        "breadcrumb": [b for b in breadcrumb if b],
        "unit": unit,
        "doc_type": doc_type,
        "text": text,
        "published_at": published_at,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "content_hash": hashlib.sha1(text.encode("utf-8")).hexdigest(),
    }


class Depo:
    """Mevcut jsonl'i okur, yeni kayıtları birleştirir, tek seferde yazar."""

    def __init__(self, yol: Path, devam: bool = True):
        self.yol = Path(yol)
        self.kayitlar: dict[str, dict] = {}
        self.sayac = {"yeni": 0, "guncellenen": 0, "degismeyen": 0, "elenen": 0}

        if devam and self.yol.exists():
            with self.yol.open(encoding="utf-8") as f:
                for satir in f:
                    satir = satir.strip()
                    if not satir:
                        continue
                    try:
                        k = json.loads(satir)
                    except json.JSONDecodeError:
                        continue
                    if k.get("url"):
                        self.kayitlar[k["url"]] = k

    @property
    def onceki_adet(self) -> int:
        return len(self.kayitlar) - self.sayac["yeni"]

    def var_mi(self, url: str) -> bool:
        return url in self.kayitlar

    def ekle(self, kayit: dict | None) -> str:
        """Kaydı depoya koyar. Dönen değer: yeni | guncellenen | degismeyen | elenen."""
        if kayit is None:
            self.sayac["elenen"] += 1
            return "elenen"

        eski = self.kayitlar.get(kayit["url"])
        if eski is None:
            durum = "yeni"
        elif eski.get("content_hash") == kayit["content_hash"]:
            # Sayfa değişmemiş: fetched_at'i bile güncellemiyoruz, satır
            # aynı kalsın ki git diff'i gürültü yapmasın.
            self.sayac["degismeyen"] += 1
            return "degismeyen"
        else:
            durum = "guncellenen"

        self.kayitlar[kayit["url"]] = kayit
        self.sayac[durum] += 1
        return durum

    def yaz(self) -> int:
        """Önce .tmp'e yazıp sonra yerine koyar — yarıda kesilirse eski dosya sağlam kalır."""
        self.yol.parent.mkdir(parents=True, exist_ok=True)
        gecici = self.yol.with_suffix(self.yol.suffix + ".tmp")
        with gecici.open("w", encoding="utf-8") as f:
            for kayit in self.kayitlar.values():
                f.write(json.dumps(kayit, ensure_ascii=False) + "\n")
        os.replace(gecici, self.yol)
        return len(self.kayitlar)
