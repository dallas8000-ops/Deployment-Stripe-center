#!/bin/sh
set -e
cd /app/backend
python manage.py migrate --noinput

if [ "${LICENSE_ENFORCEMENT_ENABLED}" = "true" ]; then
  echo "Validating license..."
  python manage.py validate_license_startup
fi

exec "$@"
