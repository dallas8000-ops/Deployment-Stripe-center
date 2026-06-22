# Railway multi-service split (Phase 1)

Run **three services** from this repo (same Dockerfile). This removes the single-instance ceiling: web and Celery workers scale to **N**; beat runs at **exactly 1** replica.

## Prerequisites

1. **PostgreSQL** plugin (shared `DATABASE_URL` on all services).
2. **Redis** plugin (shared `REDIS_URL` on all services).
3. Remove dev-only vars from Railway: `CELERY_EAGER=true`, `CHANNEL_LAYER_INMEMORY=true`, `REDIS_URL=redis://127.0.0.1:...`.
4. Do **not** set `ALLOW_SINGLE_CONTAINER=true` unless you intentionally stay on one box.

## Services

| Service | `PROCESS_TYPE` | Replicas | Health check | Notes |
|---------|----------------|----------|--------------|-------|
| **web** | `web` | 2+ | `GET /health/` | Public domain + TLS here. Runs migrations on start. |
| **worker** | `worker` | 2+ | none | `celery -A config worker` |
| **beat** | `beat` | **1** | none | `celery -A config beat` — never scale above 1 |

Optional fourth service for API Transfer queue processing:

| Service | `PROCESS_TYPE` | Replicas |
|---------|----------------|----------|
| **transfer-worker** | `transfer-worker` | 1+ |

## Railway setup

1. Create **three** services linked to this GitHub repo (same branch).
2. On each service, set **Variables** (shared): `VAULT_MASTER_KEY`, `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=false`, `DATABASE_URL`, `REDIS_URL`, Stripe/GitHub vars, etc.
3. Per-service overrides:

   **web**
   ```
   PROCESS_TYPE=web
   ```

   **worker**
   ```
   PROCESS_TYPE=worker
   CELERY_EAGER=false
   CHANNEL_LAYER_INMEMORY=false
   ```

   **beat**
   ```
   PROCESS_TYPE=beat
   CELERY_EAGER=false
   ```

4. Attach the **custom domain** only to the **web** service.
5. Deploy all three. Confirm:
   - `curl https://<domain>/health/` → `"redis":"ok"`
   - `curl https://<domain>/health/ready/` → `"status":"ready"`
   - Worker logs show `celery@` ready; beat logs show scheduler tick.

## Docker Compose (local prod profile)

```bash
npm run docker:prod
```

Starts `postgres`, `redis`, `web`, `celery`, `celery-beat` with `PROCESS_TYPE` via `scripts/docker-entrypoint.sh`.

## Procfile (Heroku-style)

See repo root `Procfile` for equivalent process types.

## Beat safety

Scheduled `*_all_projects` Celery tasks use a **Redis distributed lock** (`apps/core/distributed_lock.py`) so a misconfigured second beat replica cannot double-fire catalog jobs.

## Legacy single-container

If you must run one Railway service without Redis, set `ALLOW_SINGLE_CONTAINER=true`. This enables in-memory Channels + eager Celery (not horizontally scalable). Migrate to the three-service split for Tier-1.
