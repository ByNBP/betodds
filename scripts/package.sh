#!/usr/bin/env bash
# Projeyi baska bir makineye tasimak icin arsiv olusturur.
#
# Iceri girenler : kaynak kod, lig konfigurasyonu, VERITABANI, calisan
#                  backend/env, derlenmis frontend/dist, vendor/ (Windows
#                  Python + wheel + Node + byedpi)
# Disarida kalan : .venv (mutlak yollar), node_modules (platform ikilileri),
#                  vendor/byedpi Linux derleme ciktilari
set -euo pipefail
cd "$(dirname "$0")/.."

# --with-images : images/*.tar dosyalarini da paketle (~310 MB).
# Hedef makinede ag engelliyse derleme hic denenmez; KURULUM-OFFLINE.bat
# imajlari dogrudan yukler. Uretmek icin:
#   docker build --no-cache -t betodds:latest .
#   docker build --no-cache -t betodds-proxy:latest -f docker/proxy.Dockerfile .
#   docker save betodds:latest       -o images/betodds.tar
#   docker save betodds-proxy:latest -o images/betodds-proxy.tar
#
# DIKKAT: 'docker compose build' KULLANMAYIN. podman-compose altinda kaynak
# degisse bile var olan imaji yeniden derlemiyor ve --no-cache bayragini
# tanimiyor ("unknown flag") - sessizce ESKI imaj paketlenir.
WITH_IMAGES=0
ARGS=()
for a in "$@"; do
  case "$a" in
    --with-images) WITH_IMAGES=1 ;;
    *) ARGS+=("$a") ;;
  esac
done
OUT="${ARGS[0]:-$HOME/betodds-$(date +%Y%m%d-%H%M).zip}"

