"""HTTP API katmani."""
import asyncio
import datetime
import json
import math
import os
import time

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from . import db
from .collector import broadcaster, collector
from .config import (LIVE_MATCH_MINUTES, League, POLL_SECONDS,
                     PREDICT_CURRENT_WEIGHT, PREDICT_FORM_K, PREDICT_GAP,
                     PREDICT_POOL_SEASONS, PREDICT_SEASONS,
                     SIMILAR_GAP, SIMILAR_SAMPLE_LIMIT,
                     PREDICT_WEIGHTS, SAME_ODDS_GAP,
                     SAME_ODDS_MIN_LEGS,
                     SAME_ODDS_LIMIT, H2H_SEASONS,
                     ODDS_GOAL_GAP, ODDS_GOAL_LIMIT, ODDS_GOAL_SAMPLES,
                     RECENT_FINISHED_LIMIT,
                     load_leagues, save_leagues)
from .markets import (HIDDEN_GROUPS, LOST, MAIN_TYPES, OU_GROUP, OU_OVER,
                      OU_UNDER, WON, calibrate_total, goal_expectation,
                      group_label, outcome_label, settle)
from .predict import Predictor, backtest, goal_prediction
from .stats import StatsUnavailable, season_page

router = APIRouter(prefix="/api")


def _rows(sql: str, args: tuple = ()) -> list[dict]:
    with db.session() as con:
        return [dict(r) for r in con.execute(sql, args).fetchall()]


def _row(sql: str, args: tuple = ()) -> dict | None:
    r = _rows(sql, args)
    return r[0] if r else None


# ------------------------------------------------------------------ durum
def _build_id() -> str | None:
    """Servis edilen arayuz paketinin adi, or. 'index-Ct07VQxx.js'.

    Hangi surumun calistigini disaridan gorebilmek icin: eski bir imaj ya da
    eski bir dist klasoru calisiyorsa bu deger de eski kalir. (Windows'ta
    ikinci kurulumdan sonra eski imajin ayakta kalmasi tam olarak bu yuzden
    fark edilmemisti.)
    """
    import re
    from .main import STATIC_DIR
    try:
        with open(os.path.join(STATIC_DIR, "index.html"), encoding="utf-8") as f:
            m = re.search(r'assets/(index-[^"\']+\.js)', f.read())
        return m.group(1) if m else None
    except OSError:
        return None


@router.get("/health")
def health():
    stats = _row("""SELECT
        (SELECT COUNT(*) FROM matches)                             AS matches,
        (SELECT COUNT(*) FROM matches WHERE status='finished')     AS finished,
        (SELECT COUNT(*) FROM odds_snapshots)                      AS snapshots,
        (SELECT COUNT(*) FROM odds_ticks)                          AS ticks,
        (SELECT COUNT(*) FROM season_tables)                       AS season_rows""") or {}
    return {
        "ok": True,
        "build": _build_id(),
        "collector": {
            "running": collector.running,
            "poll_seconds": POLL_SECONDS,
            "last_poll": collector.last_poll,
            "poll_count": collector.poll_count,
            "last_error": collector.last_error,
            "leagues": len(collector.leagues),
            "sse_clients": broadcaster.count,
        },
        "db": stats,
    }


@router.get("/logs")
def logs(limit: int = Query(50, le=500)):
    return _rows("SELECT ts, level, message FROM collector_log "
                 "ORDER BY id DESC LIMIT ?", (limit,))


# ------------------------------------------------------------------ ligler
def _league_tourneys() -> dict[int, int | None]:
    """champ_id -> tourney_id.

    Kaynak sirasi: leagues.json'daki 'extra.tourney_id' ipucu, uzerine feed'den
    ogrenilen gercek deger. Ipucu, ligin ilk maci daha yakalanmadan da sezon
    tablosunun (eventsstat) senkronlanabilmesi icin var.
    """
    out: dict[int, int | None] = {}
    for l in load_leagues():
        t = (l.extra or {}).get("tourney_id")
        out[l.champ_id] = int(t) if t else None
    for r in _rows("SELECT champ_id, MAX(tourney_id) AS t FROM matches "
                   "WHERE tourney_id IS NOT NULL GROUP BY champ_id"):
        out[r["champ_id"]] = r["t"]
    return out


@router.get("/leagues")
def leagues():
    cfg = {l.champ_id: l for l in load_leagues()}
    hints = _league_tourneys()
    rows = _rows("""SELECT l.champ_id, l.name, l.slug, l.enabled, l.last_seen,
                           COUNT(m.event_id)                                  AS match_count,
                           SUM(m.status='finished')                           AS finished_count,
                           MAX(m.iteration)                                   AS iteration,
                           MAX(m.tourney_id)                                  AS tourney_id
                    FROM leagues l LEFT JOIN matches m ON m.champ_id = l.champ_id
                    GROUP BY l.champ_id ORDER BY l.name""")
    for r in rows:
        c = cfg.get(r["champ_id"])
        extra = (c.extra if c else None) or {}
        r["virtual"] = bool(c.virtual) if c else True
        # Hic mac yakalanmamis ligde MAX(m.tourney_id) NULL gelir; ipucu devreye girer.
        r["tourney_id"] = r["tourney_id"] or hints.get(r["champ_id"])
        # Sekme etiketi: tam ad ("FC 26. 5x5 Rush. Süper Lig") gezinme
        # cubugunda cok uzun. Verilmemisse tam ada duser.
        r["short_name"] = extra.get("short_name") or r["name"] or str(r["champ_id"])
    return rows


@router.post("/leagues")
def add_league(champ_id: int, name: str = "", slug: str = "", virtual: bool = True):
    items = load_leagues()
    if any(l.champ_id == champ_id for l in items):
        raise HTTPException(409, "bu lig zaten ekli")
    items.append(League(champ_id=champ_id, name=name, slug=slug, virtual=virtual))
    save_leagues(items)
    collector.reload_leagues()
    return {"ok": True, "champ_id": champ_id, "leagues": len(items)}


@router.delete("/leagues/{champ_id}")
def remove_league(champ_id: int):
    items = load_leagues()
    kept = [l for l in items if l.champ_id != champ_id]
    if len(kept) == len(items):
        raise HTTPException(404, "lig bulunamadi")
    save_leagues(kept)
    collector.reload_leagues()
    return {"ok": True, "leagues": len(kept)}


# ------------------------------------------------------------------ maclar
LATEST_ODDS = """
    SELECT t.event_id, t.o1, t.ox, t.o2, t.taken_at
    FROM odds_ticks t
    JOIN (SELECT event_id, MAX(taken_at) AS mx FROM odds_ticks GROUP BY event_id) x
      ON x.event_id = t.event_id AND x.mx = t.taken_at
"""

# Mac oncesi (kickoff) 1X2: mac baslamadan onceki SON tick. LATEST_ODDS bitmis
# bir macta mac ici son orani verir (or. 1.08/6.03/30.0) - bahis oynanabilecek
# oran o degil. Arsiv karsilastirmasinin dayanagi budur.
PREMATCH_ODDS = """
    SELECT t.event_id, t.o1 AS p1, t.ox AS px, t.o2 AS p2, t.taken_at AS prematch_at
    FROM odds_ticks t
    JOIN (SELECT event_id, MAX(taken_at) AS mx FROM odds_ticks
           WHERE phase = 'scheduled' GROUP BY event_id) x
      ON x.event_id = t.event_id AND x.mx = t.taken_at
"""


@router.get("/live")
def live(champ_id: int | None = None):
    """Devam eden ve yaklasan maclar, son bilinen oranlariyla."""
    ch, ca = _champ_clause(champ_id)
    return _rows(f"""
        SELECT m.*, o.o1, o.ox, o.o2, o.taken_at AS odds_at,
               (SELECT COUNT(*) FROM odds_snapshots s WHERE s.event_id=m.event_id) AS has_snapshot,
               (SELECT s.market_count FROM odds_snapshots s
                 WHERE s.event_id=m.event_id AND s.phase='prematch') AS snapshot_markets,
               COALESCE(m.prematch_missed, 0) AS prematch_missed
        FROM matches m LEFT JOIN ({LATEST_ODDS}) o ON o.event_id = m.event_id
        WHERE m.status IN ('live','scheduled'){ch}
        ORDER BY m.start_ts ASC""", ca)


# --------------------------------------------------- toplam gol (alt/ust)
def _totals_by_event(event_ids: list[int]) -> dict[int, dict[float, dict]]:
    """event_id -> {cizgi: {'over': oran, 'under': oran}}

    Referans set 'prekickoff'; yoksa acilis seti 'prematch'e duseriz - mac
    bittikten sonra site oranlari sildigi icin baska kaynak yok.
    """
    from .collector import PHASE_OPEN, PHASE_REF
    if not event_ids:
        return {}
    marks = ",".join("?" * len(event_ids))
    order = {PHASE_REF: 0, PHASE_OPEN: 1}
    chosen: dict[int, int] = {}
    rank: dict[int, int] = {}
    for r in _rows(f"SELECT event_id, id, phase FROM odds_snapshots "
                   f"WHERE event_id IN ({marks})", tuple(event_ids)):
        pr = order.get(r["phase"], 9)
        if r["event_id"] not in chosen or pr < rank[r["event_id"]]:
            chosen[r["event_id"]], rank[r["event_id"]] = r["id"], pr
    if not chosen:
        return {}

    by_snap = {sid: eid for eid, sid in chosen.items()}
    marks = ",".join("?" * len(by_snap))
    out: dict[int, dict[float, dict]] = {}
    for v in _rows(f"SELECT snapshot_id, t, p, coef FROM odds_values "
                   f"WHERE snapshot_id IN ({marks}) AND g = ? AND blocked = 0",
                   tuple(by_snap) + (OU_GROUP,)):
        if v["p"] is None or v["coef"] is None:
            continue
        line = out.setdefault(by_snap[v["snapshot_id"]], {}).setdefault(v["p"], {})
        line["over" if v["t"] == OU_OVER else "under"] = v["coef"]
    return out


