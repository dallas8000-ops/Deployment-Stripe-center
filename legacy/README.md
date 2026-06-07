# Archived Node.js CLI + Electron (v0.6)

This folder is **not part of the active product**. Stripe Installer was rewritten as a single Django + React app at the repo root (`backend/`, `frontend/`).

## Why it's here

Reference only — for porting any remaining logic (AI orchestrator, Neon/Supabase postgres provision, full deploy pipeline) into Django.

## If you need the old CLI

```powershell
cd legacy/node
npm install
npm run dev -- scan ./your-project
npm run gui
```

Do not run Node and Django side by side for the same project — use **one vault** (Django DB).
