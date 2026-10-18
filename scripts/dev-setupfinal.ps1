# dev-setup.ps1
# Windows-compatible startup script for StockerPro
# Docker Supabase + Backend + Frontend + Worker Process
param(
    [switch]$SkipCleanup,
    # Bypass the WSL egress guard (section 0b). Only for the case where egress is
    # genuinely unavailable but the stack is still wanted up; the backend will not
    # be able to start, so this is a diagnostic escape hatch, not a normal path.
    [switch]$SkipNetworkCheck
)

# Child processes (supabase CLI, docker) emit UTF-8. Without this the console's
# OEM code page (usually 437) renders their box-drawing output as mojibake
# such as "ΓöÇ".
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$ProjectRoot = $PSScriptRoot | Split-Path
$BackendDir = Join-Path $ProjectRoot "backend"
$WebDir = Join-Path $ProjectRoot "web"
$SupabaseDir = $ProjectRoot

# Containers the app cannot run without, mapped to their published host port.
$SupabaseRequiredContainers = [ordered]@{
    'supabase_kong_StockerPro'   = 54321
    'supabase_db_StockerPro'     = 54322
    'supabase_studio_StockerPro' = 54323
}
# Optional helper services. These can be switched off in supabase/config.toml,
# so they are only verified when the container actually exists - never required.
$SupabaseOptionalContainers = [ordered]@{
    'supabase_inbucket_StockerPro'  = 54324
    'supabase_analytics_StockerPro' = 54327
}
$SupabasePorts = @($SupabaseRequiredContainers.Values) + @($SupabaseOptionalContainers.Values)

# WSL-visible project path so the WSL commands below survive a repo move.
$ProjectRootWsl = $null
try { $ProjectRootWsl = (wsl -e wslpath -a "$ProjectRoot" 2>$null).Trim() } catch { }
if (-not $ProjectRootWsl) {
    $ProjectRootWsl = "/mnt/c/Project/StockerPro/StockerPro"
    Write-Host "   WARNING: could not resolve WSL path, falling back to $ProjectRootWsl" -ForegroundColor Yellow
}

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

function Get-FrontendProcessIds {
    # Identify only THIS project's dev server. The previous implementation
    # killed EVERY node.exe on the machine, which also took out the node-based
    # Supabase CLI, editor language servers and other projects' dev servers.
    $ids = @()
    foreach ($port in 3000, 3001) {
        $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        foreach ($c in $conns) {
            $p = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
            if ($p -and $p.ProcessName -eq 'node') { $ids += $p.Id }
        }
    }
    foreach ($proc in (Get-CimInstance Win32_Process -Filter "Name = 'node.exe'" -ErrorAction SilentlyContinue)) {
        if ($proc.CommandLine -and $proc.CommandLine -like "*$WebDir*") { $ids += [int]$proc.ProcessId }
    }
    return @($ids | Sort-Object -Unique)
}

