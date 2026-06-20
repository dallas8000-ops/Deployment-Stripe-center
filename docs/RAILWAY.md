# Railway deployment

Single-container deploy using the repo `Dockerfile` and `railway.toml`.

## Required Railway variables

Set these in **Railway → your service → Variables** (not only in local `backend/.env`):

| Variable | Example / notes |
|----------|----------------|
| `VAULT_MASTER_KEY` | **Required.** 64 hex chars — `python -c "import secrets; print(secrets.token_hex(32))"`. Pin once and never rotate without `rotate_vault_key`. |
| `DJANGO_SECRET_KEY` | Random 50+ chars |
| `DJANGO_DEBUG` | `false` |
| `DATABASE_URL` | Auto-set when you add the **PostgreSQL** plugin |
| `SAAS_STRIPE_SECRET_KEY` | Your Stripe secret (if billing enabled) |
| `SAAS_STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret |
| `SAAS_STRIPE_PRICE_*` | Price IDs for plans |
| `SAAS_STRIPE_WEBHOOK_SECRET` | From Stripe Dashboard → Webhooks |

### Vault master key (read this first)

Project secrets (Railway API token, Stripe keys, etc.) are encrypted in Postgres with a key derived from **`VAULT_MASTER_KEY`** via scrypt + AES-GCM. If the master key changes between deploys, **every stored secret becomes permanently undecryptable** — this looks like “env vars not retaining.”

| Environment | Where the key comes from |
|-------------|-------------------------|
| **Railway** | **`VAULT_MASTER_KEY` env var only** (env wins over any file on ephemeral disk) |
| **Local dev** | `~/.stripe-installer/vault-master-key` (file first; env migrates to file) |

**Railway checklist:**

1. Generate once: `python -c "import secrets; print(secrets.token_hex(32))"`
2. Railway → **stripe-installer-production** (unified service) → **Variables** → set `VAULT_MASTER_KEY` to that value
3. When merging API Transfer onto the same service, **use one key** — if old services had different keys, pick the key that decrypts live secrets or re-enter secrets after pinning a new key
4. Do **not** rely on `~/.stripe-installer/` on Railway — the filesystem resets on redeploy; the local vault mirror (`projects/*/vault.json`) uses the same master key and does not help if the key is lost
5. After setting the key, redeploy and verify: `curl https://<your-domain>/health/` shows vault ok; open a project and confirm stored tokens still decrypt

**If secrets were already lost:** set a new permanent `VAULT_MASTER_KEY`, redeploy, re-enter platform tokens in each project vault (Stripe Dashboard, Railway tokens, etc.).

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
4. **Remove dev-only vars** from Railway Raw Editor if you copied local `.env`:
   - `REDIS_URL=redis://127.0.0.1:6379/0` (breaks health checks — Railway stops routing)
   - `CELERY_EAGER=true`, `CHANNEL_LAYER_INMEMORY=true` (not needed; Django auto-configures on Railway)
   - `CORS_ALLOWED_ORIGINS=http://localhost:...`
   - `SAAS_BILLING_RETURN_URL=http://localhost:5173`
5. **Deploy logs** in Railway → Deployments → View logs (migrate errors show here).
6. **Networking** — public domain must be on the **web service**, not Postgres. Latest deploy must be **Active**.
7. Redeploy after setting variables — local `backend/.env` is **not** uploaded to Railway unless you copy vars manually.

## Custom domain

1. Railway → Settings → Networking → Custom Domain.
2. Set `APP_PUBLIC_URL=https://yourdomain.com` and add the domain to Stripe webhook URLs.
3. Update `GITHUB_APP_SETUP_URL` if using GitHub App.

## No Render

This project deploys to **Railway** (or Docker/Vercel/Fly for client apps). Render is not supported or referenced in the active deploy stack.
