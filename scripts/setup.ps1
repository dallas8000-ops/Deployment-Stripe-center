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
    Add-Content $EnvFile @"

CELERY_EAGER=true
CHANNEL_LAYER_INMEMORY=true
"@
}

Write-Host "Ensuring local vault master key (~/.stripe-installer/vault-master-key)..."
Push-Location $Backend
.\.venv\Scripts\python.exe -c "from apps.vault.master_key import resolve_vault_master_key; resolve_vault_master_key()"
Pop-Location
Write-Host "Vault master key is stored locally (never committed to git)." -ForegroundColor Green

$PrivateEnv = Join-Path $Root "private_env"
if (-not (Test-Path $PrivateEnv)) {
    New-Item -ItemType Directory -Path $PrivateEnv | Out-Null
}
foreach ($name in @("stripe", "railway", "render", "github")) {
    $example = Join-Path $PrivateEnv "$name.env.example"
    $target = Join-Path $PrivateEnv "$name.env"
    if ((Test-Path $example) -and -not (Test-Path $target)) {
        Copy-Item $example $target
        Write-Host "Created private_env/$name.env from example (local only, not in git)" -ForegroundColor Yellow
    }
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
Write-Host ""
Write-Host "Optional — test software protection locally:" -ForegroundColor Cyan
Write-Host "  cd backend"
Write-Host "  .\.venv\Scripts\python.exe manage.py issue_dev_license --email you@test.com --domain localhost"
Write-Host "  # Add printed env vars to backend/.env, set LICENSE_ENFORCEMENT_ENABLED=true, restart"