function Stop-FrontendProcess {
    $ids = @(Get-FrontendProcessIds)
    foreach ($procId in $ids) {
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
    if ($ids.Count -gt 0) {
        Write-Host "   Frontend stopped ($($ids.Count) process(es))" -ForegroundColor Gray
    }
}

function Stop-WSLBackend {
    # Kill ALL WSL python processes from our venv via internal script
    wsl -e bash "$ProjectRootWsl/backend/scripts/stop_all.sh" 2>$null
    Start-Sleep -Seconds 2
    Write-Host "   WSL backend processes stopped" -ForegroundColor Gray
}

function Test-WslOutbound {
    # Does WSL itself have working egress? Probed from INSIDE the distro, because
    # the Windows host having internet says nothing about WSL - see section 0b.
    #
    # bash's /dev/tcp is a builtin, so this needs no interpreter, no PATH entry
    # and no network tooling installed in the distro. Two targets are tried so
    # that a network which blocks 1.1.1.1 is not mistaken for broken egress.
    param([int]$TimeoutSec = 6)
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    try {
        foreach ($target in '1.1.1.1', 'github.com') {
            wsl -e timeout $TimeoutSec bash -c "exec 3<>/dev/tcp/$target/443" 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { return $true }
        }
        return $false
    } finally {
        $ErrorActionPreference = $prevEap
    }
}

function Invoke-WslNetworkRepair {
    # Self-heal a stale host-side WSL network binding (mechanism: see
    # Write-WslNetworkRemedy). Removing an HNS network is admin-only, so the work
    # runs in an elevated child process and reports back through a JSON file.
    # The child's own verdict is never trusted: this process re-probes egress
    # itself before the caller is allowed to continue.
    $repairScript = Join-Path $PSScriptRoot "wsl-network-repair.ps1"
    if (-not (Test-Path $repairScript)) {
        Write-Host "   Repair script not found: $repairScript" -ForegroundColor Yellow
        return $false
    }
    $resultFile = Join-Path $env:TEMP "wsl-network-repair.json"
    Remove-Item $resultFile -Force -ErrorAction SilentlyContinue

    Write-Host "   Rebuilding the stale WSL network (one admin consent prompt)..." -ForegroundColor Yellow
    try {
        $proc = Start-Process powershell -Verb RunAs -PassThru -ArgumentList @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$repairScript`"",
            '-ResultFile', "`"$resultFile`""
        )
    } catch {
        # UAC declined, or elevation unavailable (e.g. a non-interactive session).
        Write-Host "   Could not elevate: $($_.Exception.Message)" -ForegroundColor Yellow
        return $false
    }

    if ($proc) {
        $proc.WaitForExit(240000) | Out-Null
    } else {
        # ShellExecute gave no process handle: bound the wait by polling instead.
        Start-Sleep -Seconds 60
    }

    if (Test-Path $resultFile) {
        try {
            $r = Get-Content $resultFile -Raw | ConvertFrom-Json
            $removed = if ($r.RemovedNetworks) { @($r.RemovedNetworks) -join ', ' } else { '(none)' }
            Write-Host "   Repair child: removed [$removed], hns running=$($r.HnsRestarted), attempts=$($r.Attempts), egress=$($r.EgressOk)" -ForegroundColor Gray
        } catch {
            Write-Host "   Repair child: result file unreadable ($($_.Exception.Message))" -ForegroundColor Yellow
        }
    }

    # Independent, bounded verification of the outcome.
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        if (Test-WslOutbound) { return $true }
        Start-Sleep -Seconds 5
    }
    return $false
}

function Write-WslNetworkRemedy {
    Write-Host ""
    Write-Host "   ROOT CAUSE: WSL cannot reach the internet - the host-side WSL network" -ForegroundColor Red
    Write-Host "   binding is stale." -ForegroundColor Red
    Write-Host ""
    Write-Host "   WSL2 reaches the internet through an HNS network whose address translation" -ForegroundColor Red
    Write-Host "   is performed on Windows. When that network object goes stale, Windows still" -ForegroundColor Red
    Write-Host "   RECEIVES the guest's packets on 'vEthernet (WSL ...)' but forwards none of" -ForegroundColor Red
    Write-Host "   them to the physical adapter (measured on this machine: 300 of 300" -ForegroundColor Red
    Write-Host "   datagrams received, Wi-Fi transmit unchanged, loopback control = 0)." -ForegroundColor Red
    Write-Host "   The symptom is deceptive: the guest interface is up with a correct default" -ForegroundColor Red
    Write-Host "   route, the gateway ARP resolves, DNS still answers (it tunnels over vsock," -ForegroundColor Red
    Write-Host "   not the network) and the Windows host itself stays online." -ForegroundColor Red
    Write-Host ""
    Write-Host "   This blocks the backend, it does not merely degrade it: importing" -ForegroundColor Red
    Write-Host "   defeatbeta_api calls nltk.download() and HuggingFace at import time with" -ForegroundColor Red
    Write-Host "   no timeout, so uvicorn hangs and never binds :8001 - the frontend then" -ForegroundColor Red
    Write-Host "   502s on every /api/proxy/* call." -ForegroundColor Red
    Write-Host ""
    Write-Host "   Fix (a reboot also clears it and needs none of this):" -ForegroundColor Yellow
    Write-Host "     wsl --shutdown" -ForegroundColor Yellow
    Write-Host "     # elevated - drop the stale object, then let WSL rebuild the network:" -ForegroundColor Yellow
    Write-Host "     Get-HnsNetwork | Where-Object Name -like 'WSL*' | Remove-HnsNetwork" -ForegroundColor Yellow
    Write-Host "     Restart-Service hns -Force" -ForegroundColor Yellow
    Write-Host "     wsl -e true" -ForegroundColor Yellow
    Write-Host "   Or run: scripts\wsl-network-repair.ps1   (elevated; does all of the above)" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "   NOTE: 'net stop winnat; net start winnat; wsl --shutdown' does NOT fix this." -ForegroundColor DarkYellow
    Write-Host "   It was tried on this machine and measured failing: wsl --shutdown re-uses" -ForegroundColor DarkYellow
    Write-Host "   the stale network object, so it must be REMOVED, not merely bounced." -ForegroundColor DarkYellow
    Write-Host ""
    Write-Host "   To skip this guard: -SkipNetworkCheck" -ForegroundColor Yellow
    Write-Host ""
}

