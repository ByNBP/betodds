"""Uygulama ayarlari ve lig konfigurasyonu."""
import json
import os
from dataclasses import dataclass, field

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("BETODDS_DATA", os.path.join(os.path.dirname(BASE_DIR), "data"))
DB_PATH = os.path.join(DATA_DIR, "betodds.db")
LEAGUES_PATH = os.path.join(DATA_DIR, "leagues.json")

SITE = os.environ.get("BETODDS_SITE", "https://betandyou-1268.pro")
STATS_SITE = "https://eventsstat.com"
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

POLL_SECONDS = int(os.environ.get("BETODDS_POLL", "20"))

# Kaynak siteler bazi aglarda DPI/proxy ile filtreleniyor. Gerekirse
# BETODDS_PROXY ile yerel bir proxy'ye yonlendirilir (or. socks5://127.0.0.1:1080).
PROXY = os.environ.get("BETODDS_PROXY") or None
# Araya giren TLS proxy'lerinde sistem CA paketi gerekebilir.
CA_BUNDLE = os.environ.get("BETODDS_CA_BUNDLE") or None
HTTP_TIMEOUT = float(os.environ.get("BETODDS_HTTP_TIMEOUT", "25"))


def _parse_dns_override(raw: str) -> dict[str, str]:
    """'host=ip,host2=ip2' -> {'host': 'ip', ...}"""
    out: dict[str, str] = {}
    for part in (raw or "").split(","):
        part = part.strip()
        if "=" in part:
            host, _, ip = part.partition("=")
            host, ip = host.strip(), ip.strip()
            if host and ip:
                out[host] = ip
    return out


# Sistem DNS'i alan adini ISP'nin engel sunucusuna cozuyorsa gercek IP burada
# verilir: BETODDS_DNS_OVERRIDE="betandyou-1268.pro=185.175.165.255"
DNS_OVERRIDE = _parse_dns_override(os.environ.get("BETODDS_DNS_OVERRIDE", ""))
LANG = os.environ.get("BETODDS_LANG", "tr")
COUNTRY = int(os.environ.get("BETODDS_COUNTRY", "1"))

# Sanal maclarin gercek zamanli suresi - VARSAYILAN. Kendi arsivimizden
# olculdu: 5x5 Rush'ta medyan mac uzunlugu 10.4 dk (n=74) ve atilan golun
# final skora orani 11. dakikada %100'e ulasiyor. Canli macta "kalan gol
# beklentisi" bu sureye gore dogrusal eritilir.
#
# Sure LIGDEN LIGE degisiyor (3x3 medyani 9.4 dk, n=10); ligin kendi degeri
# leagues.json'daki 'extra.match_minutes' ile verilir ve bunu ezer. Aradaki
# 1 dakika, macin ortasinda kalan gol beklentisini ~%10 kaydiriyor.
LIVE_MATCH_MINUTES = float(os.environ.get("BETODDS_MATCH_MINUTES", "11"))

# --- beklenen gol kalibrasyonu ----------------------------------------
# Ham beklenti (market ya da harman) once EXPECT_OFFSET kadar dusurulur,
# sonra ALTINDA kalan en buyuk x.5'e yuvarlanir: 10.17 -> 9.67 -> 9.5,
# 14.60 -> 14.10 -> 13.5.
#
# Yuvarlama tam sayilara DEGIL yalnizca yarimlara yapiliyor: kitabin actigi
# Toplam Gol cizgileri her zaman x.5 (Alt 11.5, Ust 12.5). "14.0" gibi bir
# beklenti hicbir cizgiye karsilik gelmiyor, dolayisiyla "beklenti su cizgiyi
# gecti mi" sorusu da yarim kaliyordu.
#
# EXPECT_STEP izgaranin ARALIGI; hedefler izgaranin ORTA noktalaridir
# (k*STEP + STEP/2). STEP=1.0 -> 0.5, 1.5, 2.5 ... yani x.5 degerleri.
# Yuvarlama bu noktalara AŞAĞI dogru yapilir, en yakinina degil.
# 0 ya da negatif verilirse yuvarlama tamamen kapanir, yalnizca offset iner.
#
# Kural TAHMININ CIKISINA uygulanir, girdilerine degil: harmanin bilesenleri
# ham degerlerle calisir, aksi halde hem bilesene hem harmana uygulanip
# duzeltme iki kez inerdi.
EXPECT_OFFSET = float(os.environ.get("BETODDS_EXPECT_OFFSET", "0.5"))
EXPECT_STEP = float(os.environ.get("BETODDS_EXPECT_STEP", "1.0"))

