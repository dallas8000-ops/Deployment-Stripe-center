# API Transfer module

Deploy/migration features merged from **API Transfer** (`migrationengine`, `deployments`).

## Endpoints

| Route | Purpose |
|-------|---------|
| `GET /api/v1/transfer/status/` | Module status |
| `GET /api/v1/transfer/providers/status/` | Railway/Render/GitHub/Orena readiness |
| `POST /api/v1/transfer/github/import/` | Import public/private GitHub repo |
| `POST /api/v1/transfer/deploy/detect/` | Framework detection |
| `POST /api/v1/transfer/start/` | Start Render→Railway migration |
| `POST /api/v1/transfer/stop/` | Stop in-process migration worker |
| `GET /api/v1/transfer/runs/status/` | Active migration status + log tail |
| `GET /api/v1/transfer/runs/history/` | Migration run history |
| `GET /api/v1/transfer/runs/metrics/` | Queue metrics (running, queued, dead letter) |
| `POST /api/v1/transfer/runs/replay/{run_id}/` | Re-queue failed run |
| `GET /api/v1/transfer/audit/` | Tamper-evident audit log + chain verify |
| `GET /api/v1/transfer/audit/export/` | Audit export bundle |
| `POST /api/v1/transfer/platform/setup-run/` | Run verify action (read-only API checks) |
| `GET /api/v1/transfer/platform/setup-audit/` | Credential gap audit |
| `POST /api/v1/projects/{slug}/transfer/github/import/` | Import tied to project + vault |
| `POST /api/v1/projects/{slug}/transfer/deploy/` | Full deploy pipeline |
| `GET /api/v1/projects/{slug}/transfer/deploy/history/` | Deployment history |
| `POST /api/v1/transfer/env/backup/railway/` | Railway env snapshot |

## Worker

Process queued migration runs (after **Queue only** start):

```bash
npm run transfer:worker
# or one batch:
npm run transfer:worker:once
```

| Piece | App |
|-------|-----|
| Projects | `apps.projects` |
| Vault | `apps.vault` — `get_project_secret()` |
| Stripe setup | `apps.stripe_core` |

## Rule

```python
from apps.vault.services import get_project_secret

token = get_project_secret(project, "RAILWAY_API_TOKEN")
```

Never return secret values to the frontend.

## Completed (merged)

- Deploy pipeline (Railway / Render / Fly)
- GitHub import + framework detection
- Render→Railway transfer runs (`TransferRun`, worker, replay)
- Project-scoped deploy UI (`TransferPanel.tsx`)
- Platform setup audit + verify actions
- Railway env backup
- Audit log (write + list + chain verify)
- Transfer metrics endpoint + UI

## Still to port

- Discover / plan / apply / rollback (`migrationengine/adapters.py`, `planner.py`)
- Terraform plan/apply (`migrationengine/terraform.py`)
- Console bootstrap (single-call provider inventories)
- Client prewire + East Africa env templates (`core/platform_setup.py` extended features)
- Full modular frontend under `frontend/src/features/transfer/`
- Port standalone test suite (`migrationengine/tests_*.py`, `deployments/tests_*.py`)

## Production cutover

When retiring the standalone API Transfer Railway service and old Stripe Installer URLs, see [docs/CUTOVER.md](../../../docs/CUTOVER.md).

## Portfolio site & live demo links

[gilliomfrontlinedigital.com](https://gilliomfrontlinedigital.com/) is the **marketing portfolio** (repo: `FrontlineDigital/DevCollective`). It does **not** host the automation apps — each project card’s **Live demo** button opens a **separate Railway service**.

Canonical URL map (source of truth for demo buttons):

`FrontlineDigital/DevCollective/frontend/src/data/portfolioLiveUrls.ts`

| Portfolio card | Live demo key | Current Railway URL |
|----------------|---------------|---------------------|
| Stripe Installer | `stripeInstaller` | `https://stripe-installer-production.up.railway.app/login` |
| API Transfer | `apiTransfer` | `https://api-transfer-production.up.railway.app` |
| Kistie Store | `kistieStore` | `https://kistie-store-production.up.railway.app` |
| … | … | (see `portfolioLiveUrls.ts`) |

Marketing site itself:

| Role | URL |
|------|-----|
| Custom domain (Porkbun) | `https://gilliomfrontlinedigital.com` |
| Railway service | `frontlinedigital-1-production.up.railway.app` |
| Contact API | `portfolioLiveUrls.apiBase` |

**After merging Stripe Installer + API Transfer:**

1. Keep **one** Railway service for the unified app (recommend: `stripe-installer-production`).
2. Update `portfolioLiveUrls.stripeInstaller` to the unified login URL.
3. Point `portfolioLiveUrls.apiTransfer` to the **same** URL **or** remove the duplicate API Transfer card and expand the Stripe Installer card copy.
4. Update `~/.stripe-installer/portfolio-registry.json` (`productionUrl`, drop `api-transfer-legacy`).
5. Do **not** change Porkbun `@` DNS for the portfolio unless the marketing site moves — demo buttons use `*.up.railway.app` directly.

See [docs/CUTOVER.md](../../../docs/CUTOVER.md) § Gilliom portfolio architecture.
