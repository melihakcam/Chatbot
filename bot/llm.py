"""LLM arka uçları — tek arayüz: generate(prompt) -> str.

Backend bayrakla seçilir, çağıran taraf hangisi olduğunu bilmez:

    ollama       lokal model (varsayılan). CPU'da çalışır, GPU gerekmez.
    dummy        model YOK. Bağlamı olduğu gibi geri döndürür.
                 Amaç: arama zincirini model kurulumu beklemeden test etmek
                 ve bir hatanın aramadan mı modelden mi geldiğini ayırmak.

Yeni backend eklemek (Colab'daki uzak model gibi) = yeni bir sınıf + KAYIT'a bir satır.
"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OLLAMA_URL = "http://localhost:11434"

# gemma2:2b, qwen2.5:1.5b-instruct'a karsi olculdu (eval/answer_test.py, 8 soru):
#   gemma2:2b            7/8 = %88 dogruluk, ~20 sn/soru
#   qwen2.5:1.5b         4/8 = %50 dogruluk,  ~4 sn/soru
# qwen hizli ama baglamdaki cevabi goremiyor: telefon numarasi baglamin 1.
# parcasinda apacik dururken "bilgi yok" diyordu. Dogruluk hiz'in onunde.
VARSAYILAN_MODEL = "gemma2:2b"


class LLMHatasi(RuntimeError):
    pass


class OllamaBackend:
    def __init__(self, model: str = VARSAYILAN_MODEL, url: str = OLLAMA_URL):
        self.model = model
        self.url = url

    def hazir_mi(self) -> tuple[bool, str]:
        try:
            with urllib.request.urlopen(f"{self.url}/api/tags", timeout=5) as cevap:
                veri = json.loads(cevap.read())
        except (urllib.error.URLError, TimeoutError, OSError):
            return False, (
                "Ollama servisine ulasilamadi.\n"
                "  Cozum: Ollama uygulamasini baslat, veya terminalde 'ollama serve'"
            )

        modeller = [m["name"] for m in veri.get("models", [])]
        if self.model not in modeller:
            return False, (
                f"Model kurulu degil: {self.model}\n"
                f"  Cozum: ollama pull {self.model}\n"
                f"  Kurulu olanlar: {', '.join(modeller) or '(yok)'}"
            )
        return True, "hazir"

    def generate(self, prompt: str, sicaklik: float = 0.2, maks_token: int = 220,
                 sistem: str | None = None) -> str:
        """Modeli /api/chat ile çağırır.

        NEDEN /api/generate DEĞİL: instruct modeller kendi sohbet şablonlarıyla
        (system/user rolleri) eğitiliyor. Ham metin gönderince talimat takibi
        gözle görülür şekilde bozuluyordu — model bağlamdaki telefon numarasını
        görmesine rağmen "bilgi yok" diyordu.
        """
        mesajlar = []
        if sistem:
            mesajlar.append({"role": "system", "content": sistem})
        mesajlar.append({"role": "user", "content": prompt})

        istek = json.dumps({
            "model": self.model,
            "messages": mesajlar,
            "stream": False,
            "options": {
                # Düşük sıcaklık: bu bir destek botu, yaratıcılık istemiyoruz.
                # Bağlamda olmayan bilgiyi uydurma eğilimi sıcaklıkla artıyor.
                "temperature": sicaklik,
                # CPU'da her üretilen token pahalı (~5 token/sn). Prompt zaten
                # "en fazla 4 cümle" diyor; 400 token tavanı sadece model
                # kuralı unutup uzattığında devreye giriyordu ve tek cevabı
                # dakikalarca uzatabiliyordu.
                "num_predict": maks_token,
                "top_p": 0.9,
                # Model listeyi tekrarlayıp durursa erken kes.
                "repeat_penalty": 1.15,
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.url}/api/chat", data=istek,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as cevap:
                return json.loads(cevap.read())["message"]["content"].strip()
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise LLMHatasi(f"Ollama cagrisi basarisiz: {e}") from e


class DummyBackend:
    """Model yok — bulunan bağlamı özetleyerek döndürür.

    Cevap kalitesi test edilemez ama zincirin geri kalanı (arama, kapsam kapısı,
    kaynak gösterimi, hafıza) model olmadan uçtan uca çalışır.
    """

    model = "dummy"

    def hazir_mi(self) -> tuple[bool, str]:
        return True, "hazir (model yok)"

    def generate(self, prompt: str, sicaklik: float = 0.0, maks_token: int = 0,
                 sistem: str | None = None) -> str:
        bag_bas = prompt.find("--- BAGLAM ---")
        bag_son = prompt.find("--- SORU ---")
        if bag_bas == -1 or bag_son == -1:
            return "[dummy] Baglam bulunamadi."
        baglam = prompt[bag_bas + len("--- BAGLAM ---"):bag_son].strip()
        ilk = "\n".join(baglam.split("\n")[:6])
        return f"[dummy backend — model calistirilmadi]\nBulunan baglamin basi:\n{ilk}"


KAYIT = {"ollama": OllamaBackend, "dummy": DummyBackend}


def backend_olustur(ad: str = "ollama", model: str = VARSAYILAN_MODEL):
    if ad not in KAYIT:
        raise ValueError(f"Bilinmeyen backend: {ad}. Secenekler: {list(KAYIT)}")
    return OllamaBackend(model) if ad == "ollama" else DummyBackend()


if __name__ == "__main__":
    from common.console import setup_stdout_utf8

    setup_stdout_utf8()
    for ad in ("dummy", "ollama"):
        backend = backend_olustur(ad)
        hazir, mesaj = backend.hazir_mi()
        print(f"[{ad:6}] {'HAZIR' if hazir else 'HAZIR DEGIL'}: {mesaj}")
        if hazir and ad == "ollama":
            print("  test cevabi:", backend.generate(
                "Tek cumleyle cevapla: Konya hangi ulkededir?", maks_token=50))
