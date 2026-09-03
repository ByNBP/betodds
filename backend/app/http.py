"""Ortak HTTP istemcisi.

Kaynak siteler bazi aglarda iki katmanli filtreye takiliyor:
  1. DNS zehirlenmesi - alan adi ISP'nin engel sunucusuna cozuluyor
     (sertifika CN=localhost.localdomain gelir),
  2. SNI tabanli DPI - dogru IP'ye baglanilsa bile TLS el sikismasi
     resetlenir (errno 104).

Cozum: (1) icin adres cozumunu biz yapiyoruz (HostOverrideTransport),
(2) icin trafigi bir desync proxy'sine yonlendiriyoruz (BETODDS_PROXY).
"""
import httpx

from .config import CA_BUNDLE, DNS_OVERRIDE, HTTP_TIMEOUT, PROXY


class HostOverrideTransport(httpx.AsyncBaseTransport):
    """Baglantiyi verilen IP'ye kurar; SNI ve Host basligini alan adi birakir.

    httpx'in socks5 destegi adres cozumunu proxy'ye birakiyor (socks5h gibi
    davraniyor); proxy de sistem DNS'ini kullandigi icin zehirli cevaba geri
    duserdik. Bu yuzden cozumu istemci tarafinda yapiyoruz.
    """

    def __init__(self, inner: httpx.AsyncBaseTransport, mapping: dict[str, str]):
        self._inner = inner
        self._map = mapping

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        ip = self._map.get(request.url.host)
        if ip:
            host = request.url.host
            # Sertifika dogrulamasi da sni_hostname uzerinden yapilir.
            request.extensions = {**request.extensions, "sni_hostname": host}
            request.url = request.url.copy_with(host=ip)
            request.headers["Host"] = host
        return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self._inner.aclose()


def new_async_client(**overrides) -> httpx.AsyncClient:
    """Proxy, CA paketi ve DNS override ayarlariyla httpx istemcisi."""
    transport_kwargs: dict = {}
    if PROXY:
        transport_kwargs["proxy"] = PROXY
    if CA_BUNDLE:
        transport_kwargs["verify"] = CA_BUNDLE

    transport: httpx.AsyncBaseTransport = httpx.AsyncHTTPTransport(**transport_kwargs)
    if DNS_OVERRIDE:
        transport = HostOverrideTransport(transport, DNS_OVERRIDE)

    kwargs: dict = {"timeout": HTTP_TIMEOUT, "follow_redirects": True,
                    "transport": transport}
    kwargs.update(overrides)
    return httpx.AsyncClient(**kwargs)
