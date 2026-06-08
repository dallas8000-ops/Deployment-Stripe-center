# Stop stale Stripe Installer dev servers (ports 8000, 5173–5175)
$ErrorActionPreference = "SilentlyContinue"
$ports = 8000, 5173, 5174, 5175

Write-Host "Stopping dev servers on ports $($ports -join ', ')..." -ForegroundColor Cyan

foreach ($port in $ports) {
    $conns = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
    if (-not $conns.Count) { continue }
    $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $pids) {
        if ($procId -and $procId -ne 0) {
            $name = (Get-Process -Id $procId -ErrorAction SilentlyContinue).ProcessName
            Write-Host "  :$port -> PID $procId ($name)"
            Stop-Process -Id $procId -Force
        }
    }
}

Write-Host "Done. Run: npm run dev" -ForegroundColor Green
