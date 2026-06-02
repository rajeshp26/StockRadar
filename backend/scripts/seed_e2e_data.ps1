<#
.SYNOPSIS
    Seed portfolio data for e2e test user OVUH9KDf7TORSB4KuvrGEIRAvTI2
.DESCRIPTION
    Uses Supabase REST API directly to insert seed data.
#>

$SUPABASE_URL = "https://viqdqgxcumcdhqxooplw.supabase.co"
$SERVICE_KEY = "sb_secret_NxN3ywf1RrMektnf-rq9hg_FxKFOVoG"
$FIREBASE_UID = "OVUH9KDf7TORSB4KuvrGEIRAvTI2"

$HEADERS = @{
    "apikey" = $SERVICE_KEY
    "Authorization" = "Bearer $SERVICE_KEY"
    "Content-Type" = "application/json"
    "Prefer" = "return=representation"
}

function Log($msg) { Write-Host "[seed] $msg" }

function Srv($method, $table, $body, $query = "") {
    $url = "$SUPABASE_URL/rest/v1/$table" + $query
    try {
        $r = Invoke-RestMethod -Method $method -Uri $url -Headers $HEADERS -Body ($body | ConvertTo-Json -Depth 10)
        return $r
    } catch {
        $errMsg = $_.Exception.Message
        if ($errMsg -match "409|duplicate|conflict|already exists") { return $null }
        if ($errMsg -match "406") { return $null } # not acceptable = empty result
        Log "WARN: $method $table → $errMsg"
        return $null
    }
}

function SrvGet($table, $query) { return Srv GET $table $null $query }

# ── 1. User ──────────────────────────────────────────────
Log "=== Creating/looking up user ==="
$userCheck = SrvGet "users" "?auth_id=eq.$FIREBASE_UID&select=user_id"
if (-not $userCheck -or $userCheck.Count -eq 0) {
    $newUser = Srv POST "users" @{ auth_id = $FIREBASE_UID }
    $userId = $newUser[0].user_id
    Log "Created user: id=$userId"
} else {
    $userId = $userCheck[0].user_id
    Log "User exists: id=$userId"
}

# ── 2. Brokerages ────────────────────────────────────────
Log "=== Ensuring brokerages ==="
$brokerages = @{}
$brokerageData = @(
    @{ brokerage_code = "QUESTRADE"; brokerage_name = "Questrade"; country_code = "CA"; is_active = $true },
    @{ brokerage_code = "TD_DIRECT"; brokerage_name = "TD Direct Investing"; country_code = "CA"; is_active = $true },
    @{ brokerage_code = "WS_TRADE"; brokerage_name = "Wealthsimple Trade"; country_code = "CA"; is_active = $true }
)
foreach ($b in $brokerageData) {
    $existing = SrvGet "portfolio_brokerages" "?brokerage_code=eq.$($b.brokerage_code)&select=brokerage_id,brokerage_code"
    if ($existing -and $existing.Count -gt 0) {
        $brokerages[$b.brokerage_code] = $existing[0].brokerage_id
        Log "  Brokerage $($b.brokerage_code) exists: id=$($existing[0].brokerage_id)"
    } else {
        $r = Srv POST "portfolio_brokerages" $b
        $brokerages[$b.brokerage_code] = $r[0].brokerage_id
        Log "  Created brokerage $($b.brokerage_code): id=$($r[0].brokerage_id)"
    }
}

# ── 3. Accounts ──────────────────────────────────────────
Log "=== Creating accounts ==="
$accounts = @{}
$accountData = @(
    @{ account_external_id = "EXT-TFSA-001"; account_name = "Main TFSA"; account_type = "TFSA"; brokerage_code = "QUESTRADE" },
    @{ account_external_id = "EXT-RRSP-001"; account_name = "Retirement RRSP"; account_type = "RRSP"; brokerage_code = "TD_DIRECT" },
    @{ account_external_id = "EXT-MRG-001"; account_name = "Margin Account"; account_type = "Margin"; brokerage_code = "QUESTRADE" }
)
foreach ($a in $accountData) {
    $existing = SrvGet "portfolio_accounts" "?user_id=eq.$userId&account_external_id=eq.$($a.account_external_id)&select=account_id,account_name"
    if ($existing -and $existing.Count -gt 0) {
        $accounts[$a.account_name] = $existing[0].account_id
        Log "  Account '$($a.account_name)' exists: id=$($existing[0].account_id)"
    } else {
        $r = Srv POST "portfolio_accounts" @{
            user_id = $userId
            brokerage_id = $brokerages[$a.brokerage_code]
            account_external_id = $a.account_external_id
            account_name = $a.account_name
            account_type = $a.account_type
            currency = "CAD"
            is_active = $true
        }
        $accounts[$a.account_name] = $r[0].account_id
        Log "  Created account '$($a.account_name)': id=$($r[0].account_id)"
    }
}

