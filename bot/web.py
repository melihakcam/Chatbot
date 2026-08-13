"""Tarayıcı arayüzü — CLI'ın yaptığını localhost'ta yapar.

ÇALIŞTIRMA:
    python -m bot.web                      # http://127.0.0.1:8000
    python -m bot.web --port 8080
    python -m bot.web --backend dummy      # model olmadan (arama zincirini gör)

NEDEN STDLIB:
    Flask/Gradio tek bir sohbet sayfası için yeni bağımlılık demek. Proje
    boyunca bağımlılık listesi bilinçli olarak kısa tutuldu; burada da
    `http.server` yetiyor. requirements.txt değişmiyor.

NEDEN TEK KULLANICI:
    Sohbet geçmişi Chatbot nesnesinin içinde duruyor, yani sunucu tek bir
    konuşma tutuyor. Bu yerel bir geliştirme aracı; iki sekmeden aynı anda
    yazılırsa geçmiş karışır. Kilit sadece iki isteğin modeli aynı anda
    çağırıp birbirinin bağlamını bozmasını engelliyor.

DIKKAT: Sunucu yalnizca 127.0.0.1'e baglaniyor — disaridan erisilmiyor.
"""

import argparse
import html
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.console import setup_stdout_utf8
from bot.answer import Chatbot
from bot.llm import backend_olustur

BOT: Chatbot | None = None
KILIT = threading.Lock()

