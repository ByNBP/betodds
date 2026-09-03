#!/usr/bin/env bash
# Yeni bir makinede projeyi ayaga kaldirir.
#
# Iki yol var; hangisi mumkunse onu secer:
#   A) Konteyner  - tek bagimlilik: docker (veya podman). Onerilen.
#   B) Yerel      - python3.10+ gerekir; arayuz icin pakete dahil edilen
#                   hazir dist kullanilir (node/npm sart degil).
set -uo pipefail
cd "$(dirname "$0")/.."

have() { command -v "$1" >/dev/null 2>&1; }
say()  { printf '%s\n' "$*"; }
die()  { printf 'HATA: %s\n' "$*" >&2; exit 1; }

MODE="${BETODDS_SETUP_MODE:-auto}"
[ "${1:-}" = "--native" ] && MODE=native
[ "${1:-}" = "--docker" ] && MODE=docker

say "=== BetOdds kurulum ==="
mkdir -p data

# --- ag ayarlari -------------------------------------------------------
if [ ! -f backend/env ]; then
  say ""
  say "[1/3] Ag durumu tespit ediliyor..."
  ./scripts/detect-network.sh || say "  (tespit basarisiz - backend/env.example'i elle kopyalayin)"
else
  say ""
  say "[1/3] backend/env zaten var, dokunulmadi."
fi

# backend/env proxy istiyorsa onu da ayaga kaldir: 1080 bos kalirsa httpx
# baglanamayan bir socks5'e gider ve HICBIR istek cikmaz.
if grep -qE '^\s*BETODDS_PROXY=socks5://(127\.0\.0\.1|localhost):' backend/env 2>/dev/null; then
  ./scripts/proxy-baslat.sh || say "  UYARI: proxy baslatilamadi; eventsstat (sezon tablolari) calismayabilir."
fi

# --- calisma ortami ----------------------------------------------------
say ""
if [ "$MODE" != "native" ] && (have docker || have podman); then
  RUNNER=$(have docker && echo docker || echo podman)
  say "[2/3] Konteyner yolu ($RUNNER)"
  $RUNNER build -t betodds:latest . || die "imaj derlenemedi"
  say ""
  say "[3/3] Hazir. Calistirmak icin:"
  say ""
  say "  $RUNNER run -d --name betodds --restart unless-stopped \\"
  say "    --network=host -v \"\$PWD/data:/app/data\" \\"
  say "    --env-file backend/env betodds:latest"
  say ""
  say "  (--network=host, host'ta calisan DPI proxy'sine erisim icin gerekli."
  say "   Proxy gerekmiyorsa yerine: -p 8000:8000)"
  say ""
  say "  Ardindan: http://localhost:8000"
  exit 0
fi

say "[2/3] Yerel yol (python venv)"
have python3 || die "python3 bulunamadi"
PYV=$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')
python3 -c 'import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)' \
  || die "python 3.10+ gerekiyor (bulunan: $PYV)"
say "  python $PYV"

[ -d backend/.venv ] || python3 -m venv backend/.venv || die "venv olusturulamadi"
backend/.venv/bin/pip install -q --upgrade pip
backend/.venv/bin/pip install -q -r backend/requirements.txt || die "bagimliliklar kurulamadi"
say "  bagimliliklar kuruldu"

have node || say "  UYARI: node yok -> sezon tablosu cekimi (eventsstat) calismaz;
         mevcut kayitlar okunur, diger her sey normal calisir."

if [ ! -d frontend/dist ]; then
  if have npm; then
    say "  frontend derleniyor..."
    (cd frontend && npm ci --no-audit --no-fund && npm run build) || die "frontend derlenemedi"
  else
    die "frontend/dist yok ve npm de yok. Pakete dist dahil edilmis olmaliydi."
  fi
else
  say "  frontend/dist hazir"
fi

say ""
say "[3/3] Hazir. Calistirmak icin:  ./start.sh"
say "  (yalnizca backend, derlenmis arayuzu de servis eder)"
say "  Ardindan: http://localhost:8000"
say ""
say "  Sonraki acilislarda proxy'yi de baslatmayi unutmayin:"
say "    ./scripts/proxy-baslat.sh && ./start.sh"
