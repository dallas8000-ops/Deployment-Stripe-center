# Start backend + frontend (Windows — two windows)
$Root = Split-Path $PSScriptRoot -Parent
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"

if (-not (Test-Path (Join-Path $Backend ".venv\Scripts\daphne.exe"))) {
    Write-Host "Run .\scripts\setup.ps1 first" -ForegroundColor Red
    exit 1
}

Write-Host "Starting backend on :8000 and frontend on :5173..." -ForegroundColor Cyan

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$Backend'; .\.venv\Scripts\daphne.exe -b 127.0.0.1 -p 8000 config.asgi:application"
)

Start-Sleep -Seconds 2

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$Frontend'; npm run dev"
)

Write-Host "Open http://localhost:5173" -ForegroundColor Green