def _hit_lines(lines: dict[float, dict], total: int) -> dict:
    """Skor belli olduktan sonra hangi alt/ust cizgileri tutmus.

    Alt {p} toplam < p ise, Ust {p} toplam > p ise kazanir (esitlik iade, ama
    cizgiler .5 oldugu icin pratikte olmuyor).
    Dort ucun da hesaplanmasinin sebebi: hangi ikisinin gosterilecegi ekrana
    gore degisiyor. Arsiv tablosu 'ilk tutan alt' + 'en ust tutan'i, mac
    kartinin yanindaki gecmis kutusu 'ilk tutan alt' + 'ilk tutan ust'u
    gosteriyor.

      ilk tutan alt  = tutan alt cizgilerin EN DUSUGU (toplama en yakin ust sinir)
      son tutan alt  = tutan alt cizgilerin EN YUKSEGI (kitabin tavani)
      ilk tutan ust  = tutan ust cizgilerin EN DUSUGU (kitabin actigi en dusuk
                       ust - neredeyse her mac tutar, oran tabanini gosterir)
      en ust tutan   = tutan ust cizgilerin EN YUKSEGI (toplamin altindaki en buyuk)
    """
    unders = sorted(p for p, o in lines.items() if "under" in o and total < p)
    overs = sorted(p for p, o in lines.items() if "over" in o and total > p)
    res = dict(_EMPTY_HIT)
    if unders:
        res["under_first"] = unders[0]
        res["under_first_odd"] = lines[unders[0]].get("under")
        res["under_last"] = unders[-1]
        res["under_last_odd"] = lines[unders[-1]].get("under")
    if overs:
        res["over_first"] = overs[0]
        res["over_first_odd"] = lines[overs[0]].get("over")
        res["over_top"] = overs[-1]
        res["over_top_odd"] = lines[overs[-1]].get("over")
    return res


_EMPTY_HIT = {"under_first": None, "under_first_odd": None,
              "under_last": None, "under_last_odd": None,
              "over_first": None, "over_first_odd": None,
              "over_top": None, "over_top_odd": None}

_EMPTY_BOOK = {"book_over_last": None, "book_over_last_odd": None,
               "book_over_first": None, "book_over_first_odd": None,
               "book_under_first": None, "book_under_first_odd": None}


def _book_lines(lines: dict[float, dict]) -> dict:
    """Kitabin ACTIGI merdivenin iki ucu - skordan BAGIMSIZ.

    _hit_lines'tan farki: orada uclar skora gore (hangi cizgi tuttu)
    belirleniyor, burada kitabin teklif ettigi araligin ta kendisi:

      son ust  = en YUKSEK cizginin Ust bacagi  (merdivenin tavani,
                 en uzun oran - "toplam bu kadari da gecer mi")
      ilk ust  = en DUSUK cizginin Ust bacagi   (merdivenin tabani,
                 en kisa oran - "toplam bu esigi gecer mi"; neredeyse her
                 mac tutar, tabloda oran TABANINI gosterir)
      ilk alt  = en DUSUK cizginin Alt bacagi   (merdivenin tabani,
                 en uzun oran - "toplam bu kadarin altinda kalir mi")

    Skora ihtiyac duymadigi icin mac baslamadan da hesaplanabilir; su an
    yalnizca biten maclarin gectigi yollarda (_enrich_finished, /matches,
    /coverage) doluyor - /live bu hesabi hic yapmiyor.
    Askiya alinmis (blocked) bacaklar _totals_by_event'te zaten eleniyor,
    yani uclar GERCEKTEN oynanabilir olan cizgiler.
    """
    res = dict(_EMPTY_BOOK)
    overs = sorted(p for p, o in lines.items() if o.get("over") is not None)
    unders = sorted(p for p, o in lines.items() if o.get("under") is not None)
    if overs:
        res["book_over_last"] = overs[-1]
        res["book_over_last_odd"] = lines[overs[-1]]["over"]
        res["book_over_first"] = overs[0]
        res["book_over_first_odd"] = lines[overs[0]]["over"]
    if unders:
        res["book_under_first"] = unders[0]
        res["book_under_first_odd"] = lines[unders[0]]["under"]
    return res


def _attach_totals(rows: list[dict]) -> None:
    """Her maca alt/ust cizgilerini ekler.

    Iki grup: kitabin uclari (arsiv varsa yeter) ve tutan uclar (skor da
    gerekir). Sorgu artik SKORSUZ maclari da kapsiyor: kitabin uclari mac
    baslamadan da anlamli, cagiran uc skorsuz satir verirse onlar da dolar.
    """
    totals = _totals_by_event([r["event_id"] for r in rows])
    for r in rows:
        lines = totals.get(r["event_id"])
        r.update(_book_lines(lines) if lines else _EMPTY_BOOK)
        if lines and r.get("score_home") is not None \
                 and r.get("score_away") is not None:
            r.update(_hit_lines(lines, r["score_home"] + r["score_away"]))
        else:
            r.update(_EMPTY_HIT)


def _team_clause(team, side, opp):
    """Takim aramasinin WHERE parcasi - ev sahibi/deplasman ayrimiyla.

    side: 'home' -> takim yalnizca EVINDE, 'away' -> yalnizca DEPLASMANDA,
    bos -> iki taraf da. opp verilirse RAKIP de suzulur; taraf secilmemisse
    eslesme iki yonlu olur (A evinde B'ye karsi VEYA B evinde A'ya karsi) -
    aksi halde "A ile B'nin maclari" sorusu yarim cevaplanirdi.
    """
    # Yalniz rakip girilmisse onu takim gibi ele al: aramanin tarafi ters doner.
    if not team and opp:
        team, opp = opp, None
        side = {"home": "away", "away": "home"}.get(side, side)
    if not team:
        return None, []
    t, o = f"%{team}%", f"%{opp}%" if opp else None
    if side == "home":
        return ("m.home LIKE ? AND m.away LIKE ?", [t, o]) if o else ("m.home LIKE ?", [t])
    if side == "away":
        return ("m.away LIKE ? AND m.home LIKE ?", [t, o]) if o else ("m.away LIKE ?", [t])
    if o:
        return ("((m.home LIKE ? AND m.away LIKE ?) OR (m.away LIKE ? AND m.home LIKE ?))",
                [t, o, t, o])
    return "(m.home LIKE ? OR m.away LIKE ?)", [t, t]


def _day_start(day: str) -> int:
    """'YYYY-MM-DD' -> o gunun YEREL saatle basladigi an (unix saniye).

    start_ts yerel saate gore yorumlaniyor: kullanici takvimden 5 Eylul
    secince 5 Eylul 00:00'dan 6 Eylul 00:00'a kadar oynanan maclari bekler,
    UTC'ye kayan bir aralik degil.
    """
    try:
        d = datetime.date.fromisoformat(day)
    except ValueError:
        raise HTTPException(422, f"tarih 'YYYY-AA-GG' olmali: {day}")
    return int(datetime.datetime.combine(d, datetime.time.min).timestamp())


def _match_filter(champ_id, status, team, o1, ox, o2, gap, side=None, opp=None,
                  date_from=None, date_to=None):
    """/matches, /matches/stats ve /results icin ortak WHERE kurulumu.

    Oran filtresi mac ONCESI 1X2 (p.p1/px/p2) uzerinden calisir; girilmeyen
    taraf serbest kalir. `dist` girilen oranlara toplam mutlak uzakliktir.

    date_from/date_to gun bazinda ve IKI UCU DA DAHIL: date_to verilen gunun
    sonuna kadar (ertesi gunun basi haric) sayilir, yoksa "9 Eylul"u secen
    kullanici o gunku hicbir maci goremezdi.
    """
    where, args = ["1=1"], []
    if date_from:
        where.append("m.start_ts >= ?"); args.append(_day_start(date_from))
    if date_to:
        where.append("m.start_ts < ?"); args.append(_day_start(date_to) + 86400)
    if champ_id is not None:
        where.append("m.champ_id = ?"); args.append(champ_id)
    if status:
        where.append("m.status = ?"); args.append(status)
    clause, cargs = _team_clause(team, side, opp)
    if clause:
        where.append(clause); args += cargs

    wanted = [(c, v) for c, v in (("p.p1", o1), ("p.px", ox), ("p.p2", o2))
              if v is not None]
    # Uzaklik SELECT'te, filtre WHERE'de: parametre sirasi bu yuzden ayri.
    dist = " + ".join(f"ABS({c} - ?)" for c, _ in wanted) if wanted else "NULL"
    select_args = [v for _, v in wanted]
    for col, val in wanted:
        where.append(f"{col} IS NOT NULL AND ABS({col} - ?) <= ?")
        args += [val, gap]
    return " AND ".join(where), select_args, args, dist, bool(wanted)


@router.get("/matches")
def matches(champ_id: int | None = None, status: str | None = None,
            team: str | None = None,
            o1: float | None = None, ox: float | None = None,
            o2: float | None = None, gap: float = Query(0.25, gt=0),
            limit: int = Query(50, le=500), offset: int = 0):
    """Arsiv listesi.

    o1/ox/o2 verilirse mac oncesi 1X2 orani her biri icin +/- gap araliginda
    olan maclar dondurulur. Sonuc `odds_dist`e gore siralanir.
    """
    where, select_args, args, dist, wanted = _match_filter(
        champ_id, status, team, o1, ox, o2, gap)
    order = "odds_dist ASC, m.start_ts DESC" if wanted else "m.start_ts DESC"

    rows = _rows(f"""
        SELECT m.*, o.o1, o.ox, o.o2, p.p1, p.px, p.p2,
               {dist} AS odds_dist,
               (SELECT COUNT(*) FROM odds_snapshots s WHERE s.event_id=m.event_id) AS has_snapshot,
               (SELECT s.market_count FROM odds_snapshots s
                 WHERE s.event_id=m.event_id AND s.phase='prematch') AS snapshot_markets,
               COALESCE(m.prematch_missed, 0) AS prematch_missed
        FROM matches m LEFT JOIN ({LATEST_ODDS}) o ON o.event_id = m.event_id
                       LEFT JOIN ({PREMATCH_ODDS}) p ON p.event_id = m.event_id
        WHERE {where}
        ORDER BY {order} LIMIT ? OFFSET ?""",
                 tuple(select_args + args + [limit, offset]))
    _attach_totals(rows)
    return rows


