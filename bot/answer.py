"""Uçtan uca cevaplama: soru -> cevap + kaynaklar.

AKIŞ (sırası önemli):
    1. Yönlendirme kontrolü  -> OBS/LMS gibi konularda arama bile yapılmaz
    2. Sorgu yeniden yazma   -> takip sorusuysa geçmişle tamamlanır
    3. Arama                 -> BM25 + embedding
    4. Kapsam kapısı         -> alakasızsa LLM HİÇ çağrılmaz
    5. Yapısal çıkarım       -> telefon/e-posta/ders kredisi ise LLM'e GEREK YOK
    6. LLM                   -> sadece serbest sorularda, bulunan bağlamla
    7. Kaynak ekleme         -> cevabın altına kullanılan sayfa linkleri

5. adım modele olan bağımlılığı azaltır: ölçümde arama %100 isabetliydi ama
model doğru bağlamı kullanamıyordu. Cevabın metinde bir ALAN olarak durduğu
sorularda modele yaratıcılık payı bırakmanın faydası yok.

Cevaplanamayan sorular data/logs/unanswered.jsonl'e yazılır — hangi konularda
veri eksik olduğunu gösterir (crawler'a geri besleme).
"""

import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.normalize import tokenize_tr
from common.paths import LOGS_DIR
from bot.extract import _kimlik_sorusu_mu, dogrudan_cevap
from bot.llm import LLMHatasi, backend_olustur
from bot.prompt import (
    BILGI_YOK_CEVABI, BILGI_YOK_ETIKETI, KAPSAM_DISI_CEVABI, KAYITTA_YOK_CEVABI,
    SISTEM_PROMPTU, prompt_kur,
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
    dogrudan: bool = False          # LLM calistirilmadan cevaplandi
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


# Kimlik sorularında aranan aday sayısı (normalde 4). Bkz. Chatbot.sor.
KIMLIK_ADAY_SAYISI = 10

# Türkçe soru kelimeleri ve cümle başı büyük harf yanıltmasın: iki ya da daha
# fazla ard arda büyük harfle başlayan kelime = büyük olasılıkla bir ad soyad.
# "beyza kızıldağ kimdir" gibi küçük harfle yazılmış sorular için de ikinci yol
# var: bilinen soru kalıbı ("... kimdir", "... kim").
_ADAY_AD = re.compile(r"\b[A-ZÇĞİÖŞÜ][a-zçğıöşü]+\s+[A-ZÇĞİÖŞÜ][a-zçğıöşü]+")
_KIM_KALIBI = re.compile(r"\b(kimdir|kim)\b", re.IGNORECASE)
_SORU_KELIMELERI = {"kim", "kimdir", "kimler", "nedir", "ne", "nasil", "nasıl",
                    "nerede", "hangi", "kac", "kaç", "zaman", "bolum", "bölüm"}


def _kadro_adlari(parcalar: list[dict]) -> list[frozenset[str]]:
    """İndeksteki personel kayıtlarından ad kelime kümeleri çıkarır.

    Kaynak iki yer: kadro listesi satırları ("Doç. Dr. Hakan YILMAZ") ve
    kişilerin kendi sayfa başlıkları ("<birim> — Arş. Gör. Beyza KIZILDAĞ").
    """
    from bot.extract import UNVANLAR

    unvan_kelimeleri = {k for u in UNVANLAR for k in tokenize_tr(u)}
    adlar: set[frozenset[str]] = set()

    def ekle(satir: str) -> None:
        for unvan in UNVANLAR:
            if unvan not in satir:
                continue
            kalan = satir.split(unvan, 1)[1]
            kelimeler = {k for k in tokenize_tr(kalan) if k not in unvan_kelimeleri}
            if len(kelimeler) >= 2:
                adlar.add(frozenset(kelimeler))
            return

    for p in parcalar:
        if p.get("doc_type") != "personel":
            continue
        ekle(p.get("title", ""))
        for satir in re.split(r"[|\n]", p.get("text", "")):
            satir = satir.strip()
            if satir and len(satir) < 60:
                ekle(satir)
    return sorted(adlar, key=len, reverse=True)


def kadroda_ad_var_mi(soru: str, kadro: list[frozenset[str]]) -> bool:
    """Soru, kadrodaki bir kişinin adının TAMAMINI içeriyor mu?"""
    kelimeler = set(tokenize_tr(soru))
    return any(ad <= kelimeler for ad in kadro)


def ozel_ad_var_mi(soru: str) -> bool:
    """Soru bir kişi adı içeriyor gibi mi görünüyor?"""
    if _ADAY_AD.search(soru):
        return True
    if not _KIM_KALIBI.search(soru):
        return False
    # "kim/kimdir" var: soru kelimeleri dışında en az iki kelime kalıyorsa
    # (ad + soyad) kişi sorusu sayılıyor. "bölüm başkanı kim" elenir.
    kalan = [k for k in re.findall(r"\w+", soru.casefold())
             if k not in _SORU_KELIMELERI]
    return len(kalan) >= 2


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
        # Kadroda geçen adların kelime kümeleri. Kişi sorusu tespiti TAHMİNE
        # değil bu listeye dayanıyor: büyük harf/soru kalıbı sezgileri hem
        # küçük harfli soruları kaçırıyordu ("ahmet babalık hangi bölümde")
        # hem de takip sorularını yanlışlıkla kişi sanıyordu ("peki bölüm
        # başkanı kim"). İndekste kim varsa liste odur.
        self.kadro_adlari = _kadro_adlari(self.retriever.chunks)

    def sor(self, soru: str, k: int = 4) -> Cevap:
        # 1. Yönlendirme: cevap sitede değil, başka bir sistemde.
        #
        # Kişi adı geçen sorular yönlendirmeye HİÇ sokulmuyor. Sebep ölçüldü:
        # yönlendirme anahtarları kelime başından eşleşiyor (Türkçe ek alması
        # gerektiği için) ve "Kürşad Buğrahan Yapar kimdir" sorusu "kurs"
        # anahtarına takılıp KTÜNSEM'e yönlendiriliyordu — üstelik yönlendirme
        # aramadan önce çalıştığı için kişi hiç aranmıyordu.
        kisi_adi_var = kadroda_ad_var_mi(soru, self.kadro_adlari)
        yonlendirme = None if kisi_adi_var else yonlendirme_bul(soru)
        if yonlendirme:
            cevap = Cevap(metin=yonlendirme, yonlendirme=True, kullanilan_soru=soru)
            self.gecmis.append((soru, cevap.metin))
            return cevap

        # 2. Takip sorusuysa geçmişle tamamla (LLM'siz, deterministik).
        #
        # Ad soyad geçen soru takip sorusu DEĞİLDİR; kendi kendine yeter.
        # Ölçülen vaka: "aybüke babadağ kimdir" (Bilgisayar Müh.) sorulduktan
        # sonra "kürşad buğrahan yapar kimdir" sorulunca yeniden yazma başına
        # "Bilgisayar Mühendisliği" ekliyordu; arama bozuluyor ve model başka
        # bir kişinin adını veriyordu (Kürşad Buğrahan YAPAR aslında Yazılım
        # Mühendisliği'nde).
        arama_sorusu = (soru if kisi_adi_var
                        else yeniden_yaz(soru, self.gecmis, self.birimler))

        # 3. Arama
        # Kimlik sorularında daha geniş aday listesi isteniyor: cevap kadro
        # satırından OKUNUYOR, modele gitmiyor. Yani fazladan aday bağlamı
        # şişirmiyor, sadece doğru satırın listeye girme şansını artırıyor.
        # Ölçüm: k=4'te 65 kişiden 2-3'ünün kadro satırı ilk 4'e giremiyordu.
        sonuclar = self.retriever.search(
            arama_sorusu,
            k=KIMLIK_ADAY_SAYISI if (kisi_adi_var or _kimlik_sorusu_mu(arama_sorusu)) else k)

        # 4. Yapısal çıkarım kapsam kapısından ÖNCE denenir.
        #
        # Kadro satırında birebir eşleşen bir ad bulunduysa soru tanım gereği
        # kapsam içindedir — skorların ne dediğinin önemi yok. Ölçülen vaka:
        # "İsmail Koç kimdir" BM25 7.08 / kosinüs 0.811 alıyor (ikisi de eşiğin
        # altında, çünkü "ismail" ve "koç" korpusta yaygın kelimeler) ve kapı
        # reddediyordu — oysa Doç. Dr. İsmail KOÇ kadroda duruyor.
        dogrudan = dogrudan_cevap(arama_sorusu, sonuclar, kimlik=kisi_adi_var)
        if dogrudan:
            metin, kaynak = dogrudan
            cevap = Cevap(metin=metin, kaynaklar=[kaynak], dogrudan=True,
                          kullanilan_soru=arama_sorusu)
            self.gecmis.append((soru, cevap.metin))
            return cevap

        # 5. Kapsam kapısı — LLM buradan sonra çağrılır.
        if self.retriever.kapsam_disi_mi(sonuclar):
            # Soru bir KİŞİ hakkındaysa mesaj değişiyor: "sadece KTÜN hakkında
            # yardımcı olabilirim" demek yanlış bilgi veriyor, çünkü soru
            # okulla ilgili — bulunamayan şey kişinin kaydı.
            kisi_sorusu = ozel_ad_var_mi(soru)
            self._logla(soru, arama_sorusu,
                        "kayitta_yok" if kisi_sorusu else "kapsam_disi")
            cevap = Cevap(metin=KAYITTA_YOK_CEVABI if kisi_sorusu else KAPSAM_DISI_CEVABI,
                          kapsam_disi=True, kullanilan_soru=arama_sorusu)
            self.gecmis.append((soru, cevap.metin))
            return cevap

        # 6. LLM — kurallar system mesajinda, baglam+soru user mesajinda.
        #
        # Kimlik sorusunda aday listesi genişletilmişti (KIMLIK_ADAY_SAYISI);
        # yapısal çıkarım tutmadıysa o uzun liste modele GİTMEMELİ. Bağlamı
        # şişirmek modelin ders adı uydurmasına yol açıyordu (tuzak #5).
        sonuclar = sonuclar[:k]
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
