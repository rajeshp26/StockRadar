# dev-setup.ps1
# Windows-compatible startup script for StockerPro
# Docker Supabase + Backend + Frontend + Worker Process
param(
    [switch]$SkipCleanup
)

$ProjectRoot = $PSScriptRoot | Split-Path
$BackendDir = Join-Path $ProjectRoot "backend"
$WebDir = Join-Path $ProjectRoot "web"
$SupabaseDir = $ProjectRoot

function Stop-ProcessOnPort {
    param([int]$Port)
    $conn = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if ($conn) {
        $procId = $conn[0].OwningProcess
        Write-Host "   Stopping process $procId on port $Port..." -ForegroundColor Yellow
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
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

function Stop-WSLBackend {
    # Kill ALL WSL python processes from our venv via internal script
    wsl -e bash /mnt/c/Project/StockerPro/StockerPro/backend/scripts/stop_all.sh 2>$null
    Start-Sleep -Seconds 2
    Write-Host "   WSL backend processes stopped" -ForegroundColor Gray
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "          StockerPro Dev Setup (Local Supabase Mode)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Cleanup phase
if (-not $SkipCleanup) {
    Write-Host "Cleaning up ports 3000, 8001, 54321-54323..." -ForegroundColor Cyan
    Stop-ProcessOnPort -Port 3000
    Stop-WSLBackend
    Stop-ProcessOnPort -Port 8001
    # Wait for ports to be released
    $waited = 0
    while ($waited -lt 10) {
        $inUse = Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue
        if (-not $inUse) { break }
        Start-Sleep -Seconds 1
        $waited++
    }
    if ($waited -ge 10) {
        Write-Host "   WARNING: Port 8001 still in use after cleanup" -ForegroundColor Yellow
    }
    Write-Host "   Done" -ForegroundColor Gray
    Write-Host ""
}

# ── 1. Add Docker to PATH and start Docker Desktop ─────────────────────
$dockerBin = "C:\Program Files\Docker\Docker\resources\bin"
$dockerPath = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
# Set PATH for current process AND child processes
if ($env:PATH -notlike "*$dockerBin*") {
    $env:PATH = "$dockerBin;$env:PATH"
    [System.Environment]::SetEnvironmentVariable("PATH", $env:PATH, "Process")
}

Write-Host "Starting Docker Desktop..." -ForegroundColor Green
if (Test-Path $dockerPath) {
    $dockerProc = Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue
    if (-not $dockerProc) {
        Start-Process $dockerPath
        Write-Host "   Waiting for Docker to start..." -ForegroundColor Yellow
        Start-Sleep -Seconds 15
        # Wait for Docker engine to be ready
        $retries = 0
        while ($retries -lt 20) {
            & docker info 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "   Docker ready" -ForegroundColor Gray
                break
            }
            Start-Sleep -Seconds 3
            $retries++
        }
    } else {
        Write-Host "   Docker already running" -ForegroundColor Gray
    }
} else {
    Write-Host "   Docker Desktop not found at $dockerPath" -ForegroundColor Red
    Write-Host "   Install: winget install Docker.DockerDesktop" -ForegroundColor Yellow
    exit 1
}

# ── 2. Start Supabase ──────────────────────────────────────────────────
Write-Host "Starting Supabase..." -ForegroundColor Green
$supabaseCli = Get-Command supabase -ErrorAction SilentlyContinue
if ($supabaseCli) {
    $supabaseCli = $supabaseCli.Source
} else {
    $supabaseCli = "$env:APPDATA\npm\supabase.cmd"
}

# Ensure Docker is visible to Supabase CLI's Node.js process
$env:PATH = "$dockerBin;$env:PATH"

Push-Location $SupabaseDir
$supabaseStatus = & $supabaseCli status 2>&1
$isRunning = $supabaseStatus -match "supabase.*running"
if (-not $isRunning) {
    & $supabaseCli start 2>&1 | Out-Host
    Write-Host "   Supabase started on localhost:54321" -ForegroundColor Gray
} else {
    Write-Host "   Supabase already running" -ForegroundColor Gray
}
Pop-Location

# ── 2b. Detect WSL IP and update BACKEND_ORIGIN ─────────────────────────
$wslIP = (wsl -e bash -c "hostname -I").Trim()
if ($wslIP) {
    $envLocal = Join-Path $WebDir ".env.local"
    $content = Get-Content $envLocal -Raw
    $newOrigin = "http://${wslIP}:8001"
    # Always update BACKEND_ORIGIN to current WSL IP
    $content = $content -replace "BACKEND_ORIGIN=http://[^\r\n]+", "BACKEND_ORIGIN=$newOrigin"
    Set-Content -Path $envLocal -Value $content -NoNewline -Encoding UTF8
    Write-Host "   BACKEND_ORIGIN set to $newOrigin" -ForegroundColor Gray
}

# ── 2c. Verify Kong is responding (auto-restart if broken) ───────────────
Write-Host "Verifying Kong gateway..." -ForegroundColor Green
$kongHealthy = $false
$kongRetries = 0
while ($kongRetries -lt 3) {
    try {
        $kongResp = Invoke-WebRequest -Uri "http://127.0.0.1:54321/auth/v1/health" -UseBasicParsing -TimeoutSec 5
        if ($kongResp.StatusCode -eq 200) {
            $kongHealthy = $true
            break
        }
    } catch { }
    # Kong not responding — restart it
    Write-Host "   Kong not responding, restarting..." -ForegroundColor Yellow
    & docker restart supabase_kong_StockerPro 2>&1 | Out-Null
    Start-Sleep -Seconds 8
    $kongRetries++
}
if ($kongHealthy) {
    Write-Host "   Kong healthy" -ForegroundColor Gray
} else {
    Write-Host "   WARNING: Kong still not responding after restart attempts" -ForegroundColor Red
    Write-Host "   Try: docker restart supabase_kong_StockerPro" -ForegroundColor Yellow
}

# ── 3. Start Frontend in new terminal ────────────────────────────────────
Write-Host "Starting Frontend on port 3000..." -ForegroundColor Green
Write-Host "   (Opens in Terminal Window #1)" -ForegroundColor Gray
Start-Process powershell -ArgumentList "-NoExit -Command `"cd '$WebDir'; npm run dev -- -p 3000`"" -WindowStyle Normal
Write-Host "Frontend: [OK] RUNNING on http://localhost:3000" -ForegroundColor Green
Write-Host ""

# Wait for frontend to initialize
Write-Host "Waiting for frontend to initialize..." -ForegroundColor Cyan
Start-Sleep -Seconds 3

# ── 4. Start Worker Process in WSL ──────────────────────────────────────
Write-Host "Starting Worker Process (Schedulers) via WSL..." -ForegroundColor Green
Write-Host "   (Opens in Terminal Window #2)" -ForegroundColor Gray

Start-Process wsl -ArgumentList "-e bash -c `"cd /mnt/c/Project/StockerPro/StockerPro/backend && /home/rajesh/venv_stockerpro/bin/python scheduler_worker.py`"" -WindowStyle Normal
Write-Host "Worker: [OK] RUNNING (schedulers in WSL background)" -ForegroundColor Green
Write-Host ""

# Wait for worker to initialize
Write-Host "Waiting for worker to initialize..." -ForegroundColor Cyan
Start-Sleep -Seconds 2

# ── 5. Start Backend in WSL (current terminal) ──────────────────────────
Write-Host ""
Write-Host "Starting Backend on port 8001 via WSL..." -ForegroundColor Green
Write-Host ("-" * 50)
Write-Host ""

# Run uvicorn in WSL foreground — keeps terminal alive, Ctrl+C stops everything
wsl -e bash /mnt/c/Project/StockerPro/StockerPro/backend/scripts/start_backend.sh

# If we reach here, backend exited
Write-Host ""
Write-Host "Backend stopped." -ForegroundColor Yellow
Write-Host "Cleaning up frontend and worker..." -ForegroundColor Yellow
Stop-FrontendProcess
Stop-WSLBackend

Write-Host "Done." -ForegroundColor Gray