@router.get("/matches/stats")
def matches_stats(champ_id: int | None = None, status: str | None = None,
                  team: str | None = None,
                  o1: float | None = None, ox: float | None = None,
                  o2: float | None = None, gap: float = Query(0.25, gt=0)):
    """/matches ile AYNI filtreye giren maclarin gol ve alt/ust ozeti.

    Limit yok: ozet, tabloda gosterilen ilk N kaydin degil filtrenin tamaminin
    ustunden hesaplanir.
    """
    # dist SELECT'e girmiyor -> select_args da gonderilmez (yalnizca WHERE args).
    where, _select_args, args, _dist, _wanted = _match_filter(
        champ_id, status, team, o1, ox, o2, gap)
    rows = _rows(f"""
        SELECT m.event_id, m.score_home, m.score_away
        FROM matches m LEFT JOIN ({LATEST_ODDS}) o ON o.event_id = m.event_id
                       LEFT JOIN ({PREMATCH_ODDS}) p ON p.event_id = m.event_id
        WHERE {where}""", tuple(args))

    scored = [r for r in rows
              if r["score_home"] is not None and r["score_away"] is not None]
    out = {"matches": len(rows), "scored": len(scored), "archived": 0,
           "goals": None, "under_first": [], "over_top": [],
           "under_first_avg": None, "over_top_avg": None,
           "no_under": 0, "no_over": 0, "common_lines": []}
    if not scored:
        return out

    def agg(vals):
        return {"min": min(vals), "max": max(vals),
                "avg": round(sum(vals) / len(vals), 2)}

    home = [r["score_home"] for r in scored]
    away = [r["score_away"] for r in scored]
    out["goals"] = {"home": agg(home), "away": agg(away),
                    "total": agg([h + a for h, a in zip(home, away)])}

    totals = _totals_by_event([r["event_id"] for r in scored])
    out["archived"] = len(totals)
    under_hits: dict[float, int] = {}
    over_hits: dict[float, int] = {}
    # Ortak cizgi = arsivi olan TUM maclarda bulunan cizgi.
    common: set[float] | None = None
    sums: dict[float, dict[str, list[float]]] = {}

    for r in scored:
        lines = totals.get(r["event_id"])
        if not lines:
            continue
        hit = _hit_lines(lines, r["score_home"] + r["score_away"])
        if hit["under_first"] is None:
            out["no_under"] += 1
        else:
            under_hits[hit["under_first"]] = under_hits.get(hit["under_first"], 0) + 1
        if hit["over_top"] is None:
            out["no_over"] += 1
        else:
            over_hits[hit["over_top"]] = over_hits.get(hit["over_top"], 0) + 1

        have = {p for p, o in lines.items() if "over" in o and "under" in o}
        common = have if common is None else (common & have)
        for p, o in lines.items():
            b = sums.setdefault(p, {"over": [], "under": [], "won": {}})
            for side in ("over", "under"):
                if side in o:
                    b[side].append(o[side])
            # Cizgiyi hangi taraf gotururdu: settle() tek dogruluk kaynagi.
            res = settle(OU_GROUP, OU_OVER, p, r["score_home"], r["score_away"])
            key = {WON: "over", LOST: "under"}.get(res, "push")
            b["won"][key] = b["won"].get(key, 0) + 1

    def dist_rows(hits):
        return [{"line": p, "count": n} for p, n in sorted(hits.items())]

    out["under_first"] = dist_rows(under_hits)
    out["over_top"] = dist_rows(over_hits)
    for key, hits in (("under_first_avg", under_hits), ("over_top_avg", over_hits)):
        n = sum(hits.values())
        if n:
            out[key] = round(sum(p * c for p, c in hits.items()) / n, 2)

    for p in sorted(common or ()):
        b = sums[p]
        won = b["won"]
        out["common_lines"].append({
            "line": p,
            "over_avg": round(sum(b["over"]) / len(b["over"]), 3),
            "under_avg": round(sum(b["under"]) / len(b["under"]), 3),
            "matches": len(b["over"]),
            "over_won": won.get("over", 0),
            "under_won": won.get("under", 0),
            "push": won.get("push", 0),
        })
    return out


@router.get("/matches/{event_id}")
def match_detail(event_id: int):
    m = _row(f"""SELECT m.*, p.p1, p.px, p.p2
                 FROM matches m LEFT JOIN ({PREMATCH_ODDS}) p
                   ON p.event_id = m.event_id
                 WHERE m.event_id = ?""", (event_id,))
    if not m:
        raise HTTPException(404, "mac bulunamadi")
    m["snapshots"] = _rows("SELECT id, taken_at, phase, market_count FROM odds_snapshots "
                           "WHERE event_id=? ORDER BY taken_at", (event_id,))
    m["tick_count"] = (_row("SELECT COUNT(*) c FROM odds_ticks WHERE event_id=?",
                            (event_id,)) or {}).get("c", 0)

    # Gol beklentisi + hesabin dayandigi doneler. Liste tablosundakiyle ayni
    # snapshot kullanilir; detay=True yalnizca kirilimi ekler, sayilari degil.
    from .collector import PHASE_REF
    snap = _expectation_snapshot(event_id)
    e = goal_expectation(
        _rows("SELECT g, t, p, coef, blocked FROM odds_values WHERE snapshot_id=?",
              (snap["id"],)), detail=True) if snap else None
    if e:
        _apply_remaining(e, m, time.time(),
                         _league_match_minutes().get(m.get("champ_id"),
                                                     LIVE_MATCH_MINUTES))
        e["snapshot"] = {
            "phase": snap["phase"],
            "taken_at": snap["taken_at"],
            "market_count": snap["market_count"],
            "is_reference": snap["phase"] == PHASE_REF,
            "seconds_before_kickoff": (m["start_ts"] - snap["taken_at"])
                                      if m.get("start_ts") else None,
        }
    m["expect"] = e

    # Harmanlanmis tahmin + her bilesenin tek basina isabeti. Bu uc pahali
    # oldugu icin (havuzun tamami icin oran beklentisi) yalnizca tek mac
    # goruntulenirken hesaplanir, liste uclarinda degil.
    pred = _predictor(m.get("champ_id"))
    m["predict"] = pred.predict(m, exclude=event_id, detail=True)
    if m["predict"]:
        exps = _pool_expectations(pred.pool)
        m["predict"]["accuracy"] = pred.accuracy(exps)
        m["predict"]["component_accuracy"] = pred.component_accuracy(exps)
    return m


@router.get("/matches/{event_id}/similar")
def match_similar(event_id: int, gap: float = Query(SIMILAR_GAP, gt=0, le=5)):
    """Baslangic oranlari bu maca yakin olan BITEN maclar + gol tahmini.

    Ornek kumesi iki kez daraltilir:
      1) TARAF KORUNARAK takim eslesmesi: bu macin ev sahibi o macta da EVDE
         olmali ya da deplasman takimi orada da DEPLASMANDA. Ev sahipligi gol
         uretimini degistirdigi icin takimi ters tarafta gormek "ayni durum"
         sayilmiyor,
      2) oran uzakligina gore en yakin SIMILAR_SAMPLE_LIMIT tanesi.

    Pencere `gap` ile daraltilip genisletilebilir; varsayilan SIMILAR_GAP.
    Mac kendisi ornekten cikarilir (bitmis bir maci kendi tahmininde saymak
    isabeti yapay olarak yukseltirdi).

    Isabet olcumu (`accuracy`) TUM havuz uzerinden kalir: o, yontemin
    arsivdeki genel isabetini anlatiyor, bu iki takimin maclarini degil.
    """
    m = _row(f"""SELECT m.event_id, m.champ_id, m.home, m.away, m.status, m.start_ts,
                        m.score_home, m.score_away, p.p1, p.px, p.p2
                 FROM matches m LEFT JOIN ({PREMATCH_ODDS}) p
                   ON p.event_id = m.event_id
                 WHERE m.event_id = ?""", (event_id,))
    if not m:
        raise HTTPException(404, "mac bulunamadi")
    if m["p1"] is None or m["p2"] is None:
        raise HTTPException(404, "bu macin mac oncesi 1X2 orani arsivde yok")

    # Benzerlik yalnizca AYNI lig icinde anlamli: format degisince ayni oran
    # apayri bir gol beklentisine karsilik geliyor.
    pool = _prediction_pool(m["champ_id"])
    # Taraf korunur: ev sahibimiz evde YA DA deplasmanimiz deplasmanda.
    kendi = [r for r in pool
             if r["home"] == m["home"] or r["away"] == m["away"]]
    pred = goal_prediction(m["p1"], m["p2"], kendi, gap, exclude=event_id,
                           detail=True, limit=SIMILAR_SAMPLE_LIMIT)
    pred["accuracy"] = backtest(pool, gap)
    pred["pool"] = len(kendi)
    pred["pool_all"] = len(pool)
    # Hangi sezonlarin sayildigi ekranda yaziyor: ornek kumesi daraldiginda
    # sebebi gorunur olmali.
    pred["seasons"] = sorted({r["iteration"] for r in pool
                              if r.get("iteration") is not None}, reverse=True)
    return {"event_id": event_id, "home": m["home"], "away": m["away"],
            "p1": m["p1"], "px": m["px"], "p2": m["p2"], "predict": pred}


@router.get("/matches/{event_id}/odds")
def match_odds(event_id: int, phase: str = "auto"):
    """Referans oran seti + mac bittiyse hangi seceneklerin tuttugu.

    Gecerli oranlar macin BASLAMASINDAN hemen onceki settir ('prekickoff').
    Mac ici oran degisimi referans degildir. Referans set yoksa acilis setine
    ('prematch') duseriz ve bunu yanitta belirtiriz.
    """
    from .collector import PHASE_OPEN, PHASE_REF

    available = _rows("SELECT phase, taken_at, market_count FROM odds_snapshots "
                      "WHERE event_id=? ORDER BY taken_at", (event_id,))
    if not available:
        raise HTTPException(404, "bu mac icin arsiv yok "
                                 "(oranlar ancak mac oncesi yakalanabiliyor)")
    by_phase = {a["phase"]: a for a in available}
    if phase == "auto":
        chosen = by_phase.get(PHASE_REF) or by_phase.get(PHASE_OPEN) or available[-1]
    elif phase in by_phase:
        chosen = by_phase[phase]
    else:
        raise HTTPException(404, f"'{phase}' fazi icin arsiv yok")

    snap = _row("SELECT * FROM odds_snapshots WHERE event_id=? AND phase=?",
                (event_id, chosen["phase"]))
    match = _row("SELECT start_ts, status, score_home, score_away, home, away "
                 "FROM matches WHERE event_id=?", (event_id,)) or {}
    sh, sa = match.get("score_home"), match.get("score_away")
    settled = match.get("status") == "finished" and sh is not None

    # HIDDEN_GROUPS burada eleniyor - sonuclandirma sayaci (tally) da bu
    # pazarlari saymasin diye sorgunun hemen ardindan, tek yerde.
    vals = [v for v in _rows("SELECT g, gs, t, p, coef, blocked FROM odds_values "
                             "WHERE snapshot_id=? ORDER BY g, t, p", (snap["id"],))
            if v["g"] not in HIDDEN_GROUPS]
    tally = {"won": 0, "lost": 0, "void": 0, "unknown": 0}
    groups: dict[int, dict] = {}
    for v in vals:
        result = settle(v["g"], v["t"], v["p"], sh, sa) if settled else None
        if settled:
            tally[result or "unknown"] += 1
        grp = groups.setdefault(v["g"], {"g": v["g"], "label": group_label(v["g"]),
                                         "settleable": None, "outcomes": []})
        grp["outcomes"].append({
            "t": v["t"], "p": v["p"], "coef": v["coef"],
            "blocked": bool(v["blocked"]),
            "label": outcome_label(v["g"], v["t"], v["p"]),
            "result": result,
        })
        if settled and grp["settleable"] is None:
            grp["settleable"] = result is not None

    ordered = sorted(groups.values(), key=lambda x: x["g"])
    winners = [{"group": g["label"], "label": o["label"], "coef": o["coef"]}
               for g in ordered for o in g["outcomes"] if o["result"] == "won"]

    return {
        "event_id": event_id,
        "phase": chosen["phase"],
        "taken_at": snap["taken_at"],
        "seconds_before_kickoff": (match["start_ts"] - snap["taken_at"])
                                  if match.get("start_ts") else None,
        "is_reference": chosen["phase"] == PHASE_REF,
        "available_phases": available,
        "market_count": snap["market_count"],
        "settled": settled,
        "score": {"home": sh, "away": sa} if settled else None,
        "tally": tally if settled else None,
        "winners": winners if settled else None,
        "groups": ordered,
    }