# ── 4. Companies ─────────────────────────────────────────
Log "=== Ensuring companies ==="
$companies = @{}
$companyData = @(
    @{ ticker_symbol = "AAPL"; company_name = "Apple Inc."; sector = "Technology"; industry = "Consumer Electronics"; exchange = "NMS"; currency = "USD" },
    @{ ticker_symbol = "RY"; company_name = "Royal Bank of Canada"; sector = "Financial Services"; industry = "Banks"; exchange = "TSX"; currency = "CAD" },
    @{ ticker_symbol = "TD"; company_name = "Toronto-Dominion Bank"; sector = "Financial Services"; industry = "Banks"; exchange = "TSX"; currency = "CAD" },
    @{ ticker_symbol = "ENB"; company_name = "Enbridge Inc."; sector = "Energy"; industry = "Oil & Gas Midstream"; exchange = "TSX"; currency = "CAD" },
    @{ ticker_symbol = "SHOP"; company_name = "Shopify Inc."; sector = "Technology"; industry = "Software"; exchange = "NMS"; currency = "CAD" }
)
foreach ($c in $companyData) {
    $existing = SrvGet "companies" "?ticker_symbol=eq.$($c.ticker_symbol)&select=company_id"
    if ($existing -and $existing.Count -gt 0) {
        $companies[$c.ticker_symbol] = $existing[0].company_id
        Log "  Company $($c.ticker_symbol) exists: id=$($existing[0].company_id)"
    } else {
        $r = Srv POST "companies" $c
        $companies[$c.ticker_symbol] = $r[0].company_id
        Log "  Created company $($c.ticker_symbol): id=$($r[0].company_id)"
    }
}

# ── 5. Holdings ──────────────────────────────────────────
Log "=== Creating holdings ==="
$holdingsPlan = @{
    "Main TFSA" = @( @("AAPL", 50, 145.00), @("RY", 100, 95.00), @("SHOP", 30, 68.00) )
    "Retirement RRSP" = @( @("TD", 200, 72.00), @("ENB", 150, 45.00), @("AAPL", 30, 148.00) )
    "Margin Account" = @( @("SHOP", 20, 70.00), @("ENB", 75, 44.50) )
}
$holdingsCreated = 0
foreach ($acctName in $holdingsPlan.Keys) {
    $acctId = $accounts[$acctName]
    foreach ($h in $holdingsPlan[$acctName]) {
        $sym = $h[0]; $qty = $h[1]; $avgCost = $h[2]
        $companyId = $companies[$sym]
        $existing = SrvGet "portfolio_holdings" "?account_id=eq.$acctId&company_id=eq.$companyId&select=holding_id"
        if ($existing -and $existing.Count -gt 0) {
            Log "  Holding $sym in $acctName exists: id=$($existing[0].holding_id)"
        } else {
            $r = Srv POST "portfolio_holdings" @{
                account_id = $acctId
                company_id = $companyId
                symbol = $sym
                quantity = $qty
                average_cost = $avgCost
                total_cost = [Math]::Round($qty * $avgCost, 2)
                realized_gain_loss = 0
            }
            if ($r) { $holdingsCreated++ }
        }
    }
}
Log "  Created $holdingsCreated new holdings"

# ── 6. Transactions ──────────────────────────────────────
Log "=== Creating transactions ==="
$txPlan = @{
    "Main TFSA" = @(
        @("AAPL", (Get-Date).AddDays(-180), 50, 142.00, "Buy"),
        @("RY", (Get-Date).AddDays(-150), 100, 93.50, "Buy"),
        @("SHOP", (Get-Date).AddDays(-90), 30, 65.00, "Buy"),
        @("RY", (Get-Date).AddDays(-30), 10, 105.00, "Sell")
    )
    "Retirement RRSP" = @(
        @("TD", (Get-Date).AddDays(-200), 200, 70.00, "Buy"),
        @("ENB", (Get-Date).AddDays(-170), 150, 44.00, "Buy"),
        @("AAPL", (Get-Date).AddDays(-120), 30, 146.00, "Buy"),
        @("TD", (Get-Date).AddDays(-45), 10, 78.00, "Sell")
    )
    "Margin Account" = @(
        @("SHOP", (Get-Date).AddDays(-100), 20, 68.50, "Buy"),
        @("ENB", (Get-Date).AddDays(-80), 75, 44.00, "Buy")
    )
}
$txCreated = 0
foreach ($acctName in $txPlan.Keys) {
    $acctId = $accounts[$acctName]
    foreach ($tx in $txPlan[$acctName]) {
        $sym = $tx[0]; $txDate = $tx[1]; $qty = $tx[2]; $price = $tx[3]; $direction = $tx[4]
        $netCash = if ($direction -eq "Buy") { [Math]::Round(-$qty * $price, 2) } else { [Math]::Round($qty * $price, 2) }
        $dateStr = $txDate.ToString("yyyy-MM-dd")
        $existing = SrvGet "portfolio_transactions" "?account_id=eq.$acctId&symbol=eq.$sym&transaction_date=eq.$dateStr&quantity=eq.$qty&select=transaction_id"
        if ($existing -and $existing.Count -gt 0) {
            Log "  TX $sym $direction $qty on $dateStr exists"
        } else {
            $r = Srv POST "portfolio_transactions" @{
                account_id = $acctId
                company_id = $companies[$sym]
                transaction_date = $dateStr
                activity_type = "Trade"
                activity_sub_type = $direction
                direction = $direction
                symbol = $sym
                quantity = $qty
                unit_price = $price
                net_cash_amount = $netCash
                currency = "CAD"
            }
            if ($r) { $txCreated++ }
        }
    }
}
Log "  Created $txCreated new transactions"

