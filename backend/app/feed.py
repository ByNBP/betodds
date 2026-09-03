"""betandyou (1xbet tabanli) canli feed istemcisi.

Onemli davranislar:
  * Sanal ligler yalnizca `virtualSports=true` ile listeleniyor; `sports=`
    parametresiyle birlikte kullanildiginda API 406 donuyor, o yuzden
    filtreleme sadece `champs=` uzerinden yapiliyor.
  * Bir mac bitince feed'den once oranlari (GE/E) siliniyor, kisa sure sonra
    kayit tamamen dusuyor. Oran arsivi bu yuzden mac oncesinde alinmali.
"""
import time

import httpx

from .config import COUNTRY, LANG, SITE, USER_AGENT
from .http import new_async_client


def _headers(referer_path: str = "/") -> dict:
    return {"User-Agent": USER_AGENT, "Referer": f"{SITE}{referer_path}",
            "Accept": "application/json, text/plain, */*"}


class FeedClient:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client
        self._owned = client is None

    async def __aenter__(self):
        if self._client is None:
            self._client = new_async_client()
        return self

    async def __aexit__(self, *exc):
        if self._owned and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get(self, path: str, params: list, referer: str = "/"):
        assert self._client is not None, "FeedClient async context icinde kullanilmali"
        r = await self._client.get(f"{SITE}/service-api/{path}", params=params,
                                   headers=_headers(referer))
        r.raise_for_status()
        data = r.json()
        if not data.get("Success"):
            raise RuntimeError(f"{path}: Success=false ({data.get('Error')})")
        return data.get("Value")

    async def league_matches(self, champ_id: int, virtual: bool = True) -> list[dict]:
        """Bir ligin canli + yaklasan maclarini ana oranlariyla dondurur.

        DIKKAT: Sunucu sorgu parametrelerinin SIRASINI dogruluyor. Asagidaki
        sira disinda herhangi bir dizilim `406 Not Acceptable` doner - ayni
        parametreler, ayni degerler olsa bile. Bu yuzden params bir liste
        olarak veriliyor; sozluge cevirip siralamayi bozmayin.
        """
        params: list[tuple[str, object]] = [
            ("champs", champ_id), ("count", 50), ("lng", LANG), ("mode", 4),
            ("country", COUNTRY), ("getEmpty", "true"),
        ]
        if virtual:
            params.append(("virtualSports", "true"))
        params.append(("noFilterBlockEvent", "true"))
        return await self._get("LiveFeed/Get1x2_VZip", params,
                               referer=f"/{LANG}/esports/virtual/fifa/{champ_id}") or []

    async def game_full(self, event_id: int) -> dict | None:
        """Tek macin tum market gruplarini dondurur (mac oncesi ~98 oran)."""
        # Bu ucta da parametre sirasi korunmali (bkz. league_matches).
        params: list[tuple[str, object]] = [
            ("id", event_id), ("lng", LANG), ("country", COUNTRY), ("mode", 4),
            ("countevents", 250), ("isSubGames", "true"), ("GroupEvents", "true"),
            ("grMode", 4), ("marketType", 1),
        ]
        return await self._get("LiveFeed/GetGameZip", params)


def flatten_outcomes(entries) -> list[dict]:
    """GetGameZip'te GE[].E ic ice dizi ([[{...}]]) gelebiliyor; duzlestirir."""
    out = []
    for e in entries or []:
        if isinstance(e, list):
            out.extend(i for i in e if isinstance(i, dict))
        elif isinstance(e, dict):
            out.append(e)
    return out


def main_odds(entries) -> tuple[float | None, float | None, float | None]:
    """E listesinden 1 / X / 2 oranlarini cikarir (G=1, T=1/2/3)."""
    got = {}
    for o in entries or []:
        if isinstance(o, dict) and o.get("G") == 1 and o.get("T") in (1, 2, 3):
            got[o["T"]] = o.get("C")
    return got.get(1), got.get(2), got.get(3)


def parse_match(m: dict, champ_id: int) -> dict:
    """Ham feed kaydini normalize eder."""
    sc = m.get("SC") or {}
    fs = sc.get("FS") or {}
    meta = {d.get("Key"): d.get("Value") for d in (sc.get("S") or [])
            if isinstance(d, dict)}
    o1, ox, o2 = main_odds(m.get("E"))

    # DIKKAT: Feed sifir skorlari HIC gondermiyor - 0-1 biten bir macta
    # FS = {"S2": 1} gelir, 0-0 devam eden bir macta ise FS = {} gelir.
    # Yani "alan yok" ile "gol atilmadi" ayni sey; bu ikisini skora bakarak
    # ayirt edemeyiz, baslama zamanina bakmak zorundayiz.
    start_ts = m.get("S")
    started = bool(start_ts) and time.time() >= start_ts

    if m.get("F"):
        status = "finished"
    elif started or fs:
        status = "live"
    else:
        status = "scheduled"

    if status == "scheduled":
        score_h = score_a = None
    else:
        score_h, score_a = fs.get("S1") or 0, fs.get("S2") or 0
    return {
        "event_id": int(m.get("I")),
        "champ_id": champ_id,
        "league_name": m.get("L"),
        "start_ts": start_ts,
        "home": m.get("O1"), "away": m.get("O2"),
        "home_id": m.get("O1I"), "away_id": m.get("O2I"),
        "score_home": score_h, "score_away": score_a,
        "status": status,
        "status_text": sc.get("SLS") or sc.get("I") or "",
        "tourney_id": _int(meta.get("id_tourney")),
        "iteration": _int(meta.get("iteration")),
        "o1": o1, "ox": ox, "o2": o2,
    }


def _int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None
