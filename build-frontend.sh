#!/usr/bin/env bash
# Frontend'i container icinde derler; cikti frontend/dist -> backend tarafindan servis edilir.
set -euo pipefail
cd "$(dirname "$0")"
IMG=docker.io/library/node:20-alpine
RUN=(docker run --rm --userns=keep-id -v "$PWD/frontend:/app:z" -w /app "$IMG")
[ -d frontend/node_modules ] || "${RUN[@]}" npm install --no-audit --no-fund
"${RUN[@]}" npm run build
echo "-> frontend/dist hazir; backend'i yeniden baslatmak yeterli."
