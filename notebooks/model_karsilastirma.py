"""Colab'da model karşılaştırması — bu dosya notebook'a hücre hücre yapıştırılır.

NEDEN .py OLARAK DURUYOR:
    .ipynb dosyaları JSON; git diff'i okunmaz ve çakışması acı verici. Mantık
    burada düz Python olarak duruyor, Colab'da hücrelere bölünüp çalıştırılıyor.
    Notebook'un kendisi repoda tutulmuyor (çıktılarıyla birlikte şişiyor).

NEDEN COLAB:
    Lokalde NVIDIA GPU yok; gemma2:2b CPU'da soru başına 12-62 saniye alıyor ve
    2B üstü model denenemiyor. Colab'ın T4'ünde 7-9B modeller 4-bit ile çalışır.
    Amaç lokale hangi modelin kurulacağına karar vermek ve rapora tablo çıkarmak.

KULLANIM (Colab):
    1. Runtime -> Change runtime type -> T4 GPU
    2. Aşağıdaki HÜCRE bloklarını sırayla çalıştır
    3. Son hücre karşılaştırma tablosunu basar
"""

# ---------------------------------------------------------------- HÜCRE 1: kurulum
#
# DİKKAT: Repo PRIVATE. Kimlik doğrulaması olmadan git clone başarısız olur,
# /content/ktun oluşmaz, sonraki hücrelerde "No module named 'bot'" hatası alınır.
# Bu yüzden klonlama denenip SONUCU KONTROL EDİLİYOR ve başarısızsa ne yapılacağı
# yazdırılıyor — sessizce devam edip kafa karıştıran hataya yol açmıyor.
# Kod Colab'a ELLE yükleniyor (repo private, git clone kimlik doğrulaması istiyor).
#
# Bu hücre "ne yüklediğini" varsaymıyor: zip de olabilir, klasör de, dosyaların
# doğrudan /content'e atılmış hâli de. Proje kökünü `bot/` ve `index/` klasörlerini
# arayarak kendisi buluyor. Böylece yükleme biçimi değişince hücreyi düzenlemek
# gerekmiyor — ve yanlış dizinde çalışıp "No module named 'bot'" hatası vermiyor.
KURULUM = r"""
!pip -q install sentence-transformers rank-bm25 transformers accelerate bitsandbytes

import os, sys, glob, zipfile

ATLA = {"sample_data", "__pycache__", ".git", ".config", ".ipynb_checkpoints"}


# bot/ index/ common/ klasorlerini BIRLIKTE iceren dizini bulur.
def proje_kokunu_bul(basla="/content", derinlik=4):
    for kok, klasorler, _ in os.walk(basla):
        klasorler[:] = [d for d in klasorler if d not in ATLA]
        if kok.count(os.sep) - basla.count(os.sep) > derinlik:
            klasorler[:] = []
            continue
        if {"bot", "index", "common"} <= set(klasorler):
            return kok
    return None


KOK = proje_kokunu_bul()

# Klasor yerine zip atilmissa: ac, tekrar ara.
if KOK is None:
    for z_yol in glob.glob("/content/**/*.zip", recursive=True):
        with zipfile.ZipFile(z_yol) as z:
            z.extractall("/content/ktun")
        print(f"Zip acildi: {z_yol}")
    KOK = proje_kokunu_bul()

if KOK is None:
    print("Proje bulunamadi. /content icinde su anda sunlar var:")
    for ad in sorted(os.listdir("/content")):
        print("   ", ad)
    raise SystemExit(
        "\nSoldaki klasor simgesine tiklayip ktunChatbot klasorunu surukle,\n"
        "sonra bu hucreyi tekrar calistir.\n"
        "Gereken klasorler: bot/ index/ common/ eval/ data/sample/"
    )

os.chdir(KOK)
sys.path.insert(0, KOK)        # 'bot', 'index', 'common' import edilebilsin
os.environ["KTUN_KOK"] = KOK   # sonraki hucreler bunu kullaniyor

print("Proje koku:", KOK)
print("Klasorler:", sorted(d for d in os.listdir() if os.path.isdir(d) and not d.startswith(".")))
ornek = os.path.join(KOK, "data", "sample", "pages.sample.jsonl")
print("Ornek veri:", "VAR" if os.path.exists(ornek) else "YOK — indeks kurulamaz")
"""

# ---------------------------------------------------------------- HÜCRE 2: indeks
# data/raw gitignore'da, repoda data/sample var — Colab bununla çalışır.
INDEKS = r"""
import os
os.chdir(os.environ["KTUN_KOK"])
!python -m index.build_index --input data/sample/pages.sample.jsonl
"""

