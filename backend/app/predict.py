"""Gol tahmini: dort bilesenin agirlikli harmani.

Bilesenler (her biri tek basina bir 'toplam gol' tahmini uretir):

  odds    Mac oncesi oranlarin ima ettigi beklenti (markets.goal_expectation).
          Bahiscinin kendi modelini okur.
  season  Sezon puan durumlarindan cikan takim gucu: atak = attigi gol,
          defans = yedigi gol; lig ortalamasina gore carpan. Onceki sezonlar
          + guncel sezon (agirligi ayri, cunku az mac oynanmis olur).
  form    BIZIM arsivimizdeki lig maclarindan takim formu. Az mac oynamis
          takim lig ortalamasina cekilir (buzusme).
  similar Baslangic oranlari (1 ve 2 ayagi) bu maca +/-gap yakin olan BITEN
          maclarin gol ortalamasi.
  venue   Saha bazli form: ev sahibinin YALNIZCA ev maclarindaki, deplasmanin
          YALNIZCA deplasman maclarindaki uretimi. 'form' bileseni iki sahayi
          birlikte sayar; bu ayrimi gormek icin ayri bir etmen.

Agirliklar arsiv uzerinde leave-one-out olculerek secildi; olculen degerler
config.PREDICT_WEIGHTS aciklamasinda. Bir bilesen o mac icin uretilemezse
agirligi kalanlar arasinda oransal dagitilir - eksik bilesen tahmini
sifira dogru cekmez.

Benzerlik olcusu mac ONCESI oran (p1/p2) - canli oran mac ici hareketi tasidigi
icin karsilastirmaya uygun degil (bkz. api.PREMATCH_ODDS). Berabere ayagi (px)
benzerlige KATILMAZ: bu ligde X, 1/2'den neredeyse tamamen turetilebiliyor.

Ev/deplasman ayrimi: her bilesen kendi ev PAYINI verir, paylar ayni
agirliklarla harmanlanir ve toplamla carpilir. Sabit bir ev sahibi avantaji
EKLENMEZ - arsivde tersi olculdu (ev 3.37, deplasman 3.70 gol; n=43). Saha
etkisi bunun yerine 'venue' bileseniyle takim bazinda olculur.
"""
import statistics as st

from .config import EXPECT_OFFSET, EXPECT_STEP
from .markets import calibrate_total


def _agg(vals):
    return {"min": min(vals), "max": max(vals),
            "avg": round(st.mean(vals), 2),
            "median": round(st.median(vals), 2)}


def similar(p1, p2, pool, gap, exclude=None):
    """Baslangic oranlari (p1, p2) her ikisi de +/-gap icinde kalan biten maclar.

    pool: [{'event_id','home','away','start_ts','score_home','score_away',
            'p1','px','p2'}] - skoru ve mac oncesi orani bilinen biten maclar.
    Sonuc oran uzakligina gore yakindan uzaga siralidir.
    """
    if p1 is None or p2 is None:
        return []
    out = []
    for r in pool:
        if exclude is not None and r["event_id"] == exclude:
            continue
        if r["p1"] is None or r["p2"] is None:
            continue
        d1, d2 = abs(r["p1"] - p1), abs(r["p2"] - p2)
        if d1 <= gap and d2 <= gap:
            out.append({**r,
                        "total": r["score_home"] + r["score_away"],
                        "d1": round(d1, 2), "d2": round(d2, 2),
                        "dist": round(d1 + d2, 3)})
    out.sort(key=lambda r: r["dist"])
    return out


