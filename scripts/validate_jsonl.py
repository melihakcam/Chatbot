"""pages.jsonl şema doğrulayıcı — A ile B arasındaki ortak hakem.

A "crawler'ım bitti" derken, B "veri bozuk geliyor" derken ikisi de bu komutu
çalıştırır. Tartışma bitmiş olur.

KULLANIM:
    python scripts/validate_jsonl.py data/sample/pages.sample.jsonl
    python scripts/validate_jsonl.py data/raw/pages.jsonl

Çıkış kodu 0 = temiz, 1 = hatalı. (CI'a bağlanabilir.)
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.console import setup_stdout_utf8

ZORUNLU_ALANLAR = {
    "url", "title", "breadcrumb", "unit", "doc_type",
    "text", "published_at", "fetched_at", "content_hash",
}
GECERLI_TIPLER = {"personel", "duyuru", "haber", "sayfa", "pdf", "tablo"}
MIN_METIN = 20
TARIH_DESENI = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def satiri_dogrula(kayit: dict, no: int) -> list[str]:
    hatalar = []

    eksik = ZORUNLU_ALANLAR - kayit.keys()
    if eksik:
        hatalar.append(f"eksik alan: {sorted(eksik)}")
    fazla = kayit.keys() - ZORUNLU_ALANLAR
    if fazla:
        hatalar.append(f"sema disi alan: {sorted(fazla)}")
    if eksik:
        return hatalar  # kalan kontroller anlamsız

    if not isinstance(kayit["url"], str) or not kayit["url"].startswith("http"):
        hatalar.append("url gecersiz")
    # Tuzak #1: brm/prsnl Base64'tur, '+' yeniden encode edilirse bosluga doner.
    if "%2B" in kayit["url"] or "%3D" in kayit["url"]:
        hatalar.append("url yeniden encode edilmis (%2B/%3D) — SCHEMA.md kural 1")
    if " " in kayit["url"]:
        hatalar.append("url'de bosluk var — '+' bosluga donmus olabilir (tuzak #1)")

    if not isinstance(kayit["title"], str) or not kayit["title"].strip():
        hatalar.append("title bos")
    if not isinstance(kayit["breadcrumb"], list):
        hatalar.append("breadcrumb liste degil")
    if kayit["unit"] is not None and not isinstance(kayit["unit"], str):
        hatalar.append("unit string veya null olmali")

    if kayit["doc_type"] not in GECERLI_TIPLER:
        hatalar.append(f"gecersiz doc_type: {kayit['doc_type']!r}")

    metin = kayit.get("text")
    if not isinstance(metin, str) or len(metin.strip()) < MIN_METIN:
        hatalar.append(f"text {MIN_METIN} karakterden kisa")

    tarih = kayit["published_at"]
    if tarih is not None and not (isinstance(tarih, str) and TARIH_DESENI.match(tarih)):
        hatalar.append(f"published_at YYYY-MM-DD degil: {tarih!r}")
    if kayit["doc_type"] in {"duyuru", "haber"} and tarih is None:
        hatalar.append("duyuru/haber icin published_at bos olamaz")

    if not isinstance(kayit["fetched_at"], str) or "T" not in kayit["fetched_at"]:
        hatalar.append("fetched_at ISO 8601 degil")
    if not re.fullmatch(r"[0-9a-f]{40}", str(kayit["content_hash"])):
        hatalar.append("content_hash SHA1 degil")

    return hatalar


def main(argv: list[str]) -> int:
    setup_stdout_utf8()
    if len(argv) != 2:
        print(__doc__)
        return 2

    yol = Path(argv[1])
    if not yol.exists():
        print(f"HATA: dosya yok: {yol}")
        return 1

    toplam = bozuk = 0
    tipler: Counter[str] = Counter()
    birimler: Counter[str] = Counter()
    gorulen_url: dict[str, int] = {}
    hata_satirlari: list[str] = []

    with yol.open(encoding="utf-8") as f:
        for no, satir in enumerate(f, 1):
            satir = satir.strip()
            if not satir:
                continue
            toplam += 1
            try:
                kayit = json.loads(satir)
            except json.JSONDecodeError as e:
                bozuk += 1
                hata_satirlari.append(f"  satir {no}: JSON bozuk — {e}")
                continue

            hatalar = satiri_dogrula(kayit, no)

            url = kayit.get("url")
            if url in gorulen_url:
                hatalar.append(f"tekrar eden url (ilk gorulme: satir {gorulen_url[url]})")
            elif url:
                gorulen_url[url] = no

            if hatalar:
                bozuk += 1
                if len(hata_satirlari) < 30:
                    baslik = str(kayit.get("title", "?"))[:45]
                    hata_satirlari.append(f"  satir {no} [{baslik}]: " + "; ".join(hatalar))
            else:
                tipler[kayit["doc_type"]] += 1
                birimler[kayit["unit"] or "(genel)"] += 1

    print(f"DOSYA: {yol}")
    print(f"Toplam satir : {toplam}")
    print(f"Gecerli      : {toplam - bozuk}")
    print(f"Hatali       : {bozuk}")

    if hata_satirlari:
        print("\nHATALAR:")
        print("\n".join(hata_satirlari))

    print("\nTip dagilimi:")
    for tip, adet in tipler.most_common():
        print(f"  {tip:10} {adet:>4}")

    print(f"\nBirim sayisi: {len(birimler)}")
    for birim, adet in birimler.most_common(8):
        print(f"  {birim[:45]:47} {adet:>3}")

    # Bot tarafi icin uyarilar: hata degil ama kapsam bosluguna isaret eder.
    print()
    for tip in ("personel", "tablo", "pdf", "duyuru"):
        if tipler[tip] == 0:
            print(f"UYARI: hic '{tip}' kaydi yok — bu soru tipi cevapsiz kalir")

    print("\nSONUC: TEMIZ" if bozuk == 0 else f"\nSONUC: {bozuk} HATALI SATIR")
    return 0 if bozuk == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
