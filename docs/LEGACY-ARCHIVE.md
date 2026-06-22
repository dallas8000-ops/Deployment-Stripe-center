# Legacy archive policy

The `legacy/` directory holds the **v0.6 Node.js CLI and Electron GUI**. It is not deployed and not part of Tier-1 production.

## Status

| Item | Status |
|------|--------|
| `legacy/node/` | Archived reference — logic ported to Django |
| `legacy/desktop/` | Archived Electron shell |
| `STRIPE_INSTALLER_CLI` env | Optional; Python codegen is canonical |
| `api-transfer-production` Railway | Retire per [CUTOVER.md](CUTOVER.md) |

## Removal criteria

Delete `legacy/` from the repo when **all** are true:

1. [CUTOVER.md](CUTOVER.md) manual steps 1–5 complete (unified app only in production).
2. No operator relies on `legacy/node` for codegen or GUI.
3. README and `settings.py` references updated (search `legacy/`).

Until then, keep `legacy/` for diff reference only. Do **not** run Node and Django vaults on the same project.

## After deletion

- Remove `STRIPE_INSTALLER_CLI` from `settings.py` and `.env.example`.
- Remove legacy sections from README and ARCHITECTURE.md.
