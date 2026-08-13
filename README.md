# KTÜN Destek Chatbotu

Konya Teknik Üniversitesi **Yapay Zeka ve Makine Öğrenmesi Mühendisliği bölümü** için,
sadece bölümle ilgili sorulara cevap veren destek chatbotu. Bilgi kaynağı üniversitenin
kendi sitesi (ktun.edu.tr); bilgi modele ezberletilmez, soru anında ilgili sayfalar bulunup
modele okutulur (**RAG**).

Hedef soru tipleri: **kişi/iletişim** · **tarih/takvim** · **ders/program** · **duyuru/haber**

## Kapsam: tek bölüm

Bot tüm üniversiteye değil, tek bölüme cevap veriyor. Sebep pratik: 31 bölümün tamamı
binlerce sayfa demek, ve arama havuzu büyüdükçe "hangi bölümün sınav takvimi" ayrımı
zorlaşıp yanlış bölümün cevabı dönüyor. Tek bölümde 67 kayıt, hepsi aynı birime ait —
`unit` alanına bakarak eleme yapmak gerekmiyor.

Çekilen 67 kaydın dağılımı: **41 PDF** (öğretim planı, 4 dönem ders programı, 10 sınav
takvimi, staj belgeleri, kalite/süreç dosyaları) · 11 sayfa · 9 personel (8 hoca + liste) ·
4 tablo (AKTS ders listeleri) · 2 duyuru.

Hocaların akademik geçmişi ve verdiği dersler kişi sayfalarının AJAX sekmelerinden geliyor;
bir hoca = bir kayıt (sekmeler ayrı kayıt olsaydı hepsi aynı URL'e düşerdi). Yayın listeleri
(makale, kitap, bildiri) bilerek toplanmıyor — hedef soru tipleri kişi/ders odaklı.

> Bölümün "Öğretim Planı", "Ders Programı", "Sınav Programları" sayfalarının **metni
> neredeyse boştur** — sadece PDF linkleri taşırlar. Asıl içerik `/Dosyalar/**.pdf`
> altında, yani `/tr/Birim/` dışında. Bu yüzden `--sadece-birim` PDF'leri elemez
> (`crawler/run.py:ekle`); elerse bölümün ders ve sınav verisinin tamamı kaybolur.

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

## Komutlar

```bash
python scripts/validate_jsonl.py data/raw/pages.jsonl         # şema doğrula
python scripts/make_sample.py                                 # crawler çıktısı -> örnek veri
python common/normalize.py                                    # Türkçe normalizasyon testleri
```

Veri güncellemek = crawler'ı tekrar çalıştırmak; `--sifirdan` verilmezse mevcut
kayıtlarla birleştirir.

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
- **`data/sample/pages.sample.jsonl`** (67 gerçek sayfa, repoda) → `data/raw/` gitignore'da,
  yani repoyu klonlayan biri crawler'ı çalıştırmadan elinde veri bulamaz. Örnek dosya
  crawler çıktısından üretilir (`scripts/make_sample.py`); gerçek veriye geçmek tek şey
  değiştirir: `--input` yolu, kod değişmez.
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