# ── 7. Dividends ────────────────────────────────────────
Log "=== Creating dividends ==="
$dividends = @(
    @("Main TFSA", "RY", (Get-Date).AddDays(-60), 42.00),
    @("Main TFSA", "RY", (Get-Date).AddDays(-150), 40.00),
    @("Retirement RRSP", "TD", (Get-Date).AddDays(-60), 76.00),
    @("Retirement RRSP", "TD", (Get-Date).AddDays(-150), 72.00),
    @("Retirement RRSP", "ENB", (Get-Date).AddDays(-60), 52.50),
    @("Margin Account", "ENB", (Get-Date).AddDays(-60), 26.25)
)
$divCreated = 0
foreach ($d in $dividends) {
    $acctName = $d[0]; $sym = $d[1]; $payDate = $d[2]; $amount = $d[3]
    $acctId = $accounts[$acctName]
    $dateStr = $payDate.ToString("yyyy-MM-dd")
    $existing = SrvGet "portfolio_dividends" "?account_id=eq.$acctId&symbol=eq.$sym&payment_date=eq.$dateStr&select=dividend_id"
    if ($existing -and $existing.Count -gt 0) { continue }
    $r = Srv POST "portfolio_dividends" @{
        account_id = $acctId
        company_id = $companies[$sym]
        symbol = $sym
        payment_date = $dateStr
        amount = $amount
        currency = "CAD"
        fiscal_year = $payDate.Year
        fiscal_month = $payDate.Month
    }
    if ($r) { $divCreated++ }
}
Log "  Created $divCreated new dividends"

# ── 8. Performance Snapshots ─────────────────────────────
Log "=== Creating performance snapshots ==="
$perfCreated = 0
foreach ($acctName in $accounts.Keys) {
    $acctId = $accounts[$acctName]
    for ($i = 0; $i -lt 12; $i++) {
        $d = (Get-Date).AddMonths(-$i)
        $d = Get-Date -Year $d.Year -Month $d.Month -Day 1
        $dateStr = $d.ToString("yyyy-MM-dd")
        $existing = SrvGet "portfolio_performance" "?account_id=eq.$acctId&snapshot_date=eq.$dateStr&select=snapshot_id"
        if ($existing -and $existing.Count -gt 0) { continue }
        $totalVal = [Math]::Round(50000 - $i * 500 + $i * 200, 2)
        $costBasis = [Math]::Round(48000 - $i * 400, 2)
        $r = Srv POST "portfolio_performance" @{
            account_id = $acctId
            snapshot_date = $dateStr
            total_value = $totalVal
            cost_basis = $costBasis
            net_deposits = 0
        }
        if ($r) { $perfCreated++ }
    }
}
Log "  Created $perfCreated performance snapshots"

# ── 9. Current Market Data ───────────────────────────────
Log "=== Updating current market data ==="
$prices = @{ AAPL = 178.50; RY = 102.30; TD = 78.40; ENB = 47.20; SHOP = 82.00 }
foreach ($sym in $prices.Keys) {
    $companyId = $companies[$sym]
    $price = $prices[$sym]
    Srv POST "current_market_data" @{
        company_id = $companyId
        current_price = $price
        open_price = $price - 0.50
        high_price = $price + 1.00
        low_price = $price - 1.00
        close_price = $price
        volume = 1000000
        market_state = "CLOSED"
    } -query "?on_conflict=company_id"
    Log "  Updated $sym = $$price"
}

# ── 10. Price History (90 days) ──────────────────────────
Log "=== Creating price history ==="
$basePrices = @{ AAPL = 175.00; RY = 100.00; TD = 76.00; ENB = 45.00; SHOP = 65.00 }
$phCreated = 0
$random = [Random]::new(42)
foreach ($sym in $basePrices.Keys) {
    $companyId = $companies[$sym]
    $base = $basePrices[$sym]
    for ($i = 90; $i -ge 0; $i--) {
        $d = (Get-Date).AddDays(-$i)
        $dateStr = $d.ToString("yyyy-MM-dd")
        $daily = $base + ($random.NextDouble() * 6 - 3)
        $daily = [Math]::Round($daily, 2)
        $existing = SrvGet "price_history" "?company_id=eq.$companyId&price_date=eq.$dateStr&select=company_id"
        if ($existing -and $existing.Count -gt 0) { continue }
        $r = Srv POST "price_history" @{
            company_id = $companyId
            price_date = $dateStr
            open_price = [Math]::Round($daily - 0.2, 2)
            close_price = $daily
            high_price = [Math]::Round($daily + 0.5, 2)
            low_price = [Math]::Round($daily - 0.5, 2)
            volume = 2000000
        }
        if ($r) { $phCreated++ }
    }
}
Log "  Created $phCreated price history rows"

Log "=== E2E seed complete! ==="
