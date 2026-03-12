#!/usr/bin/env sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

if [ "$#" -lt 1 ]; then
  echo "usage: scripts/restore_db.sh <backup_file.sql>"
  exit 1
fi

INPUT_PATH="$1"
DB_USER="${POSTGRES_USER:-bookpoint}"
DB_NAME="${POSTGRES_DB:-bookpoint}"

if [ ! -f "$INPUT_PATH" ]; then
  echo "[restore] backup file not found: $INPUT_PATH"
  exit 1
fi

echo "[restore] restoring $INPUT_PATH into database $DB_NAME"
docker compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" < "$INPUT_PATH"
echo "[restore] restore completed"
