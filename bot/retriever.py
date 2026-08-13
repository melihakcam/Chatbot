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

# Başlık eşleşmesi bonusu.
#
# NEDEN VAR: Bölümde birbirine çok benzeyen ama FARKLI belgeler var:
#   "Ders Listesi (AKTS) — DÖNEM 1"     müfredat: hangi ders, kaç kredi
#   "2025-2026 Güz Dönemi Ders Programı" haftalık çizelge: hangi gün, saat
#   "2025-2026 Güz yarıyılı final takvimi" sınav tarihleri
# Hepsinde ders kodları ve dönem adları geçiyor, gövde metinleri birbirine
# benziyor. "Birinci dönemde hangi dersler var" sorusunda model haftalık
# çizelgeden cevap veriyordu — doğru belge müfredattı.
#
# Ayırt edici bilgi GÖVDEDE değil BAŞLIKTA duruyor. Sorgu kelimeleri başlıkta
# geçiyorsa o parçaya bonus veriliyor (alan ağırlıklı arama).
BASLIK_BONUSU = 0.015

# Görev tanımı belgeleri için sıralama cezası.
# Silmek yerine geri çekiyoruz: "bölüm başkanının görevleri neler" gibi bir
# soru gelirse bu belgeler DOĞRU cevap. Ceza sadece soru görev/sorumluluk
# sormadığında uygulanıyor.
GOREV_TANIMI_CEZASI = 0.55
GOREV_KELIMELERI = {"gorev", "gorevi", "gorevleri", "sorumluluk", "sorumluluklari",
                    "yetki", "yetkileri", "tanimi", "komisyon", "komisyonu"}

# Sorgu eş anlamlı genişletmesi (sadece BM25 tarafı).
#
# NEDEN VAR: Kullanıcı "hoca" der, sitede "Akademik Personel" yazar. Bu kelime
# hiçbir kayıtta geçmediği için "bölümde hangi hocalar var" sorusunda personel
# kayıtları BM25'te sıfır alıyor ve sonuçlara hiç giremiyordu; yerlerine her
# PDF'in altındaki "Bölüm Başkanı" imza satırları çıkıyordu.
#
# Embedding tarafına dokunulmuyor: anlamsal arama bu ilişkiyi zaten kısmen
# yakalıyor, sorun kelime eşleşmesinde.
ES_ANLAMLILAR = {
    "hoca": ["akademik", "personel"],
    "hocalar": ["akademik", "personel"],
    "hocalari": ["akademik", "personel"],
    "akademisyen": ["akademik", "personel"],
    "akademisyenler": ["akademik", "personel"],
    "ogretim": ["akademik", "personel"],
    "kadro": ["akademik", "personel"],
    "telefonu": ["telefon", "iletisim"],
    "maili": ["posta", "iletisim"],
    "mail": ["posta", "iletisim"],
}

# --- KAPSAM EŞİKLERİ (ölçümle belirlendi, eval/retrieval_test.py) ---
#
# Kapı İKİ koşulu birden arar. Sebep: hiçbir sinyal TEK BAŞINA ayırmıyor.
# Tek bölüm verisinde (109 parça, 18 kapsam içi / 6 dışı soru) ölçüm:
#
#            BM25              kosinüs
#   içi      3.20 - 20.89      0.832 - 0.876
#   dışı     0.00 -  3.83      0.797 - 0.843
#
# İki aralık da ÇAKIŞIYOR: BM25'te 3.20 (içi) < 3.83 (dışı),
# kosinüste 0.832 (içi) < 0.843 (dışı). Yani "BM25 yeterliyse kabul et"
# de "kosinüs yeterliyse kabul et" de yanlış sonuç veriyor.
#
# Ama çakışmalar FARKLI sorulardan geliyor:
#   "aşk şiiri yaz"      BM25 3.83 (yüksek — "yaz" stajla eşleşiyor) ama kosinüs 0.812
#   "bugün günlerden ne" kosinüs 0.843 (yüksek) ama BM25 0.00
# İkisini birden isteyince ayırım tam oluyor.
#
# NOT: Bu eşikler korpusa bağlı. Veri seti değişirse (yeni bölüm eklenirse,
# tüm üniversiteye çıkılırsa) yeniden ölçülmeli — eval/retrieval_test.py
# "yanlış ret" ve "sızıntı" satırlarını gösteriyor.
BM25_ESIGI = 3.0
KOSINUS_ESIGI = 0.82

