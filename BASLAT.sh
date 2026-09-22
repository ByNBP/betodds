#!/usr/bin/env bash
# Kurulumdan sonra yigini baslatir: proxy (gerekiyorsa) + backend.
set -uo pipefail
cd "$(dirname "$0")"
. scripts/lib-linux.sh

[ -x backend/.venv/bin/uvicorn ] || die "kurulum yapilmamis - once ./KURULUM.sh"

say "=== BetOdds baslatiliyor ==="
if proxy_wanted; then
  proxy_start || warn "proxy baslatilamadi - toplayici veri cekemeyebilir"
fi
backend_start

if wait_health 40; then
  say ""
  say "-> http://localhost:$BETODDS_PORT"
  health_summary backend/.venv/bin/python | sed 's/^/   /'
else
  warn "backend saglik vermedi. Son loglar:"
  show_backend_log
  exit 1
fi
