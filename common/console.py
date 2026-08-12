"""Windows konsolunda Türkçe çıktı için UTF-8 ayarı.

NEDEN VAR:
    Windows'ta Python'un stdout'u varsayılan olarak cp1254 (Türkçe ANSI) kullanır.
    Bu kod sayfası bazı Unicode karakterleri (örn. birleşen nokta U+0307, bazı
    tırnak/tire çeşitleri, emoji) basamaz ve program UnicodeEncodeError ile ÇÖKER.

    Web'den çekilen metinde bu karakterler kaçınılmaz olarak vardır. Chatbot
    cevabı ekrana yazarken çökmesin diye her giriş noktasında bu çağrılır.
"""

import sys


def setup_stdout_utf8() -> None:
    """stdout/stderr'i UTF-8'e çevirir. Basılamayan karakter çökertmez, '?' olur."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass  # yönlendirilmiş/özel stream — dokunma
