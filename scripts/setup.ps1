# First-time setup (Windows)
param(
    [switch]$SkipMigrate
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Backend = Join-Path $Root "backend"
$EnvFile = Join-Path $Backend ".env"
$EnvExample = Join-Path $Backend ".env.example"

Write-Host "Stripe Installer setup" -ForegroundColor Cyan

$VenvPython = Join-Path $Backend ".venv\Scripts\python.exe"
$PyvenvCfg = Join-Path $Backend ".venv\pyvenv.cfg"
$VenvBroken = $false
if (Test-Path $PyvenvCfg) {
    $cfg = Get-Content $PyvenvCfg -Raw
    if ($cfg -match "saas\\backend" -or $cfg -notmatch [regex]::Escape($Backend)) {
        $VenvBroken = $true
    }
}

if ($VenvBroken -or -not (Test-Path $VenvPython)) {
    if ($VenvBroken) {
        Write-Host "Removing broken venv (still pointed at old saas/ path)..." -ForegroundColor Yellow
        Remove-Item -Recurse -Force (Join-Path $Backend ".venv") -ErrorAction SilentlyContinue
    } else {
        Write-Host "Creating Python venv..."
    }
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

Write-Host "Installing npm dependencies (root + frontend)..."
Push-Location $Root
npm install
Pop-Location
npm install --prefix (Join-Path $Root "frontend")

Write-Host ""
Write-Host "Done. Start the app:" -ForegroundColor Green
Write-Host "  npm run dev"
Write-Host "  # or: .\scripts\dev.ps1"
Write-Host ""
Write-Host "Open http://localhost:5173" -ForegroundColor Yellow
