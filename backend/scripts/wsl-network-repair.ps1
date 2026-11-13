# wsl-network-repair.ps1
# Rebuild the host-side WSL2 network binding. RUNS ELEVATED (HNS operations are
# admin-only); dev-setupfinal.ps1 launches it only after its egress probe fails.
#
# Measured failure this repairs (Windows 11 25H2, WSL 2.6.x, NAT networking):
#   The guest is healthy - eth0 up, correct default route, gateway ARP resolves,
#   DNS answers (it tunnels over vsock), the host has internet - yet Windows
#   receives the guest's packets on vEthernet (WSL ...) and forwards none of them
#   out the physical adapter (NIC counters: Rx +300/300, Wi-Fi Tx unchanged;
#   loopback control reads 0). Host-side evidence at the same time: Get-NetNat is
#   empty and IPv4 forwarding is Disabled on the WSL vEthernet, while HNS still
#   reports the old ICS network. The persisted HNS network object is stale, so
#   `wsl --shutdown` alone re-uses it and changes nothing.
#
# Repair: drop the stale network object, restart HNS, let WSL rebuild the
# network, then poll egress until it answers. Bounded: two attempts, never open
# ended.

[CmdletBinding()]
param(
    # Structured outcome for the caller (JSON). The caller re-verifies egress
    # itself and must not trust this file alone.
    [string]$ResultFile = (Join-Path $env:TEMP 'wsl-network-repair.json'),
    # Per-attempt polling window after WSL has been started.
    [int]$AttemptSeconds = 30,
    [int]$ProbeTimeoutSec = 6
)

$ErrorActionPreference = 'Continue'

$result = [ordered]@{
    StartedUtc      = (Get-Date).ToUniversalTime().ToString('o')
    IsElevated      = $false
    WslVersion      = $null
    BeforeNetworks  = @()
    RemovedNetworks = @()
    RemoveErrors    = @()
    HnsRestarted    = $false
    Attempts        = 0
    EgressOk        = $false
    AfterNetworks   = @()
    Error           = $null
}

function Test-Elevated {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    return ([Security.Principal.WindowsPrincipal]$id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# Raw TCP to a public address from inside WSL. Independent of DNS on purpose:
# DNS keeps working through a vsock tunnel even while egress is dead, so a DNS
# success would prove nothing.
function Test-WslEgress {
    param([int]$TimeoutSec = 6)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    try {
        foreach ($target in '1.1.1.1', 'github.com') {
            & wsl.exe -e timeout $TimeoutSec bash -c "exec 3<>/dev/tcp/$target/443" 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { return $true }
        }
        return $false
    } finally { $ErrorActionPreference = $prev }
}

function Save-Result {
    try {
        $result | ConvertTo-Json -Depth 4 | Set-Content -Path $ResultFile -Encoding UTF8
    } catch {
        Write-Host ("   (could not write $ResultFile : " + $_.Exception.Message + ")") -ForegroundColor Yellow
    }
}

$result.IsElevated = Test-Elevated
if (-not $result.IsElevated) {
    $result.Error = 'not elevated'
    Save-Result
    Write-Host "ERROR: this script must run elevated (HNS network removal is admin-only)." -ForegroundColor Red
    exit 2
}

$result.WslVersion = ((& wsl.exe --version 2>&1 | Out-String) -replace '\s+', ' ').Trim()

Write-Host "=== stale WSL network before repair ===" -ForegroundColor Cyan
$before = @(Get-HnsNetwork -ErrorAction SilentlyContinue | Where-Object { $_.Name -like 'WSL*' })
$result.BeforeNetworks = @($before | ForEach-Object { "$($_.Name) [$($_.Type)]" })
if ($before.Count -eq 0) { Write-Host "   (no WSL HNS network present)" } else { $before | Format-Table Name, Type -AutoSize | Out-String | Write-Host }

# The network cannot be removed while the VM holds it.
Write-Host "wsl --shutdown" -ForegroundColor Cyan
& wsl.exe --shutdown 2>$null | Out-Null
Start-Sleep -Seconds 4

foreach ($n in $before) {
    Write-Host ("removing HNS network: {0} ({1})" -f $n.Name, $n.Type) -ForegroundColor Cyan
    try {
        $n | Remove-HnsNetwork -ErrorAction Stop
        $result.RemovedNetworks += $n.Name
        Write-Host "   removed" -ForegroundColor Gray
    } catch {
        $result.RemoveErrors += "$($n.Name): $($_.Exception.Message)"
        Write-Host ("   remove failed: " + $_.Exception.Message) -ForegroundColor Yellow
    }
}

Write-Host "Restart-Service hns" -ForegroundColor Cyan
Restart-Service hns -Force -ErrorAction SilentlyContinue
Start-Service hns -ErrorAction SilentlyContinue
Start-Sleep -Seconds 5
$result.HnsRestarted = ((Get-Service hns -ErrorAction SilentlyContinue).Status -eq 'Running')
Write-Host ("   hns status: " + (Get-Service hns -ErrorAction SilentlyContinue).Status) -ForegroundColor Gray

# Let WSL rebuild the network, then poll for real egress. Two bounded attempts:
# a rebuild sometimes needs a second VM start before the switch port carries.
$deadlineTotal = 2
for ($attempt = 1; $attempt -le $deadlineTotal; $attempt++) {
    $result.Attempts = $attempt
    Write-Host ("starting WSL to rebuild the network (attempt $attempt)") -ForegroundColor Cyan
    & wsl.exe -e true 2>$null | Out-Null

    $deadline = (Get-Date).AddSeconds($AttemptSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-WslEgress -TimeoutSec $ProbeTimeoutSec) {
            $result.EgressOk = $true
            break
        }
        Start-Sleep -Seconds 3
    }
    if ($result.EgressOk) { break }

    Write-Host "   egress still failing; forcing a clean VM restart" -ForegroundColor Yellow
    & wsl.exe --shutdown 2>$null | Out-Null
    Start-Sleep -Seconds 4
}

$result.AfterNetworks = @(Get-HnsNetwork -ErrorAction SilentlyContinue | Where-Object { $_.Name -like 'WSL*' } | ForEach-Object { "$($_.Name) [$($_.Type)]" })
Save-Result

Write-Host "=== after repair ===" -ForegroundColor Cyan
@($result.AfterNetworks) | ForEach-Object { Write-Host ("   " + $_) }
if ($result.EgressOk) {
    Write-Host "   egress: OK" -ForegroundColor Green
    exit 0
}
Write-Host "   egress: STILL BROKEN - a reboot is the remaining remedy" -ForegroundColor Red
exit 1