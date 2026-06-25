# Production hosting — Stripe Installer



Guide for running the Django + React installer itself in production (not the apps it generates for clients).



## Stack



| Service | Role |

|---------|------|

| **Daphne** | ASGI server (HTTP + WebSocket + built React UI) |

| **Celery worker** | Pipeline jobs |

| **Redis** | Celery broker + Channels layer |

| **PostgreSQL** | App database (required in Docker prod profile) |

| **WhiteNoise** | Serves `frontend/dist` static assets |



## Quick start — Docker Compose (recommended)



1. Copy `backend/.env.example` → `backend/.env` and set at minimum:



```env

VAULT_MASTER_KEY=<64-hex-chars>

DJANGO_SECRET_KEY=<random-50-chars>

DJANGO_DEBUG=false

```



2. Build and start the full stack:



```powershell

npm run docker:prod

```



This starts **postgres**, **redis**, **web** (Daphne on `:8000`), **celery**, and **celery-beat** (drift checks). Open **http://127.0.0.1:8000** — API and React UI are served from the same origin.



Stop:



```powershell

npm run docker:prod:down

```



### Services



| Service | Port | Profile |

|---------|------|---------|

| redis | 6379 | default |

| postgres | 5432 | `prod` |

| web | 8000 | `prod` |

| celery | — | `prod` |
| celery-beat | — | `prod` |



Local dev still uses `npm run dev` (Vite on `:5173`, API on `:8000`). Only use Docker prod when hosting the installer itself.



## Manual setup (without Docker)



### 1. Environment



Copy `backend/.env.example` to `backend/.env` and set:



```env

DJANGO_DEBUG=false

DJANGO_SECRET_KEY=<random-50-chars>

DJANGO_ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com

CORS_ALLOWED_ORIGINS=https://yourdomain.com



VAULT_MASTER_KEY=<64-hex-chars>

DATABASE_URL=postgresql://user:pass@postgres:5432/stripe_core



REDIS_URL=redis://redis:6379/0

CELERY_EAGER=false

CHANNEL_LAYER_INMEMORY=false

```



Generate keys:



```powershell

python -c "import secrets; print(secrets.token_hex(32))"  # VAULT_MASTER_KEY

python -c "import secrets; print(secrets.token_urlsafe(50))"  # DJANGO_SECRET_KEY

```



### 2. Build frontend



```powershell

cd frontend

npm ci

npm run build

```



WhiteNoise serves `frontend/dist` from Daphne when the folder exists.



### 3. Start services



```powershell

docker compose up -d redis postgres

cd backend

.venv\Scripts\python.exe manage.py migrate

.venv\Scripts\python.exe manage.py collectstatic --noinput

.venv\Scripts\celery.exe -A config worker -l info

.venv\Scripts\daphne.exe -b 0.0.0.0 -p 8000 config.asgi:application

```



## 4. SSL / reverse proxy



Put nginx or Caddy in front of Daphne:



- Proxy `/api` and `/ws` to `127.0.0.1:8000`

- Or serve everything from Daphne (static + SPA fallback included)

- Terminate TLS at the proxy



WebSocket path: `/ws/runs/{run_id}/?token={jwt}`



## 5. Platform billing (optional)



Set `SAAS_STRIPE_*` vars in `.env` for Stripe Installer subscriptions. See `backend/.env.example`.



## 6. Vault key rotation



`VAULT_MASTER_KEY` encrypts all project secrets. Rotating it requires re-encrypting vault rows — plan maintenance before changing in production.



## Git workspace (real app folders only)



Each project must use `local_path` pointing at **your app's own folder** on disk (e.g. `C:\Software Projects\YourApp`). The hub **does not** clone repos into `backend/clones/` — clone manually in your app folder, then use **Git pull** in Settings or `POST /api/v1/projects/{slug}/git-pull/`.

### Private repositories

| Method | Local dev | Docker prod |
|--------|-----------|-------------|
| **HTTPS token** | Store `GITHUB_TOKEN` or `GIT_TOKEN` in project vault | Same |
| **SSH key** | `GIT_SSH_KEY_PATH` in `backend/.env` | Mount: `GIT_SSH_KEY_PATH=./.git-secrets/id_ed25519` |
| **Credential file** | `GIT_CREDENTIALS_PATH` in `.env` | Mount read-only into web/celery |

Git pull: `POST /api/v1/projects/{slug}/git-pull/` (pulls in `local_path` only).

Open PR: `POST /api/v1/projects/{slug}/open-pr/` (requires `GITHUB_TOKEN` in vault).

### Vault key rotation

```powershell
python manage.py rotate_vault_key --new-key <64-hex> --dry-run
python manage.py rotate_vault_key --new-key <64-hex>
```

### CLI

```powershell
python manage.py stripe_core run <slug>
python manage.py stripe_core deploy <slug> --push
```

## Local dev shortcuts



| Variable | Effect |

|----------|--------|

| `CELERY_EAGER=true` | Run pipeline in-process (no worker) |

| `CHANNEL_LAYER_INMEMORY=true` | WebSocket without Redis |



Do **not** use these in production.

## Production deploy checklist

Use this before pointing a real domain at the installer.

### Environment

- [ ] `DJANGO_DEBUG=false`, strong `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` set
- [ ] `VAULT_MASTER_KEY` generated and backed up (rotation needs `manage.py rotate_vault_key`)
- [ ] `DATABASE_URL` → PostgreSQL (not SQLite)
- [ ] `REDIS_URL` reachable from web + celery + celery-beat
- [ ] `CELERY_EAGER=false`, `CHANNEL_LAYER_INMEMORY=false`
- [ ] `CORS_ALLOWED_ORIGINS` / `SAAS_BILLING_RETURN_URL` match your public URL
- [ ] Each project's `local_path` points at its real app folder (not inside this hub repo)

### Services

- [ ] `python manage.py migrate` after each deploy
- [ ] `python manage.py collectstatic --noinput` (or image build includes `frontend/dist`)
- [ ] Daphne (or ASGI) behind TLS reverse proxy
- [ ] Celery worker running
- [ ] Celery beat running (`stripe_engine.check_all_projects_drift` every 6h)

### GitHub App (optional)

- [ ] Create GitHub App with webhook URL: `https://your-host/api/v1/webhooks/github/`
- [ ] Set `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY`, `GITHUB_APP_SLUG`, `GITHUB_WEBHOOK_SECRET`
- [ ] Setup URL: `https://your-host/agency/github/callback` (or `GITHUB_APP_SETUP_URL`)
- [ ] Org admins install via Agency → **Install GitHub App**

### SaaS billing (optional)

- [ ] `SAAS_STRIPE_*` price IDs and webhook endpoint for org subscriptions
- [ ] Free tier limits: `ORG_FREE_MEMBER_LIMIT`, `ORG_FREE_PROJECT_LIMIT`

### Smoke test

- [ ] Register / log in, create project, init vault, run pipeline
- [ ] `GET /api/v1/health/` returns ok
- [ ] WebSocket run logs on `/ws/runs/{id}/`

