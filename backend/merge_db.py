#!/usr/bin/env python3
"""Iki betodds veritabanini birlestirir (kaynak -> hedef).

    python backend/merge_db.py eski.db                     # data/betodds.db'ye
    python backend/merge_db.py eski.db --hedef baska.db
    python backend/merge_db.py eski.db --dene              # yazmadan rapor

Neden duz bir 'INSERT' yetmiyor:

  * odds_snapshots.id her iki veritabaninda da 1'den baslar. odds_values
    yalnizca snapshot_id tasidigi icin, id'ler yeniden eslenmeden kopyalanan
    oranlar BASKA bir macin snapshot'ina baglanir. Bu betik her snapshot'i
    hedefte yeni bir id ile olusturup degerleri o id'ye yazar.

  * Ayni mac iki tarafta da olabilir. Secim kurallari:
      - matches      : daha 'tam' olan kazanir (bitmis + skoru olan > canli >
                       baslamamis; esitlikte last_update buyuk olan)
      - odds_snapshots: ayni (event_id, phase) icin market_count'u BUYUK olan
                       kazanir - eksik yakalanmis set tam olani ezmesin
      - odds_ticks   : (event_id, taken_at) benzersiz; mukerrer olan atlanir
      - season_tables: fetched_at daha yeni olan kazanir

  * collector_log tasinmaz (yalnizca gunluk gurultusu).

Hedef veritabani yazmadan once yedeklenir: <hedef>.bak-<zaman>

Toplayici CALISIRKEN de calistirilabilir (SQLite WAL + tek islem), ama en
temizi uygulamayi durdurup calistirmaktir.
"""
import argparse
import os
import shutil
import sqlite3
import sys
import time


def cols(con, table):
    return [r["name"] for r in con.execute(f"PRAGMA table_info({table})")]


def common_cols(src, dst, table):
    """Iki semada da bulunan sutunlar.

    Eski bir veritabaninda migration ile eklenen sutunlar (or.
    matches.prematch_missed) eksik olabilir; kesisim disindakiler hedefteki
    varsayilanlarina birakilir.
    """
    return [c for c in cols(src, table) if c in set(cols(dst, table))]


def completeness(row):
    """Bir mac kaydinin 'tamlik' puani - hangi kaydin korunacagini belirler."""
    score = {"finished": 3, "live": 2, "scheduled": 1}.get(row["status"], 0)
    if row["score_home"] is not None and row["score_away"] is not None:
        score += 4
    return (score, row["last_update"] or 0)


