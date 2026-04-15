# dev-setup.ps1
# Windows-compatible startup script for StockerPro
# Frontend in new terminal, Backend in current terminal with full logs

param(
    [switch]$SkipCleanup
)

$ProjectRoot = $PSScriptRoot | Split-Path
$BackendDir = Join-Path $ProjectRoot "backend"
$WebDir = Join-Path $ProjectRoot "web"

function Stop-ProcessOnPort {
    param([int]$Port)
    $conn = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if ($conn) {
        $procId = $conn[0].OwningProcess
        Write-Host "   Stopping process $procId on port $Port..." -ForegroundColor Yellow
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 500
    }
}

function Stop-FrontendProcess {
    $nodeProcesses = Get-Process -Name "node" -ErrorAction SilentlyContinue
    if ($nodeProcesses) {
        foreach ($proc in $nodeProcesses) {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
        Write-Host "   Frontend stopped" -ForegroundColor Gray
    }
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "                    StockerPro Dev Setup" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Cleanup phase
if (-not $SkipCleanup) {
    Write-Host "Cleaning up ports 3000, 8001..." -ForegroundColor Cyan
    Stop-ProcessOnPort -Port 3000
    Stop-ProcessOnPort -Port 8001
    Write-Host "   Cleaning up WSL processes..." -ForegroundColor Yellow
    wsl bash -c "pkill -f uvicorn 2>/dev/null; pkill -f 'python.*main:app' 2>/dev/null; sleep 1"
    Write-Host "   Done" -ForegroundColor Gray
    Write-Host ""
}

# Start frontend in new terminal
Write-Host "Starting Frontend on port 3000..." -ForegroundColor Green
Write-Host "   (Opens in a new terminal window)" -ForegroundColor Gray

Start-Process powershell -ArgumentList "-NoExit -Command `"cd '$WebDir'; npm run dev -- -p 3000`"" -WindowStyle Normal

Write-Host "Frontend: [OK] RUNNING on http://localhost:3000" -ForegroundColor Green
Write-Host ""

# Wait for frontend to initialize
Write-Host "Waiting for frontend to initialize..." -ForegroundColor Cyan
Start-Sleep -Seconds 3

# ── Backend — runs in WSL (Linux) so DefeatBeta works ────────────────────────
Write-Host ""
Write-Host "Starting Backend on port 8001 (via WSL)..." -ForegroundColor Green
Write-Host ("-" * 50)
Write-Host ""

# Convert Windows path to WSL path reliably
# C:\Project\StockerPro\StockerPro\backend -> /mnt/c/Project/StockerPro/StockerPro/backend
$DriveLetter = $BackendDir.Substring(0, 1).ToLower()
$PathWithoutDrive = $BackendDir.Substring(2).Replace("\", "/")
$WslBackendDir = "/mnt/$DriveLetter$PathWithoutDrive"

$WslCommand = "source ~/venv_stockerpro/bin/activate && cd '$WslBackendDir' && export PYTHONPATH='$WslBackendDir/..:$WslBackendDir' && uvicorn main:app --host 0.0.0.0 --port 8001 --reload"

# Run backend in current terminal via WSL (blocking — all logs visible here)
wsl bash -c $WslCommand

# If we reach here, backend exited
Write-Host ""
Write-Host "Backend stopped." -ForegroundColor Yellow
Write-Host "Cleaning up frontend..." -ForegroundColor Yellow
Stop-FrontendProcess
Write-Host "Done." -ForegroundColor Gray