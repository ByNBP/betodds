#!/usr/bin/env python3
"""'Bülten' PDF ciktilarini arsive aktarir.

    python backend/import_bulletin.py 1.pdf 2.pdf ...        # yazar
    python backend/import_bulletin.py *.pdf --dene           # yazmadan rapor
    python backend/import_bulletin.py b.pdf --champ 2860561  # ligi elle ver

Kaynak, sitenin bitmis mac listesini PDF olarak veren baska bir arac. Bizim
toplayicimizin acik kalan pencerelerini kapatiyor: site bitmis macin
oranlarini siliyor, dolayisiyla o maclar bizim arsivimize hic girmediyse
BASKA hicbir yerden alinamiyor.

GUVENILIRLIK - olculdu, varsayilmadi (bkz. asagidaki secim kurallari):

  Oranlar (MS1/MS0/MS2)  Kesisen 54 macta bizim yakaladigimiz mac oncesi
                         tick ile BIREBIR ayni. Tam guveniliyor.

  Skorlar                242 macin 229'u eventsstat sezon tablosuyla
                         tutuyor, 13'u TUTMUYOR. Tutmayanlarin hepsinde
                         bulten skoru daha dusuk: bulteni ureten arac da
                         bizim gibi yoklama yapiyor ve maci bitmeden
                         yakalayabiliyor. Yani bulten skoru tek basina
                         yeterli degil.

Skor secim sirasi (en guvenilirden en zayifa):

  1. eventsstat sezon tablosu (season_matches) - sitenin kendi sezon ozeti,
     puan durumu averajiyla dogrulanmis. Hangi iterasyona ait oldugu
     asagida parmak iziyle bulunuyor, tahmin edilmiyor.
  2. Bizim saglam kaydimiz (missing=0) - maci feed'de sonuna kadar gorduk.
  3. Bulten.
  4. Bizim eksik kaydimiz (missing>0) - feed'den dusen mac, kismi skor.

Bu sira sadece teorik degil: kesisen 9 uyusmazligin 6'sinda bizim kayit
eksikti (missing=2) ve sezon tablosu bulteni dogruladi; 3'unde bizim kayit
saglamdi ve sezon tablosu BIZI dogruladi.

Uretilen kayitlar:
  * matches      - source='bulten' ile isaretlenir (nereden geldigi kalici)
  * odds_ticks   - phase='scheduled', taken_at=start_ts-1 (mac oncesi 1X2).
                   Kendi tick'imiz varsa DOKUNULMAZ; sadece bosluk doldurur.
  * odds_snapshots yazilmaz - bultende alt/ust market seti yok, dolayisiyla
    bu maclar icin "beklenen gol" hesaplanamaz (Sonuclar sayfasinda '—').

Ayni PDF birden cok kez calistirilabilir: mac kimligi dogal anahtardan
(lig + baslangic + takimlar) turetildigi icin tekrar calistirmak ayni
satirlari gunceller, yenisini uretmez.

'pdftotext' (poppler-utils) gerekir - PDF'i sutun duzenini koruyarak metne
cevirmenin en guvenilir yolu, ve bu betik tek seferlik bir arac oldugu icin
uygulamaya yeni bir Python bagimliligi eklemiyoruz.
"""
import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import db                                    # noqa: E402
from app.config import load_leagues                   # noqa: E402

# Bulten satiri:  DURUM  TARIH  SAAT  EV  DEPLASMAN  SKOR  MS1  MS0  MS2  [TOPLAM]
STATUS_ROW = re.compile(r"^(BITTI|BEKLEYEN|CANLI)\b")
STATUS_MAP = {"BITTI": "finished", "CANLI": "live", "BEKLEYEN": "scheduled"}
# Baslikta lig adi:  "FC 26 · 5x5 Rush Süper Lig"
HEAD_LEAGUE = re.compile(r"(FC\s*\d+\s*[·.]\s*.+?)\s*$")
# Sezon tablosu bir bloga ait sayilsin diye aranan en dusuk uyum. 229/242 =
# %94.6 olculdu; %80 esigi hem bunu rahat geciyor hem de yanlis iterasyona
# rastgele oturmayi (gozlenen en yuksek yanlis uyum ~%3) disarida birakiyor.
FINGERPRINT_MIN = 0.80


