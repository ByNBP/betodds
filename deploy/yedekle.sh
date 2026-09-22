#!/bin/sh
# Veritabaninin tutarli kopyasini alir (VACUUM INTO - canli WAL dosyasini
# dogrudan kopyalamak bozuk dosya verir), sikistirir, son 14 yedegi tutar.
# cron: 0 4 * * * /opt/betodds/deploy/yedekle.sh >> /var/log/betodds-yedek.log 2>&1
set -eu
cd "$(dirname "$0")/.."
mkdir -p data/yedek
AD="betodds-$(date +%Y%m%d-%H%M%S).db"
docker exec betodds python -c "import sqlite3; sqlite3.connect('/app/data/betodds.db').execute(\"VACUUM INTO '/app/data/yedek/$AD'\")"
gzip "data/yedek/$AD"
ls -1t data/yedek/betodds-*.db.gz | tail -n +15 | xargs -r rm --
echo "$(date '+%F %T') tamam: data/yedek/$AD.gz"
