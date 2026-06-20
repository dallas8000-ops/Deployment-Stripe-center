# Production cutover helper - run from repo root after: railway login
# Docs: docs/CUTOVER.md, docs/MERGE-STATUS.md

$ErrorActionPreference = "Stop"
$UnifiedUrl = "https://stripe-installer.gilliomfrontlinedigital.com"
$UnifiedRailwayUrl = "https://stripe-installer-production.up.railway.app"
$LegacyUrl = "https://api-transfer-production.up.railway.app"

Write-Host "=== Deployment & Stripe Automation Center - cutover helper ===" -ForegroundColor Cyan

Write-Host "`n1. Health checks"
try {
    $unified = Invoke-RestMethod -Uri "$UnifiedUrl/health/" -TimeoutSec 20
    Write-Host "   Unified: $($unified.status) (vault: $($unified.checks.vault))" -ForegroundColor Green
} catch {
    Write-Host "   Unified health FAILED: $_" -ForegroundColor Red
}

try {
    $legacy = Invoke-RestMethod -Uri "$LegacyUrl/health/" -TimeoutSec 15
    Write-Host "   Legacy api-transfer still UP: $($legacy.status)" -ForegroundColor Yellow
} catch {
    Write-Host "   Legacy api-transfer unreachable (OK if already deleted)" -ForegroundColor Green
}

Write-Host "`n2. Portfolio registry (~/.stripe-installer/portfolio-registry.json)"
$reg = Join-Path $env:USERPROFILE ".stripe-installer\portfolio-registry.json"
if (Test-Path $reg) {
    Write-Host "   Found: $reg" -ForegroundColor Green
} else {
    Write-Host "   Missing - copy from backend portfolio_registry EXAMPLE_REGISTRY" -ForegroundColor Yellow
}

Write-Host "`n3. Deploy provider tokens (optional - NOT copied from api-transfer service vars)"
Write-Host "   These were never Railway service variables on api-transfer. They live in each"
Write-Host "   project's vault (~/.stripe-installer/projects/<slug>/ or in-app Settings)."
Write-Host "   Add server-level vars on Stripe-Installer ONLY if you want live deploy without"
Write-Host "   per-project vault setup:"
@(
    "RAILWAY_API_TOKEN   (https://railway.com/account/tokens)",
    "RAILWAY_PROJECT_ID  (auto-set by Railway on this service - do not copy manually)",
    "RENDER_API_TOKEN",
    "RENDER_OWNER_ID",
    "FLY_API_TOKEN",
    "GITHUB_TOKEN",
    "ORENA_API_TOKEN"
) | ForEach-Object { Write-Host "     - $_" }

Write-Host "`n   Keep on unified service only (do NOT duplicate with conflicting values):"
@(
    "VAULT_MASTER_KEY",
    "DJANGO_SECRET_KEY",
    "DATABASE_URL",
    "SAAS_STRIPE_SECRET_KEY",
    "SAAS_STRIPE_WEBHOOK_SECRET",
    "SAAS_STRIPE_PRICE_STARTER",
    "SAAS_STRIPE_PRICE_PRO",
    "SAAS_STRIPE_PRICE_ENTERPRISE"
) | ForEach-Object { Write-Host "     - $_" }

if (Get-Command railway -ErrorAction SilentlyContinue) {
    Write-Host "`n   Railway CLI status:"
    railway whoami 2>&1
    railway status 2>&1
} else {
    Write-Host "`n   Install Railway CLI: https://docs.railway.com/develop/cli" -ForegroundColor Yellow
}

Write-Host "`n4. Stripe webhooks (live mode)"
Write-Host "   KEEP:    $UnifiedUrl/api/v1/billing/webhook/ (or $UnifiedRailwayUrl/api/v1/billing/webhook/)"
Write-Host "   DISABLE: $LegacyUrl/api/billing/webhook"
Write-Host "   Dashboard: Developers -> Webhooks -> api-transfer-production -> Disable"
Write-Host "   CLI (needs secret key with webhook write):"
Write-Host "            stripe webhook_endpoints update we_1ThOh0RxznXvj6jhjt7jZ3nm --disabled=true --live -c"

Write-Host "`n5. After 48h quiet on legacy URL - delete api-transfer-production in Railway dashboard"

Write-Host "`n6. Local verify (from backend/):"
Write-Host "   python manage.py verify_cutover"
