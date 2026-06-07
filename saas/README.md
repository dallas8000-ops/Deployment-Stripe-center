# Stripe Installer SaaS

Browser-based product: **Django + DRF + Channels + Celery + React**.

## Structure

```
saas/
├── backend/          Django API, pipeline engine, WebSocket consumer
├── frontend/         React + Vite SPA with live pipeline terminal
├── docker-compose.yml   Redis (optional Postgres commented out)
└── package.json      Convenience scripts for Windows dev
```

## Quick start (local dev)

```powershell
cd saas
npm run setup          # venv + pip + npm install + migrate

# Generate vault key and paste into backend/.env
python -c "import secrets; print(secrets.token_hex(32))"
copy backend\.env.example backend\.env
# Edit backend\.env — set VAULT_MASTER_KEY (CELERY_EAGER=true is pre-set for dev)

npm run dev:backend    # terminal 1 — Daphne on :8000
npm run dev:frontend   # terminal 2 — Vite on :5173
```

Open http://localhost:5173 — register, create a project, unlock vault, save Stripe keys.

**Dev mode** (`.env`): `CELERY_EAGER=true` + `CHANNEL_LAYER_INMEMORY=true` — no Redis or Celery worker required.

**Production mode**: `docker compose up -d redis`, set `CELERY_EAGER=false`, run `npm run dev:celery` + Daphne.

## Verify install

```powershell
cd saas\backend
.venv\Scripts\python.exe manage.py smoke_test
```

Checks vault encrypt → mask → verify → delete without real Stripe keys.

## Vault UX

- Write-only secrets — values never shown after save
- Masked display: `sk_live_••••••••••••`
- Green **Verified ✅** badge after live Stripe API check
- Delete requires confirmation modal

## Prerequisites

- Python 3.11+
- Node 20+
- Redis (production / WebSocket fan-out) — `npm run redis` or Docker

## Backend setup (manual)

```bash
cd saas/backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python -c "import secrets; print(secrets.token_hex(32))"   # → VAULT_MASTER_KEY
copy .env.example .env

python manage.py migrate
python manage.py createsuperuser
```

### Run (production-style — 4 terminals)

```bash
# 1 — Redis
docker compose up -d redis

# 2 — Celery worker
celery -A config worker -l info

# 3 — ASGI server (HTTP + WebSocket)
daphne -b 127.0.0.1 -p 8000 config.asgi:application

# 4 — Frontend
cd ../frontend && npm run dev
```

## Frontend

```bash
cd saas/frontend
npm install
npm run dev
```

Proxies `/api` and `/ws` to Django.

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/register/` | Create account |
| POST | `/api/v1/auth/login/` | JWT login |
| POST | `/api/v1/projects/{slug}/vault/init/` | Initialize encrypted vault |
| POST | `/api/v1/projects/{slug}/vault/keys/set/` | Store secret (write-only) |
| POST | `/api/v1/projects/{slug}/vault/keys/delete/` | Delete with `{ key, confirm: true }` |
| POST | `/api/v1/projects/{slug}/verify/` | Stripe key verification |
| POST | `/api/v1/projects/{slug}/runs/` | Start pipeline (202 + run id) |
| GET | `/api/v1/projects/{slug}/runs/{id}/download/` | Download generated zip |

### WebSocket

```
ws://localhost:8000/ws/runs/{run_id}/?token={jwt_access_token}
```

Messages: `{ "type": "pipeline.event", "runId": "...", "event": { "step", "status", "message" } }`

## Pipeline steps

1. Verify API keys  
2. Provision products/prices + webhook (Stripe API)  
3. Generate code (Python Jinja2 codegen; optional Node CLI via `STRIPE_INSTALLER_CLI`)  
4. Optional sync `.env.local`  
5. Readiness score  

## Platform billing (optional)

Set in `backend/.env`:

```
SAAS_STRIPE_SECRET_KEY=sk_test_...
SAAS_STRIPE_WEBHOOK_SECRET=whsec_...
SAAS_STRIPE_PRICE_STARTER=price_...
SAAS_STRIPE_PRICE_PRO=price_...
SAAS_BILLING_RETURN_URL=http://localhost:5173/billing
```

## Related

- [`docs/DJANGO-SAAS-API-MAP.md`](../docs/DJANGO-SAAS-API-MAP.md)
