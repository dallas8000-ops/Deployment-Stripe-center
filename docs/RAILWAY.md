# Railway deployment

Single-container deploy using the repo `Dockerfile` and `railway.toml`.

## Required Railway variables

Set these in **Railway → your service → Variables** (not only in local `backend/.env`):

| Variable | Example / notes |
|----------|----------------|
| `VAULT_MASTER_KEY` | 64 hex chars — `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DJANGO_SECRET_KEY` | Random 50+ chars |
| `DJANGO_DEBUG` | `false` |
| `DATABASE_URL` | Auto-set when you add the **PostgreSQL** plugin |
| `SAAS_STRIPE_SECRET_KEY` | Your Stripe secret (if billing enabled) |
| `SAAS_STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret |
| `SAAS_STRIPE_PRICE_*` | Price IDs for plans |
| `SAAS_STRIPE_WEBHOOK_SECRET` | From Stripe Dashboard → Webhooks |

**Auto-configured by Railway** (do not hardcode in repo):

- `RAILWAY_PUBLIC_DOMAIN` — public hostname (e.g. `your-app.up.railway.app`)
- `PORT` — injected; entrypoint binds Daphne to this port

**Auto-configured by Django when `RAILWAY_PUBLIC_DOMAIN` is set:**

- `APP_PUBLIC_URL` → `https://<RAILWAY_PUBLIC_DOMAIN>`
- `SAAS_BILLING_RETURN_URL` → same (billing checkout return)
- `CORS_ALLOWED_ORIGINS` → same
- `ALLOWED_HOSTS` → includes `.railway.app` and your public domain

## Optional (recommended for production)

| Variable | Purpose |
|----------|---------|
| `REDIS_URL` | Celery + WebSocket scaling (add Redis plugin) |
| `CELERY_EAGER` | `false` when Redis + Celery worker service exist |
| `CHANNEL_LAYER_INMEMORY` | `false` when using Redis |
| `GITHUB_APP_*` | GitHub App install + PR checks |
| `APP_PUBLIC_URL` | Custom domain override (if not using `*.up.railway.app`) |
| `LICENSE_ENFORCEMENT_ENABLED` | `false` unless licensing deployed copies |

## Stripe webhooks (production)

| Endpoint | URL |
|----------|-----|
| SaaS billing | `https://<your-domain>/api/v1/billing/webhook/` |
| GitHub App | `https://<your-domain>/api/v1/webhooks/github/` |
| License validate | `https://<your-domain>/api/v1/license/validate/` |

## Health check

Railway uses `GET /health/` (see `railway.toml`). After deploy:

```bash
curl https://<your-domain>/health/
```

Expect `"status":"ok"` with database and vault checks passing.

## Troubleshooting 502

1. **PostgreSQL plugin** attached and `DATABASE_URL` visible in Variables.
2. **`VAULT_MASTER_KEY`** set (app health fails without it).
3. **`LICENSE_ENFORCEMENT_ENABLED`** — if `true`, valid license required or startup exits.
4. **Deploy logs** in Railway → Deployments → View logs (migrate errors show here).
5. Redeploy after setting variables — local `backend/.env` is **not** uploaded to Railway unless you copy vars manually.

## Custom domain

1. Railway → Settings → Networking → Custom Domain.
2. Set `APP_PUBLIC_URL=https://yourdomain.com` and add the domain to Stripe webhook URLs.
3. Update `GITHUB_APP_SETUP_URL` if using GitHub App.

## No Render

This project deploys to **Railway** (or Docker/Vercel/Fly for client apps). Render is not supported or referenced in the active deploy stack.
