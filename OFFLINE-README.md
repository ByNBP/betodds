# BetOdds - cevrimdisi (full) paket

Bu paket **internet baglantisi olmadan** kurulacak sekilde hazirlandi.
Kurulum sirasinda hicbir sey indirilmez; gereken her sey icinde gelir.

## Hizli baslangic

1. Zip'i ac (or. `C:\betodds`).
2. `KURULUM-OFFLINE.bat` dosyasina cift tikla.
3. Tarayicidan `http://localhost:8000` (Docker yolu) ya da
   `http://127.0.0.1:8000` (yerel yol) adresini ac.

Script iki yoldan uygun olani kendisi secer:

| yol | ne zaman secilir | ne gerektirir |
|---|---|---|
| **A - Docker** | `docker info` calisiyorsa | Docker Desktop kurulu olmali |
| **B - Yerel**  | Docker yoksa ya da `-Native` verilirse | **hicbir sey** |

Yolu elle secmek icin:

```powershell
.\KURULUM-OFFLINE.bat -Native        # Docker'i hic kullanma
.\KURULUM-OFFLINE.bat -Port 8010     # baska port (yerel yol)
```

Kurulumdan sonra sunucuyu tekrar baslatmak icin `BASLAT.bat`.

## Paketin icinde ne var

| klasor | icerik | neden |
|---|---|---|
| `images/betodds.tar` | derlenmis uygulama imaji (~287 MB) | Docker yolunda derleme yapilmaz; npm/pypi'ye cikilmaz |
| `images/betodds-proxy.tar` | byedpi proxy imaji (~8 MB) | ayni |
| `vendor/python/` | Python 3.12.8 embeddable + `get-pip.py` | hedef makinede Python kurulu olmasi gerekmez |
| `vendor/wheels/` | 26 adet Windows wheel (cp312, win_amd64) | pypi.org'a cikilmaz |
| `vendor/node/` | Node.js 20 win-x64 (portable) | `backend/app/stats.py` sezon tablosunu ancak Node ile cozebiliyor |
| `vendor/byedpi-win/` | byedpi 0.17.3 Windows binary | GitHub'a cikilmaz |
| `vendor/byedpi/` | byedpi kaynak kodu | proxy imajini yeniden derlemek gerekirse |
| `frontend/dist/` | **derlenmis arayuz** | npm gerekmez |
| `data/leagues.json` | lig konfigurasyonu | - |

