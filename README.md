# KTÜN Destek Chatbotu

Konya Teknik Üniversitesi için, **sadece** üniversiteyle ilgili sorulara cevap veren destek
chatbotu. Bilgi kaynağı üniversitenin kendi sitesi (ktun.edu.tr); bilgi modele
ezberletilmez, soru anında ilgili sayfalar bulunup modele okutulur (**RAG**).

Hedef soru tipleri: **kişi/iletişim** · **tarih/takvim** · **ders/program** · **duyuru/haber**

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

| Ölçüt | Sonuç | Hedef |
|---|---|---|
| Doğru sayfa ilk 4'te | **20/20 (%100)** | %80 |
| Kişi / Tarih / Ders / Duyuru | %100 / %100 / %100 / %100 | %70 |
| Kapsam dışı sızıntı | **0/8** | 0 |
| Kapsam içi yanlış ret | **0/20** | 0 |

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
- **`data/sample/pages.sample.jsonl`** (40 gerçek sayfa, repoda) → B, crawler hiç
  yazılmamışken çalışır. Gerçek veri gelince tek değişen `--input` yolu olur, kod değişmez.
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
| Hoca iletişimi | Kişi sayfası sekmeleri AJAX. Kaynak: `/tr/Universite/TelefonRehberiBirimDetay` |
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

Login arkasındaki kişisel veri (not, transkript, ders kaydı) — OBS'ye yönlendirilir ·
İngilizce sayfalar · alt alan adları (`obs`, `lms`, `kutuphane`…) — yalnızca yönlendirme.
