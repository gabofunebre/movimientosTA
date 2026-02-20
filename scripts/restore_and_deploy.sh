#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ $# -lt 1 ]]; then
  echo "Uso: $0 <ruta_dump> [ref_git]"
  exit 1
fi

DUMP_PATH="$1"
REF_GIT="${2:-main}"

if [[ ! -f "$DUMP_PATH" ]]; then
  echo "❌ Error: dump no encontrado en '$DUMP_PATH'"
  exit 1
fi

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
DB_SERVICE="${DB_SERVICE:-db}"
APP_SERVICE="${APP_SERVICE:-app}"
HEALTH_URL="${HEALTH_URL:-http://localhost:8000/health}"
RESTORE_ONLY="${RESTORE_ONLY:-0}"

if [[ "$RESTORE_ONLY" != "1" ]]; then
  echo "▶ Actualizando código fuente..."
  git fetch --all --prune
  git checkout "$REF_GIT"
  if [[ "$REF_GIT" == "main" ]]; then
    git pull --ff-only origin main
  fi
else
  echo "▶ Modo restore-only: se omite actualización de código"
fi

echo "▶ Levantando base de datos..."
$DOCKER_COMPOSE up -d "$DB_SERVICE" >/dev/null

echo "▶ Restaurando dump '$DUMP_PATH' en base '$POSTGRES_DB'..."
DB_CONTAINER_ID="$($DOCKER_COMPOSE ps -q "$DB_SERVICE")"
if [[ -z "$DB_CONTAINER_ID" ]]; then
  echo "❌ Error: no se pudo obtener el contenedor del servicio '$DB_SERVICE'"
  exit 1
fi

CONTAINER_DUMP_PATH="/tmp/restore_$(date +%s)_$(basename "$DUMP_PATH" | tr -cs '[:alnum:]._-' '_')"
cleanup_dump() {
  $DOCKER_COMPOSE exec -T "$DB_SERVICE" rm -f "$CONTAINER_DUMP_PATH" >/dev/null 2>&1 || true
}
trap cleanup_dump EXIT

echo "▶ Copiando dump al contenedor de base..."
docker cp "$DUMP_PATH" "${DB_CONTAINER_ID}:$CONTAINER_DUMP_PATH"

$DOCKER_COMPOSE exec -T "$DB_SERVICE" pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner "$CONTAINER_DUMP_PATH"

echo "▶ Levantando app..."
$DOCKER_COMPOSE up -d "$APP_SERVICE" >/dev/null

if [[ "$RESTORE_ONLY" != "1" ]]; then
  echo "▶ Ejecutando smoke test: $HEALTH_URL"
  curl -fsS "$HEALTH_URL" >/dev/null
  echo "✅ Restore + deploy completado correctamente"
else
  echo "✅ Restore completado correctamente (smoke omitido por RESTORE_ONLY=1)"
fi
