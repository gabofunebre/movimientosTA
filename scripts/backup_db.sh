#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  echo "❌ Error: no existe .env en $ROOT_DIR"
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

: "${POSTGRES_USER:?❌ POSTGRES_USER no está definido en .env}"
: "${POSTGRES_DB:?❌ POSTGRES_DB no está definido en .env}"

DOCKER_COMPOSE=${DOCKER_COMPOSE:-"docker compose"}
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
TS="$(date +%Y%m%d_%H%M%S)"
DUMP_PATH="${1:-$BACKUP_DIR/${POSTGRES_DB}_${TS}.dump}"

mkdir -p "$BACKUP_DIR"

APP_SERVICE="${APP_SERVICE:-app}"
DB_SERVICE="${DB_SERVICE:-db}"

app_was_running=0
if $DOCKER_COMPOSE ps --status running --services 2>/dev/null | grep -qx "$APP_SERVICE"; then
  app_was_running=1
fi

cleanup() {
  if [[ "$app_was_running" -eq 1 ]]; then
    echo "▶ Reiniciando app ($APP_SERVICE)..."
    $DOCKER_COMPOSE start "$APP_SERVICE" >/dev/null
    echo "✅ App iniciada nuevamente"
  fi
}
trap cleanup EXIT

echo "▶ Validando servicio de base de datos..."
$DOCKER_COMPOSE up -d "$DB_SERVICE" >/dev/null

if [[ "$app_was_running" -eq 1 ]]; then
  echo "▶ Deteniendo app temporalmente para snapshot consistente..."
  $DOCKER_COMPOSE stop "$APP_SERVICE" >/dev/null
fi

echo "▶ Generando dump en formato custom (-Fc): $DUMP_PATH"
$DOCKER_COMPOSE exec -T "$DB_SERVICE" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > "$DUMP_PATH"

echo "✅ Backup completado: $DUMP_PATH"
