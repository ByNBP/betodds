#!/usr/bin/env bash
# DPI bypass proxy'sini (byedpi/ciadpi) 127.0.0.1:1080'de baslatir.
#
# Neden gerekli: eventsstat.com (sezon tablolari) bu aglarda SNI tabanli DPI'a
# takiliyor - dogru IP'ye baglanilsa bile TLS resetleniyor. backend/env
# icindeki BETODDS_PROXY bu adresi gosterir; proxy ayakta degilse toplayici
# hicbir istek atamaz.
#
# Kaynak vendor/byedpi altinda GOMULU (GitHub'a erisim gerekmez). Derleme
# vendor/ ICINDE DEGIL, tools/byedpi-linux altinda yapilir: aksi halde host'ta
# uretilen glibc ikilisi ve .o dosyalari docker derleme baglamina girip
# Alpine imajindaki 'make' adimini "guncel" gosteriyor ve musl konteynerine
# glibc ikilisi kopyalaniyordu.
#
# Compose ile calistiriyorsaniz buna gerek yok: proxy servisi yigina dahil.
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${BETODDS_PROXY_PORT:-1080}"
# Strateji: kok .env icindeki CIADPI_ARGS ile ayni varsayilan.
ARGS="${CIADPI_ARGS:--r 1+s}"
BUILD=tools/byedpi-linux
BIN="$BUILD/ciadpi"

if command -v ss >/dev/null && ss -ltn 2>/dev/null | grep -q ":$PORT "; then
  echo "-> $PORT zaten dinleniyor; proxy calisiyor sayiliyor."
  exit 0
fi

if [ ! -x "$BIN" ]; then
  echo "-> ciadpi derleniyor ($BUILD)..."
  mkdir -p "$BUILD"
  cp -r vendor/byedpi/. "$BUILD/"
  # Derleyici uyarilari (kavl.h) normal; hata olursa cikti tekrar gosterilir.
  make -C "$BUILD" >/dev/null 2>&1 || { make -C "$BUILD"; exit 1; }
fi

# shellcheck disable=SC2086
nohup "$BIN" -i 127.0.0.1 -p "$PORT" $ARGS >/tmp/ciadpi.log 2>&1 &
sleep 1

if command -v ss >/dev/null && ! ss -ltn 2>/dev/null | grep -q ":$PORT "; then
  echo "HATA: proxy baslamadi. /tmp/ciadpi.log:"
  tail -20 /tmp/ciadpi.log
  exit 1
fi
echo "-> proxy hazir: socks5://127.0.0.1:$PORT  (strateji: $ARGS)"