# ---------------------------------------------------------------- HÜCRE 3: backend
# Colab'da Ollama yok; transformers ile aynı generate() arayüzü sağlanıyor.
# bot/ tarafındaki hiçbir kod değişmiyor — llm.py'nin sözleşmesi buydu.
BACKEND = r'''
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

class ColabBackend:
    """bot/llm.py ile aynı arayüz: generate(prompt, ..., sistem=None) -> str"""

    def __init__(self, model_adi: str):
        self.model = model_adi
        self.tokenizer = AutoTokenizer.from_pretrained(model_adi)
        self.llm = AutoModelForCausalLM.from_pretrained(
            model_adi,
            quantization_config=BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_quant_type="nf4",
            ),
            device_map="auto",
        )

    def hazir_mi(self):
        return True, "hazir"

    def generate(self, prompt, sicaklik=0.2, maks_token=220, sistem=None):
        mesajlar = ([{"role": "system", "content": sistem}] if sistem else [])
        mesajlar.append({"role": "user", "content": prompt})

        # Gemma sistem rolünü desteklemiyor — kuralları kullanıcı mesajına katıyoruz.
        if "gemma" in self.model.lower() and sistem:
            mesajlar = [{"role": "user", "content": f"{sistem}\n\n{prompt}"}]

        girdi = self.tokenizer.apply_chat_template(
            mesajlar, add_generation_prompt=True, return_tensors="pt"
        ).to(self.llm.device)

        with torch.no_grad():
            cikti = self.llm.generate(
                girdi,
                max_new_tokens=maks_token,
                temperature=max(sicaklik, 0.01),
                do_sample=sicaklik > 0,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        return self.tokenizer.decode(cikti[0][girdi.shape[-1]:], skip_special_tokens=True).strip()
'''

# ---------------------------------------------------------------- HÜCRE 4: karşılaştırma
KARSILASTIRMA = r'''
import os, sys, time, gc, torch

# Guvenlik agi: hucreler sirasiz calistirilirsa veya oturum yeniden baglanirsa
# calisma dizini /content'e doner ve "No module named 'bot'" hatasi alinir.
KOK = os.environ.get("KTUN_KOK")
if not KOK:
    raise SystemExit("Once 1. hucreyi calistir (proje kokunu o buluyor).")
os.chdir(KOK)
if KOK not in sys.path:
    sys.path.insert(0, KOK)

from bot.answer import Chatbot
from eval.answer_test import SORULAR, KAPSAM_DISI

# Hepsi Türkçe destekli, Colab T4'e 4-bit ile sığan modeller.
ADAYLAR = [
    "google/gemma-2-2b-it",          # lokalde kazanan, referans
    "Qwen/Qwen2.5-1.5B-Instruct",    # lokalde hızlı ama isabetsiz
    "Qwen/Qwen2.5-7B-Instruct",      # lokalde çalışmaz, tavanı görmek için
    "google/gemma-2-9b-it",          # en büyük aday
]

sonuclar = []
for model_adi in ADAYLAR:
    print(f"\n{'='*70}\n{model_adi}\n{'='*70}")
    try:
        bot = Chatbot("dummy")            # indeks/retriever kurulsun
        bot.backend = ColabBackend(model_adi)   # backend'i degistir
    except Exception as e:
        print(f"  YUKLENEMEDI: {e}")
        continue

    isabet, sure_toplam = 0, 0.0
    for soru, beklenen, tip in SORULAR:
        bot.gecmisi_temizle()
        t = time.time()
        cevap = bot.sor(soru)
        sure_toplam += time.time() - t
        ok = beklenen.casefold() in cevap.metin.casefold()
        isabet += ok
        print(f"  {'OK  ' if ok else 'HATA'} {soru[:42]:44} {cevap.metin[:70]}")

    # Kapsam disi sorular LLM'e hic gitmiyor (kapi retriever'da), yine de dogrula.
    kapsam_ok = sum(bot.sor(s).kapsam_disi for s in KAPSAM_DISI)

    sonuclar.append({
        "model": model_adi,
        "dogruluk": f"{isabet}/{len(SORULAR)}",
        "yuzde": round(100 * isabet / len(SORULAR)),
        "kapsam": f"{kapsam_ok}/{len(KAPSAM_DISI)}",
        "sn_soru": round(sure_toplam / len(SORULAR), 1),
    })

    del bot
    gc.collect()
    torch.cuda.empty_cache()
'''

# ---------------------------------------------------------------- HÜCRE 5: tablo
TABLO = r'''
import pandas as pd
tablo = pd.DataFrame(sonuclar)
print(tablo.to_markdown(index=False))   # dogrudan README'ye yapistirilabilir
tablo.to_csv("model_karsilastirma.csv", index=False)
'''

if __name__ == "__main__":
    print(__doc__)
    for ad, hucre in [("1 KURULUM", KURULUM), ("2 INDEKS", INDEKS), ("3 BACKEND", BACKEND),
                      ("4 KARSILASTIRMA", KARSILASTIRMA), ("5 TABLO", TABLO)]:
        print(f"\n{'#' * 70}\n# HUCRE {ad}\n{'#' * 70}{hucre}")
