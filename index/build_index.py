"""Parçalardan arama indeksi üretir: anlamsal (embedding) + kelime (BM25).

İki arama birlikte kullanılıyor çünkü tek başına ikisi de yetersiz:
    BM25       -> "YAZ102", "Emine BAŞ" gibi tam eşleşmelerde güçlü,
                  "finaller ne zaman" gibi kelime örtüşmeyen sorularda kör
    embedding  -> anlamı yakalar ama ders kodu/özel isim gibi nadir
                  token'larda zayıf

ÇALIŞTIRMA:
    python -m index.build_index                              # örnek veri
    python -m index.build_index --input data/raw/pages.jsonl # gerçek veri

Çıktı (data/index/):
    chunks.jsonl     parçalar (metin + kaynak bilgisi)
    embeddings.npy   float32, L2-normalize edilmiş  (satır sayısı = parça sayısı)
    bm25.pkl         BM25 indeksi
    meta.json        model adı, boyut, üretim zamanı
"""

import argparse
import json
import pickle
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.console import setup_stdout_utf8
from common.paths import INDEX_DIR, SAMPLE_PAGES, setup_model_cache

# Model cache'i D:'ye yönlendir — sentence_transformers import'undan ÖNCE olmalı.
MODEL_CACHE = setup_model_cache()

import numpy as np  # noqa: E402
from rank_bm25 import BM25Okapi  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

from common.normalize import tokenize_tr  # noqa: E402
from index.chunk import chunk_pages, load_pages  # noqa: E402

MODEL_ADI = "intfloat/multilingual-e5-small"


def embed_metni(parca: dict) -> str:
    """Embedding'e giden metin.

    Başlık ve birim adı metne ekleniyor: "Doç. Dr. Emine BAŞ" tek başına
    hangi bölümde olduğunu söylemiyor, "Yazılım Mühendisliği" bağlamı
    olmadan "Yazılım'da hangi hocalar var" sorusuyla eşleşmez.

    "passage: " öneki e5 modelinin eğitim formatı — sorguda "query: " kullanılır.
    Önek atlanırsa isabet gözle görülür şekilde düşer.
    """
    baslik = parca["title"]
    if parca["unit"] and parca["unit"] not in baslik:
        baslik = f"{parca['unit']} — {baslik}"
    return f"passage: {baslik}\n{parca['text']}"


def build(girdi: Path, cikti_dizin: Path, model_adi: str = MODEL_ADI) -> dict:
    setup_stdout_utf8()
    print(f"GIRDI       : {girdi}")
    print(f"MODEL CACHE : {MODEL_CACHE}")

    kayitlar = load_pages(girdi)
    parcalar = chunk_pages(kayitlar)
    print(f"{len(kayitlar)} kayit -> {len(parcalar)} parca")

    if not parcalar:
        print("HATA: parca uretilemedi")
        return {}

    print(f"\nModel yukleniyor: {model_adi}")
    baslangic = time.time()
    model = SentenceTransformer(model_adi, cache_folder=str(MODEL_CACHE))
    print(f"  yuklendi ({time.time() - baslangic:.1f} sn)")

    print("Embedding hesaplaniyor...")
    baslangic = time.time()
    vektorler = model.encode(
        [embed_metni(p) for p in parcalar],
        batch_size=32,
        convert_to_numpy=True,
        normalize_embeddings=True,   # kosinus = nokta carpimi olsun
        show_progress_bar=True,
    ).astype(np.float32)
    print(f"  bitti ({time.time() - baslangic:.1f} sn)  sekil={vektorler.shape}")

    # BM25 tarafi normalize_tr'den gecer. Sorgu tarafi da AYNI fonksiyonu
    # kullanmak zorunda, yoksa Turkce buyuk/kucuk harf tuzagi arama tutmaz.
    print("BM25 indeksi kuruluyor...")
    bm25 = BM25Okapi([tokenize_tr(f"{p['title']} {p['text']}") for p in parcalar])

    cikti_dizin.mkdir(parents=True, exist_ok=True)

    with (cikti_dizin / "chunks.jsonl").open("w", encoding="utf-8") as f:
        for p in parcalar:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    np.save(cikti_dizin / "embeddings.npy", vektorler)

    with (cikti_dizin / "bm25.pkl").open("wb") as f:
        pickle.dump(bm25, f)

    meta = {
        "model": model_adi,
        "boyut": int(vektorler.shape[1]),
        "parca_sayisi": len(parcalar),
        "kaynak": str(girdi),
        "uretim_zamani": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    (cikti_dizin / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nYAZILDI: {cikti_dizin}")
    for dosya in sorted(cikti_dizin.iterdir()):
        print(f"  {dosya.name:18} {dosya.stat().st_size / 1024:>8.1f} KB")
    return meta


def main() -> int:
    ayristirici = argparse.ArgumentParser(description="KTUN chatbot arama indeksi kurar")
    ayristirici.add_argument("--input", type=Path, default=SAMPLE_PAGES,
                             help="pages.jsonl yolu (varsayilan: ornek veri)")
    ayristirici.add_argument("--output", type=Path, default=INDEX_DIR)
    ayristirici.add_argument("--model", default=MODEL_ADI)
    args = ayristirici.parse_args()

    if not args.input.exists():
        print(f"HATA: girdi dosyasi yok: {args.input}")
        return 1

    return 0 if build(args.input, args.output, args.model) else 1


if __name__ == "__main__":
    raise SystemExit(main())