# İkinci yol: kelime örtüşmesi zayıf ama anlamca çok yakın sorular için.
# "Staj yapmak için ne gerekiyor" BM25'te 2.35 alıyor (eşiğin altı) ama
# kosinüsü 0.868 — kapsam dışı hiçbir sorunun ulaşamadığı bir seviye
# (kapsam dışı kosinüs tavanı 0.843). Bu yol olmadan geçerli soru reddediliyordu.
KOSINUS_TEK_BASINA_ESIGI = 0.85


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
        soru_tokenleri = tokenize_tr(soru)
        genisletilmis = list(soru_tokenleri)
        for token in soru_tokenleri:
            genisletilmis.extend(ES_ANLAMLILAR.get(token, ()))
        bm25_skorlar = self.bm25.get_scores(genisletilmis)
        bm25_sira = np.argsort(-bm25_skorlar)[:ADAY_SAYISI]

        # Kapsam kapisi bu iki sayiya bakar (bkz. kapsam_disi_mi).
        self._son_bm25_max = float(bm25_skorlar.max()) if len(bm25_skorlar) else 0.0
        self._son_kosinus_max = float(kosinusler.max()) if len(kosinusler) else 0.0

        rrf: dict[int, float] = {}
        for sira, idx in enumerate(dense_sira):
            rrf[int(idx)] = rrf.get(int(idx), 0.0) + 1.0 / (RRF_K + sira + 1)
        for sira, idx in enumerate(bm25_sira):
            rrf[int(idx)] = rrf.get(int(idx), 0.0) + 1.0 / (RRF_K + sira + 1)

        # Görev tanımı belgeleri: soru görev/sorumluluk sormuyorsa geri çekilir.
        # Bu belgeler bir rolün sorumluluklarını anlatıyor, o rolde kimin
        # olduğunu değil (bkz. index/chunk.py, gorev_tanimi_mi).
        gorev_sorusu = bool(GOREV_KELIMELERI & set(tokenize_tr(soru)))
        if not gorev_sorusu:
            for idx in list(rrf):
                if self.chunks[idx].get("gorev_tanimi"):
                    rrf[idx] *= GOREV_TANIMI_CEZASI

        # Baslik bonusu: ayirt edici bilgi govdede degil baslikta duruyor
        # (mufredat / haftalik cizelge / sinav takvimi ayrimi gibi).
        soru_kelimeleri = set(tokenize_tr(soru))
        if soru_kelimeleri:
            for idx in list(rrf):
                baslik_kelimeleri = set(tokenize_tr(self.chunks[idx]["title"]))
                ortak = soru_kelimeleri & baslik_kelimeleri
                if ortak:
                    rrf[idx] += BASLIK_BONUSU * len(ortak) / len(soru_kelimeleri)

        # Her yöntemin BİRİNCİSİNE slot garantisi.
        #
        # NEDEN: RRF iki sıralamayı toplar. Bir yöntemde 1. ama diğerinde 34.
        # olan parça tek katkı alır (1/61) ve iki yöntemde de vasat olan
        # parçalara (iki katkı) yenilir. Ölçülen somut vaka: "bölümde hangi
        # hocalar var" sorusunda kadro listesi BM25'te 1., kosinüste 34. —
        # sonuçlara hiç giremiyordu, yerine görev tanımı PDF'leri çıkıyordu.
        garantili = [int(bm25_sira[0]), int(dense_sira[0])] if len(self.chunks) else []

        siralanmis = sorted(rrf.items(), key=lambda x: -x[1])
        sira_indeksleri = [i for i in garantili if i in rrf]
        sira_indeksleri += [i for i, _ in siralanmis if i not in sira_indeksleri]

        en_iyiler: list[tuple[int, float]] = []
        kaynak_sayaci: dict[str, int] = {}
        for idx in sira_indeksleri:
            rrf_skor = rrf[idx]
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
        bm25 = getattr(self, "_son_bm25_max", 0.0)
        kosinus = getattr(self, "_son_kosinus_max", 0.0)
        yeterli = ((bm25 >= BM25_ESIGI and kosinus >= KOSINUS_ESIGI)
                   or kosinus >= KOSINUS_TEK_BASINA_ESIGI)
        return not yeterli


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
