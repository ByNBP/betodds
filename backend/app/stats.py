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


async def season_table(tourney_id: int, iteration: int,
                       game: str = "fifa") -> list[dict]:
    """Bir sezonun puan durumunu dondurur."""
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
    return table
