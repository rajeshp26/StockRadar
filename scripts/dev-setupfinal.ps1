# dev-setup.ps1
# Windows-compatible startup script for StockerPro
# Frontend, Backend, AND Worker Process in separate terminals
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

function Stop-PythonProcesses {
    # Stop any Python processes running schedulers or workers
    $pythonProcs = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like "*scheduler_worker*" -or 
        $_.CommandLine -like "*uvicorn*"
    }
    if ($pythonProcs) {
        foreach ($proc in $pythonProcs) {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
        Write-Host "   Python processes stopped" -ForegroundColor Gray
    }
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "          StockerPro Dev Setup (3-Process Mode)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Cleanup phase
if (-not $SkipCleanup) {
    Write-Host "Cleaning up ports 3000, 8001..." -ForegroundColor Cyan
    Stop-ProcessOnPort -Port 3000
    Stop-ProcessOnPort -Port 8001
    Stop-PythonProcesses
    
    Write-Host "   Cleaning up WSL processes..." -ForegroundColor Yellow
    wsl bash -c "pkill -f uvicorn 2>/dev/null; pkill -f 'python.*main:app' 2>/dev/null; pkill -f 'python.*scheduler_worker' 2>/dev/null; sleep 1"
    Write-Host "   Done" -ForegroundColor Gray
    Write-Host ""
}

# ── 1. Start Frontend in new terminal ────────────────────────────────────
Write-Host "Starting Frontend on port 3000..." -ForegroundColor Green
Write-Host "   (Opens in Terminal Window #1)" -ForegroundColor Gray
Start-Process powershell -ArgumentList "-NoExit -Command `"cd '$WebDir'; npm run dev -- -p 3000`"" -WindowStyle Normal
Write-Host "Frontend: [OK] RUNNING on http://localhost:3000" -ForegroundColor Green
Write-Host ""

# Wait for frontend to initialize
Write-Host "Waiting for frontend to initialize..." -ForegroundColor Cyan
Start-Sleep -Seconds 3

# ── 2. Start Worker Process in new terminal (NEW) ────────────────────────
Write-Host "Starting Worker Process (Schedulers)..." -ForegroundColor Green
Write-Host "   (Opens in Terminal Window #2)" -ForegroundColor Gray

# Convert Windows path to WSL path
$DriveLetter = $BackendDir.Substring(0, 1).ToLower()
$PathWithoutDrive = $BackendDir.Substring(2).Replace("\", "/")
$WslBackendDir = "/mnt/$DriveLetter$PathWithoutDrive"

$WorkerCommand = "wsl bash -c 'source ~/venv_stockerpro/bin/activate ; cd $WslBackendDir ; export PYTHONPATH=$WslBackendDir/..:$WslBackendDir ; python scheduler_worker.py'"

Start-Process powershell -ArgumentList "-NoExit -Command `"$WorkerCommand`"" -WindowStyle Normal
Write-Host "Worker: [OK] RUNNING (schedulers in background)" -ForegroundColor Green
Write-Host ""

# Wait for worker to initialize
Write-Host "Waiting for worker to initialize..." -ForegroundColor Cyan
Start-Sleep -Seconds 2

# ── 3. Start Backend in current terminal ─────────────────────────────────
Write-Host ""
Write-Host "Starting Backend on port 8001 (via WSL)..." -ForegroundColor Green
Write-Host ("-" * 50)
Write-Host ""

$BackendCommand = "source ~/venv_stockerpro/bin/activate ; cd '$WslBackendDir' ; export PYTHONPATH='$WslBackendDir/..:$WslBackendDir' ; uvicorn main:app --host 0.0.0.0 --port 8001 --reload"

# Run backend in current terminal via WSL (blocking — all logs visible here)
wsl bash -c $BackendCommand

# If we reach here, backend exited
Write-Host ""
Write-Host "Backend stopped." -ForegroundColor Yellow
Write-Host "Cleaning up frontend and worker..." -ForegroundColor Yellow
Stop-FrontendProcess
Stop-PythonProcesses

# Clean up WSL processes
wsl bash -c "pkill -f 'python.*scheduler_worker' 2>/dev/null"

Write-Host "Done." -ForegroundColor Gray