def goal_prediction(p1, p2, pool, gap, exclude=None, detail=False, limit=None):
    """Benzer oranli maclarin gol ortalamasi.

    Tahmin = ornekteki maclarin toplam gol ORTALAMASI. Agirliklandirma yok:
    hangi macin sayildigi ekranda tek tek gorulebilsin diye kasitli olarak
    seffaf tutuldu.

    limit verilirse yalnizca EN YAKIN o kadar ornek sayilir. Kesme
    ortalamadan ONCE yapilir: ekranda listelenen maclar ile ortalamanin
    dayandigi maclar ayni kume olmali, aksi halde tablonun alt satirindaki
    ortalama tablodaki satirlardan hesaplanamaz gorunurdu.
    'n_all' kesilmeden onceki eslesme sayisidir.

    n kucukse ortalama gurultuludur; 'n' her zaman sonuca konur ve arayuz onu
    gizlemez. Ornek bulunamazsa n=0 doner (uydurulmus bir sayi degil).
    """
    if p1 is None or p2 is None:
        return None
    sample = similar(p1, p2, pool, gap, exclude)
    n_all = len(sample)
    if limit is not None:
        sample = sample[:limit]
    out = {
        "gap": gap,
        "ref": {"p1": p1, "p2": p2},
        "n": len(sample),
        "n_all": n_all,
        "limit": limit,
        "total": None, "home": None, "away": None,
        "median": None, "min": None, "max": None, "stdev": None,
    }
    if not sample:
        return out

    totals = [s["total"] for s in sample]
    out["total"] = round(st.mean(totals), 2)
    out["median"] = round(st.median(totals), 2)
    out["min"], out["max"] = min(totals), max(totals)
    out["stdev"] = round(st.pstdev(totals), 2) if len(totals) > 1 else 0.0
    out["home"] = round(st.mean([s["score_home"] for s in sample]), 2)
    out["away"] = round(st.mean([s["score_away"] for s in sample]), 2)

    if detail:
        out["samples"] = sample
        out["histogram"] = [{"goals": g, "n": totals.count(g)}
                            for g in sorted(set(totals))]
    return out


def backtest(pool, gap):
    """Yontemin arsiv uzerindeki isabeti (leave-one-out).

    Her biten mac icin kendisi disarida birakilarak tahmin uretilir ve gercek
    sonucla karsilastirilir. Yaninda iki referans:
      - arsiv geneli ortalama (hicbir benzerlik kullanmayan taban)
    Tahminin bu tabandan iyi olup olmadigi ekranda gorunsun diye buradan
    donuyor; arsiv buyudukce dogal olarak degisir.
    """
    errs, base_errs = [], []
    for a in pool:
        rest = [b for b in pool if b["event_id"] != a["event_id"]]
        if not rest:
            continue
        actual = a["score_home"] + a["score_away"]
        grand = st.mean([b["score_home"] + b["score_away"] for b in rest])
        base_errs.append(abs(grand - actual))
        s = similar(a["p1"], a["p2"], rest, gap)
        if s:
            errs.append(abs(st.mean([x["total"] for x in s]) - actual))
    if not base_errs:
        return None
    return {
        "n": len(errs),
        "mae": round(st.mean(errs), 2) if errs else None,
        "baseline_mae": round(st.mean(base_errs), 2),
        "baseline_avg": round(st.mean(
            [b["score_home"] + b["score_away"] for b in pool]), 2),
    }


# ==========================================================================
#  Bilesenler
# ==========================================================================

