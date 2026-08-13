# KTÜN Destek Chatbotu

Konya Teknik Üniversitesi için, **sadece** üniversiteyle ilgili sorulara cevap veren destek
chatbotu. Bilgi kaynağı üniversitenin kendi sitesi (ktun.edu.tr); bilgi modele
ezberletilmez, soru anında ilgili sayfalar bulunup modele okutulur (**RAG**).

Hedef soru tipleri: **kişi/iletişim** · **tarih/takvim** · **ders/program** · **duyuru/haber**

## Kapsam

**Bilgisayar ve Bilişim Bilimleri Fakültesi**'nin üç bölümü — Bilgisayar Mühendisliği,
Yazılım Mühendisliği, Yapay Zeka ve Makine Öğrenmesi Mühendisliği — artı üniversite geneli
duyuru, haber ve akademik takvim. 31 bölümün tamamı binlerce sayfa demek ve arama havuzu
büyüdükçe "hangi bölümün sınav takvimi" ayrımı zorlaşıyor; üç bölüm bu ayrımı hâlâ anlamlı
tutacak kadar çeşitli, `unit` alanı da onu ayırt etmeye yetiyor.

Çekilen **486 kayıt**: 257 PDF (öğretim planları, ders/sınav programları, staj ve kalite
belgeleri) · 73 duyuru · 69 personel · 48 sayfa · 24 tablo (AKTS ders listeleri) · 15 haber.

| Birim | Kayıt |
|---|---|
| Yazılım Mühendisliği | 198 |
| Bilgisayar Mühendisliği | 178 |
| Yapay Zeka ve Makine Öğrenmesi Mühendisliği | 67 |
| (üniversite geneli) | 43 |

