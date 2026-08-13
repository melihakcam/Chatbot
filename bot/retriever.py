"""Hibrit arama: BM25 (kelime) + embedding (anlam), RRF ile birleştirme.

NEDEN İKİSİ BİRDEN:
    "YAZ102 kaç kredi"        -> BM25 kazanır (ders kodu nadir token, embedding kör)
    "finaller ne zaman"       -> embedding kazanır (takvimde "final" kelimesi
                                 geçmeyebilir, "yarıyıl sonu sınavı" yazar)

RRF (Reciprocal Rank Fusion):
    İki listenin SKORLARI farklı ölçekte (BM25 0-30 arası, kosinüs 0-1).
    Skorları toplamak yanlış olur; RRF sadece SIRALAMAYA bakar:
        skor = Σ 1 / (K + sıra)
    Kalibrasyon gerektirmez, iki yöntem de eşit söz hakkına sahip olur.

KAPSAM KAPISI:
    En iyi kosinüs benzerliği eşiğin altındaysa LLM hiç çağrılmaz.
    "hava nasıl" gibi sorular indekste karşılığı olmadığı için burada durur;
    model uydurma şansı bulamaz.
"""

import json
import pickle
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.paths import INDEX_DIR, setup_model_cache

MODEL_CACHE = setup_model_cache()

import numpy as np  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

from common.normalize import tokenize_tr  # noqa: E402

RRF_K = 60          # RRF sabiti; literatürdeki standart değer
ADAY_SAYISI = 30    # her yöntemden kaç aday alınacak (birleştirmeden önce)

# Aynı kaynak sayfadan en fazla kaç parça sonuca girebilir.
#
# NEDEN VAR: Bir bölümün personel sayfası ~20 parçaya bölünüyor ve her parçanın
# metninde "Yazılım Mühendisliği — Akademik Personel" yazıyor. Bölüm adı geçen
# HER soruda bu 20 parça birden ~0.88 kosinüs alıp ilk 4'ü dolduruyordu:
# "birinci dönem dersleri" sorusunda ders listesi hiç görünmüyor, model de
# bağlamda ders olmadığı için ders adı UYDURUYORDU.
# Kota, farklı kaynaklara yer açarak bunu kesiyor.
KAYNAK_BASINA_MAKS = 2

# --- KAPSAM EŞİKLERİ (ölçümle belirlendi) ---
#
# İlk denemede kapsam kapısı sadece kosinüse bakıyordu ve ÇALIŞMADI:
# e5 modeli her metni birbirine biraz benzer görüyor, skorlar 0.79-0.92 gibi
# dar bir banda sıkışıyor. Ölçüm sonucu (14 soru, 8 kapsam içi / 6 dışı):
#
#   soru tipi     kosinüs        BM25
#   kapsam içi    0.817 - 0.923   4.59 - 18.18
#   kapsam dışı   0.805 - 0.842   0.00 -  3.36
#
# Kosinüs aralıkları ÇAKIŞIYOR (0.817 içi < 0.842 dışı) -> tek başına kullanılamaz.
# BM25 ise ayırıyor: kapsam dışı sorularda kelime örtüşmesi yok, skor sıfıra yakın.
# Bu yüzden kapı BM25 üzerine kuruldu; kosinüs sadece kelime örtüşmesi olmayan
# ama anlamca çok yakın sorular için ikinci bir yol olarak duruyor.
BM25_ESIGI = 4.0
KOSINUS_YEDEK_ESIGI = 0.87


@dataclass
class Sonuc:
    chunk_id: str
    url: str
    title: str
    unit: str | None
    doc_type: str
    published_at: str | None
    text: str
    kosinus: float
    rrf: float

    def kaynak(self) -> str:
        return f"{self.title} — {self.url}"


