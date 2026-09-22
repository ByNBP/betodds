#!/usr/bin/env bash
# Backend'i ve proxy'yi durdurur.
set -uo pipefail
cd "$(dirname "$0")"
. scripts/lib-linux.sh

say "=== BetOdds durduruluyor ==="
stop_pidfile "$BACKEND_PIDF" "backend"
stop_pidfile "$PROXY_PIDF" "proxy"

# uvicorn'u nohup ile baslatirken kaydettigimiz pid kabuk surecine ait;
# pidfile kaybolduysa (elle silme, yeniden acilan oturum) port hala dolu
# olabilir - bunu sessizce gecmeyelim.
if port_busy "$BETODDS_PORT"; then
  warn "$BETODDS_PORT hala dolu. Baska bir surec tutuyor olabilir:"
  ss -ltnp 2>/dev/null | grep ":$BETODDS_PORT " >&2 || true
fi
