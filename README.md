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

```
ktun.edu.tr ──crawl──> data/raw/pages.jsonl ──parçala+embed──> data/index/
                                                                    │
Soru ──> (gerekirse) soruyu tamamla ──> Arama (BM25 + anlamsal) ──> en iyi 4 parça
                                                                    │
                                              ┌─────────────────────┴──────────────┐
                                        skor düşük                            skor yeterli
                                              │                                    │
                              "Sadece KTÜN hakkında..."              LLM (≤2B) ──> cevap + kaynak linki
```

Model bilgiyi **ezberlemez**. Bu yüzden veri güncellemek = crawler'ı tekrar çalıştırmak,
ve 2B'lik küçük bir model yeterli olur (modelden bilgi değil, okuduğunu anlatması isteniyor).

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

Örnek oturum:

```
Sen > Yazılım Mühendisliğinde hangi hocalar var
Bot > Yazılım Mühendisliği Bölümü'nde Doç. Dr. Emine BAŞ, Doç. Dr. İsmail KOÇ
      ve Dr. Öğr. Üyesi Burak YILMAZ gibi hocalar görev yapmaktadır.
      Kaynak: ...

Sen > peki bölümün telefonu ne
Bot > Yazılım Mühendisliği Bölümünün telefon numarası 0 (332) 205 14 29'dur.
```

### Diğer komutlar

```bash
python -m bot.cli --no-llm "yazılım mühendisliği hocaları"
```

```bash
python -m eval.retrieval_test
```

```bash
python -m eval.answer_test
```

```bash
python scripts/validate_jsonl.py data/sample/pages.sample.jsonl
```

CLI içinde: `/kaynak` (son cevabın kaynakları), `/temizle` (hafızayı sıfırla), `/cik`.

---

## Ölçüm sonuçları

**Arama** (`eval/retrieval_test.py`, LLM olmadan, 20 soru + 8 kapsam dışı):

| Ölçüt | 41 kayıt (M4) | 486 kayıt (güncel) | Hedef |
|---|---|---|---|
| Doğru sayfa ilk 4'te | 20/20 (%100) | **17/20 (%85)** | %80 |
| Kişi / Tarih / Ders / Duyuru | %100 hepsi | %83 / %100 / %60 / %100 | %70 |
| Kapsam dışı sızıntı | 0/8 | **5/8** | 0 |
| Kapsam içi yanlış ret | 0/20 | **0/20** | 0 |

### 🔴 Kapsam kapısı yeniden kalibre edilmeli

Kapı, kapsam dışı soruların BM25 skorunun düşük kalmasına dayanıyor
(`bot/retriever.py`, `BM25_ESIGI = 4.0`). Eşik 41 kayıtlık veriyle ölçülmüştü ve
o ölçekte aralıklar ayrıktı: kapsam dışı 0.00–3.36, kapsam içi 4.59–18.18.

486 kayıtta aynı ölçüm **çakışıyor**:

| | BM25 |
|---|---|
| kapsam içi **min** | 5.76 ("kayıt yenileme tarihleri") |
| kapsam dışı **max** | 8.06 ("makarna tarifi ver") |

Yani hiçbir tek BM25 eşiği iki kümeyi ayıramaz — eşiği yükseltmek gerçek soruları
reddetmeye başlar. Sebep BM25'in nadir terimlere yüksek IDF vermesi: korpus
büyüdükçe alakasız sorular da bir belgeye çarpıyor ("hava durumu" → bir öğrenci
proje listesi, "makarna" → yemek listesi duyurusu). Kapının ikinci bir sinyale
ihtiyacı var (birim/terim eşleşmesi, sorgu sınıflandırma vb.).

Denenen ve **işe yaramayan** bir yol: duyuru/haber liste sayfalarını indeksten
çıkarmak. Sızıntıyı değiştirmedi (5/8) ve arama isabetini 14/20'ye düşürdü —
bazı testler zaten liste sayfasına eşleşerek geçiyordu.

**Cevap** (`eval/answer_test.py`, 8 soru):

| Model | Doğruluk | Hız |
|---|---|---|
| **gemma2:2b** (varsayılan) | **7/8 (%88)** | ~20 sn/soru |
| qwen2.5:1.5b-instruct | 4/8 (%50) | ~4 sn/soru |

qwen hızlı ama bağlamdaki cevabı göremiyor — telefon numarası bağlamın 1.
parçasında apaçık dururken "bilgi yok" diyordu. Doğruluk hızın önünde tutuldu.

### Bilinen kusur
"Güz yarıyılı ne zaman başlıyor" sorusunda model bazen Bahar tarihini veriyor.
Akademik takvim PDF'inde GÜZ ve BAHAR blokları ayrı parçalarda ve etiketli, ama
embedding "güz" sorgusunda BAHAR parçasını üste çıkarabiliyor.

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

### 🔴 Sessizce bozan iki tuzak

1. **URL'ler yeniden encode edilmez.** `brm`/`prsnl` Base64'tür, içinde `+` ve `=` geçer.
   `+` query string'de boşluğa döner ve sayfa bulunamaz. Sadece `html.unescape()` uygulanır.

2. **`.lower()` Türkçe'yi bozar.** `"İ".lower()` → `i` + **ayrı** birleşen nokta (U+0307);
   `"I".lower()` → `i` (Türkçe'de `ı` olmalı). Sonuç: *"bilgisayar"* araması *"BİLGİSAYAR"*
   ile **eşleşmez** — hata vermez, sadece yanlış cevap verir.
   Çözüm: `common/normalize.py` → `normalize_tr()`. İndeksleme ve sorgu **aynı** fonksiyonu
   kullanmak zorunda.

---

## Kapsam dışı

**Diğer 30 bölüm ve genel üniversite sayfaları** — bot tek bölüme cevap veriyor (yukarı bak) ·
login arkasındaki kişisel veri (not, transkript, ders kaydı) — OBS'ye yönlendirilir ·
İngilizce sayfalar · alt alan adları (`obs`, `lms`, `kutuphane`…) — yalnızca yönlendirme ·
`.docx`/`.xlsx` ekler (staj formları, 2024-2025 güz sınav takvimleri) — metne çevrilmiyor,
`scope.DISLANAN_UZANTILAR` içinde.
