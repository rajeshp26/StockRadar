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
    $nodeProcesses = Get-Process -Name "node" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*next*" }
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

# Start backend in current terminal (blocking - all logs visible)
Write-Host ""
Write-Host "Starting Backend on port 8001..." -ForegroundColor Green
Write-Host ("-" * 50)
Write-Host ""

$venvPython = Join-Path $BackendDir "venv\Scripts\python.exe"
$env:PYTHONPATH = "$ProjectRoot;$BackendDir"

# Run backend in current terminal (blocking)
& $venvPython -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload

# If we reach here, backend exited
Write-Host ""
Write-Host "Backend stopped." -ForegroundColor Yellow
Write-Host "Cleaning up frontend..." -ForegroundColor Yellow
Stop-FrontendProcess
Write-Host "Done." -ForegroundColor Gray