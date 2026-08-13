"""Uçtan uca cevaplama: soru -> cevap + kaynaklar.

AKIŞ (sırası önemli):
    1. Yönlendirme kontrolü  -> OBS/LMS gibi konularda arama bile yapılmaz
    2. Sorgu yeniden yazma   -> takip sorusuysa geçmişle tamamlanır
    3. Arama                 -> BM25 + embedding
    4. Kapsam kapısı         -> alakasızsa LLM HİÇ çağrılmaz
    5. LLM                   -> sadece bulunan bağlamla cevap yazar
    6. Kaynak ekleme         -> cevabın altına kullanılan sayfa linkleri

Cevaplanamayan sorular data/logs/unanswered.jsonl'e yazılır — hangi konularda
veri eksik olduğunu gösterir (crawler'a geri besleme).
"""

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.paths import LOGS_DIR
from bot.llm import LLMHatasi, backend_olustur
from bot.prompt import (
    BILGI_YOK_CEVABI, BILGI_YOK_ETIKETI, KAPSAM_DISI_CEVABI, SISTEM_PROMPTU, prompt_kur,
)
from bot.redirects import yonlendirme_bul
from bot.retriever import Retriever, Sonuc
from bot.rewrite import yeniden_yaz

# Modelin "bulamadım" dediğini anlamak için. Birincil sinyal BILGI_YOK etiketi;
# diğerleri model etiketi kullanmayıp kendi cümlesini kurduğunda yakalar.
# Bu durumda kaynak gösterilmez — sayfa bulundu ama cevabı içermiyordu, link
# vermek kullanıcıyı yanıltır.
BILMIYORUM_ISARETLERI = (
    BILGI_YOK_ETIKETI.casefold(), "elimde bilgi yok", "bilgi bulunmuyor", "bilmiyorum",
)


@dataclass
class Cevap:
    metin: str
    kaynaklar: list[Sonuc] = field(default_factory=list)
    kapsam_disi: bool = False
    yonlendirme: bool = False
    kullanilan_soru: str = ""

    def tam_metin(self) -> str:
        if not self.kaynaklar:
            return self.metin
        linkler = []
        gorulen = set()
        for s in self.kaynaklar:
            if s.url in gorulen:
                continue
            gorulen.add(s.url)
            linkler.append(f"  - {s.title}: {s.url}")
        return self.metin + "\n\nKaynak:\n" + "\n".join(linkler)


class Chatbot:
    def __init__(self, backend_adi: str = "ollama", model: str | None = None):
        self.retriever = Retriever()
        self.backend = (backend_olustur(backend_adi, model) if model
                        else backend_olustur(backend_adi))
        self.gecmis: list[tuple[str, str]] = []
        # Takip sorularinda konu tasimak icin indekste gecen birim adlari.
        self.birimler = sorted(
            {p["unit"] for p in self.retriever.chunks if p.get("unit")}
        )

    def sor(self, soru: str, k: int = 4) -> Cevap:
        # 1. Yönlendirme: cevap sitede değil, başka bir sistemde.
        yonlendirme = yonlendirme_bul(soru)
        if yonlendirme:
            cevap = Cevap(metin=yonlendirme, yonlendirme=True, kullanilan_soru=soru)
            self.gecmis.append((soru, cevap.metin))
            return cevap

        # 2. Takip sorusuysa geçmişle tamamla (LLM'siz, deterministik).
        arama_sorusu = yeniden_yaz(soru, self.gecmis, self.birimler)

        # 3. Arama
        sonuclar = self.retriever.search(arama_sorusu, k=k)

        # 4. Kapsam kapısı — LLM buradan sonra çağrılır.
        if self.retriever.kapsam_disi_mi(sonuclar):
            self._logla(soru, arama_sorusu, "kapsam_disi")
            cevap = Cevap(metin=KAPSAM_DISI_CEVABI, kapsam_disi=True,
                          kullanilan_soru=arama_sorusu)
            self.gecmis.append((soru, cevap.metin))
            return cevap

        # 5. LLM — kurallar system mesajinda, baglam+soru user mesajinda.
        try:
            metin = self.backend.generate(
                prompt_kur(arama_sorusu, sonuclar), sistem=SISTEM_PROMPTU
            )
        except LLMHatasi as e:
            return Cevap(metin=f"Model calistirilamadi: {e}", kullanilan_soru=arama_sorusu)

        # 6. Model "bilmiyorum" dediyse kaynak gösterme — yanıltıcı olur.
        bilmiyor = any(i in metin.casefold() for i in BILMIYORUM_ISARETLERI)
        if bilmiyor:
            self._logla(soru, arama_sorusu, "cevap_yok")
            metin = BILGI_YOK_CEVABI

        cevap = Cevap(
            metin=metin,
            kaynaklar=[] if bilmiyor else sonuclar,
            kullanilan_soru=arama_sorusu,
        )
        self.gecmis.append((soru, cevap.metin))
        return cevap

    def _logla(self, soru: str, arama_sorusu: str, sebep: str) -> None:
        """Cevapsız kalan soruyu kaydet — veri eksigini gosterir."""
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        kayit = {
            "zaman": datetime.now().isoformat(timespec="seconds"),
            "soru": soru,
            "arama_sorusu": arama_sorusu,
            "sebep": sebep,
            "bm25_max": round(getattr(self.retriever, "_son_bm25_max", 0.0), 2),
            "kosinus_max": round(getattr(self.retriever, "_son_kosinus_max", 0.0), 3),
        }
        with (LOGS_DIR / "unanswered.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(kayit, ensure_ascii=False) + "\n")

    def gecmisi_temizle(self) -> None:
        self.gecmis.clear()
