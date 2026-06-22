# SOC 2 readiness — control mapping

This is a **readiness checklist**, not a certification. Map each control to evidence in this repo and your operator runbooks.

## CC6 — Logical access

| Control | Implementation | Evidence |
|---------|----------------|----------|
| Unique user IDs | Django `User` + JWT | `apps/accounts/` |
| MFA for privileged users | TOTP | `apps/accounts/mfa.py`, `/account/security` |
| Enterprise SSO | OIDC | `apps/accounts/sso.py`, `deploy/OIDC-SSO.md` |
| Session timeout | JWT refresh window | `SIMPLE_JWT` in `config/settings.py` |
| Quarterly access review | Process | `deploy/COMPLIANCE.md` |

## CC7 — System operations

| Control | Implementation | Evidence |
|---------|----------------|----------|
| Health / readiness | `/health/`, `/health/ready/` | `apps/diagnostics/` |
| Metrics | `/health/metrics/` | `apps/diagnostics/ops_metrics.py` |
| Error tracking | Sentry | `config/sentry.py`, `deploy/OBSERVABILITY.md` |
| Request tracing | `X-Request-ID` | `apps/core/middleware.py` |
| Backup | Vault + DB backups | `stripe_engine.auto_backup_all_projects` beat task |

## CC8 — Change management

| Control | Implementation | Evidence |
|---------|----------------|----------|
| Version control | GitHub | `origin/main` deploys |
| CI tests + coverage gate | GitHub Actions | `.github/workflows/` |
| Dependency scanning | Dependabot, pip-audit | `.github/dependabot.yml` |
| Production config guard | `DEBUG=false` default | `config/settings.py` |

## CC9 — Risk mitigation (audit)

| Control | Implementation | Evidence |
|---------|----------------|----------|
| Project audit log | `AuditLog` model | `apps/projects/audit.py` |
| Transfer tamper-evident log | Hash chain | `apps/api_transfer/audit.py` |
| Chain verification | `verify_audit_chain` | management command + API |
| Retention policy | Env + prune job | `AUDIT_LOG_RETENTION_DAYS`, `prune_audit_logs` |
| Secret redaction in audits | `redact_sensitive_values` | `apps/api_transfer/redaction.py` |

## CC6.1 — Encryption

| Control | Implementation | Evidence |
|---------|----------------|----------|
| Secrets at rest | Vault AES-GCM | `apps/vault/crypto.py` |
| Key rotation | `rotate_vault_key` | `docs/compliance/KEY-ROTATION.md` |
| TLS in transit | Railway / reverse proxy | `deploy/DNS-SSL-SETUP.md` |
| No secrets in frontend | API design | `docs/AUTOMATION-CENTER.md` |

## Operator cadence

| Frequency | Action |
|-----------|--------|
| Weekly | Review Sentry errors; confirm `/health/` green |
| Monthly | `compliance_check`; review subprocessors list |
| Quarterly | Access review; pen test findings triage |
| Annually | Vault key rotation drill (staging); DPA review |
