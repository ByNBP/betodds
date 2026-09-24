#!/usr/bin/env bash
# Kaynak sitelere erisimi test eder; gerekiyorsa backend/env dosyasini yazar.
#
# Iki katmanli filtre olabiliyor:
#   1) DNS zehirlenmesi - alan adi ISP'nin engel sunucusuna cozulur
#      (sertifika CN=localhost.localdomain gelir)
#   2) SNI tabanli DPI  - dogru IP'ye baglanilsa bile TLS resetlenir
set -uo pipefail
cd "$(dirname "$0")/.."

# Her host icin uygulamanin GERCEKTEN kullandigi yolu deniyoruz: eventsstat'in
# kok URL'si erisilebilirken bile bos donuyor, "/" ile test etmek yaniltir.
ENV_FILE=backend/env
PROXY_DEFAULT=socks5://127.0.0.1:1080

# Ayna adresi TEK KAYNAK: var olan backend/env icindeki BETODDS_SITE. Burada
# ikinci bir sabit tutmak, site degisince bu betigi sessizce eski adrese
# bakar hale getiriyordu.
SITE_DEFAULT=https://betandyou-1268.pro
SITE="$(sed -n 's/^BETODDS_SITE=//p' "$ENV_FILE" 2>/dev/null | tail -1)"
SITE="${SITE:-$SITE_DEFAULT}"
SITE_HOST="${SITE#*://}"; SITE_HOST="${SITE_HOST%%/*}"

HOSTS=("$SITE_HOST" eventsstat.com)
declare -A PROBE=(
  ["$SITE_HOST"]="/tr/"
  [eventsstat.com]="/tr/statisticpopup/cyber/fifa/149/56"
)

say() { printf '%s\n' "$*"; }

doh() {   # $1=hostname -> gercek IP (DoH; yerel DNS'e guvenmiyoruz)
  curl -s --max-time 12 -H 'accept: application/dns-json' \
    "https://cloudflare-dns.com/dns-query?name=$1&type=A" \
    | grep -o '"data":"[0-9.]*"' | head -1 | cut -d'"' -f4
}

direct_ok() {  # $1=host $2=ip(bos olabilir)
  local args=(-s --max-time 12 -o /dev/null -w '%{http_code}')
  [ -n "${2:-}" ] && args+=(--resolve "$1:443:$2")
  [ "$(curl "${args[@]}" "https://$1${PROBE[$1]}" 2>/dev/null)" != "000" ]
}

proxy_ok() {   # $1=host $2=ip
  [ "$(curl -s --max-time 15 --socks5 127.0.0.1:1080 --resolve "$1:443:$2" \
        -o /dev/null -w '%{http_code}' "https://$1${PROBE[$1]}" 2>/dev/null)" != "000" ]
}

say "Ag durumu kontrol ediliyor..."
declare -A REAL_IP
need_override=0
need_proxy=0

for h in "${HOSTS[@]}"; do
  printf '  %-24s ' "$h"
  if direct_ok "$h" ""; then
    say "dogrudan erisilebiliyor"
    continue
  fi
  ip="$(doh "$h")"
  if [ -z "$ip" ]; then
    say "COZULEMEDI (DoH yaniti yok)"; continue
  fi
  REAL_IP[$h]="$ip"
  need_override=1
  if direct_ok "$h" "$ip"; then
    say "gercek IP ile calisiyor ($ip) -> DNS override yeterli"
  elif proxy_ok "$h" "$ip"; then
    say "proxy + gercek IP ile calisiyor ($ip)"
    need_proxy=1
  else
    say "ERISILEMIYOR ($ip) -> DPI bypass proxy'si gerekiyor"
    need_proxy=1
  fi
done

overrides=""
for h in "${!REAL_IP[@]}"; do
  overrides="${overrides:+$overrides,}$h=${REAL_IP[$h]}"
done

{
  echo "# scripts/detect-network.sh tarafindan uretildi - $(date '+%Y-%m-%d %H:%M')"
  echo "BETODDS_SITE=$SITE"
  echo "BETODDS_POLL=20"
  [ "$need_override" = 1 ] && echo "BETODDS_DNS_OVERRIDE=$overrides"
  if [ "$need_proxy" = 1 ]; then
    echo "BETODDS_PROXY=$PROXY_DEFAULT"
  else
    echo "# BETODDS_PROXY=$PROXY_DEFAULT"
  fi
} > "$ENV_FILE"

say ""
say "-> $ENV_FILE yazildi:"
sed 's/^/     /' "$ENV_FILE"
if [ "$need_proxy" = 1 ]; then
  say ""
  say "  DPI bypass proxy'si gerekiyor. Kaynak depoda gomulu (vendor/byedpi):"
  say "    ./scripts/proxy-baslat.sh"
  say "  (bu makinede calisan strateji: -r 1+s; tutmazsa -o 1+s veya -q 1+s deneyin)"
fi
