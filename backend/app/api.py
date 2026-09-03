"""HTTP API katmani."""
import asyncio
import json
import time

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from . import db
from .collector import broadcaster, collector
from .config import (LIVE_MATCH_MINUTES, League, POLL_SECONDS,
                     PREDICT_CURRENT_WEIGHT, PREDICT_FORM_K, PREDICT_GAP,
                     PREDICT_SEASONS, PREDICT_WEIGHTS, load_leagues, save_leagues)
from .markets import (LOST, MAIN_TYPES, OU_GROUP, OU_OVER, OU_UNDER, WON,
                      goal_expectation, group_label, outcome_label, settle)
from .predict import Predictor, backtest, goal_prediction
from .stats import StatsUnavailable, season_table

router = APIRouter(prefix="/api")


def _rows(sql: str, args: tuple = ()) -> list[dict]:
    with db.session() as con:
        return [dict(r) for r in con.execute(sql, args).fetchall()]


def _row(sql: str, args: tuple = ()) -> dict | None:
    r = _rows(sql, args)
    return r[0] if r else None


# ------------------------------------------------------------------ durum
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
      ilk tutan alt  = tutan alt cizgilerin EN DUSUGU (toplama en yakin ust sinir)
      en ust tutan   = tutan ust cizgilerin EN YUKSEGI (toplamin altindaki en buyuk)
    """
    unders = sorted(p for p, o in lines.items() if "under" in o and total < p)
    overs = sorted((p for p, o in lines.items() if "over" in o and total > p),
                   reverse=True)
    res = {"under_first": None, "under_first_odd": None,
           "over_top": None, "over_top_odd": None}
    if unders:
        res["under_first"] = unders[0]
        res["under_first_odd"] = lines[unders[0]].get("under")
    if overs:
        res["over_top"] = overs[0]
        res["over_top_odd"] = lines[overs[0]].get("over")
    return res


def _attach_totals(rows: list[dict]) -> None:
    """Listedeki her maca tutan alt/ust cizgilerini ekler (skor + arsiv varsa)."""
    scored = [r for r in rows
              if r.get("score_home") is not None and r.get("score_away") is not None]
    totals = _totals_by_event([r["event_id"] for r in scored])
    for r in rows:
        lines = totals.get(r["event_id"])
        if lines and r.get("score_home") is not None:
            r.update(_hit_lines(lines, r["score_home"] + r["score_away"]))
        else:
            r.update({"under_first": None, "under_first_odd": None,
                      "over_top": None, "over_top_odd": None})


def _match_filter(champ_id, status, team, o1, ox, o2, gap):
    """/matches ve /matches/stats icin ortak WHERE kurulumu.

    Oran filtresi mac ONCESI 1X2 (p.p1/px/p2) uzerinden calisir; girilmeyen
    taraf serbest kalir. `dist` girilen oranlara toplam mutlak uzakliktir.
    """
    where, args = ["1=1"], []
    if champ_id is not None:
        where.append("m.champ_id = ?"); args.append(champ_id)
    if status:
        where.append("m.status = ?"); args.append(status)
    if team:
        where.append("(m.home LIKE ? OR m.away LIKE ?)")
        args += [f"%{team}%", f"%{team}%"]

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
def match_similar(event_id: int, gap: float = Query(PREDICT_GAP, gt=0, le=5)):
    """Baslangic oranlari bu maca yakin olan BITEN maclar + gol tahmini.

    Pencere `gap` ile daraltilip genisletilebilir; varsayilan PREDICT_GAP.
    Mac kendisi ornekten cikarilir (bitmis bir maci kendi tahmininde saymak
    isabeti yapay olarak yukseltirdi).
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
    pred = goal_prediction(m["p1"], m["p2"], pool, gap, exclude=event_id, detail=True)
    pred["accuracy"] = backtest(pool, gap)
    pred["pool"] = len(pool)
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

    vals = _rows("SELECT g, gs, t, p, coef, blocked FROM odds_values "
                 "WHERE snapshot_id=? ORDER BY g, t, p", (snap["id"],))
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
    added, skipped, failed = 0, 0, []
    for it in range(start, end + 1):
        exists = _row("SELECT 1 FROM season_tables WHERE tourney_id=? AND iteration=? "
                      "LIMIT 1", (tourney_id, it))
        if exists:
            skipped += 1
            continue
        try:
            table = await season_table(tourney_id, it)
        except (StatsUnavailable, Exception) as ex:    # noqa: BLE001
            failed.append({"iteration": it, "error": str(ex)[:120]})
            continue
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
        added += 1
        await asyncio.sleep(0.4)          # kaynagi yormayalim
    return {"added": added, "skipped": skipped, "failed": failed[:20],
            "failed_count": len(failed)}



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

    return {
        "counts": counts,
        "coverage": _coverage(champ_id),
        "avg_goals": avg_goals,
        "avg_goals_sample": g.get("n") or 0,
        "by_league": by_league,
        "live": live,
        "goal_distribution": _goal_distribution(live),
        "season_trends": _season_trends(champ_id),
    }


