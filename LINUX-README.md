# BetOdds — Linux paketi

Kullanıma hazır paket. Hedef makinede gereken tek şey **Python 3.10+**;
bağımlılıklar, derlenmiş arayüz ve veritabanı paketin içinde geliyor.
**Ağ erişimi gerekmez** — ne PyPI'ye, ne npm'e, ne de GitHub'a çıkar.

## Kurulum

```bash
tar xzf betodds-linux-*.tar.gz
cd betodds
./KURULUM.sh
```

Bittiğinde adres yazılır: <http://localhost:8000>

`KURULUM.sh` sırayla:

| Adım | İş |
|---|---|
| 1 | `backend/env` kontrolü — pakette hazır geliyor (site aynası, DNS override, proxy) |
| 2 | Python 3.10+ bulur, `backend/.venv` kurar, **pakete dahil wheel'lerden** yükler |
| 3 | Arayüz — `frontend/dist` pakete dahil, derleme yok |
| 4 | Gerekiyorsa DPI bypass proxy'sini derleyip 1080'de başlatır |
| 5 | Backend'i başlatır, `/api/health` ile doğrular |

## Günlük kullanım

```bash
./BASLAT.sh     # proxy + backend başlat
./DURUM.sh      # toplayıcı çalışıyor mu, kaç maç/tick var
./DURDUR.sh     # ikisini de durdur
```

Loglar `logs/backend.log` ve `logs/proxy.log`.

## Seçenekler

```bash
./KURULUM.sh --systemd      # oturum kapansa da çalışsın (kullanıcı servisi)
./KURULUM.sh --docker       # yerel Python yerine docker compose yığını
./KURULUM.sh --no-start     # sadece kur, başlatma
BETODDS_PORT=9000 ./KURULUM.sh   # 8000 doluysa
```

### `--systemd` neden önemli

Projenin tüm değeri **maç öncesi oranları kaçırmamakta** — kaynak site maç
bitince oranları siliyor ve geriye dönük alınamıyor. Toplayıcı durduğu sürede
oynanan maçlar kalıcı olarak kayıp. `--systemd` kullanıcı servisi kurar,
`loginctl enable-linger` açar; makine açık olduğu sürece oturum kapansa bile
toplayıcı çalışır ve çökerse yeniden başlar.

```bash
systemctl --user status betodds
journalctl --user -u betodds -f
```

## Python sürümü

Paket **cp310–cp313** için wheel taşır (Ubuntu 22.04/24.04, Debian 12/13,
Fedora 40+, Arch). İkili paketler — `pydantic_core`, `uvloop`, `httptools`,
`watchfiles`, `websockets`, `PyYAML` — Python sürümüne özeldir, o yüzden hepsi
ayrı ayrı taşınıyor.

Hedef makinenin sürümü listede yoksa `KURULUM.sh` uyarır ve PyPI'ye düşer
(bu durumda ağ gerekir). Mimari `x86_64` dışındaysa (örn. `aarch64`) paketi o
mimaride üretin:

```bash
./scripts/vendor-indir-linux.sh && ./scripts/paket-linux.sh
```

`python3-venv` ayrı paket olabilir:

```bash
sudo apt install python3-venv      # Debian/Ubuntu
```

## DPI bypass proxy'si

Kaynak site Türkiye'de iki katmanlı filtreye takılıyor (DNS zehirlenmesi +
SNI tabanlı DPI). Çözüm `byedpi/ciadpi` — kaynağı `vendor/byedpi` altında
**gömülü**, GitHub'a çıkılmıyor.

`KURULUM.sh` önce **derlemeyi** dener (`cc` + `make`); derleyici yoksa pakete
dahil hazır ikiliye düşer (`vendor/byedpi-linux-x86_64/ciadpi`). Yerel derleme
tercih edilir çünkü hazır ikili derlendiği glibc'den (2.34) eskisinde çalışmaz.

```bash
sudo apt install build-essential   # derleme için
```

Strateji tutmazsa (`DURUM.sh` toplayıcıda hata gösteriyorsa):

```bash
./DURDUR.sh
CIADPI_ARGS="-q 1+s" ./scripts/proxy-baslat.sh && ./BASLAT.sh
```

Çalıştığı doğrulanmış stratejiler: `-r 1+s`, `-o 1+s`, `-q 1+s`.
Çalışmayanlar: `-s`, `-d`, `-f`.

**Sistem geneli VPN kullanıyorsanız** proxy gerekmez — `backend/env` içindeki
`BETODDS_PROXY` satırını yorum yapın; `KURULUM.sh` proxy'yi hiç başlatmaz.

## Site adresi değişirse

betandyou aynaları sık değişiyor. `backend/env` içindeki `BETODDS_SITE`
**tek düzeltme noktası** — alan adı başka hiçbir dosyada gömülü değil.
Değiştirdikten sonra DNS override'ı tazeleyin:

```bash
rm backend/env && ./scripts/detect-network.sh && ./BASLAT.sh
```

`detect-network.sh` adresi DoH ile çözer, yerel DNS'in verdiğiyle karşılaştırır,
proxy gerekip gerekmediğini ölçer ve `backend/env`'i yeniden yazar.

## Paket üretme (kaynak makinede)

```bash
./build-frontend.sh              # frontend/dist
./scripts/vendor-indir-linux.sh  # wheel'ler (~33 MB, ağ gerekir)
./scripts/paket-linux.sh         # -> ~/betodds-linux-<tarih>.tar.gz
```

| Seçenek | Etki |
|---|---|
| `--no-db` | veritabanını dışarıda bırak (hedef sıfırdan başlar) |
| `--with-images` | `images/*.tar` docker imajlarını da koy (`--docker` için çevrimdışı) |

Veritabanı `VACUUM INTO` ile kopyalanır — canlı WAL dosyasını doğrudan
kopyalamak bozuk bir dosya verir.

## Sorun giderme

| Belirti | Bakılacak yer |
|---|---|
| `./DURUM.sh` "toplayıcı DURDU" | `logs/backend.log` |
| toplayıcı çalışıyor ama `hata:` dolu | proxy ayakta mı (`./DURUM.sh`), strateji tutuyor mu |
| yeni maç gelmiyor | site adresi değişmiş olabilir → yukarıdaki bölüm |
| port dolu | `BETODDS_PORT=9000 ./BASLAT.sh` |
| `python 3.10+ bulunamadi` | `python3-venv` kurulu mu |

Arayüzün gerçekten render olduğunu doğrulamak (docker gerekir):

```bash
docker run --rm --network=host -v "$PWD/frontend:/app:z" -w /app \
  -e SMOKE_URL=http://127.0.0.1:8000/ node:20-alpine npm run smoke
```

Mimari, market kodları, tahmin modeli ve API uçları için `README.md`.
