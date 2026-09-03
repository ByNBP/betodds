#!/usr/bin/env python3
"""Onceki toplayici dosyalarini veritabanina aktarir.

Kaynaklar (varsa):
  ~/fc26-history.csv        biten maclar + acilis/son 1X2
  ~/fc26-odds-ticks.jsonl   oran hareketi
  ~/fc26-odds-full.jsonl    mac oncesi tam market snapshot'lari
  ~/.fc26-league/<t>-<i>.json  eventsstat sezon tablolari
"""
import csv
import json
import os
import re
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import db                                    # noqa: E402

HOME = os.path.expanduser("~")
CHAMP = 2986291
LEAGUE = "FC 26. 5x5 Rush. Süper Lig"
TOURNEY = 149


def ts(text: str, fmt: str = "%Y-%m-%d %H:%M:%S") -> int:
    try:
        return int(datetime.strptime(text, fmt).timestamp())
    except (ValueError, TypeError):
        return 0


def num(v):
    if v in (None, "", "-"):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def import_history(con) -> int:
    path = os.path.join(HOME, "fc26-history.csv")
    if not os.path.exists(path):
        return 0
    n = 0
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            eid = int(r["event_id"])
            start = ts(r["baslangic"], "%Y-%m-%d %H:%M")
            fin = ts(r.get("kayit", ""))
            con.execute("""INSERT INTO matches(event_id, champ_id, league_name,
                    start_ts, home, away, status, score_home, score_away,
                    tourney_id, first_seen, last_update, finished_at)
                VALUES (?,?,?,?,?,?, 'finished', ?,?,?,?,?,?)
                ON CONFLICT(event_id) DO UPDATE SET
                    status='finished',
                    score_home=COALESCE(matches.score_home, excluded.score_home),
                    score_away=COALESCE(matches.score_away, excluded.score_away),
                    finished_at=COALESCE(matches.finished_at, excluded.finished_at)""",
                (eid, CHAMP, LEAGUE, start, r["ev"], r["deplasman"],
                 int(r["ev_skor"]), int(r["dep_skor"]), TOURNEY, fin, fin, fin))
            n += 1
    return n


def import_ticks(con) -> int:
    path = os.path.join(HOME, "fc26-odds-ticks.jsonl")
    if not os.path.exists(path):
        return 0
    n = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            eid = int(d["event_id"])
            taken = ts(d["t"])
            score = d.get("skor") or [None, None]
            phase = "live" if d.get("faz") == "canli" else "scheduled"
            # tick'lerden mac kaydini da tureti (CSV'de olmayan maclar icin)
            con.execute("""INSERT OR IGNORE INTO matches(event_id, champ_id,
                    league_name, home, away, status, first_seen, last_update)
                VALUES (?,?,?,?,?,?,?,?)""",
                (eid, CHAMP, LEAGUE, d.get("ev"), d.get("dep"), phase, taken, taken))
            o = d.get("oran") or {}
            con.execute("""INSERT OR IGNORE INTO odds_ticks(event_id, taken_at, phase,
                    score_home, score_away, o1, ox, o2) VALUES (?,?,?,?,?,?,?,?)""",
                (eid, taken, phase, score[0], score[1],
                 num(o.get("1")), num(o.get("X")), num(o.get("2"))))
            n += 1
    return n


def import_full(con) -> int:
    path = os.path.join(HOME, "fc26-odds-full.jsonl")
    if not os.path.exists(path):
        return 0
    n = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            eid = int(d["event_id"])
            taken = ts(d["t"])
            values = [(m.get("G"), m.get("GS"), o.get("T"), o.get("P"),
                       o.get("C"), 1 if o.get("B") else 0)
                      for m in d.get("marketler", []) for o in m.get("secenekler", [])]
            if not values:
                continue
            con.execute("""INSERT OR IGNORE INTO matches(event_id, champ_id,
                    league_name, start_ts, home, away, status, first_seen, last_update)
                VALUES (?,?,?,?,?,?, 'scheduled', ?,?)""",
                (eid, CHAMP, LEAGUE, ts(d.get("baslangic", ""), "%Y-%m-%d %H:%M"),
                 d.get("ev"), d.get("dep"), taken, taken))
            cur = con.execute("INSERT OR IGNORE INTO odds_snapshots(event_id, taken_at, "
                              "phase, market_count) VALUES (?,?,'prematch',?)",
                              (eid, taken, len(values)))
            if not cur.lastrowid:
                continue
            con.executemany("INSERT INTO odds_values(snapshot_id, g, gs, t, p, coef, "
                            "blocked) VALUES (?,?,?,?,?,?,?)",
                            [(cur.lastrowid, *v) for v in values])
            n += 1
    return n


def import_seasons(con) -> int:
    d = os.path.join(HOME, ".fc26-league")
    if not os.path.isdir(d):
        return 0
    now = int(time.time())
    n = 0
    for fn in sorted(os.listdir(d)):
        m = re.match(r"(\d+)-(\d+)\.json$", fn)
        if not m:
            continue
        tourney, it = int(m.group(1)), int(m.group(2))
        with open(os.path.join(d, fn), encoding="utf-8") as f:
            table = json.load(f)
        con.executemany("""INSERT OR REPLACE INTO season_tables(champ_id, tourney_id,
                iteration, team, pos, played, wins, draws, losses, gf, ga, points,
                fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [(CHAMP, tourney, it, r["takim"], r["sira"], r["o"], r["g"], r["b"],
              r["m"], r["at"], r["ye"], r["p"], now) for r in table])
        n += 1
    return n


def main():
    db.init_db()
    with db.session() as con:
        con.execute("INSERT OR IGNORE INTO leagues(champ_id, name, slug, enabled) "
                    "VALUES (?,?,?,1)",
                    (CHAMP, LEAGUE, "fc26-5x5-rush-superleague"))
        h = import_history(con)
        t = import_ticks(con)
        fl = import_full(con)
        s = import_seasons(con)
        # tick'lerden turetilen maclarin skorunu son tick'ten tamamla
        con.execute("""UPDATE matches SET
                score_home = COALESCE(score_home, (SELECT score_home FROM odds_ticks k
                    WHERE k.event_id=matches.event_id ORDER BY taken_at DESC LIMIT 1)),
                score_away = COALESCE(score_away, (SELECT score_away FROM odds_ticks k
                    WHERE k.event_id=matches.event_id ORDER BY taken_at DESC LIMIT 1)),
                start_ts   = COALESCE(start_ts, first_seen)
            WHERE score_home IS NULL OR start_ts IS NULL""")
        # Ice aktarilan eski kayitlar 'scheduled' kalmasin: bu maclar coktan
        # bitti, aksi halde canli ekranda hayalet satir olarak gorunurler.
        con.execute("UPDATE matches SET status='finished', "
                    "finished_at=COALESCE(finished_at, last_update) "
                    "WHERE status != 'finished' AND start_ts < ?",
                    (int(time.time()) - 3 * 3600,))
    print(f"mac (csv): {h} | tick: {t} | snapshot: {fl} | sezon: {s}")


if __name__ == "__main__":
    main()
