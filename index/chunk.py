"""pages.jsonl -> arama parçaları (chunks).

Her kayıt tipi farklı davranır çünkü dört hedef soru tipinin gerektirdiği
bütünlük farklı (bkz. plan M3):

    personel  -> her hoca KENDİ parçası; bölüm adı her parçaya context olarak
                 eklenir (yoksa "Yazılım'da kim var" sorusu isim parçasını
                 bulsa bile hangi bölüm olduğunu kaybeder)
    tablo     -> "DÖNEM N" bloğu bölünmez; ders kodu/ad/AKTS aynı parçada kalır
    pdf       -> akademik takvim; "GÜZ/BAHAR YARIYILI" bloğu bölünmez
    duyuru/
    haber     -> tek parça + published_at; nav breadcrumb çöpü ayıklanır
    sayfa     -> başlığa göre değil, kayan pencere (genel amaçlı)

Çıktı formatı (build_index.py'nin girdisi):
    {"chunk_id", "url", "title", "unit", "doc_type", "published_at", "text"}
"""

import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.console import setup_stdout_utf8

# Kayan pencere boyutu. Gerçek tokenizer'a bağımlı olmamak için kelime sayısı
# kullanılıyor (Türkçe'de kelime başına ortalama alt-token sayısı ingilizceden
# fazladır, bu yüzden ~500 token hedefi için kelime bütçesi tedbirli tutuldu).
PENCERE_KELIME = 380
ORTUSME_KELIME = 60

TITLE_ONEKLERI = ("Prof.", "Doç.", "Dr.", "Arş.", "Öğr.")
NAV_COPU = {"anasayfa", ">", "duyuru detay", "haber detay", "detay"}


def _chunk_id(url: str, index: int) -> str:
    return hashlib.sha1(f"{url}#{index}".encode("utf-8")).hexdigest()[:16]


def _kayit_yap(kaynak: dict, index: int, text: str) -> dict | None:
    text = text.strip()
    if len(text) < 10:
        return None
    return {
        "chunk_id": _chunk_id(kaynak["url"], index),
        "url": kaynak["url"],
        "title": kaynak["title"],
        "unit": kaynak["unit"],
        "doc_type": kaynak["doc_type"],
        "published_at": kaynak["published_at"],
        "text": text,
    }


# ---------------------------------------------------------------- personel

def _kisi_satiri_mi(satir: str) -> bool:
    return satir.strip().startswith(TITLE_ONEKLERI)


def split_personel(kaynak: dict) -> list[dict]:
    """Personel kaydını parçalar. Kısa kayıtlar BÖLÜNMEZ.

    ÖNEMLİ: Bu fonksiyon eskiden liste sayfasını kişi başına bölüyordu. Crawler
    yazıldıktan sonra veri şekli değişti — artık her hoca ZATEN ayrı bir kayıt,
    ayrıca kadro listesi de ayrı bir kayıt. İkinci kez bölmek zarar veriyordu:

        Kadro listesi (8 isim, tek sayfa) -> 8 ayrı parçaya bölünüyordu.
        Sonuç: indekste "bölümün tüm hocaları" diye bir parça KALMIYOR.
        "Bölümde hangi hocalar var" sorusunda bağlama en fazla 2 isim
        girebiliyordu (kaynak başına kota 2) ve bot listenin tamamını
        asla göremiyordu.

    Yeni kural: bütçeye sığıyorsa tek parça (kadro listesi böyle korunuyor),
    sığmıyorsa kayan pencere (uzun hoca profilleri böyle bölünüyor).
    """
    if _kelime_sayisi(kaynak["text"]) <= PENCERE_KELIME:
        kayit = _kayit_yap(kaynak, 0, kaynak["text"])
        return [kayit] if kayit else []

    baslik = kaynak["title"]
    return _kayan_pencere(kaynak, onek=f"{baslik}\n")


# ---------------------------------------------------------------- dönem-bloklu (tablo/pdf)

_DONEM_BASLIK = re.compile(
    r"^(DÖNEM\s+\d+|GÜZ\s+YARIYILI|BAHAR\s+YARIYILI|\d+\.\s*YARIYIL)\s*$", re.I
)