def season_strength(season_rows, n_prev, w_cur):
    """Sezon puan durumlarindan takim basina atak/defans carpani.

    season_rows: [{'iteration','team','played','gf','ga'}] - season_tables.
    n_prev     : guncelden geriye kac sezon kullanilacak.
    w_cur      : GUNCEL sezonun agirligi; kalan agirlik onceki sezonlara esit
                 dagitilir. Guncel sezon az mac oynanmis olabilecegi icin
                 tam agirlik verilmez (olculdu: w_cur=1.0 -> MAE 1.82,
                 w_cur=0.2 -> MAE 1.65).

    Donen: (mu, att, dfn)
      mu  : takim-mac basi lig ortalamasi gol
      att : takim -> attigi golun lig ortalamasina orani  (>1 = golcu)
      dfn : takim -> yedigi golun lig ortalamasina orani  (>1 = zayif defans)
    """
    by_it: dict[int, list] = {}
    for r in season_rows:
        by_it.setdefault(r["iteration"], []).append(r)
    if not by_it:
        return None
    cur = max(by_it)
    its = sorted(by_it, reverse=True)[:n_prev + 1]
    prev = [i for i in its if i != cur]

    gf: dict[str, float] = {}
    ga: dict[str, float] = {}
    wt: dict[str, float] = {}
    for it in its:
        w = w_cur if it == cur else (1 - w_cur) / max(1, len(prev))
        if w <= 0:
            continue
        for r in by_it[it]:
            if not r["played"]:
                continue
            t = r["team"]
            gf[t] = gf.get(t, 0.0) + w * r["gf"] / r["played"]
            ga[t] = ga.get(t, 0.0) + w * r["ga"] / r["played"]
            wt[t] = wt.get(t, 0.0) + w
    if not gf:
        return None
    mu = st.mean([gf[t] / wt[t] for t in gf])
    if mu <= 0:
        return None
    return (mu,
            {t: (gf[t] / wt[t]) / mu for t in gf},
            {t: (ga[t] / wt[t]) / mu for t in ga},
            {"seasons": len(its), "current": cur, "current_weight": w_cur})


def season_component(home, away, strength):
    """Poisson tarzi carpim: lambda = lig_ort x atak x rakip_defans."""
    if not strength:
        return None
    mu, att, dfn, meta = strength
    if home not in att or away not in att or home not in dfn or away not in dfn:
        return None
    lh = mu * att[home] * dfn[away]
    la = mu * att[away] * dfn[home]
    return {
        "total": round(lh + la, 2), "home": round(lh, 2), "away": round(la, 2),
        "detail": {"mu": round(mu, 3),
                   "att_home": round(att[home], 3), "def_home": round(dfn[home], 3),
                   "att_away": round(att[away], 3), "def_away": round(dfn[away], 3),
                   **meta},
    }


def form_component(home, away, pool, k, exclude=None):
    """Kendi arsivimizdeki lig maclarindan takim formu.

    k: buzusme sabiti. w = n/(n+k) ile takimin kendi ortalamasi lig
    ortalamasina cekilir; 2 mac oynamis takim lig ortalamasindan cok
    uzaklasamaz. Olculdu: k=1 en iyi (MAE 1.77), k=20 -> 1.90.
    """
    rest = [r for r in pool if exclude is None or r["event_id"] != exclude]
    if not rest:
        return None
    mu = st.mean([r["score_home"] + r["score_away"] for r in rest]) / 2

    def rate(team):
        sc, cd = [], []
        for r in rest:
            if r["home"] == team:
                sc.append(r["score_home"]); cd.append(r["score_away"])
            elif r["away"] == team:
                sc.append(r["score_away"]); cd.append(r["score_home"])
        if not sc:
            return mu, mu, 0
        w = len(sc) / (len(sc) + k)
        return (w * st.mean(sc) + (1 - w) * mu,
                w * st.mean(cd) + (1 - w) * mu, len(sc))

    ah, dh, nh = rate(home)
    aa, da, na = rate(away)
    lh, la = (ah + da) / 2, (aa + dh) / 2
    return {
        "total": round(lh + la, 2), "home": round(lh, 2), "away": round(la, 2),
        "detail": {"home_played": nh, "away_played": na, "league_avg": round(mu, 2),
                   "home_scored": round(ah, 2), "home_conceded": round(dh, 2),
                   "away_scored": round(aa, 2), "away_conceded": round(da, 2),
                   "shrink_k": k},
    }


