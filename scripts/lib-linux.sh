#!/usr/bin/env bash
# KURULUM.sh / BASLAT.sh / DURDUR.sh / DURUM.sh ortak islevleri.
# Kendi basina calistirilmaz; `. scripts/lib-linux.sh` ile kaynak edilir.

# Port onceligi: ortam degiskeni > backend/env > 8000. Kurulum sirasinda
# verilen port backend/env'e yazilir; aksi halde sonraki ./BASLAT.sh ve
# ./DURUM.sh varsayilana donup YANLIS ornegi raporluyordu.
if [ -z "${BETODDS_PORT:-}" ]; then
  BETODDS_PORT="$(sed -n 's/^[[:space:]]*BETODDS_PORT=//p' backend/env 2>/dev/null | tail -1)"
fi
BETODDS_PORT="${BETODDS_PORT:-8000}"
BETODDS_PROXY_PORT="${BETODDS_PROXY_PORT:-1080}"

LOG_DIR=logs
BACKEND_PIDF="$LOG_DIR/backend.pid"
PROXY_PIDF="$LOG_DIR/proxy.pid"

have() { command -v "$1" >/dev/null 2>&1; }
say()  { printf '%s\n' "$*"; }
warn() { printf 'UYARI: %s\n' "$*" >&2; }
die()  { printf 'HATA: %s\n' "$*" >&2; exit 1; }

# --- python ------------------------------------------------------------
# Dagitimlar "python3"u farkli surumlere bagliyor (22.04 -> 3.10,
# 24.04 -> 3.12). Adaylari en yeniden eskiye deneyip 3.10+ olani seciyoruz;
# secilen surum wheel'lerin hangi cp klasoerunden kurulacagini da belirler.
find_python() {
  local c
  for c in python3.13 python3.12 python3.11 python3.10 python3 python; do
    have "$c" || continue
    "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' \
      2>/dev/null || continue
    # venv modulu ayri paket olabiliyor (Debian: python3-venv).
    "$c" -c 'import venv' 2>/dev/null || continue
    printf '%s\n' "$c"
    return 0
  done
  return 1
}

py_tag() {  # $1=yorumlayici -> cp310 / cp312 ...
  "$1" -c 'import sys; print("cp%d%d" % sys.version_info[:2])'
}

