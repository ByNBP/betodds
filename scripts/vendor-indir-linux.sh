#!/usr/bin/env bash
# Cevrimdisi LINUX paketi icin wheel'leri indirir -> vendor/wheels-linux/<arch>/
#
# Neden birden fazla surum: pydantic_core, uvloop, httptools, watchfiles,
# websockets ve PyYAML ikili wheel ve cp surumune OZEL. Hedef makinenin
# python'u 3.10 mu 3.13 mu bilmiyoruz (Ubuntu 22.04 -> 3.10,
# 24.04 -> 3.12, Fedora 41 -> 3.13), o yuzden hepsini tasiyoruz.
# Saf python wheel'leri (fastapi, httpx, starlette...) tek kopya yeter.
#
# Bunlar depoda TUTULMUYOR (~33 MB, yeniden indirilebilir) - bkz .gitignore.
set -euo pipefail
cd "$(dirname "$0")/.."

ARCH="$(uname -m)"
OUT="vendor/wheels-linux/$ARCH"
VERSIONS="${BETODDS_PY_VERSIONS:-3.10 3.11 3.12 3.13}"

PIP=backend/.venv/bin/pip
[ -x "$PIP" ] || PIP="$(command -v pip3 || command -v pip)" \
  || { echo "HATA: pip bulunamadi" >&2; exit 1; }

case "$ARCH" in
  x86_64)  PLAT=(--platform manylinux2014_x86_64  --platform manylinux_2_17_x86_64) ;;
  aarch64) PLAT=(--platform manylinux2014_aarch64 --platform manylinux_2_17_aarch64) ;;
  *) echo "HATA: bilinmeyen mimari $ARCH" >&2; exit 1 ;;
esac

mkdir -p "$OUT"
echo "Linux wheel'leri indiriliyor -> $OUT"
for v in $VERSIONS; do
  tag="cp${v/./}"
  echo "  python $v ($tag)..."
  # --platform any: saf python wheel'leri de ayni cagriya dahil olsun.
  "$PIP" download --only-binary=:all: "${PLAT[@]}" --platform any \
    --python-version "$v" --implementation cp --abi "$tag" \
    -r backend/requirements.txt -d "$OUT" --quiet \
    || { echo "  UYARI: $v icin bazi wheel'ler alinamadi" >&2; }
done

# pip'in KENDISI: Debian/Ubuntu'da python3-venv kurulu degilse olusan venv
# pip'siz kaliyor (ensurepip yok). Bu wheel'i tasiyarak KURULUM.sh pip'i
# wheel'in icinden bootstrap edebiliyor - python3-venv paketi gerekmiyor.
"$PIP" download --only-binary=:all: --no-deps pip -d "$OUT" --quiet \
  || echo "  UYARI: pip wheel'i alinamadi" >&2

echo
echo "-> $(ls "$OUT"/*.whl 2>/dev/null | wc -l) wheel, $(du -sh "$OUT" | cut -f1)"
echo "   surume ozel ikili paketler:"
ls "$OUT" | grep -v 'py3-none-any\|py2.py3' | sed 's/-manylinux.*//' | sort -u | sed 's/^/     /'
