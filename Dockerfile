# syntax=docker/dockerfile:1
# Railway production image — Stripe Installer
# manage.py: backend/manage.py (WORKDIR /app/backend)
# ASGI: config.asgi:application (Daphne — Channels/WebSockets)
# WSGI: config.wsgi:application (available; production uses Daphne)
# Port: ${PORT:-8080}

FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS backend
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

COPY backend/ ./
COPY --from=frontend /app/frontend/dist /app/frontend/dist

RUN DJANGO_SECRET_KEY=build-placeholder-not-used-at-runtime \
    DJANGO_DEBUG=False \
    python manage.py collectstatic --noinput

COPY scripts/docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
