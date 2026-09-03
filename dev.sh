#!/usr/bin/env bash
# Gelistirme modu: backend (8000) + Vite dev sunucusu (5173, container icinde).
# Frontend degisiklikleri aninda yansir; /api istekleri backend'e proxy'lenir.
set -euo pipefail
cd "$(dirname "$0")"

./backend/run.sh --reload &
BACKEND_PID=$!
trap 'kill $BACKEND_PID 2>/dev/null || true' EXIT

exec docker run --rm -it --userns=keep-id --network=host \
  -v "$PWD/frontend:/app:z" -w /app \
  docker.io/library/node:20-alpine npm run dev
