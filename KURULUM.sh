#!/usr/bin/env bash
# BetOdds - Linux kurulumu. Tek komut: ./KURULUM.sh
#
# Yaptiklari:
#   1) Python 3.10+ bulur, backend/.venv olusturur
#   2) Bagimliliklari PAKETE DAHIL wheel'lerden kurar (ag gerekmez)
#   3) Gerekiyorsa DPI bypass proxy'sini derleyip baslatir
#   4) Backend'i baslatir, saglik kontrolu yapar, adresi yazar
#
# Arayuz pakete DERLENMIS olarak geliyor: node/npm gerekmez.
set -uo pipefail
cd "$(dirname "$0")"
. scripts/lib-linux.sh

MODE=native
START=1
SYSTEMD=0
for a in "$@"; do
  case "$a" in
    --docker)   MODE=docker ;;
    --native)   MODE=native ;;
    --no-start) START=0 ;;
    --systemd)  SYSTEMD=1 ;;
    -h|--help)
      sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
      say ""
      say "Secenekler:"
      say "  --docker     docker compose ile kur (proxy dahil yigin)"
      say "  --no-start   kur ama baslatma"
      say "  --systemd    systemd kullanici servisi kur (oturum kapansa da calisir)"
      say "  BETODDS_PORT=9000 ./KURULUM.sh   farkli port"
      exit 0 ;;
    *) die "bilinmeyen secenek: $a  (--help)" ;;
  esac
done

say "=== BetOdds kurulumu (Linux) ==="
mkdir -p data logs

# --- 1) ag ayarlari ----------------------------------------------------
# backend/env pakete DAHIL geliyor (calisan site aynasi + DNS override).
# Yoksa tespit et; varsa dokunma - hedef makinede elle degistirilmis olabilir.
say ""
if [ -f backend/env ]; then
  say "[1/5] backend/env var, dokunulmadi."
  say "      site: $(sed -n 's/^BETODDS_SITE=//p' backend/env | tail -1)"
else
  say "[1/5] Ag durumu tespit ediliyor..."
  ./scripts/detect-network.sh \
    || warn "tespit basarisiz - backend/env.example'i kopyalayip elle duzenleyin"
fi

# Varsayilan disi port kalici olsun: sonraki ./BASLAT.sh ve ./DURUM.sh
# ayni portu bulsun diye backend/env'e yaziyoruz.
if [ "$BETODDS_PORT" != 8000 ] && [ -f backend/env ]; then
  if grep -q '^[[:space:]]*BETODDS_PORT=' backend/env; then
    sed -i "s|^[[:space:]]*BETODDS_PORT=.*|BETODDS_PORT=$BETODDS_PORT|" backend/env
  else
    printf '\nBETODDS_PORT=%s\n' "$BETODDS_PORT" >> backend/env
  fi
  say "      port: $BETODDS_PORT (backend/env'e yazildi)"
fi

# --- docker yolu -------------------------------------------------------
if [ "$MODE" = docker ]; then
  RUNNER=""
  have docker && RUNNER=docker
  [ -z "$RUNNER" ] && have podman && RUNNER=podman
  [ -z "$RUNNER" ] && die "docker/podman yok. Yerel kurulum icin: ./KURULUM.sh --native"

  say ""
  say "[2/5] Konteyner yolu ($RUNNER)"
  # Hazir imaj varsa derleme denenmez: hedef agda derleme icin gereken
  # depolara (alpine, pypi, npm) erisim olmayabilir.
  loaded=0
  for img in betodds betodds-proxy; do
    [ -f "images/$img.tar" ] || continue
    say "  images/$img.tar yukleniyor..."
    $RUNNER load -i "images/$img.tar" >/dev/null && loaded=1
  done
  if [ "$loaded" = 0 ]; then
    say "  imajlar derleniyor (birkac dakika)..."
    $RUNNER compose build || die "imaj derlenemedi (ag?). Hazir imaj icin images/ klasorune tar koyun."
  fi
  say ""
  say "[3/5] Yigin baslatiliyor..."
  $RUNNER compose up -d || die "compose baslatilamadi"
  say ""
  say "[4/5] Saglik kontrolu..."
  wait_health 60 && say "  backend ayakta" || warn "backend saglik vermedi: $RUNNER compose logs"
  say ""
  say "[5/5] Hazir -> http://localhost:$BETODDS_PORT"
  say "  Durdurmak: $RUNNER compose down"
  exit 0
fi

# --- 2) python + venv --------------------------------------------------
say ""
say "[2/5] Python ortami"
PY="$(find_python)" || die "python 3.10+ (ve venv modulu) bulunamadi.
  Debian/Ubuntu : sudo apt install python3 python3-venv
  Fedora        : sudo dnf install python3
  Arch          : sudo pacman -S python"
say "  $PY -> $("$PY" -V 2>&1)"

VPY=backend/.venv/bin/python
WHEELS="vendor/wheels-linux/$(uname -m)"

