"""1xbet market kodlarinin (G = grup, T = secenek) okunabilir karsiliklari.

Feed bu isimleri gondermiyor; asagidaki eslemeler canli veriden dogrulanarak
cikarildi. Bilinmeyen kodlar ham haliyle gosterilir.
"""

GROUP_NAMES = {
    1: "Maç Sonucu",
    2: "Handikap",
    8: "Çifte Şans",
    14: "Tek/Çift",
    15: "Ev Sahibi Toplam",
    17: "Toplam Gol",
    19: "Grup 19 (çözülmedi)",
    20: "Golü Atan Takım",
    62: "Deplasman Toplam",
    136: "Kesin Skor",
    9939: "Tam Toplam Gol",
}

# --- kod cozumu hakkinda -------------------------------------------------
# Feed market isimlerini gondermiyor; asagidakiler canli veriden dogrulandi:
#   G=9939  11 secenek, kitap toplami (sum 1/oran) 1.207 -> tam bir market,
#           P = 3..13 ve en dusuk oran P=7'de; ayni macta Ust/Alt 7.5 cizgisi
#           basabas. Yani P dogrudan macin toplam gol sayisi.
#   G=136   P = ev.deplasman kodlamasi (1.002 -> 1-2, 4.006 -> 4-6). Sunulan
#           skorlarin toplamlari 3..13 araligina dusuyor ve en dusuk oran
#           4-3'te (toplam 7) - G=9939'un zirvesiyle birebir ortusuyor.
#   G=14    Tek/Cift. Ima edilen olasilik her macta tam 0.500/0.500 ve bu,
#           G=9939 dagilimindan cikan tek/cift ayrimiyla ortusuyor (KG olsaydi
#           7 gollu bir macta ~0.95/0.05 olurdu). Ancak iki ayak da hep 1.92
#           geldigi icin hangisinin tek oldugu belirlenemedi -> sonuclandirilmaz.
#   G=20    N. golu hangi takim atar. T388/T389, kesin skor marketinden turetilen
#           ev/deplasman gol payini neredeyse birebir izliyor (0.407-0.415,
#           0.385-0.385, 0.485-0.496); T390 sabit ~0.018 ile "o gol atilmaz".
#           P = kacinci gol. Sonuclandirmak icin gol SIRASI gerekir, elimizde
#           sadece final skor var -> sonuclandirilmaz.
#   G=19    cozulemedi. Ortak dagilimdan turetilen sekiz aday olayin en iyisi
#           bile 0.150 ortalama hata veriyor (G=20 dogrulamasi 0.01 icindeydi).

# (G, T) -> etiket sablonu; {p} varsa P (cizgi/handikap) yerine konur.
OUTCOME_NAMES = {
    (1, 1): "1", (1, 2): "X", (1, 3): "2",
    (8, 4): "1X", (8, 5): "12", (8, 6): "X2",
    (2, 7): "Handikap 1 ({p})", (2, 8): "Handikap 2 ({p})",
    (17, 9): "Üst {p}", (17, 10): "Alt {p}",
    (15, 11): "Ev Üst {p}", (15, 12): "Ev Alt {p}",
    (62, 13): "Dep. Üst {p}", (62, 14): "Dep. Alt {p}",
    # G=14 tek/cift oldugu dogrulandi ama iki ayak da her macta 1.92 geldigi
    # icin hangisinin "tek" hangisinin "cift" oldugu ayirt edilemedi.
    (14, 182): "Tek/Çift A", (14, 183): "Tek/Çift B",
    (20, 388): "{p}. golü ev sahibi", (20, 389): "{p}. golü deplasman",
    (20, 390): "{p}. gol atılmaz",
}

# Ana pazar: frontend'in her macta gosterecegi 1X2 uclusu
MAIN_GROUP = 1
MAIN_TYPES = {1: "1", 2: "X", 3: "2"}


def fmt_param(p):
    if p is None:
        return ""
    f = float(p)
    return str(int(f)) if f == int(f) else str(f)


def correct_score_label(p) -> str:
    """G=136'da P = ev.deplasman (or. 4.006 -> '4-6')."""
    if p is None:
        return "?"
    home = int(p)
    away = int(round((float(p) - home) * 1000))
    return f"{home}-{away}"


def outcome_label(g, t, p=None):
    if g == 136:
        return correct_score_label(p)
    if g == 9939:
        return f"{fmt_param(p)} gol"
    tpl = OUTCOME_NAMES.get((g, t))
    if tpl:
        # Handikapta P hic gelmezse cizgi 0 demektir.
        return tpl.format(p=fmt_param(p) if p is not None else "0")
    base = f"T{t}"
    return f"{base} ({fmt_param(p)})" if p is not None else base


