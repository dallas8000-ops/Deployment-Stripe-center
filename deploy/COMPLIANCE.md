# Compliance — Automation Center

Operational compliance for **Deployment & Stripe Automation Center** (Tier-1 production). Use this index with the detailed docs under `docs/compliance/`.

## Quick checks

```bash
cd backend
python manage.py compliance_check
python manage.py verify_audit_chain
python manage.py prune_audit_logs --dry-run
```

## Documents

| Doc | Purpose |
|-----|---------|
| [docs/compliance/SOC2-READINESS.md](../docs/compliance/SOC2-READINESS.md) | Control mapping (access, change mgmt, logging) |
| [docs/compliance/SUBPROCESSORS.md](../docs/compliance/SUBPROCESSORS.md) | Third parties that process customer data |
| [docs/compliance/DPA-OUTLINE.md](../docs/compliance/DPA-OUTLINE.md) | Enterprise DPA outline |
| [docs/compliance/KEY-ROTATION.md](../docs/compliance/KEY-ROTATION.md) | Vault master key rotation runbook |
| [deploy/OBSERVABILITY.md](OBSERVABILITY.md) | Sentry, structured logs, request IDs |
| [deploy/OIDC-SSO.md](OIDC-SSO.md) | Enterprise SSO |

## Audit logging

| Store | Location | Tamper evidence |
|-------|----------|-----------------|
| Project actions | `projects.AuditLog` | DB + actor + timestamp |
| API Transfer ops | `api_transfer.AuditEntry` | Hash chain (`verify_audit_chain`) |

**Retention** (env):

- `AUDIT_LOG_RETENTION_DAYS` — project audit (default `365`)
- `TRANSFER_AUDIT_RETENTION_DAYS` — transfer chain (default `2555` ≈ 7 years)

Nightly beat task `compliance.prune_audit_logs` prunes project logs. Transfer logs are **not** auto-pruned; export then prune manually if required.

## Access reviews

Quarterly (recommended):

1. Export org members from Django admin or `/api/v1/organizations/`.
2. Confirm MFA enabled for admins (`/account/security`).
3. Revoke stale API tokens and org invites.
4. Review Railway/GitHub/Stripe dashboard access for operators.

## Change management

- All production changes via GitHub `main` + Railway deploy.
- Dependabot + `pip-audit` in CI (`.github/workflows/`).
- Pre-deploy: `python manage.py check_production` (if configured) and `verify_cutover`.

## Penetration test scope (vault)

Include in external pen tests:

- `apps/vault/crypto.py` — AES-GCM envelope encryption, key derivation
- `rotate_vault_key` — re-encryption under new master key
- API paths that read/write vault secrets (auth required, no secret leakage in responses/logs)
- Transfer audit chain integrity (`verify_audit_chain`)