function Get-ExcludedTcpRanges {
    # Windows reserves chunks of the dynamic TCP range (49152-65535) for
    # Hyper-V/WinNAT. A port inside such a reservation cannot be bound: Docker
    # fails with WSAEACCES ("An attempt was made to access a socket in a way
    # forbidden by its access permissions") and silently publishes no host
    # port. Ranges marked '*' are administered exclusions and ARE bindable,
    # so they are not treated as blocking.
    $ranges = @()
    foreach ($line in (netsh int ipv4 show excludedportrange protocol=tcp 2>$null)) {
        if ($line -match '^\s*(\d+)\s+(\d+)\s*(\*?)\s*$') {
            $ranges += [pscustomobject]@{
                Start        = [int]$Matches[1]
                End          = [int]$Matches[2]
                Administered = ($Matches[3] -eq '*')
            }
        }
    }
    return $ranges
}

function Get-ReservedSupabasePorts {
    param([int[]]$Ports = $SupabasePorts)
    $ranges = Get-ExcludedTcpRanges
    $blocked = @()
    foreach ($p in $Ports) {
        foreach ($r in $ranges) {
            if ($p -ge $r.Start -and $p -le $r.End) {
                if (-not $r.Administered) {
                    $blocked += [pscustomobject]@{ Port = $p; Start = $r.Start; End = $r.End }
                }
                break
            }
        }
    }
    return $blocked
}

function Write-PortReservationRemedy {
    param([object[]]$Blocked)
    Write-Host ""
    Write-Host "   ROOT CAUSE: Windows has reserved these TCP port(s) for Hyper-V/WinNAT:" -ForegroundColor Red
    foreach ($b in $Blocked) {
        Write-Host ("     {0}  (inside reserved range {1}-{2})" -f $b.Port, $b.Start, $b.End) -ForegroundColor Red
    }
    Write-Host "   Docker cannot publish a reserved port (bind fails with WSAEACCES)," -ForegroundColor Red
    Write-Host "   so Supabase starts 'healthy' but with no host port => Connection refused." -ForegroundColor Red
    Write-Host ""
    Write-Host "   Fix - run these in an ELEVATED PowerShell, then re-run this script:" -ForegroundColor Yellow
    Write-Host "     net stop winnat" -ForegroundColor Yellow
    Write-Host "     netsh int ipv4 add excludedportrange protocol=tcp startport=54320 numberofports=100 store=persistent" -ForegroundColor Yellow
    Write-Host "     net start winnat" -ForegroundColor Yellow
    Write-Host "     docker restart supabase_kong_StockerPro supabase_db_StockerPro supabase_studio_StockerPro supabase_inbucket_StockerPro supabase_analytics_StockerPro" -ForegroundColor Yellow
    Write-Host ""
}

function Get-SupabaseContainerState {
    # Map of container name -> Docker State (e.g. 'running', 'exited').
    # One docker call, so it is cheap to reuse.
    $state = @{}
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    try {
        foreach ($line in (& docker ps -a --format "{{.Names}}|{{.State}}" 2>$null)) {
            $parts = "$line" -split '\|'
            if ($parts.Count -eq 2) { $state[$parts[0].Trim()] = $parts[1].Trim() }
        }
    } finally {
        $ErrorActionPreference = $prevEap
    }
    return $state
}

function Test-ContainerPortPublished {
    param([string]$Name, [int]$Port)
    # A published host port shows up as e.g. "0.0.0.0:54321" in `docker port`.
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    try {
        $bound = (& docker port $Name 2>$null | Out-String)
    } finally {
        $ErrorActionPreference = $prevEap
    }
    return ($bound -match ("0\.0\.0\.0:" + $Port + "\b"))
}

