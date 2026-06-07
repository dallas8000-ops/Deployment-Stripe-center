# Stripe Installer

AI-assisted Stripe setup that **never exposes secrets to AI or logs**. One Django + React product — encrypted vault, live pipeline, codegen, diagnose/fix, and deploy readiness.

## Architecture

```
backend/          Django — vault, pipeline, stripe_engine, billing, deploy, ai
frontend/         React — dashboard, vault UI, live pipeline terminal
legacy/node/      Archived Node CLI + Electron (reference only)
```

### One database, one vault

| Data | Stored | Exposed via API? |
|------|--------|------------------|
| Stripe keys | AES-256-GCM in Postgres/SQLite | **Never** — write-only, masked display only |
| Projects, runs, manifest | Django ORM | Yes (no secret values) |
| Scan / readiness | JSON on `Project` | Yes (sanitized) |

## Quick start

```powershell
.\scripts\setup.ps1          # first time: venv, .env + vault key, migrate, npm
npm run dev                  # backend :8000 + frontend :5173
```

Open **http://localhost:5173**

## Features

| Area | What it does |
|------|----------------|
| **Vault** | Write-only secrets, `sk_live_••••••••••••` display, live verify badge |
| **Scanner** | Detect framework, deps, existing Stripe code |
| **Pipeline** | Verify → provision → codegen → optional env sync → readiness |
| **WebSocket** | Live pipeline log stream in the browser |
| **Diagnose & fix** | Health scan + automated repairs |
| **Codegen** | Jinja2 templates — Django, Next.js, Express, Flask, and more |
| **Deploy** | Postgres schema export, DATABASE_URL status |
| **AI** | Local sanitized recommendations (optional Anthropic/OpenAI later) |
| **Billing** | Platform subscriptions (optional `SAAS_STRIPE_*` env) |

## API (base `/api/v1/`)

| Method | Path |
|--------|------|
| POST | `/auth/register/`, `/auth/login/` |
| GET/POST | `/projects/` |
| POST | `/projects/{slug}/vault/init/`, `.../vault/keys/set/`, `.../vault/keys/delete/` |
| POST | `/projects/{slug}/verify/`, `.../runs/`, `.../diagnose/`, `.../fix/` |
| GET | `/projects/{slug}/readiness/`, `.../runs/{id}/download/` |
| GET | `/projects/{slug}/postgres/status/`, `.../postgres/schema/` |
| POST | `/projects/{slug}/ai/recommend/` |
| WS | `/ws/runs/{run_id}/?token={jwt}` |

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for module mapping.

## Dev environment

`backend/.env` (see `backend/.env.example`):

- `VAULT_MASTER_KEY` — **required** — `python -c "import secrets; print(secrets.token_hex(32))"`
- `CELERY_EAGER=true` + `CHANNEL_LAYER_INMEMORY=true` — no Redis/Celery needed locally

Production: `docker compose up -d redis`, set `CELERY_EAGER=false`, run Celery worker + Daphne.

## Verify

```powershell
npm run smoke
cd frontend; npm run build
```

## Legacy Node CLI

The v0.6 CLI and Electron app live in [`legacy/node/`](legacy/node/README.md) for reference only. **Do not run both stacks on the same project.**

## Roadmap

- [ ] Neon/Supabase auto-provision (port from legacy)
- [ ] Full one-click deploy pipeline in Django
- [ ] Anthropic/OpenAI provider in `apps.ai`
- [ ] Production hosting guide (Postgres, Redis, SSL)
