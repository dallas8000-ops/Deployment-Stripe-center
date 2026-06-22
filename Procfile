# Process types for Railway / Heroku-style orchestration.
# Web runs migrations; worker and beat assume schema is current.
web: sh -c 'cd backend && python manage.py migrate --noinput && daphne -b 0.0.0.0 -p ${PORT:-8080} config.asgi:application'
worker: sh -c 'cd backend && celery -A config worker -l info'
beat: sh -c 'cd backend && celery -A config beat -l info'
transfer-worker: sh -c 'cd backend && python manage.py transfer_worker'
