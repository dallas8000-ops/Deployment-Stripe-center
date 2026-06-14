#!/bin/sh
set -e
cd /app/backend

echo "Starting Stripe Installer (PORT=${PORT:-8000})..."
python manage.py migrate --noinput

if [ "${LICENSE_ENFORCEMENT_ENABLED}" = "true" ]; then
  echo "Validating license..."
  python manage.py validate_license_startup
fi

echo "Launching Daphne on 0.0.0.0:${PORT:-8000}"
exec daphne -b 0.0.0.0 -p "${PORT:-8000}" config.asgi:application
