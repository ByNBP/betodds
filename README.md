# BetOdds

Maç **başlamadan önceki** bahis oranlarını kalıcı olarak arşivler, canlı skor ve
oran hareketini web arayüzünde gösterir.

## Neden var

Kaynak site, bir maç bittikten sonra oranları **tamamen siliyor**: bitmiş maçın
`GetGameZip` yanıtı skoru döndürür ama market listesi (`GE`) boş gelir, birkaç
saat sonra kayıt tümüyle düşer. Sitenin istatistik servisi (`statisticfeed`) de
bu sanal maçlar için `204 No Content` döner. Yani geçmiş oran hiçbir yerden
geriye dönük alınamıyor — **yakalanmazsa kaybolur.** Bu projenin tek işi o
pencereyi kaçırmamak.

## Mimari

```
backend/  FastAPI + SQLite + asyncio toplayıcı   (tek yazar, API sadece okur)
frontend/ React + Vite + Recharts                (container içinde derlenir)
data/     betodds.db, leagues.json
```

Toplayıcı her `BETODDS_POLL` saniyede (varsayılan 20) yapılandırılmış her ligi
çeker ve:

1. maç kaydını günceller,
2. 1/X/2 oranını zaman serisine yazar (`odds_ticks`),
3. maç **başlamadan önce** tüm market setini bir kez arşivler (`odds_snapshots`
   + `odds_values`, maç başına ~98 oran),
4. feed'den düşen ya da `F=true` olan maçı bitmiş olarak kapatır.

## Başka bir makineye taşıma

`scripts/package.sh` bir arşiv üretir. İçine giren: kaynak kod, lig
konfigürasyonu, derlenmiş frontend ve **veritabanı**. Girmeyen: `backend/.venv`
(mutlak yollar gömülü), `frontend/node_modules` (platforma özel ikililer),
`backend/env` (makineye/ağa özel).

Veritabanı `VACUUM INTO` ile kopyalanır — canlı WAL dosyasını doğrudan
kopyalamak bozuk bir dosya verir.

### Windows

1. ZIP'i sağ tık → **Tümünü ayıkla**
2. Oluşan `betodds` klasöründe **`KURULUM.bat`** dosyasına çift tıklayın

`KURULUM.bat` → `KURULUM.ps1` şunları sırayla yapar:

| Adım | İş |
|---|---|
| 1 | Docker Desktop yoksa `winget` ile kurar (yönetici yetkisi ister, kendini yükseltir) |
| 2 | Ağ durumunu tespit edip `backend/env` yazar |
| 3 | İmajları derler (`images\*.tar` varsa derlemek yerine onları yükler) |
| 4 | `docker compose up -d`, sağlık kontrolü, tarayıcıyı açar |

Docker kurulumu **yeniden başlatma** isteyebilir; script bunu tespit edip ne
yapılacağını söyler ve tekrar çalıştırmanızı ister.

#### İmaj derlenemedi / depolara erişilemiyor

Tarayıcının çalışıyor olması konteynerin de çalıştığı anlamına gelmez —
Docker Desktop (WSL2) kendi ağ yığınını ve DNS'ini kullanır. Teşhis:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\tani-docker.ps1
```

Host DNS'ini, motoru, `docker pull`'u ve konteyner içinden DNS/paket deposu
erişimini ayrı ayrı test eder. En sık çözüm: **Settings → Docker Engine**
JSON'una `"dns": ["8.8.8.8", "1.1.1.1"]` ekleyip *Apply & restart*.

**Ağ hiç düzelmezse hazır imajlarla kurun:** `betodds.tar.gz` ve
`betodds-proxy.tar.gz` dosyalarını proje içindeki `images\` klasörüne koyup
`KURULUM.bat`'ı çalıştırın. Script derlemek yerine onları yükler; farklı bir
araçla üretilmiş olsalar bile etiketlerini compose'un beklediği adlara çevirir.

#### "Virtualization support not detected"

Docker Desktop donanım sanallaştırma ister. Teşhis:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\tani.ps1
```