def venue_component(home, away, pool, k, exclude=None):
    """Saha bazli form: ev sahibi EVDE, deplasman DEPLASMANDA ne uretiyor.

    'form' bileseninden farki, her takimin yalnizca ilgili sahadaki maclarini
    saymasi. Buzusme de saha bazli: az ev maci oynamis takim lig EV
    ortalamasina, az deplasman maci oynamis takim lig DEPLASMAN ortalamasina
    cekilir - bu ligde ikisi ayni degil (arsivde ev 3.37, deplasman 3.70).
    """
    rest = [r for r in pool if exclude is None or r["event_id"] != exclude]
    if not rest:
        return None
    mu_h = st.mean([r["score_home"] for r in rest])   # lig ev ortalamasi
    mu_a = st.mean([r["score_away"] for r in rest])   # lig deplasman ortalamasi

    def rate(team, at_home):
        """(attigi, yedigi, mac sayisi) - yalnizca ilgili sahadaki maclardan."""
        sc, cd = [], []
        for r in rest:
            if at_home and r["home"] == team:
                sc.append(r["score_home"]); cd.append(r["score_away"])
            elif not at_home and r["away"] == team:
                sc.append(r["score_away"]); cd.append(r["score_home"])
        own, opp = (mu_h, mu_a) if at_home else (mu_a, mu_h)
        if not sc:
            return own, opp, 0
        w = len(sc) / (len(sc) + k)
        return (w * st.mean(sc) + (1 - w) * own,
                w * st.mean(cd) + (1 - w) * opp, len(sc))

    ah, dh, nh = rate(home, True)     # ev sahibi, ev maclari
    aa, da, na = rate(away, False)    # deplasman, deplasman maclari
    if not nh and not na:
        return None                   # iki takim da hic oynamamis: bilgi yok
    lh, la = (ah + da) / 2, (aa + dh) / 2
    return {
        "total": round(lh + la, 2), "home": round(lh, 2), "away": round(la, 2),
        "detail": {"home_played": nh, "away_played": na,
                   "league_home_avg": round(mu_h, 2), "league_away_avg": round(mu_a, 2),
                   "home_scored": round(ah, 2), "home_conceded": round(dh, 2),
                   "away_scored": round(aa, 2), "away_conceded": round(da, 2),
                   "shrink_k": k},
    }


# ==========================================================================
#  Harman
# ==========================================================================

LABELS = {"odds": "Oran beklentisi", "season": "Sezon gücü",
          "form": "Form (arşiv)", "similar": "Benzer oranlı maçlar",
          "venue": "Saha etkisi (ev/dep.)"}


def blend(components, weights):
    """Bilesenleri agirlikli harmanlar.

    Uretilemeyen bilesenin agirligi kalanlar arasinda ORANSAL dagitilir:
    eksik veri tahmini asagi cekmemeli. Hicbiri yoksa None.

    Ev/deplasman: her bilesenin kendi ev PAYI ayni agirliklarla harmanlanip
    toplamla carpilir.
    """
    used = {k: c for k, c in components.items()
            if c and c.get("total") is not None and weights.get(k, 0) > 0}
    wsum = sum(weights[k] for k in used)
    if not used or wsum <= 0:
        return None
    eff = {k: weights[k] / wsum for k in used}

    total = sum(eff[k] * used[k]["total"] for k in used)
    shares = {k: used[k]["home"] / used[k]["total"]
              for k in used
              if used[k].get("home") is not None and used[k]["total"]}
    share = None
    if shares:
        sw = sum(eff[k] for k in shares)
        share = sum(eff[k] * shares[k] for k in shares) / sw
    # Kalibrasyon TEK noktada, harmanin cikisinda: bilesenler ham calisir.
    cal = calibrate_total(total)
    return {
        "total": cal,
        "total_raw": round(total, 2),
        "adjust": {"offset": EXPECT_OFFSET, "step": EXPECT_STEP},
        "home": round(cal * share, 2) if share is not None and cal is not None else None,
        "away": round(cal * (1 - share), 2) if share is not None and cal is not None else None,
        "home_share": round(100 * share, 1) if share is not None else None,
        "effective_weights": {k: round(v, 3) for k, v in eff.items()},
    }


