# split_framework_repo.ps1
# Phase C app carve - StockerPro framework-repo split (USER-EXECUTED).
#
# Converts this repo from the merged framework layout to the pinned-package
# dependency model: framework/, .lifecycle/ and the reference-app scaffold
# (src/, vite/playwright/tsconfig/components/index.html, framework docs) are
# removed; the thin binding (framework.config.json + migrated .framework/state)
# is written; the carve is committed in atomic per-step commits and tagged
# `post-split`.
#
# Plan: .omo/plans/framework-repo-split.md (Phase C). Locked decisions D1-D9.
#
# USAGE:
#   .\scripts\split_framework_repo.ps1            # dry run: print every step, change nothing
#   .\scripts\split_framework_repo.ps1 -Execute   # apply (each step commits atomically)
#
# Preconditions (asserted by step 1 in BOTH modes):
#   - clean working tree (the in-flight Phase 2 valuation files must be
#     committed or stashed first - `git status --porcelain` must be empty)
#   - `agentic-lifecycle` installed in the active python env from the pin
#     (pip install "agentic-lifecycle @ git+https://github.com/rajeshp26/agentic-lifecycle.git@v0.1.0")
#   - user-approved app `opencode.json`, `AGENTS.md`, `framework/opencode/plugin/bootstrap.ts`
#     are in place (asserted by step 5 markers below)
#
# The script NEVER authors plane files (opencode.json / AGENTS.md / .opencode/**):
# those are user-committed; step 5 only verifies their markers. It does not push.

param(
    [switch]$Execute
)

$ErrorActionPreference = 'Stop'
$Apply = [bool]$Execute
$ProjectRoot = $PSScriptRoot | Split-Path
$VerificationDir = Join-Path $ProjectRoot 'verification_output'

function Write-Step { param([string]$Msg) Write-Host ""; Write-Host "STEP  $Msg" -ForegroundColor Cyan }
function Write-Ok   { param([string]$Msg) Write-Host "  [PASS]  $Msg" -ForegroundColor Green }
function Write-Warn { param([string]$Msg) Write-Host "  [WARN]  $Msg" -ForegroundColor Yellow }
function Write-Fail { param([string]$Msg) Write-Host "  [FAIL]  $Msg" -ForegroundColor Red }

