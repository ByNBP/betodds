#!/usr/bin/env bash
# Backend'i gelistirme modunda calistirir.
cd "$(dirname "$0")"
# Cagiranin verdigi port env dosyasindakini ezsin: `. ./env` normalde
# devraldigimiz degeri ustune yaziyor ve BASLAT.sh baska bir portu
# beklerken sunucu baskasini dinliyordu.
_CALLER_PORT="${BETODDS_PORT:-}"
# env dosyasi varsa yukle (proxy / DNS override ayarlari)
[ -f env ] && set -a && . ./env && set +a
BETODDS_PORT="${_CALLER_PORT:-${BETODDS_PORT:-8000}}"

exec ./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "${BETODDS_PORT:-8000}" "$@"
