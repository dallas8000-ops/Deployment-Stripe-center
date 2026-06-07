# First-time setup for Stripe Installer SaaS (Windows)
param(
    [switch]$SkipMigrate
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Backend = Join-Path $Root "backend"
$EnvFile = Join-Path $Backend ".env"
$EnvExample = Join-Path $Backend ".env.example"

Write-Host "Stripe Installer setup" -ForegroundColor Cyan

if (-not (Test-Path (Join-Path $Backend ".venv\Scripts\python.exe"))) {
    Write-Host "Creating Python venv..."
    Push-Location $Backend
    python -m venv .venv
    .\.venv\Scripts\pip.exe install -r requirements.txt
    Pop-Location
}

if (-not (Test-Path $EnvFile)) {
    Write-Host "Creating backend/.env from example..."
    Copy-Item $EnvExample $EnvFile
    $key = -join ((1..32 | ForEach-Object { '{0:x2}' -f (Get-Random -Max 256) }))
    Add-Content $EnvFile @"

VAULT_MASTER_KEY=$key
CELERY_EAGER=true
CHANNEL_LAYER_INMEMORY=true
"@
    Write-Host "Generated VAULT_MASTER_KEY in backend/.env" -ForegroundColor Green
}

if (-not $SkipMigrate) {
    Write-Host "Running migrations..."
    Push-Location $Backend
    .\.venv\Scripts\python.exe manage.py migrate
    Pop-Location
}

if (-not (Test-Path (Join-Path $Root "node_modules"))) {
    npm install --prefix $Root
}

if (-not (Test-Path (Join-Path $Root "frontend\node_modules"))) {
    npm install --prefix (Join-Path $Root "frontend")
}

Write-Host ""
Write-Host "Done. Start the app:" -ForegroundColor Green
Write-Host "  npm run dev"
Write-Host ""
Write-Host "Open http://localhost:5173" -ForegroundColor Yellow
