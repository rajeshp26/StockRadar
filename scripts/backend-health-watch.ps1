# backend-health-watch.ps1
# Readiness gate for the StockerPro backend.
#
# dev-setupfinal.ps1 launches uvicorn in the foreground, so by default the only
# thing it can observe is "uvicorn was launched". That is not the same as "the
# backend is serving". Importing defeatbeta_api performs unbounded network I/O
# at import time (nltk.download plus a HuggingFace request, neither with a
# timeout), so with no egress the process hangs and never binds :8001 - and the
# frontend then 502s on every /api/proxy/* call with no explanation.
#
# This script is launched with -NoNewWindow so its output lands in the same
# console as the setup script. It polls the backend's own /health endpoint,
# reports the outcome, and exits. It never blocks startup; it only reports.
param(
    [string]$Url = 'http://127.0.0.1:8001/health',
    [int]$TimeoutSec = 90
)

$deadline = (Get-Date).AddSeconds($TimeoutSec)

while ((Get-Date) -lt $deadline) {
    try {
        $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        if ($resp.StatusCode -eq 200) {
            Write-Host ""
            Write-Host "   Backend READY: $Url returned HTTP 200" -ForegroundColor Green
            exit 0
        }
    } catch { }
    Start-Sleep -Seconds 2
}

Write-Host ""
Write-Host "   Backend NOT READY after ${TimeoutSec}s: $Url never answered." -ForegroundColor Red
Write-Host "   The process is most likely stuck in an import-time network call" -ForegroundColor Yellow
Write-Host "   (defeatbeta_api). Check the backend output above for its last line." -ForegroundColor Yellow
exit 1