Hocaların akademik geçmişi ve verdiği dersler kişi sayfalarının AJAX sekmelerinden geliyor;
bir hoca = bir kayıt (sekmeler ayrı kayıt olsaydı hepsi aynı URL'e düşerdi). Yayın listeleri
(makale, kitap, bildiri) bilerek toplanmıyor — hedef soru tipleri kişi/ders odaklı.

> Bölümlerin "Öğretim Planı", "Ders Programı", "Sınav Programları" sayfalarının **metni
> neredeyse boştur** — sadece PDF linkleri taşırlar. Asıl içerik `/Dosyalar/**.pdf`
> altında, yani `/tr/Birim/` dışında. Bu yüzden `--sadece-birim` PDF'leri elemez
> (`crawler/run.py:ekle`); elerse ders ve sınav verisinin tamamı kaybolur.
>
> Simetrik olarak `--birimsiz`, duyuru/haber taranırken birim sayfalarına girmeyi
> engeller: duyuru listeleri her birime link veriyor ve filtresiz gezinti kapsam dışı
> bölümleri (Mimarlık, Teknik Bilimler MYO…) içeri sızdırıyor.

---

## Nasıl çalışıyor?

Sistem iki bağımsız hattan oluşuyor. Soldaki hat **verinin hazırlanması** (elle
tetiklenir), sağdaki hat **sorunun cevaplanması** (her soruda çalışır).

```mermaid
flowchart TD
    subgraph VERI["VERİ HATTI — elle tetiklenir"]
        SITE[ktun.edu.tr]
        CRAWL["crawler/run.py<br/>BFS + PDF + AJAX"]
        RAW[("data/raw/pages.jsonl<br/>486 kayıt")]
        CHUNK["index/chunk.py<br/>tipe göre parçalama"]
        IDX[("data/index/<br/>348 parça · embedding · BM25")]
        SITE --> CRAWL --> RAW --> CHUNK --> IDX
    end

    subgraph SORU["SORU HATTI — her soruda"]
        Q([Kullanıcı sorusu])
        YON{"OBS / LMS /<br/>kütüphane konusu mu?"}
        REW["bot/rewrite.py<br/>takip sorusunu tamamla"]
        ARA["bot/retriever.py<br/>BM25 + embedding, RRF"]
        KAPI{"kapsam içi mi?<br/>BM25 ≥ 3.0 VE kos ≥ 0.82<br/>(486 kayıtta sızdırıyor)"}
        EXT{"cevap bir ALAN mı?<br/>telefon / e-posta / ders kodu"}
        LLM["bot/llm.py<br/>gemma2:2b"]
        CEVAP([Cevap + kaynak linki])
        RED([“Sadece KTÜN hakkında<br/>yardımcı olabilirim”])
        LINK([Doğru adrese yönlendirme])

        Q --> YON
        YON -- evet --> LINK
        YON -- hayır --> REW --> ARA --> KAPI
        KAPI -- hayır --> RED
        KAPI -- evet --> EXT
        EXT -- evet --> CEVAP
        EXT -- hayır --> LLM --> CEVAP
    end

    IDX -.okur.-> ARA
```

Üç tasarım kararı bu şemayı belirliyor:

**Model bilgiyi ezberlemez.** Veri güncellemek = crawler'ı tekrar çalıştırmak, saatlerce
eğitim değil. 2B'lik model yeterli çünkü ondan bilgi değil, **okuduğunu anlatması** isteniyor.

**Kapsam kapısı modelden ÖNCE.** Alakasız soruda model hiç çalışmaz — uydurma şansı bulamaz.

**Yapısal cevaplar modeli atlar.** Telefon, e-posta, ders kredisi gibi bilgiler metinde bir
alan olarak duruyor; bunları modele yazdırmanın faydası yok. O sorular model kalitesinden
bağımsız ve anlık.

---

## Kurulum

```bash
pip install -r requirements.txt
```

Model çalıştırmak için ayrıca [Ollama](https://ollama.com) gerekir:

```bash
ollama pull gemma2:2b
```

---

## Çalıştırma

Veri çekmek (A tarafı — hedef fakültenin üç bölümü + üniversite geneli):

```bash
python -m crawler.run --seed "https://www.ktun.edu.tr/tr/Birim/Hakkimizda/?brm=14Nor138UPTTvDv6Apnukw==" --unit "Yapay Zeka ve Makine Öğrenmesi Mühendisliği" --sadece-birim
```

```bash
python -m crawler.run --seed "https://www.ktun.edu.tr/tr/Universite/TumDuyurular?page=1" --seed "https://www.ktun.edu.tr/tr/Universite/TumHaberler?page=1" --seed "https://www.ktun.edu.tr/tr/Universite/AkademikTakvim" --birimsiz --derinlik 1
```

Diğer iki bölüm için `--seed`/`--unit` değiştirilir; `--sifirdan` verilmezse mevcut
kayıtlarla birleşir. Sonra şema doğrulama ve örnek veri:

```bash
python scripts/validate_jsonl.py data/raw/pages.jsonl
```

```bash
python scripts/make_sample.py
```

Indeks ve bot (B tarafı):

```bash
python -m index.build_index
```

```bash
python -m bot.cli
```

Tarayıcıda kullanmak istersen (aynı bot, `http://127.0.0.1:8000`):

```bash
python -m bot.web
```

Crawler çalıştırmadan denemek için indeks örnek veriden de kurulabilir
(`--input` verilmezse `data/sample/pages.sample.jsonl` kullanılır).

### Diğer komutlar

```bash
python -m bot.cli --no-llm "bölümde hangi hocalar var"
```

```bash
python -m eval.retrieval_test
```

```bash
python -m eval.answer_test
```

```bash
python scripts/validate_jsonl.py data/raw/pages.jsonl
```

```bash
python scripts/make_sample.py
```

CLI içinde: `/kaynak` (son cevabın kaynakları), `/temizle` (hafızayı sıfırla), `/cik`.

Veri güncellemek = crawler'ı tekrar çalıştırmak; `--sifirdan` verilmezse mevcut
kayıtlarla birleştirir.

---

## Kapsam kapısı nasıl ayarlandı

Alakasız soruda modelin hiç çalışmaması gerekiyor. Bunun için bir eşik lazım, ve
eşik **tahminle değil ölçümle** kondu.

> Aşağıdaki rakamlar kapsam **tek bölümken** (67 kayıt) alınmıştır ve eşiklerin
> neden bu değerlerde olduğunu anlatır. Kapsam fakülteye genişleyince bu ayırım
> bozuldu — güncel durum için [Kapsam kapısı yeniden kalibre
> edilmeli](#-kapsam-kapısı-yeniden-kalibre-edilmeli).

Ölçüm (18 kapsam içi / 6 kapsam dışı soru):

| | BM25 | kosinüs |
|---|---|---|
| kapsam içi | 3.20 – 20.89 | 0.832 – 0.876 |
| kapsam dışı | 0.00 – 3.83 | 0.797 – 0.843 |

**İki aralık da çakışıyor** — hiçbir sinyal tek başına ayıramıyor. Ama çakışmalar
farklı sorulardan geliyor:

- *"aşk şiiri **yaz**"* → BM25 yüksek (staj metinlerindeki "yaz" ile eşleşiyor),
  kosinüs düşük
- *"bugün günlerden ne"* → kosinüs yüksek, BM25 sıfır

İkisini **birden** şart koşunca ayırım tam oluyor. Ayrıca çok yüksek kosinüs
(≥ 0.85) tek başına yeterli sayılıyor: *"Staj yapmak için ne gerekiyor"* BM25'te
2.35 alıp reddediliyordu, kosinüsü 0.868 — kapsam dışı hiçbir sorunun ulaşamadığı
seviye.

---

## Ölçüm sonuçları

Güncel veriyle (**486 kayıt → 348 parça**) ölçüldü. Karşılaştırma sütunu, kapsam
tek bölümken (67 kayıt → 104 parça) alınan ölçüm — ikisi de aynı soru kümesiyle
(`eval/retrieval_test.py`, 18 kapsam içi / 6 kapsam dışı).

**Arama** (model çalıştırılmadan):

| Ölçüt | 67 kayıt (tek bölüm) | 486 kayıt (güncel) | Hedef |
|---|---|---|---|
| Doğru kaynak ilk 4'te | 17/18 (%94) | **16/18 (%89)** | %80 |
| kişi / tarih / ders / duyuru | %100 / %100 / %83 / %100 | %100 / %100 / %83 / %75 | %70 |
| Kapsam dışı sızıntı | 0/6 | **2/6** | 0 |
| Kapsam içi yanlış ret | 0/18 | **0/18** | 0 |

Arama isabeti hedefin üstünde. Kapsam 4.7 katına çıkarken ilk ölçüm 14/18'e
düşmüştü; aşağıdaki üç düzeltmeyle 16/18'e çıktı ve kişi soruları %100 oldu.
Açık kalan tek gerileme kapsam kapısı.

### Ölçekle ortaya çıkan üç sessiz hata

Hiçbiri 67 kayıtta görünmüyordu, hiçbiri hata mesajı vermiyor:

| # | Belirti | Kök sebep | Çözüm |
|---|---|---|---|
| 10 | Kişi sorularında ilk 4 sonuç görev tanımı formu, isim yok | Bazı PDF'ler her karakteri ayrı konumlandırıyor; pypdf `"G ö r e v  U n v a n ı :"` çıkarıyor. İmza bulunamayınca belge işaretlenmiyor, ceza uygulanmıyor — ayrıca BM25 her harfi ayrı token sayıyor | `index/chunk.py:bosluklari_onar` |
| 11 | Ceza yiyen belge yine 1. sırada | Ceza RRF'e çarpılıyor, **sonra** başlık bonusu ekleniyordu; bonus (0.010) cezayı telafi ediyordu — RRF'in tek katkısı ≈0.016 | Ceza bonustan sonraya alındı |
| 12 | "araştırma görevlileri kimler" haber sayfalarını getiriyor | Veride 17 Arş. Gör. kaydı var; site "Arş. Gör." yazıyor, kullanıcı "araştırma görevlisi" diyor | Eş anlamlı listesine eklendi |

#10 üçünün en öğreticisi: **tek bir metin çıkarma kusuru üç katmanı birden
bozuyor** — belge sınıflandırma, kelime araması ve anlamsal arama. Hiçbiri
çökmüyor, sadece yanlış belge üste çıkıyor.

### 🔴 Kapsam kapısı yeniden kalibre edilmeli

Kapı iki sinyale birden bakıyor (`bot/retriever.py`): `BM25_ESIGI = 3.0` **ve**
`KOSINUS_ESIGI = 0.82`, ayrıca tek başına yeterli sayılan `KOSINUS_TEK_BASINA = 0.85`.
Bu eşikler 67 kayıtlık veriyle ölçülmüştü ve o ölçekte ayırım tamdı (0/6 sızıntı).

486 kayıtta iki dağılım da **çakışıyor**:

| | BM25 | kosinüs |
|---|---|---|
| kapsam içi (18 soru) | 2.63 – 24.17 | **0.839** – 0.880 |
| kapsam dışı (6 soru) | 0.00 – 8.15 | 0.808 – **0.848** |

Sızan iki soru: *"hava durumu nasıl"* (bm25 7.35, kos 0.838) ve *"makarna tarifi
ver"* (bm25 8.15, kos 0.828) — ikisi de BM25 eşiğini rahatça aşıyor.

**Eşik oynatmak bu sorunu çözmüyor.** Kosinüs eşiğini kapsam içi tabanına (0.839)
çekmek sızıntıyı kapatır ama iki küme arasında kalan pay **0.001** — 24 soruluk
kümeye ezberletmek demek, 25. soruda tutmaz. Sebep BM25'in nadir terimlere yüksek
IDF vermesi: korpus büyüdükçe alakasız sorgu da bir belgeye çarpıyor ("hava durumu"
→ öğrenci proje listesi, "makarna" → yemek duyurusu). Kapının **üçüncü ve farklı
cinsten** bir sinyale ihtiyacı var; aday yönler: sorgunun birim/alan terimleriyle
örtüşmesi, sorgu sınıflandırma, ya da top-1 ile korpus ortalaması arasındaki fark.

Denenen ve **işe yaramayan** bir yol (A tarafı): duyuru/haber liste sayfalarını
indeksten çıkarmak. Sızıntıyı değiştirmedi ve arama isabetini düşürdü — bazı
testler zaten liste sayfasına eşleşerek geçiyordu.

**Cevap** (`eval/answer_test.py`):

| Ölçüt | 67 kayıt (tek bölüm) | 486 kayıt (güncel) |
|---|---|---|
| Cevap doğruluğu | 8/8 (%100) | **7/8 (%88)** |
| Kapsam dışı reddi | 2/2 | **1/2** |
| Yönlendirme | 1/1 | 1/1 |
| Sohbet hafızası | çalışıyor | çalışıyor |
| Süre | ort. 57.5 sn/soru | ort. 49.3 sn/soru (CPU, gemma2:2b) |

**Soru kümesi yeni kapsama göre yeniden yazıldı.** Küme tek bölüm varken
yazılmıştı; kapsam üç bölüme çıkınca sorular tek doğru cevabı olmayan sorulara
dönüştü ve ölçüm, sistem doğru çalışırken HATA saymaya başladı: *"bölüm başkanı
kim"* sorusuna Bilgisayar Mühendisliği'nin başkanı geliyor, test YZM'ninkini
bekliyordu. Sorular artık birim adı taşıyor — birimsiz soruda ölçülen şey
doğruluk değil şanstı. Bu düzeltmeden önce ölçüm 5/8 gösteriyordu.

Kalan tek cevap hatası "araştırma görevlileri kimler": arama artık doğru personel
sayfalarını getiriyor (16/18 ölçümünde bu soru geçiyor) ama 2B model listeden
Arş. Gör. unvanlılarını ayıklamak yerine ilk gördüğü isimleri sayıyor.

**Kapsam dışı sızıntı** ("makarna tarifi ver" modele gitti) yukarıdaki kapsam
kapısı bulgusunun cevap tarafındaki karşılığı — açık kusur.

**Model seçimi:** `gemma2:2b` varsayılan. `qwen2.5:1.5b-instruct` beş kat hızlı
ama bağlamdaki cevabı göremiyor — telefon numarası bağlamın 1. parçasında apaçık
dururken "bilgi yok" diyordu. Doğruluk hızın önünde tutuldu.

### Colab T4'te model karşılaştırması

> ⚠️ Bu bölüm **67 kayıtlık (tek bölüm) veriyle** ölçüldü; 486 kayıtla
> tekrarlanmadı. Notebook güncel örnek veriyle yeniden üretildi, yani ölçüm
> tekrar çalıştırılabilir durumda — ama aşağıdaki rakamlar eski kapsamındır.

Lokalde NVIDIA GPU yok, 2B üstü model denenemiyordu. Tavanı görmek için aynı 8
soru Colab'ın T4'ünde 4-bit nicelemeyle ölçüldü
([`notebooks/model_karsilastirma.ipynb`](notebooks/model_karsilastirma.ipynb)).
Arama zinciri ve promptlar birebir aynı; değişen tek şey `bot/llm.py` yerine
`generate()` sözleşmesini sağlayan bir Colab backend'i.

| Model | Doğruluk | Kapsam dışı reddi | sn/soru |
|---|---|---|---|
| Qwen2.5-1.5B-Instruct | 6/8 (%75) | 2/2 | 10.1 |
| **Qwen2.5-7B-Instruct** | **8/8 (%100)** | 2/2 | 12.7 |

**Ne çıkarıyoruz:** asıl fark doğrulukta değil, maliyette. 7B, 1.5B'nin dört
katı parametreyle soru başına yalnızca 2.6 saniye daha alıyor — GPU'da darboğaz
üretim değil, model yükleme ve bellek. Doğruluk tarafında 7B'nin 8/8'i tek
başına bir üstünlük değil: lokal `gemma2:2b` de aynı veriyle aynı 8 soruda 8/8
yapıyordu. Yani o ölçekte 8 soruluk küme **2B ile doymuştu**.

Bu, 486 kayıtla birlikte değişmiş olabilir: aynı sorularda 2B artık 5/8 yapıyor
ve hatalarının bir kısmı "bağlamda üç bölümün belgesi var, hangisi sorulmuş"
ayrımını yapamamaktan geliyor — tam da büyük modelin fark yaratmasını
bekleyeceğin yer. Karşılaştırmayı güncel veriyle tekrarlamak artık boş bir iş
değil; eski kapsamında olduğu gibi "ölçüm zaten doymuş" denemez.

**Bu tablonun söylemedikleri:**
- `google/gemma-2-*` ölçülemedi (HF'de kapalı repo, lisans onayı + token
  istiyor). Yani lokal varsayılanın GPU'daki karşılığı tabloda **yok**;
  7B ile gemma2:2b arasındaki fark doğrudan değil, lokal ölçümle dolaylı
  kıyaslanıyor.
- Qwen2.5-1.5B burada 6/8 yaptı; lokalde (Ollama, `q4_K_M`) bundan belirgin
  kötüydü. Aynı model ailesi, farklı niceleme ve farklı sohbet şablonu —
  hangisinin etkili olduğu ölçülmedi, dolayısıyla "1.5B aslında iyiymiş"
  demek için erken.
- 8 soruluk kümede tek soru %12.5 ediyor; bu tablo sıralama verir, ince fark
  vermez.

**Karar:** lokal varsayılan `gemma2:2b` olarak kalıyor — 7B bu makinede zaten
çalışmıyor, karşılaştırma bir seçim değil tavan ölçümü. Somut kazanç doğrulukta
değil sürede: aynı 8 soru CPU'da ortalama 57.5 saniye alırken T4'te ~13 saniye,
yani dört kat daha büyük modelle dört kattan fazla hız. Kod tarafında hiçbir
değişiklik gerekmiyor; değişen tek şey `bot/llm.py`'nin arkasındaki backend.

### Bilinen kusurlar
- **Kapsam kapısı 486 kayıtta sızdırıyor** — yukarıdaki kırmızı başlık. Ölçekle
  gelen ve hâlâ açık olan tek ciddi gerileme.
- **Birimsiz soru belirsiz** — "bölüm başkanı kim" üç bölümden birini seçiyor.
  Sistem bunu kullanıcıya sormuyor, sessizce birini alıyor.
- 2B model unvana göre süzemiyor: "araştırma görevlileri kimler" sorusunda doğru
  kadro sayfası bağlamda, ama model Arş. Gör. olanları ayıklamıyor.
- "Güz yarıyılı ne zaman başlıyor" sorusunda model bazen Bahar tarihini veriyor.
  Akademik takvim PDF'inde GÜZ ve BAHAR blokları ayrı parçalarda ve etiketli, ama
  embedding "güz" sorgusunda BAHAR parçasını üste çıkarabiliyor.
- "Birinci dönem dersleri neler" sorusunda görev tanımı PDF'i 1. sırada; doğru
  belge (öğretim planı) 3. sırada, cevap bağlama giriyor ama sıralama ideal değil.
- Bu bölümün iletişim sayfasında **telefon ve e-posta yok**, sadece adres var.
  `bot/extract.py`'nin telefon/e-posta çıkarımı bu veride devreye girmiyor —
  kod sorunu değil, sitede o bilgi yok (telefon rehberi uçları da boş dönüyor).
- CPU'da soru başına yarım dakikayı bulabiliyor. GPU'lu bir ortamda saniyeler.

---

## Ölçümle bulunan tuzaklar

Hiçbiri hata mesajı vermiyor — sistem çalışıyor görünüp yanlış cevap veriyor.

| # | Belirti | Kök sebep | Çözüm |
|---|---|---|---|
| 1 | Türkçe arama tutmuyor | `"İ".lower()` fazladan U+0307 üretiyor | `common/normalize.py` |
| 2 | Sayfa bulunamıyor | `brm` Base64'ünde `+` boşluğa dönüyor | URL yeniden encode edilmiyor |
| 3 | Model bağlamdaki cevabı görmüyor | Kaçış cümlesi promptta birebir yazılıydı, model kopyalıyordu | Etiket (`BILGI_YOK`) |
| 4 | Talimat takibi bozuk | `/api/generate` sohbet şablonunu uygulamıyor | `/api/chat` |
| 5 | Model ders adı uyduruyor | 20 personel parçası bağlamı dolduruyor | Kaynak başına kota |
| 6 | Kadro listesi hiç görünmüyor | RRF zayıflığı: BM25'te 1., kosinüste 34. | Her yöntemin birincisine slot |
| 7 | Müfredat/çizelge karışıyor | Ayırt edici bilgi başlıkta, gövdede değil | Başlık eşleşme bonusu |
| 8 | Kişi soruları form belgelerine düşüyor | Görev tanımı PDF'leri aynı kelimeleri içeriyor | Belge sınıfı + ceza |
| 9 | "peki" ile başlayan soru reddediliyor | Bağlaç BM25 ağırlığını sulandırıyor | Takip bağlaçları ayıklanıyor |

Bu tablo projenin en öğretici çıktısı. Ortak noktaları: **hiçbiri çökmüyor, hiçbiri
log basmıyor.** Sistem sağlıklı görünürken yanlış cevap veriyor. Hepsi ancak ölçüm
yazıldıktan sonra görülebildi — bu yüzden `eval/` klasörü modelden önce yazıldı.

İki tanesi ayrıca genel ders niteliğinde:

**#6 — RRF'in kör noktası.** Reciprocal Rank Fusion iki sıralamayı toplar. Bir yöntemde
1., diğerinde 34. olan parça tek katkı alır (1/61) ve *iki yöntemde de vasat* olan
parçalara (iki katkı) yenilir. Kadro listesi tam olarak bu durumdaydı: BM25'in
tartışmasız birincisi, sonuçlarda yok. Çözüm her yöntemin birincisine slot ayırmak.

**#3 — Küçük modelde kaçış cümlesi.** Prompt'a "cevap yoksa şunu yaz: ..." diye
hazır bir cümle koymak, 1.5B modele en kolay token yolunu vermek demek. Model o
cümleyi kopyalamayı öğreniyor ve bağlamdaki cevabı görmezden geliyordu (doğruluk 1/8).
Cümle yerine modelin doğal üretmeyeceği bir etiket (`BILGI_YOK`) konunca kısayol kapandı.

---

## Kim neyi yazıyor?

Proje 2 kişilik ve **kimse kimseyi beklemez**. İki taraf birbirinin koduna değil,
sadece [`SCHEMA.md`](SCHEMA.md)'deki `pages.jsonl` formatına bağlıdır.

| Kişi | Sahibi olduğu klasörler | Girdi | Çıktı |
|---|---|---|---|
| **A — Veri** | `crawler/`, `scripts/` | ktun.edu.tr | `data/raw/pages.jsonl` |
| **B — Bot** | `index/`, `bot/`, `notebooks/`, `eval/` | `pages.jsonl` | CLI cevabı |
| Ortak | `common/`, `SCHEMA.md`, `requirements.txt` | — | küçük, nadir değişir |

Bağımsızlığı sağlayan iki şey:
- **`data/sample/pages.sample.jsonl`** (200 gerçek sayfa, repoda) → `data/raw/` gitignore'da,
  yani repoyu klonlayan biri crawler'ı çalıştırmadan elinde veri bulamaz. Örnek dosya
  crawler çıktısından üretilir (`scripts/make_sample.py`); gerçek veriye geçmek tek şey
  değiştirir: `--input` yolu, kod değişmez. Sınır 200, çünkü 120'de eval testlerinin
  beklediği üç sayfa (telefon, "Yemek Listesi", öğretim görevlisi ilanı) örnekten düşüyordu.
- **`--backend dummy`** → B, model kurulumunu beklemeden arama zincirini test eder.

Branch düzeni: `feat/crawler` (A) ve `feat/bot` (B), günlük PR.
`data/` klasörü `.gitignore`'da — sadece `data/sample/` commit'lenir.

---

## Siteden öğrenilenler (crawler yazarken bunlara dikkat)

Site canlı olarak incelendi. Sunucu tarafında render ediliyor → `requests` yeterli,
Selenium **gerekmiyor**. `robots.txt` ve `sitemap.xml` **yok** → ana sayfadan BFS crawl şart.

| Konu | Bulgu |
|---|---|
| İçerik kabı | `<main id="mainContent">` |
| Yan menü | `mainContent` **içinde** — alt sayfaları keşfetmek için gerekli, ama metne girerse tüm sayfalar birbirine benzer. `.gdlr-core-pbf-sidebar-left` silinir |
| Bölümler | Ana menüde **yok**. Ana menü → Fakülte → "Bölümler" (2 kademe). 31 bölüm bulundu |
| `brm` id | **Sayfa başına**, birim başına değil → URL'ler tahmin edilemez, menüden keşfedilir |
| Akademik takvim | Sayfa metninde yok, **`<iframe>` içindeki PDF**'te (metin tabanlı, OCR gerekmez) |
| Ders listesi | Sayfa boş görünür; asıl liste `GET /tr/Birim/BolumDersListesiGetir?id=<id>` ucunda. id `onclick="derslistegetir(5018)"` içinde |
| Hoca sayfası | Sekmeler AJAX: `POST /tr/Universite/<sekme>` + `id=<token>`, token `onclick="Sayfa_Getir(...)"` içinde. Sayfanın kendi metni sadece ad + fakülte + bölüm (261 chr). Hoca adı `<h6>`'da — h1/h2 herkeste "Akademik Personel" |
| Telefon rehberi | `TelefonRehberiAramaDetay` / `TelefonRehberiBirimDetay` uçları **boş tablo dönüyor**; rehberde veri yok. Telefon/e-posta bu yüzden toplanamıyor |
| Duyuru başlığı | Sayfada **iki `<h1>`** var; ilki jenerik ("Duyuru Detay"), ikincisi gerçek başlık |

Bu tabloyla ilgili iki kritik kural yukarıdaki [tuzaklar tablosunda](#ölçümle-bulunan-tuzaklar)
detaylı: URL'ler yeniden encode edilmez (#2) ve `.lower()` Türkçe'de kullanılmaz (#1).

---

## Kapsam dışı

**Diğer 30 bölüm ve genel üniversite sayfaları** — bot tek bölüme cevap veriyor (yukarı bak) ·
login arkasındaki kişisel veri (not, transkript, ders kaydı) — OBS'ye yönlendirilir ·
İngilizce sayfalar · alt alan adları (`obs`, `lms`, `kutuphane`…) — yalnızca yönlendirme ·
`.docx`/`.xlsx` ekler (staj formları, 2024-2025 güz sınav takvimleri) — metne çevrilmiyor,
`scope.DISLANAN_UZANTILAR` içinde.