@router.get("/matches/{event_id}/ticks")
def match_ticks(event_id: int, limit: int = Query(2000, le=20000)):
    """Oran hareketi zaman serisi (grafik icin)."""
    return _rows("SELECT taken_at, phase, score_home, score_away, o1, ox, o2 "
                 "FROM odds_ticks WHERE event_id=? ORDER BY taken_at LIMIT ?",
                 (event_id, limit))


# ---------------------------------------------------------------- istatistik
@router.get("/stats/teams")
def team_stats(champ_id: int | None = None):
    """Biten maclardan takim formu (arsivimizden uretilir)."""
    where, args = ["status='finished'", ], []
    if champ_id is not None:
        where.append("champ_id = ?"); args.append(champ_id)
    rows = _rows(f"SELECT home, away, score_home, score_away FROM matches "
                 f"WHERE {' AND '.join(where)} AND score_home IS NOT NULL", tuple(args))
    agg: dict[str, dict] = {}
    for r in rows:
        for team, gf, ga in ((r["home"], r["score_home"], r["score_away"]),
                             (r["away"], r["score_away"], r["score_home"])):
            if not team:
                continue
            a = agg.setdefault(team, {"team": team, "played": 0, "wins": 0,
                                      "draws": 0, "losses": 0, "gf": 0, "ga": 0})
            a["played"] += 1; a["gf"] += gf; a["ga"] += ga
            a["wins"] += gf > ga; a["draws"] += gf == ga; a["losses"] += gf < ga
    out = sorted(agg.values(), key=lambda x: (-x["wins"], x["losses"]))
    for a in out:
        p = a["played"] or 1
        a["points"] = a["wins"] * 3 + a["draws"]
        a["avg_for"] = round(a["gf"] / p, 2)
        a["avg_against"] = round(a["ga"] / p, 2)
        a["avg_total"] = round((a["gf"] + a["ga"]) / p, 2)
    return out


@router.get("/stats/seasons")
def seasons(tourney_id: int, team: str | None = None):
    if team:
        return _rows("SELECT * FROM season_tables WHERE tourney_id=? AND team LIKE ? "
                     "ORDER BY iteration", (tourney_id, f"%{team}%"))
    return _rows("SELECT iteration, COUNT(*) teams, MAX(played) played "
                 "FROM season_tables WHERE tourney_id=? GROUP BY iteration "
                 "ORDER BY iteration DESC", (tourney_id,))


@router.get("/stats/seasons/{iteration}")
def season_detail(tourney_id: int, iteration: int):
    return _rows("SELECT * FROM season_tables WHERE tourney_id=? AND iteration=? "
                 "ORDER BY pos", (tourney_id, iteration))


