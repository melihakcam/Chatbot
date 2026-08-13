"""model_karsilastirma.py -> model_karsilastirma.ipynb üretir.

NEDEN İKİ DOSYA:
    .ipynb JSON olduğu için git diff'i okunmuyor ve iki kişilik projede
    çakışması acı verici. Bu yüzden hücrelerin KAYNAĞI .py dosyasında duruyor.
    Ama Colab .py dosyasını notebook olarak açamıyor — yüklemek için .ipynb
    gerekiyor. Bu script ikisini senkron tutuyor.

KULLANIM:
    python notebooks/uret_ipynb.py
    -> notebooks/model_karsilastirma.ipynb  (Colab'a yüklenecek dosya)

Hücreleri değiştirmek istersen model_karsilastirma.py'yi düzenle, sonra bunu
tekrar çalıştır. .ipynb'yi elle düzenleme, üzerine yazılır.
"""

import base64
import gzip
import io
import json
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model_karsilastirma import BACKEND, INDEKS, KARSILASTIRMA, KURULUM, TABLO

PROJE = Path(__file__).resolve().parent.parent
CIKTI = Path(__file__).resolve().parent / "model_karsilastirma.ipynb"

# Colab'da gereken her sey. data/models (470 MB HF onbellegi) ve data/index
# BILEREK yok: birincisini Colab kendi indiriyor, ikincisini 2. hucre kuruyor.
PAKETE_GIREN = ["bot", "index", "common", "eval", "data/sample", "requirements.txt"]

BASLIK = """# KTÜN Chatbot — Model Karşılaştırması

Lokalde NVIDIA GPU yok; `gemma2:2b` CPU'da soru başına 12-62 saniye alıyor ve
2B üstü model denenemiyor. Colab'ın T4'ünde 7-9B modeller 4-bit ile çalışır.

**Amaç:** lokale hangi modelin kurulacağına karar vermek ve rapora tablo çıkarmak.

Kod bu notebook'un içinde gömülü geliyor — **başka dosya yüklemene gerek yok.**

## Çalıştırmadan önce

1. **Runtime → Change runtime type → T4 GPU** (zorunlu)
2. `google/gemma-*` modellerini de ölçmek istiyorsan: huggingface.co →
   Settings → Access Tokens'tan bir token al, `gemma-2-2b-it` ve `gemma-2-9b-it`
   sayfalarında lisansı kabul et, sonra Colab'ın sol panelindeki 🔑 **Secrets**
   bölümüne `HF_TOKEN` adıyla ekle ve "Notebook access"i aç.
   *Bunu atlarsan hiçbir şey kırılmaz — gemma'lar atlanır, Qwen modelleri ölçülür.*

Sonra hücreleri sırayla çalıştır. Son hücre Markdown tablo basar, doğrudan
README'ye yapıştırılabilir.
"""


def _temizle(bilgi: tarfile.TarInfo):
    """__pycache__/.pyc atar; mtime'i sabitler.

    mtime sabitlenmezse aynı kod her üretimde farklı base64 veriyor ve
    notebook'un git diff'i sebepsiz yere değişiyor.
    """
    ad = bilgi.name
    if "__pycache__" in ad or ad.endswith((".pyc", ".pyo")):
        return None
    bilgi.mtime, bilgi.uid, bilgi.gid = 0, 0, 0
    bilgi.uname = bilgi.gname = ""
    return bilgi


def payload_uret() -> str:
    """Projenin gereken kısmını tar.gz + base64 olarak döndürür."""
    tampon = io.BytesIO()
    # Once duz tar, sonra gzip.compress(mtime=0). "w:gz" kullanilsaydi gzip
    # basligina o anki saat yazilir ve payload her uretimde degisirdi.
    with tarfile.open(fileobj=tampon, mode="w", format=tarfile.GNU_FORMAT) as tar:
        for yol in PAKETE_GIREN:
            hedef = PROJE / yol
            if not hedef.exists():
                raise SystemExit(f"Pakete girecek yol yok: {yol}")
            tar.add(hedef, arcname=yol, filter=_temizle)
    return base64.b64encode(gzip.compress(tampon.getvalue(), mtime=0)).decode("ascii")


def satirla(b64: str, genislik: int = 96) -> str:
    """Tek satırlık base64'ü notebook JSON'unda okunur parçalara böler."""
    parcalar = [b64[i:i + genislik] for i in range(0, len(b64), genislik)]
    return '"\n    "'.join(parcalar)


def markdown_hucre(metin: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": metin.splitlines(keepends=True)}


def kod_hucre(metin: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": metin.strip().splitlines(keepends=True),
    }


def main() -> int:
    b64 = payload_uret()
    kurulum = KURULUM.replace("__PAYLOAD__", satirla(b64))

    hucreler = [
        markdown_hucre(BASLIK),
        markdown_hucre(
            "## 1. Kurulum\n\n"
            "**Hiçbir dosya yüklemene gerek yok.** Projenin Colab'da gereken kısmı "
            "(`bot/ index/ common/ eval/ data/sample/`) sıkıştırılıp bu hücrenin "
            "içine gömülü; hücre onu `/content/ktun`'a açıyor ve bağımlılıkları "
            "kuruyor. Ne zip, ne GitHub, ne token.\n\n"
            "> Klasörü zip'leyip yüklemek işe yaramıyordu: klasörün tamamı ~760 MB "
            "(`data/models` 470 MB embedding önbelleği + `.git` 290 MB), Colab'ın "
            "ihtiyacı olan kısım ise 0.5 MB — üstelik Colab'ın sol paneli klasör "
            "değil **dosya** kabul ediyor.\n\n"
            "⚠️ Gömülü kod üretildiği andaki hâlidir. Projede değişiklik yaptıysan "
            "`python notebooks/uret_ipynb.py` ile notebook'u yenile."
        ),
        kod_hucre(kurulum),
        markdown_hucre("## 2. İndeks\n"
                       "`data/raw/` gitignore'da; Colab repodaki örnek veriyle çalışır."),
        kod_hucre(INDEKS),
        markdown_hucre("## 3. Backend\n"
                       "Colab'da Ollama yok. `ColabBackend`, `bot/llm.py` ile **aynı** "
                       "`generate()` arayüzünü sağlıyor — `bot/` tarafında tek satır "
                       "değişmiyor."),
        kod_hucre(BACKEND),
        markdown_hucre("## 4. Karşılaştırma\n"
                       "Her model aynı sorularla ölçülür. Model değişimi arasında GPU "
                       "belleği boşaltılır, yoksa ikinci model sığmaz."),
        kod_hucre(KARSILASTIRMA),
        markdown_hucre("## 5. Tablo\nÇıktı doğrudan README'ye yapıştırılabilir."),
        kod_hucre(TABLO),
    ]

    notebook = {
        "cells": hucreler,
        "metadata": {
            "accelerator": "GPU",
            "colab": {"provenance": [], "gpuType": "T4"},
            "kernelspec": {"display_name": "Python 3", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 0,
    }

    CIKTI.write_text(json.dumps(notebook, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"YAZILDI: {CIKTI}")
    print(f"  {len(hucreler)} hucre ({sum(h['cell_type'] == 'code' for h in hucreler)} kod)")
    print("\nColab'a yuklemek icin: colab.research.google.com -> Dosya -> Not defteri yukle")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