Kurulum sirasinda acilanlar `runtime\` ve `tools\` altina cikar; bu iki
klasoru silip kurulumu tekrar calistirmak her seyi sifirlar.

## Baglanti modu (onemli)

Kaynak site bazi aglarda DNS + DPI ile filtreleniyor. Iki secenek var:

**1. VPN kullaniyorsan (senin durumun)** - proxy'yi kapat.
`.env` icindeki satirin yorumunu kaldir:

```ini
BETODDS_PROXY=
```

Docker yolunda `docker compose up -d` ile tekrar baslat. Yerel yolda script
zaten 1080 portunu dinleyen bir sey yoksa proxy'yi kendiliginden devre disi
birakiyor.

**2. byedpi proxy'si ile (varsayilan)** - `.env` icinde `CIADPI_ARGS=-r 1+s`
hazir geliyor. Kurulum betigi 1080'de dinleyen bir sey yoksa paketten cikan
`tools\byedpi\ciadpi.exe` dosyasini KENDISI baslatir; elle bir sey yapmaniza
gerek yok. Proxy'yi hic istemiyorsaniz:

```powershell
.\KURULUM-OFFLINE.bat -NoProxy      # VPN modu: proxy baslatilmaz, ayar bosaltilir
```

Elle baslatmak isterseniz:

```powershell
tools\byedpi\ciadpi.exe -i 127.0.0.1 -p 1080 -r 1+s
```

Strateji tutmazsa `-o 1+s`, `-q 1+s`, `-s 1+s` deneyin
(`scripts\tani-veri.ps1` hepsini sirayla dener ve calisani `.env`'e yazar).

### DNS

`backend/env` icinde sabit bir IP var:

```ini
BETODDS_DNS_OVERRIDE=betandyou-8229.pro=185.175.166.0
```

VPN uzerinden DNS zaten temiz cozuluyorsa bu satira gerek yok; site IP
degistirirse bu satir yuzunden erisilemez hale gelir. Veri gelmiyorsa
denenecek ilk seylerden biri bu satiri yorum yapmaktir.

## Tahmin modeli

Maç başına iki sayı gösteriliyor:

* **Beklenti** — maç öncesi oranların ima ettiği gol sayısı (marj çıkarılmış).
* **Tahmin** — dört etmenin ağırlıklı harmanı (`backend/app/predict.py`).

Çarpanlar arşiv üzerinde leave-one-out ölçülerek seçildi:

| etmen | çarpan | tek başına hata (MAE) | ortam değişkeni |
|---|---|---|---|
| sezon gücü (puan durumları) | 0.45 | 1.65 | `BETODDS_W_SEASON` |
| oran beklentisi | 0.40 | 1.67 | `BETODDS_W_ODDS` |
| form (bizim arşivimiz) | 0.10 | 1.77 | `BETODDS_W_FORM` |
| benzer oranlı maçlar | 0.05 | 2.17 | `BETODDS_W_SIMILAR` |
| *taban: arşiv ortalaması* | — | 1.93 | — |

Harmanın kendi hatası 1.74. `benzer` etmeni tek başına tabandan bile kötü
olduğu için çarpanı düşük: 0.10 yapılırsa 1.76, 0.25 yapılırsa 1.82'ye çıkıyor.
Dört etmen de aktif kalacak şekilde taranan en iyi bileşim yukarıdaki.
MAE'nin standart hatası ~0.17 olduğundan bu farklar istatistiksel olarak
anlamlı değil; çarpanları kendin denemek istersen ortam değişkenleri hazır.

Diğer ayarlar: `BETODDS_PREDICT_SEASONS` (kaç sezon geriye, vars. 10),
`BETODDS_PREDICT_CUR_W` (güncel sezonun ağırlığı, vars. 0.20),
`BETODDS_PREDICT_FORM_K` (form büzüşmesi, vars. 1),
`BETODDS_PREDICT_GAP` (benzer oran penceresi, vars. 0.50).

Maça tıklandığında açılan sayfada her etmenin katkısı, sezon gücü formülü,
form tablosu ve modelin canlı ölçülen isabeti tek tek görünür.

## Eski veritabanini birlestirme

Onceki bir kurulumda biriktirdiginiz arsivi kaybetmemek icin:

```powershell
runtime\python\python.exe backend\merge_db.py C:\eski-paket\data\betodds.db --dene
runtime\python\python.exe backend\merge_db.py C:\eski-paket\data\betodds.db
```

Docker yolunda, host'ta Python olmasa da imajin icindeki Python kullanilir:

```powershell
docker compose run --rm --no-deps betodds python backend/merge_db.py /app/data/eski.db --dene
```

(Eski dosyayi once `data\eski.db` olarak kopyalayin; `data` klasoru konteynerde
`/app/data` olarak gorunur.)

`--dene` hicbir sey yazmadan ne olacagini raporlar. Gercek calistirmada hedef
once `data\betodds.db.bak-<zaman>` olarak yedeklenir.

Betik `odds_snapshots.id` degerlerini yeniden esler - iki veritabaninda da
id'ler 1'den basladigi icin duz kopyalama oranlari YANLIS maca baglardi.
Cakisan kayitlarda: daha tam olan mac kaydi, `market_count`'u buyuk olan
snapshot ve `fetched_at`'i yeni olan sezon satiri kazanir. Cikti sonundaki
`sahipsiz oran degeri: 0` satiri eslemenin tuttugunun kontroludur.

## Veri

Veritabani `data\betodds.db` (SQLite) **pakete dahil** - dolu arsivle geliyor,
ilk acilista tahmin modeli hemen calisir:

| | |
|---|---|
| mac | 96 (89 bitmis) |
| mac oncesi oran seti | 136 snapshot / 14.119 oran degeri |
| 1X2 zaman serisi | 8.170 tick |
| sezon tablosu | 1.660 satir (turnuva 149 ve 129) |

Baska bir kurulumdaki arsivi de eklemek isterseniz ustteki
"Eski veritabanini birlestirme" bolumune bakin - uzerine yazmaz, birlestirir.

## Izlenen ligler

`data\leagues.json`:

| champ_id | lig | tourney_id | mac suresi |
|---|---|---|---|
| 2986291 | FC 26. 5x5 Rush. Super Lig | 149 | 11 dk |
| 2860561 | FC 25. 3x3. Konferans Ligi | 129 | 10 dk |

Ligler modelde AYRIKTIR: tahmin havuzu `champ_id`, sezon gucu `tourney_id` ile
sinirlanir. Sebebi olculebilir - 5x5 Rush mac basi ~7 gol, 3x3 ~14. Yeni lig
ekleme adimlari icin `README.md` -> "Lig ekleme".

## Sorun giderme

| belirti | bak |
|---|---|
| Eski arayuz / eski davranis goruluyor | `runtime\`, `tools\` sil, kurulumu tekrar calistir. Docker yolunda: `docker compose down` + `docker image rm betodds:latest` + kurulum |
| Veri guncellenmiyor | `http://127.0.0.1:8000/api/health` -> `collector.last_error`. Ayrica `/api/logs` |
| Docker konteynerinden siteye cikilamiyor | VPN split-tunnel ise WSL2'yi kapsamaz. Test: `docker compose exec betodds curl -sS -o NUL -w "%{http_code}" https://betandyou-8229.pro/` |
| `python.exe` acilmiyor | `runtime\python` klasorunu silip kurulumu tekrar calistir |
