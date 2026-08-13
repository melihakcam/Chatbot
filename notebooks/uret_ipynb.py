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

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model_karsilastirma import BACKEND, INDEKS, KARSILASTIRMA, KURULUM, TABLO

CIKTI = Path(__file__).resolve().parent / "model_karsilastirma.ipynb"

BASLIK = """# KTÜN Chatbot — Model Karşılaştırması

Lokalde NVIDIA GPU yok; `gemma2:2b` CPU'da soru başına 12-62 saniye alıyor ve
2B üstü model denenemiyor. Colab'ın T4'ünde 7-9B modeller 4-bit ile çalışır.

**Amaç:** lokale hangi modelin kurulacağına karar vermek ve rapora tablo çıkarmak.

**Önce: Runtime → Change runtime type → T4 GPU**

Hücreleri sırayla çalıştır. Son hücre Markdown tablo basar, doğrudan README'ye
yapıştırılabilir.
"""


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
    hucreler = [
        markdown_hucre(BASLIK),
        markdown_hucre(
            "## 1. Kurulum\n\n"
            "**Önce proje dosyalarını yükle:** soldaki klasör simgesine tıkla, "
            "proje klasörünü (veya zip'ini) `/content` içine sürükle. "
            "Sonra bu hücreyi çalıştır.\n\n"
            "Hücre proje kökünü kendisi bulur — zip, klasör ya da doğrudan atılmış "
            "dosyalar, hepsi çalışır. Repo private olduğu için Colab klonlayamıyor.\n\n"
            "Gereken klasörler: `bot/ index/ common/ eval/ data/sample/` "
            "(model ağırlıkları ve indeks gerekmez, Colab kendisi üretir)."
        ),
        kod_hucre(KURULUM),
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
