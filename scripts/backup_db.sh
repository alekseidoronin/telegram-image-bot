#!/usr/bin/env bash

set -euo pipefail

# Root of the project (this script lives in scripts/)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_PATH="$PROJECT_ROOT/bot_database.db"

# Where to store backups (can be overridden через переменную окружения DB_BACKUP_DIR)
BACKUP_DIR="${DB_BACKUP_DIR:-$PROJECT_ROOT/db_backups}"

mkdir -p "$BACKUP_DIR"

if [ ! -f "$DB_PATH" ]; then
  echo "Database file not found: $DB_PATH" >&2
  exit 1
fi

TIMESTAMP="$(date +'%Y-%m-%d_%H-%M')"
BACKUP_FILE="$BACKUP_DIR/bot_database_$TIMESTAMP.db"

cp "$DB_PATH" "$BACKUP_FILE"
echo "Backup created: $BACKUP_FILE"

# Опционально: чистим бэкапы старше 7 дней
find "$BACKUP_DIR" -type f -name 'bot_database_*.db' -mtime +7 -print -delete || true

