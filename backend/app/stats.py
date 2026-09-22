"""eventsstat.com'dan sezon (iteration) puan durumlarini ceker.

betandyou'daki istatistik popup'i asagidaki adresi iframe olarak gomuyor:
    https://eventsstat.com/<lng>/statisticpopup/cyber/fifa/<tourney>/<iteration>
Sayfa Nuxt SSR oldugu icin veri `window.__NUXT__` IIFE'sinde geliyor; onu
Node ile calistirip JSON'a ceviriyoruz (saf regex ile guvenli ayristirilamaz).
"""
import asyncio
import json
import shutil

import httpx

from .config import LANG, SITE, STATS_SITE, USER_AGENT
from .http import new_async_client

NODE = shutil.which("node")


class StatsUnavailable(RuntimeError):
    """Kaynak sayfaya erisilemedi ya da Node bulunamadi."""


async def _nuxt_state(html: str) -> dict:
    if not NODE:
        raise StatsUnavailable("node bulunamadi; sezon tablosu ayristirilamiyor")
    i = html.find("window.__NUXT__=")
    if i < 0:
        raise StatsUnavailable("sayfada __NUXT__ yok")
    js = ("global.window=global;\n" + html[i:html.find("</script>", i)] +
          "\nconsole.log(JSON.stringify(window.__NUXT__));\n")
    proc = await asyncio.create_subprocess_exec(
        NODE, "-e", js, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)
    out, err = await asyncio.wait_for(proc.communicate(), timeout=40)
    if proc.returncode != 0:
        raise StatsUnavailable(f"node hatasi: {err.decode()[:200]}")
    return json.loads(out.decode())


def _find_rows(state) -> list[dict]:
    """State agacinda puan durumu satirlarini bulur."""
    found: list[dict] = []

    def walk(o):
        if found:
            return
        if isinstance(o, dict):
            rows = o.get("rows")
            if isinstance(rows, list) and rows and isinstance(rows[0], dict) \
                    and "points" in rows[0]:
                found.extend(rows)
                return
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(state)
    return found


def _num(v) -> int:
    try:
        return int(str(v).strip() or 0)
    except (TypeError, ValueError):
        return 0


def _fixtures(rows: list[dict]) -> list[dict]:
    """Capraz sonuc tablosunu tekil maclara acar.

    Her satirin 'positions' dizisi: [takim adi, sonuc_1, sonuc_2, ...] - indis
    j, siralamada num=j olan takimi gosterir. Hucre "3:5" bicimindedir ve
    SATIR TAKIMI EVDEDIR. Dogrulama: her takimin hucrelerinden cikan ev+
    deplasman gol toplami, puan durumundaki averaji birebir veriyor
    (PSG 89-61 ev + 83-72 deplasman = 172-133).

    Takimin kendisine denk gelen hucre bos gelir; oynanmamis eslesmeler de
    bos olabilir - ikisi de atlanir.
    """
    name = {_num(r.get("num")): (r.get("title") or "") for r in rows}
    out = []
    for r in rows:
        home = r.get("title") or ""
        pos = r.get("positions") or []
        if not home or not isinstance(pos, list):
            continue
        for j, cell in enumerate(pos):
            if j == 0 or not isinstance(cell, str) or ":" not in cell:
                continue
            away = name.get(j)
            if not away or away == home:
                continue
            sh, _, sa = cell.partition(":")
            try:
                out.append({"home": home, "away": away,
                            "score_home": int(sh.strip()),
                            "score_away": int(sa.strip())})
            except ValueError:
                continue
    return out


async def season_page(tourney_id: int, iteration: int,
                      game: str = "fifa") -> dict:
    """Bir sezonun puan durumu + o sezonun tum maclari.

    Ikisi de AYNI sayfadan cikiyor; ayri istek atmak kaynagi bos yere iki kez
    yormak olurdu.
    """
    url = f"{STATS_SITE}/{LANG}/statisticpopup/cyber/{game}/{tourney_id}/{iteration}"
    async with new_async_client() as c:
        r = await c.get(url, headers={"User-Agent": USER_AGENT,
                                      "Referer": f"{SITE}/"})
        r.raise_for_status()
        html = r.text
    rows = _find_rows(await _nuxt_state(html))
    table = []
    for r_ in rows:
        gf, _, ga = (r_.get("difference") or "0-0").partition("-")
        table.append({
            "pos": _num(r_.get("num")), "team": r_.get("title") or "",
            "played": _num(r_.get("gamesCount")), "wins": _num(r_.get("wins")),
            "draws": _num(r_.get("draws")), "losses": _num(r_.get("losses")),
            "gf": _num(gf), "ga": _num(ga), "points": _num(r_.get("points")),
        })
    return {"table": table, "matches": _fixtures(rows)}


async def season_table(tourney_id: int, iteration: int,
                       game: str = "fifa") -> list[dict]:
    """Yalnizca puan durumu (geriye donuk uyumluluk)."""
    return (await season_page(tourney_id, iteration, game))["table"]