def merge(src_path, dst_path, dry=False):
    if not os.path.exists(src_path):
        sys.exit(f"kaynak bulunamadi: {src_path}")
    if not os.path.exists(dst_path):
        sys.exit(f"hedef bulunamadi: {dst_path}")
    if os.path.abspath(src_path) == os.path.abspath(dst_path):
        sys.exit("kaynak ve hedef ayni dosya")

    if not dry:
        bak = f"{dst_path}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(dst_path, bak)
        print(f"yedek: {bak}")

    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    dst = sqlite3.connect(dst_path)
    src.row_factory = dst.row_factory = sqlite3.Row
    dst.execute("PRAGMA journal_mode=WAL")
    dst.execute("PRAGMA busy_timeout=15000")

    stat = {k: 0 for k in (
        "lig_eklendi", "mac_eklendi", "mac_guncellendi", "mac_korundu",
        "snapshot_eklendi", "snapshot_degistirildi", "snapshot_korundu",
        "oran_eklendi", "tick_eklendi", "tick_mukerrer", "sezon_eklendi",
        "sezon_guncellendi")}

    def counts(con, label):
        return {t: con.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
                for t in ("matches", "odds_snapshots", "odds_values",
                          "odds_ticks", "season_tables")}

    before = counts(dst, "hedef")
    print(f"kaynak : {counts(src, 'kaynak')}")
    print(f"hedef  : {before}")

    try:
        dst.execute("BEGIN")

        # ------------------------------------------------------------ ligler
        c = common_cols(src, dst, "leagues")
        for r in src.execute("SELECT * FROM leagues"):
            hit = dst.execute("SELECT champ_id FROM leagues WHERE champ_id=?",
                              (r["champ_id"],)).fetchone()
            if not hit:
                dst.execute(
                    f"INSERT INTO leagues ({','.join(c)}) "
                    f"VALUES ({','.join('?' * len(c))})", tuple(r[x] for x in c))
                stat["lig_eklendi"] += 1

        # ------------------------------------------------------------ maclar
        c = common_cols(src, dst, "matches")
        for r in src.execute("SELECT * FROM matches"):
            cur = dst.execute("SELECT * FROM matches WHERE event_id=?",
                              (r["event_id"],)).fetchone()
            if not cur:
                dst.execute(
                    f"INSERT INTO matches ({','.join(c)}) "
                    f"VALUES ({','.join('?' * len(c))})", tuple(r[x] for x in c))
                stat["mac_eklendi"] += 1
            elif completeness(r) > completeness(cur):
                upd = [x for x in c if x != "event_id"]
                dst.execute(
                    f"UPDATE matches SET {','.join(x + '=?' for x in upd)} "
                    f"WHERE event_id=?",
                    tuple(r[x] for x in upd) + (r["event_id"],))
                stat["mac_guncellendi"] += 1
            else:
                stat["mac_korundu"] += 1

        # ----------------------------------------- snapshot'lar + oran degerleri
        vc = common_cols(src, dst, "odds_values")
        for s in src.execute("SELECT * FROM odds_snapshots"):
            cur = dst.execute(
                "SELECT * FROM odds_snapshots WHERE event_id=? AND phase=?",
                (s["event_id"], s["phase"])).fetchone()
            if cur:
                # Tam olan set kazanir; esitlikte hedefteki kalir.
                if (s["market_count"] or 0) <= (cur["market_count"] or 0):
                    stat["snapshot_korundu"] += 1
                    continue
                dst.execute("DELETE FROM odds_values WHERE snapshot_id=?",
                            (cur["id"],))
                dst.execute("DELETE FROM odds_snapshots WHERE id=?", (cur["id"],))
                stat["snapshot_degistirildi"] += 1
            else:
                stat["snapshot_eklendi"] += 1

            # id VERILMEDEN ekleniyor -> hedef kendi id'sini uretir.
            cur_ins = dst.execute(
                "INSERT INTO odds_snapshots (event_id, taken_at, phase, market_count) "
                "VALUES (?,?,?,?)",
                (s["event_id"], s["taken_at"], s["phase"], s["market_count"]))
            new_id = cur_ins.lastrowid
            rows = src.execute("SELECT * FROM odds_values WHERE snapshot_id=?",
                               (s["id"],)).fetchall()
            if rows:
                fields = [x for x in vc if x != "snapshot_id"]
                dst.executemany(
                    f"INSERT INTO odds_values (snapshot_id,{','.join(fields)}) "
                    f"VALUES ({','.join('?' * (len(fields) + 1))})",
                    [(new_id,) + tuple(r[x] for x in fields) for r in rows])
                stat["oran_eklendi"] += len(rows)

        # ------------------------------------------------------------ tickler
        c = [x for x in common_cols(src, dst, "odds_ticks") if x != "id"]
        for r in src.execute("SELECT * FROM odds_ticks"):
            cur_ins = dst.execute(
                f"INSERT OR IGNORE INTO odds_ticks ({','.join(c)}) "
                f"VALUES ({','.join('?' * len(c))})", tuple(r[x] for x in c))
            if cur_ins.rowcount:
                stat["tick_eklendi"] += 1
            else:
                stat["tick_mukerrer"] += 1

        # ------------------------------------------------------ sezon tablolari
        c = common_cols(src, dst, "season_tables")
        for r in src.execute("SELECT * FROM season_tables"):
            cur = dst.execute(
                "SELECT fetched_at FROM season_tables "
                "WHERE tourney_id=? AND iteration=? AND team=?",
                (r["tourney_id"], r["iteration"], r["team"])).fetchone()
            if not cur:
                dst.execute(
                    f"INSERT INTO season_tables ({','.join(c)}) "
                    f"VALUES ({','.join('?' * len(c))})", tuple(r[x] for x in c))
                stat["sezon_eklendi"] += 1
            elif (r["fetched_at"] or 0) > (cur["fetched_at"] or 0):
                dst.execute(
                    f"INSERT OR REPLACE INTO season_tables ({','.join(c)}) "
                    f"VALUES ({','.join('?' * len(c))})", tuple(r[x] for x in c))
                stat["sezon_guncellendi"] += 1

        if dry:
            dst.execute("ROLLBACK")
            print("\n--- DENEME: hicbir sey yazilmadi ---")
        else:
            dst.execute("COMMIT")
    except Exception:
        dst.execute("ROLLBACK")
        raise

    print("\nsonuc:")
    for k, v in stat.items():
        if v:
            print(f"  {k:22} {v}")
    if not dry:
        after = counts(dst, "hedef")
        print("\nhedef:")
        for t in before:
            print(f"  {t:16} {before[t]:6} -> {after[t]:6}  ({after[t]-before[t]:+d})")

        # Yetim kalan deger var mi? (id yeniden eslemesi tuttu mu)
        orphan = dst.execute(
            "SELECT COUNT(*) c FROM odds_values v LEFT JOIN odds_snapshots s "
            "ON s.id = v.snapshot_id WHERE s.id IS NULL").fetchone()["c"]
        print(f"\nsahipsiz oran degeri: {orphan}" + (" (SORUN VAR)" if orphan else " ✓"))
    src.close()
    dst.close()


if __name__ == "__main__":
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description="betodds veritabanlarini birlestirir")
    ap.add_argument("kaynak", help="birlestirilecek eski veritabani")
    ap.add_argument("--hedef", default=os.path.join(here, "data", "betodds.db"))
    ap.add_argument("--dene", action="store_true",
                    help="yazmadan ne olacagini gosterir")
    a = ap.parse_args()
    merge(a.kaynak, a.hedef, a.dene)