BIOS'ta VT-x/AMD-V durumunu, Windows bileşenlerini (Sanal Makine Platformu, WSL),
WSL sürümünü ve `hypervisorlaunchtype` ayarını kontrol edip yapılacakları
sıralar. En sık sebep BIOS/UEFI'de sanallaştırmanın kapalı olmasıdır
(Intel: *Intel VT-x*, AMD: *SVM Mode*).

#### Sanallaştırma hiç açılamıyorsa

Docker'a gerek yok:

```powershell
KURULUM.bat -Native
```

Sanallaştırma gerektirmez. Yaptıkları:

| | |
|---|---|
| Python | `winget` ile kurar; **Microsoft Store kısayolunu ayırt eder** — o "python" komutu vardır ama kod çalıştırmaz, script gerçek yorumlayıcıyı arar (`python` → `python3` → `py -3`) ve 3.10+ şartını doğrular |
| Node.js | kurar — sadece arayüz için değil, backend de sezon tablolarını ayrıştırmak için kullanıyor |
| Bağımlılıklar | `backend/.venv` içine kurulur |
| Arayüz | pakete dahil edilen hazır `frontend/dist` |
| DPI proxy | byedpi Windows sürümünü **indirip çalıştırır** (`tools\byedpi\ciadpi.exe`) |
| Loglar | `logs\backend.log` ve `logs\backend.err.log` — sunucu çökerse hata burada kalır |

Proxy stratejisi tutmazsa:

```powershell
KURULUM.bat -Native -ProxyArgs "-q 1+s"
```

Durdurmak için:

```powershell
Get-Process python, ciadpi -ErrorAction SilentlyContinue | Stop-Process
```

Seçenekler:

```powershell
KURULUM.bat -Native        # Docker yerine yerel Python kurulumu
KURULUM.bat -SkipInstall   # hiçbir şey kurma, sadece derle ve çalıştır
```

Yalnızca Docker kurulumunu atlayıp derleyip çalıştırmak için
`scripts\setup.ps1` de kullanılabilir.

Yığın iki servisten oluşur:

| Servis | İş |
|---|---|
| `proxy` | byedpi/ciadpi, kaynağından derlenir, SOCKS5 1080 |
| `betodds` | backend + derlenmiş frontend, port 8000 |

**Proxy neden yığının içinde:** Docker Desktop `--network=host` desteklemez ve
`host.docker.internal` platforma göre değişir. Proxy'yi servis yapınca backend
ona `socks5://proxy:1080` ile ulaşır — host ağına hiç bağımlılık kalmaz.

**byedpi kaynağı `vendor/byedpi` altında gömülüdür** (MIT, v0.17.3-38-gba53229).
Önceki sürüm derleme sırasında GitHub'dan klonluyordu ve GitHub'a erişilemeyen
ağlarda imaj derlenemiyordu. Artık derleme yalnızca Alpine paket deposuna,
pypi'ye ve npm'e çıkar.

Proxy stratejisi tutmazsa `docker-compose.yml` içindeki `CIADPI_ARGS` değerini
`-q 1+s` veya `-r 1+s` yapıp `docker compose up -d --force-recreate proxy`.

### Linux

Kendi paketi var — ayrıntısı `LINUX-README.md`:

```bash
tar xzf betodds-linux-*.tar.gz && cd betodds && ./KURULUM.sh
```

Hedef makinede gereken tek şey **Python 3.10+**. Bağımlılık wheel'leri
(cp310–cp313), derlenmiş arayüz ve veritabanı paketin içinde; **ağ erişimi
gerekmez**. `KURULUM.sh` venv'i kurar, gerekiyorsa DPI bypass proxy'sini
derleyip başlatır, backend'i ayağa kaldırır ve `/api/health` ile doğrular.

Sonrası: `./BASLAT.sh`, `./DURUM.sh`, `./DURDUR.sh`.
Oturum kapansa da toplansın diye: `./KURULUM.sh --systemd`.

Paketi üretmek (kaynak makinede):

```bash
./build-frontend.sh && ./scripts/vendor-indir-linux.sh && ./scripts/paket-linux.sh
```

### macOS

```bash
tar xzf betodds-*.tar.gz && cd betodds && ./scripts/setup.sh
```