# ----------------------------------------------------------------- tahmin
# app/predict.py: bes bilesenin agirlikli harmani.
#
# BU AGIRLIKLAR ELLE AYARLANDI (2026-09-04). Asagidaki MAE degerleri, dort
# bilesenli onceki surumde leave-one-out ile OLCULEN degerlerdir; yeni
# agirliklar bir taramanin sonucu DEGIL, tercihtir. Isabetin ne oldugunu
# gormek icin mac detay sayfasindaki "Tahmin nasil olustu" panelinde
# bilesen basina ve harman geneli hata canli hesaplaniyor.
#
# Etmenler TEK BASINA olculen hata (MAE, n=47, dort bilesenli surum):
#   sezon gucu          1.65      <- tek basina en iyi
#   oran beklentisi     1.67
#   form (arsiv)        1.77
#   arsiv ortalamasi    1.93      (hicbir sey kullanmayan taban)
#   benzer oranli mac   2.17      <- tabandan BILE kotu
#   saha etkisi         -         (yeni bilesen, henuz olculmedi)
#
# Onceki varsayilan: oran .40 sezon .45 form .10 benzer .05 -> MAE 1.736.
# 'benzer' agirligi o taramada arttikca isabet duzenli olarak kotulesiyordu
# (.10 -> 1.761, .25 -> 1.818); simdi .25 verildi. MAE'nin standart hatasi
# ~0.17 oldugu icin bu farklarin hicbiri istatistiksel olarak anlamli degil,
# ama beklenti yonu bu.
PREDICT_WEIGHTS = {
    "odds":    float(os.environ.get("BETODDS_W_ODDS", "0.20")),
    "season":  float(os.environ.get("BETODDS_W_SEASON", "0.25")),
    "form":    float(os.environ.get("BETODDS_W_FORM", "0.15")),
    "similar": float(os.environ.get("BETODDS_W_SIMILAR", "0.25")),
    # Saha bazli form: ev sahibi evde, deplasman deplasmanda ne uretiyor.
    "venue":   float(os.environ.get("BETODDS_W_VENUE", "0.15")),
}

# Mac kartinin yanindaki "ayni oranli maclar" kutusu. Bir mac, bu macin iki
# takimindan YALNIZCA biri o macta oynadiysa, o takimin oradaki orani
# buradakine bu kadar yakinsa VE 1/X/2 ayaklarindan en az SAME_ODDS_MIN_LEGS
# tanesi bu kadar yakinsa listeye girer.
SAME_ODDS_GAP = float(os.environ.get("BETODDS_SAME_ODDS_GAP", "0.02"))
# Tutmasi gereken ayak sayisi (1/X/2 uzerinden). Takimin kendi ayagi zaten
# sart oldugu icin 2 demek "kendi ayagi + en az bir tane daha" demek.
SAME_ODDS_MIN_LEGS = int(os.environ.get("BETODDS_SAME_ODDS_MIN_LEGS", "2"))
# Liste en yakin tarihli bu kadar macla sinirli.
SAME_ODDS_LIMIT = int(os.environ.get("BETODDS_SAME_ODDS_LIMIT", "5"))

# --- oran golu ---------------------------------------------------------
# "Bu oranla oynanmis maclarda kac gol oluyor?" Aday mac, EV/DEPLASMAN
# KONUMLARI KORUNARAK bu macin oranlarina yakin fiyatlanmis olmali: ev ayagi
# ev ayagiyla, deplasman ayagi deplasman ayagiyla karsilastirilir. (Takim
# bazli 'ayni oranli maclar' kutusundan farki bu - orada takim hangi tarafta
# olursa olsun kendi ayagindan okunuyor.)
#
# Tolerans olcumu (mevcut arsiv, macin KENDINDEN ONCEKI maclari):
#   ±0.02 -> ort.  3-6 ornek, maclarin %12-21'inde hic ornek yok
#   ±0.05 -> ort. 10-13 ornek, %5-7'sinde yok
#   ±0.10 -> ort. 14-16 ornek, %4'unde yok
# Varsayilan "ayni oran" tanimiyla ayni (SAME_ODDS_GAP): dar tutuluyor,
# cunku genisledikce "ayni oranli mac" baska fiyatli bir mac olmaya basliyor.
ODDS_GOAL_GAP = float(os.environ.get("BETODDS_ODDS_GOAL_GAP", str(SAME_ODDS_GAP)))
# Ortalamaya girecek EN FAZLA mac (en yeniden geriye).
ODDS_GOAL_LIMIT = int(os.environ.get("BETODDS_ODDS_GOAL_LIMIT", "20"))
# Bunlardan ekranda ornek olarak listelenecek mac sayisi.
ODDS_GOAL_SAMPLES = int(os.environ.get("BETODDS_ODDS_GOAL_SAMPLES", "5"))

# Karsilasma gecmisi kutusunda gosterilecek sezon sayisi (eventsstat capraz
# sonuc tablosundan). Bizim arsivimiz yalnizca birkac gunu kapsiyor; gecmis
# sezonlar tek kaynak.
H2H_SEASONS = int(os.environ.get("BETODDS_H2H_SEASONS", "4"))

# Sayfanin tepesinde ozetlenen son biten mac sayisi.
RECENT_FINISHED_LIMIT = int(os.environ.get("BETODDS_RECENT_FINISHED", "5"))

# 'similar' bileseni: baslangic oranlarinin (1 ve 2 ayagi) bu araliktaki
# BITEN maclari ornek kabul edilir. Genis pencere ornek sayisini artirir ama
# benzerligi zayiflatir.
PREDICT_GAP = float(os.environ.get("BETODDS_PREDICT_GAP", "0.50"))

