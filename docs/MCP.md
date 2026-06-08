# MCP server — Stripe Installer

Expose project readiness, drift, vault status, and pipeline control to Cursor (or any MCP client) over stdio.

## Setup

1. Copy `.cursor/mcp.json.example` → `.cursor/mcp.json` (gitignored).
2. Set `STRIPE_INSTALLER_USER` to your Stripe Installer account email.
3. Ensure the backend venv is active or use the full path to `python` in `mcp.json`.
4. Restart Cursor or reload MCP servers.

## Run manually

```powershell
cd backend
$env:STRIPE_INSTALLER_USER = "you@example.com"
python manage.py run_mcp_server
```

The server speaks JSON-RPC on stdin/stdout (MCP tools protocol).

## Tools

| Tool | Description |
|------|-------------|
| `list_projects` | Projects visible to `STRIPE_INSTALLER_USER` |
| `project_readiness` | CI-style readiness gate |
| `project_drift` | Stripe catalog drift vs manifest |
| `project_diagnose` | Full health report (needs `local_path`) |
| `project_vault_status` | Masked vault keys (never plaintext) |
| `start_pipeline` | Queue a pipeline run |
| `project_open_pr_prep` | Suggested PR title/body + dirty files |

## Security

- Secrets are never returned — vault tool uses the same masked entries as the UI.
- Access is scoped to the user email in `STRIPE_INSTALLER_USER` (same RBAC as the web app).
- Do not commit `.cursor/mcp.json` if it contains local paths or emails you consider sensitive.