Docker varsa konteyner yolunu, yoksa yerel yolu (python venv + pakete dahil
edilmiş hazır `dist`) seçer. Yerel yolda `node` yoksa yalnızca sezon tablosu
çekimi devre dışı kalır, geri kalan her şey çalışır.

### Site adresi değişirse

betandyou aynaları sık değişiyor. Tek komut:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\site-degistir.ps1
```

Adresi sorar (veya `-Site https://yeni-adres.pro` ile verilir) ve sırasıyla:

1. Adresi normalleştirir (şema ekler, yolu atar)
2. DoH ile gerçek IP'yi bulur, iki sağlayıcıyla karşılaştırır
3. Yerel DNS zehirliyse `BETODDS_DNS_OVERRIDE` yazar
4. **Sayfayı değil, gerçek API ucunu dener** — `Success=true` mi, maç geliyor mu
5. Yapılandırılan ligin hâlâ veri döndürdüğünü kontrol eder
6. `backend/env`'i günceller (diğer satırları koruyarak)
7. Servisi yeniden oluşturur ve toplayıcının düzeldiğini doğrular

**Doğrulama geçmezse `backend/env` değiştirilmez** — yanlış adresle çalışır
duruma düşmezsiniz.

Alan adı başka hiçbir dosyada gömülü değildir; `detect-network.ps1` ve
`tani-veri.ps1` host adını `BETODDS_SITE`'tan türetir.

### Ağ tespiti

`scripts/detect-network.ps1` (Windows) / `scripts/detect-network.sh` (Unix)
alan adlarını DoH ile çözer, yerel DNS'in verdiğiyle karşılaştırır ve
zehirlenme varsa `BETODDS_DNS_OVERRIDE` yazar. **Gerçek IP zamanla değişebilir**,
o yüzden sabit yazmak yerine her kurulumda yeniden tespit edilir.

## Çalıştırma

```bash
./start.sh          # frontend build + backend, tek port: http://localhost:8000
./dev.sh            # backend + Vite dev sunucusu (5173), anlık yenileme
./build-frontend.sh # sadece frontend derlemesi
```

Kurulmuş bir Linux paketinde proxy'yi de yöneten sarmalayıcılar:
`./BASLAT.sh`, `./DURUM.sh`, `./DURDUR.sh`.

İlk kurulum backend için:

```bash
cd backend && python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
```

Frontend `node:20-alpine` container'ında derlenir; ana makinede node/npm
gerekmez (`docker`/`podman` yeterli).

### Ortam değişkenleri

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `BETODDS_POLL` | `20` | Poll aralığı (saniye) |
| `BETODDS_SITE` | betandyou adresi | Kaynak site — **alan adı değişince tek düzeltme noktası** |
| `BETODDS_PROXY` | — | `socks5://127.0.0.1:1080` gibi; site filtreliyse |
| `BETODDS_CA_BUNDLE` | — | Araya giren TLS proxy'si varsa CA dosyası |
| `BETODDS_DATA` | `../data` | Veritabanı ve config dizini |
| `BETODDS_NO_COLLECTOR` | — | `1` ise sadece API çalışır |

### Ağ filtresi (Türkiye'de gerekli)

Kaynak site iki katmanlı bir filtreye takılıyor:

1. **DNS zehirlenmesi** — `betandyou-8229.pro` sistem DNS'inde ISP'nin engel
   sunucusuna (`195.175.254.2`) çözülüyor; o adres `CN=localhost.localdomain`
   imzalı sahte bir sertifika sunuyor. Gerçek IP DoH ile alındı:
   `185.175.166.0` (Cloudflare ve Google aynı yanıtı veriyor).
2. **SNI tabanlı DPI** — doğru IP'ye bağlanılsa bile TLS el sıkışması
   resetleniyor (`errno 104`).

Çözüm — `byedpi` proxy'sini başlat, sonra backend'i çalıştır:

```bash
./scripts/proxy-baslat.sh     # vendor/byedpi'yi derler, 127.0.0.1:1080'de açar
./start.sh
```

