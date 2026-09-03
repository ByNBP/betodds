#!/usr/bin/env bash
# Uretim benzeri calistirma: tek port (8000), frontend build'i backend servis eder.
set -euo pipefail
cd "$(dirname "$0")"
[ -d frontend/dist ] || ./build-frontend.sh
exec ./backend/run.sh
