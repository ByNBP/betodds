#!/usr/bin/env python3
"""Toplayicinin kapali oldugu araliktaki maclarin skorlarini arsive aktarir.

    python backend/import_results.py --from "2026-09-30 16:00"            # yazar
    python backend/import_results.py --from "2026-09-30 16:00" --dene     # rapor
    python backend/import_results.py --from ... --to ... --champ 2860561

Kaynak, sitenin kendi sonuc servisi (Sonuclar sayfasi):
    /service-api/result/web/api/v3/games?champId=..&dateFrom=..&dateTo=..
Mac kimligi (id) feed'deki event_id ile ayni; skor "5:1 (5:1)" bicimindedir,
ilk kisim mac sonucu. Turnuva/sezon meta'si bu listede YOK - her yeni mac
icin GetGameZip'ten aliniyor (bitmis macta da SC.S altinda donuyor).

ORAN YOK: site bitmis macin oranlarini siliyor. Bu yuzden yeni eklenen
kayitlar prematch_missed=1 ve source='sonuc' ile isaretlenir.

Var olan kayitlarda yalnizca skor (sitenin kesin sonucu), status='finished'
ve eksik tourney/iteration tamamlanir; oranlara dokunulmaz.
"""
import argparse
import asyncio
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import db                                          # noqa: E402
from app.config import LANG, SITE, load_leagues             # noqa: E402
from app.feed import FeedClient, _headers, _int             # noqa: E402

DAY = 86400


def _ts(s: str) -> int:
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return int(datetime.strptime(s, fmt).timestamp())
        except ValueError:
            pass
    raise argparse.ArgumentTypeError(f"tarih okunamadi: {s!r} (YYYY-AA-GG SS:DD)")


def _score(s: str | None) -> tuple[int | None, int | None]:
    head = (s or "").split(" ", 1)[0]
    h, sep, a = head.partition(":")
    if not sep:
        return None, None
    return _int(h), _int(a)


async def fetch_games(feed: FeedClient, champ_id: int, t0: int, t1: int) -> list[dict]:
    """Sonuc servisini tam gunluk parcalar halinde sorgular.

    Servis gun sinirina oturmayan araligi 400 ile reddediyor (16:00 - 22:40
    olmuyor, 16:00 - 24:00 oluyor); bu yuzden yerel gece yarisindan baslayip
    tam gunler isteniyor, aralik disi maclar burada eleniyor.
    """
    out: dict[int, dict] = {}
    start = int(datetime.fromtimestamp(t0).replace(
        hour=0, minute=0, second=0, microsecond=0).timestamp())
    while start < t1:
        end = start + DAY
        r = await feed._client.get(
            f"{SITE}/service-api/result/web/api/v3/games",
            params=[("champId", champ_id), ("dateFrom", start), ("dateTo", end),
                    ("lng", LANG), ("ref", 50)],
            headers=_headers(f"/{LANG}/results"))
        r.raise_for_status()
        for g in r.json().get("items") or []:
            if t0 <= (g.get("dateStart") or 0) < t1:
                out[int(g["id"])] = g
        start = end
    return sorted(out.values(), key=lambda g: g["dateStart"])


async def meta(feed: FeedClient, event_id: int) -> tuple[int | None, int | None]:
    try:
        game = await feed.game_full(event_id)
    except Exception as ex:                                  # noqa: BLE001
        pass                          # eskimis mac: sezon tablodan bulunur
        return None, None
    sc = (game or {}).get("SC") or {}
    m = {d.get("Key"): d.get("Value") for d in (sc.get("S") or []) if isinstance(d, dict)}
    return _int(m.get("id_tourney")), _int(m.get("iteration"))


def season_by_result(tourney_id: int | None, home: str, away: str,
                     sh: int, sa: int) -> int | None:
    """GetGameZip meta vermezse sezon, eventsstat sezon ozetinden bulunur.

    Her sezonda bir takim cifti evinde bir kez oynuyor; ayni cift + ayni skor
    birden fazla sezonda tutarsa en yenisi alinir (aralik son birkac saat).
    """
    if not tourney_id:
        return None
    with db.session() as con:
        r = con.execute(
            "SELECT MAX(iteration) FROM season_matches WHERE tourney_id=? AND home=? "
            "AND away=? AND score_home=? AND score_away=?",
            (tourney_id, home, away, sh, sa)).fetchone()
    return r[0] if r else None


