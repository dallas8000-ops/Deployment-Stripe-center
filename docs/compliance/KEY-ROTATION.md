# Vault master key rotation

The vault encrypts per-project secrets with a deployment-wide **master key** (`VAULT_MASTER_KEY`). Rotate periodically and after any suspected compromise.

## Prerequisites

- Maintenance window (all web/worker/beat processes must use the new key after rotation).
- Backup: export vault via existing backup beat task or DB snapshot.
- Generate a new 32-byte key as **64-char hex** (or base64).

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Staging drill (required annually)

```bash
cd backend
export VAULT_MASTER_KEY=<staging-current-hex>
python manage.py rotate_vault_key --new-key <new-hex> --dry-run
python manage.py rotate_vault_key --new-key <new-hex>
# Update staging Railway/env to new key, redeploy, verify /health/ vault: ok
```

## Production rotation

1. **Dry run** — count secrets that would be re-encrypted:

   ```bash
   python manage.py rotate_vault_key --new-key <NEW_HEX> --dry-run
   ```

2. **Rotate** (writes new ciphertext for every vault secret):

   ```bash
   python manage.py rotate_vault_key --new-key <NEW_HEX>
   ```

3. **Update env** — set `VAULT_MASTER_KEY=<NEW_HEX>` on Railway (and local `backend/.env` if used).

4. **Redeploy** all services (web, worker, beat, transfer-worker) in one rollout.

5. **Verify**:

   ```bash
   curl https://<your-domain>/health/
   python manage.py compliance_check
   ```

6. **Securely destroy** the old key after 24h stable operation.

## What rotation does

`apps/vault/rotation.py` decrypts each `VaultSecret` with the current master key and re-encrypts with the new key. It does **not** rotate Stripe API keys or Railway tokens — only the envelope encryption layer.

## Pen test focus

- Confirm old master key cannot decrypt after rotation.
- Confirm rotation is atomic per secret (transaction per row).
- Confirm master key never appears in logs, Sentry, or API responses.