# 'season' bileseni: guncelden geriye kac sezon ve guncel sezonun agirligi.
# Tarama: n_prev=10 & w_cur=0.2 -> MAE 1.646; w_cur=1.0 -> 1.823 (guncel
# sezon tek basina az mac oynanmis oldugu icin gurultulu).
PREDICT_SEASONS = int(os.environ.get("BETODDS_PREDICT_SEASONS", "10"))

# 'similar' havuzu kac sezon geriye baksin. Sanal ligde sezonlar hizli
# donuyor (birkac gunde bir iteration atliyor); eski sezonlarin maclari
# guncel gol profilini artik tarif etmiyor. Sezonu BILINMEYEN maclar havuza
# girmez: son 4 sezonun icinde olduklarini soyleyemeyiz.
PREDICT_POOL_SEASONS = int(os.environ.get("BETODDS_PREDICT_POOL_SEASONS", "4"))

# Mac detayindaki "Benzer oranli maclar" panelinin VARSAYILAN sapma payi.
# PREDICT_GAP'ten (0.50) ayri tutuluyor: o, harmanlanmis tahminin 'similar'
# bileseninin penceresi ve tum listelerde kullaniliyor; burasi ise tek bir
# maca bakarken "gercekten ayni fiyat" demek istedigimiz yer.
#
# Olcum (son 4 sezon havuzu, taraf korunmus eslesme ile):
#   ±0.50 -> ort. 45 (3x3) / 34 (5x5) ornek
#   ±0.05 -> ort.  7 (3x3) /  4 (5x5) ornek  <- dar ama "ayni oran" demek bu
# Kullanici paneldeki kutudan bu degeri her an genisletebiliyor.
SIMILAR_GAP = float(os.environ.get("BETODDS_SIMILAR_GAP", "0.05"))

# Mac detayindaki "Ornekteki maclar" listesinde en fazla kac mac. Liste oran
# uzakligina gore sirali oldugu icin kesilen kisim EN UZAK ornekler olur.
SIMILAR_SAMPLE_LIMIT = int(os.environ.get("BETODDS_SIMILAR_SAMPLE_LIMIT", "50"))
PREDICT_CURRENT_WEIGHT = float(os.environ.get("BETODDS_PREDICT_CUR_W", "0.20"))

# 'form' bileseni buzusme sabiti: w = n/(n+k). Tarama: k=1 -> 1.774,
# k=20 -> 1.899.
PREDICT_FORM_K = float(os.environ.get("BETODDS_PREDICT_FORM_K", "1"))

# Bir mac feed'den bu kadar ardisik poll boyunca kaybolursa bitmis sayilir.
MISSING_TICKS_TO_FINISH = 2

# Skorsuz mac feed'den dustugunde hemen kapatilmaz: baslamamis bir mac gecici
# olarak listeden dusebilir. Ancak baslama saatinin uzerinden bu kadar sure
# gectiyse artik geri gelmeyecektir - skorsuz da olsa kapatilir. Aksi halde
# (or. toplayici maci yakalayip hemen sonra durursa) kayit "yaklasan" listesinde
# kalici olarak asili kalir.
FINISH_GRACE_SECONDS = int(os.environ.get("BETODDS_FINISH_GRACE", "3600"))


@dataclass
class League:
    champ_id: int
    name: str = ""
    slug: str = ""
    enabled: bool = True
    # Sanal sporlar yalnizca virtualSports=true ile listeleniyor; gercek
    # ligler icin bu False olmali.
    virtual: bool = True
    extra: dict = field(default_factory=dict)


DEFAULT_LEAGUES = [
    League(champ_id=2986291, name="FC 26. 5x5 Rush. Süper Lig",
           slug="fc26-5x5-rush-superleague", virtual=True,
           extra={"tourney_id": 149, "match_minutes": 11.0,
                  "short_name": "FC 5x5 Superlig"}),
    League(champ_id=2860561, name="FC 25. 3x3. Konferans Ligi",
           slug="fc25-3x3-conference-league", virtual=True,
           extra={"tourney_id": 129, "match_minutes": 10.0,
                  "short_name": "3x3 Konferans"}),
]


def load_leagues() -> list[League]:
    """data/leagues.json'dan lig listesini okur, yoksa varsayilani yazar."""
    if not os.path.exists(LEAGUES_PATH):
        save_leagues(DEFAULT_LEAGUES)
        return list(DEFAULT_LEAGUES)
    with open(LEAGUES_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    out = []
    for item in raw:
        out.append(League(
            champ_id=int(item["champ_id"]),
            name=item.get("name", ""),
            slug=item.get("slug", ""),
            enabled=bool(item.get("enabled", True)),
            virtual=bool(item.get("virtual", True)),
            extra=item.get("extra") or {},
        ))
    return out


def save_leagues(leagues: list[League]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = LEAGUES_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump([{"champ_id": l.champ_id, "name": l.name, "slug": l.slug,
                    "enabled": l.enabled, "virtual": l.virtual, "extra": l.extra}
                   for l in leagues], f, ensure_ascii=False, indent=2)
    os.replace(tmp, LEAGUES_PATH)
