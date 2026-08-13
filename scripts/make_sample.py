"""data/raw/pages.jsonl -> data/sample/pages.sample.jsonl

    python scripts/make_sample.py
    python scripts/make_sample.py --max-kayit 40

NEDEN VAR:
    `data/raw/` .gitignore'da; repoyu klonlayan biri crawler'ı çalıştırmadan
    elinde hiç veri bulamaz. Örnek dosya repoya commit'lenen küçük, gerçek bir
    kesit — B tarafı (index/, bot/) bunu okuyarak crawler'ı beklemeden çalışır.
    Gerçek veriye geçmek tek şey değiştirir: --input yolu. Kod değişmez.

M0'DAN FARKI:
    Bu script eskiden siteyi kendi geziyordu (fetch/extract/tablo mantığının
    ikinci bir kopyası). Crawler yazıldıktan sonra o kopya iki kaynaklı gerçek
    üretmeye başladı: örnek dosya crawler'ın çıkardığından farklı alanlar
    içerebiliyordu. Artık site tek yerden geziliyor, bu script sadece seçim
    yapıyor.

SEÇİM:
    Kayıt sayısı sınırın altındaysa hepsi kopyalanır. Üstündeyse doc_type
    dağılımı korunarak örneklenir ve her tipten en az iki kayıt alınır —
    yoksa 41 PDF'in yanında tek duyuru kaybolur ve B "duyuru" senaryosunu
    hiç test edemez. Tip içinde metin uzunluğuna göre eşit aralıklı seçim
    yapılır, böylece hem 300 karakterlik iletişim sayfası hem 21.000
    karakterlik staj yönergesi örneğe girer.
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.console import setup_stdout_utf8

KOK = Path(__file__).resolve().parent.parent
GIRDI = KOK / "data" / "raw" / "pages.jsonl"
CIKTI = KOK / "data" / "sample" / "pages.sample.jsonl"

# Tipin örnekte hiç görünmemesi, o senaryonun test edilememesi demek.
TIP_BASINA_EN_AZ = 2


def oku(yol: Path) -> list[dict]:
    kayitlar = []
    with yol.open(encoding="utf-8") as f:
        for satir in f:
            satir = satir.strip()
            if satir:
                kayitlar.append(json.loads(satir))
    return kayitlar


def esit_aralikli(kayitlar: list[dict], adet: int) -> list[dict]:
    """Uzunluğa göre sıralayıp eşit aralıklı seçer: uçlar da örneğe girer."""
    if adet >= len(kayitlar):
        return kayitlar
    sirali = sorted(kayitlar, key=lambda k: len(k["text"]))
    adim = (len(sirali) - 1) / (adet - 1) if adet > 1 else 1
    return [sirali[round(i * adim)] for i in range(adet)]


def sec(kayitlar: list[dict], max_kayit: int) -> list[dict]:
    if len(kayitlar) <= max_kayit:
        return kayitlar

    tipe_gore: dict[str, list[dict]] = defaultdict(list)
    for k in kayitlar:
        tipe_gore[k["doc_type"]].append(k)

    # Önce her tipe taban pay, kalan kotayı dağılıma göre böl.
    paylar = {t: min(TIP_BASINA_EN_AZ, len(ks)) for t, ks in tipe_gore.items()}
    taban = sum(paylar.values())
    if taban > max_kayit:
        # Tip başına taban pay sınırdan büyük. Tipi kırpmak yerine sınırı
        # aşıyoruz: eksik tip, birkaç fazla kayıttan daha pahalı.
        print(f"  ! --max-kayit {max_kayit} < {len(tipe_gore)} tip x {TIP_BASINA_EN_AZ} "
              f"= {taban}; {taban} kayit yaziliyor")
    kalan = max_kayit - taban
    if kalan > 0:
        toplam = sum(len(ks) - paylar[t] for t, ks in tipe_gore.items()) or 1
        for tip, ks in tipe_gore.items():
            ek = round(kalan * (len(ks) - paylar[tip]) / toplam)
            paylar[tip] = min(len(ks), paylar[tip] + ek)

    secilen = []
    for tip, ks in tipe_gore.items():
        secilen += esit_aralikli(ks, paylar[tip])
    # Girdi sırasını koru: örnek dosyanın diff'i okunabilir kalsın.
    sirasi = {id(k): i for i, k in enumerate(kayitlar)}
    return sorted(secilen, key=lambda k: sirasi[id(k)])


def main(argv: list[str] | None = None) -> int:
    setup_stdout_utf8()
    ap = argparse.ArgumentParser(description="crawler ciktisindan ornek veri seti")
    ap.add_argument("--input", default=str(GIRDI))
    ap.add_argument("--out", default=str(CIKTI))
    ap.add_argument("--max-kayit", type=int, default=120)
    a = ap.parse_args(argv)

    girdi = Path(a.input)
    if not girdi.exists():
        print(f"HATA: {girdi} yok. Once crawler'i calistir:")
        print("  python -m crawler.run --seed <bolum> --sadece-birim")
        return 1

    kayitlar = oku(girdi)
    if not kayitlar:
        print(f"HATA: {girdi} bos")
        return 1

    secilen = sec(kayitlar, a.max_kayit)

    cikti = Path(a.out)
    cikti.parent.mkdir(parents=True, exist_ok=True)
    with cikti.open("w", encoding="utf-8") as f:
        for k in secilen:
            f.write(json.dumps(k, ensure_ascii=False) + "\n")

    print(f"GIRDI  : {girdi}  ({len(kayitlar)} kayit)")
    print(f"YAZILDI: {cikti}  ({len(secilen)} kayit)")
    print("Tip dagilimi:", dict(Counter(k["doc_type"] for k in secilen)))
    birimler = {k.get("unit") for k in secilen}
    print(f"Birim  : {len(birimler)} ({', '.join(str(b) for b in sorted(birimler, key=str))})")
    print(f"\nDogrulamak icin:\n  python scripts/validate_jsonl.py {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
