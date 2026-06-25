# syntax=docker/dockerfile:1
# Railway production image — Stripe Installer
# manage.py: backend/manage.py (WORKDIR /app/backend)
# ASGI: config.asgi:application (Daphne — Channels/WebSockets)
# Startup: /entrypoint.sh — collectstatic → migrate → Daphne (web only)
# Port: ${PORT:-8080}
# Railway service Root Directory must be repo root (empty), not backend/.

FROM node:20-alpine AS frontend
WORKDIR /app/frontend
# Railway injects NODE_ENV=production during builds — devDeps (typescript, vite) are required.
ENV NODE_ENV=development \
    NPM_CONFIG_PRODUCTION=false
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

COPY scripts/docker-entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

ENV PROCESS_TYPE=web

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