@router.post("/stats/seasons/sync")
async def sync_seasons(tourney_id: int, start: int, end: int,
                       champ_id: int | None = None):
    """eventsstat'tan sezon tablolarini ceker (var olanlari atlar)."""
    if end < start or end - start > 200:
        raise HTTPException(400, "gecersiz aralik (en fazla 200 sezon)")
    added, skipped, failed, games = 0, 0, [], 0
    for it in range(start, end + 1):
        # Hem puan durumu HEM maclari varsa atla. Sezon maclari sonradan
        # eklendigi icin, yalnizca tablosu olan sezonlar yeniden cekilmeli.
        exists = _row("SELECT 1 FROM season_tables WHERE tourney_id=? AND iteration=? "
                      "AND EXISTS(SELECT 1 FROM season_matches sm "
                      "           WHERE sm.tourney_id=season_tables.tourney_id "
                      "             AND sm.iteration=season_tables.iteration) "
                      "LIMIT 1", (tourney_id, it))
        if exists:
            skipped += 1
            continue
        try:
            page = await season_page(tourney_id, it)
        except (StatsUnavailable, Exception) as ex:    # noqa: BLE001
            failed.append({"iteration": it, "error": str(ex)[:120]})
            continue
        table = page["table"]
        if not table:
            failed.append({"iteration": it, "error": "bos tablo"})
            continue
        now = int(time.time())
        with db.session() as con:
            con.executemany("""INSERT OR REPLACE INTO season_tables
                (champ_id, tourney_id, iteration, team, pos, played, wins, draws,
                 losses, gf, ga, points, fetched_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [(champ_id, tourney_id, it, r["team"], r["pos"], r["played"],
                  r["wins"], r["draws"], r["losses"], r["gf"], r["ga"],
                  r["points"], now) for r in table])
            # Ayni sayfadan cikan capraz sonuc tablosu: sezonun tekil maclari.
            con.executemany("""INSERT OR REPLACE INTO season_matches
                (tourney_id, iteration, home, away, score_home, score_away, fetched_at)
                VALUES (?,?,?,?,?,?,?)""",
                [(tourney_id, it, m["home"], m["away"], m["score_home"],
                  m["score_away"], now) for m in page["matches"]])
            games += len(page["matches"])
        added += 1
        await asyncio.sleep(0.4)          # kaynagi yormayalim
    return {"added": added, "skipped": skipped, "matches": games,
            "failed": failed[:20], "failed_count": len(failed)}



COMPLETE_SNAPSHOT_JOIN = """
    FROM matches m
    LEFT JOIN (
      SELECT s.event_id, s.market_count,
             EXISTS(SELECT 1 FROM odds_values v
                    WHERE v.snapshot_id = s.id AND v.g = 1) AS has_main
      FROM odds_snapshots s WHERE s.phase = 'prematch'
    ) sn ON sn.event_id = m.event_id
"""


def _champ_clause(champ_id: int | None, alias: str = "m") -> tuple[str, tuple]:
    """Lig filtresi: (' AND m.champ_id = ?', (champ_id,)) ya da ('', ())."""
    if champ_id is None:
        return "", ()
    return f" AND {alias}.champ_id = ?", (champ_id,)


def _coverage(champ_id: int | None = None) -> dict:
    """Mac oncesi arsiv kapsamasi.

    Ozeti macin durumundan turetiyoruz, bayraktan degil: toplayici hic
    gormeden bitmis maclar (or. ice aktarilan eski kayitlar) bayrak alamaz
    ama yine de kalici bir aciktir - site bitmis macin oranlarini siliyor.
      pending : henuz baslamamis, hala yakalanabilir
      missed  : baslamis/bitmis ve arsivi yok -> geri kazanilamaz
    """
    from .collector import MIN_PREMATCH_OUTCOMES as MIN
    ch, ca = _champ_clause(champ_id)
    rows = _rows(
        "SELECT m.status, "
        "  CASE WHEN sn.market_count >= ? AND sn.has_main = 1 THEN 1 ELSE 0 END AS ok, "
        "  COUNT(*) AS n"
        + COMPLETE_SNAPSHOT_JOIN +
        f" WHERE 1=1{ch}"
        " GROUP BY m.status, ok", (MIN,) + ca)
    # Referans set = baslangictan hemen onceki. Gecerli oranlar bunlar;
    # acilis seti yalnizca sigorta.
    ref = _row("SELECT COUNT(*) n FROM matches m WHERE EXISTS("
               "  SELECT 1 FROM odds_snapshots s WHERE s.event_id=m.event_id "
               f"  AND s.phase='prekickoff' AND s.market_count >= ?){ch}",
               (MIN,) + ca) or {}
    ref_started = _row("SELECT COUNT(*) n FROM matches m "
                       "WHERE m.status IN ('live','finished') AND EXISTS("
                       "  SELECT 1 FROM odds_snapshots s WHERE s.event_id=m.event_id "
                       f"  AND s.phase='prekickoff' AND s.market_count >= ?){ch}",
                       (MIN,) + ca) or {}
    started = _row("SELECT COUNT(*) n FROM matches m "
                   f"WHERE m.status IN ('live','finished'){ch}", ca) or {}

    listed = sum(r["n"] for r in rows)
    archived = sum(r["n"] for r in rows if r["ok"])
    pending = sum(r["n"] for r in rows
                  if not r["ok"] and r["status"] == "scheduled")
    missed = sum(r["n"] for r in rows
                 if not r["ok"] and r["status"] in ("live", "finished"))
    upcoming = [r for r in rows if r["status"] == "scheduled"]
    return {
        "listed": listed,
        "archived": archived,
        "pending": pending,
        "missed": missed,
        "pct": round(100 * archived / listed, 1) if listed else None,
        "upcoming_listed": sum(r["n"] for r in upcoming),
        "upcoming_archived": sum(r["n"] for r in upcoming if r["ok"]),
        "reference_archived": ref.get("n") or 0,
        "reference_of_started": ref_started.get("n") or 0,
        "started": started.get("n") or 0,
    }


@router.get("/coverage")
def coverage(champ_id: int | None = None, limit: int = Query(100, le=500)):
    """Ozet + tam mac oncesi arsivi olmayan maclarin listesi."""
    from .collector import MIN_PREMATCH_OUTCOMES as MIN
    ch, ca = _champ_clause(champ_id)
    gaps = _rows(
        "SELECT m.event_id, m.home, m.away, m.status, m.start_ts, "
        "  COALESCE(m.prematch_missed, 0) AS prematch_missed, "
        "  sn.market_count AS snapshot_markets, "
        "  CASE WHEN m.status = 'scheduled' THEN 'pending' ELSE 'missed' END AS kind"
        + COMPLETE_SNAPSHOT_JOIN +
        " WHERE (sn.event_id IS NULL OR sn.has_main = 0 OR sn.market_count < ?)"
        + ch +
        " ORDER BY m.start_ts DESC LIMIT ?", (MIN,) + ca + (limit,))
    return {"summary": _coverage(champ_id), "gaps": gaps}


# ------------------------------------------------------------------ pano


# {where} _match_filter'dan gelir (lig, takim/taraf, oran araligi); skor
# sarti burada duruyor cunku "biten mac" sayilmanin kosulu, filtre degil.
FINISHED_SELECT = """
        SELECT m.*, p.p1, p.px, p.p2
        FROM matches m LEFT JOIN ({odds}) p ON p.event_id = m.event_id
        WHERE {where} AND m.score_home IS NOT NULL
        ORDER BY m.start_ts DESC
"""


def _finished_rows(champ_id, team=None, side=None, opp=None,
                   o1=None, ox=None, o2=None, gap=0.25, limit=None,
                   date_from=None, date_to=None):
    """Biten maclari filtreleyip sonuc tablosunun alanlariyla tamamlar."""
    where, _sa, args, _d, _w = _match_filter(
        champ_id, "finished", team, o1, ox, o2, gap, side, opp,
        date_from, date_to)
    sql = FINISHED_SELECT.format(odds=PREMATCH_ODDS, where=where)
    if limit is not None:
        sql += " LIMIT ?"
        args = args + [limit]
    rows = _rows(sql, tuple(args))
    _enrich_finished(rows)
    return rows


def _enrich_finished(rows: list[dict]) -> None:
    """Biten mac satirlarini sonuc tablosunun gosterdigi alanlarla tamamlar.

    Hem panonun tepesindeki ozet hem Sonuclar sayfasi ayni sutunlari
    gosteriyor; hesap tek yerde.
    """
    if not rows:
        return
    _attach_totals(rows)             # kitabin uclari + tutan cizgiler
    _attach_expectations(rows)       # mac oncesi gol beklentisi
    _attach_odds_goals(rows)         # ayni oranli son maclardan "oran golu"
    for row in rows:
        row["total"] = row["score_home"] + row["score_away"]
        e = row.get("expect") or {}
        # "Beklenen gol tuttu" olcutu: gercek toplam beklentinin USTUNDE.
        # Yani beklenti bir tahmin degil, ALT SINIR gibi okunuyor - "en az bu
        # kadar gol" bekleniyordu, oldu mu?
        row["expect_hit"] = (e.get("total") is not None
                             and row["total"] > e["total"])


def _recent_finished(champ_id: int | None,
                     limit: int = RECENT_FINISHED_LIMIT) -> list[dict]:
    """Son biten maclar - panonun tepesindeki ozet.

    Siralama macin OYNANDIGI ana (start_ts) gore, kapandigi ana gore degil.
    finished_at iki nedenle bozuk bir siralama uretiyordu: feed'den dusen mac
    saatler sonra kapaniyor (49 kayitta 1 saatten fazla fark var) ve disaridan
    ice aktarilan kayitlarda alan hic yok. Ikisi karisinca listede tarihler
    ileri geri zipliyordu.
    """
    return _finished_rows(champ_id, limit=limit)


def _rate(hits: int, n: int) -> dict:
    """Tutma orani + PAYDA. Yuzde tek basina yaniltici: 3 macta 2 tutmus
    bir kural %66 gorunur, o yuzden n her zaman yaninda gider."""
    return {"hit": hits, "n": n, "pct": round(100 * hits / n, 1) if n else None}


def _hit_rates(scored: list[dict], counts: dict) -> dict:
    """Sonuclar sayfasindaki tutma oranlari.

    Kume 'hit' filtresinden ONCEKI satirlardir - counts ile ayni. Aksi
    halde "Tuttu"ya basinca oran %100 cikardi.

    Paydalar farkli: beklenti yalnizca mac oncesi arsivi olan maclarda,
    kitap uclari yalnizca o ucu acilmis maclarda olculebilir.

    Iki ust cizgisi de olculuyor: SON ust merdivenin tavani (nadiren tutar,
    uzun oran), ILK ust tabani (cogu mac tutar, oranin tabani). Ikisi birlikte
    kitabin actigi araligin ne kadarinin gerceklestigini anlatiyor.
    """
    last_n = last_hit = first_n = first_hit = 0
    for r in scored:
        tot = r.get("total")
        if tot is None:
            continue
        if r.get("book_over_last") is not None:
            last_n += 1
            last_hit += tot > r["book_over_last"]
        if r.get("book_over_first") is not None:
            first_n += 1
            first_hit += tot > r["book_over_first"]
    return {
        "expect": _rate(counts["hit"], counts["hit"] + counts["miss"]),
        "over_last": _rate(last_hit, last_n),
        "over_first": _rate(first_hit, first_n),
    }


def _finished_span(champ_id: int | None) -> dict:
    """Arsivde biten maclarin ilk/son gunu - tarih kutularinin sinirlari.

    Tarih suzgecinden ETKILENMEZ: secim daraldikca takvimin sinirlari da
    daralsaydi kullanici bir kez sectigi araligin disina cikamazdi.
    """
    row = _row("""SELECT MIN(start_ts) AS lo, MAX(start_ts) AS hi FROM matches m
                   WHERE m.status = 'finished' AND m.score_home IS NOT NULL
                     AND (? IS NULL OR m.champ_id = ?)""",
               (champ_id, champ_id))
    day = lambda ts: datetime.date.fromtimestamp(ts).isoformat()  # noqa: E731
    return {"first": day(row["lo"]), "last": day(row["hi"])} if row and row["lo"] \
        else {"first": None, "last": None}


@router.get("/results")
def results(champ_id: int | None = None, hit: str | None = None,
            team: str | None = None, side: str | None = None,
            opp: str | None = None,
            date_from: str | None = None, date_to: str | None = None,
            o1: float | None = None, ox: float | None = None,
            o2: float | None = None, gap: float = Query(0.25, gt=0),
            limit: int = Query(50, ge=1, le=200), offset: int = 0):
    """Sonuclar sayfasi: biten maclar, panodaki ozetle ayni bicimde.

    Filtreler:
      team + side  takim adi; side 'home'/'away' ile yalnizca evinde ya da
                   deplasmanda oynadigi maclar, bos birakilirsa iki taraf da
      opp          rakip (taraf secilmemisse eslesme iki yonlu)
      date_from/   maçin oynandigi gun araligi (YYYY-AA-GG), iki ucu da dahil
      date_to
      o1/ox/o2     mac oncesi 1X2 orani, her biri icin +/- gap
      hit          'yes' -> toplam gol beklentiyi asanlar
                   'no'  -> beklentisi OLAN ama asmayanlar
                   yok   -> hepsi

    Beklentisi olmayan maclar (mac oncesi arsivi yakalanmamis) hit
    filtrelerinin ikisine de girmez - "tuttu mu" sorusu onlar icin
    cevaplanamiyor. `counts` ve `avg_goals` ise hit DISINDAKI filtrelerin
    tamami uzerinden hesaplanir: secim daraldikca ozet de daralir.

    team/opp/oran suzmesi SQL'de, hit suzmesi Python'da: expect_hit mac
    oncesi snapshot'tan hesaplanan bir deger, SQL'de yok. Bu yuzden once
    SQL daraltir, sonra kalan satirlar zenginlestirilir - filtre girildikce
    istek HIZLANIR.
    """
    rows = _finished_rows(champ_id, team, side, opp, o1, ox, o2, gap,
                          date_from=date_from, date_to=date_to)

    scored = [r for r in rows if (r.get("expect") or {}).get("total") is not None]
    counts = {
        "all": len(rows),
        "hit": sum(1 for r in scored if r["expect_hit"]),
        "miss": sum(1 for r in scored if not r["expect_hit"]),
        "no_expect": len(rows) - len(scored),
    }
    if hit == "yes":
        rows = [r for r in scored if r["expect_hit"]]
    elif hit == "no":
        rows = [r for r in scored if not r["expect_hit"]]

    total = len(rows)
    goals = sum(r["total"] for r in rows)
    page = rows[offset:offset + limit]
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "hit": hit,
        "counts": counts,
        "rates": _hit_rates(scored, counts),
        "filters": {"team": team or "", "side": side or "", "opp": opp or "",
                    "date_from": date_from or "", "date_to": date_to or "",
                    "o1": o1, "ox": ox, "o2": o2, "gap": gap},
        "date_range": _finished_span(champ_id),
        "avg_goals": round(goals / total, 2) if total else None,
        "matches": page,
    }


@router.get("/dashboard")
def dashboard(champ_id: int | None = None):
    """Ana sayfadaki panonun tum verisini tek istekte dondurur.

    champ_id verilirse HER SEY o lige daralir - sayimlar, kapsama, mac basi
    gol, mac listesi ve sezon trendi. Ligler ayni oyunun cok farkli gol
    profilli formatlari oldugu icin karisik bir ozet hicbir ligi tarif etmiyor.
    """
    ch, ca = _champ_clause(champ_id)
    counts = _row(f"""SELECT
        SUM(status='live')      AS live,
        SUM(status='scheduled') AS scheduled,
        SUM(status='finished')  AS finished,
        COUNT(*)                AS total FROM matches m WHERE 1=1{ch}""", ca) or {}
    counts["snapshots"] = (_row(
        "SELECT COUNT(*) c FROM odds_snapshots s "
        f"JOIN matches m ON m.event_id = s.event_id WHERE 1=1{ch}", ca) or {}).get("c", 0)
    counts["ticks"] = (_row(
        "SELECT COUNT(*) c FROM odds_ticks t "
        f"JOIN matches m ON m.event_id = t.event_id WHERE 1=1{ch}", ca) or {}).get("c", 0)

    # Bizim arsivimizden mac basi gol (yalnizca skoru bilinen biten maclar)
    g = _row("""SELECT COUNT(*) n, SUM(score_home + score_away) total
                FROM matches m WHERE status='finished'
                      AND score_home IS NOT NULL""" + ch, ca) or {}
    avg_goals = round((g.get("total") or 0) / g["n"], 2) if g.get("n") else None

    # Lig kirilimi: formatlar farkli gol profiline sahip (5x5 Rush ~7 gol),
    # tek bir genel ortalama iki lig izlenirken yaniltici olur.
    by_league = _rows("""SELECT m.champ_id, COALESCE(l.name, m.league_name) AS name,
                                SUM(m.status='live')      AS live,
                                SUM(m.status='scheduled') AS scheduled,
                                SUM(m.status='finished')  AS finished,
                                COUNT(*)                  AS total,
                                SUM(CASE WHEN m.status='finished'
                                          AND m.score_home IS NOT NULL THEN 1 END) AS scored,
                                SUM(CASE WHEN m.status='finished'
                                          AND m.score_home IS NOT NULL
                                         THEN m.score_home + m.score_away END) AS goals
                         FROM matches m LEFT JOIN leagues l ON l.champ_id = m.champ_id
                         GROUP BY m.champ_id ORDER BY name""")
    for r in by_league:
        n = r.pop("scored") or 0
        total = r.pop("goals") or 0
        r["avg_goals"] = round(total / n, 2) if n else None
        r["avg_goals_sample"] = n
    if champ_id is not None:
        by_league = [r for r in by_league if r["champ_id"] == champ_id]

    # p1/px/p2 (mac oncesi 1X2) benzer mac aramasi icin: canli macta o1/ox/o2
    # mac ici orandir, benzerlik olcusu olarak kullanilamaz.
    live = _rows(f"""
        SELECT m.*, o.o1, o.ox, o.o2, p.p1, p.px, p.p2,
               (SELECT COUNT(*) FROM odds_snapshots s WHERE s.event_id=m.event_id) AS has_snapshot,
               (SELECT s.market_count FROM odds_snapshots s
                 WHERE s.event_id=m.event_id AND s.phase='prematch') AS snapshot_markets,
               COALESCE(m.prematch_missed, 0) AS prematch_missed
        FROM matches m LEFT JOIN ({LATEST_ODDS}) o ON o.event_id = m.event_id
                       LEFT JOIN ({PREMATCH_ODDS}) p ON p.event_id = m.event_id
        WHERE m.status IN ('live','scheduled'){ch}
        ORDER BY m.start_ts ASC""", ca)
    _attach_expectations(live)
    _attach_predictions(live)
    _attach_h2h(live)
    _attach_positions(live)
    _attach_match_minutes(live)

    return {
        "counts": counts,
        "coverage": _coverage(champ_id),
        "avg_goals": avg_goals,
        "avg_goals_sample": g.get("n") or 0,
        "by_league": by_league,
        "recent_finished": _recent_finished(champ_id),
        "live": live,
        "season_trends": _season_trends(champ_id),
    }


# --------------------------------------------------- lig sirasi / mac suresi
def _attach_positions(rows: list[dict]) -> None:
    """Her maca iki takimin lig sirasini ekler (home_pos / away_pos).

    Sira macin OYNANDIGI sezondan okunur; o sezonun tablosu henuz cekilmemisse
    (surmekte olan sezon icin normal) en son bilinen sezona duseriz ve
    pos_current=True ile isaretleriz - arayuz bunu "guncel tablodan" diye
    gosterebilsin, sira uydurulmus gibi durmasin.
    """
    cache: dict[int, tuple[dict, int | None]] = {}
    for r in rows:
        tid = r.get("tourney_id")
        if tid is None:
            r["home_pos"] = r["away_pos"] = None
            r["pos_iteration"], r["pos_current"] = None, False
            continue
        if tid not in cache:
            cache[tid] = _season_positions(tid)
        by_iter, latest = cache[tid]
        it = r.get("iteration")
        use = it if it in by_iter else latest
        table = by_iter.get(use, {})
        r["home_pos"] = table.get(r.get("home"))
        r["away_pos"] = table.get(r.get("away"))
        r["pos_iteration"] = use
        r["pos_current"] = use is not None and use != it


def _attach_match_minutes(rows: list[dict]) -> None:
    """Sanal macin gercek zamanli suresi (dakika) - ligden lige degisir.

    Arayuz "kac dakika kaldi" hesabini bununla yapiyor; leagues.json
    disinda baska kaynagi yok, o yuzden mac satirina yaziyoruz.
    """
    mins = _league_match_minutes()
    for r in rows:
        r["match_minutes"] = mins.get(r.get("champ_id"), LIVE_MATCH_MINUTES)


# --------------------------------------------------- karsilasma gecmisi (h2h)
def _season_positions(tourney_id: int | None) -> tuple[dict, int | None]:
    """(iterasyon -> {takim: sira}, en son iterasyon)

    Sira, macin OYNANDIGI sezondan okunur. matches.iteration ancak
    GetGameZip'ten geri yazildigi maclarda dolu (bkz. collector._save_meta);
    eski kayitlarda bos oldugu icin en son sezona duseriz - bu durum
    'pos_current' bayragiyla isaretlenir, sira uydurulmus gibi gorunmesin.
    """
    if tourney_id is None:
        return {}, None
    by_iter: dict[int, dict[str, int]] = {}
    for r in _rows("SELECT iteration, team, pos FROM season_tables "
                   "WHERE tourney_id = ?", (tourney_id,)):
        by_iter.setdefault(r["iteration"], {})[r["team"]] = r["pos"]
    return by_iter, (max(by_iter) if by_iter else None)


H2H_LIMIT = 8



def _decorate(rows: list[dict], home: str, by_iter: dict,
              latest: int | None) -> None:
    """Gecmis mac satirlarini ekranda gerekli alanlarla tamamlar.

    Hem karsilasma gecmisi hem ayni oranli maclar ayni sutunlari gosteriyor;
    tutan cizgiler ve lig sirasi tek yerden ekleniyor.
    """
    totals = _totals_by_event([r["event_id"] for r in rows])
    for r in rows:
        r["total"] = r["score_home"] + r["score_away"]
        r.update(_hit_lines(totals.get(r["event_id"]) or {}, r["total"]))
        it = r["iteration"] if r["iteration"] in by_iter else latest
        table = by_iter.get(it) or {}
        r["home_pos"] = table.get(r["home"])
        r["away_pos"] = table.get(r["away"])
        # Sira macin kendi sezonundan mi geldi, yoksa en son tablodan mi?
        r["pos_current"] = bool(table) and r["iteration"] not in by_iter
        # Onceki maclar iki dizilistede olabilir; ekranda su anki ev sahibinin
        # attigi gol hep ayni sutunda dursun.
        swapped = r["home"] != home
        r["for_home"] = r["score_away"] if swapped else r["score_home"]
        r["for_away"] = r["score_home"] if swapped else r["score_away"]


def _summary(rows: list[dict], split: bool = True) -> dict:
    """split=False: ev/deplasman kirilimi verilmez.

    'Ayni oranli maclar' listesinde gecmis macin taraflari bizim maci degil,
    baska bir eslesmeyi tarif ediyor - o satirlarda ev/deplasman ortalamasi
    yaniltici olurdu.
    """
    n = len(rows)
    if not n:
        return {"n": 0, "matches": []}
    out = {"n": n,
           "avg_total": round(sum(r["total"] for r in rows) / n, 2),
           "matches": rows}
    if split:
        out["avg_home"] = round(sum(r["for_home"] for r in rows) / n, 2)
        out["avg_away"] = round(sum(r["for_away"] for r in rows) / n, 2)
    return out


PAST_SELECT = """
        SELECT m.event_id, m.start_ts, m.home, m.away, m.iteration,
               m.score_home, m.score_away, p.p1, p.px, p.p2
        FROM matches m LEFT JOIN ({odds}) p ON p.event_id = m.event_id
        WHERE m.champ_id = ? AND m.status = 'finished'
              AND m.score_home IS NOT NULL AND m.score_away IS NOT NULL
              AND m.event_id != ?
"""


def _same_odds(match: dict, exclude: set[int], by_iter: dict,
               latest: int | None, gap: float = SAME_ODDS_GAP) -> dict:
    """Bu macin takimlarindan YALNIZCA BIRININ oynadigi ve o takimin ayni
    oranla fiyatlandigi BITEN maclar.

    Olcut takim bazli, ayak bazli degil:
      * gecmis macta bizim iki takimimizdan TAM OLARAK biri olacak
        (ikisi de varsa o zaten karsilasma gecmisi, ustteki tabloda),
      * o takimin O MACTAKI orani, BU MACTAKI oranina +/-gap yakin olacak.

    Takim evde de deplasmanda da olabilir; oran her iki tarafta da takimin
    kendi ayagindan okunur (evdeyse 1, deplasmandaysa 2). Boylece "bu takim
    daha once de bu fiyata oynadi, ne oldu" sorusu cevaplanir.

    Takimin kendi ayagi TEK BASINA yetmiyor: 1/X/2 ucundan en az
    SAME_ODDS_MIN_LEGS tanesi tutmali. Tek ayak esitlendiginde kalan iki ayak
    cok farkli olabiliyordu - "ayni oranli" denen mac aslinda bambaska
    fiyatlanmis bir mac cikiyordu.

    Ayaklar TAKIMIN BAKIS ACISINDAN hizalanir: (kendi orani, beraberlik,
    rakip orani). Takim gecmis macta obur tarafta oynadiysa o macin 1 ve 2
    ayaklari yer degistirir; ham sutunlari karsilastirmak takim deplasmandayken
    yanlis ayaklari eslestirirdi.
    """
    home, away = match.get("home"), match.get("away")
    p1, px, p2 = match.get("p1"), match.get("px"), match.get("p2")
    if not home or not away or p1 is None or p2 is None:
        return {"n": 0, "matches": [], "gap": gap}
    ref = {home: p1, away: p2}
    # Takimin bakis acisiyla (kendi, beraberlik, rakip)
    ref_legs = {home: (p1, px, p2), away: (p2, px, p1)}

    # Aday havuzu: iki takimdan en az biri gecen maclar, yeniden eskiye.
    # "Tam olarak biri" ve oran yakinligi Python'da suzuluyor - takimin hangi
    # tarafta oynadigina gore farkli sutuna bakmak gerekiyor, bunu SQL'de
    # yazmak okunmaz bir CASE yiginina donusuyor.
    rows = _rows(
        PAST_SELECT.format(odds=PREMATCH_ODDS) +
        """      AND p.p1 IS NOT NULL AND p.p2 IS NOT NULL
              AND (m.home IN (?, ?) OR m.away IN (?, ?))
        ORDER BY m.start_ts DESC
        LIMIT 500""",
        (match.get("champ_id"), match.get("event_id"),
         home, away, home, away))

    picked = []
    for r in rows:
        if r["event_id"] in exclude:
            continue
        ours = {r["home"], r["away"]} & {home, away}
        if len(ours) != 1:
            continue
        team = ours.pop()
        at_home = r["home"] == team
        odd = r["p1"] if at_home else r["p2"]
        if abs(odd - ref[team]) > gap:
            continue
        cand_legs = ((r["p1"], r["px"], r["p2"]) if at_home
                     else (r["p2"], r["px"], r["p1"]))
        hits = sum(1 for x, y in zip(ref_legs[team], cand_legs)
                   if x is not None and y is not None and abs(x - y) <= gap)
        if hits < SAME_ODDS_MIN_LEGS:
            continue
        r["leg_hits"] = hits
        r["team"] = team
        r["team_odd"] = odd
        r["team_ref"] = ref[team]
        r["team_side"] = "home" if at_home else "away"
        r["hit_1"], r["hit_2"] = at_home, not at_home
        picked.append(r)
        if len(picked) >= SAME_ODDS_LIMIT:
            break

    _decorate(picked, home, by_iter, latest)
    out = _summary(picked, split=False)
    out["gap"] = gap
    out["limit"] = SAME_ODDS_LIMIT
    out["min_legs"] = SAME_ODDS_MIN_LEGS
    out["ref"] = {"p1": p1, "px": px, "p2": p2}
    return out


def _season_h2h(tourney_id: int | None, home: str, away: str,
                seasons: int = H2H_SEASONS) -> dict:
    """Son N sezonda ayni iki takimin oynadigi maclar (eventsstat).

    Bizim arsivimiz yalnizca birkac gunu kapsiyor, dolayisiyla gecmis
    sezonlardaki eslesmeler icin tek kaynak sitenin sezon ozeti. Oran YOK -
    o kayitlar sadece skor tasiyor.
    """
    if tourney_id is None or not home or not away:
        return {"n": 0, "seasons": [], "matches": []}
    its = [r["iteration"] for r in _rows(
        "SELECT DISTINCT iteration FROM season_matches WHERE tourney_id = ? "
        "ORDER BY iteration DESC LIMIT ?", (tourney_id, seasons))]
    if not its:
        return {"n": 0, "seasons": [], "matches": []}
    marks = ",".join("?" * len(its))
    rows = _rows(
        f"""SELECT iteration, home, away, score_home, score_away
            FROM season_matches
            WHERE tourney_id = ? AND iteration IN ({marks})
                  AND ((home = ? AND away = ?) OR (home = ? AND away = ?))
            ORDER BY iteration DESC, home""",
        (tourney_id, *its, home, away, away, home))
    for r in rows:
        r["total"] = r["score_home"] + r["score_away"]
        # Ekranda su anki ev sahibinin golu hep ayni sutunda dursun.
        swapped = r["home"] != home
        r["for_home"] = r["score_away"] if swapped else r["score_home"]
        r["for_away"] = r["score_home"] if swapped else r["score_away"]
    out = {"n": len(rows), "seasons": its, "matches": rows}
    if rows:
        n = len(rows)
        out["avg_total"] = round(sum(r["total"] for r in rows) / n, 2)
        out["avg_home"] = round(sum(r["for_home"] for r in rows) / n, 2)
        out["avg_away"] = round(sum(r["for_away"] for r in rows) / n, 2)
    return out


def _odds_goal(match: dict, pool: list[dict], gap: float = ODDS_GOAL_GAP,
               limit: int = ODDS_GOAL_LIMIT,
               samples: int = ODDS_GOAL_SAMPLES) -> dict:
    """Ayni oranla oynanmis son maclardan beklenen gol - "oran golu".

    Aday mac EV/DEPLASMAN KONUMLARI KORUNARAK eslesir: ev ayagi ev ayagiyla,
    deplasman ayagi deplasman ayagiyla, ikisi de +/-gap icinde. Takim onemli
    degil - soru "bu FIYATA oynanan maclarda kac gol oluyor".

    Yalnizca macin KENDINDEN ONCEKI maclar sayilir. Sonradan oynanmis maclari
    katmak, bitmis bir macin tahminine o macin gelecegini karistirmak olurdu;
    "tuttu mu" sorusu da anlamsizlasirdi.

    Beklenen gol, ortalamaya uygulamanin kendi kalibrasyonuyla bulunur
    (bkz. markets.calibrate_total): ortalamadan 0.5 dusulup altindaki x.5'e
    yuvarlanir, boylece dogrudan bir Alt/Ust cizgisiyle karsilastirilabilir.
    """
    p1, p2 = match.get("p1"), match.get("p2")
    out = {"n": 0, "gap": gap, "limit": limit, "total": None, "avg_total": None,
           "avg_home": None, "avg_away": None, "matches": []}
    if p1 is None or p2 is None:
        return out

    ref_ts, ref_id = match.get("start_ts"), match.get("event_id")
    picked = []
    for r in pool:                       # havuz tarihe gore AZALAN
        if r["event_id"] == ref_id:
            continue
        if ref_ts is not None and r["start_ts"] >= ref_ts:
            continue
        if r["p1"] is None or r["p2"] is None:
            continue
        if abs(r["p1"] - p1) > gap or abs(r["p2"] - p2) > gap:
            continue
        picked.append(r)
        if len(picked) >= limit:
            break
    if not picked:
        return out

    home = [r["score_home"] for r in picked]
    away = [r["score_away"] for r in picked]
    avg = (sum(home) + sum(away)) / len(picked)
    out.update({
        "n": len(picked),
        "avg_home": round(sum(home) / len(picked), 2),
        "avg_away": round(sum(away) / len(picked), 2),
        "avg_total": round(avg, 2),
        "total": calibrate_total(avg),
        "matches": [{"event_id": r["event_id"], "start_ts": r["start_ts"],
                     "home": r["home"], "away": r["away"],
                     "score_home": r["score_home"], "score_away": r["score_away"],
                     "total": r["score_home"] + r["score_away"],
                     "p1": r["p1"], "px": r["px"], "p2": r["p2"]}
                    for r in picked[:samples]],
    })
    return out


def _attach_odds_goals(rows: list[dict]) -> None:
    """Her maca oran golunu ekler (tablo sutunu icin duz alanlar).

    Havuz LIG BASINA bir kez okunur; her mac icin ayri sorgu atmak listeyi
    mac sayisi kadar yavaslatirdi. Sezon siniri YOK - "son 20 mac" zaten
    yakinligi tarihten aliyor.
    """
    pools: dict[int | None, list[dict]] = {}
    for r in rows:
        champ = r.get("champ_id")
        if champ not in pools:
            pools[champ] = _prediction_pool(champ, seasons=0)
        og = _odds_goal(r, pools[champ])
        r["odds_goal"] = og["total"]
        r["odds_goal_n"] = og["n"]
        total = r.get("total")
        if total is None and r.get("score_home") is not None:
            total = r["score_home"] + r["score_away"]
        r["odds_goal_hit"] = (og["total"] is not None and total is not None
                              and total > og["total"])


def _h2h(match: dict, positions: tuple[dict, int | None] | None = None,
         tourney: int | None = None,
         pool: list[dict] | None = None) -> dict:
    """Ayni iki takimin gecmiste oynadigi BITEN maclar.

    Ev/deplasman ayrimi gozetilmez: iki dizilis de ayni eslesmedir, arsiv
    zaten kucuk (bir ciftin en fazla 3 macini gorduk).
    """
    home, away = match.get("home"), match.get("away")
    # matches.tourney_id cogu kayitta bos (liste feed'i gondermiyor); cagiran
    # taraf ligin turnuvasini cozup geciriyor.
    tourney = tourney or match.get("tourney_id")
    by_iter, latest = positions if positions is not None else \
        _season_positions(tourney)
    rows = []
    if home and away:
        rows = _rows(
            PAST_SELECT.format(odds=PREMATCH_ODDS) +
            """      AND ((m.home = ? AND m.away = ?) OR (m.home = ? AND m.away = ?))
        ORDER BY m.start_ts DESC LIMIT ?""",
            (match.get("champ_id"), match.get("event_id"),
             home, away, away, home, H2H_LIMIT))
        _decorate(rows, home, by_iter, latest)
    out = _summary(rows)
    out["same_odds"] = _same_odds(match, {r["event_id"] for r in rows},
                                  by_iter, latest)
    seasons = _season_h2h(tourney, home, away)
    out["seasons"] = seasons

    # Oran golu: ayni fiyata, ayni dizilisle oynanmis son maclar.
    out["odds_goal"] = _odds_goal(match, pool or [])
    return out


def _attach_h2h(rows: list[dict]) -> None:
    """Listedeki her maca karsilasma gecmisini ekler.

    Sezon tablosu turnuva basina BIR kez okunur; her mac icin ayri sorgu
    atmak 1660 satirlik tabloyu mac sayisi kadar tekrar okurdu.
    """
    tourneys = _league_tourneys()
    cache: dict[int | None, tuple] = {}
    pools: dict[int | None, list[dict]] = {}
    for m in rows:
        t = m.get("tourney_id") or tourneys.get(m.get("champ_id"))
        if t not in cache:
            cache[t] = _season_positions(t)
        champ = m.get("champ_id")
        if champ not in pools:
            pools[champ] = _prediction_pool(champ, seasons=0)
        m["h2h"] = _h2h(m, cache[t], tourney=t, pool=pools[champ])


@router.get("/matches/{event_id}/h2h")
def match_h2h(event_id: int):
    """Bu macin iki takimi arasindaki gecmis maclar."""
    m = _row("SELECT event_id, champ_id, home, away, tourney_id FROM matches "
             "WHERE event_id = ?", (event_id,))
    if not m:
        raise HTTPException(404, "mac bulunamadi")
    t = m["tourney_id"] or _league_tourneys().get(m["champ_id"])
    return _h2h(m, _season_positions(t), tourney=t,
                lines=_totals_by_event([event_id]).get(event_id))


def _prediction_pool(champ_id: int | None = None,
                     seasons: int = PREDICT_POOL_SEASONS) -> list[dict]:
    """Tahmin havuzu: skoru ve mac oncesi 1X2 orani bilinen BITEN maclar.

    Tek sorgu ile cekilip bellekte suzuluyor; arsiv kucuk (yuzlerce satir) ve
    her mac icin ayri sorgu atmak listeyi N kat yavaslatirdi.

    champ_id verilmeli: havuz LIGE OZELDIR. Ligler ayni oyunun farkli
    formatlari (5x5 Rush ~7 gol, 3x3 daha az) - birinin arsivi otekinin
    'form' ve 'benzer oranli mac' bilesenlerini bozar.

    Havuz son PREDICT_POOL_SEASONS sezonla sinirli. Pencere LIG BASINA
    hesaplaniyor: iteration numaralari turnuvalar arasinda cakisiyor
    (149: 1-56, 129: 1-219), tek bir esik iki ligden birini bombos birakirdi.
    """
    where, args = "", ()
    if champ_id is not None:
        where, args = " AND m.champ_id = ?", (champ_id,)
    rows = _rows(f"""
        SELECT m.event_id, m.champ_id, m.iteration, m.home, m.away, m.start_ts,
               m.score_home, m.score_away, p.p1, p.px, p.p2
        FROM matches m JOIN ({PREMATCH_ODDS}) p ON p.event_id = m.event_id
        WHERE m.status = 'finished' AND m.score_home IS NOT NULL
              AND m.score_away IS NOT NULL AND p.p1 IS NOT NULL
              AND p.p2 IS NOT NULL{where}
        ORDER BY m.start_ts DESC""", args)
    return _last_seasons(rows, seasons)


def _last_seasons(rows: list[dict], n: int) -> list[dict]:
    """Satirlari her ligin SON n sezonuyla sinirlar.

    Sezonu bos olan satirlar elenir - hangi sezona dustuklerini bilmiyoruz,
    "son 4 sezon" diye gosterilen bir kumeye emin olmadan koyamayiz.
    """
    if n <= 0:
        return rows
    keep: dict[int, set] = {}
    by_champ: dict[int, set] = {}
    for r in rows:
        if r.get("iteration") is not None:
            by_champ.setdefault(r["champ_id"], set()).add(r["iteration"])
    for champ, its in by_champ.items():
        keep[champ] = set(sorted(its, reverse=True)[:n])
    return [r for r in rows if r.get("iteration") is not None
            and r["iteration"] in keep.get(r["champ_id"], ())]


def _season_rows(tourney_id: int | None) -> list[dict]:
    """Sezon gucu satirlari - TEK bir tourney icin.

    Iteration numaralari turnuvalar arasinda cakisiyor (149: 1-56, 129: 1-219);
    filtresiz okumak iki ligin sezonlarini ayni sezon sanip birlestirirdi.
    tourney bilinmiyorsa bos donulur: 'season' bileseni uretilemez, agirligi
    kalan bilesenlere dagitilir (bkz. predict.blend).
    """
    if tourney_id is None:
        return []
    return _rows("SELECT iteration, team, played, gf, ga FROM season_tables "
                 "WHERE tourney_id = ?", (tourney_id,))


def _predictor(champ_id: int | None = None, gap: float = PREDICT_GAP,
               weights: dict | None = None) -> Predictor:
    """Bir LIGIN tahmin modelini kurar (havuz + sezon gucu bir kez hesaplanir)."""
    tourney = _league_tourneys().get(champ_id) if champ_id is not None else None
    return Predictor(
        pool=_prediction_pool(champ_id),
        season_rows=_season_rows(tourney),
        weights=weights or PREDICT_WEIGHTS,
        gap=gap, n_prev=PREDICT_SEASONS, w_cur=PREDICT_CURRENT_WEIGHT,
        form_k=PREDICT_FORM_K)


def _pool_expectations(pool: list[dict]) -> dict[int, dict]:
    """Havuzdaki her mac icin oran beklentisi (isabet olcumunun oran ayagi)."""
    out: dict[int, dict] = {}
    for m in pool:
        snap = _expectation_snapshot(m["event_id"])
        if not snap:
            continue
        e = goal_expectation(
            _rows("SELECT g, t, p, coef, blocked FROM odds_values "
                  "WHERE snapshot_id=?", (snap["id"],)))
        if e:
            out[m["event_id"]] = e
    return out


def _attach_predictions(rows: list[dict], pred: Predictor | None = None) -> None:
    """Her maca harmanlanmis gol tahminini ekler.

    _attach_expectations'tan SONRA cagrilmali: oran bileseni m['expect']
    uzerinden okunuyor.

    Liste birden fazla lig icerebilir (pano canli+yaklasan listesi); her lig
    icin ayri model kurulur ve lig basina bir kez onbelleklenir.
    """
    if pred is not None:
        for m in rows:
            m["predict"] = pred.predict(m, exclude=m["event_id"])
        return
    cache: dict[int | None, Predictor] = {}
    for m in rows:
        champ = m.get("champ_id")
        model = cache.get(champ)
        if model is None:
            model = cache[champ] = _predictor(champ)
        m["predict"] = model.predict(m, exclude=m["event_id"])


def _expectation_snapshot(event_id: int) -> dict | None:
    """Beklenti hesabinda kullanilacak snapshot: referans set once, yoksa acilis.

    TEK yerden donmesi sart: gol beklentisi tablosu, dagilim paneli ve mac
    detayindaki kirilim ayni sete bakmazsa ayni mac icin farkli sayilar
    gosterirler.
    """
    from .collector import PHASE_OPEN, PHASE_REF
    return _row("SELECT id, phase, taken_at, market_count FROM odds_snapshots "
                "WHERE event_id=? "
                "ORDER BY CASE phase WHEN ? THEN 0 WHEN ? THEN 1 ELSE 2 END LIMIT 1",
                (event_id, PHASE_REF, PHASE_OPEN))


def _league_match_minutes() -> dict[int, float]:
    """champ_id -> sanal macin gercek zamanli suresi (dakika).

    Lig basina degisiyor: kendi arsivimizden son tick ile baslangic arasindaki
    fark olculdu -> 5x5 Rush medyan 10.4 dk (n=74), 3x3 medyan 9.4 dk (n=10).
    Aradaki ~1 dakika, macin ortasinda kalan gol beklentisini %10 kaydiriyor.
    Deger leagues.json'daki 'extra.match_minutes' ile ligden lige verilir;
    yoksa LIVE_MATCH_MINUTES'a duser.
    """
    out: dict[int, float] = {}
    for l in load_leagues():
        v = (l.extra or {}).get("match_minutes")
        if v:
            try:
                out[l.champ_id] = float(v)
            except (TypeError, ValueError):
                pass
    return out


def _apply_remaining(e: dict, match: dict, now: float,
                     minutes: float = LIVE_MATCH_MINUTES) -> None:
    """Kalan gol beklentisi. Gol gelisi zamanla dogrusal (arsivden olculdu),
    Poisson surecinde de gecmis gol gelecegi degistirmez - bu yuzden atilan
    gol sayisi degil yalnizca gecen sure kullanilir.
    """
    e["elapsed_min"] = e["remaining"] = None
    e["match_minutes"] = minutes
    if match.get("status") == "live" and match.get("start_ts"):
        elapsed = max(0.0, (now - match["start_ts"]) / 60)
        left = max(0.0, 1 - elapsed / minutes)
        e["elapsed_min"] = round(elapsed, 1)
        e["left_share"] = round(left, 4)
        e["remaining"] = round(e["total"] * left, 2)


def _attach_expectations(rows: list[dict]) -> None:
    """Her maca mac oncesi oranlardan cikan gol beklentisini ekler.

    Kullanilan set: referans ('prekickoff') varsa o, yoksa acilis ('prematch')
    - mac basladiktan sonra site oranlari sildigi icin baska kaynak yok.

    ACILIS setinin ayri bir beklenti olarak tasinmasi DENENDI ve birakildi:
    arsivdeki 400 macin 399'unda acilis ('prematch') ile kickoff oncesi
    ('prekickoff') set birebir ayni ham beklentiyi veriyor - aralarinda medyan
    24 dakika olmasina ragmen. Kitap Toplam Gol cizgilerini mac oncesinde
    oynatmiyor; ayri bir sayi olarak yazmak ayni rakami iki kez gostermek
    olurdu. Ekranda beklentinin yanindaki ikinci sayi bu yuzden HAM deger
    (kalibrasyon oncesi, expect.total_raw).

    Sorgular TOPLU: eskiden mac basina iki sorgu atiliyordu (1500 maclik bir
    listede 3000 sorgu). Simdi snapshot'lar tek, degerler tek sorguda geliyor.
    """
    from .collector import PHASE_OPEN, PHASE_REF
    if not rows:
        return
    ids = [m["event_id"] for m in rows]
    marks = ",".join("?" * len(ids))

    # 1) her macin referans ve acilis snapshot'lari
    snaps: dict[int, dict[str, int]] = {}
    for r in _rows(f"SELECT id, event_id, phase FROM odds_snapshots "
                   f"WHERE event_id IN ({marks})", tuple(ids)):
        snaps.setdefault(r["event_id"], {})[r["phase"]] = r["id"]

    # Yalnizca KULLANILAN set okunuyor. Iki fazi da cekmek satir sayisini
    # ikiye katliyordu ve acilis seti artik ayri bir sayi uretmiyor.
    used_by_event = {ev: (by_phase.get(PHASE_REF) or by_phase.get(PHASE_OPEN))
                     for ev, by_phase in snaps.items()}
    wanted = {sid for sid in used_by_event.values() if sid}
    values: dict[int, list[dict]] = {}
    if wanted:
        wl = list(wanted)
        # SQLite'in degisken sinirina takilmamak icin parcali okunuyor.
        for i in range(0, len(wl), 400):
            chunk = wl[i:i + 400]
            cm = ",".join("?" * len(chunk))
            for v in _rows(f"SELECT snapshot_id, g, t, p, coef, blocked "
                           f"FROM odds_values WHERE snapshot_id IN ({cm})",
                           tuple(chunk)):
                values.setdefault(v["snapshot_id"], []).append(v)

    now = time.time()
    minutes = _league_match_minutes()
    for m in rows:
        used = used_by_event.get(m["event_id"])
        e = goal_expectation(values.get(used, [])) if used else None
        m["expect"] = e
        if e:
            _apply_remaining(e, m, now,
                             minutes.get(m.get("champ_id"), LIVE_MATCH_MINUTES))



def _season_trends(champ_id: int | None = None) -> list[dict]:
    """Her lig icin sezon basina mac basi gol ortalamasi.

    Bir macin iki takimi da tabloda sayildigi icin mac sayisi = played/2;
    ligdeki toplam gol = sum(gf). Yani ortalama = 2*sum(gf)/sum(played).

    Turnuva basina ayri gruplanir: iteration numaralari turnuvalar arasinda
    cakisiyor (149'da 1-56, 129'da 1-219), tek bir GROUP BY iteration iki
    ligin ayri sezonlarini ayni satirda toplardi.
    """
    rows = _rows("""SELECT tourney_id, iteration, SUM(gf) gf, SUM(played) played
                    FROM season_tables GROUP BY tourney_id, iteration
                    HAVING played > 0 ORDER BY tourney_id, iteration""")
    names = {l["tourney_id"]: l["name"] or str(l["champ_id"])
             for l in leagues() if l.get("tourney_id")}
    by_tourney: dict[int, list] = {}
    for r in rows:
        by_tourney.setdefault(r["tourney_id"], []).append({
            "iteration": r["iteration"],
            "matches": r["played"] // 2,
            "avg_goals": round(2 * r["gf"] / r["played"], 2)})
    out = [{"tourney_id": t, "name": names.get(t, f"turnuva {t}"), "trend": v}
           for t, v in sorted(by_tourney.items())]
    if champ_id is not None:
        want = _league_tourneys().get(champ_id)
        out = [t for t in out if t["tourney_id"] == want]
    return out


# ------------------------------------------------------------------ canli akis
@router.get("/stream")
async def stream():
    """Server-Sent Events: collector her poll'da olay yayinlar."""
    async def gen():
        q = broadcaster.subscribe()
        try:
            yield f"data: {json.dumps({'type': 'hello', 'ts': int(time.time())})}\n\n"
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=25)
                    yield f"data: {json.dumps(ev)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            broadcaster.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@router.post("/collector/poll")
async def force_poll():
    """Elle tek poll tetikler (gelistirme/teshis icin)."""
    try:
        return await collector.poll_once()
    except Exception as ex:                            # noqa: BLE001
        raise HTTPException(502, f"poll basarisiz: {ex}") from ex


@router.get("/markets/labels")
def market_labels():
    """Frontend'in ham G/T kodlarini etiketleyebilmesi icin sozluk."""
    from .markets import GROUP_NAMES, OUTCOME_NAMES
    return {"groups": {str(k): v for k, v in GROUP_NAMES.items()},
            "outcomes": {f"{g}:{t}": v for (g, t), v in OUTCOME_NAMES.items()},
            "main": {"group": 1, "types": {str(k): v for k, v in MAIN_TYPES.items()}}}