# Set-Utf8NoBom - PS 5.1's Set-Content -Encoding UTF8 writes a BOM, which would
# corrupt .gitignore first-line matching, JSON parsing, and Python sources.
# .NET WriteAllText with UTF8Encoding($false) writes UTF-8 without BOM.
function Set-Utf8NoBom {
    param([string]$Path, [string]$Content)
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

# Invoke-Check runs a read-only assertion in BOTH modes (dry-run still
# preflights; nothing mutates). Returns $true on success.
function Invoke-Check {
    param(
        [string]$Label,
        [scriptblock]$Body
    )
    try {
        $ok = & $Body
        if ($ok) { Write-Ok $Label; return $true }
        Write-Fail $Label
        return $false
    }
    catch {
        Write-Fail "$Label - $($_.Exception.Message)"
        return $false
    }
}

# Invoke-Step runs a mutating step only in -Execute mode. Dry-run prints what
# would happen. A failing step stops the carve (nothing half-applied is left).
function Invoke-Step {
    param(
        [string]$Label,
        [scriptblock]$Body
    )
    if (-not $Apply) {
        Write-Warn "[dry-run] would: $Label"
        return
    }
    Write-Step $Label
    try {
        & $Body
        Write-Ok $Label
    }
    catch {
        Write-Fail "$Label FAILED - $($_.Exception.Message)"
        Write-Host "Carve aborted. Re-run after resolving; completed steps are committed and reversible via git." -ForegroundColor Magenta
        exit 1
    }
}

function Get-Git {
    param([string[]]$Args)
    $out = & git -C $ProjectRoot @Args 2>&1
    return $out
}

function Commit-Atomic {
    param([string]$Message)
    if (-not $Apply) { return }
    $status = & git -C $ProjectRoot status --porcelain
    if ($LASTEXITCODE -ne 0) { throw "git status failed (exit $LASTEXITCODE)" }
    if ([string]::IsNullOrWhiteSpace($status)) {
        Write-Warn "no changes to commit for: $Message"
        return
    }
    & git -C $ProjectRoot add -A
    if ($LASTEXITCODE -ne 0) { throw "git add failed (exit $LASTEXITCODE)" }
    & git -C $ProjectRoot commit -m $Message
    if ($LASTEXITCODE -ne 0) { throw "git commit failed (exit $LASTEXITCODE)" }
    Write-Ok "committed: $Message"
}

# ---------------------------------------------------------------------------
# STEP 1 - Preflight (asserts in both modes; archives gate evidence only on apply)
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   Framework Repo Split - Phase C carve (StockerPro)" -ForegroundColor Cyan
Write-Host "   Mode: $(if ($Apply) { 'EXECUTE' } else { 'DRY RUN (no changes)' })" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

$preflightOk = $true

Write-Step "1. Preflight"

# 1a. clean working tree
if (-not (Invoke-Check "clean working tree" {
    $status = & git -C $ProjectRoot status --porcelain
    if ($LASTEXITCODE -ne 0) { return $false }
    if ([string]::IsNullOrWhiteSpace($status)) { return $true }
    Write-Host "       Dirty entries:"
    $status -split "`n" | ForEach-Object { if ($_.Trim()) { Write-Host "         $_" -ForegroundColor Yellow } }
    return $false
})) { $preflightOk = $false }

# 1b. framework package installed from the pin (distribution check, not import -
# the local framework/ dir would shadow an import pre-carve)
if (-not (Invoke-Check "agentic-lifecycle installed (pip show)" {
    $show = & python -m pip show agentic-lifecycle 2>&1
    if ($LASTEXITCODE -ne 0) { return $false }
    $v = $show | Select-String '^Version:'
    if ($v) { Write-Host "       $($v.Line.Trim())" }
    return $true
})) { $preflightOk = $false }

# 1c. working branch warning (not a block; carve is reversible per step)
$branch = (& git -C $ProjectRoot branch --show-current 2>&1)
if ($branch -and $branch.Trim() -eq 'main') {
    Write-Warn "on branch 'main' - consider a carve branch; every step is an atomic commit so this is safe, but a branch makes rollback trivially visible"
}

if (-not $preflightOk) {
    Write-Fail "preflight failed - resolve the items above (commit/stash the dirty tree, install the pinned package), then re-run"
    exit 1
}

# 1d. archive current gate evidence (apply mode only; heavy 41-suite validate)
if ($Apply) {
    Invoke-Step "archive pre-carve gate evidence to verification_output/" {
        if (-not (Test-Path $VerificationDir)) { New-Item -ItemType Directory -Path $VerificationDir -Force | Out-Null }
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        & python $ProjectRoot\framework\validate.py *> "$VerificationDir\split-pre-$stamp-validate.txt"
        $vc = $LASTEXITCODE
        & python $ProjectRoot\framework\security\check_enforcement_plane.py *> "$VerificationDir\split-pre-$stamp-plane.txt"
        $pc = $LASTEXITCODE
        Write-Ok "validate.py exit $vc (baseline - recorded, not enforced)"
        Write-Warn "check_enforcement_plane exit $pc (RED expected pre-carve: framework/** in app plane) - recorded as known pre-state"
    }
}
else {
    Write-Warn "[dry-run] would archive: python framework/validate.py + check_enforcement_plane.py output -> verification_output/split-pre-*.txt"
}

# ---------------------------------------------------------------------------
# STEP 2 - Remove framework/, .lifecycle/, reference-app scaffold, framework docs
# ---------------------------------------------------------------------------
Write-Step "2. Remove framework-owned tree + reference-app scaffold (git rm)"

$removalsTracked = @(
    'framework/',
    '.lifecycle/',
    'src/',
    'package.json',
    'package-lock.json',
    'vite.config.ts',
    'playwright.config.ts',
    'tsconfig.json',
    'components.json',
    'index.html',
    'README.md',
    'MANIFEST.md',
    'TEAM_LEAD.md',
    'requirements-framework.txt',
    'framework/docs/AGENTIC_ARCHITECTURE.md',
    'framework/docs/framework-portability-assessment.md'
)

if ($Apply) {
    Invoke-Step "git rm -r on $($removalsTracked.Count) tracked paths (framework/.lifecycle/src/configs/docs)" {
        $existing = @()
        foreach ($p in $removalsTracked) {
            $ls = & git -C $ProjectRoot ls-files --error-unmatch $p 2>$null
            if ($LASTEXITCODE -eq 0) { $existing += $p }
            else { Write-Warn "path not tracked (skipped): $p" }
        }
        if ($existing.Count -eq 0) { throw "nothing to remove - already carved?" }
        & git -C $ProjectRoot rm -r --quiet -- $existing
        if ($LASTEXITCODE -ne 0) { throw "git rm failed (exit $LASTEXITCODE)" }
        # untracked framework-owned artifacts: docs/PR-CONCURRENCY-surgical.patch
        foreach ($leftover in @('docs/PR-CONCURRENCY-surgical.patch')) {
            $full = Join-Path $ProjectRoot $leftover
            if (Test-Path -LiteralPath $full) {
                Remove-Item -LiteralPath $full -Force
                Write-Ok "removed untracked artifact: $leftover"
            }
        }
        # gitignored leftovers under the removed dirs (telemetry/.manifest caches,
        # any reference-app files ignored under src/)
        # safety: refuse to silently delete untracked NON-ignored files
        $stray = @(& git -C $ProjectRoot ls-files --others --exclude-standard -- framework .lifecycle src 2>$null)
        if ($stray.Count -gt 0) {
            throw "untracked non-ignored files would be lost: $($stray -join ', ') - review and commit or move them first"
        }
        foreach ($dir in @('framework', '.lifecycle', 'src')) {
            $full = Join-Path $ProjectRoot $dir
            if (Test-Path -LiteralPath $full) {
                Remove-Item -LiteralPath $full -Recurse -Force
                Write-Ok "removed gitignored residue dir: $dir"
            }
        }
    }
    Commit-Atomic 'chore(split): remove framework, .lifecycle, reference-app scaffold, framework docs'
}
else {
    Write-Warn "[dry-run] would git rm -r: $($removalsTracked -join ', ')"
    Write-Warn "[dry-run] would remove untracked: docs/PR-CONCURRENCY-surgical.patch; gitignored residue under framework/, .lifecycle/, src/"
    Write-Warn "[dry-run] would commit: chore(split): remove framework, .lifecycle, reference-app scaffold, framework docs"
}

# ---------------------------------------------------------------------------
# STEP 3 - Write app framework.config.json (the ONE config; D3, D5-D8)
# ---------------------------------------------------------------------------
Write-Step "3. Write framework.config.json (app_root / state_folder / gate + surface settings)"

$ConfigPath = Join-Path $ProjectRoot 'framework.config.json'
$ConfigTemplate = @'
{
  "framework": {
    "distribution": "agentic-lifecycle",
    "pin": "git+https://github.com/rajeshp26/agentic-lifecycle.git@v0.1.0",
    "version": "0.1.0"
  },
  "app_root": ".",
  "state_folder": ".framework/state",
  "gate_settings": {
    "browser_output_dir": ".framework/telemetry/browser",
    "env": {}
  },
  "surface": {
    "agents_from_package": true,
    "skills_paths": [],
    "commands_shims": true,
    "hooks_shims": true,
    "plugin_generate": []
  },
  "readiness": {
    "openapi_schema": ".framework/state/contracts/*.openapi.yaml",
    "contract_tests": "backend/tests/test_*contract*.py",
    "frontend_manifest": "web/package.json",
    "playwright_config": "web/playwright.config.ts",
    "browser_specs": "web/e2e/**"
  }
}
'@

if ($Apply) {
    Invoke-Step "write $ConfigPath (skip if present)" {
        if (Test-Path -LiteralPath $ConfigPath) {
            Write-Warn "framework.config.json already exists - left untouched"
        }
        else {
            Set-Utf8NoBom $ConfigPath $ConfigTemplate
            Write-Ok "wrote framework.config.json"
        }
    }
}
else {
    Write-Warn "[dry-run] would write framework.config.json (template below):"
    Write-Host $ConfigTemplate -ForegroundColor DarkGray
}

# ---------------------------------------------------------------------------
# STEP 4 - Run `python -m framework.init` (binding bootstrap + state migration)
# Needs the INSTALLED package: the local framework/ was removed in step 2.
# ---------------------------------------------------------------------------
Write-Step "4. python -m framework.init (migrate .planning -> .framework/state, generate shims)"

if ($Apply) {
    Invoke-Step "run python -m framework.init from $ProjectRoot" {
        Push-Location $ProjectRoot
        try {
            & python -m framework.init
            if ($LASTEXITCODE -ne 0) { throw "python -m framework.init exit $LASTEXITCODE" }
        }
        finally { Pop-Location }
        Write-Ok "binding bootstrap + state migration done"
    }
    Commit-Atomic 'chore(split): migrate GSD state to .framework/state, generate plugin/command shims'
}
else {
    Write-Warn "[dry-run] would run: python -m framework.init"
    Write-Warn "[dry-run] would commit: chore(split): migrate GSD state to .framework/state, generate plugin/command shims"
}

# ---------------------------------------------------------------------------
# STEP 5 - Assert user-authored plane files (NEVER authored by this script)
# ---------------------------------------------------------------------------
Write-Step "5. Verify user-approved plane files (opencode.json / AGENTS.md / bootstrap.ts)"

$PlaneOk = $true
if (-not (Invoke-Check "AGENTS.md present + carries the enforcement-plane fence" {
    $f = Join-Path $ProjectRoot 'AGENTS.md'
    if (-not (Test-Path -LiteralPath $f)) { return $false }
    $c = Get-Content -LiteralPath $f -Raw
    return ($c -match 'enforcement-plane') -and ($c -match 'AGENTS') -and ($c.Length -gt 200)
})) { $PlaneOk = $false }

if (-not (Invoke-Check "opencode.json is the THIN binding (plugin bootstrap.ts, AGENTS.md instructions)" {
    $f = Join-Path $ProjectRoot 'opencode.json'
    if (-not (Test-Path -LiteralPath $f)) { return $false }
    $c = Get-Content -LiteralPath $f -Raw
    return ($c -match 'bootstrap\.ts') -and ($c -match 'AGENTS\.md')
})) { $PlaneOk = $false }

if (-not (Invoke-Check "framework/opencode/plugin/bootstrap.ts present" {
    $f = Join-Path $ProjectRoot 'framework/opencode/plugin\bootstrap.ts'
    return Test-Path -LiteralPath $f
})) { $PlaneOk = $false }

if (-not $PlaneOk) {
    if ($Apply) {
        Write-Fail "plane files are missing/incomplete - place the user-approved opencode.json, AGENTS.md, and framework/opencode/plugin/bootstrap.ts, then re-run"
        exit 1
    }
    Write-Warn "[dry-run] these markers are checked in -Execute mode; missing markers will abort the carve"
}

# ---------------------------------------------------------------------------
# STEP 6 - .gitignore: add .framework runtime, scope .opencode ignore to plugin/*.js,
#          drop obsolete framework lines
# ---------------------------------------------------------------------------
Write-Step "6. Update .gitignore"

$GitIgnorePath = Join-Path $ProjectRoot '.gitignore'
$obsoleteLines = @(
    'framework/.manifest/',
    'framework/telemetry/browser/',
    'framework/telemetry/models-resolved.json'
)

if ($Apply) {
    Invoke-Step "rewrite .gitignore (runtime ignores, scoped .opencode, drop framework lines)" {
        $lines = @(Get-Content -LiteralPath $GitIgnorePath)
        $out = New-Object System.Collections.Generic.List[string]
        foreach ($line in $lines) {
            $trimmed = $line.TrimEnd()
            if ($obsoleteLines -contains $trimmed) { continue }                      # drop framework-owned
            if ($trimmed -eq '.opencode/') {
                $out.Add('framework/opencode/plugin/*.js')                                   # scope: generated shims only
                continue
            }
            $out.Add($line)
        }
        # idempotent append of the .framework runtime block
        $block = @(
            '',
            '# Framework runtime (agentic-lifecycle) - committed state lives in .framework/state',
            '.framework/telemetry/',
            '.framework/tasks/',
            '.framework/blockers.yaml',
            '.framework/retro/',
            '.framework/verification/',
            '.framework/recovery/',
            '.framework/claims/',
            '.framework/.manifest/'
        )
        if (-not ($out -contains '.framework/telemetry/')) { foreach ($b in $block) { $out.Add($b) } }
        $outText = $out -join "`n"
        if (-not $outText.EndsWith("`n")) { $outText += "`n" }
        Set-Utf8NoBom $GitIgnorePath $outText
        Write-Ok ".gitignore updated"
    }
    Commit-Atomic 'chore(split): gitignore framework runtime, scope .opencode to generated plugin shims'
}
else {
    Write-Warn "[dry-run] would: drop '$($obsoleteLines -join "', '")'; change '.opencode/' -> 'framework/opencode/plugin/*.js'; append .framework runtime block"
    Write-Warn "[dry-run] would commit: chore(split): gitignore framework runtime, scope .opencode to generated plugin shims"
}

# ---------------------------------------------------------------------------
# STEP 7 - Cosmetic cleanup: re-point 4 comment references to post-split paths
# ---------------------------------------------------------------------------
Write-Step "7. Re-point cosmetic comment references"

# (path-relative, old-exact, new) - each old must match EXACTLY once
$cosmeticEdits = @(
    @{
        Path = 'backend/scripts/gate_chart_series_integrity.py'
        Old  = 'Exit codes follow framework/gates/EXIT_CODES.md:'
        New  = 'Exit codes follow the installed framework gates contract (agentic-lifecycle: framework/gates/EXIT_CODES.md):'
    },
    @{
        Path = 'backend/application/services/portfolio_service.py'
        Old  = '# Rationale: .planning/USER-ASK.md A6.'
        New  = '# Rationale: user ask A6 (migrated state: .framework/state/ - see committed DID referencing A6).'
    },
    @{
        Path = 'backend/tests/test_portfolio_snapshots.py'
        Old  = 'the concern, use LTTB instead. See .planning/USER-ASK.md A6."'
        New  = 'the concern, use LTTB instead. See user ask A6 (migrated state: .framework/state/)."'
    },
    @{
        Path = 'web/src/app/globals.css'
        Old  = 'Values verbatim from `framework/opencode/skills/apple-ui/tokens.css`.'
        New  = 'Values verbatim from `framework/opencode/skills/apple-ui/tokens.css` (installed package surface).'
    }
)

if ($Apply) {
    Invoke-Step "apply 4 comment re-points (each old string must match exactly once)" {
        $applied = 0
        foreach ($e in $cosmeticEdits) {
            $full = Join-Path $ProjectRoot $e.Path
            if (-not (Test-Path -LiteralPath $full)) { Write-Warn "skip (missing): $($e.Path)"; continue }
            $content = [System.IO.File]::ReadAllText($full)
            $count = ([regex]::Matches($content, [regex]::Escape($e.Old))).Count
            if ($count -eq 0) { Write-Warn "skip (old string absent): $($e.Path)"; continue }
            if ($count -gt 1) { throw "ambiguous (found $count matches): $($e.Path) - manual review required" }
            $content = $content.Replace($e.Old, $e.New)
            Set-Utf8NoBom $full $content
            Write-Ok "re-pointed $($e.Path)"
            $applied++
        }
        if ($applied -eq 0) { Write-Warn "no cosmetic edits applied (all already updated?)" }
    }
    Commit-Atomic 'chore(split): re-point comment references to installed framework paths'
}
else {
    Write-Warn "[dry-run] would apply 4 comment re-points (gate_chart_series_integrity.py, portfolio_service.py, test_portfolio_snapshots.py, web/src/app/globals.css)"
    Write-Warn "[dry-run] would commit: chore(split): re-point comment references to installed framework paths"
}

# ---------------------------------------------------------------------------
# STEP 8 - Final: assert CI untouched, tag post-split
# ---------------------------------------------------------------------------
Write-Step "8. Finalize (CI untouched, tag post-split)"

# 8a. CI unchanged assertion - .github/workflows must not be staged/moved
if (-not (Invoke-Check "app CI (backend-only workflows) untouched" {
    $wf = Join-Path $ProjectRoot '.github\workflows'
    if (-not (Test-Path -LiteralPath $wf)) { Write-Warn ".github/workflows missing - nothing to check"; return $true }
    $unexpected = & git -C $ProjectRoot status --porcelain -- .github 2>$null
    return [string]::IsNullOrWhiteSpace(($unexpected -join ''))
})) { $preflightOk = $false }

# 8b. gitignore keeps app working state out (a final pre-commit sanity read)
if (-not (Invoke-Check ".planning/ and .omo/ still ignored (legacy + agent scratch)" {
    $c = Get-Content -LiteralPath $GitIgnorePath -Raw
    return ($c -match '(?m)^\.planning/$') -and ($c -match '(?m)^\.omo/$')
})) { $preflightOk = $false }

if ($preflightOk -and $Apply) {
    Invoke-Step "tag post-split (skip if exists)" {
        $tagExists = & git -C $ProjectRoot tag --list 'post-split'
        if ($tagExists) { Write-Warn "tag 'post-split' already exists - left untouched" }
        else {
            & git -C $ProjectRoot tag 'post-split'
            if ($LASTEXITCODE -ne 0) { throw "git tag failed (exit $LASTEXITCODE)" }
            Write-Ok "tagged post-split"
        }
    }
}
elseif ($Apply) {
    Write-Fail "final assertions failed - not tagging post-split"
    exit 1
}
else {
    Write-Warn "[dry-run] would tag post-split after the final commit"
}

# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
if ($Apply) {
    Write-Host "   CARVE COMPLETE. Next (user):" -ForegroundColor Green
    Write-Host "   1. Restart opencode (config loaded once; new thin opencode.json now active)" -ForegroundColor Gray
    Write-Host "   2. Gate C: pip-installed 'python -m framework.validate --profile app' exit 0;" -ForegroundColor Gray
    Write-Host "      'check_enforcement_plane' exit 0; 'pytest backend/tests' exit 0; 51 kernel tests" -ForegroundColor Gray
    Write-Host "   3. Phase D joint evidence on both repos" -ForegroundColor Gray
}
else {
    Write-Host "   DRY RUN - no changes made. Re-run with -Execute to apply." -ForegroundColor Yellow
}
Write-Host "============================================================" -ForegroundColor Cyan