async def run(t0: int, t1: int, champs: list[int], dry: bool) -> None:
    db.init_db()
    now = int(time.time())
    tourneys = {l.champ_id: l.extra.get("tourney_id") for l in load_leagues()}
    fmt = lambda t: time.strftime("%d.%m %H:%M", time.localtime(t))  # noqa: E731
    async with FeedClient() as feed:
        for champ_id in champs:
            games = await fetch_games(feed, champ_id, t0, t1)
            added = updated = same = skipped = from_table = 0
            for g in games:
                eid = int(g["id"])
                sh, sa = _score(g.get("score"))
                if sh is None:
                    skipped += 1                     # iptal / skorsuz
                    continue
                with db.session() as con:
                    row = con.execute(
                        "SELECT score_home, score_away, status, tourney_id, iteration "
                        "FROM matches WHERE event_id=?", (eid,)).fetchone()
                if row and (row["score_home"], row["score_away"], row["status"]) \
                        == (sh, sa, "finished") and row["iteration"] is not None:
                    same += 1
                    continue
                tid = it = None
                if not row or row["iteration"] is None:
                    tid, it = await meta(feed, eid)
                    await asyncio.sleep(0.2)          # kaynagi yormayalim
                    if it is None:
                        tid = tid or tourneys.get(champ_id)
                        it = season_by_result(tid, g.get("opp1"), g.get("opp2"), sh, sa)
                        from_table += it is not None
                if dry:
                    print(f"  {'guncelle' if row else 'ekle':8} {fmt(g['dateStart'])} "
                          f"{g.get('opp1')} {sh}-{sa} {g.get('opp2')}  sezon {it}")
                    updated += bool(row)
                    added += not row
                    continue
                with db.session() as con:
                    if row:
                        con.execute(
                            "UPDATE matches SET score_home=?, score_away=?, "
                            "status='finished', finished_at=COALESCE(finished_at,?), "
                            "tourney_id=COALESCE(tourney_id,?), "
                            "iteration=COALESCE(iteration,?), last_update=? "
                            "WHERE event_id=?", (sh, sa, now, tid, it, now, eid))
                        updated += 1
                    else:
                        ids1, ids2 = g.get("opp1Ids") or [None], g.get("opp2Ids") or [None]
                        con.execute(
                            "INSERT INTO matches(event_id, champ_id, league_name, start_ts, "
                            "home, away, home_id, away_id, status, score_home, score_away, "
                            "status_text, tourney_id, iteration, first_seen, last_update, "
                            "finished_at, missing, prematch_missed, source) "
                            "VALUES (?,?,?,?,?,?,?,?,'finished',?,?,'',?,?,?,?,?,0,1,'sonuc')",
                            (eid, champ_id, g.get("champName"), g["dateStart"],
                             g.get("opp1"), g.get("opp2"), ids1[0], ids2[0], sh, sa,
                             tid, it, now, now, now))
                        added += 1
            print(f"champ {champ_id}: {len(games)} mac ({fmt(t0)} - {fmt(t1)}) -> "
                  f"{added} yeni, {updated} guncellendi, {same} zaten dogru, "
                  f"{skipped} skorsuz, sezonu tablodan bulunan {from_table}{'  [DENEME - yazilmadi]' if dry else ''}")
    if not dry:
        db.log("info", f"import_results: {fmt(t0)} - {fmt(t1)} arasi skorlar aktarildi")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--from", dest="t0", type=_ts, required=True)
    ap.add_argument("--to", dest="t1", type=_ts, default=int(time.time()))
    ap.add_argument("--champ", type=int, action="append",
                    help="lig (champ_id); verilmezse etkin tum ligler")
    ap.add_argument("--dene", action="store_true", help="yazmadan rapor ver")
    a = ap.parse_args()
    champs = a.champ or [l.champ_id for l in load_leagues() if l.enabled]
    asyncio.run(run(a.t0, a.t1, champs, a.dene))


if __name__ == "__main__":
    main()