SAYFA = """<!doctype html>
<html lang="tr">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KTÜN Destek Chatbotu</title>
<style>
  :root { color-scheme: light dark; }
  body { margin: 0; font: 16px/1.55 system-ui, sans-serif;
         background: #f6f7f9; color: #16181d; }
  @media (prefers-color-scheme: dark) {
    body { background: #14161a; color: #e7e9ee; }
  }
  header { padding: 14px 20px; border-bottom: 1px solid #8883;
           display: flex; align-items: baseline; gap: 12px; }
  header b { font-size: 17px; }
  header span { font-size: 13px; opacity: .65; }
  header button { margin-left: auto; font: inherit; font-size: 13px;
                  padding: 5px 12px; border-radius: 7px; cursor: pointer;
                  border: 1px solid #8886; background: transparent; color: inherit; }
  #akis { max-width: 780px; margin: 0 auto; padding: 22px 20px 150px; }
  .balon { padding: 12px 15px; border-radius: 13px; margin: 12px 0;
           max-width: 82%; white-space: pre-wrap; overflow-wrap: anywhere; }
  .sen { margin-left: auto; background: #2f6fed; color: #fff;
         border-bottom-right-radius: 4px; }
  .bot { background: #fff; border: 1px solid #8883; border-bottom-left-radius: 4px; }
  @media (prefers-color-scheme: dark) { .bot { background: #1d2027; } }
  .bot.disi { border-style: dashed; opacity: .85; }
  .not { font-size: 12.5px; opacity: .6; margin: -6px 0 10px; }
  details { margin-top: 9px; font-size: 13.5px; }
  summary { cursor: pointer; opacity: .7; }
  details ol { margin: 8px 0 0; padding-left: 22px; }
  details li { margin-bottom: 7px; }
  details a { color: inherit; }
  .tip { font-size: 11.5px; opacity: .6; }
  footer { position: fixed; bottom: 0; left: 0; right: 0; padding: 14px 20px;
           background: inherit; border-top: 1px solid #8883; }
  form { max-width: 780px; margin: 0 auto; display: flex; gap: 10px; }
  input { flex: 1; font: inherit; padding: 11px 14px; border-radius: 10px;
          border: 1px solid #8886; background: #fff; color: inherit; }
  @media (prefers-color-scheme: dark) { input { background: #1d2027; } }
  button.gonder { font: inherit; padding: 11px 22px; border: 0; border-radius: 10px;
                  background: #2f6fed; color: #fff; cursor: pointer; }
  button:disabled { opacity: .5; cursor: default; }
  .bekle { display: flex; align-items: center; gap: 9px; opacity: .75;
           font-size: 14px; margin: 12px 0; }
  .nokta { width: 8px; height: 8px; border-radius: 50%; background: currentColor;
           animation: yanip 1.1s infinite ease-in-out; }
  .nokta:nth-child(2) { animation-delay: .18s }
  .nokta:nth-child(3) { animation-delay: .36s }
  @keyframes yanip { 0%, 70%, 100% { opacity: .25 } 35% { opacity: 1 } }
</style>

<header>
  <b>KTÜN Destek Chatbotu</b>
  <span id="durum">__DURUM__</span>
  <button onclick="temizle()">Sohbeti sıfırla</button>
</header>

<div id="akis"></div>

<footer>
  <form onsubmit="gonder(event)">
    <input id="kutu" autocomplete="off" autofocus
           placeholder="Örn: bölüm başkanı kim">
    <button class="gonder" id="dugme">Sor</button>
  </form>
</footer>

<script>
const akis = document.getElementById("akis");

function kaydir() { window.scrollTo(0, document.body.scrollHeight); }

function balon(sinif, metin) {
  const d = document.createElement("div");
  d.className = "balon " + sinif;
  d.textContent = metin;
  akis.appendChild(d);
  kaydir();
  return d;
}

async function gonder(olay) {
  olay.preventDefault();
  const kutu = document.getElementById("kutu");
  const soru = kutu.value.trim();
  if (!soru) return;

  kutu.value = "";
  document.getElementById("dugme").disabled = true;
  balon("sen", soru);

  // CPU'da soru basina ~1 dakika surebiliyor. Gecen sure sayilmazsa
  // sayfa donmus saniliyor — bu yuzden saniye sayaci gosteriliyor.
  const bekleme = document.createElement("div");
  bekleme.className = "bekle";
  bekleme.innerHTML = '<span class="nokta"></span><span class="nokta"></span>'
                    + '<span class="nokta"></span><span id="sayac">0 sn</span>';
  akis.appendChild(bekleme);
  kaydir();
  const basla = Date.now();
  const sayac = setInterval(() => {
    bekleme.querySelector("#sayac").textContent =
      Math.round((Date.now() - basla) / 1000) + " sn";
  }, 1000);

  try {
    const y = await fetch("/sor", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ soru })
    });
    const v = await y.json();
    clearInterval(sayac);
    bekleme.remove();

    if (v.hata) { balon("bot disi", "HATA: " + v.hata); return; }

    // Takip sorusu yeniden yazildiysa hangi soruyla arandigi gosteriliyor;
    // "peki bolum baskani kim" -> "bolum baskani kim" gibi.
    if (v.arama_sorusu && v.arama_sorusu !== soru) {
      const n = document.createElement("div");
      n.className = "not";
      n.textContent = "arama sorusu: " + v.arama_sorusu;
      akis.appendChild(n);
    }

    const b = balon("bot" + (v.kapsam_disi ? " disi" : ""), v.metin);

    if (v.kaynaklar.length) {
      const d = document.createElement("details");
      d.innerHTML = "<summary>" + v.kaynaklar.length + " kaynak</summary>";
      const ol = document.createElement("ol");
      for (const k of v.kaynaklar) {
        const li = document.createElement("li");
        const a = document.createElement("a");
        a.href = k.url; a.target = "_blank"; a.textContent = k.baslik;
        const t = document.createElement("div");
        t.className = "tip";
        t.textContent = k.tip + " · kosinüs " + k.kosinus;
        li.appendChild(a); li.appendChild(t);
        ol.appendChild(li);
      }
      d.appendChild(ol);
      b.appendChild(d);
    }
    const s = document.createElement("div");
    s.className = "not";
    s.textContent = v.sure + " sn";
    akis.appendChild(s);
    kaydir();
  } catch (e) {
    clearInterval(sayac);
    bekleme.remove();
    balon("bot disi", "Sunucuya ulasilamadi: " + e);
  } finally {
    document.getElementById("dugme").disabled = false;
    kutu.focus();
  }
}

async function temizle() {
  await fetch("/temizle", { method: "POST" });
  akis.innerHTML = "";
  document.getElementById("kutu").focus();
}
</script>
</html>
"""


