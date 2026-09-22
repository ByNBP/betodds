"""SQLite semasi ve erisim yardimcilari.

Basit ve tek dosyalik tutuldu; collector tek yazar, API sadece okur.
"""
import os
import sqlite3
import time
from contextlib import contextmanager

from .config import DATA_DIR, DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS leagues (
  champ_id   INTEGER PRIMARY KEY,
  name       TEXT,
  slug       TEXT,
  sport_id   INTEGER,
  sport_name TEXT,
  enabled    INTEGER DEFAULT 1,
  last_seen  INTEGER
);

CREATE TABLE IF NOT EXISTS matches (
  event_id    INTEGER PRIMARY KEY,
  champ_id    INTEGER NOT NULL,
  league_name TEXT,
  start_ts    INTEGER,
  home        TEXT,
  away        TEXT,
  home_id     INTEGER,
  away_id     INTEGER,
  status      TEXT DEFAULT 'scheduled',   -- scheduled | live | finished
  score_home  INTEGER,
  score_away  INTEGER,
  status_text TEXT,
  tourney_id  INTEGER,
  iteration   INTEGER,
  first_seen  INTEGER,
  last_update INTEGER,
  finished_at INTEGER,
  missing     INTEGER DEFAULT 0,
  -- Mac basladiginda elimizde tam bir mac-oncesi arsiv yoksa 1 olur.
  -- Geriye donuk doldurulamaz (site bitmis macin oranlarini siliyor),
  -- bu yuzden kapsama acigini sayabilmek icin kalici olarak isaretliyoruz.
  prematch_missed INTEGER DEFAULT 0,
  -- Kaydin kaynagi: NULL = toplayicinin kendi yakalamasi, 'bulten' =
  -- disaridan ice aktarildi (backend/import_bulletin.py).
  source      TEXT
);
CREATE INDEX IF NOT EXISTS ix_matches_champ  ON matches(champ_id, start_ts DESC);
CREATE INDEX IF NOT EXISTS ix_matches_status ON matches(status, start_ts DESC);

-- Mac oncesi cekilen tam market seti. Mac bitince site oranlari siliyor,
-- bu yuzden phase='prematch' kaydi tek kalici kaynak.
CREATE TABLE IF NOT EXISTS odds_snapshots (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id     INTEGER NOT NULL,
  taken_at     INTEGER NOT NULL,
  phase        TEXT NOT NULL,
  market_count INTEGER,
  UNIQUE(event_id, phase)
);
CREATE TABLE IF NOT EXISTS odds_values (
  snapshot_id INTEGER NOT NULL,
  g           INTEGER,
  gs          INTEGER,
  t           INTEGER,
  p           REAL,
  coef        REAL,
  blocked     INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_odds_values_snap ON odds_values(snapshot_id);

-- Oran hareketi zaman serisi (her poll'da 1X2).
CREATE TABLE IF NOT EXISTS odds_ticks (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id   INTEGER NOT NULL,
  taken_at   INTEGER NOT NULL,
  phase      TEXT,
  score_home INTEGER,
  score_away INTEGER,
  o1 REAL, ox REAL, o2 REAL
);
CREATE INDEX IF NOT EXISTS ix_ticks_event ON odds_ticks(event_id, taken_at);
-- Ayni ani iki kez yazmayi engeller: importer'in tekrar calistirilmasi ve
-- collector'in ust uste binen poll'lari mukerrer satir uretmesin.
CREATE UNIQUE INDEX IF NOT EXISTS ux_ticks_event_time ON odds_ticks(event_id, taken_at);

-- eventsstat.com'dan gelen sezon (iteration) puan durumlari.
CREATE TABLE IF NOT EXISTS season_tables (
  champ_id   INTEGER,
  tourney_id INTEGER NOT NULL,
  iteration  INTEGER NOT NULL,
  team       TEXT NOT NULL,
  pos        INTEGER,
  played     INTEGER, wins INTEGER, draws INTEGER, losses INTEGER,
  gf         INTEGER, ga INTEGER, points INTEGER,
  fetched_at INTEGER,
  PRIMARY KEY (tourney_id, iteration, team)
);

-- eventsstat sezon sayfasindaki capraz sonuc tablosu: her hucre BIR mac.
-- 'positions' dizisinde satir takimi EVDE, sutun takimi deplasmandadir
-- (dogrulandi: hucre toplamlari puan durumunun averajiyla birebir tutuyor).
-- Oran YOK - bu kayitlar bizim arsivimizden degil, sitenin sezon ozetinden.
CREATE TABLE IF NOT EXISTS season_matches (
  tourney_id INTEGER NOT NULL,
  iteration  INTEGER NOT NULL,
  home       TEXT NOT NULL,
  away       TEXT NOT NULL,
  score_home INTEGER,
  score_away INTEGER,
  fetched_at INTEGER,
  PRIMARY KEY (tourney_id, iteration, home, away)
);
CREATE INDEX IF NOT EXISTS ix_season_matches_pair
  ON season_matches(tourney_id, home, away);

CREATE TABLE IF NOT EXISTS collector_log (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  ts        INTEGER,
  level     TEXT,
  message   TEXT
);
"""


def connect() -> sqlite3.Connection:
    os.makedirs(DATA_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=15000")
    con.execute("PRAGMA foreign_keys=ON")
    return con


@contextmanager
def session():
    con = connect()
    try:
        yield con
        con.commit()
    finally:
        con.close()


MIGRATIONS = [
    ("matches", "prematch_missed", "INTEGER DEFAULT 0"),
    # Kaydin nereden geldigi. Bos/NULL = toplayicinin kendi yakalamasi.
    # 'bulten' = disaridan ice aktarilan PDF listesi (import_bulletin.py):
    # oranlari birebir dogrulandi ama skorlari kismi olabiliyor, ve mac
    # oncesi tam market seti YOK - bu yuzden "beklenen gol" hesaplanamaz.
    ("matches", "source", "TEXT"),
]


def init_db() -> None:
    with session() as con:
        con.executescript(SCHEMA)
        # Eski veritabanlarina eksik sutunlari ekle
        for table, column, decl in MIGRATIONS:
            cols = {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
            if column not in cols:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def log(level: str, message: str) -> None:
    try:
        with session() as con:
            con.execute("INSERT INTO collector_log(ts, level, message) VALUES (?,?,?)",
                        (int(time.time()), level, message[:2000]))
            # log tablosunu sinirli tut
            con.execute("DELETE FROM collector_log WHERE id < "
                        "(SELECT MAX(id) - 2000 FROM collector_log)")
    except sqlite3.Error:
        pass