def split_by_donem(kaynak: dict) -> list[dict]:
    """DÖNEM/YARIYIL başlığına göre böler; blok içi asla parçalanmaz.

    Ders listesinde her satır "kod | ad | AKTS | koordinatör" — bunu ortadan
    bölmek "kaç kredi" sorusunu cevapsız bırakır. Takvim PDF'inde de aynı
    mantık: GÜZ/BAHAR karışmasın diye her parça kendi dönem başlığını taşır.
    """
    satirlar = kaynak["text"].split("\n")

    bloklar: list[tuple[str | None, list[str]]] = []
    guncel_baslik: str | None = None
    guncel_satirlar: list[str] = []

    for satir in satirlar:
        eslesme = _DONEM_BASLIK.match(satir.strip())
        if eslesme:
            if guncel_satirlar:
                bloklar.append((guncel_baslik, guncel_satirlar))
            guncel_baslik = eslesme.group(1)
            guncel_satirlar = []
        else:
            guncel_satirlar.append(satir)
    if guncel_satirlar:
        bloklar.append((guncel_baslik, guncel_satirlar))

    if len(bloklar) <= 1:
        # Dönem başlığı yok. Küçükse tek parça (küçük tablolar için doğru davranış),
        # büyükse kayan pencereye devret — LEE akademik takvimi gibi başlıksız uzun
        # PDF'ler burada 1000+ kelimelik tek parçaya dönüşüyordu.
        if _kelime_sayisi(kaynak["text"]) > PENCERE_KELIME:
            return _kayan_pencere(kaynak, onek=f"{kaynak['title']}\n")
        kayit = _kayit_yap(kaynak, 0, kaynak["text"])
        return [kayit] if kayit else []

    parcalar = []
    for baslik, satirlar in bloklar:
        onek = f"{kaynak['title']}"
        if baslik:
            onek += f" — {baslik}"
        govde = "\n".join(s for s in satirlar if s.strip())

        # Blok bütçeyi aşıyorsa içeride kayan pencere uygula, ama başlık ön ekini
        # her parçaya taşı — yoksa ikinci yarı "hangi dönem" bilgisini kaybeder.
        if _kelime_sayisi(govde) > PENCERE_KELIME:
            gecici = dict(kaynak, text=govde)
            for alt in _kayan_pencere(gecici, onek=onek + "\n"):
                alt["chunk_id"] = _chunk_id(kaynak["url"], len(parcalar))
                parcalar.append(alt)
            continue

        kayit = _kayit_yap(kaynak, len(parcalar), onek + "\n" + govde)
        if kayit:
            parcalar.append(kayit)
    return parcalar


# ---------------------------------------------------------------- duyuru / haber

def split_duyuru(kaynak: dict) -> list[dict]:
    """Tek parça; nav breadcrumb çöpü ayıklanır, published_at korunur.

    Duyuru sayfası şöyle başlıyor:
        Duyuru Detay / Anasayfa / > / Duyurular / > / Duyuru Detay / 12 / Ağustos / 2026 / <gerçek başlık>
    Bu çöp indekse girerse tüm duyurular birbirine benzer ve arama karışır.
    Gerçek başlık kayıtta zaten var — metinde onu bulup oradan başlıyoruz.
    """
    satirlar = [s for s in kaynak["text"].split("\n") if s.strip()]

    baslik_norm = " ".join(kaynak["title"].split()).casefold()
    baslik_index = next(
        (i for i, s in enumerate(satirlar) if " ".join(s.split()).casefold() == baslik_norm),
        None,
    )
    if baslik_index is not None:
        satirlar = satirlar[baslik_index:]
    else:
        while satirlar and satirlar[0].strip().lower() in NAV_COPU:
            satirlar.pop(0)

    metin = "\n".join(satirlar)

    if kaynak["published_at"]:
        metin = f"[{kaynak['published_at']}] {metin}"

    if _kelime_sayisi(metin) <= PENCERE_KELIME:
        kayit = _kayit_yap(kaynak, 0, metin)
        return [kayit] if kayit else []

    # Nadiren çok uzun duyuru: genel kayan pencereye devret ama tarihi her parçaya taşı.
    gecici = dict(kaynak, text=metin)
    return _kayan_pencere(gecici, onek=f"[{kaynak['published_at']}] " if kaynak["published_at"] else "")