def _prediction_pool(champ_id: int | None = None) -> list[dict]:
    """Tahmin havuzu: skoru ve mac oncesi 1X2 orani bilinen BITEN maclar.

    Tek sorgu ile cekilip bellekte suzuluyor; arsiv kucuk (yuzlerce satir) ve
    her mac icin ayri sorgu atmak listeyi N kat yavaslatirdi.

    champ_id verilmeli: havuz LIGE OZELDIR. Ligler ayni oyunun farkli
    formatlari (5x5 Rush ~7 gol, 3x3 daha az) - birinin arsivi otekinin
    'form' ve 'benzer oranli mac' bilesenlerini bozar.
    """
    where, args = "", ()
    if champ_id is not None:
        where, args = " AND m.champ_id = ?", (champ_id,)
    return _rows(f"""
        SELECT m.event_id, m.champ_id, m.home, m.away, m.start_ts,
               m.score_home, m.score_away, p.p1, p.px, p.p2
        FROM matches m JOIN ({PREMATCH_ODDS}) p ON p.event_id = m.event_id
        WHERE m.status = 'finished' AND m.score_home IS NOT NULL
              AND m.score_away IS NOT NULL AND p.p1 IS NOT NULL
              AND p.p2 IS NOT NULL{where}
        ORDER BY m.start_ts DESC""", args)


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

    Referans set ('prekickoff') varsa o, yoksa acilis seti kullanilir - mac
    basladiktan sonra site oranlari sildigi icin baska kaynak yok.
    """
    now = time.time()
    minutes = _league_match_minutes()
    for m in rows:
        snap = _expectation_snapshot(m["event_id"])
        e = goal_expectation(
            _rows("SELECT g, t, p, coef, blocked FROM odds_values WHERE snapshot_id=?",
                  (snap["id"],))) if snap else None
        m["expect"] = e
        if e:
            _apply_remaining(e, m, now,
                             minutes.get(m.get("champ_id"), LIVE_MATCH_MINUTES))


def _goal_distribution(live: list[dict]) -> dict | None:
    """Bahisci oranlarinin ima ettigi toplam gol dagilimi (market G=9939).

    G=9939 tam bir market: secenekler P=3..13 toplam gol, kitap toplami ~1.2.
    Oranlari olasiliga cevirip marji cikarmak icin normalize ediyoruz.

    Snapshot secimi _attach_expectations ile AYNI olmali (referans set once):
    aksi halde ayni mac icin bu panelin "en olasi" degeri gol beklentisi
    tablosundakiyle uyusmuyor. Bu yuzden secim _expectation_snapshot'ta.
    """
    for m in live:
        snap = _expectation_snapshot(m["event_id"])
        rows = _rows("SELECT p AS goals, coef FROM odds_values "
                     "WHERE g = 9939 AND snapshot_id = ? ORDER BY p",
                     (snap["id"],)) if snap else []
        if not rows:
            continue
        book = sum(1 / r["coef"] for r in rows if r["coef"])
        if not book:
            continue
        return {
            "event_id": m["event_id"], "home": m["home"], "away": m["away"],
            "start_ts": m["start_ts"], "margin": round((book - 1) * 100, 1),
            "bins": [{"goals": int(r["goals"]), "coef": r["coef"],
                      "prob": round(100 * (1 / r["coef"]) / book, 2)}
                     for r in rows if r["coef"]],
        }
    return None


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
