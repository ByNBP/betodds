#!/usr/bin/env bash
# Yiginin durumunu ozetler.
set -uo pipefail
cd "$(dirname "$0")"
. scripts/lib-linux.sh

say "=== BetOdds durum ==="
printf '  proxy   : '
if proxy_running; then say "calisiyor (127.0.0.1:$BETODDS_PROXY_PORT)"
elif proxy_wanted;  then say "DURDU - backend/env istiyor! ./scripts/proxy-baslat.sh"
else say "gerekmiyor"; fi

printf '  backend : '
if health_json >/dev/null; then
  say "calisiyor (http://localhost:$BETODDS_PORT)"
  health_summary backend/.venv/bin/python | sed 's/^/  /'
else
  say "DURDU"
  [ -f logs/backend.log ] && { say ""; say "  son loglar:"; tail -10 logs/backend.log | sed 's/^/    /'; }
  exit 1
fi