`-o 1+s` = ClientHello'yu SNI konumundan bölüp OOB veri olarak gönder. Denenen
stratejilerden `-o 1+s`, `-q 1+s` ve `-r 1+s` çalıştı; `-s`, `-d`, `-f`
çalışmadı. Ayarlar `backend/env` dosyasında (`run.sh` otomatik yükler):

```
BETODDS_PROXY=socks5://127.0.0.1:1080
BETODDS_DNS_OVERRIDE=betandyou-8229.pro=185.175.166.0,eventsstat.com=83.147.204.194
```

DNS override neden gerekli: httpx'in socks5 desteği adres çözümünü proxy'ye
bırakıyor (`socks5h` gibi), proxy de sistem DNS'ini kullandığı için zehirli
yanıta geri düşülüyordu. `app/http.py` içindeki `HostOverrideTransport`
bağlantıyı doğru IP'ye kurar ama SNI ve `Host` başlığını alan adı olarak
bırakır — sertifika doğrulaması da bozulmaz.

### Lig ekleme

İzlenen ligler (`data/leagues.json`):

| champ_id | Lig | tourney_id | maç süresi |
|---|---|---|---|
| 2986291 | FC 26. 5x5 Rush. Süper Lig | 149 | 11 dk |
| 2860561 | FC 25. 3x3. Konferans Ligi | 129 | 10 dk |

**champ_id** lig sayfasının URL'sindeki sayıdır:

```
https://betandyou-8229.pro/tr/esports/virtual/fifa/2860561-fc-25-3x3-conference-league
                                                 ^^^^^^^
```

**tourney_id / iteration** sezon tablosu (eventsstat) adresinden okunur; aynı
değerler feed'de `GetGameZip` yanıtındaki `S` meta alanında da geliyor:

```
https://betandyou-8229.pro/tr/statisticpopup/cyber/fifa/129/219
                                                        ^^^ ^^^
                                                  tourney  iteration
```

Ekleme — `data/leagues.json`'a satır yazın ya da API'yi çağırın:

```bash
curl -X POST "localhost:8000/api/leagues?champ_id=2860561&name=FC%2025%203x3&virtual=true"
```

`virtual=true` şart: sanal ligler feed'de yalnızca `virtualSports=true` ile
listeleniyor ve `sports=` parametresiyle birlikte kullanıldığında API `406`
döndürüyor — bu yüzden filtreleme sadece `champs=` üzerinden yapılıyor.

Ardından sezon tablolarını çekin (tahminin `season` bileşeni buradan gelir):

```bash
curl -X POST "localhost:8000/api/stats/seasons/sync?tourney_id=129&start=190&end=219&champ_id=2860561"
```

`leagues.json` içindeki `extra` alanı iki ayar taşır:

* `tourney_id` — sezon tablosu (eventsstat) için ipucu. Ligin ilk maçı daha
  yakalanmadan senkron yapılabilsin diye var; feed'den gerçek değer
  öğrenilince o kullanılır.
* `match_minutes` — sanal maçın gerçek zamanlı süresi. Canlı maçta "kalan gol
  beklentisi" bu süreye göre eritilir. Arşivden ölçüldü: 5x5 Rush medyan
  10.4 dk (n=74), 3x3 medyan 9.4 dk (n=10). Verilmezse
  `config.LIVE_MATCH_MINUTES` (11) kullanılır.

Yeni bir lig için süreyi birkaç maç biriktikten sonra ölçün:

```sql
SELECT (MAX(t.taken_at) - m.start_ts) / 60.0
FROM matches m JOIN odds_ticks t ON t.event_id = m.event_id
WHERE m.status='finished' AND t.phase='live' GROUP BY m.event_id;
```

**Ligler modelde ayrıktır.** Tahmin havuzu (`form`, `similar`) `champ_id` ile,
sezon gücü `tourney_id` ile sınırlanır. Sebebi ölçülebilir: 5x5 Rush maç başı
~7 gol, 3x3 ~14. İki arşivi tek havuzda toplamak ikisinin de tahminini bozar.
Aynı nedenle `iteration` numaraları turnuvalar arasında çakıştığı için
(149: 1-56, 129: 1-219) sezon sorguları her zaman `tourney_id` ile filtrelenir.

