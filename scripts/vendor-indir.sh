#!/usr/bin/env bash
# Cevrimdisi Windows paketi icin gereken ucuncu taraf ikilileri indirir.
#
# Bunlar depoda TUTULMUYOR (~49 MB, hepsi yeniden indirilebilir). Yalnizca
# `scripts/package.sh --with-images` calistiracaksaniz gerekli; gelistirme
# ve Linux'ta calistirma icin gerekmez.
#
# vendor/byedpi (kaynak) ve vendor/byedpi-win (Windows ikilisi) depoda
# GOMULU kalir: bunlarin kaynagi GitHub ve bu projenin hedef aglarinda
# GitHub'a erisilemiyor - vendorlamanin sebebi zaten bu.
set -euo pipefail
cd "$(dirname "$0")/.."

PY_VER=3.12.8
NODE_VER=20.18.1

get() {  # $1=hedef dosya  $2=url
  if [ -f "$1" ]; then echo "  var: $1"; return; fi
  echo "  indiriliyor: $(basename "$1")"
  mkdir -p "$(dirname "$1")"
  curl -fsSL -o "$1.tmp" "$2" && mv "$1.tmp" "$1"
}

echo "Windows paketi icin ikililer indiriliyor..."
get "vendor/python/python-$PY_VER-embed-amd64.zip" \
    "https://www.python.org/ftp/python/$PY_VER/python-$PY_VER-embed-amd64.zip"
get "vendor/python/get-pip.py" "https://bootstrap.pypa.io/get-pip.py"
get "vendor/node/node-v$NODE_VER-win-x64.zip" \
    "https://nodejs.org/dist/v$NODE_VER/node-v$NODE_VER-win-x64.zip"

echo "  wheel'ler (cp312 / win_amd64)..."
mkdir -p vendor/wheels
PIP=backend/.venv/bin/pip
[ -x "$PIP" ] || PIP="$(command -v pip3 || command -v pip)"
# --no-deps SART: liste zaten COZULMUS (uvloop cikarilmis, colorama eklenmis).
# Bagimlilik cozumunu pip'e birakirsak Linux isaretlerine gore uvloop ister
# ve Windows wheel'i olmadigi icin patlar.
"$PIP" download --only-binary=:all: --platform win_amd64 \
  --python-version 3.12 --implementation cp --abi cp312 --no-deps \
  -r vendor/requirements-win.txt -d vendor/wheels --quiet
"$PIP" download --only-binary=:all: --platform win_amd64 \
  --python-version 3.12 --implementation cp --abi cp312 --no-deps \
  pip setuptools wheel -d vendor/wheels --quiet

echo
echo "-> hazir:"
du -sh vendor/python vendor/node vendor/wheels
echo "   wheel sayisi: $(ls vendor/wheels | wc -l)"
