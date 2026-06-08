#!/bin/sh
set -e
cd /app/backend
python manage.py migrate --noinput
exec "$@"