def group_label(g):
    return GROUP_NAMES.get(g, f"Grup {g}")


# ---------------------------------------------------------------- sonuclandirma
# 'won' / 'lost' / 'void' (iade) / None (bu market final skordan belirlenemez)
WON, LOST, VOID = "won", "lost", "void"


def _ou(value, line, over: bool):
    """Ust/Alt: cizgiye tam esitlik iade."""
    if line is None:
        return None
    if value == line:
        return VOID
    return WON if (value > line) == over else LOST


def settle(g, t, p, home: int, away: int):
    """Bir secenegin final skora gore sonucu.

    None donmesi 'bilmiyoruz' demektir - uydurmaktansa isaretsiz birakiyoruz.
    """
    if home is None or away is None:
        return None
    total, diff = home + away, home - away

    if g == 1:
        return {1: WON if diff > 0 else LOST,
                2: WON if diff == 0 else LOST,
                3: WON if diff < 0 else LOST}.get(t)
    if g == 8:                                   # cifte sans
        return {4: WON if diff >= 0 else LOST,
                5: WON if diff != 0 else LOST,
                6: WON if diff <= 0 else LOST}.get(t)
    if g == 2:                                   # handikap (P yoksa cizgi 0)
        line = float(p) if p is not None else 0.0
        margin = diff + line if t == 7 else -diff + line
        return VOID if margin == 0 else (WON if margin > 0 else LOST)
    if g == 17:
        return _ou(total, p, over=(t == 9))
    if g == 15:
        return _ou(home, p, over=(t == 11))
    if g == 62:
        return _ou(away, p, over=(t == 13))
    if g == 136:                                 # kesin skor: P = ev.deplasman
        if p is None:
            return None
        eh = int(p)
        ea = int(round((float(p) - eh) * 1000))
        return WON if (eh, ea) == (home, away) else LOST
    if g == 9939:                                # tam toplam gol
        return None if p is None else (WON if int(p) == total else LOST)

    # G=14 (hangi ayak tek/cift belli degil), G=19 (cozulmedi),
    # G=20 (gol sirasi gerekir) -> belirlenemez
    return None


# ------------------------------------------------------- gol beklentisi
TOTAL_GOALS_GROUP = 9939        # "Tam Toplam Gol": P dogrudan toplam gol sayisi
SCORE_GROUP = 136               # "Kesin Skor": P = ev.deplasman kodlamasi
OU_GROUP = 17                   # "Toplam Gol": Ust/Alt cizgileri
OU_OVER, OU_UNDER = 9, 10       # (17,9)="Ust {p}", (17,10)="Alt {p}"


def _normalized(pairs):
    """[(deger, oran)] -> [(deger, olasilik)]. Marj oransal olarak cikarilir."""
    usable = [(v, c) for v, c in pairs if c and c > 1]
    book = sum(1 / c for _, c in usable)
    if not usable or book <= 0:
        return [], 0.0
    return [(v, (1 / c) / book) for v, c in usable], book


