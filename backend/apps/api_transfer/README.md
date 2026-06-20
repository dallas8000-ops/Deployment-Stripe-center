# API Transfer module

Deploy/migration features merged from **API Transfer** (`migrationengine`, `deployments`).

## Endpoints (slice 1)

| Route | Purpose |
|-------|---------|
| `GET /api/v1/transfer/status/` | Module status |
| `GET /api/v1/transfer/providers/status/` | Railway/Render/GitHub readiness |
| `POST /api/v1/transfer/github/import/` | Import public/private GitHub repo |
| `POST /api/v1/transfer/deploy/detect/` | Framework detection |
| `POST /api/v1/transfer/start/` | Start Render→Railway migration |
| `POST /api/v1/transfer/stop/` | Stop in-process migration worker |
| `GET /api/v1/transfer/runs/status/` | Active migration status + log tail |
| `GET /api/v1/transfer/runs/history/` | Migration run history |
| `POST /api/v1/transfer/runs/replay/{run_id}/` | Re-queue failed run |
| `POST /api/v1/transfer/platform/setup-run/` | Run verify action (read-only API checks) |
| `GET /api/v1/transfer/platform/setup-audit/` | Credential gap audit |

## Worker

Process queued migration runs (after **Queue only** start):

```bash
npm run transfer:worker
# or one batch:
npm run transfer:worker:once
```
| `POST /api/v1/projects/{slug}/transfer/github/import/` | Import tied to project + vault |
| `POST /api/v1/projects/{slug}/transfer/deploy/` | Full deploy pipeline |
| `GET /api/v1/projects/{slug}/transfer/deploy/history/` | Deployment history |
| `POST /api/v1/transfer/env/backup/railway/` | Railway env snapshot |

| Piece | App |
|-------|-----|
| Projects | `apps.projects` |
| Vault | `apps.vault` — `get_project_secret()` |
| Stripe setup | `apps.stripe_installer` |

## Rule

```python
from apps.vault.services import get_project_secret

token = get_project_secret(project, "RAILWAY_API_TOKEN")
```

Never return secret values to the frontend.

## Still to port

- Render→Railway transfer runs (`TransferRun`, worker)
- Platform setup audit / console bootstrap
- Terraform plan/apply
- Full API Transfer frontend (`features/transfer/`)
