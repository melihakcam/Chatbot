"""Sistem promptu ve bağlam hazırlama.

TASARIM KARARLARI (hepsi ölçümle şekillendi, bkz. eval/answer_test.py):

1. Bağlam BÜTÇESİ dar (4 parça / ~1100 kelime). 2B model uzun bağlamda dağılıyor.

2. Her parça numaralandırılıp kaynağıyla veriliyor — cevabın hangi sayfadan
   geldiğini gösterebilmek için.

3. Sistem kuralları AYRI bir "system" mesajında gidiyor, kullanıcı mesajına
   gömülmüyor. Instruct modeller böyle eğitiliyor; ham metin olarak gönderince
   talimat takibi bozuluyor.

4. "Bilmiyorum" cevabı için promptta HAZIR CÜMLE YOK, sadece BILGI_YOK etiketi
   var. Sebep: ilk sürümde kaçış cümlesi promptta birebir yazılıydı ve 1.5B
   model onu kopyalamayı en kolay yol olarak seçiyordu — telefon numarası
   bağlamın 1. parçasında apaçık dururken bile "bilgi yok" diyordu (1/8 doğruluk).
   Etiket modelin doğal üretmeyeceği bir dizi olduğu için bu kısayol kapandı.

5. Tarih prompt'a ekleniyor — "son duyuru", "bu dönem" için gerekli.
"""

from datetime import date

# Model bunu yazarsa "cevap bulamadım" demektir. Kullanıcıya bu etiket
# gosterilmez, answer.py duzgun bir cumleyle degistirir.
BILGI_YOK_ETIKETI = "BILGI_YOK"

SISTEM_PROMPTU = f"""Sen Konya Teknik Üniversitesi (KTÜN) öğrenci destek asistanısın.

Sana bir BAGLAM metni ve bir SORU verilecek. Görevin: sorunun cevabını bağlamdan
bulup yazmak.

KURALLAR:
1. Bağlamı baştan sona oku. Cevap ilk parçada olmayabilir, hepsine bak.
2. Telefon, e-posta, tarih, ders kodu, kişi ismi gibi bilgileri bağlamda
   yazdığı gibi AYNEN aktar.
3. Kısa ve net ol, en fazla 4 cümle. Liste isteniyorsa madde madde yaz.
4. Türkçe, resmi ama samimi bir dille yaz.
5. Bağlamda olmayan bilgi ekleme, tahmin yürütme.
6. Bağlamda cevap gerçekten yoksa sadece şunu yaz: {BILGI_YOK_ETIKETI}"""

KAPSAM_DISI_CEVABI = (
    "Ben sadece Konya Teknik Üniversitesi hakkında yardımcı olabilirim. "
    "KTÜN'ün bölümleri, akademik takvimi, dersleri, duyuruları veya iletişim "
    "bilgileri hakkında soru sorabilirsin."
)

# Kapsam kapısı iki farklı durumu ayıramıyordu ve ikisine de yukarıdaki cevabı
# veriyordu: (a) soru gerçekten alakasız ("makarna tarifi ver"), (b) soru
# okulla ilgili ama aranan şey kayıtlarda yok (indekste olmayan bir asistanın
# adı). (b)'ye "sadece KTÜN hakkında yardımcı olabilirim" demek kullanıcıya
# sorusunu yanlış sormuş hissi veriyor — oysa kusur veri kapsamında.
#
# Ayrım sorunun ÖZEL AD içerip içermediğine bakarak yapılıyor: kişi soruları
# neredeyse her zaman bir ada dayanıyor ve alakasız sorular ("bitcoin fiyatı
# kaç") ad içermiyor.
KAYITTA_YOK_CEVABI = (
    "Bu ismi kayıtlarımda bulamadım. Verilerim Bilgisayar ve Bilişim Bilimleri "
    "Fakültesi'nin üç bölümüyle sınırlı (Bilgisayar, Yazılım, Yapay Zeka ve "
    "Makine Öğrenmesi Mühendisliği); aradığın kişi başka bir birimdeyse ya da "
    "sayfası taranmamışsa göremiyorum. ktun.edu.tr üzerinden kontrol edebilirsin."
)

BILGI_YOK_CEVABI = (
    "Bu konuda elimde bilgi yok, ktun.edu.tr üzerinden kontrol edebilirsin."
)

# Bağlam bütçesi. Kelime bazlı çünkü tokenizer'a bağımlı olmak istemiyoruz;
# Türkçe'de kelime başına ~1.6 alt-token, 1100 kelime ≈ 1700 token.
BAGLAM_KELIME_BUTCESI = 1100


def baglam_kur(sonuclar) -> str:
    """Arama sonuçlarını numaralı bağlam metnine çevirir, bütçeyi aşmaz."""
    parcalar = []
    kelime = 0

    for i, s in enumerate(sonuclar, 1):
        metin = s.text.strip()
        metin_kelime = len(metin.split())

        if kelime + metin_kelime > BAGLAM_KELIME_BUTCESI:
            kalan = BAGLAM_KELIME_BUTCESI - kelime
            if kalan < 40:
                break
            metin = " ".join(metin.split()[:kalan]) + " ..."
            metin_kelime = kalan

        baslik = s.title
        if s.published_at:
            baslik += f" ({s.published_at} tarihli)"

        parcalar.append(f"[{i}] {baslik}\n{metin}")
        kelime += metin_kelime

    return "\n\n".join(parcalar)


def prompt_kur(soru: str, sonuclar) -> str:
    """Kullanıcı mesajını kurar. Sistem kuralları ayrı gider (SISTEM_PROMPTU)."""
    bugun = date.today().strftime("%d.%m.%Y")
    return (
        f"Bugünün tarihi: {bugun}\n\n"
        f"--- BAGLAM ---\n{baglam_kur(sonuclar)}\n\n"
        f"--- SORU ---\n{soru}"
    )
