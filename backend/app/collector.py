"""Arka plan toplayici.

Her lig icin canli feed'i periyodik olarak cekip:
  * mac kayitlarini gunceller,
  * her poll'da 1X2 oranini zaman serisine yazar,
  * mac BASLAMADAN once tum market setini bir kez arsivler,
  * feed'den dusen / F=true olan maci bitmis olarak isaretler.

Mac oncesi arsiv kritik: site, mac bitince oranlari tamamen siliyor
(GetGameZip skoru dondurur ama GE bos gelir), yani gecmis oran baska
hicbir yerden geri alinamiyor.
"""
import asyncio
import time

from . import db
from .config import (FINISH_GRACE_SECONDS, MISSING_TICKS_TO_FINISH, POLL_SECONDS,
                     League, load_leagues)
from .feed import FeedClient, flatten_outcomes, parse_match


class Broadcaster:
    """SSE aboneleri icin basit yayin kanali."""

    def __init__(self) -> None:
        self._subs: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=10)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def publish(self, event: dict) -> None:
        for q in list(self._subs):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # yavas abone: bu turu atlar, bir sonrakini alir

    @property
    def count(self) -> int:
        return len(self._subs)


broadcaster = Broadcaster()

# Bir mac oncesi arsivin "tam" sayilmasi icin gereken en az secenek sayisi.
# Gercek setler 98-110 arasi geliyor; bunun altina dusen bir yakalama, oranlarin
# bir kisminin o an askiya alinmis (B=true) oldugu anlamina gelir ve mac
# baslamadan once daha iyisiyle degistirilmelidir.
MIN_PREMATCH_OUTCOMES = 40

# Referans oran seti: macin BASLAMASINA bu kadar saniye kala alinan snapshot.
# Her poll'da tazelenir, boylece elde kalan kayit baslangica en yakin olandir.
# Mac ici oran degisimi bizim icin gecerli degil.
PREKICKOFF_WINDOW = 180
PHASE_OPEN = "prematch"        # ilk gorusteki set (sigorta)
PHASE_REF = "prekickoff"       # referans set - baslangictan hemen once