# --- port / surec ------------------------------------------------------
port_busy() {  # $1=port
  if have ss; then
    ss -ltn 2>/dev/null | grep -q ":$1 "
  else
    # ss yoksa: bash'in kendi tcp destegi. Baglanabiliyorsak dolu.
    (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null && exec 3>&- && return 0
    return 1
  fi
}

pid_alive() { [ -n "${1:-}" ] && kill -0 "$1" 2>/dev/null; }

read_pid() { [ -f "$1" ] && tr -dc '0-9' < "$1"; }

stop_pidfile() {  # $1=pidfile $2=ad
  local pid; pid="$(read_pid "$1")"
  if pid_alive "$pid"; then
    kill "$pid" 2>/dev/null
    local i
    for i in $(seq 1 20); do
      pid_alive "$pid" || break
      sleep 0.25
    done
    pid_alive "$pid" && kill -9 "$pid" 2>/dev/null
    say "  $2 durduruldu (pid $pid)"
  else
    say "  $2 zaten calismiyor"
  fi
  rm -f "$1"
}

# --- proxy -------------------------------------------------------------
# backend/env BETODDS_PROXY=socks5://127.0.0.1:... istiyorsa proxy SART:
# 1080 bos kalirsa httpx baglanamayan bir socks5'e gider ve toplayici
# HICBIR istek atamaz - hata da vermez, sadece bos doner.
proxy_wanted() {
  grep -qE '^[[:space:]]*BETODDS_PROXY=socks5://(127\.0\.0\.1|localhost):' \
    backend/env 2>/dev/null
}

proxy_running() { port_busy "$BETODDS_PROXY_PORT"; }

proxy_start() {
  proxy_running && { say "  proxy zaten calisiyor ($BETODDS_PROXY_PORT)"; return 0; }
  mkdir -p "$LOG_DIR"
  BETODDS_PROXY_PORT="$BETODDS_PROXY_PORT" ./scripts/proxy-baslat.sh
}

# --- backend -----------------------------------------------------------
backend_running() {
  pid_alive "$(read_pid "$BACKEND_PIDF")" || port_busy "$BETODDS_PORT"
}

backend_start() {
  # Portun DOLU olmasi bizim backend'in ayakta oldugu anlamina gelmez.
  # Once /api/health soruyoruz: cevap veren bizizdir. Bunu ayirmadan
  # "zaten calisiyor" deyip baslatmayi atliyorduk; port baskasindayken
  # kurulum hicbir sey baslatmadan saglik hatasiyla bitiyordu.
  if health_json >/dev/null; then
    say "  backend zaten calisiyor ($BETODDS_PORT)"
    return 0
  fi
  # Kendi pid'imiz yasiyorsa aciliyor olabilir; wait_health beklesin.
  if pid_alive "$(read_pid "$BACKEND_PIDF")"; then
    say "  backend aciliyor ($BETODDS_PORT)"
    return 0
  fi
  if port_busy "$BETODDS_PORT"; then
    die "$BETODDS_PORT portunu baska bir surec tutuyor (BetOdds degil).
  Kimin tuttugu   : ss -ltnp | grep :$BETODDS_PORT
  Baska port ile  : BETODDS_PORT=8100 ./KURULUM.sh
  (verilen port backend/env'e yazilir, sonraki ./BASLAT.sh onu kullanir)"
  fi
  [ -x backend/.venv/bin/uvicorn ] || die "backend/.venv yok - once ./KURULUM.sh"
  mkdir -p "$LOG_DIR"
  BETODDS_PORT="$BETODDS_PORT" nohup ./backend/run.sh \
    >> "$LOG_DIR/backend.log" 2>&1 &
  echo $! > "$BACKEND_PIDF"
  say "  backend baslatildi (pid $(cat "$BACKEND_PIDF"))"
}

health_json() {
  curl -fsS --max-time 5 "http://127.0.0.1:$BETODDS_PORT/api/health" 2>/dev/null
}

wait_health() {  # $1=saniye (varsayilan 40)
  local n="${1:-40}" i
  for i in $(seq 1 "$n"); do
    health_json >/dev/null && return 0
    # Surec olduyse beklemeye devam etmenin anlami yok.
    pid_alive "$(read_pid "$BACKEND_PIDF")" || [ "$i" -lt 3 ] || return 1
    sleep 1
  done
  return 1
}

# --- ozet --------------------------------------------------------------
# /api/health ciktisini tek satirlik ozete cevirir. Toplayicinin GERCEKTEN
# veri cektigi last_error ile anlasilir; "port aciliyor" yetmez.
health_summary() {
  local h; h="$(health_json)" || return 1
  printf '%s' "$h" | "${1:-python3}" -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(1)
c, b = d.get("collector", {}), d.get("db", {})
print("toplayici: %s | %s lig | %ss | hata: %s" % (
    "calisiyor" if c.get("running") else "DURDU",
    c.get("leagues", "?"), c.get("poll_seconds", "?"),
    c.get("last_error") or "yok"))
print("arsiv: %s mac | %s snapshot | %s tick" % (
    b.get("matches", "?"), b.get("snapshots", "?"), b.get("ticks", "?")))
' 2>/dev/null
}

# --- systemd (istege bagli) --------------------------------------------
# Kullanici servisi: root gerekmez. linger acilir, boylece oturum
# kapansa da toplayici calismaya devam eder - projenin tum degeri
# pencereyi kacirmamakta oldugu icin bu onemli.
install_systemd() {
  local root unit_dir
  root="$(pwd)"
  unit_dir="$HOME/.config/systemd/user"
  have systemctl || { warn "systemctl yok - systemd atlandi"; return 1; }
  mkdir -p "$unit_dir"

  if proxy_wanted; then
    cat > "$unit_dir/betodds-proxy.service" <<UNIT
[Unit]
Description=BetOdds DPI bypass proxy (ciadpi)
Before=betodds.service

[Service]
Type=simple
WorkingDirectory=$root
ExecStart=$root/tools/byedpi-linux/ciadpi -i 127.0.0.1 -p $BETODDS_PROXY_PORT -r 1+s
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
UNIT
  fi

  cat > "$unit_dir/betodds.service" <<UNIT
[Unit]
Description=BetOdds toplayici + API
After=network-online.target betodds-proxy.service
Wants=betodds-proxy.service

[Service]
Type=simple
WorkingDirectory=$root
Environment=BETODDS_PORT=$BETODDS_PORT
ExecStart=$root/backend/run.sh
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
UNIT

  systemctl --user daemon-reload
  # Oturum kapandiginda servisin durmamasi icin linger sart.
  loginctl enable-linger "$USER" >/dev/null 2>&1 \
    || warn "linger acilamadi - oturum kapaninca servis durabilir"
  proxy_wanted && systemctl --user enable --now betodds-proxy.service
  systemctl --user enable --now betodds.service
  say "  systemctl --user status betodds"
}

# Backend acilmadiginda son loglari gosterir. Log dosyasi HIC olusmamis
# olabilir (surec baslatilamadiysa) - tail'in ham hatasini basmayalim.
show_backend_log() {
  if [ -s "$LOG_DIR/backend.log" ]; then
    tail -25 "$LOG_DIR/backend.log" >&2
  else
    say "  ($LOG_DIR/backend.log yok - backend hic baslatilamadi)" >&2
  fi
}
