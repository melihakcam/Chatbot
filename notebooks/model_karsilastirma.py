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
# NEDEN ZIP DEĞİL KLONLAMA:
#     Önce "klasörü zip'leyip Colab'a yükle" deniyordu. Çalışmadı: klasörün
#     tamamı ~760 MB (data/models 470 MB HF önbelleği + .git 290 MB), işe
#     yarayan kısım 0.5 MB. Yükleme ya kopuyor ya da içeri eski __pycache__
#     giriyor. `git clone --depth 1` ise 1 MB'ın altında ve her çalıştırmada
#     güncel — kod değişince yeniden zip'lemek gerekmiyor.
#
# TOKEN NEREDE DURUYOR:
#     Repo private. Token notebook'a YAZILMIYOR (repoya sızar); Colab'ın
#     Secrets panelinden okunuyor. Secret yoksa gizli giriş kutusu açılıyor,
#     yani hücre yine de çalışıyor — sadece her oturumda soruyor.
#     google/gemma-* HF'de KAPALI repo; onun için ayrıca HF_TOKEN gerekiyor,
#     yoksa 4. hücre o modelleri atlıyor (çökmüyor).
KURULUM = r"""
!pip -q install sentence-transformers rank-bm25 transformers accelerate bitsandbytes

import getpass
import os
import subprocess
import sys

REPO = "github.com/melihakcam/Chatbot.git"
KOK = "/content/ktun"


# Colab Secrets'tan okur; panel yoksa veya izin verilmemisse None doner.
def gizli(ad):
    try:
        from google.colab import userdata
        return userdata.get(ad)
    except Exception:
        return None


if os.path.isdir(os.path.join(KOK, "bot")):
    subprocess.run(["git", "-C", KOK, "pull", "--quiet"], check=False)
    print("Repo zaten vardi, guncellendi.")
else:
    gh = gizli("GH_TOKEN")
    if not gh:
        print("Colab Secrets'ta GH_TOKEN yok (sol paneldeki anahtar simgesi).")
        gh = getpass.getpass("GitHub token: ").strip()

    sonuc = subprocess.run(
        ["git", "clone", "--depth", "1", f"https://{gh}@{REPO}", KOK],
        capture_output=True, text=True,
    )
    if sonuc.returncode:
        # Token hata metninde gecebiliyor; loglara dusmesin diye maskeleniyor.
        raise SystemExit("Klonlama basarisiz:\n" + sonuc.stderr.replace(gh, "***"))
    print("Repo klonlandi.")

os.chdir(KOK)
if KOK not in sys.path:
    sys.path.insert(0, KOK)    # 'bot', 'index', 'common' import edilebilsin
os.environ["KTUN_KOK"] = KOK   # sonraki hucreler bunu kullaniyor

# gemma-2 HF'de kapali: token yoksa 4. hucre o modelleri atlar.
hf = gizli("HF_TOKEN")
if hf:
    os.environ["HF_TOKEN"] = hf

ornek = "data/sample/pages.sample.jsonl"
print("Kok         :", KOK)
print("Ornek veri  :", "VAR" if os.path.exists(ornek) else "YOK — indeks kurulamaz")
print("HF_TOKEN    :", "var" if hf else "YOK — google/gemma-* atlanacak")
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

# google/gemma-* HF'de kapali repo (lisans onayi + token ister). Token yoksa
# indirme 4 dakika sonra 401 ile duserdi; bastan eleniyor ki neden belli olsun.
if not os.environ.get("HF_TOKEN"):
    atlanan = [m for m in ADAYLAR if m.startswith("google/")]
    ADAYLAR = [m for m in ADAYLAR if m not in atlanan]
    if atlanan:
        print("HF_TOKEN yok, atlanan modeller:", ", ".join(atlanan))

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