# Cevrimdisi paketin ise yaramasi icin vendor/ altindaki Windows ikilileri
# sart; bunlar depoda tutulmuyor (bkz. .gitignore). Eksikse kurulum hedef
# makinede patlardi - burada, paketlemeden ONCE soyleyelim.
#
# Kontrol --with-images'tan BAGIMSIZ: gomulu Python + wheel'ler her paket
# icine giriyor ve KURULUM-OFFLINE.bat'in YEREL yolu yalnizca onlara
# dayaniyor. Docker imajlari sadece konteyner yolu icin gerekli.
missing=()
compgen -G "vendor/python/*embed-amd64.zip" >/dev/null || missing+=("vendor/python")
compgen -G "vendor/node/*.zip"              >/dev/null || missing+=("vendor/node")
compgen -G "vendor/wheels/*.whl"            >/dev/null || missing+=("vendor/wheels")
OFFLINE_OK=1
if [ ${#missing[@]} -gt 0 ]; then
  OFFLINE_OK=0
  if [ "$WITH_IMAGES" = 1 ]; then
    echo "HATA: cevrimdisi paket icin eksik: ${missing[*]}" >&2
    echo "  once calistirin: ./scripts/vendor-indir.sh" >&2
    exit 1
  fi
  echo "UYARI: eksik: ${missing[*]} - paket cevrimdisi kurulamayacak" >&2
  echo "  cevrimdisi paket icin: ./scripts/vendor-indir.sh" >&2
fi
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
STAGE="$TMP/betodds"
mkdir -p "$STAGE/data"

# Kaynak
# backend/env DAHIL: calisan ayarlar (site aynasi, DNS override, proxy) hedef
# makinede de gecerli. Makineye ozel olan tek sey proxy'nin ayakta olup
# olmadigi ve onu kurulum betigi kendisi belirliyor.
for p in KURULUM.ps1 KURULUM.bat KURULUM-OFFLINE.ps1 KURULUM-OFFLINE.bat \
         BASLAT.bat OFFLINE-README.md \
         backend/app backend/requirements.txt backend/run.sh backend/env \
         backend/env.example backend/import_local.py backend/merge_db.py \
         frontend/src frontend/index.html \
         frontend/package.json frontend/package-lock.json frontend/vite.config.js \
         frontend/scripts frontend/dist scripts docker vendor Dockerfile \
         docker-compose.yml .env .dockerignore .gitattributes .gitignore README.md \
         dev.sh start.sh build-frontend.sh; do
  [ -e "$p" ] || continue
  mkdir -p "$STAGE/$(dirname "$p")"
  cp -r "$p" "$STAGE/$(dirname "$p")/"
done

# vendor/byedpi Linux derleme ciktilari pakete girmesin (Windows'ta ise
# yaramaz; Windows ikilisi vendor/byedpi-win icinde geliyor).
rm -f "$STAGE"/vendor/byedpi/*.o "$STAGE"/vendor/byedpi/ciadpi
# Linux paketine ait varliklar da girmesin: manylinux wheel'leri (~33 MB) ve
# glibc ikilisi Windows'ta tamamen olu agirlik.
rm -rf "$STAGE"/vendor/wheels-linux "$STAGE"/vendor/byedpi-linux-*
# __pycache__ bu makinenin Python surumune ait (.pyc etiketli); tasinmasi
# gereksiz.
find "$STAGE" -name '__pycache__' -type d -prune -exec rm -rf {} +

# images/ : hazir docker imajlari yalnizca --with-images ile girer (300+ MB).
mkdir -p "$STAGE/images"
[ -f images/BURAYA-KOYUN.txt ] && cp images/BURAYA-KOYUN.txt "$STAGE/images/"

# Veritabani: canli WAL'i kopyalamak bozuk dosya verir.
# VACUUM INTO tutarli ve sikistirilmis tek dosya uretir.
if [ -f data/betodds.db ]; then
  STAGE="$STAGE" python3 - <<'PY'
import sqlite3, os
src = "data/betodds.db"
dst = os.environ["STAGE"] + "/data/betodds.db"
con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
con.execute("VACUUM INTO ?", (dst,))
con.close()
n = sqlite3.connect(dst)
tables = [r[0] for r in n.execute(
    "SELECT name FROM sqlite_master WHERE type='table'")]
print(f"  veritabani kopyalandi: {os.path.getsize(dst)/1024:.0f} KB, "
      f"{len(tables)} tablo")
for t in ("matches", "odds_snapshots", "odds_values", "odds_ticks", "season_tables"):
    if t in tables:
        print(f"    {t}: {n.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}")
n.close()
PY
fi
[ -f data/leagues.json ] && cp data/leagues.json "$STAGE/data/"

if [ "$WITH_IMAGES" = 1 ]; then
  echo
  echo "  hazir imajlar paketleniyor..."
  # KURULUM-OFFLINE.ps1 images\*.tar ariyor (gz DEGIL: 'docker load' akisi
  # dogrudan tar bekliyor, sikistirmayi zip zaten yapiyor).
  for img in betodds betodds-proxy; do
    src="images/$img.tar"
    if [ -f "$src" ]; then
      cp "$src" "$STAGE/images/"
      # printf %f locale'e bagli (tr_TR virgul bekler) - tamsayi MB kullaniyoruz
      echo "    $img.tar  $(( $(stat -c%s "$src") / 1048576 )) MB"
    else
      echo "    UYARI: $src yok - once uretin:"
      echo "      docker compose build && docker save $img:latest -o $src"
    fi
  done
fi

# .bat/.ps1 CRLF olmali: LF satir sonlu bir .bat'ta 'goto'/etiket davranisi
# Windows'ta bozulabiliyor. Kabuk betikleri ve Dockerfile LF kalir.
find "$STAGE" -type f \( -name '*.bat' -o -name '*.ps1' \) -print0 |
  while IFS= read -r -d '' f; do
    python3 -c "
import sys
p = sys.argv[1]
d = open(p, 'rb').read().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
open(p, 'wb').write(d)
" "$f"
  done

case "$OUT" in
  *.zip)
    # Windows hedefi: zip. Kabuk betikleri ve Dockerfile LF kalmali,
    # sadece .bat/.ps1 CRLF olmali - zip icerigi oldugu gibi tasir.
    ( cd "$TMP" && python3 -c "
import os, sys, zipfile
out = sys.argv[1]
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk('betodds'):
        for f in files:
            fp = os.path.join(root, f)
            z.write(fp, fp)
" "$OUT" )
    ;;
  *) tar -czf "$OUT" -C "$TMP" betodds ;;
esac
echo
echo "-> $OUT  ($(du -h "$OUT" | cut -f1))"
echo
if [ "$OFFLINE_OK" = 1 ]; then
  BAT=KURULUM-OFFLINE.bat
  if [ "$WITH_IMAGES" = 1 ]; then
    NOTE="(hicbir sey indirmez; Python/Node/imajlar paketin icinde)"
  else
    NOTE="(hicbir sey indirmez; gomulu Python ile yerel kurulum)"
  fi
else
  BAT=KURULUM.bat
  NOTE="(her seyi indirir, derler, calistirir ve tarayiciyi acar)"
fi
echo "   Windows:"
echo "     1. $(basename "$OUT") dosyasini sag tik -> Tumunu ayikla"
echo "     2. Olusan betodds klasorunde $BAT dosyasina cift tiklayin"
echo "        $NOTE"
if [ "$OFFLINE_OK" = 1 ] && [ "$WITH_IMAGES" = 0 ]; then
  echo "     Docker yolu icin imajlar gerekir: --with-images ile paketleyin."
fi
echo
echo "   Linux: ayri paket - ./scripts/paket-linux.sh (bkz. LINUX-README.md)"
