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

# Hazir ikili pakete dahil (vendor/byedpi-linux-x86_64/ciadpi). Once
# derlemeyi deniyoruz: yerelde derlenen ikili hedefin glibc'sine uyar,
# hazir olan ise derlendigi surumden (GLIBC_2.34) eskisinde calismaz.
PREBUILT="vendor/byedpi-linux-$(uname -m)/ciadpi"

if [ ! -x "$BIN" ]; then
  if command -v make >/dev/null && command -v cc >/dev/null; then
    echo "-> ciadpi derleniyor ($BUILD)..."
    mkdir -p "$BUILD"
    cp -r vendor/byedpi/. "$BUILD/"
    # Derleyici uyarilari (kavl.h) normal; hata olursa cikti tekrar gosterilir.
    make -C "$BUILD" >/dev/null 2>&1 || { make -C "$BUILD"; exit 1; }
  elif [ -x "$PREBUILT" ]; then
    echo "-> derleyici yok; pakete dahil hazir ikili kullaniliyor."
    mkdir -p "$BUILD"
    cp "$PREBUILT" "$BIN"
  else
    echo "HATA: ciadpi ne derlenebiliyor ne de hazir ikili var." >&2
    echo "  derleyici kurun (Debian/Ubuntu: apt install build-essential)" >&2
    exit 1
  fi
fi

mkdir -p logs
# shellcheck disable=SC2086
nohup "$BIN" -i 127.0.0.1 -p "$PORT" $ARGS >>logs/proxy.log 2>&1 &
echo $! > logs/proxy.pid
sleep 1

if command -v ss >/dev/null && ! ss -ltn 2>/dev/null | grep -q ":$PORT "; then
  echo "HATA: proxy baslamadi. logs/proxy.log:"
  tail -20 logs/proxy.log
  exit 1
fi
echo "-> proxy hazir: socks5://127.0.0.1:$PORT  (strateji: $ARGS)"