def goal_expectation(values, detail: bool = False):
    """Mac oncesi market setinden beklenen gol sayilari.

    values: [{'g':..,'t':..,'p':..,'coef':..,'blocked':..}] - tek bir snapshot.
    detail: True ise sonuca 'detail' anahtari eklenir; hesabin dayandigi her
    ara deger (hangi secenek, hangi oran, hangi olasilik, hangi katki) tek tek
    dokulur. Liste uclarinda kapali, mac detay sayfasinda acik kullanilir.

    SEVIYE (toplam) G=9939'dan gelir: P dogrudan toplam gol sayisidir ve market
    tamdir (kitap toplami ~1.21, yani sadece marj).

    PAY (ev/deplasman) G=136'dan gelir ama YALNIZCA ORAN olarak. Kesin skor
    marketi sunulan ~35 skorla sinirli, ustu kesik: kendi basina beklenen
    toplami ~0.4 gol dusuk veriyor (kitap toplami 1.02-1.13, tam bir markette
    olmasi gerekenin altinda). Bu yuzden seviyeyi toplamdan, dagilimi kesin
    skordan aliyoruz.

    Yeterli veri yoksa None doner - uydurmuyoruz.
    """
    totals = [(v["p"], v["coef"]) for v in values
              if v["g"] == TOTAL_GOALS_GROUP and not v.get("blocked") and v["p"] is not None]
    dist, book = _normalized(totals)
    if not dist:
        return None
    total = sum(p * q for p, q in dist)
    top_goals, top_prob = max(dist, key=lambda x: x[1])

    out = {"total": round(total, 2),
           "home": None, "away": None,
           "top_total": int(top_goals), "top_prob": round(100 * top_prob, 1),
           "margin": round((book - 1) * 100, 1),
           "line": None, "line_over": None, "line_under": None}

    # Beklentiye en yakin Ust/Alt cizgisi. Esit uzaklikta iki cizgi varsa
    # dusuk olan secilir (deterministik olsun).
    ou: dict[float, dict[int, float]] = {}
    for v in values:
        if v["g"] == OU_GROUP and not v.get("blocked") and v["p"] is not None:
            ou.setdefault(v["p"], {})[v["t"]] = v["coef"]
    both = [p for p, side in ou.items() if OU_OVER in side and OU_UNDER in side]
    if both:
        line = min(both, key=lambda p: (abs(p - total), p))
        out["line"] = line
        out["line_over"] = ou[line][OU_OVER]
        out["line_under"] = ou[line][OU_UNDER]

    scores = [(v["p"], v["coef"]) for v in values
              if v["g"] == SCORE_GROUP and not v.get("blocked") and v["p"] is not None]
    sdist, sbook = _normalized(scores)
    eh = ea = share = None
    if sdist:
        eh = sum(int(p) * q for p, q in sdist)
        ea = sum(round((p - int(p)) * 1000) * q for p, q in sdist)
        if eh + ea > 0:
            share = eh / (eh + ea)
            out["home"] = round(total * share, 2)
            out["away"] = round(total * (1 - share), 2)

    if detail:
        out["detail"] = _expectation_detail(
            dist, book, total, dict(totals),
            sdist, sbook, dict(scores), eh, ea, share,
            ou, both, out["line"])
    return out


def _expectation_detail(dist, book, total, total_coefs,
                        sdist, sbook, score_coefs, eh, ea, share,
                        ou, line_candidates, line):
    """Beklentinin hangi donelerden ciktigini satir satir dokur.

    Ekranda gosterilecek her sayi burada uretilir; frontend hicbir sey yeniden
    hesaplamaz. Boylece tabloda gorunen deger ile kirilimin toplami arasinda
    fark olusamaz.
    """
    d = {
        # 1) Seviye: tam toplam gol marketi
        "total_market": {
            "g": TOTAL_GOALS_GROUP,
            "label": group_label(TOTAL_GOALS_GROUP),
            "book": round(book, 4),
            "margin_pct": round((book - 1) * 100, 1),
            "n": len(dist),
            "expected": round(total, 3),
            "bins": [{
                "goals": int(v),
                "coef": total_coefs.get(v),
                "raw_pct": round(100 / total_coefs[v], 2) if total_coefs.get(v) else None,
                "prob_pct": round(100 * q, 2),
                "contrib": round(v * q, 3),
            } for v, q in sorted(dist)],
        },
        "score_market": None,
        "line": None,
    }

    # 2) Pay: kesin skor marketi (yalnizca oran olarak kullanilir)
    if sdist:
        rows = sorted(({
            "label": correct_score_label(p),
            "home": int(p),
            "away": int(round((p - int(p)) * 1000)),
            "coef": score_coefs.get(p),
            "prob_pct": round(100 * q, 2),
        } for p, q in sdist), key=lambda r: -r["prob_pct"])
        d["score_market"] = {
            "g": SCORE_GROUP,
            "label": group_label(SCORE_GROUP),
            "book": round(sbook, 4),
            "margin_pct": round((sbook - 1) * 100, 1),
            "n": len(sdist),
            # Bu marketin kendi seviyesi DUSUK cikar (market ustu kesik);
            # bu yuzden yalnizca eh/ea orani kullaniliyor.
            "own_total": round((eh or 0) + (ea or 0), 3),
            "eh": round(eh, 3) if eh is not None else None,
            "ea": round(ea, 3) if ea is not None else None,
            "home_share_pct": round(100 * share, 1) if share is not None else None,
            "scores": rows,
        }

    # 3) Cizgi secimi: beklentiye en yakin alt/ust
    if line_candidates:
        d["line"] = {
            "g": OU_GROUP,
            "label": group_label(OU_GROUP),
            "chosen": line,
            "candidates": [{
                "line": p,
                "distance": round(abs(p - total), 3),
                "over": ou[p].get(OU_OVER),
                "under": ou[p].get(OU_UNDER),
                "chosen": p == line,
            } for p in sorted(line_candidates)],
        }
    return d