class Predictor:
    """Bir istek boyunca yeniden kullanilan model.

    Sezon gucu ve arsiv havuzu bir kez hesaplanir; her mac icin yalnizca
    bilesenler degerlendirilir.
    """

    def __init__(self, pool, season_rows, weights, gap, n_prev, w_cur, form_k):
        self.pool = pool
        self.weights = weights
        self.gap = gap
        self.form_k = form_k
        self.strength = season_strength(season_rows, n_prev, w_cur)

    def components(self, match, exclude=None, detail=False):
        exp = match.get("expect") or {}
        # HAM beklenti: kalibrasyon (bkz. markets.calibrate_total) harmanin
        # CIKISINDA uygulaniyor. Kalibre degeri girdi yaparsak duzeltme once
        # bilesene, sonra harmana inip iki kat olurdu.
        raw = exp.get("total_raw", exp.get("total"))
        odds = ({"total": raw,
                 "home": exp.get("home_raw", exp.get("home")),
                 "away": exp.get("away_raw", exp.get("away"))}
                if raw is not None else None)
        sim = goal_prediction(match.get("p1"), match.get("p2"), self.pool,
                              self.gap, exclude=exclude, detail=detail)
        if sim and sim.get("total") is None:
            sim = None
        return {
            "odds": odds,
            "season": season_component(match.get("home"), match.get("away"),
                                       self.strength),
            "form": form_component(match.get("home"), match.get("away"),
                                   self.pool, self.form_k, exclude=exclude),
            "similar": sim,
            "venue": venue_component(match.get("home"), match.get("away"),
                                     self.pool, self.form_k, exclude=exclude),
        }

    def predict(self, match, exclude=None, detail=False):
        comp = self.components(match, exclude, detail)
        out = blend(comp, self.weights)
        if out is None:
            return None
        out["weights"] = dict(self.weights)
        out["components"] = {
            k: (None if not c else {**c, "label": LABELS[k],
                                    "weight": self.weights.get(k, 0),
                                    "effective": out["effective_weights"].get(k, 0)})
            for k, c in comp.items()
        }
        return out

    def accuracy(self, expectations):
        """Modelin arsiv uzerindeki isabeti (leave-one-out).

        expectations: event_id -> markets.goal_expectation ciktisi. Oran
        bileseni bunlardan gelir; form ve benzer bilesenleri her mac icin
        kendisi disarida birakilarak yeniden hesaplanir.

        DIKKAT: sezon tablosu tek bir anlik goruntudur (en son cekilen). Bu
        tablodan once oynanmis maclar icin guncel sezon satirlari o macin
        sonucunu de icerir - kucuk bir sizinti. Guncel sezonun agirligi
        dusuk (w_cur) oldugu icin etkisi sinirli, yine de MAE bir miktar
        iyimser olabilir.
        """
        errs, base = [], []
        for m in self.pool:
            actual = m["score_home"] + m["score_away"]
            rest = [r for r in self.pool if r["event_id"] != m["event_id"]]
            if not rest:
                continue
            base.append(abs(st.mean([r["score_home"] + r["score_away"]
                                     for r in rest]) - actual))
            row = {**m, "expect": expectations.get(m["event_id"])}
            p = self.predict(row, exclude=m["event_id"])
            if p:
                errs.append(abs(p["total"] - actual))
        if not base:
            return None
        return {
            "n": len(errs),
            "mae": round(st.mean(errs), 2) if errs else None,
            "baseline_mae": round(st.mean(base), 2),
            "baseline_avg": round(st.mean([r["score_home"] + r["score_away"]
                                           for r in self.pool]), 2),
        }

    def component_accuracy(self, expectations):
        """Her bilesenin TEK BASINA isabeti - agirliklarin gerekcesi."""
        out = {}
        for key in LABELS:
            errs = []
            for m in self.pool:
                actual = m["score_home"] + m["score_away"]
                row = {**m, "expect": expectations.get(m["event_id"])}
                c = self.components(row, exclude=m["event_id"]).get(key)
                if c and c.get("total") is not None:
                    errs.append(abs(c["total"] - actual))
            out[key] = {"label": LABELS[key], "n": len(errs),
                        "mae": round(st.mean(errs), 2) if errs else None,
                        "weight": self.weights.get(key, 0)}
        return out
