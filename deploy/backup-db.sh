#!/usr/bin/env bash
# Codzienna kopia bazy Prawdowida (baza jest tylko na tym serwerze).
#
# Postgres w Dockerze: ustaw PG_CONTAINER (nazwa z `docker ps`), PG_USER i DB_NAME.
# Cron roota (`sudo crontab -e`):
#   15 3 * * * PG_CONTAINER=postgres /opt/prawdowid/deploy/backup-db.sh
# Postgres bez Dockera: cron użytkownika postgres, bez PG_CONTAINER.
#
# Przywrócenie (Docker):
#   docker exec -i <kontener> pg_restore --clean --no-owner -U prawdowid -d prawdowid < plik.dump
set -euo pipefail

DB_NAME="${DB_NAME:-prawdowid}"
PG_USER="${PG_USER:-prawdowid}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/prawdowid}"
KEEP_DAYS="${KEEP_DAYS:-14}"

mkdir -p "$BACKUP_DIR"
target="$BACKUP_DIR/${DB_NAME}-$(date +%F).dump"
if [ -n "${PG_CONTAINER:-}" ]; then
  docker exec "$PG_CONTAINER" pg_dump -Fc -U "$PG_USER" "$DB_NAME" > "$target.tmp"
else
  pg_dump -Fc "$DB_NAME" > "$target.tmp"
fi
mv "$target.tmp" "$target"
find "$BACKUP_DIR" -name "${DB_NAME}-*.dump" -mtime +"$KEEP_DAYS" -delete