# ---------------------------------------------------------------- genel amaçlı kayan pencere

def _kelime_sayisi(text: str) -> int:
    return len(text.split())


def _kayan_pencere(kaynak: dict, onek: str = "") -> list[dict]:
    satirlar = [s for s in kaynak["text"].split("\n") if s.strip()]
    if not satirlar:
        return []

    parcalar: list[dict] = []
    pencere: list[str] = []
    kelime = 0

    def kaydet():
        if not pencere:
            return
        metin = onek + "\n".join(pencere)
        kayit = _kayit_yap(kaynak, len(parcalar), metin)
        if kayit:
            parcalar.append(kayit)

    # Tek başına bütçeyi aşan satırlar (uzun paragraflar) kelime bazında bölünür,
    # yoksa 1000+ kelimelik tek parça oluşur ve 2B model bağlamda boğulur.
    bolunmus: list[str] = []
    for satir in satirlar:
        if _kelime_sayisi(satir) <= PENCERE_KELIME:
            bolunmus.append(satir)
            continue
        kelimeler = satir.split()
        adim = PENCERE_KELIME - ORTUSME_KELIME
        for bas in range(0, len(kelimeler), adim):
            bolunmus.append(" ".join(kelimeler[bas:bas + PENCERE_KELIME]))

    for satir in bolunmus:
        satir_kelime = _kelime_sayisi(satir)
        if kelime + satir_kelime > PENCERE_KELIME and pencere:
            kaydet()
            # Örtüşme: son ORTUSME_KELIME kelimelik kısmı yeni pencereye taşı.
            kuyruk_kelimeler = " ".join(pencere).split()[-ORTUSME_KELIME:]
            pencere = [" ".join(kuyruk_kelimeler)] if kuyruk_kelimeler else []
            kelime = len(kuyruk_kelimeler)
        pencere.append(satir)
        kelime += satir_kelime
    kaydet()

    return parcalar


# ---------------------------------------------------------------- dispatch

def chunk_record(kaynak: dict) -> list[dict]:
    """Bir pages.jsonl satırını doc_type'ına göre parçalara böler."""
    if kaynak["doc_type"] == "personel":
        return split_personel(kaynak)
    if kaynak["doc_type"] in ("tablo", "pdf"):
        return split_by_donem(kaynak)
    if kaynak["doc_type"] in ("duyuru", "haber"):
        return split_duyuru(kaynak)
    return _kayan_pencere(kaynak)  # "sayfa" ve tanımsız tipler


# Bilgi taşımayan sayfaların metni. Bunlar indekse girerse arama sonucunda
# gerçek içeriğin yerini çalıyor: "Bölüm Dersleri" sayfası sadece
# "Program Seçiniz" yazıyor (asıl liste AJAX ucunda) ama "hangi dersler var"
# sorusunda 1. sıraya çıkıp gerçek ders listesini 4'lük bağlamdan dışarı itiyordu.
ICERIKSIZ_ISARETLER = ("program seçiniz", "seçiniz", "tıklayınız")

# PDF alt bilgisi — her sayfada tekrarlanan telif/iletişim satırları.
#
# NEDEN ELENİYOR: Kalite belgelerinin her sayfasında aynı telif satırı var.
# Bu satırlar parçanın gövdesini oluşturunca, "bölümde hangi hocalar var"
# sorusunda ilk üç sırayı "© Copyright ... Tüm Hakları Saklıdır" parçaları
# dolduruyor ve gerçek personel kaydı dışarı itiliyordu. Bilgi taşımıyorlar.
ALTBILGI_DESENLERI = re.compile(
    r"(?i)(©\s*copyright|tüm hakları saklıdır|bilgi için\s*:|"
    r"kalitekoordinatorlugu@|sayfa\s+\d+\s*/\s*\d+|"
    # Kalite belgelerinin sayfa başlığı: her belgede birebir aynı.
    r"doküman\s*no|i̇lk yayın tarihi|ilk yayın tarihi|revizyon\s*(no|tarihi))"
)
ANLAMLI_MIN_KELIME = 8

