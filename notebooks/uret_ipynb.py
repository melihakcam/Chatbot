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

## Çalıştırmadan önce iki ayar

1. **Runtime → Change runtime type → T4 GPU**
2. Sol paneldeki 🔑 **Secrets** → şu ikisini ekle, "Notebook access" aç:

| Secret | Nereden | Gerekli mi |
|---|---|---|
| `GH_TOKEN` | GitHub → Settings → Developer settings → Personal access tokens → Fine-grained, sadece `Chatbot` reposu + `Contents: Read` | Evet — repo private |
| `HF_TOKEN` | huggingface.co → Settings → Access Tokens (ayrıca `google/gemma-2-2b-it` ve `-9b-it` sayfalarında lisansı kabul et) | Hayır — yoksa gemma modelleri atlanır, Qwen'ler ölçülür |

`GH_TOKEN` secret'ı yoksa hücre gizli bir giriş kutusu açar; token notebook'a
yazılmaz, dolayısıyla repoya da sızmaz.

Sonra hücreleri sırayla çalıştır. Son hücre Markdown tablo basar, doğrudan
README'ye yapıştırılabilir.
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
            "Hiçbir şey yüklemen gerekmiyor — bu hücre repoyu kendisi klonluyor "
            "(`--depth 1`, 1 MB'ın altında) ve bağımlılıkları kuruyor.\n\n"
            "> Klasörü zip'leyip yüklemek işe yaramıyordu: klasörün tamamı ~760 MB "
            "(`data/models` 470 MB embedding önbelleği + `.git` 290 MB), Colab'ın "
            "ihtiyacı olan kısım ise 0.5 MB. Ayrıca Colab'ın sol paneli klasör değil "
            "**dosya** kabul ediyor. Klonlama ikisini birden çözüyor ve kod "
            "değiştiğinde yeniden yüklemek gerekmiyor.\n\n"
            "Hücre ikinci kez çalıştırılırsa klonlamak yerine `git pull` yapar."
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
