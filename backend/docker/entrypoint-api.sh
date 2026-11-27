#!/bin/sh
# Entrypoint API (Story 9.1) : PostgreSQL -> migrations Alembic -> uvicorn.
# Le schéma est exclusivement géré par Alembic (D-05/D-07).
set -eu

log_json() {
    level="$1"
    message="$2"
    printf '{"timestamp":"%s","level":"%s","logger":"entrypoint-api","message":"%s"}\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$level" "$message"
}

: "${POSTGRES_USER:?POSTGRES_USER doit être défini dans backend/.env}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD doit être défini dans backend/.env}"
: "${POSTGRES_DB:?POSTGRES_DB doit être défini dans backend/.env}"

PG_HOST="${POSTGRES_HOST:-postgres}"
PG_PORT="${POSTGRES_PORT:-5432}"
PG_TIMEOUT="${PG_READY_TIMEOUT_SECONDS:-60}"

case "$PG_TIMEOUT" in
    ''|*[!0-9]*)
        log_json ERROR "PG_READY_TIMEOUT_SECONDS doit être un entier positif (reçu : ${PG_TIMEOUT})"
        exit 1
        ;;
esac

elapsed=0
log_json INFO "Attente de PostgreSQL sur ${PG_HOST}:${PG_PORT}"
until pg_isready -h "$PG_HOST" -p "$PG_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q; do
    if [ "$elapsed" -ge "$PG_TIMEOUT" ]; then
        log_json ERROR "Timeout : PostgreSQL n'est pas prêt après ${PG_TIMEOUT}s"
        exit 1
    fi
    log_json INFO "PostgreSQL indisponible (${elapsed}s/${PG_TIMEOUT}s), nouvelle tentative dans 2s"
    sleep 2
    elapsed=$((elapsed + 2))
done
log_json INFO "PostgreSQL prêt"

log_json INFO "Application des migrations Alembic (upgrade head)"
if ! alembic upgrade head; then
    log_json ERROR "Échec d'alembic upgrade head : l'API ne démarrera pas"
    exit 1
fi
log_json INFO "Migrations Alembic terminées"

log_json INFO "Démarrage de l'API HTTP sur 0.0.0.0:8000"
exec uvicorn iryx.main:app --host 0.0.0.0 --port 8000