class Retriever:
    def __init__(self, index_dizin: Path = INDEX_DIR):
        if not (index_dizin / "meta.json").exists():
            raise FileNotFoundError(
                f"Indeks bulunamadi: {index_dizin}\n"
                "Once calistir: python -m index.build_index"
            )

        self.meta = json.loads((index_dizin / "meta.json").read_text(encoding="utf-8"))

        with (index_dizin / "chunks.jsonl").open(encoding="utf-8") as f:
            self.chunks = [json.loads(s) for s in f if s.strip()]

        self.embeddings = np.load(index_dizin / "embeddings.npy")

        with (index_dizin / "bm25.pkl").open("rb") as f:
            self.bm25 = pickle.load(f)

        self.model = SentenceTransformer(self.meta["model"], cache_folder=str(MODEL_CACHE))

    def _dense(self, soru: str) -> np.ndarray:
        # "query: " oneki e5'in egitim formati — build_index'te "passage: " kullanildi.
        vektor = self.model.encode(
            f"query: {soru}", convert_to_numpy=True, normalize_embeddings=True
        ).astype(np.float32)
        return self.embeddings @ vektor  # normalize edildigi icin nokta carpimi = kosinus

    def search(self, soru: str, k: int = 4) -> list[Sonuc]:
        kosinusler = self._dense(soru)
        dense_sira = np.argsort(-kosinusler)[:ADAY_SAYISI]

        # BM25 sorgusu indeksle AYNI normalize_tr'den gecmek zorunda,
        # yoksa Turkce buyuk/kucuk harf tuzagi eslesmeyi bozar.
        bm25_skorlar = self.bm25.get_scores(tokenize_tr(soru))
        bm25_sira = np.argsort(-bm25_skorlar)[:ADAY_SAYISI]

        # Kapsam kapisi bu iki sayiya bakar (bkz. kapsam_disi_mi).
        self._son_bm25_max = float(bm25_skorlar.max()) if len(bm25_skorlar) else 0.0
        self._son_kosinus_max = float(kosinusler.max()) if len(kosinusler) else 0.0

        rrf: dict[int, float] = {}
        for sira, idx in enumerate(dense_sira):
            rrf[int(idx)] = rrf.get(int(idx), 0.0) + 1.0 / (RRF_K + sira + 1)
        for sira, idx in enumerate(bm25_sira):
            rrf[int(idx)] = rrf.get(int(idx), 0.0) + 1.0 / (RRF_K + sira + 1)

        # Kaynak cesitliligi: ayni sayfadan gelen parcalar sonuclari doldurmasin.
        siralanmis = sorted(rrf.items(), key=lambda x: -x[1])
        en_iyiler: list[tuple[int, float]] = []
        kaynak_sayaci: dict[str, int] = {}
        for idx, rrf_skor in siralanmis:
            kaynak = self.chunks[idx]["url"]
            if kaynak_sayaci.get(kaynak, 0) >= KAYNAK_BASINA_MAKS:
                continue
            kaynak_sayaci[kaynak] = kaynak_sayaci.get(kaynak, 0) + 1
            en_iyiler.append((idx, rrf_skor))
            if len(en_iyiler) == k:
                break

        sonuclar = []
        for idx, rrf_skor in en_iyiler:
            parca = self.chunks[idx]
            sonuclar.append(Sonuc(
                chunk_id=parca["chunk_id"], url=parca["url"], title=parca["title"],
                unit=parca["unit"], doc_type=parca["doc_type"],
                published_at=parca["published_at"], text=parca["text"],
                kosinus=float(kosinusler[idx]), rrf=rrf_skor,
            ))
        return sonuclar

    def kapsam_disi_mi(self, sonuclar: list[Sonuc]) -> bool:
        """Soru KTÜN kapsamı dışında mı? True ise LLM hiç çağrılmaz.

        search() çağrıldıktan sonra kullanılmalı — son sorgunun skorlarına bakar.
        """
        if not sonuclar:
            return True
        if getattr(self, "_son_bm25_max", 0.0) >= BM25_ESIGI:
            return False
        return getattr(self, "_son_kosinus_max", 0.0) < KOSINUS_YEDEK_ESIGI


if __name__ == "__main__":
    from common.console import setup_stdout_utf8

    setup_stdout_utf8()
    retriever = Retriever()
    print(f"Indeks: {retriever.meta['parca_sayisi']} parca, model {retriever.meta['model']}\n")

    sorular = sys.argv[1:] or [
        "Yazılım Mühendisliğinde hangi hocalar var",
        "Emine Baş hangi bölümde",
        "yazılım mühendisliği bölüm telefonu",
        "YAZ102 dersi kaç kredi",
        "güz yarıyılı final sınavları ne zaman",
        "yatay geçiş başvuru tarihleri",
        "son duyuru ne",
        "hava durumu nasıl",
        "makarna tarifi ver",
    ]

    for soru in sorular:
        sonuclar = retriever.search(soru, k=4)
        kapsam = "KAPSAM DISI" if retriever.kapsam_disi_mi(sonuclar) else "kapsam ici"
        print(f"\n{'=' * 72}\nSORU: {soru}   [{kapsam}]")
        for i, s in enumerate(sonuclar, 1):
            print(f"  {i}. kos={s.kosinus:.3f} [{s.doc_type:8}] {s.title[:48]}")
            print(f"     {s.text[:110].replace(chr(10), ' / ')}")