# Personel parçaları kısa olmak ZORUNDA — bir hoca kaydı "Doç. Dr. Emine BAŞ"
# yani 4 kelime. Uzunluk filtresi bunları silmemeli.
UZUNLUK_MUAF_TIPLER = {"personel"}


def anlamli_mi(parca: dict) -> bool:
    """Parça gerçek bilgi taşıyor mu? Başlık tekrarı ve menü kalıntısı sayılmaz."""
    satirlar = [s.strip() for s in parca["text"].split("\n") if s.strip()]
    # Alt bilgi satırları bilgi taşımıyor, "içerik var mı" sayımına girmemeli.
    satirlar = [s for s in satirlar if not ALTBILGI_DESENLERI.search(s)]

    # Başlıkla aynı olan satırları çıkar — geriye kalan asıl içeriktir.
    baslik_parcalari = {parca["title"].casefold()}
    if parca["unit"]:
        baslik_parcalari.add(parca["unit"].casefold())
    govde = [s for s in satirlar if s.casefold() not in baslik_parcalari]

    metin = " ".join(govde).strip()
    if not metin:
        return False
    if metin.casefold() in ICERIKSIZ_ISARETLER:
        return False
    if parca["doc_type"] in UZUNLUK_MUAF_TIPLER:
        return True
    return len(metin.split()) >= ANLAMLI_MIN_KELIME


# Görev tanımı belgeleri: bölümdeki her rol için doldurulmuş aynı form
# (Bölüm Başkanı, Staj Komisyonu, Sekreterlik, Proje Komisyonu...).
#
# NEDEN AYRI İŞARETLENİYOR: Bu belgeler bir görevin SORUMLULUKLARINI anlatır,
# o görevde KİMİN olduğunu değil. Ama "araştırma", "ders programı", "görev"
# gibi kelimeleri bolca içerdikleri için kişi ve ders sorularında ilk sıralara
# çıkıp gerçek cevabı bağlamın dışına itiyorlardı:
#   "araştırma görevlileri kimler" -> 1. sıra görev tanımı PDF'i, kadro listesi yok
#   "birinci dönem dersleri neler" -> ilk iki sıra görev tanımı PDF'i
# Silinmiyorlar (birinin "bölüm başkanının görevleri neler" diye sorma hakkı var),
# sadece etiketleniyorlar; sıralama kararını bot/retriever.py veriyor.
GOREV_TANIMI_ISARETLERI = ("görev unvanı", "bağlı alt unvanlar", "vekalet eden",
                           "üst birim adı", "görevin tanımı")


def gorev_tanimi_mi(metin: str) -> bool:
    dusuk = metin.casefold()
    return sum(i in dusuk for i in GOREV_TANIMI_ISARETLERI) >= 2


# --- Harf aralığı bozuk PDF metni ---
#
# Bazı PDF'ler her karakteri ayrı ayrı konumlandırıyor; pypdf bunu harfler
# arasında boşlukla çıkarıyor:
#
#     "G ö r e v  U n v a n ı :"   (kelime arası ÇİFT boşluk)
#
# Üç yeri birden bozuyordu, hiçbiri hata vermeden:
#   1. gorev_tanimi_mi() "görev unvanı" arıyor, bulamıyor -> belge
#      işaretlenmiyor -> sıralama cezası uygulanmıyor. Ölçülen sonuç:
#      "bölüm başkanı kim" sorusunda ilk 4 sonucun tamamı görev tanımı
#      PDF'i, isim geçen personel sayfası ilk 4'e hiç giremiyor.
#   2. BM25 her harfi ayrı token sayıyor; belge kelime aramasında görünmez.
#   3. Embedding harf dizisini anlamsız buluyor.
#
# Onarım satır bazında: kelime arası çift boşluksa tek boşluklar harf
# aralığıdır. Eşik yüksek tutuldu (>=8 token ve %60'ı tek karakter) ki
# "A B C" gibi kısa normal satırlar bozulmasın.
def _harf_araligi_bozuk_mu(satir: str) -> bool:
    parcalar = satir.split()
    if len(parcalar) < 8:
        return False
    return sum(1 for p in parcalar if len(p) == 1) / len(parcalar) >= 0.6


