#!/usr/bin/env bash
# Linux icin kullanima hazir paket uretir (tar.gz).
#
# Hedef makinede gereken TEK sey: python3.10+ ve tar. Ag gerekmez -
# bagimlilik wheel'leri, derlenmis arayuz ve veritabani paketin icinde.
#
#   ./scripts/paket-linux.sh                  -> ~/betodds-linux-<tarih>.tar.gz
#   ./scripts/paket-linux.sh --no-db          -> veritabanini disarida birak
#   ./scripts/paket-linux.sh --with-images    -> docker imaj tar'larini da koy
#   ./scripts/paket-linux.sh /yol/paket.tar.gz
set -euo pipefail
cd "$(dirname "$0")/.."

WITH_IMAGES=0
WITH_DB=1
ARGS=()
for a in "$@"; do
  case "$a" in
    --with-images) WITH_IMAGES=1 ;;
    --no-db)       WITH_DB=0 ;;
    *) ARGS+=("$a") ;;
  esac
done
OUT="${ARGS[0]:-$HOME/betodds-linux-$(date +%Y%m%d-%H%M).tar.gz}"
ARCH="$(uname -m)"

say() { printf '%s\n' "$*"; }

# --- on kosullar -------------------------------------------------------
# Bunlar eksikken paket URETILEBILIR ama hedefte ise yaramaz; burada,
# paketlemeden ONCE soyleyelim.
[ -f frontend/dist/index.html ] \
  || { say "HATA: frontend/dist yok - once ./build-frontend.sh" >&2; exit 1; }

WHEELS="vendor/wheels-linux/$ARCH"
if ! compgen -G "$WHEELS/*.whl" >/dev/null; then
  say "HATA: $WHEELS bos - once ./scripts/vendor-indir-linux.sh" >&2
  exit 1
fi

# Hazir ciadpi: hedefte derleyici yoksa yedek. Derlemeyi yine de once
# deniyor (bkz. proxy-baslat.sh) cunku yerel derleme glibc uyumu icin
# daha guvenli - bu ikili yalnizca fallback.
PREBUILT_DIR="vendor/byedpi-linux-$ARCH"
if [ ! -x "$PREBUILT_DIR/ciadpi" ]; then
  say "  hazir ciadpi uretiliyor ($PREBUILT_DIR)..."
  ./scripts/proxy-baslat.sh >/dev/null 2>&1 || true
  mkdir -p "$PREBUILT_DIR"
  if [ -x tools/byedpi-linux/ciadpi ]; then
    cp tools/byedpi-linux/ciadpi "$PREBUILT_DIR/"
  else
    say "  UYARI: ciadpi derlenemedi - pakette hazir ikili olmayacak" >&2
  fi
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
STAGE="$TMP/betodds"
mkdir -p "$STAGE/data" "$STAGE/logs"

# --- kaynak ------------------------------------------------------------
# backend/env DAHIL: calisan site aynasi, DNS override ve proxy ayari
# hedef makinede de gecerli.
# vendor/ SECMELI kopyalaniyor: Windows ikilileri (python, node, wheels,
# byedpi-win, ~49 MB) Linux paketinde tamamen olu agirlik.
for p in KURULUM.sh BASLAT.sh DURDUR.sh DURUM.sh \
         start.sh dev.sh build-frontend.sh \
         backend/app backend/requirements.txt backend/run.sh backend/env \
         backend/env.example backend/import_local.py backend/merge_db.py \
         frontend/src frontend/index.html frontend/package.json \
         frontend/package-lock.json frontend/vite.config.js \
         frontend/scripts frontend/dist \
         docker Dockerfile docker-compose.yml .env .dockerignore \
         README.md LINUX-README.md; do
  [ -e "$p" ] || continue
  mkdir -p "$STAGE/$(dirname "$p")"
  cp -r "$p" "$STAGE/$(dirname "$p")/"
done

# scripts/ : Windows'a ozel .ps1'ler paketin disinda kalir.
mkdir -p "$STAGE/scripts"
for s in scripts/*.sh; do cp "$s" "$STAGE/scripts/"; done

# vendor/ : yalnizca Linux'ta ise yarayanlar
mkdir -p "$STAGE/vendor"
cp -r vendor/byedpi "$STAGE/vendor/"
cp vendor/README.md "$STAGE/vendor/" 2>/dev/null || true
rm -f "$STAGE"/vendor/byedpi/*.o "$STAGE"/vendor/byedpi/ciadpi
[ -x "$PREBUILT_DIR/ciadpi" ] && cp -r "$PREBUILT_DIR" "$STAGE/vendor/"
mkdir -p "$STAGE/$WHEELS" && cp "$WHEELS"/*.whl "$STAGE/$WHEELS/"

# Bu makinenin python surumune ait .pyc'ler tasinmasin.
find "$STAGE" -name '__pycache__' -type d -prune -exec rm -rf {} +

# --- veritabani --------------------------------------------------------
# Canli WAL'i dogrudan kopyalamak BOZUK dosya verir; VACUUM INTO tutarli
# ve sikistirilmis tek dosya uretir.
if [ "$WITH_DB" = 1 ] && [ -f data/betodds.db ]; then
  STAGE="$STAGE" python3 - <<'PY'
import os, sqlite3
dst = os.environ["STAGE"] + "/data/betodds.db"
con = sqlite3.connect("file:data/betodds.db?mode=ro", uri=True)
con.execute("VACUUM INTO ?", (dst,))
con.close()
n = sqlite3.connect(dst)
tables = {r[0] for r in n.execute("SELECT name FROM sqlite_master WHERE type='table'")}
print("  veritabani: %.0f KB" % (os.path.getsize(dst) / 1024))
for t in ("matches", "odds_snapshots", "odds_values", "odds_ticks", "season_tables"):
    if t in tables:
        print("    %-16s %s" % (t, n.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]))
n.close()
PY
else
  say "  veritabani pakete DAHIL EDILMEDI (bos baslanacak)"
fi
[ -f data/leagues.json ] && cp data/leagues.json "$STAGE/data/"

# --- docker imajlari (istege bagli) ------------------------------------
if [ "$WITH_IMAGES" = 1 ]; then
  mkdir -p "$STAGE/images"
  for img in betodds betodds-proxy; do
    if [ -f "images/$img.tar" ]; then
      cp "images/$img.tar" "$STAGE/images/"
      say "  images/$img.tar  $(( $(stat -c%s "images/$img.tar") / 1048576 )) MB"
    else
      say "  UYARI: images/$img.tar yok - uretmek icin:" >&2
      say "    docker build --no-cache -t $img:latest ." >&2
      say "    docker save $img:latest -o images/$img.tar" >&2
    fi
  done
fi

chmod +x "$STAGE"/*.sh "$STAGE"/scripts/*.sh "$STAGE"/backend/run.sh 2>/dev/null || true

mkdir -p "$(dirname "$OUT")"
tar -czf "$OUT" -C "$TMP" betodds

say ""
say "-> $OUT  ($(du -h "$OUT" | cut -f1))"
say ""
say "   Hedef makinede:"
say "     tar xzf $(basename "$OUT")"
say "     cd betodds"
say "     ./KURULUM.sh"
say ""
say "   Gereken: python3.10+ (venv modulu ile). Ag GEREKMEZ."
