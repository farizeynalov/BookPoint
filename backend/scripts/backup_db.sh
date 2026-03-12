#!/usr/bin/env sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

TIMESTAMP="$(date +"%Y%m%d_%H%M%S")"
OUTPUT_PATH="${1:-backups/bookpoint_${TIMESTAMP}.sql}"
DB_USER="${POSTGRES_USER:-bookpoint}"
DB_NAME="${POSTGRES_DB:-bookpoint}"

mkdir -p "$(dirname "$OUTPUT_PATH")"
echo "[backup] creating database backup at $OUTPUT_PATH"

docker compose exec -T db pg_dump -U "$DB_USER" -d "$DB_NAME" > "$OUTPUT_PATH"
echo "[backup] backup completed: $OUTPUT_PATH"