def bosluklari_onar(metin: str) -> str:
    """'G ö r e v  U n v a n ı' -> 'Görev Unvanı'. Sağlam satırlara dokunmaz."""
    onarilmis = []
    for satir in metin.split("\n"):
        if _harf_araligi_bozuk_mu(satir):
            # Once kelime siniri (>=2 bosluk) korunur, sonra harf araliklari silinir.
            satir = re.sub(r" {2,}", "\x00", satir).replace(" ", "").replace("\x00", " ")
        onarilmis.append(satir)
    return "\n".join(onarilmis)


def altbilgiyi_temizle(parca: dict) -> dict:
    """Alt bilgi satırlarını parça metninden siler."""
    satirlar = [s for s in parca["text"].split("\n")
                if not ALTBILGI_DESENLERI.search(s)]
    parca["text"] = "\n".join(satirlar).strip()
    return parca


def chunk_pages(kayitlar: list[dict]) -> list[dict]:
    parcalar: list[dict] = []
    elenen = 0
    for kayit in kayitlar:
        # Harf araligi bozuk PDF metni once onarilir — parcalama, isaretleme
        # ve arama zincirinin tamami bu metni okuyor (bkz. bosluklari_onar).
        kayit = {**kayit, "text": bosluklari_onar(kayit["text"])}

        # İşaretleme KAYIT seviyesinde: form başlıkları ("Görev Unvanı:",
        # "Bağlı Alt Unvanlar:") belgenin sadece ilk parçasında geçiyor.
        # Parça bazında bakınca aynı belgenin ikinci yarısı işaretsiz kalıyor
        # ve cezadan kaçıp sonuçlara sızıyordu.
        gorev = gorev_tanimi_mi(kayit["text"])
        for parca in chunk_record(kayit):
            if anlamli_mi(parca):
                temiz = altbilgiyi_temizle(parca)
                temiz["gorev_tanimi"] = gorev
                parcalar.append(temiz)
            else:
                elenen += 1
    if elenen:
        print(f"  ({elenen} iceriksiz parca elendi)")
    return parcalar


def load_pages(yol: Path) -> list[dict]:
    with yol.open(encoding="utf-8") as f:
        return [json.loads(satir) for satir in f if satir.strip()]


if __name__ == "__main__":
    setup_stdout_utf8()

    girdi = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        Path(__file__).resolve().parent.parent / "data" / "sample" / "pages.sample.jsonl"
    )
    kayitlar = load_pages(girdi)
    parcalar = chunk_pages(kayitlar)

    print(f"GIRDI : {girdi}  ({len(kayitlar)} kayit)")
    print(f"CIKTI : {len(parcalar)} parca\n")

    dagilim: dict[str, int] = {}
    for p in parcalar:
        dagilim[p["doc_type"]] = dagilim.get(p["doc_type"], 0) + 1
    print("Tip dagilimi:", dagilim)

    uzunluklar = [_kelime_sayisi(p["text"]) for p in parcalar]
    print(f"Kelime sayisi: min={min(uzunluklar)} ort={sum(uzunluklar)//len(uzunluklar)} "
          f"maks={max(uzunluklar)}  (butce: {PENCERE_KELIME})")

    print("\n--- ORNEKLER ---")
    for tip in ("personel", "tablo", "pdf", "duyuru"):
        ornek = next((p for p in parcalar if p["doc_type"] == tip), None)
        if ornek:
            print(f"\n[{tip}] {ornek['title'][:50]}")
            print("  " + ornek["text"][:220].replace("\n", " / "))