class Collector:
    def __init__(self) -> None:
        self.leagues: list[League] = []
        self.running = False
        self.last_poll: int | None = None
        self.last_error: str | None = None
        self.poll_count = 0
        self._task: asyncio.Task | None = None

    # ---------------------------------------------------------------- yasam
    async def start(self) -> None:
        db.init_db()
        self.reload_leagues()
        self.running = True
        self._task = asyncio.create_task(self._loop(), name="collector")

    async def stop(self) -> None:
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def reload_leagues(self) -> None:
        self.leagues = [l for l in load_leagues() if l.enabled]
        with db.session() as con:
            for l in self.leagues:
                con.execute(
                    "INSERT INTO leagues(champ_id, name, slug, enabled) VALUES (?,?,?,1) "
                    "ON CONFLICT(champ_id) DO UPDATE SET name=excluded.name, "
                    "slug=excluded.slug, enabled=1",
                    (l.champ_id, l.name, l.slug))

    # ---------------------------------------------------------------- dongu
    async def _loop(self) -> None:
        while self.running:
            started = time.time()
            try:
                await self.poll_once()      # last_error'u kendisi ayarlar
            except asyncio.CancelledError:
                raise
            except Exception as ex:                    # noqa: BLE001
                self.last_error = f"{type(ex).__name__}: {ex}"
                db.log("error", self.last_error)
            elapsed = time.time() - started
            await asyncio.sleep(max(1.0, POLL_SECONDS - elapsed))

    async def poll_once(self) -> dict:
        summary = {"leagues": 0, "matches": 0, "snapshots": 0, "finished": 0,
                   "missed": 0, "failed": 0}
        first_failure = None
        seen: set[int] = set()
        fetched: set[int] = set()      # bu poll'da feed'i basariyla alinan ligler
        async with FeedClient() as feed:
            for league in self.leagues:
                try:
                    raw = await feed.league_matches(league.champ_id, league.virtual)
                except Exception as ex:                # noqa: BLE001
                    summary["failed"] += 1
                    first_failure = first_failure or f"champ {league.champ_id}: {ex}"
                    db.log("error", f"champ {league.champ_id}: {ex}")
                    continue
                res = await self._process(feed, league, raw)
                fetched.add(league.champ_id)
                seen |= res["seen"]
                summary["leagues"] += 1
                for k in ("matches", "snapshots", "missed"):
                    summary[k] += res[k]
        summary["finished"] = self._close_missing(seen, fetched, int(time.time()))
        # Tek bir lig bile cekilemediyse bu bir kesintidir; saglikli gorunmesin.
        self.last_error = first_failure if summary["leagues"] == 0 and self.leagues else None
        self.last_poll = int(time.time())
        self.poll_count += 1
        broadcaster.publish({"type": "poll", "ts": self.last_poll, **summary})
        return summary

    async def _process(self, feed: FeedClient, league: League,
                       raw: list[dict]) -> dict:
        """Bir ligin feed yanitini isler. Kapatma burada YAPILMAZ: feed'den
        dusen maclar poll sonunda tum ligler icin tek seferde degerlendirilir
        (bkz. _close_missing)."""
        now = int(time.time())
        res = {"matches": 0, "snapshots": 0, "missed": 0, "seen": set()}
        seen: set[int] = res["seen"]

        for item in raw:
            try:
                m = parse_match(item, league.champ_id)
            except (TypeError, ValueError):
                continue
            seen.add(m["event_id"])
            res["matches"] += 1
            self._upsert_match(m, now)
            self._insert_tick(m, now)

            # Mac oncesi arsiv: listelenen ve henuz oynanmamis HER mac icin tam
            # market seti tutulur. Eksik yakalandiysa mac baslayana kadar her
            # poll'da yenisiyle degistirilir - mac basladiktan sonra site
            # oranlari siliyor, ikinci sans yok.
            eid = m["event_id"]
            if m["status"] == "scheduled":
                # 1) Acilis seti: ilk goruste bir kez; eksik yakalandiysa yukselt.
                if self._snapshot_state(eid, PHASE_OPEN) != "complete":
                    if await self._snapshot(feed, eid, now, PHASE_OPEN,
                                            strategy="upgrade"):
                        res["snapshots"] += 1
                # 2) Referans set: baslangica yaklasinca her poll'da tazele.
                start = m.get("start_ts") or 0
                if 0 <= start - now <= PREKICKOFF_WINDOW:
                    if await self._snapshot(feed, eid, now, PHASE_REF,
                                            strategy="refresh"):
                        res["snapshots"] += 1
            elif self._snapshot_state(eid, PHASE_REF) != "complete" \
                    and self._snapshot_state(eid, PHASE_OPEN) != "complete":
                res["missed"] += self._mark_missed(eid)

        with db.session() as con:
            con.execute("UPDATE leagues SET last_seen=? WHERE champ_id=?",
                        (now, league.champ_id))
        return res

    # ------------------------------------------------------------ yazicilar
    def _upsert_match(self, m: dict, now: int) -> None:
        with db.session() as con:
            con.execute("""
                INSERT INTO matches(event_id, champ_id, league_name, start_ts, home, away,
                                    home_id, away_id, status, score_home, score_away,
                                    status_text, tourney_id, iteration,
                                    first_seen, last_update, missing)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)
                ON CONFLICT(event_id) DO UPDATE SET
                    status      = excluded.status,
                    score_home  = COALESCE(excluded.score_home, matches.score_home),
                    score_away  = COALESCE(excluded.score_away, matches.score_away),
                    status_text = excluded.status_text,
                    league_name = excluded.league_name,
                    tourney_id  = COALESCE(excluded.tourney_id, matches.tourney_id),
                    iteration   = COALESCE(excluded.iteration, matches.iteration),
                    last_update = excluded.last_update,
                    missing     = 0
            """, (m["event_id"], m["champ_id"], m["league_name"], m["start_ts"],
                  m["home"], m["away"], m["home_id"], m["away_id"], m["status"],
                  m["score_home"], m["score_away"], m["status_text"],
                  m["tourney_id"], m["iteration"], now, now))
            if m["status"] == "finished":
                con.execute("UPDATE matches SET finished_at=COALESCE(finished_at,?) "
                            "WHERE event_id=?", (now, m["event_id"]))

    def _insert_tick(self, m: dict, now: int) -> None:
        if m["o1"] is None and m["ox"] is None and m["o2"] is None:
            return                       # oranlar askiya alinmis
        with db.session() as con:
            con.execute(
                "INSERT OR IGNORE INTO odds_ticks(event_id, taken_at, phase, score_home, "
                "score_away, o1, ox, o2) VALUES (?,?,?,?,?,?,?,?)",
                (m["event_id"], now, m["status"], m["score_home"], m["score_away"],
                 m["o1"], m["ox"], m["o2"]))

    def _snapshot_state(self, event_id: int, phase: str = "prematch") -> str:
        """'none' | 'partial' | 'complete'

        Sadece kaydin varligina bakmak yetmez: oranlarin bir kismi askiya
        alinmisken cekilen snapshot birkac secenekle doner ve oyle kalirsa
        mac oncesi set kalici olarak eksik kalir.
        """
        with db.session() as con:
            row = con.execute(
                "SELECT s.market_count, "
                "  EXISTS(SELECT 1 FROM odds_values v "
                "         WHERE v.snapshot_id=s.id AND v.g=1) AS has_main "
                "FROM odds_snapshots s WHERE s.event_id=? AND s.phase=?",
                (event_id, phase)).fetchone()
        if row is None:
            return "none"
        if row["has_main"] and (row["market_count"] or 0) >= MIN_PREMATCH_OUTCOMES:
            return "complete"
        return "partial"

    def _mark_missed(self, event_id: int) -> int:
        """Mac, tam bir mac-oncesi arsiv olmadan basladi/bitti: kalici isaret."""
        with db.session() as con:
            cur = con.execute(
                "UPDATE matches SET prematch_missed=1 "
                "WHERE event_id=? AND COALESCE(prematch_missed,0)=0", (event_id,))
            return cur.rowcount or 0

    async def _snapshot(self, feed: FeedClient, event_id: int, now: int,
                        phase: str = PHASE_OPEN, strategy: str = "upgrade") -> bool:
        """strategy:
            upgrade - yalnizca eldekinden daha dolu bir set gelirse degistir
            refresh - tam bir set geldiyse her seferinde degistir (referans set)
        """
        try:
            game = await feed.game_full(event_id)
        except Exception as ex:                        # noqa: BLE001
            db.log("warn", f"snapshot {event_id}: {ex}")
            return False
        groups = (game or {}).get("GE") or []
        values = []
        for ge in groups:
            for o in flatten_outcomes(ge.get("E")):
                values.append((ge.get("G"), ge.get("GS"), o.get("T"), o.get("P"),
                               o.get("C"), 1 if o.get("B") else 0))
        if not values:
            return False
        complete = (len(values) >= MIN_PREMATCH_OUTCOMES
                    and any(v[0] == 1 for v in values))
        with db.session() as con:
            old = con.execute("SELECT id, market_count FROM odds_snapshots "
                              "WHERE event_id=? AND phase=?",
                              (event_id, phase)).fetchone()
            if old:
                if strategy == "refresh":
                    # Kismi bir cekim, elimizdeki tam seti bozmasin.
                    if not complete:
                        return False
                elif len(values) <= (old["market_count"] or 0):
                    return False
                con.execute("DELETE FROM odds_values WHERE snapshot_id=?", (old["id"],))
                con.execute("DELETE FROM odds_snapshots WHERE id=?", (old["id"],))
            cur = con.execute(
                "INSERT OR IGNORE INTO odds_snapshots(event_id, taken_at, phase, "
                "market_count) VALUES (?,?,?,?)", (event_id, now, phase, len(values)))
            if not cur.lastrowid:
                return False
            sid = cur.lastrowid
            con.executemany(
                "INSERT INTO odds_values(snapshot_id, g, gs, t, p, coef, blocked) "
                "VALUES (?,?,?,?,?,?,?)", [(sid, *v) for v in values])
        db.log("info", f"snapshot[{phase}] {event_id}: {len(values)} oran")
        broadcaster.publish({"type": "snapshot", "event_id": event_id,
                             "phase": phase, "count": len(values)})
        return True

    def _close_missing(self, seen: set[int], fetched: set[int], now: int) -> int:
        """Feed'den dusen maclari bitmis say - TUM acik kayitlar icin.

        Lig dongusunun icinde degil, poll'un sonunda bir kez calisir. Bunun
        sebebi: leagues.json'dan cikarilan ya da enabled=false yapilan bir
        ligin kayitlarini lig kapsamli bir tarama hic ziyaret etmez, ama
        /api/live ve /api/dashboard lig filtresi uygulamadigi icin bu kayitlar
        panoda "yaklasan" olarak asili kalir.

        seen    : bu poll'da feed'de gorulen event id'leri
        fetched : feed'i basariyla alinan lig id'leri (ag hatasi alan lig
                  buraya girmez; onun maclari bu tur hic degerlendirilmez -
                  gecici bir kesinti maclari bitirmemeli)
        """
        configured = {l.champ_id for l in self.leagues}
        with db.session() as con:
            rows = con.execute(
                "SELECT event_id, champ_id, missing, score_home, start_ts "
                "FROM matches WHERE status != 'finished'").fetchall()
            closed = 0
            for r in rows:
                if r["event_id"] in seen:
                    continue
                tracked = r["champ_id"] in configured
                if tracked and r["champ_id"] not in fetched:
                    continue
                # Baslama saatinin uzerinden bu kadar gectiyse mac feed'e geri
                # donmeyecektir.
                stale = bool(r["start_ts"]) and now - r["start_ts"] > FINISH_GRACE_SECONDS
                missing = (r["missing"] or 0) + 1
                if tracked:
                    # Skor gelmisse mac oynandi. Skor yoksa yas sinirini bekleriz:
                    # baslamamis bir mac feed'den gecici olarak dusebilir.
                    done = (missing >= MISSING_TICKS_TO_FINISH
                            and (r["score_home"] is not None or stale))
                else:
                    # Ligi artik izlemiyoruz: bu kaydi bir daha kimse gormeyecek,
                    # tek olcut yas.
                    done = stale
                if done:
                    con.execute("UPDATE matches SET status='finished', missing=?, "
                                "finished_at=COALESCE(finished_at,?) WHERE event_id=?",
                                (missing, now, r["event_id"]))
                    closed += 1
                else:
                    con.execute("UPDATE matches SET missing=? WHERE event_id=?",
                                (missing, r["event_id"]))
        if closed:
            broadcaster.publish({"type": "finished", "count": closed})
        return closed


collector = Collector()
