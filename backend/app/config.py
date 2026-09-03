"""Uygulama ayarlari ve lig konfigurasyonu."""
import json
import os
from dataclasses import dataclass, field

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("BETODDS_DATA", os.path.join(os.path.dirname(BASE_DIR), "data"))
DB_PATH = os.path.join(DATA_DIR, "betodds.db")
LEAGUES_PATH = os.path.join(DATA_DIR, "leagues.json")

SITE = os.environ.get("BETODDS_SITE", "https://betandyou-8229.pro")
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
# verilir: BETODDS_DNS_OVERRIDE="betandyou-8229.pro=185.175.165.255"
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

# ----------------------------------------------------------------- tahmin
# app/predict.py: dort bilesenin agirlikli harmani.
#
# Agirliklar arsiv uzerinde leave-one-out olculerek secildi (n=47).
#
# Etmenler TEK BASINA (MAE):
#   sezon gucu          1.65      <- tek basina en iyi
#   oran beklentisi     1.67
#   form (arsiv)        1.77
#   arsiv ortalamasi    1.93      (hicbir sey kullanmayan taban)
#   benzer oranli mac   2.17      <- tabandan BILE kotu
#
# Dort etmen de aktif olacak sekilde taranan en iyi harman:
#   oran .40 sezon .45 form .10 benzer .05   MAE 1.736   <- varsayilan
# Karsilastirma:
#   benzer'siz (oran .4 sezon .4 form .2)    MAE 1.730
#   benzer .10                               MAE 1.761
#   benzer .25                               MAE 1.818
#   esit dortlu (.25 x4)                     MAE 1.835
#
# MAE'nin standart hatasi ~0.17: yukaridaki farklarin hicbiri istatistiksel
# olarak anlamli degil. 'similar' agirligi arttikca isabet duzenli olarak
# kotulesiyor, bu yuzden taramanin verdigi dusuk degerde birakildi.
PREDICT_WEIGHTS = {
    "odds":    float(os.environ.get("BETODDS_W_ODDS", "0.40")),
    "season":  float(os.environ.get("BETODDS_W_SEASON", "0.45")),
    "form":    float(os.environ.get("BETODDS_W_FORM", "0.10")),
    "similar": float(os.environ.get("BETODDS_W_SIMILAR", "0.05")),
}

# 'similar' bileseni: baslangic oranlarinin (1 ve 2 ayagi) bu araliktaki
# BITEN maclari ornek kabul edilir. Genis pencere ornek sayisini artirir ama
# benzerligi zayiflatir.
PREDICT_GAP = float(os.environ.get("BETODDS_PREDICT_GAP", "0.50"))

# 'season' bileseni: guncelden geriye kac sezon ve guncel sezonun agirligi.
# Tarama: n_prev=10 & w_cur=0.2 -> MAE 1.646; w_cur=1.0 -> 1.823 (guncel
# sezon tek basina az mac oynanmis oldugu icin gurultulu).
PREDICT_SEASONS = int(os.environ.get("BETODDS_PREDICT_SEASONS", "10"))
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
                  "short_name": "5x5 Rush"}),
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