# Debian/Ubuntu python3-venv'i ayri paketliyor. Kurulu degilken
# `python -m venv` DIZINI OLUSTURUP ensurepip adiminda patliyor: geriye
# pip'siz, yarim bir .venv kaliyor. Ikinci calistirmada "zaten var" gorunup
# kuruluma gecmek "No module named pip" ile bitiyordu. Cozum: --without-pip
# ile olustur, pip'i pakete dahil wheel'den bootstrap et - boylece
# python3-venv paketi hic gerekmiyor.
make_venv() {
  rm -rf backend/.venv
  "$PY" -m venv backend/.venv 2>/dev/null && return 0
  say "  ensurepip yok (python3-venv eksik) - venv pip'siz olusturuluyor"
  "$PY" -m venv --without-pip backend/.venv
}

# pip'i wheel'in ICINDEN calistirabiliyoruz: wheel bir zip ve zipimport
# calisiyor. Ag ve ensurepip gerekmez.
ensure_pip() {
  "$VPY" -m pip --version >/dev/null 2>&1 && return 0
  local w
  w="$(ls "$WHEELS"/pip-*.whl 2>/dev/null | head -1)"
  if [ -n "$w" ]; then
    say "  pip yok - pakete dahil wheel'den kuruluyor"
    "$VPY" "$w/pip" install -q --no-index --find-links "$WHEELS" pip \
      >/dev/null 2>&1 && "$VPY" -m pip --version >/dev/null 2>&1 && return 0
  fi
  "$VPY" -m ensurepip --default-pip >/dev/null 2>&1 && return 0
  return 1
}

if [ -x backend/.venv/bin/python ] && backend/.venv/bin/python -c '' 2>/dev/null; then
  say "  backend/.venv zaten var"
else
  # Tasinan bir .venv icindeki mutlak yollar bozuk olur.
  [ -e backend/.venv ] && say "  mevcut .venv kullanilamiyor, yeniden olusturuluyor"
  make_venv || die "venv olusturulamadi.
  Debian/Ubuntu : sudo apt install python3-venv
  Fedora        : sudo dnf install python3"
  say "  backend/.venv olusturuldu"
fi

ensure_pip || die "venv'e pip kurulamadi.
  Debian/Ubuntu : sudo apt install python3-venv
  sonra: rm -rf backend/.venv && ./KURULUM.sh"

TAG="$(py_tag "$VPY")"

# Wheel'ler cp surumune ozel (pydantic_core, uvloop, httptools...). Pakette
# hangi surumler varsa onlar; yoksa PyPI'ye dusuyoruz.
if [ -d "$WHEELS" ] && compgen -G "$WHEELS/*$TAG*.whl" >/dev/null; then
  say "  bagimliliklar pakete dahil wheel'lerden kuruluyor ($TAG, ag yok)"
  "$VPY" -m pip install -q --no-index --find-links "$WHEELS" \
    -r backend/requirements.txt || die "wheel'lerden kurulum basarisiz"
else
  if [ -d "$WHEELS" ]; then
    warn "pakette $TAG wheel'i yok ($(uname -m)) - PyPI'den kuruluyor"
  else
    say "  vendor/wheels-linux yok - PyPI'den kuruluyor"
  fi
  "$VPY" -m pip install -q --upgrade pip
  "$VPY" -m pip install -q -r backend/requirements.txt \
    || die "bagimliliklar kurulamadi (ag?).
  Cevrimdisi kurulum icin paketi ./scripts/paket-linux.sh ile uretin."
fi
say "  fastapi/uvicorn/httpx hazir"

# --- 3) arayuz ---------------------------------------------------------
say ""
say "[3/5] Arayuz"
if [ -f frontend/dist/index.html ]; then
  say "  frontend/dist pakete dahil - derleme gerekmiyor"
elif have npm; then
  say "  dist yok, derleniyor..."
  ( cd frontend && npm ci --no-audit --no-fund && npm run build ) \
    || die "frontend derlenemedi"
else
  die "frontend/dist yok ve npm de yok. Paket eksik uretilmis olabilir."
fi

# --- 4) proxy ----------------------------------------------------------
say ""
if proxy_wanted; then
  say "[4/5] DPI bypass proxy'si (backend/env istiyor)"
  proxy_start || warn "proxy baslatilamadi - toplayici veri cekemeyebilir"
else
  say "[4/5] Proxy gerekmiyor (backend/env dogrudan baglaniyor)"
fi

# --- systemd (istege bagli) --------------------------------------------
if [ "$SYSTEMD" = 1 ]; then
  say ""
  say "  systemd kullanici servisi kuruluyor..."
  install_systemd
fi

# --- 5) baslat ---------------------------------------------------------
say ""
if [ "$START" = 0 ]; then
  say "[5/5] Kurulum bitti (--no-start). Baslatmak icin: ./BASLAT.sh"
  exit 0
fi
if [ "$SYSTEMD" = 1 ]; then
  say "[5/5] systemd servisi calisiyor -> http://localhost:$BETODDS_PORT"
  exit 0
fi

say "[5/5] Baslatiliyor..."
backend_start
if wait_health 40; then
  say ""
  say "-> Hazir:  http://localhost:$BETODDS_PORT"
  health_summary "$VPY" | sed 's/^/   /'
  say ""
  say "   Durdurmak : ./DURDUR.sh"
  say "   Durum     : ./DURUM.sh"
  say "   Log       : logs/backend.log"
else
  say ""
  warn "backend saglik vermedi. Son loglar:"
  show_backend_log
  exit 1
fi