## Beklenen gol kalibrasyonu

Gösterilen beklenti, marketten çıkan **ham** değer değil:

```
ham beklenti − 0.5  →  en yakın 0.5 katına yuvarla
14.85 − 0.5 = 14.35 → 14.5
```

Sabitler `config.py` içinde (`BETODDS_EXPECT_OFFSET`, `BETODDS_EXPECT_STEP`).
İşlem arayüzde açıkça yazılır (kartta `(14.85 − 0.5)`, hücrede tam işlem
ipucu olarak) — gösterilen sayının türetilmiş olduğu gizlenmiyor.

**Kural tahminin çıkışına uygulanır, girdilerine değil.** Harman
(`predict.py`) bileşenleri ham değerlerle çalışır; kalibrasyon hem oran
bileşenine hem harmana uygulansaydı düzeltme iki kez inerdi. Ham değerler
`total_raw` / `home_raw` / `away_raw` olarak API'de durur.

Kalibrasyondan **etkilenenler**: alt/üst çizgi seçimi (beklentiye en yakın
çizgi), ev/deplasman ayrışımı (pay kesin skordan, seviye kalibre toplamdan),
canlı maçta kalan gol beklentisi, ve `expect_hit` ("beklenti tuttu")
ölçütü — 1002 maçlık arşivde tutma oranı %49.8'den %52.1'e çıktı, çünkü
beklenti alt sınır gibi okunuyor ve alt sınır düştü.

## Referans oranlar ve sonuçlandırma

**Geçerli oranlar, maçın başlamasından hemen önceki settir.** Maç içinde oranlar
değişse bile referans bu değildir. Toplayıcı iki set tutar:

| Faz | Ne zaman | Rol |
|---|---|---|
| `prematch` | maç ilk görüldüğünde (~25 dk önce) | sigorta — toplayıcı çökerse elde bir şey kalsın |
| `prekickoff` | başlangıca son 3 dakika, her poll'da tazelenir | **referans set** |

Ölçülen: referans set başlangıçtan **1 saniye** önce alınabiliyor. (Bu ligde maç
öncesi oranlar zaten oynamıyor — açılış ve referans setleri birebir aynı çıktı —
ama tanım gereği referans olan `prekickoff`.)

Maç bittiğinde `GET /api/matches/{id}/odds` her seçeneği final skora göre
sonuçlandırır (`won` / `lost` / `void` / `null`) ve arayüz tutan ihtimalleri
işaretler. Sonuçlandırma `markets.py:settle()` içinde; 23 birim testi var.

**Sonuçlandırılabilen:** maç sonucu, handikap, çifte şans, toplam gol, ev/deplasman
toplamı, kesin skor, tam toplam gol.

**Sonuçlandırılamayan** (uydurmak yerine işaretsiz bırakılıyor):

- `G=14` **Tek/Çift** — market doğrulandı (ima edilen olasılık her maçta tam
  0.500/0.500 ve G=9939 dağılımının tek/çift ayrımıyla örtüşüyor) ama iki ayak da
  hep 1.92 geldiği için hangisinin "tek" olduğu ayırt edilemedi.
- `G=20` **N. golü atan takım** — T388/T389, kesin skor marketinden türetilen
  ev/deplasman gol payını birebir izliyor (0.407↔0.415, 0.385↔0.385, 0.485↔0.496),
  T390 sabit ~0.018 ile "o gol atılmaz". Sonuçlandırmak için gol **sırası** gerekir;
  elimizde yalnızca final skor var.
- `G=19` — çözülemedi. Ortak dağılımdan türetilen sekiz aday olayın en iyisi bile
  0.150 ortalama hata veriyor (G=20 doğrulaması 0.01 içindeydi).

## Maç öncesi arşiv kapsaması

