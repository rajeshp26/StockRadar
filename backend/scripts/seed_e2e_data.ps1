<#
.SYNOPSIS
    Seed the E2E portfolio fixture.

.DESCRIPTION
    Thin wrapper around scripts/seed_e2e_data.py.

    This file used to carry its own copy of the portfolio plan, and it was the
    third copy of it: it wrote a Sell with a POSITIVE quantity and buy prices
    that contradicted the average costs it also wrote, so the account's history
    totalled 110 shares against a 100-share position. Three copies of one
    fixture is how the fixture ended up asserting two different positions for
    the same account.

    The plan now lives in exactly one place (scripts/e2e_fixtures.py) and the
    seeding logic in exactly one place (scripts/seed_e2e_data.py). This wrapper
    sets the environment and forwards arguments, so it cannot drift.

    Kept as a .ps1 because it is the entry point operators already use.

.PARAMETER Reset
    Rebuild the fixture accounts: delete their transactions, holdings and
    position_state_checkpoint events, then re-create everything from the
    fixture. Real accounts are never touched.

.EXAMPLE
    .\scripts\seed_e2e_data.ps1

.EXAMPLE
    .\scripts\seed_e2e_data.ps1 -Reset

.NOTES
    Requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in the environment.
    Credentials are never stored in this repository.
#>
param([switch]$Reset)

$ErrorActionPreference = "Stop"

if (-not $env:SUPABASE_URL -or -not $env:SUPABASE_SERVICE_ROLE_KEY) {
    throw "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in the environment. Credentials are not stored in this repository."
}

$backend = Split-Path -Parent $PSScriptRoot
$seeder = Join-Path $backend "scripts\seed_e2e_data.py"

if (-not (Test-Path $seeder)) {
    throw "Seeder not found: $seeder"
}

$seederArgs = @($seeder)
if ($Reset) { $seederArgs += "--reset" }

Push-Location $backend
try {
    & python @seederArgs
    if ($LASTEXITCODE -ne 0) {
        throw "seed_e2e_data.py exited with code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
