# Agent rules for Deployment-Stripe-center

These rules apply to every AI coding agent (Claude Code, Codex, Cursor, Windsurf, Copilot) working in this repo.

## Never create clones of portfolio repos on this machine

- Do **not** `git clone` (or unzip a GitHub archive of) any portfolio repo into this repo or anywhere under `C:\Software Projects`. A second local copy of a repo has repeatedly drifted from the real one and pushed conflicting work to Railway-connected branches.
- To **review** another repo, read it in place at its canonical path (see `backend/apps/stripe_core/portfolio_workspace.py` -> `DEFAULT_LOCAL_PATHS`). Do not modify it from here unless asked.
- If an isolated copy is genuinely required, use a throwaway directory under the OS temp folder (`%TEMP%` / `tempfile.mkdtemp()`), never inside `C:\Software Projects`, and delete it when done.
- Do not leave `*.patch` files, `.tmp-*` folders, or logs in the repo root.

## Generated deploy configs

- `backend/apps/deploy/infra.py` must never emit a guessed start command. Django start commands come from `resolve_django_wsgi_module()`; if it returns `None`, the Dockerfile / `railway.toml` is skipped.
- Never generate a root `railway.toml` or `Dockerfile` for a monorepo (app under `backend/` or `apps/backend/`): Railway services there are configured per service, and a root config overrides every service's build.
- Regression tests: `backend/apps/deploy/tests/test_infra_generation.py`.