Kural: **listelenen ve henüz oynanmamış her maçın tam market seti saklanır.**
Site bu lig için aynı anda yalnızca ~4 maç listeliyor (LineFeed bu ligde boş
döner, `count=200` de aynı 4'ü verir) — yani "listelenmiş maçlar" kayan bir
pencere ve maçlar başlangıçtan ~25 dakika önce görünür.

Toplayıcı her poll'da:

1. Henüz başlamamış her maç için arşiv durumunu kontrol eder —
   `none` / `partial` / `complete`.
2. `complete` değilse yeniden çeker. **Sadece kaydın varlığına bakmak yetmez:**
   oranların bir kısmı askıya alınmışken (`B=true`) çekilen snapshot birkaç
   seçenekle döner; böyle bir yakalama `partial` sayılır ve maç başlayana kadar
   daha dolusuyla değiştirilir. Bir snapshot ancak 1X2 grubunu içeriyor ve
   `MIN_PREMATCH_OUTCOMES` (40) seçeneği aşıyorsa `complete` sayılır — gerçek
   setler 98–110 arası gelir.
3. Bir maç tam arşiv olmadan başlarsa `prematch_missed` işaretlenir. Bu
   **geri alınamaz**: site maç bitince oranları siliyor.

Kapsama `GET /api/coverage` ile ölçülür ve Arşiv sayfasının üstünde gösterilir:

```json
{"listed": 17, "archived": 13, "pending": 0, "missed": 4, "pct": 76.5,
 "upcoming_listed": 2, "upcoming_archived": 2}
```

`pending` yakalanabilir (maç henüz başlamadı), `missed` kalıcı açıktır.

## Feed'in tuhaflığı: parametre sırası

Sunucu sorgu parametrelerinin **sırasını** doğruluyor. Şu dizilim `200` döner:

```
champs, count, lng, mode, country, getEmpty, virtualSports, noFilterBlockEvent
```

Aynı parametreler, aynı değerler, farklı sırada → **`406 Not Acceptable`**.
Örneğin `virtualSports`'u `noFilterBlockEvent`'ten sonraya almak isteği kırar.
Bu yüzden `feed.py` parametreleri sözlük değil **liste** olarak veriyor;
sözlüğe çevirip sıralamayı bozmayın.

## API

| Uç | Açıklama |
|---|---|
| `GET /api/health` | Toplayıcı durumu + DB sayaçları |
| `GET /api/leagues` | İzlenen ligler (kısa ad, tourney_id) |
| `GET /api/dashboard` | Lig sayfasının tüm verisi (`champ_id` ile daralır) |
| `GET /api/live` | Devam eden ve yaklaşan maçlar |
| `GET /api/results` | Biten maçlar — `hit=yes/no` ile beklenti filtresi |
| `GET /api/matches` | Filtreli maç listesi (`team`, `champ_id`, `status`) |
| `GET /api/matches/{id}/h2h` | Karşılaşma geçmişi, son sezonlar, aynı oranlı maçlar, bahis önerisi |

"Aynı oranlı maçlar" ölçütü: takımın kendi ayağı ±`BETODDS_SAME_ODDS_GAP`
(0.02) yakın olacak **ve** 1/X/2 ayaklarından en az
`BETODDS_SAME_ODDS_MIN_LEGS` (2) tanesi tutacak. Ayaklar takımın bakış
açısıyla hizalanır (kendi oranı, beraberlik, rakip oranı), yani takım
geçmişte diğer tarafta oynadıysa 1 ile 2 yer değiştirir.

| `GET /api/matches/{id}/odds` | Maç öncesi tam market seti (etiketlenmiş) |
| `GET /api/matches/{id}/ticks` | Oran hareketi zaman serisi |
| `GET /api/coverage` | Maç öncesi arşiv kapsaması (`champ_id`) |
| `GET /api/stats/teams` | Bizim arşivden takım formu |
| `GET /api/stats/seasons` | eventsstat sezon tabloları |
| `POST /api/stats/seasons/sync` | Sezon tablolarını + o sezonun maçlarını çeker |
| `GET /api/stream` | SSE — her poll'da olay |

Arayüz üç sayfa: her ligin kendi **canlı** sayfası (`/lig/<champ_id>`),
**Arşiv** ve **Sonuçlar**. Lig seçimi uygulama geneli; canlı sekmeleri,
Arşiv'deki ve Sonuçlar'daki lig anahtarı aynı seçimi paylaşır.

Tam liste: `http://localhost:8000/docs`

## Market kodları

Feed market **isimlerini göndermiyor**, sadece sayısal `G` (grup) ve `T`
(seçenek) kodları var. `backend/app/markets.py` içinde çözülenler:

| Kod | Market |
|---|---|
| G=1 T=1/2/3 | Maç sonucu 1 / X / 2 |
| G=8 T=4/5/6 | Çifte şans 1X / 12 / X2 |
| G=2 T=7/8 | Handikap (P = çizgi) |
| G=17 T=9/10 | Toplam gol Üst / Alt |
| G=15, G=62 | Ev sahibi / deplasman toplamı |
| G=14 T=182/183 | Karşılıklı gol var / yok |
| G=136 | Kesin skor, P = `ev.deplasman` (4.006 → 4-6) |
| G=9939 | Tam toplam gol, P = gol sayısı |

`G=19` ve `G=20` **çözülemedi**; uydurmak yerine ham kod gösteriliyor. Gerekçe
ve doğrulama yöntemi `markets.py` içindeki yorumlarda.

## Test

```bash
# Frontend gerçekten render oluyor mu (jsdom içinde çalıştırır):
docker run --rm --network=host -v "$PWD/frontend:/app:z" -w /app \
  -e SMOKE_URL=http://127.0.0.1:8000/ node:20-alpine npm run smoke
```

## Bilinen kısıtlar

- **Geçmişe dönük oran alınamaz.** Toplayıcı çalışmadığı sürede oynanan
  maçların oranları kalıcı olarak kayıptır.
- Bazı ağlarda kaynak alan adları DPI/TLS filtresine takılıyor
  (`CERTIFICATE_VERIFY_FAILED` / bağlantı zaman aşımı). Bu durumda
  `BETODDS_PROXY` ayarlanmalı; toplayıcı hatayı `/api/health` üzerinden
  bildirir ve arayüzün üst şeridinde kırmızı olarak gösterir.
- Sezon tabloları eventsstat sayfasından Node ile ayrıştırılır; ana makinede
  `node` yoksa `/api/stats/seasons/sync` çalışmaz (mevcut kayıtlar okunur).

## Görsel doğrulama

Grafik geometrisi jsdom'da doğrulanamaz (layout yok), bu yüzden gerçek tarayıcıda
ekran görüntüsü alınır:

```bash
docker run --rm --network=host -v "$PWD/frontend:/app:z" -w /app node:20-alpine \
  sh -c "apk add --no-cache chromium && npm i -D puppeteer-core && \
         CHROME=/usr/bin/chromium-browser node scripts/shot.mjs"
```

`scripts/shot.mjs` tam sayfayı, `scripts/shot-el.mjs` tek paneli yakalar. İkisi de
konsol hatalarını ve çizilen SVG/çubuk/çizgi sayısını raporlar.

**Not:** `fullPage: true` ile alınan görüntüde sayfanın en altındaki grafik boş
çıkabiliyor (ResponsiveContainer, puppeteer'ın viewport yeniden boyutlandırmasıyla
anlık olarak sıfır ölçüyor). Bu bir render hatası değil; şüphelenirsen
`shot-el.mjs` ile o paneli ayrı yakala.

## Grafik renkleri

Kategorik seri renkleri doğrulanmış paletten alındı ve kendi koyu yüzeyimize
(`#171b24`) karşı test edildi:

| Slot | Hex | Kullanım |
|---|---|---|
| 1 | `#3987e5` | 1 — ev sahibi |
| 2 | `#d95926` | X — beraberlik |
| 3 | `#199e70` | 2 — deplasman |

Altı kontrolün hepsi geçiyor (en kötü CVD ΔE 9.4, normal görüş ΔE 26.5, kontrast
≥ 3:1). İlk denediğim renkler (`#4da3ff / #fbbf24 / #f472b6`) koyu yüzeyde
parlaklık bandında **FAIL** veriyordu. Renk değiştirirsen doğrulayıcıyı yeniden
çalıştır — göz kararı yapma.