class Islemci(BaseHTTPRequestHandler):
    def _yolla(self, kod: int, tip: str, govde: bytes) -> None:
        self.send_response(kod)
        self.send_header("Content-Type", tip)
        self.send_header("Content-Length", str(len(govde)))
        self.end_headers()
        self.wfile.write(govde)

    def do_GET(self) -> None:
        if self.path not in ("/", "/index.html"):
            self._yolla(404, "text/plain; charset=utf-8", b"yok")
            return
        durum = f"{BOT.backend.model} · {BOT.retriever.meta['parca_sayisi']} parça"
        sayfa = SAYFA.replace("__DURUM__", html.escape(durum))
        self._yolla(200, "text/html; charset=utf-8", sayfa.encode("utf-8"))

    def do_POST(self) -> None:
        if self.path == "/temizle":
            with KILIT:
                BOT.gecmisi_temizle()
            self._yolla(200, "application/json", b'{"ok":true}')
            return

        if self.path != "/sor":
            self._yolla(404, "text/plain; charset=utf-8", b"yok")
            return

        uzunluk = int(self.headers.get("Content-Length") or 0)
        try:
            soru = json.loads(self.rfile.read(uzunluk)).get("soru", "").strip()
        except (ValueError, UnicodeDecodeError):
            soru = ""
        if not soru:
            self._yolla(400, "application/json", b'{"hata":"bos soru"}')
            return

        basla = time.time()
        try:
            # Kilit: iki sekme ayni anda sorarsa sohbet gecmisi birbirine karisir.
            with KILIT:
                cevap = BOT.sor(soru)
            veri = {
                "metin": cevap.tam_metin(),
                "kapsam_disi": cevap.kapsam_disi,
                "arama_sorusu": cevap.kullanilan_soru,
                "sure": round(time.time() - basla, 1),
                "kaynaklar": [
                    {"baslik": k.title, "url": k.url,
                     "tip": k.doc_type, "kosinus": round(k.kosinus, 3)}
                    for k in cevap.kaynaklar
                ],
            }
        except Exception as hata:                      # noqa: BLE001
            # Sunucu tek soruda comeyecek; hata tarayiciya yaziliyor.
            veri = {"hata": f"{type(hata).__name__}: {hata}"}

        self._yolla(200, "application/json; charset=utf-8",
                    json.dumps(veri, ensure_ascii=False).encode("utf-8"))

    def log_message(self, bicim: str, *args) -> None:
        return          # istek loglari sohbet ciktisini bogmasin


def main() -> int:
    setup_stdout_utf8()

    ayristirici = argparse.ArgumentParser(description="KTUN chatbot — tarayici arayuzu")
    ayristirici.add_argument("--port", type=int, default=8000)
    ayristirici.add_argument("--backend", default="ollama", choices=["ollama", "dummy"])
    ayristirici.add_argument("--model", default=None, help="ollama model adi")
    args = ayristirici.parse_args()

    kontrol = (backend_olustur(args.backend, args.model) if args.model
               else backend_olustur(args.backend))
    hazir, mesaj = kontrol.hazir_mi()
    if not hazir:
        print(f"HATA: {mesaj}")
        print("\nModel olmadan arama zincirini gormek icin:")
        print("  python -m bot.web --backend dummy")
        return 1

    global BOT
    print("Indeks ve model yukleniyor...")
    BOT = Chatbot(args.backend, args.model)

    sunucu = ThreadingHTTPServer(("127.0.0.1", args.port), Islemci)
    print(f"Hazir. Model: {BOT.backend.model} | "
          f"Indeks: {BOT.retriever.meta['parca_sayisi']} parca")
    print(f"\n  http://127.0.0.1:{args.port}\n")
    print("Durdurmak icin Ctrl+C.")
    try:
        sunucu.serve_forever()
    except KeyboardInterrupt:
        print("\nKapatiliyor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