# --------------------------------------------------------------- ayristirma
def pdf_lines(path: str) -> list[str]:
    if not shutil.which("pdftotext"):
        sys.exit("pdftotext bulunamadi. Kurulum: sudo apt install poppler-utils")
    out = subprocess.run(["pdftotext", "-layout", path, "-"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"{path}: pdftotext basarisiz - {out.stderr.strip()[:200]}")
    return out.stdout.splitlines()


def parse_pdf(path: str) -> tuple[str | None, list[dict]]:
    """(lig adi, satirlar). Satir: durum/ts/home/away/skor/oranlar."""
    league = None
    rows = []
    for line in pdf_lines(path):
        s = line.strip()
        if league is None and "·" in s and s.startswith("FC"):
            m = HEAD_LEAGUE.match(s)
            if m:
                league = m.group(1).strip()
        if not STATUS_ROW.match(s):
            continue
        # -layout sutunlari 2+ bosluklu ayirir; takim adlarindaki tek
        # bosluklar ("Real Madrid") bu sayede bolunmuyor.
        f = re.split(r"\s{2,}", s)
        if len(f) < 9:
            continue
        try:
            ts = int(datetime.strptime(f"{f[1]} {f[2]}", "%d.%m.%Y %H:%M").timestamp())
        except ValueError:
            continue
        sh = sa = None
        if ":" in f[5]:
            try:
                sh, sa = (int(x) for x in f[5].split(":"))
            except ValueError:
                pass
        rows.append({
            "status": STATUS_MAP.get(f[0], "finished"),
            "ts": ts, "home": f[3], "away": f[4],
            "score": None if sh is None else (sh, sa),
            "odds": tuple(_num(x) for x in f[6:9]),
            "src": os.path.basename(path),
        })
    return league, rows


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _slug(s: str) -> str:
    """Lig adlarini karsilastirmak icin: harf/rakam disi her sey duser.
    'FC 26 · 5x5 Rush Süper Lig' ile 'FC 26. 5x5 Rush. Süper Lig' esitlensin."""
    return re.sub(r"[^0-9a-zçğıöşü]", "", (s or "").lower())


def event_id(champ: int, row: dict) -> int:
    """Dogal anahtardan turetilen kalici kimlik.

    Bultende site'nin event_id'si YOK. NEGATIF uretiyoruz: sitenin kimlikleri
    pozitif ve artiyor (~749 milyon), negatif alan ileride de asla onlarla
    cakismaz. Ayni mac tekrar aktarildiginda ayni kimlik cikar - betik
    yeniden calistirilabilir olsun diye.
    """
    key = f"{champ}|{row['ts']}|{row['home']}|{row['away']}".encode()
    return -(int(hashlib.sha1(key).hexdigest()[:12], 16) % 900_000_000_000)


# ------------------------------------------------------- iterasyon parmak izi
def split_blocks(rows: list[dict]) -> list[list[dict]]:
    """Satirlari sezonlara (iterasyon) boler.

    Bir sezonda her siralı takim cifti YALNIZCA BIR kez oynuyor (20 takim ->
    380 mac). Demek ki ayni cift ikinci kez gorundugunde yeni sezon
    baslamistir - sinir tarihten degil, verinin kendisinden cikiyor.
    """
    blocks: list[list[dict]] = []
    cur: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for r in sorted(rows, key=lambda r: r["ts"]):
        pair = (r["home"], r["away"])
        if pair in seen:
            blocks.append(cur)
            cur, seen = [], set()
        seen.add(pair)
        cur.append(r)
    if cur:
        blocks.append(cur)
    return blocks


def match_iteration(con, tourney: int, block: list[dict]) -> tuple[int | None, float, int]:
    """Blogu sezon tablosundaki bir iterasyona oturtur.

    Skorlarin cogunlugu hangi iterasyonun hucreleriyle tutuyorsa o. Esik
    altinda kalirsa None - o blok icin sezon tablosu kullanilmaz (henuz
    cekilmemis yeni sezon boyle davranir).
    """
    scored = [r for r in block if r["score"]]
    if not scored:
        return None, 0.0, 0
    cells: dict[int, dict[tuple[str, str], tuple[int, int]]] = defaultdict(dict)
    for r in con.execute("SELECT iteration, home, away, score_home, score_away "
                         "FROM season_matches WHERE tourney_id=?", (tourney,)):
        cells[r["iteration"]][(r["home"], r["away"])] = (r["score_home"], r["score_away"])
    best, best_hit = None, 0
    for it, cell in cells.items():
        hit = sum(1 for r in scored if cell.get((r["home"], r["away"])) == r["score"])
        if hit > best_hit:
            best, best_hit = it, hit
    ratio = best_hit / len(scored) if scored else 0.0
    return (best, ratio, len(scored)) if ratio >= FINGERPRINT_MIN else (None, ratio, len(scored))


# ------------------------------------------------------------------ yazma
def run(paths: list[str], champ_arg: int | None, dry: bool) -> None:
    leagues = {l.champ_id: l for l in load_leagues()}

    league_name = None
    rows: dict[tuple[int, str, str], dict] = {}
    for p in paths:
        name, rs = parse_pdf(p)
        league_name = league_name or name
        for r in rs:
            # Ayni mac birden cok PDF'te olabilir (ayni veri, farkli siralama).
            # Skoru olan kayit skorsuz olani ezer.
            key = (r["ts"], r["home"], r["away"])
            old = rows.get(key)
            if old is None or (old["score"] is None and r["score"] is not None):
                rows[key] = r
        print(f"{os.path.basename(p):14} {len(rs):4} satir  ({name})")
    rows_l = sorted(rows.values(), key=lambda r: r["ts"])
    if not rows_l:
        sys.exit("PDF'lerde bulten satiri bulunamadi.")

    # --- lig
    champ = champ_arg
    if champ is None:
        want = _slug(league_name)
        for cid, l in leagues.items():
            if want and want == _slug(l.name):
                champ = cid
                break
    if champ is None:
        sys.exit(f"Lig eslesmedi: {league_name!r}. --champ <id> ile verin.\n"
                 "Tanimli: " + ", ".join(f"{c}={l.name}" for c, l in leagues.items()))
    lg = leagues.get(champ)
    if lg is None:
        sys.exit(f"champ {champ} leagues.json'da yok.")
    tourney = (lg.extra or {}).get("tourney_id")
    print(f"\nlig     : {lg.name} (champ={champ}, tourney={tourney})")
    print(f"benzersiz mac: {len(rows_l)}  "
          f"{datetime.fromtimestamp(rows_l[0]['ts']):%d.%m %H:%M} -> "
          f"{datetime.fromtimestamp(rows_l[-1]['ts']):%d.%m %H:%M}")

    db.init_db()
    with db.session() as con:
        # --- mevcut kayitlar (dogal anahtarla)
        have = {(r["start_ts"], r["home"], r["away"]): dict(r)
                for r in con.execute("SELECT * FROM matches WHERE champ_id=?", (champ,))}
        has_tick = {r["event_id"] for r in con.execute(
            "SELECT DISTINCT event_id FROM odds_ticks WHERE phase='scheduled'")}

        # --- sezon tablosu: her blok hangi iterasyon?
        season: dict[tuple[str, str], tuple[int, int]] = {}
        iter_of: dict[int, int] = {}          # ts -> iteration
        if tourney:
            for block in split_blocks(rows_l):
                it, ratio, n = match_iteration(con, tourney, block)
                span = (f"{datetime.fromtimestamp(block[0]['ts']):%d.%m %H:%M}"
                        f" -> {datetime.fromtimestamp(block[-1]['ts']):%d.%m %H:%M}")
                if it is None:
                    print(f"blok {span}: sezon tablosunda karsiligi yok "
                          f"(en iyi uyum %{ratio * 100:.0f}, {n} skorlu mac)"
                          " - skorlar bultenden alinacak")
                    continue
                print(f"blok {span}: iterasyon {it} (uyum %{ratio * 100:.0f}, "
                      f"{n} skorlu mac)")
                for r in con.execute("SELECT home, away, score_home, score_away "
                                     "FROM season_matches WHERE tourney_id=? AND iteration=?",
                                     (tourney, it)):
                    season[(r["home"], r["away"])] = (r["score_home"], r["score_away"])
                for r in block:
                    iter_of[r["ts"]] = it

        stat = Counter()
        fixes = []
        for r in rows_l:
            key = (r["ts"], r["home"], r["away"])
            cur = have.get(key)
            eid = cur["event_id"] if cur else event_id(champ, r)
            ours = ((cur["score_home"], cur["score_away"])
                    if cur and cur["score_home"] is not None else None)
            ssc = season.get((r["home"], r["away"])) if r["ts"] in iter_of else None

            # skor secimi - dosya basindaki siraya gore
            if ssc is not None:
                score, why = ssc, "sezon"
            elif ours is not None and not cur.get("missing"):
                score, why = ours, "bizim"
            elif r["score"] is not None:
                score, why = r["score"], "bulten"
            else:
                score, why = ours, ("bizim-eksik" if ours else "yok")
            stat[f"skor:{why}"] += 1
            if cur and ours is not None and score is not None and score != ours:
                fixes.append((r, ours, score, why))

            # Gecmis tarihli 'bekleyen'/'canli' satirlar arsive bitmis girer:
            # aksi halde canli ekranda hic bitmeyen hayalet satir olurlar.
            status = "finished" if r["ts"] < time.time() - 3600 else r["status"]

            if not dry:
                if cur:
                    con.execute(
                        "UPDATE matches SET score_home=?, score_away=?, status=?,"
                        " iteration=COALESCE(iteration, ?), last_update=? "
                        "WHERE event_id=?",
                        (score[0] if score else None, score[1] if score else None,
                         status, iter_of.get(r["ts"]), int(time.time()), eid))
                else:
                    con.execute(
                        """INSERT INTO matches(event_id, champ_id, league_name,
                               start_ts, home, away, status, score_home, score_away,
                               tourney_id, iteration, first_seen, last_update, source)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?, 'bulten')
                           ON CONFLICT(event_id) DO UPDATE SET
                               score_home=excluded.score_home,
                               score_away=excluded.score_away,
                               status=excluded.status,
                               last_update=excluded.last_update""",
                        (eid, champ, lg.name, r["ts"], r["home"], r["away"],
                         status, score[0] if score else None,
                         score[1] if score else None, tourney, iter_of.get(r["ts"]),
                         r["ts"], int(time.time())))
            stat["mac:guncellendi" if cur else "mac:yeni"] += 1

            # Mac oncesi 1X2. Kendi yakaladigimiz tick varsa DOKUNMA - o,
            # zamani bilinen gercek bir olcum; bulteninki kapanis degeri.
            o1, ox, o2 = r["odds"]
            if o1 and eid not in has_tick:
                if not dry:
                    con.execute("INSERT OR IGNORE INTO odds_ticks(event_id, taken_at,"
                                " phase, o1, ox, o2) VALUES (?,?, 'scheduled', ?,?,?)",
                                (eid, r["ts"] - 1, o1, ox, o2))
                stat["oran:eklendi"] += 1
            elif o1:
                stat["oran:bizde-var"] += 1

    print("\n--- ozet " + ("(DENEME - yazilmadi) " if dry else "") + "-" * 30)
    for k in sorted(stat):
        print(f"  {k:22} {stat[k]:4}")
    if fixes:
        print(f"\n  mevcut kaydin skoru degisti ({len(fixes)}):")
        for r, old, new, why in fixes:
            print(f"    {datetime.fromtimestamp(r['ts']):%d.%m %H:%M} "
                  f"{r['home'][:18]:18}-{r['away'][:18]:18} "
                  f"{old[0]}:{old[1]} -> {new[0]}:{new[1]}  ({why})")


def main():
    ap = argparse.ArgumentParser(description="Bulten PDF'lerini arsive aktarir")
    ap.add_argument("pdf", nargs="+")
    ap.add_argument("--champ", type=int, default=None,
                    help="lig champ_id (bulten basligindan bulunamazsa)")
    ap.add_argument("--dene", action="store_true", help="yazmadan rapor")
    a = ap.parse_args()
    run(a.pdf, a.champ, a.dene)


if __name__ == "__main__":
    main()
