#!/usr/bin/env bash
# Codzienna kopia bazy Prawdowida (baza jest tylko na tym serwerze).
#
# Cron użytkownika postgres (`sudo crontab -u postgres -e`):
#   15 3 * * * /opt/prawdowid/deploy/backup-db.sh
#
# Przywrócenie: pg_restore --clean --no-owner -d prawdowid <plik.dump>
set -euo pipefail

DB_NAME="${DB_NAME:-prawdowid}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/prawdowid}"
KEEP_DAYS="${KEEP_DAYS:-14}"

mkdir -p "$BACKUP_DIR"
target="$BACKUP_DIR/${DB_NAME}-$(date +%F).dump"
pg_dump -Fc "$DB_NAME" > "$target.tmp"
mv "$target.tmp" "$target"
find "$BACKUP_DIR" -name "${DB_NAME}-*.dump" -mtime +"$KEEP_DAYS" -delete
