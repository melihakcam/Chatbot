# Veri Sözleşmesi — `pages.jsonl`

Bu dosya **A (crawler) ile B (bot) arasındaki tek bağlantı noktasıdır.**
A bu formatta üretir, B bu formatı okur. İki taraf birbirinin koduna bakmadan çalışır.

**Bu şema donduruldu.** Değiştirmek gerekirse iki kişi de haberdar olmalı ve
`scripts/validate_jsonl.py` aynı commit'te güncellenmeli.

---

## Format

Her satır bir JSON nesnesi (JSON Lines). Dosya UTF-8.

```json
{
  "url": "https://www.ktun.edu.tr/tr/Birim/AkademikPersonel/?brm=ZqPz79axeg4K1EYxLLCyVg==",
  "title": "Akademik Personel",
  "breadcrumb": ["Akademik", "Bilgisayar ve Bilişim Bilimleri Fakültesi", "Yazılım Mühendisliği"],
  "unit": "Yazılım Mühendisliği",
  "doc_type": "personel",
  "text": "Akademik Personel\nDoç. Dr. Emine BAŞ\n...",
  "published_at": null,
  "fetched_at": "2026-08-12T21:00:00",
  "content_hash": "9f2b1c..."
}
```

## Alanlar

| Alan | Tip | Zorunlu | Açıklama |
|---|---|---|---|
| `url` | string | ✅ | Tam URL. **Sayfadan çıkarıldığı gibi**, yeniden encode edilmemiş (bkz. Tuzak #1) |
| `title` | string | ✅ | Sayfa başlığı. Boşsa `unit` veya URL son parçası kullanılır |
| `breadcrumb` | string[] | ✅ | Sayfanın yeri. Bilinmiyorsa `[]` |
| `unit` | string \| null | ✅ | Bağlı olduğu birim/bölüm. Genel sayfalarda `null` |
| `doc_type` | enum | ✅ | `personel` · `duyuru` · `haber` · `sayfa` · `pdf` · `tablo` |
| `text` | string | ✅ | Temiz metin. **En az 20 karakter.** Tablolar Markdown satırı olarak |
| `published_at` | string \| null | ✅ | `YYYY-MM-DD`. Duyuru/haberde dolu, diğerlerinde `null` |
| `fetched_at` | string | ✅ | ISO 8601, çekilme anı |
| `content_hash` | string | ✅ | `text` alanının SHA1'i. Değişmeyen sayfayı atlamak için |

### `doc_type` seçim kuralı
- `personel` → akademik/idari personel listesi veya kişi kaydı
- `duyuru` / `haber` → `DuyuruDetay` / `HaberDetay` sayfaları
- `pdf` → kaynağı PDF olan içerik (akademik takvim dahil)
- `tablo` → içeriğin ana gövdesi tablo olan sayfa (`BolumDersleri` gibi)
- `sayfa` → diğer her şey

---

## Kurallar

1. **URL yeniden encode edilmez.** `brm` / `prsnl` parametreleri Base64'tür, içinde `+` ve `=`
   geçer. `+` query string'de boşluğa dönüşür ve sayfa bulunamaz. HTML'den çıkarılan değer
   yalnızca `html.unescape()`'ten geçirilir, `urlencode`/`quote` **uygulanmaz**.
2. **Aynı `url` iki kez yazılmaz.** Tekrar çalıştırmada `content_hash` aynıysa satır atlanır.
3. **`text` boş veya çöp olamaz.** Menü/footer temizlenmiş olmalı; 20 karakterin altı yazılmaz.
4. **Tablolar korunur.** `<table>` satırları `| hücre | hücre |` biçiminde tek satırda kalır;
   düz metne çevrilip satır/sütun ilişkisi kaybedilmez.
5. **Metin normalize edilmez.** `text` orijinal büyük/küçük harfiyle yazılır.
   Normalizasyon (`normalize_tr`) sadece **arama sırasında** uygulanır.

## Doğrulama

```bash
python scripts/validate_jsonl.py data/sample/pages.sample.jsonl
```

Bu komut iki taraf için de ortak hakemdir: A "işim bitti" derken, B "veri bozuk" derken
aynı komutu çalıştırır.
