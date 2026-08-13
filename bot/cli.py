"""Terminal sohbeti.

ÇALIŞTIRMA:
    python -m bot.cli                          # Ollama ile
    python -m bot.cli --backend dummy          # model olmadan (arama testi)
    python -m bot.cli --model gemma2:2b        # baska model
    python -m bot.cli --no-llm                 # sadece arama sonuclarini goster
    python -m bot.cli "yazilim hocalari kimler"  # tek soru sor ve cik

KOMUTLAR:
    /kaynak    son cevabin kaynaklarini detayli goster
    /temizle   sohbet gecmisini sifirla
    /cik       cikis
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.console import setup_stdout_utf8
from bot.answer import Chatbot
from bot.llm import backend_olustur
from bot.retriever import Retriever


def sadece_arama(sorular: list[str]) -> int:
    """--no-llm: modeli hic calistirmadan arama sonuclarini goster."""
    retriever = Retriever()
    print(f"Indeks: {retriever.meta['parca_sayisi']} parca (LLM kapali)\n")
    for soru in sorular:
        sonuclar = retriever.search(soru, k=4)
        durum = "KAPSAM DISI" if retriever.kapsam_disi_mi(sonuclar) else "kapsam ici"
        print(f"SORU: {soru}   [{durum}]")
        for i, s in enumerate(sonuclar, 1):
            print(f"  {i}. [{s.doc_type:8}] {s.title[:52]}")
            print(f"     {s.text[:100].replace(chr(10), ' / ')}")
        print()
    return 0


def main() -> int:
    setup_stdout_utf8()

    ayristirici = argparse.ArgumentParser(description="KTUN destek chatbotu")
    ayristirici.add_argument("soru", nargs="*", help="tek soru sor ve cik")
    ayristirici.add_argument("--backend", default="ollama", choices=["ollama", "dummy"])
    ayristirici.add_argument("--model", default=None, help="ollama model adi")
    ayristirici.add_argument("--no-llm", action="store_true",
                             help="modeli calistirma, sadece arama sonuclarini goster")
    args = ayristirici.parse_args()

    if args.no_llm:
        return sadece_arama(args.soru or ["yazilim muhendisligi hocalari"])

    # Model hazir mi kontrolu — hata mesaji cozumuyle birlikte gelsin.
    kontrol = backend_olustur(args.backend, args.model) if args.model else backend_olustur(args.backend)
    hazir, mesaj = kontrol.hazir_mi()
    if not hazir:
        print(f"HATA: {mesaj}")
        print("\nModel olmadan arama zincirini test etmek icin:")
        print("  python -m bot.cli --backend dummy")
        return 1

    print("Indeks ve model yukleniyor...")
    bot = Chatbot(args.backend, args.model)
    print(f"Hazir. Model: {bot.backend.model} | Indeks: {bot.retriever.meta['parca_sayisi']} parca")

    if args.soru:
        cevap = bot.sor(" ".join(args.soru))
        print("\n" + cevap.tam_metin())
        return 0

    print("Komutlar: /kaynak  /temizle  /cik\n")
    son_cevap = None

    while True:
        try:
            soru = input("\nSen > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGorusuruz.")
            return 0

        if not soru:
            continue
        if soru in ("/cik", "/exit", "/q"):
            print("Gorusuruz.")
            return 0
        if soru == "/temizle":
            bot.gecmisi_temizle()
            print("Sohbet gecmisi silindi.")
            continue
        if soru == "/kaynak":
            if son_cevap is None or not son_cevap.kaynaklar:
                print("Son cevapta kaynak yok.")
                continue
            for i, s in enumerate(son_cevap.kaynaklar, 1):
                print(f"\n[{i}] {s.title}  (kosinus={s.kosinus:.3f}, tip={s.doc_type})")
                print(f"    {s.url}")
                print(f"    {s.text[:300].replace(chr(10), ' / ')}")
            continue

        cevap = bot.sor(soru)
        son_cevap = cevap

        if cevap.kullanilan_soru != soru and not cevap.yonlendirme:
            print(f"  (arama sorusu: {cevap.kullanilan_soru})")

        print(f"\nBot > {cevap.tam_metin()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
