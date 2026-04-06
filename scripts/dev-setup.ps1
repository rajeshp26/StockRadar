# dev-setup.ps1
# Windows-compatible startup script for StockerPro

$ProjectRoot = Get-Location
$BackendDir = Join-Path $ProjectRoot "backend"
$WebDir = Join-Path $ProjectRoot "web"

Write-Host "🧹 Cleaning up ports 3000 and 8001..." -ForegroundColor Cyan

# Port cleanup logic
function Stop-ProcessOnPort($port) {
    $process = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    if ($process) {
        $procId = $process.OwningProcess[0]
        Write-Host "   Stopping process $procId on port $port..." -ForegroundColor Yellow
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
}

Stop-ProcessOnPort 3000
Stop-ProcessOnPort 8001

Write-Host "⏳ Waiting for ports to be released..." -ForegroundColor Cyan
Start-Sleep -Seconds 2

Write-Host "🚀 Starting Backend on port 8001..." -ForegroundColor Green
$BackendCommand = {
    param($root)
    cd "$root\backend"
    $env:PYTHONPATH = "$root\backend;$root"
    backend\venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload
}

Start-Job -ScriptBlock $BackendCommand -ArgumentList $ProjectRoot -Name "StockerProBackend" | Out-Null

Write-Host "⏳ Waiting for backend to initialize..." -ForegroundColor Cyan
Start-Sleep -Seconds 4

Write-Host "🚀 Starting Frontend on port 3000..." -ForegroundColor Green
cd $WebDir
$env:PORT = 3000
npm run dev

# After the user stops the frontend (Ctrl+C), we should stop the backend job
Stop-Job -Name "StockerProBackend"
Remove-Job -Name "StockerProBackend"
Write-Host "🛑 Backend job stopped." -ForegroundColor Red
