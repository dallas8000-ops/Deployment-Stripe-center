#!/bin/sh
set -e
cd /app/backend

echo "Starting Stripe Installer (PORT=${PORT:-8080})..."
python manage.py migrate --noinput

if [ "${LICENSE_ENFORCEMENT_ENABLED}" = "true" ]; then
  echo "Validating license..."
  python manage.py validate_license_startup
fi

echo "Launching Daphne on 0.0.0.0:${PORT:-8080}"
exec daphne -b 0.0.0.0 -p "${PORT:-8080}" config.asgi:application
