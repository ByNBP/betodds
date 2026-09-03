#!/usr/bin/env bash
# Backend'i gelistirme modunda calistirir.
cd "$(dirname "$0")"
# env dosyasi varsa yukle (proxy / DNS override ayarlari)
[ -f env ] && set -a && . ./env && set +a

exec ./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 "$@"
