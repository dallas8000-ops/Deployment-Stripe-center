#!/bin/sh
set -e
cd /app/backend

PROCESS_TYPE="${PROCESS_TYPE:-web}"

run_migrate() {
  python manage.py migrate --noinput
}

validate_license_if_needed() {
  if [ "${LICENSE_ENFORCEMENT_ENABLED}" = "true" ]; then
    echo "Validating license..."
    python manage.py validate_license_startup
  fi
}

case "$PROCESS_TYPE" in
  web)
    echo "Starting web (Daphne) — PORT=${PORT:-8080}"
    run_migrate
    validate_license_if_needed
    exec daphne -b 0.0.0.0 -p "${PORT:-8080}" config.asgi:application
    ;;
  worker)
    echo "Starting Celery worker (scale to N replicas)"
    exec celery -A config worker -l info
    ;;
  beat)
    echo "Starting Celery beat — run exactly ONE replica"
    exec celery -A config beat -l info
    ;;
  transfer-worker)
    echo "Starting API transfer worker (scale to N replicas)"
    exec python manage.py transfer_worker
    ;;
  *)
    echo "Unknown PROCESS_TYPE=${PROCESS_TYPE} (expected web|worker|beat|transfer-worker)"
    exit 1
    ;;
esac