function Test-SupabaseStackUp {
    # "Up" means every required container is running. Deliberately independent of
    # published ports: a running-but-portless stack is reported by the assertion
    # below rather than silently re-started (running `supabase start` cannot fix
    # a Windows port reservation anyway).
    $state = Get-SupabaseContainerState
    foreach ($name in $SupabaseRequiredContainers.Keys) {
        if ($state[$name] -ne 'running') { return $false }
    }
    return $true
}

function Get-UnpublishedSupabasePorts {
    # `supabase start` can exit 0 while Docker silently fails to bind every
    # host port, so assert the bindings instead of trusting the exit code.
    # `docker port <missing>` raises a NativeCommandError, so guard the calls.
    $missing = @()
    $state = Get-SupabaseContainerState
    foreach ($name in $SupabaseRequiredContainers.Keys) {
        if (-not (Test-ContainerPortPublished -Name $name -Port $SupabaseRequiredContainers[$name])) {
            $missing += $SupabaseRequiredContainers[$name]
        }
    }
    foreach ($name in $SupabaseOptionalContainers.Keys) {
        # Optional service: only enforce the binding when the container exists.
        if ($state.ContainsKey($name) -and
            -not (Test-ContainerPortPublished -Name $name -Port $SupabaseOptionalContainers[$name])) {
            $missing += $SupabaseOptionalContainers[$name]
        }
    }
    return @($missing)
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "          StockerPro Dev Setup (Local Supabase Mode)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Cleanup phase
if (-not $SkipCleanup) {
    Write-Host "Cleaning up ports 3000 and 8001..." -ForegroundColor Cyan
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

# ── 0. Preflight guard: Windows reserved port ranges ────────────────────
# Docker Desktop binds the Supabase host ports on Windows. If Windows has
# reserved them for Hyper-V/WinNAT the bind fails silently, Supabase comes up
# "healthy" and the backend only ever sees ECONNREFUSED. Fail loudly instead.
Write-Host "Checking Windows reserved port ranges..." -ForegroundColor Green
$reservedSupabasePorts = Get-ReservedSupabasePorts
if ($reservedSupabasePorts.Count -gt 0) {
    Write-PortReservationRemedy -Blocked $reservedSupabasePorts
    exit 1
}
Write-Host "   No conflicting reservations for $($SupabasePorts -join ', ')" -ForegroundColor Gray
Write-Host ""

# ── 0b. WSL egress guard ────────────────────────────────────────────────
# See Write-WslNetworkRemedy() for the mechanism. Checked here, before Docker or
# Supabase are touched, so a stale WinNAT binding is reported in ~8s instead of
# surfacing minutes later as a backend that never binds and a 502-ing frontend.
if ($SkipNetworkCheck) {
    Write-Host "WSL connectivity check skipped (-SkipNetworkCheck)" -ForegroundColor Yellow
    Write-Host ""
} else {
    Write-Host "Checking WSL outbound connectivity..." -ForegroundColor Green
    if (Test-WslOutbound) {
        Write-Host "   WSL can reach the internet" -ForegroundColor Gray
        Write-Host ""
    } else {
        Write-Host "   WSL cannot reach the internet." -ForegroundColor Red
        if (Invoke-WslNetworkRepair) {
            Write-Host "   Repaired - WSL can reach the internet again." -ForegroundColor Green
            Write-Host "   The guest got a NEW address and the vEthernet was rebuilt; nothing may" -ForegroundColor Gray
            Write-Host "   cache the old WSL IP (BACKEND_ORIGIN is pinned to 127.0.0.1 below)." -ForegroundColor Gray
            Write-Host ""
        } else {
            Write-WslNetworkRemedy
            exit 1
        }
    }
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
# Decide from Docker's own state, not from CLI text. `supabase status` prints a
# human-readable table to a console but JSON when piped, so matching on its
# output is fragile. If Docker has already published every host port, the stack
# is up and `supabase start` must not be run.
if (Test-SupabaseStackUp) {
    Write-Host "   Supabase already running" -ForegroundColor Gray
} else {
    # Render native stderr as plain lines so a benign CLI notice ("already
    # running", "Stopped services") is not shown as a NativeCommandError block.
    & $supabaseCli start 2>&1 | ForEach-Object { "$_" } | Out-Host
}
Pop-Location

# Verify the host ports are REALLY published. `supabase start` can exit 0
# while Docker silently fails to bind every port (see guard section 0).
$unpublished = Get-UnpublishedSupabasePorts
if ($unpublished.Count -gt 0) {
    Write-Host "   ERROR: Supabase host port(s) not published: $($unpublished -join ', ')" -ForegroundColor Red
    $reservedSupabasePorts = Get-ReservedSupabasePorts -Ports $unpublished
    if ($reservedSupabasePorts.Count -gt 0) {
        Write-PortReservationRemedy -Blocked $reservedSupabasePorts
    } else {
        Write-Host "   No Windows reservation found for those ports." -ForegroundColor Yellow
        Write-Host "   Inspect: docker ps --filter label=com.supabase.cli.project=StockerPro" -ForegroundColor Yellow
    }
    exit 1
}
Write-Host "   Supabase published on $($SupabasePorts -join ', ')" -ForegroundColor Gray

# ── 2b. Point the frontend proxy at the backend via loopback ────────────
# The WSL IP is NOT stable - it is re-assigned on every WSL restart, and it does
# not exist at all under mirrored networking - so it must never be baked into
# config. Windows reaches WSL services through WSL's localhost forwarding
# (localhostForwarding=true), which survives restarts. 127.0.0.1 rather than
# "localhost": the relay binds IPv4 only, and Node may try ::1 first.
$envLocal = Join-Path $WebDir ".env.local"
$backendOrigin = "http://127.0.0.1:8001"
if (Test-Path $envLocal) {
    $content = Get-Content $envLocal -Raw
    if ($content -match [regex]::Escape("BACKEND_ORIGIN=$backendOrigin")) {
        Write-Host "   BACKEND_ORIGIN already $backendOrigin" -ForegroundColor Gray
    } elseif ($content -match 'BACKEND_ORIGIN=http://') {
        $content = $content -replace "BACKEND_ORIGIN=http://[^\r\n]+", "BACKEND_ORIGIN=$backendOrigin"
        Set-Content -Path $envLocal -Value $content -NoNewline -Encoding UTF8
        Write-Host "   BACKEND_ORIGIN set to $backendOrigin" -ForegroundColor Gray
    } else {
        Add-Content -Path $envLocal -Value "BACKEND_ORIGIN=$backendOrigin"
        Write-Host "   BACKEND_ORIGIN added as $backendOrigin" -ForegroundColor Gray
    }
} else {
    Write-Host "   WARNING: $envLocal not found - frontend proxy origin not set" -ForegroundColor Yellow
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
    $reservedSupabasePorts = Get-ReservedSupabasePorts
    if ($reservedSupabasePorts.Count -gt 0) {
        Write-PortReservationRemedy -Blocked $reservedSupabasePorts
    } else {
        Write-Host "   Ports are published and not reserved, so this is a Kong-level fault." -ForegroundColor Yellow
        Write-Host "   Try: supabase stop; supabase start" -ForegroundColor Yellow
        Write-Host "   Logs: docker logs supabase_kong_StockerPro" -ForegroundColor Yellow
    }
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

Start-Process wsl -ArgumentList "-e bash -c `"cd $ProjectRootWsl/backend && /home/rajesh/venv_stockerpro/bin/python scheduler_worker.py`"" -WindowStyle Normal
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

# Readiness gate. Launched with -NoNewWindow so it reports into THIS console.
# uvicorn runs in the foreground below, so without this the script cannot tell
# "serving" apart from "hung in an import-time network call".
$healthWatch = $null
$healthScript = Join-Path $PSScriptRoot "backend-health-watch.ps1"
if (Test-Path $healthScript) {
    $healthWatch = Start-Process powershell -NoNewWindow -PassThru -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$healthScript`"",
        '-Url', 'http://127.0.0.1:8001/health', '-TimeoutSec', '90'
    )
} else {
    Write-Host "   WARNING: $healthScript not found - backend readiness will not be reported" -ForegroundColor Yellow
}

# Run uvicorn in WSL foreground — keeps terminal alive, Ctrl+C stops everything
wsl -e bash "$ProjectRootWsl/backend/scripts/start_backend.sh"

# If we reach here, backend exited
if ($healthWatch -and -not $healthWatch.HasExited) {
    Stop-Process -Id $healthWatch.Id -Force -ErrorAction SilentlyContinue
}
Write-Host ""
Write-Host "Backend stopped." -ForegroundColor Yellow
Write-Host "Cleaning up frontend and worker..." -ForegroundColor Yellow
Stop-FrontendProcess
Stop-WSLBackend

Write-Host "Done." -ForegroundColor Gray
