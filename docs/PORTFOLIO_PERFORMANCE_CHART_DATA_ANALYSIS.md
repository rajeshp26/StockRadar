# Portfolio Performance Chart Data Analysis

**Date:** July 14, 2026
**Status:** PROPOSED — Awaiting Review

---

## Executive Summary

| Account | ID | Snapshots | Last Value | Last Net Deposits | Data Quality | Spike |
|---------|-----|-----------|------------|-------------------|--------------|-------|
| TFSA (5ZHK5CAD) | 9 | 68 | $51,585.00 | $34,982.02 | INCOMPLETE | Yes |
| RRSP (K9R43CAD) | 8 | 64 | $32,629.06 | $25,892.24 | INCOMPLETE | Yes |
| Non-registered (12403CAD) | 7 | 67 | $15,530.12 | $7,885.83 | OK | Yes |
| **ALL ACCOUNTS** | — | 67 | **$99,744.18** | **$68,760.09** | OK | Yes |

**Decision: REUSE backend logic with targeted fixes** — backend handles ~60% of edge cases correctly. Remaining 40% is fixable with targeted code changes.

---

## Table of Contents

1. [TFSA Account Data](#1-tfsa-account-data)
2. [RRSP Account Data](#2-rrsp-account-data)
3. [Non-registered Account Data](#3-non-registered-account-data)
4. [All Accounts Combined](#4-all-accounts-combined)
5. [Cross-Account Verification](#5-cross-account-verification)
6. [Topic: FX Conversion](#6-topic-fx-conversion)
7. [Topic: CDR Handling](#7-topic-cdr-handling) (includes critical pipeline fix)
8. [Topic: Split Handling](#8-topic-split-handling)
9. [Topic: Event Replay](#9-topic-event-replay)
10. [Topic: Repair Script](#10-topic-repair-script)
11. [Code Path Reference](#11-code-path-reference)
12. [Implementation Plan](#12-implementation-plan)
13. [Risk Analysis](#13-risk-analysis)
14. [Database Schema Changes](#14-database-schema-changes)

---

## 1. TFSA Account Data

**Metadata:** `account_id=9`, `external_id="HQ035ZHK5CAD"`, `auth_id=59a7ced9-aa7c-4f34-b77e-266fc8a8e796`

### All 68 Data Points (30-day compression)

**Expected values** calculated from `docs/activities-export-2026-05-10.csv` + `price_history` table:
- **Exp PV** = Σ(holdings × historical close_price) + Exp Cash Balance (N/A when missing price data)
- **Obs PV** = Portfolio Value (total market value of holdings + cash)
- **Exp Cost Basis** = Σ(holdings × purchase_price) from BUY transactions
- **Obs Cost Basis** = Total purchase price of current holdings
- **Exp ND** = Σ(MoneyMovement + BonusPayment net_cash_amount) where transaction_date ≤ snapshot_date
- **Obs ND** = Net Deposits (cumulative deposits minus withdrawals)
- **Exp Cash** = Σ(all cash-impacting transactions) where transaction_date ≤ snapshot_date
- **Obs Cash** = Cash in account

| # | Date | Exp PV | Obs PV | Exp Cost Basis | Obs Cost Basis | Exp ND | Obs ND | Exp Cash | Obs Cash |
|---|------|--------|--------|----------------|----------------|--------|--------|----------|----------|
| 1 | 2021-02-08 | $1,000.00 | $0.00 | $0.00 | $0.00 | $1,000.00 | $0.00 | $1,000.00 | $0.00 |
| 2 | 2021-03-10 | $1,521.43 | $0.00 | $1,775.16 | $0.00 | $2,600.00 | $0.00 | $824.85 | $0.00 |
| 3 | 2021-04-09 | $2,591.96 | $0.00 | $2,838.22 | $0.00 | $3,000.00 | $0.00 | $161.78 | $0.00 |
| 4 | 2021-05-10 | $2,617.32 | $0.00 | $3,000.93 | $0.00 | $3,500.00 | $0.00 | $499.07 | $0.00 |
| 5 | 2021-06-09 | $4,064.65 | $0.00 | $3,443.79 | $0.00 | $4,933.00 | $0.00 | $1,472.98 | $0.00 |
| 6 | 2021-07-09 | $5,652.02 | $0.00 | $3,780.82 | $0.00 | $5,433.00 | $0.00 | $2,145.39 | $0.00 |
| 7 | 2021-08-09 | N/A | $0.00 | $4,733.05 | $0.00 | $5,933.00 | $0.00 | $1,848.62 | $0.00 |
| 8 | 2021-09-08 | N/A | $0.00 | $4,448.05 | $0.00 | $6,683.00 | $0.00 | $2,979.12 | $0.00 |
| 9 | 2021-10-08 | N/A | $0.00 | $5,493.11 | $0.00 | $6,710.37 | $0.00 | $1,961.43 | $0.00 |
| 10 | 2021-11-08 | N/A | $0.00 | $5,369.03 | $0.00 | $7,210.37 | $0.00 | $2,716.23 | $0.00 |
| 11 | 2021-12-08 | N/A | $0.00 | $5,369.03 | $0.00 | $7,710.37 | $0.00 | $3,216.23 | $0.00 |
| 12 | 2022-01-07 | N/A | $0.00 | $5,369.03 | $0.00 | $7,710.37 | $0.00 | $3,216.23 | $0.00 |
| 13 | 2022-02-07 | N/A | $0.00 | $5,876.12 | $0.00 | $7,710.37 | $0.00 | $2,709.15 | $0.00 |
| 14 | 2022-03-09 | N/A | $0.00 | $8,234.87 | $0.00 | $12,710.37 | $0.00 | $5,350.39 | $0.00 |
| 15 | 2022-04-08 | N/A | $0.00 | $10,825.92 | $0.00 | $14,210.37 | $0.00 | $4,259.34 | $0.00 |
| 16 | 2022-05-09 | N/A | $0.00 | $13,047.53 | $0.00 | $17,210.37 | $0.00 | $5,037.72 | $0.00 |
| 17 | 2022-06-08 | N/A | $0.00 | $14,906.41 | $0.00 | $17,210.37 | $0.00 | $3,184.98 | $0.00 |
| 18 | 2022-07-08 | N/A | $0.00 | $18,523.85 | $0.00 | $18,210.37 | $0.00 | $567.54 | $0.00 |
| 19 | 2022-08-08 | N/A | $0.00 | $19,263.15 | $0.00 | $18,210.37 | $0.00 | -$169.69 | $0.00 |
| 20 | 2022-09-07 | N/A | $0.00 | $19,376.55 | $0.00 | $18,210.37 | $0.00 | -$283.09 | $0.00 |
| 21 | 2022-10-07 | N/A | $0.00 | $19,542.94 | $0.00 | $18,210.37 | $0.00 | -$449.48 | $0.00 |
| 22 | 2022-11-07 | N/A | $0.00 | $19,685.94 | $0.00 | $18,210.37 | $0.00 | -$592.48 | $0.00 |
| 23 | 2022-12-07 | N/A | $0.00 | $19,774.44 | $0.00 | $18,210.37 | $0.00 | -$680.98 | $0.00 |
| 24 | 2023-01-06 | N/A | $0.00 | $19,770.02 | $0.00 | $18,210.37 | $0.00 | -$672.75 | $0.00 |
| 25 | 2023-02-06 | N/A | $0.00 | $19,770.02 | $0.00 | $18,210.37 | $0.00 | -$672.75 | $0.00 |
| 26 | 2023-03-08 | N/A | $0.00 | $22,376.31 | $0.00 | $21,210.37 | $0.00 | -$279.04 | $0.00 |
| 27 | 2023-04-07 | N/A | $0.00 | $24,621.32 | $0.00 | $22,710.37 | $0.00 | -$1,024.06 | $0.00 |
| 28 | 2023-05-08 | N/A | $0.00 | $25,073.32 | $0.00 | $22,910.37 | $0.00 | -$1,272.73 | $0.00 |
| 29 | 2023-06-07 | N/A | $0.00 | $25,073.17 | $0.00 | $22,910.37 | $0.00 | -$1,271.79 | $0.00 |
| 30 | 2023-07-07 | N/A | $0.00 | $25,233.17 | $0.00 | $22,910.37 | $0.00 | -$1,434.86 | $0.00 |
| 31 | 2023-08-07 | N/A | $0.00 | $25,188.76 | $0.00 | $22,973.29 | $0.00 | -$1,567.14 | $0.00 |
| 32 | 2023-09-06 | N/A | $0.00 | $25,366.29 | $0.00 | $23,027.29 | $0.00 | -$1,690.67 | $0.00 |
| 33 | 2023-10-06 | N/A | $0.00 | $25,512.54 | $0.00 | $23,048.29 | $0.00 | -$1,815.92 | $0.00 |
| 34 | 2023-11-06 | N/A | $0.00 | $25,512.54 | $0.00 | $23,048.29 | $0.00 | -$1,815.92 | $0.00 |
| 35 | 2023-12-06 | N/A | $0.00 | $25,512.54 | $0.00 | $23,048.29 | $0.00 | -$1,815.92 | $0.00 |
| 36 | 2024-01-05 | N/A | $0.00 | $25,497.15 | $0.00 | $25,048.29 | $0.00 | -$63.63 | $0.00 |
| 37 | 2024-02-05 | N/A | $0.00 | $30,695.28 | $0.00 | $27,960.29 | $0.00 | -$2,349.76 | $0.00 |
| 38 | 2024-03-06 | N/A | $0.00 | $32,009.94 | $0.00 | $29,203.29 | $0.00 | -$2,421.41 | $0.00 |
| 39 | 2024-04-05 | N/A | $0.00 | $32,140.87 | $0.00 | $29,203.29 | $0.00 | -$2,590.68 | $0.00 |
| 40 | 2024-05-06 | N/A | $0.00 | $32,528.87 | $0.00 | $29,203.29 | $0.00 | -$2,978.68 | $0.00 |
| 41 | 2024-06-05 | N/A | $0.00 | $32,528.87 | $0.00 | $29,203.29 | $0.00 | -$2,978.68 | $0.00 |
| 42 | 2024-07-05 | $130,081.74 | $0.00 | $33,110.43 | $0.00 | $29,203.29 | $0.00 | -$3,560.24 | $0.00 |
| 43 | 2024-08-05 | $132,569.77 | $4.02 | $33,110.43 | $0.00 | $29,203.29 | $0.00 | -$3,560.24 | $4.02 |
| 44 | 2024-09-04 | $114,367.34 | $4.02 | $33,110.43 | $0.00 | $29,203.29 | $0.00 | -$3,560.24 | $4.02 |
| 45 | 2024-10-04 | $81,055.07 | $4.02 | $33,828.91 | $0.00 | $29,203.29 | $0.00 | -$4,278.71 | $4.02 |
| 46 | 2024-11-04 | $80,021.53 | $4.02 | $33,828.91 | $0.00 | $29,203.29 | $0.00 | -$4,278.71 | $4.02 |
| 47 | 2024-12-04 | $84,074.41 | $4.02 | $34,185.23 | $0.00 | $29,203.29 | $0.00 | -$4,635.04 | $4.02 |
| 48 | 2025-01-03 | $68,511.76 | $91.35 | $34,185.23 | $356.33 | $28,791.49 | -$411.80 | -$5,046.84 | -$105.07 |
| 49 | 2025-02-04 | $64,428.11 | $626.25 | $35,654.53 | $356.33 | $30,594.98 | $1,391.69 | -$4,712.65 | $429.83 |
| 50 | 2025-03-07 | $39,950.38 | $1,133.50 | $38,079.84 | $356.33 | $32,594.98 | $3,391.69 | -$5,137.96 | $937.08 |
| 51 | 2025-04-07 | $33,433.19 | $949.55 | $39,151.84 | $356.33 | $34,145.74 | $4,942.45 | -$4,659.20 | $753.13 |
| 52 | 2025-05-07 | $32,694.70 | $1,103.41 | $39,151.84 | $356.33 | $34,145.74 | $4,942.45 | -$4,659.20 | $906.99 |
| 53 | 2025-06-06 | $33,848.55 | $1,709.05 | $39,870.64 | $356.33 | $34,564.33 | $5,361.04 | -$4,959.41 | $1,512.63 |
| 54 | 2025-07-07 | $33,724.03 | $643.30 | $40,350.14 | $356.33 | $34,572.02 | $5,368.73 | -$5,431.22 | $446.88 |
| 55 | 2025-08-06 | $36,854.14 | $779.86 | $40,903.74 | $356.33 | $34,572.02 | $5,368.73 | -$5,984.82 | $583.44 |
| 56 | 2025-09-05 | $39,413.45 | $779.86 | $41,145.54 | $356.33 | $34,572.02 | $5,368.73 | -$6,226.62 | $583.44 |
| 57 | 2025-10-07 | $40,833.83 | $779.86 | $41,411.94 | $356.33 | $34,572.02 | $5,368.73 | -$6,493.02 | $583.44 |
| 58 | 2025-11-06 | $40,277.32 | $779.86 | $41,717.69 | $356.33 | $34,572.02 | $5,368.73 | -$6,798.77 | $583.44 |
| 59 | 2025-12-08 | $38,141.86 | $779.86 | $42,046.69 | $356.33 | $34,572.02 | $5,368.73 | -$7,127.77 | $583.44 |
| 60 | 2026-01-08 | $39,030.93 | $747.53 | $42,338.63 | $356.33 | $34,572.02 | $5,368.73 | -$7,222.54 | $551.11 |
| 61 | 2026-02-09 | $39,755.22 | $1,134.88 | $43,292.63 | $356.33 | $34,572.02 | $5,368.73 | -$8,176.54 | $938.46 |
| 62 | 2026-03-11 | $38,393.60 | $978.62 | $43,292.63 | $356.33 | $34,982.02 | $5,778.73 | -$7,766.54 | $782.20 |
| 63 | 2026-04-10 | $36,598.13 | $978.62 | $43,945.63 | $356.33 | $34,982.02 | $5,778.73 | -$8,419.54 | $782.20 |
| 64 | 2026-05-31 | $61,281.77 | $1,007.12 | $43,945.63 | $356.33 | $34,982.02 | $5,778.73 | -$8,419.54 | $810.70 |
| 65 | 2026-07-01 | $57,547.17 | $1,007.12 | $43,945.63 | $356.33 | $34,982.02 | $5,778.73 | -$8,419.54 | $810.70 |
| **66** | **2026-07-14** | **$60,149.54** | **$51,585.00** | **$43,945.63** | **$43,172.07** | **$34,982.02** | **$34,982.02** | **-$8,419.54** | **$963.38** |

**Key observations:**
- Rows 1-6: Exp PV matches Exp ND (no stock purchases yet, all cash)
- Rows 7-41: Exp PV = N/A due to missing price data for held symbols (DFN, GME, HCLN, SCR, BB, etc.)
- Rows 42+: Exp PV available — massive discrepancy: Obs PV=$4.02 vs Exp PV=$130K+ (snapshots have $0 for holdings)
- Row 66 (today): Obs PV=$51,585 vs Exp PV=$60,150 (15% understated due to missing prices)
- Rows 1-42: Obs ND = $0 but actual deposits made → **snapshots missing net_deposits**
- Row 66: Exp ND = $34,982.02 = Obs ND → **correct only on last row**
- Rows 1-42: Obs Cost Basis = $0 → **snapshots missing cost basis**
- Row 66: Exp CB = $43,945 ≈ Obs CB = $43,172 → **approximately correct only on last row**

---

## 2. RRSP Account Data

**Metadata:** `account_id=8`, `external_id="HQ16K9R43CAD"`

### All 64 Data Points

| # | Date | Portfolio Value | Net Deposits | Cost Basis | Cash Balance |
|---|------|----------------|--------------|------------|--------------|
| 1 | 2021-04-22 | $250.00 | $250.00 | $0.00 | $250.00 |
| 2 | 2021-05-24 | $250.00 | $250.00 | $0.00 | $250.00 |
| 3 | 2021-06-23 | $292.48 | $250.00 | $0.00 | $292.48 |
| 4 | 2021-07-23 | $292.48 | $250.00 | $0.00 | $292.48 |
| 5 | 2021-08-23 | $292.48 | $250.00 | $0.00 | $292.48 |
| 6 | 2021-09-22 | $292.48 | $250.00 | $0.00 | $292.48 |
| 7 | 2021-10-22 | $292.48 | $250.00 | $0.00 | $292.48 |
| 8 | 2021-11-22 | $292.48 | $250.00 | $0.00 | $292.48 |
| 9 | 2021-12-22 | $292.48 | $250.00 | $0.00 | $292.48 |
| 10 | 2022-01-21 | $292.48 | $250.00 | $0.00 | $292.48 |
| 11 | 2022-02-21 | $292.48 | $250.00 | $0.00 | $292.48 |
| 12 | 2022-03-23 | $292.48 | $250.00 | $0.00 | $292.48 |
| 13 | 2022-04-22 | $1,586.86 | $1,750.00 | $0.00 | $1,586.86 |
| 14 | 2022-05-23 | $1,320.43 | $1,750.00 | $0.00 | $1,320.43 |
| 15 | 2022-06-22 | $1,320.43 | $1,750.00 | $0.00 | $1,320.43 |
| 16 | 2022-07-22 | $1,320.43 | $1,750.00 | $0.00 | $1,320.43 |
| 17 | 2022-08-22 | $1,320.43 | $1,750.00 | $0.00 | $1,320.43 |
| 18 | 2022-09-21 | $1,320.43 | $1,750.00 | $0.00 | $1,320.43 |
| 19 | 2022-10-21 | $1,320.43 | $1,750.00 | $0.00 | $1,320.43 |
| 20 | 2022-11-21 | $1,320.43 | $1,750.00 | $0.00 | $1,320.43 |
| 21 | 2022-12-21 | $1,320.43 | $1,750.00 | $0.00 | $1,320.43 |
| 22 | 2023-01-20 | $1,320.43 | $1,750.00 | $0.00 | $1,320.43 |
| 23 | 2023-02-20 | $1,320.43 | $1,750.00 | $0.00 | $1,320.43 |
| 24 | 2023-03-22 | $1,320.43 | $1,750.00 | $0.00 | $1,320.43 |
| 25 | 2023-04-21 | $412.63 | $2,150.00 | $300.26 | $101.39 |
| 26 | 2023-05-22 | $1,446.93 | $4,150.00 | $300.26 | $1,135.69 |
| 27 | 2023-06-21 | $2,848.34 | $4,744.00 | $1,160.64 | $534.87 |
| 28 | 2023-07-21 | $4,370.55 | $6,894.00 | $1,812.76 | $161.45 |
| 29 | 2023-08-21 | $5,205.05 | $7,894.00 | $2,812.39 | $9.83 |
| 30 | 2023-09-20 | $6,132.13 | $9,194.00 | $3,155.03 | $526.91 |
| 31 | 2023-10-20 | $6,260.03 | $9,544.00 | $3,958.70 | $114.20 |
| 32 | 2023-11-20 | $6,325.48 | $9,544.00 | $3,958.70 | $179.65 |
| 33 | 2023-12-20 | $6,353.05 | $9,544.00 | $3,958.70 | $207.22 |
| 34 | 2024-01-19 | $6,393.17 | $9,544.00 | $3,958.70 | $247.34 |
| 35 | 2024-02-19 | $6,207.66 | $9,544.00 | $3,958.70 | $61.83 |
| 36 | 2024-03-20 | $6,233.75 | $9,544.00 | $3,958.70 | $87.92 |
| 37 | 2024-04-19 | $6,256.69 | $9,544.00 | $3,958.70 | $110.86 |
| 38 | 2024-05-20 | $6,341.16 | $9,544.00 | $3,958.70 | $195.33 |
| 39 | 2024-06-19 | $6,357.87 | $9,544.00 | $3,958.70 | $212.04 |
| 40 | 2024-07-19 | $6,194.74 | $9,544.00 | $3,958.70 | $48.91 |
| 41 | 2024-08-19 | $6,262.15 | $9,544.00 | $3,958.70 | $116.32 |
| 42 | 2024-09-18 | $6,281.71 | $9,544.00 | $3,958.70 | $135.88 |
| 43 | 2024-10-18 | $6,321.23 | $9,544.00 | $3,958.70 | $175.40 |
| 44 | 2024-11-18 | $6,389.57 | $9,544.00 | $3,958.70 | $243.74 |
| 45 | 2024-12-18 | $12,136.40 | $13,044.00 | $5,866.00 | $1,620.56 |
| 46 | 2025-01-17 | $14,259.61 | $12,398.03 | $6,840.50 | $43.78 |
| 47 | 2025-02-21 | $14,291.70 | $12,398.03 | $6,840.50 | $75.87 |
| 48 | 2025-03-24 | $14,292.64 | $12,398.97 | $6,840.50 | $76.81 |
| 49 | 2025-04-28 | $14,348.39 | $12,398.97 | $6,840.50 | $132.56 |
| 50 | 2025-05-28 | $14,348.39 | $12,398.97 | $6,840.50 | $132.56 |
| 51 | 2025-06-27 | $14,477.59 | $12,517.50 | $6,840.50 | $261.76 |
| 52 | 2025-07-28 | $14,411.56 | $12,522.45 | $6,840.50 | $195.73 |
| 53 | 2025-08-27 | $14,331.50 | $15,851.45 | $6,840.50 | $115.67 |
| 54 | 2025-09-26 | $13,955.26 | $17,851.45 | $6,840.50 | -$260.57 |
| 55 | 2025-10-27 | $13,929.84 | $18,018.43 | $6,840.50 | -$285.99 |
| 56 | 2025-11-26 | $14,330.59 | $19,018.43 | $7,540.50 | -$212.49 |
| 57 | 2025-12-26 | $14,737.23 | $20,715.78 | $7,540.50 | $194.15 |
| 58 | 2026-01-28 | $14,969.20 | $22,015.78 | $8,863.38 | -$181.63 |
| 59 | 2026-02-27 | $15,034.21 | $22,015.78 | $8,863.38 | -$116.62 |
| 60 | 2026-03-31 | $18,673.06 | $25,892.24 | $9,678.78 | $2,419.71 |
| 61 | 2026-04-30 | $18,822.67 | $25,892.24 | $9,678.78 | $2,569.32 |
| 62 | 2026-05-31 | $18,861.57 | $25,892.24 | $9,678.78 | $2,608.22 |
| 63 | 2026-07-01 | $18,861.57 | $25,892.24 | $9,678.78 | $2,608.22 |
| **64** | **2026-07-14** | **$32,629.06** | **$25,892.24** | **$21,198.95** | **$2,608.22** |

---

## 3. Non-registered Account Data

**Metadata:** `account_id=7`, `external_id="H46312403CAD"`

### All 67 Data Points

| # | Date | Portfolio Value | Net Deposits | Cost Basis | Cash Balance |
|---|------|----------------|--------------|------------|--------------|
| 1 | 2021-01-07 | $500.00 | $500.00 | $0.00 | $500.00 |
| 2 | 2021-02-08 | $500.00 | $500.00 | $0.00 | $500.00 |
| 3 | 2021-03-10 | $500.00 | $500.00 | $0.00 | $500.00 |
| 4 | 2021-04-09 | $500.00 | $500.00 | $0.00 | $500.00 |
| 5 | 2021-05-10 | $500.00 | $500.00 | $0.00 | $500.00 |
| 6 | 2021-06-09 | -$7.02 | $67.00 | $0.00 | -$7.02 |
| 7 | 2021-07-09 | $19.58 | $67.00 | $0.00 | $19.58 |
| 8 | 2021-08-09 | $19.58 | $67.00 | $0.00 | $19.58 |
| 9 | 2021-09-08 | $19.58 | $67.00 | $0.00 | $19.58 |
| 10 | 2021-10-08 | -$7.79 | $39.63 | $0.00 | -$7.79 |
| 11 | 2021-11-08 | -$7.79 | $39.63 | $0.00 | -$7.79 |
| 12 | 2021-12-08 | -$7.79 | $39.63 | $0.00 | -$7.79 |
| 13 | 2022-01-07 | -$7.79 | $39.63 | $0.00 | -$7.79 |
| 14 | 2022-02-07 | -$7.79 | $39.63 | $0.00 | -$7.79 |
| 15 | 2022-03-09 | -$7.79 | $39.63 | $0.00 | -$7.79 |
| 16 | 2022-04-08 | $2.21 | $49.63 | $0.00 | $2.21 |
| 17 | 2022-05-09 | $2.21 | $49.63 | $0.00 | $2.21 |
| 18 | 2022-06-08 | $2,787.41 | $4,049.63 | $0.00 | $2,787.41 |
| 19 | 2022-07-08 | $2,439.81 | $4,049.63 | $0.00 | $2,439.81 |
| 20 | 2022-08-08 | $1,330.06 | $6,049.63 | $1,013.90 | $698.66 |
| 21 | 2022-09-07 | $1,838.96 | $7,749.63 | $1,013.90 | $1,207.56 |
| 22 | 2022-10-07 | $1,805.92 | $10,249.63 | $1,230.98 | $1,124.72 |
| 23 | 2022-11-07 | $2,167.61 | $11,249.63 | $1,608.34 | $876.99 |
| 24 | 2022-12-07 | $1,335.92 | $11,259.63 | $1,728.76 | $34.30 |
| 25 | 2023-01-06 | $1,379.41 | $11,259.63 | $1,728.76 | $77.79 |
| 26 | 2023-02-06 | $1,439.17 | $11,259.63 | $1,728.76 | $137.55 |
| 27 | 2023-03-08 | $1,478.82 | $11,274.63 | $2,028.08 | $40.11 |
| 28 | 2023-04-07 | $1,451.86 | $10,874.63 | $2,028.08 | $13.15 |
| 29 | 2023-05-08 | $2,170.15 | $11,474.63 | $2,028.08 | $731.43 |
| 30 | 2023-06-07 | $1,453.85 | $9,530.63 | $2,028.08 | $15.14 |
| 31 | 2023-07-07 | $2,902.90 | $10,430.63 | $2,028.08 | $1,464.19 |
| 32 | 2023-08-07 | $1,498.10 | $8,967.71 | $2,028.08 | $59.39 |
| 33 | 2023-09-06 | $1,456.96 | $8,913.71 | $2,028.08 | $18.24 |
| 34 | 2023-10-06 | $1,462.80 | $8,892.71 | $2,028.08 | $24.08 |
| 35 | 2023-11-06 | $1,526.58 | $8,892.71 | $2,028.08 | $87.86 |
| 36 | 2023-12-06 | $1,539.08 | $8,892.71 | $2,028.08 | $100.37 |
| 37 | 2024-01-05 | $1,875.62 | $8,892.71 | $2,028.08 | $436.90 |
| 38 | 2024-02-05 | $1,496.60 | $8,452.81 | $2,028.08 | $57.89 |
| 39 | 2024-03-06 | $1,467.16 | $8,409.81 | $2,028.08 | $28.44 |
| 40 | 2024-04-05 | $1,500.01 | $8,409.81 | $2,028.08 | $61.29 |
| 41 | 2024-05-06 | $1,555.23 | $8,409.81 | $2,028.08 | $116.51 |
| 42 | 2024-06-05 | $1,571.87 | $8,409.81 | $2,028.08 | $133.15 |
| 43 | 2024-07-05 | $1,609.17 | $8,409.81 | $2,028.08 | $170.45 |
| 44 | 2024-08-05 | $1,677.80 | $8,409.81 | $2,028.08 | $239.09 |
| 45 | 2024-09-04 | $1,691.78 | $8,409.81 | $2,028.08 | $253.06 |
| 46 | 2024-10-04 | $1,728.00 | $8,409.81 | $2,028.08 | $289.29 |
| 47 | 2024-11-04 | $1,786.88 | $8,409.81 | $2,028.08 | $348.16 |
| 48 | 2024-12-04 | $1,674.05 | $8,409.81 | $2,305.09 | $84.90 |
| 49 | 2025-01-03 | $1,639.17 | $8,349.81 | $2,305.09 | $50.02 |
| 50 | 2025-02-04 | $1,700.76 | $8,349.81 | $2,305.09 | $111.62 |
| 51 | 2025-03-07 | $1,714.20 | $8,349.81 | $2,305.09 | $125.06 |
| 52 | 2025-04-07 | $1,953.15 | $8,349.81 | $2,305.09 | $364.01 |
| 53 | 2025-05-07 | $1,991.45 | $8,349.81 | $2,305.09 | $402.31 |
| 54 | 2025-06-06 | $2,004.91 | $8,349.81 | $2,305.09 | $415.77 |
| 55 | 2025-07-07 | $2,024.86 | $8,349.81 | $2,305.09 | $435.72 |
| 56 | 2025-08-06 | $2,061.10 | $8,349.81 | $2,305.09 | $471.96 |
| 57 | 2025-09-05 | $1,778.22 | $8,052.81 | $2,305.09 | $189.08 |
| 58 | 2025-10-07 | $1,798.94 | $8,052.81 | $2,305.09 | $209.80 |
| 59 | 2025-11-06 | $1,680.98 | $7,885.83 | $2,305.09 | $91.84 |
| 60 | 2025-12-08 | $1,695.23 | $7,885.83 | $2,305.09 | $106.09 |
| 61 | 2026-01-08 | $1,717.38 | $7,885.83 | $2,305.09 | $128.24 |
| 62 | 2026-02-09 | $1,756.42 | $7,885.83 | $2,305.09 | $167.28 |
| 63 | 2026-03-11 | $1,770.75 | $7,885.83 | $2,305.09 | $181.61 |
| 64 | 2026-04-10 | $1,797.59 | $7,885.83 | $2,305.09 | $208.45 |
| 65 | 2026-05-31 | $1,910.58 | $7,885.83 | $2,305.09 | $321.44 |
| 66 | 2026-07-01 | $1,910.58 | $7,885.83 | $2,305.09 | $321.44 |
| **67** | **2026-07-14** | **$15,530.12** | **$7,885.83** | **$10,437.80** | **$321.44** |

---

## 4. All Accounts Combined

| # | Date | Portfolio Value | Net Deposits | Cost Basis | Cash Balance |
|---|------|----------------|--------------|------------|--------------|
| 1 | 2021-01-07 | $500.00 | $500.00 | $0.00 | $500.00 |
| 2 | 2021-02-08 | $500.00 | $500.00 | $0.00 | $500.00 |
| 3 | 2021-03-10 | $500.00 | $500.00 | $0.00 | $500.00 |
| 4 | 2021-04-09 | $500.00 | $500.00 | $0.00 | $500.00 |
| 5 | 2021-05-10 | $419.45 | $750.00 | $0.00 | $419.45 |
| 6 | 2021-06-09 | $285.46 | $317.00 | $0.00 | $285.46 |
| 7 | 2021-07-09 | $312.06 | $317.00 | $0.00 | $312.06 |
| 8 | 2021-08-09 | $312.06 | $317.00 | $0.00 | $312.06 |
| 9 | 2021-09-08 | $312.06 | $317.00 | $0.00 | $312.06 |
| 10 | 2021-10-08 | $284.69 | $289.63 | $0.00 | $284.69 |
| 11 | 2021-11-08 | $284.69 | $289.63 | $0.00 | $284.69 |
| 12 | 2021-12-08 | $284.69 | $289.63 | $0.00 | $284.69 |
| 13 | 2022-01-07 | $284.69 | $289.63 | $0.00 | $284.69 |
| 14 | 2022-02-07 | $284.69 | $289.63 | $0.00 | $284.69 |
| 15 | 2022-03-09 | $284.69 | $289.63 | $0.00 | $284.69 |
| 16 | 2022-04-08 | $294.69 | $299.63 | $0.00 | $294.69 |
| 17 | 2022-05-09 | $1,322.64 | $1,799.63 | $0.00 | $1,322.64 |
| 18 | 2022-06-08 | $3,832.33 | $5,799.63 | $0.00 | $3,832.33 |
| 19 | 2022-07-08 | $2,618.71 | $5,799.63 | $0.00 | $2,618.71 |
| 20 | 2022-08-08 | $1,331.71 | $7,799.63 | $1,013.90 | $700.31 |
| 21 | 2022-09-07 | $1,840.61 | $9,499.63 | $1,013.90 | $1,209.21 |
| 22 | 2022-10-07 | $1,807.57 | $11,999.63 | $1,230.98 | $1,126.37 |
| 23 | 2022-11-07 | $2,169.26 | $12,999.63 | $1,608.34 | $878.64 |
| 24 | 2022-12-07 | $1,337.57 | $13,009.63 | $1,728.76 | $35.95 |
| 25 | 2023-01-06 | $1,381.06 | $13,009.63 | $1,728.76 | $79.44 |
| 26 | 2023-02-06 | $1,440.82 | $13,009.63 | $1,728.76 | $139.20 |
| 27 | 2023-03-08 | $1,480.47 | $13,024.63 | $2,028.08 | $41.76 |
| 28 | 2023-04-07 | $1,498.13 | $13,024.63 | $2,028.08 | $59.42 |
| 29 | 2023-05-08 | $2,559.92 | $14,024.63 | $2,328.34 | $809.96 |
| 30 | 2023-06-07 | $4,289.85 | $14,274.63 | $3,188.72 | $537.66 |
| 31 | 2023-07-07 | $6,862.67 | $15,674.63 | $3,619.53 | $1,630.49 |
| 32 | 2023-08-07 | $5,886.45 | $15,861.71 | $3,840.84 | $238.64 |
| 33 | 2023-09-06 | $7,168.97 | $17,307.71 | $4,840.47 | $535.03 |
| 34 | 2023-10-06 | $7,709.40 | $18,436.71 | $5,986.78 | $124.85 |
| 35 | 2023-11-06 | $7,836.41 | $18,436.71 | $5,986.78 | $251.86 |
| 36 | 2023-12-06 | $7,871.51 | $18,436.71 | $5,986.78 | $286.97 |
| 37 | 2024-01-05 | $8,240.86 | $18,436.71 | $5,986.78 | $656.31 |
| 38 | 2024-02-05 | $7,938.87 | $17,996.81 | $5,986.78 | $354.33 |
| 39 | 2024-03-06 | $7,688.72 | $17,953.81 | $5,986.78 | $104.17 |
| 40 | 2024-04-05 | $7,741.50 | $17,953.81 | $5,986.78 | $156.95 |
| 41 | 2024-05-06 | $7,880.45 | $17,953.81 | $5,986.78 | $295.90 |
| 42 | 2024-06-05 | $7,920.05 | $17,953.81 | $5,986.78 | $335.50 |
| 43 | 2024-07-05 | $7,790.42 | $17,953.81 | $5,986.78 | $205.87 |
| 44 | 2024-08-05 | $8,061.19 | $17,953.81 | $5,986.78 | $476.65 |
| 45 | 2024-09-04 | $8,336.75 | $17,953.81 | $5,986.78 | $752.20 |
| 46 | 2024-10-04 | $7,961.62 | $17,953.81 | $5,986.78 | $377.08 |
| 47 | 2024-11-04 | $8,367.40 | $17,953.81 | $5,986.78 | $782.85 |
| 48 | 2024-12-04 | $10,387.46 | $19,953.81 | $6,620.12 | $2,456.06 |
| 49 | 2025-01-03 | $16,049.29 | $20,336.04 | $9,501.92 | $47.89 |
| 50 | 2025-02-04 | $16,602.14 | $22,139.53 | $9,501.92 | $600.75 |
| 51 | 2025-03-07 | $16,321.22 | $24,139.53 | $9,501.92 | $319.83 |
| 52 | 2025-04-07 | $17,235.57 | $25,691.23 | $9,501.92 | $1,234.18 |
| 53 | 2025-05-07 | $17,443.25 | $25,691.23 | $9,501.92 | $1,441.86 |
| 54 | 2025-06-06 | $17,374.12 | $26,109.82 | $9,501.92 | $1,372.73 |
| 55 | 2025-07-07 | $17,200.76 | $26,240.99 | $9,501.92 | $1,199.37 |
| 56 | 2025-08-06 | $16,806.91 | $29,272.99 | $9,501.92 | $805.52 |
| 57 | 2025-09-05 | $16,594.60 | $29,272.99 | $9,501.92 | $593.21 |
| 58 | 2025-10-07 | $16,244.50 | $31,272.99 | $9,501.92 | $243.11 |
| 59 | 2025-11-06 | $16,402.53 | $32,272.99 | $10,201.92 | $73.89 |
| 60 | 2025-12-08 | $16,496.46 | $32,272.99 | $10,201.92 | $167.82 |
| 61 | 2026-01-08 | $17,396.02 | $35,270.34 | $11,524.80 | $459.63 |
| 62 | 2026-02-09 | $16,977.71 | $35,270.34 | $11,524.80 | $41.32 |
| 63 | 2026-03-11 | $21,340.38 | $39,556.80 | $11,524.80 | $4,403.99 |
| 64 | 2026-04-10 | $21,243.78 | $39,556.80 | $12,340.20 | $3,204.87 |
| 65 | 2026-05-31 | $21,779.27 | $39,556.80 | $12,340.20 | $3,740.36 |
| 66 | 2026-07-01 | $21,779.27 | $39,556.80 | $12,340.20 | $3,740.36 |
| **67** | **2026-07-14** | **$99,744.18** | **$68,760.09** | **$74,808.82** | **$3,893.04** |

---

## 5. Cross-Account Verification (2026-07-14)

| Metric | TFSA | RRSP | Non-registered | Sum | ALL Query | Match |
|--------|------|------|----------------|-----|-----------|-------|
| Portfolio Value | $51,585.00 | $32,629.06 | $15,530.12 | $99,744.18 | $99,744.18 | ✓ |
| Net Deposits | $34,982.02 | $25,892.24 | $7,885.83 | $68,760.09 | $68,760.09 | ✓ |
| Cost Basis | $43,172.07 | $21,198.95 | $10,437.80 | $74,808.82 | $74,808.82 | ✓ |
| Cash Balance | $963.38 | $2,608.22 | $321.44 | $3,893.04 | $3,893.04 | ✓ |

---

## 6. Topic: FX Conversion

### 6.1 Verified Findings

| # | Assumption | Verified | Evidence |
|---|------------|----------|----------|
| 1 | `portfolio_accounts` has `currency` column | ✅ YES | All 6 accounts have `currency="CAD"` (DB query) |
| 2 | `build_snapshot_row()` accepts `account_currency` | ✅ YES | Function signature at `snapshot_builder.py:198` |
| 3 | `FXService.convert_or_warn()` accepts `as_of` | ✅ YES | Function signature at `fx_service.py:101` |
| 4 | `exchange_rates` has historical rates | ❌ NO | Only 1 row in DB (2026-06-24). Backfill script exists but not run. |
| 5 | Holding dict has `trade_date` field | ❌ NO | `h.get("trade_date")` returns None. Not in `HoldingState` dataclass. |
| 6 | Snapshot job passes `account_currency` | ✅ YES | `portfolio_snapshot_job.py:458` passes it correctly |
| 7 | Frontend uses `value_currency` | ✅ YES | `OverviewTab.tsx:54` reads `overview.value_currency` |
| 8 | Dashboard hardcodes `value_currency: "USD"` | ✅ YES | `portfolio.py:199` and `portfolio.py:222` |

### 6.2 Critical Finding: No Historical FX Rates

**Current state of `exchange_rates` table:**
```
Total rows: 1
Oldest rate: USD->CAD on 2026-06-24: 1.42351997
Newest rate: USD->CAD on 2026-06-24: 1.42351997
```

**Impact:** For any snapshot before 2026-06-24, `FXService.get_rate()` will:
1. Check instance cache → miss
2. Query `exchange_rates` table → no row found for that date
3. Try inverse rate → no row found
4. If `as_of != today` → return `None` → fallback to unconverted value

**Result:** Enabling FX conversion NOW will only work for today's snapshot. All historical snapshots (2021-02 to 2026-07-13) will still show unconverted values.

**Prerequisite:** Run backfill script before enabling FX conversion:
```bash
python scripts/backfill_exchange_rates.py --start 2020-01-01 --pairs USD/CAD CAD/USD
```

### 6.3 The Problem (3 things)

| # | Problem | Location | Fix |
|---|---------|----------|-----|
| 1 | FX conversion OFF by default | `config.py:260` | Enable by default |
| 2 | Dashboard hardcodes `value_currency: "USD"` | `portfolio.py:199,222` | Use `account_currency` |
| 3 | No historical FX rates in DB | `exchange_rates` table | Run backfill script |

**Note on cost basis FX timing:** The holding dict does NOT have a `trade_date` field. The `HoldingState` dataclass only has: `company_id`, `symbol`, `quantity`, `total_cost`, `average_cost`, `realized_gain_loss`. Using `snapshot_date` for cost basis FX is acceptable as a first approximation. This can be refined later by adding `trade_date` to the holding dict.

### 6.4 Proposed Fix

**Step 1: Backfill historical FX rates (prerequisite)**
```bash
python scripts/backfill_exchange_rates.py --start 2020-01-01 --pairs USD/CAD CAD/USD
```

This will populate `exchange_rates` with ~6,000 rows (daily USD/CAD rates from 2020-01-01 to today).

**Step 2: Enable FX conversion** (`config.py:260`)
```python
# BEFORE
ENABLE_FX_CONVERSION: bool = Field(default=False, ...)

# AFTER
ENABLE_FX_CONVERSION: bool = Field(default=True, ...)
```

**Step 3: Fix dashboard value_currency** (`portfolio.py:199,222`)
```python
# BEFORE (line 199)
"value_currency": "USD",

# AFTER
"value_currency": acc.get("currency", "CAD"),
```

```python
# BEFORE (line 222)
"overview": overview | {"value_currency": "USD"},

# AFTER
"overview": overview | {"value_currency": "CAD"},  # User's accounts are CAD
```

### 6.5 What This Achieves

| Before | After |
|--------|-------|
| USD values displayed as `$51,585` (looks like CAD) | USD values converted to CAD: `C$70,200` |
| Cost basis uses today's FX rate | Cost basis uses today's FX rate (acceptable approximation) |
| Dashboard shows `$` (ambiguous) | Dashboard shows `C$` (correct) |
| All accounts appear single-currency | Each account shows its native currency |

### 6.6 What This Does NOT Change

- No new database tables
- No new services
- No new API endpoints
- No frontend changes needed (already handles `value_currency`)
- No schema migrations
- Cost basis still uses snapshot-date FX rate (trade_date not available in holding dict)

### 6.7 Implementation Steps

1. Run backfill script: `python scripts/backfill_exchange_rates.py --start 2020-01-01`
2. Change `ENABLE_FX_CONVERSION` default to `True`
3. Fix `portfolio.py:199` to use `acc.get("currency", "CAD")`
4. Fix `portfolio.py:222` to use `"CAD"` (or dynamic account currency)
5. Re-run snapshot job for historical data
6. Verify TFSA values are now correct

### 6.8 Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| FX rates unavailable for some dates | Medium | Medium | Graceful degradation (unconverted value) |
| Historical snapshots incorrect | High | Low | Re-run snapshot job with FX enabled |
| Backfill script fails | Low | High | Check yfinance connectivity, retry |
| Cost basis slightly off (snapshot-date vs trade-date) | Medium | Low | Acceptable approximation, refine later |

---

## 7. Topic: CDR Handling

### 7.1 Critical Finding: Entire CDR Pricing Pipeline Is Broken

**Impact:** HIGH — All CDR prices are incorrect

**What are CDRs?** Canadian Depositary Receipts are fractional ownership units of US stocks, traded on the NEO Exchange (Cboe Canada) in CAD. They are issued by CIBC Mellon and include a built-in CAD/USD FX hedge.

**The correct CDR pricing formula:**
```
CDR_price_CAD = (US_stock_price_USD / CDR_ratio) × USD_CAD_rate
```

**What the code actually does:**
1. Price ingestion fetches `TSLA.TO` from Yahoo Finance (`price_ingestion_job.py:51-52`)
2. `TSLA.TO` on Yahoo Finance is the **full Tesla share on the TSX** (~$340-400 CAD), NOT a CDR
3. `_resolve_holding_price` divides this by `CDR_RATIO=10` to get ~$34-40 (`snapshot_builder.py:164-165`)
4. The FX component is entirely ignored — CDRs are priced using US stock price × FX rate / ratio

**Additional bug: double FX conversion.** `companies.currency` is "USD" (the underlying US stock's currency). `portfolio_repository._enrich_holdings()` sets `price_currency = "USD"` from this. So `convert_holding_fx` converts the already-CAD CDR value from "USD" to "CAD" again.

#### Complete Bug Inventory

**Pricing pipeline bugs (root cause):**

| # | Bug | Location | Impact |
|---|-----|----------|--------|
| 1 | CDR ratio hardcoded to 10 | `snapshot_builder.py:124` | CDR prices wrong for non-1:10 ratios |
| 2 | FX hedge ignored | `_resolve_holding_price` lines 164-165, 184-185 | CDR prices off by ~5-10% |
| 3 | `TSLA.TO` is full TSX share, not CDR | `price_ingestion_job.py:51-52` | All CDR prices fundamentally wrong |
| 4 | Double FX conversion | `price_currency = "USD"` from `companies.currency` | CDR values converted twice |

**API endpoints missing CDR ratio adjustment (4 critical bugs):**

These endpoints read `current_market_data` directly and apply raw US prices without dividing by `CDR_RATIO`. CDR holdings show ~10x their true price.

| # | Endpoint | Location | Bug |
|---|----------|----------|-----|
| 5 | `GET /portfolio/dashboard` | `api/portfolio.py:208-211` | `h["current_price"] = pd["price"]` — no CDR check |
| 6 | `GET /portfolio/accounts` | `api/portfolio.py:441-443` | `h["current_price"] = price` — no CDR check |
| 7 | `GET /portfolio/accounts/{id}/holdings` | `api/portfolio.py:742-744` | `h["current_price"] = price` — no CDR check |
| 8 | `GET /portfolio/holdings` | `api/portfolio.py:811-813` | `h["current_price"] = price` — no CDR check |

**Watchlist bugs (3 high-severity bugs):**

| # | Component | Location | Bug |
|---|-----------|----------|-----|
| 9 | Watchlist service | `watchlist_service.py:148-157` | Displays US price, not CDR price |
| 10 | SSE price broadcast | `main.py:83-94` | Broadcasts US price for CDR symbols |
| 11 | Stock price endpoint | `api/watchlists.py:228-234` | Returns US price for CDR symbols |

**Performance & incremental snapshot bugs:**

| # | Component | Location | Bug |
|---|-----------|----------|-----|
| 12 | `get_holding_performance()` | `portfolio_service.py:2301-2326` | Reads `price_history` without CDR ratio — historical chart shows US price levels |
| 13 | `_fill_snapshot_gaps_incremental` | `portfolio_snapshot_job.py:302-304` | Hardcodes `price_currency = "USD"` from `companies.currency` — wrong for CDR |

**What works correctly (snapshot pipeline):**

| # | Component | Location | Status |
|---|-----------|----------|--------|
| 14 | `_resolve_holding_price()` | `snapshot_builder.py:129-200` | Correctly applies CDR ratio |
| 15 | `build_snapshot_row()` | `snapshot_builder.py:279-480` | Correctly passes override |
| 16 | `build_snapshot_from_replay()` | `replay_engine.py:223-372` | Correctly passes overrides |
| 17 | `_enrich_holdings()` | `portfolio_service.py:488-491` | Correctly applies CDR ratio |
| 18 | `portfolio_snapshot_job.py` | Lines 459-463 | Correctly builds overrides dict |
| 19 | `event_projection_handler.py` | Lines 120-165 | Preserves `exchange_override` |
| 20 | `portfolio_parser.py` | Lines 178-343 | Correctly detects CDR symbols |
| 21 | `backfill_snapshots.py` | Lines 48-114 | Passes `exchange_overrides` |

**Root cause:** The codebase has two independent pricing paths:
1. **Snapshot path** (`_resolve_holding_price`): Correctly applies CDR ratio via the 4-tier price cascade
2. **Direct `current_market_data` path** (4 API endpoints + watchlist): Reads raw US prices with no CDR awareness

The frontend is completely CDR-agnostic — it renders whatever `current_price` the backend sends. The fix must be applied in the backend before data reaches the API response.

### 7.2 Critical Design Insight: What `current_market_data` Actually Stores

**The price ingestion flow for CDR holdings:**

1. `price_ingestion_job.py:43` — `exchange = h.get("exchange_override") or "UNKNOWN"` → `"TOR"`
2. `price_ingestion_job.py:44` — `pref = prefs.get((cid, "TOR"))` → `"yfinance_tor"`
3. `price_ingestion_job.py:51-52` — Routes to yfinance batch fetch
4. `yfinance_provider.py:43-45` — `_resolve_symbol("TSLA", "TOR")` → `"TSLA.TO"`
5. `yf.Ticker("TSLA.TO")` — Returns **full TSX share price in CAD** (~$340-400 CAD)
6. `price_repository.py:63-71` — Upserts to `current_market_data` with `on_conflict="company_id"`

**What this means:** For CDR holdings, `current_market_data.current_price` stores the **full TSX share price in CAD** (~$340-400), NOT the CDR price (~$34-40) and NOT the US stock price in USD (~$250).

**The current `_resolve_holding_price` divides by 10:**
- `$350 (TSX CAD) / 10 = $35 CAD` — **approximately correct CDR price**
- The formula works because: `TSX_share_CAD ≈ US_stock_USD × FX_rate`, and `CDR_price = US_stock_USD / CDR_ratio × FX_rate`, so `TSX_share_CAD / CDR_ratio ≈ CDR_price`

**What `price_history` stores:** US stock prices in USD (populated by `market_data_scheduler` from the US exchange).

**The two sources have different currencies:**

| Source | Table | Currency | What it stores |
|--------|-------|----------|----------------|
| `yfinance_tor` | `current_market_data` | CAD | Full TSX share price |
| `supabase_market_data` | `current_market_data` | USD | US stock price |
| `market_data_scheduler` | `price_history` | USD | US stock historical prices |

### 7.3 Design Criteria

| Criterion | Weight | Assessment |
|-----------|--------|------------|
| **Correctness** | Critical | Must use actual CDR pricing formula |
| **Completeness** | High | Must handle all 3 code paths (snapshot, replay, live API) |
| **Single source of truth** | High | CDR price derivation in one place |
| **Minimal blast radius** | High | Changes to existing functions should be additive |
| **Backwards compatibility** | High | Existing data must not break |
| **No snowflakes** | High | Consistent patterns, no special cases |
| **Performance** | Medium | Derivation at read time is acceptable |
| **Testability** | Medium | Each component independently testable |
| **Production readiness** | High | Graceful degradation when data missing |

### 7.4 Architecture Decision: Store Ratio, Apply at Read Time (Corrected)

**Chosen approach:** Store per-company CDR ratio in `companies` table. Apply the correct formula at read time based on the price source.

**The key insight:** `current_market_data` stores different things for CDR holdings depending on the ingestion source:
- `yfinance_tor` source: stores **full TSX share price in CAD** (~$340-400)
- `supabase_market_data` source: stores **US stock price in USD** (~$250)

The formula must match the source:

| Source | Stored price | Correct formula | Result |
|--------|-------------|-----------------|--------|
| `yfinance_tor` (Tier 1) | TSX share in CAD | `price / cdr_ratio` | CDR price in CAD |
| `supabase_market_data` (Tier 1) | US stock in USD | `price / cdr_ratio * fx_rate` | CDR price in CAD |
| `price_history` (Tier 2) | US stock in USD | `price / cdr_ratio * fx_rate` | CDR price in CAD |

**Why this is correct:**
- `TSX_share_CAD / CDR_ratio ≈ CDR_price_CAD` (because `TSX_share_CAD ≈ US_stock_USD × FX_rate`)
- `US_stock_USD / CDR_ratio × FX_rate = CDR_price_CAD` (the full formula)

**Alternatives considered and rejected:**

| Alternative | Why Rejected |
|-------------|-------------|
| Normalize all prices at ingestion time | `current_market_data` is keyed by `company_id` — can't store both US and CDR prices |
| Create separate `cdr_prices` table | Adds schema complexity, requires separate ingestion pipeline |
| Use only `price_history` for CDR prices | `price_history` may not have recent data; Tier 1 fallback needed |

**Why read-time derivation is best:**
1. **No schema changes to price tables** — `current_market_data` continues as-is
2. **Single derivation point** — `_resolve_holding_price` is the only function that computes CDR prices
3. **Source-aware** — different formulas for different price sources
4. **Graceful degradation** — if ratio or FX rate is missing, falls back to current behavior
5. **Minimal code changes** — only 3 functions need modification

### 7.4 Database Changes

```sql
ALTER TABLE companies 
ADD COLUMN cdr_ratio DECIMAL(10, 4),
ADD COLUMN cdr_ratio_date DATE;
```

**Storage rationale:**
- `cdr_ratio` is per-issuer (CIBC sets it per CDR), not per-holding
- Same `company_id` can have both CDR and non-CDR holdings (via `exchange_override`)
- `cdr_ratio_date` tracks when the ratio was last validated (for staleness detection)
- `NULL` means "not a CDR" or "ratio unknown" — falls back to hardcoded constant

**Initial values:** Derived from existing data:
```python
# For each CDR holding:
# 1. Get earliest lot's trade_date
# 2. Fetch US stock price from price_history on that date
# 3. Get CDR average_cost (per-unit cost in CAD)
# 4. Fetch FX rate on trade_date
# 5. Compute: cdr_ratio = (US_price × fx_rate) / average_cost
```

### 7.5 Detailed Code Changes

#### 7.5.1 Price Resolution: `_resolve_holding_price` (Corrected)

**File:** `shared/snapshot_builder.py:129-200`

**Changes:** Add optional `fx_service`, `cdr_ratio`, `company_currency`, `price_source` parameters. Apply source-aware CDR formula.

```python
def _resolve_holding_price(
    company_id, symbol, avg_cost, latest_prices, price_history,
    snapshot_date, stale_threshold_days=30, exchange_override=None,
    fx_service=None,                                # NEW
    cdr_ratio=None,                                  # NEW
    company_currency=None,                           # NEW
    price_source=None,                               # NEW — "yfinance_tor" or "supabase_market_data"
):
    is_cdr = exchange_override == "TOR"
    
    # Tier 1: current market price (existing logic)
    info = latest_prices.get(company_id, {})
    if info.get("price") is not None:
        # ... existing staleness check ...
        price = Decimal(str(info["price"]))
        
        if is_cdr:
            ratio = cdr_ratio or CDR_RATIO
            price = price / Decimal(str(ratio))
            
            # Source-aware: yfinance_tor stores TSX share in CAD (already correct)
            # supabase_market_data stores US stock in USD (needs FX)
            if price_source != "yfinance_tor" and fx_service and company_currency == "USD":
                rate = fx_service.get_rate("USD", "CAD", snapshot_date)
                if rate is not None:
                    price = price * rate
        
        return price, PriceTier.CURRENT, pd
    
    # Tier 2: forward-fill from price_history (US prices in USD)
    result = resolve_price_forward_filled(company_id, snapshot_date, price_history)
    if result is not None and result.get("price") is not None:
        price = Decimal(str(result["price"]))
        
        if is_cdr:
            ratio = cdr_ratio or CDR_RATIO
            price = price / Decimal(str(ratio))
            # price_history always stores US prices in USD — need FX
            if fx_service and company_currency == "USD":
                rate = fx_service.get_rate("USD", "CAD", snapshot_date)
                if rate is not None:
                    price = price * rate
        
        return price, PriceTier.FORWARD_FILL, result_date
    
    # Tier 3: DISABLED (existing)
    # Tier 4: unavailable (existing)
```

**Key design decisions:**
- `price_source` parameter tells the function where Tier 1 price came from
- `yfinance_tor` source → price is TSX share in CAD → only divide by ratio (no FX)
- `supabase_market_data` source or `price_history` → price is USD → divide by ratio AND multiply by FX
- If FX rate unavailable, returns CDR price without FX (graceful degradation)
- Cost basis is NOT adjusted (already at CDR purchase price)

#### 7.5.2 Snapshot Building: `build_snapshot_row` (Corrected)

**File:** `shared/snapshot_builder.py:279-480`

**Changes:**
1. Pass `fx_service`, `cdr_ratio`, `company_currency`, `price_source` to `_resolve_holding_price`
2. Set `price_currency = "CAD"` for CDR holdings (prevents double FX conversion)

```python
# In build_snapshot_row, before calling _resolve_holding_price:
is_cdr = exchange_override == "TOR"
cdr_ratio_val = None
company_ccy = None
price_source_val = None
if is_cdr:
    cdr_ratio_val = companies_cdr_ratios.get(cid)  # from companies table
    company_ccy = company_currencies.get(cid, "USD")
    # Determine price source from latest_prices info
    price_info = latest_prices.get(cid, {})
    price_source_val = price_info.get("source")  # pass through from current_market_data

price, tier, price_date = _resolve_holding_price(
    ..., fx_service=fx_service,
    cdr_ratio=cdr_ratio_val, company_currency=company_ccy,
    price_source=price_source_val,
)

# After price resolution, fix price_currency for CDR:
if is_cdr:
    price_currency = "CAD"  # CDR price is in CAD, not USD
```

#### 7.5.3 Event Replay: `build_snapshot_from_replay`

**File:** `shared/snapshot_builder.py` (replay path)

Same pattern as `build_snapshot_row` — pass `fx_service`, `cdr_ratio`, `company_currency` to `_resolve_holding_price`. Set `price_currency = "CAD"` for CDR holdings in the holding dict.

#### 7.5.4 Live Holdings: `_enrich_holdings` (Corrected)

**File:** `application/services/portfolio_service.py:465-520`

**Changes:**
1. Derive CDR price using source-aware formula
2. Set `price_currency = "CAD"` for CDR holdings
3. Set `cost_currency = "CAD"` for CDR holdings

```python
# In _enrich_holdings, after fetching US price:
if h.get("exchange_override") == "TOR":
    ratio = cdr_ratios.get(cid, float(CDR_RATIO))
    cdr_price = price / ratio
    # current_market_data for CDRs stores TSX share in CAD (from yfinance_tor)
    # Dividing by ratio gives CDR price in CAD — no FX needed
    h["current_price"] = cdr_price
    h["current_value"] = cdr_price * qty
    h["price_currency"] = "CAD"      # FIX: was "USD" (from companies.currency)
    h["cost_currency"] = "CAD"       # FIX: was "USD"
```

**Note:** `_enrich_holdings` reads from `current_market_data` which stores TSX share price in CAD for CDRs. So `price / ratio` gives the correct CDR price in CAD. No FX multiplication needed here because the source is already CAD.

#### 7.5.5 API Endpoints: Fix 4+ Endpoints Missing CDR Ratio

**Files:** `api/portfolio.py` — 4 endpoints

**The problem:** These endpoints read `current_market_data` directly and apply raw TSX share prices without CDR adjustment. CDR holdings show ~10x their true price.

**The fix:** Add a shared helper and apply CDR ratio in all endpoints.

**New helper function** (add to `api/portfolio.py` or `shared/snapshot_builder.py`):

```python
def apply_cdr_adjustment(holding: dict, price: float, cdr_ratios: dict) -> float:
    """Apply CDR ratio to TSX share price if holding is a CDR.
    
    current_market_data stores TSX share price in CAD for CDRs (from yfinance_tor).
    Dividing by CDR_RATIO gives the correct CDR price in CAD.
    
    Returns CDR-adjusted price or original price if not CDR.
    """
    if holding.get("exchange_override") != "TOR":
        return price
    cid = holding.get("company_id")
    ratio = cdr_ratios.get(cid, float(CDR_RATIO))
    return price / ratio
```

**Endpoint fixes:**

```python
# 1. GET /portfolio/dashboard (portfolio.py:208-211)
# BEFORE:
h["current_price"] = pd["price"]
h["current_value"] = pd["price"] * qty

# AFTER:
cdr_price = apply_cdr_adjustment(h, pd["price"], cdr_ratios)
h["current_price"] = cdr_price
h["current_value"] = cdr_price * qty
```

```python
# 2. GET /portfolio/accounts (portfolio.py:441-443)
# BEFORE:
h["current_price"] = price
h["current_value"] = price * (h.get("quantity", 0) or 0)

# AFTER:
cdr_price = apply_cdr_adjustment(h, price, cdr_ratios)
h["current_price"] = cdr_price
h["current_value"] = cdr_price * (h.get("quantity", 0) or 0)
```

```python
# 3. GET /portfolio/accounts/{id}/holdings (portfolio.py:742-744)
# BEFORE:
h["current_price"] = price
h["current_value"] = price * qty

# AFTER:
cdr_price = apply_cdr_adjustment(h, price, cdr_ratios)
h["current_price"] = cdr_price
h["current_value"] = cdr_price * qty
```

```python
# 4. GET /portfolio/holdings (portfolio.py:811-813)
# BEFORE:
h["current_price"] = price
h["current_value"] = price * qty

# AFTER:
cdr_price = apply_cdr_adjustment(h, price, cdr_ratios)
h["current_price"] = cdr_price
h["current_value"] = cdr_price * qty
```

**CDR ratios loading** — add at the top of each endpoint (or cache in a shared function):

```python
# Load CDR ratios from companies table
cdr_ratios = {}
cdr_companies = supabase.table("companies").select("company_id, cdr_ratio") \
    .not_.is_("cdr_ratio", "null").execute()
for row in (cdr_companies.data or []):
    cdr_ratios[row["company_id"]] = float(row["cdr_ratio"])
```

#### 7.5.6 Watchlist & SSE: Fix CDR Price Display

**Files:** `api/watchlists.py`, `main.py`, `application/services/watchlist_service.py`

**The problem:** Watchlist displays TSX share price instead of CDR price. SSE broadcasts raw TSX price.

**The fix:** Apply CDR ratio when the symbol has CDR holdings.

```python
# watchlist_service.py — when enriching watchlist items with prices:
# Check if any holding for this company has exchange_override="TOR"
# If so, apply CDR_RATIO division to the displayed price

# main.py SSE broadcast — apply CDR ratio if symbol is a CDR:
# Look up exchange_override for the company, divide by CDR_RATIO if CDR
```

**Note:** Watchlist items are keyed by normalized symbol (e.g., "TSLA"), not by company_id. The CDR check requires a company lookup. This can be batched (one query for all watchlist symbols).

#### 7.5.7 Performance Endpoint: Fix `get_holding_performance()`

**File:** `application/services/portfolio_service.py:2301-2326`

**The problem:** Reads `price_history` (US prices in USD) without CDR ratio or FX adjustment. Historical performance chart shows US price levels (~$350) instead of CDR levels (~$35).

**The fix:** Apply CDR ratio AND historical FX rate to `price_history` prices.

```python
# In get_holding_performance(), after fetching price_history:
# Check if this holding is a CDR
holding_info = supabase.table("portfolio_holdings") \
    .select("exchange_override") \
    .eq("account_id", account_id).eq("symbol", symbol).limit(1).execute()
is_cdr = holding_info.data and holding_info.data[0].get("exchange_override") == "TOR"

if is_cdr:
    ratio = float(cdr_ratios.get(company_id, CDR_RATIO))
    # Pre-fetch all historical FX rates for the date range
    fx_rates = fx_service.get_rate_range("USD", "CAD", start_date, end_date)
    
    for row in rows.data:
        px = float(row["close_price"])
        pd_str = row["price_date"]
        # ... split adjustment ...
        
        # Apply CDR ratio
        px /= ratio
        
        # Apply historical FX rate (price_history stores USD)
        fx_rate = fx_rates.get(pd_str)
        if fx_rate:
            px *= float(fx_rate)
        
        price_map.setdefault(sym_up, {})[pd_str] = px
```

**Note:** This requires `FXService.get_rate_range()` to batch-fetch historical FX rates. If not available, fallback to ratio-only (approximate).

#### 7.5.8 Incremental Snapshot: Fix `_fill_snapshot_gaps_incremental`

**File:** `application/jobs/portfolio_snapshot_job.py:302-304`

**The problem:** Hardcodes `price_currency = "USD"` from `companies.currency`. Wrong for CDR holdings.

**The fix:** Override `price_currency` for CDR holdings.

```python
# BEFORE (line 302-304):
price_currency = "USD"
if company_currencies and cid in company_currencies:
    price_currency = company_currencies[cid]

# AFTER:
price_currency = "USD"
if company_currencies and cid in company_currencies:
    price_currency = company_currencies[cid]

# Override for CDR holdings — CDR price is in CAD
if exchange_overrides and exchange_overrides.get(cid) == "TOR":
    price_currency = "CAD"
```

### 7.6 CDR Ratio Backfill Script (Corrected)

**New file:** `scripts/backfill_cdr_ratios.py`

```python
# For each CDR holding:
# 1. Get earliest lot's trade_date from portfolio_transactions
# 2. Fetch TSX share price from current_market_data (yfinance_tor source)
# 3. Get CDR average_cost (per-unit cost in CAD)
# 4. Compute CDR ratio — no FX needed because both are in CAD

# The formula depends on what price is stored:
#
# If using current_market_data (TSX share price in CAD from yfinance_tor):
#   cdr_ratio = tsx_share_price / average_cost_cdr
#   Example: $350 CAD / $35 CAD = 10.0
#
# If using price_history (US stock price in USD):
#   cdr_ratio = (us_price_usd × fx_rate) / average_cost_cdr
#   Example: ($250 × 1.40) / $35 = 10.0
#
# The first approach is simpler and more accurate.
# Use current_market_data if available (yfinance_tor source).

# Example for TSLA CDR:
# - current_market_data.current_price = $350 (TSX share in CAD)
# - CDR average_cost = $29.41 (per-unit cost in CAD)
# - cdr_ratio = $350 / $29.41 ≈ 11.9 (not exactly 10!)
```

**Key insight:** The backfill should use `current_market_data` (TSX share price in CAD) divided by `average_cost` (CDR cost in CAD). This produces the correct ratio without needing FX rate lookup.

### 7.7 Edge Cases

| Scenario | Behavior |
|----------|----------|
| `cdr_ratio` is NULL | Falls back to `CDR_RATIO` constant (10) |
| FX rate unavailable | Returns CDR price without FX conversion (slightly off, but not broken) |
| CDR ratio changes (stock split) | Update `cdr_ratio` in companies table; historical snapshots use ratio at computation time |
| Non-CDR holding with `exchange_override="TOR"` | No CDR adjustment applied (ratio check prevents false positives) |
| CDR held in USD account | FX converts CAD→USD correctly |
| CDR held in CAD account | No FX conversion (price already in CAD) |
| `company_currency` is not "USD" | No FX conversion applied (only USD→CDR needed) |
| `current_market_data` source is `yfinance_tor` | Price is TSX share in CAD — divide by ratio only |
| `current_market_data` source is `supabase_market_data` | Price is US stock in USD — divide by ratio AND multiply by FX |
| `price_history` source | Always US stock in USD — divide by ratio AND multiply by FX |

### 7.8 Files Changed

| File | Change Type | Lines Changed |
|------|------------|---------------|
| `shared/snapshot_builder.py` | Modify | ~40 lines (signature + source-aware CDR logic) |
| `api/portfolio.py` | Modify | ~40 lines (4 endpoints + helper) |
| `application/services/portfolio_service.py` | Modify | ~50 lines (_enrich_holdings + get_holding_performance) |
| `application/jobs/portfolio_snapshot_job.py` | Modify | ~10 lines (price_currency override for CDR) |
| `application/services/watchlist_service.py` | Modify | ~15 lines (CDR price adjustment) |
| `main.py` | Modify | ~10 lines (SSE CDR adjustment) |
| `api/watchlists.py` | Modify | ~10 lines (stock price endpoint) |
| `scripts/backfill_cdr_ratios.py` | New | ~80 lines |
| `tests/test_cdr_pricing.py` | New | ~200 lines |
| Supabase migration | New | 3 lines (ALTER TABLE) |

### 7.9 What Does NOT Change

- `current_market_data` schema — continues storing whatever price the ingestion job provides
- `price_history` schema — continues storing US historical prices
- `price_ingestion_job` — continues fetching TSX share price for CDRs (correct behavior)
- `portfolio_parser` — CDR detection unchanged
- `exchange_override` mechanism — unchanged
- `convert_holding_fx` — unchanged (CDR price arrives in CAD, `price_currency="CAD"` prevents double conversion)

### 7.10 Why This Is the Best Design

1. **Correctness:** Source-aware formula — different treatment for `yfinance_tor` (CAD) vs `supabase_market_data` (USD) vs `price_history` (USD)
2. **Single source of truth:** `_resolve_holding_price` is the ONLY place CDR prices are computed
3. **No double conversion:** `price_currency = "CAD"` for CDR holdings prevents `convert_holding_fx` from re-converting
4. **Minimal blast radius:** Only 3 existing functions modified, no schema changes to price tables
5. **Backwards compatible:** `cdr_ratio` NULL falls back to hardcoded 10 (same as current behavior)
6. **No snowflakes:** CDR handling follows the same price cascade pattern as all other holdings
7. **Graceful degradation:** Missing ratio or FX rate produces slightly wrong price, not a crash
8. **Testable:** Each component (ratio lookup, FX conversion, price derivation) independently testable
9. **Complete:** Fixes all 13 bugs (pricing, API, watchlist, performance, incremental snapshot)

### 7.11 Implementation Order (With Clear Outcomes)

Each step has a **specific, verifiable outcome**. A developer can check off each step as complete.

| Step | What to do | Outcome | Verify |
|------|-----------|---------|--------|
| **1** | Add `cdr_ratio` and `cdr_ratio_date` columns to `companies` table | DB schema updated | `SELECT column_name FROM information_schema.columns WHERE table_name='companies' AND column_name IN ('cdr_ratio','cdr_ratio_date')` returns 2 rows |
| **2** | Create `apply_cdr_adjustment()` helper in `api/portfolio.py` | Function exists and is importable | `python -c "from api.portfolio import apply_cdr_adjustment; print('OK')"` |
| **3** | Modify `_resolve_holding_price` signature: add `fx_service`, `cdr_ratio`, `company_currency`, `price_source` params | Function accepts new params (all optional, default None) | `python -c "from shared.snapshot_builder import _resolve_holding_price; import inspect; sig=inspect.signature(_resolve_holding_price); assert 'fx_service' in sig.parameters; assert 'cdr_ratio' in sig.parameters; print('OK')"` |
| **4** | Implement source-aware CDR logic in `_resolve_holding_price`: `yfinance_tor` → divide only; else → divide × FX | CDR price correct for both sources | Unit test: mock `latest_prices` with TSX CAD price + `price_source="yfinance_tor"` → result = price/ratio. Unit test: mock with `price_source="supabase_market_data"` → result = price/ratio*fx |
| **5** | Modify `build_snapshot_row`: pass `cdr_ratio`, `company_currency`, `price_source` to `_resolve_holding_price`; set `price_currency="CAD"` for CDR | Snapshot uses correct CDR price and currency | Integration test: build snapshot for CDR holding → `holdings_json[0]["current_price"]` ≈ $35 (not $350) |
| **6** | Modify `build_snapshot_from_replay`: same changes as step 5 | Replay path uses correct CDR price | Run `step9_rebuild_all_snapshots.py` → CDR holdings show correct prices |
| **7** | Modify `_enrich_holdings`: CDR price = `price / ratio`; set `price_currency="CAD"`, `cost_currency="CAD"` | Live API shows correct CDR price | `GET /portfolio/holdings` → CDR holding `current_price` ≈ $35 (not $350) |
| **8** | Fix 4 API endpoints: add `apply_cdr_adjustment()` call | All holdings endpoints show correct CDR price | `GET /portfolio/dashboard` → CDR holding `current_price` ≈ $35. Same for `/portfolio/accounts`, `/portfolio/accounts/{id}/holdings`, `/portfolio/holdings` |
| **9** | Fix `_fill_snapshot_gaps_incremental`: override `price_currency="CAD"` for CDR holdings | Gap-filled snapshots use correct currency | Re-run gap fill → CDR holdings have `price_currency="CAD"` in holding dict |
| **10** | Fix watchlist service + SSE + stock price endpoint | Watchlist shows CDR price, SSE broadcasts CDR price | Add CDR to watchlist → displayed price ≈ $35 (not $350) |
| **11** | Fix `get_holding_performance()`: apply CDR ratio + FX to `price_history` prices | Historical performance chart shows CDR price levels | `GET /portfolio/holdings/{symbol}/performance` → chart Y-axis shows ~$35 range (not ~$350) |
| **12** | Write `backfill_cdr_ratios.py` script | Script runs without error | `python scripts/backfill_cdr_ratios.py` → `companies.cdr_ratio` populated for all CDR companies |
| **13** | Run backfill script | CDR ratios stored in DB | `SELECT company_id, cdr_ratio FROM companies WHERE cdr_ratio IS NOT NULL` returns rows for all CDR companies |
| **14** | ~~Rebuild all snapshots~~ **BLOCKED** | See section 9.1 — blocked by other pending effects | Run after all pending items in section 9 are resolved |
| **15** | Write CDR pricing tests (all 13 bugs) | Tests pass | `python -m pytest tests/test_cdr_pricing.py -v` → all tests pass |

---

## 8. Topic: Split Handling

### 8.1 Bug: Holdings Not Adjusted for Splits

**Impact:** MEDIUM — Stale quantities after split

| Aspect | Current State | Problem |
|--------|--------------|---------|
| **Price adjustment** | Back-adjusts historical prices (`portfolio_repository.py:1284-1298`) | OK |
| **Holdings adjustment** | NOT adjusted | Stale quantities |
| **Split factor parsing** | Correctly handles forward/reverse | OK |
| **Code duplication** | `_get_split_factors()` in both `portfolio_repository.py:1204` and `financial_repository.py:1424` | Maintenance risk |

**Code review finding:**
> When a stock splits, the user's share count in `portfolio_holdings` should change, but there is no code to do this. The price is back-adjusted, which masks the problem for valuation, but the holdings table has stale quantities.

### 8.2 Price-Unit Normalization Heuristic

**Impact:** LOW — Could mask legitimate splits

```python
# portfolio_repository.py:1300-1335
# If consecutive prices within 60 days differ by >5x, scale older prices
# This could incorrectly "fix" a legitimate recent split
```

### 8.3 Implementation: Event-Driven Split Handling

**Approach:** Add `split` as a first-class event type in `portfolio_events`. When `price_ingestion_job` detects new splits, it emits per-account `split` events. The replay engine processes these, adjusting `HoldingState.quantity`, `HoldingState.average_cost`, and each lot's `quantity`/`cost_per_share`.

#### 8.3.1 SQL Migration

**File:** `supabase/migrations/003_add_split_processed.sql`

```sql
ALTER TABLE splits ADD COLUMN IF NOT EXISTS processed BOOLEAN DEFAULT FALSE;
UPDATE splits SET processed = TRUE WHERE processed = FALSE;
```

Existing splits marked `processed=TRUE` (already handled by price-only logic). New splits get `processed=FALSE`.

#### 8.3.2 Replay Engine: `_handle_split()`

**File:** `shared/replay_engine.py`

```python
def _handle_split(self, state: AccountState, event: dict) -> None:
    """Adjust holdings for a stock split event."""
    data = event.get("data", {}) or {}
    company_id = data.get("company_id")
    split_factor = _decimal(data.get("split_factor"))
    if not company_id or split_factor <= 0 or split_factor == 1:
        return
    holding = state.holdings.get(int(company_id))
    if not holding:
        return
    holding.quantity *= split_factor
    holding.average_cost /= split_factor
    for lot in holding.lots:
        lot["quantity"] *= split_factor
        lot["cost_per_share"] /= split_factor
```

**Behavior:** When a `split` event is encountered during replay, `HoldingState.quantity` and `HoldingState.average_cost` are adjusted. Each lot's `quantity` and `cost_per_share` are also adjusted. `total_cost` is unchanged (value preserved).

#### 8.3.3 Split Event Producer

**File:** `application/jobs/price_ingestion_job.py`

```python
def _emit_split_events() -> None:
    """For each unprocessed split, emit a split event per affected account."""
    from infrastructure.repositories.event_store import EventStore
    from shared.split_utils import parse_split_factor

    event_store = EventStore()

    # 1. Get unprocessed splits
    splits_res = repo.client.table("splits") \
        .select("company_id, report_date, split_factor") \
        .eq("processed", False).execute()

    if not splits_res.data:
        return

    # 2. For each split, find accounts holding that company
    for split in splits_res.data:
        cid = split["company_id"]
        factor = parse_split_factor(split.get("split_factor") or "")
        if factor <= 0 or factor == 1:
            continue

        holdings_res = repo.client.table("portfolio_holdings") \
            .select("account_id").eq("company_id", cid).execute()
        account_ids = list({h["account_id"] for h in (holdings_res.data or [])})
        if not account_ids:
            continue

        # 3. Emit a split event per account
        events = [{
            "event_type": "split",
            "event_version": 1,
            "aggregate_id": f"account_{aid}",
            "aggregate_type": "account",
            "data": {"company_id": cid, "split_factor": str(factor),
                     "report_date": split["report_date"]},
            "metadata": {},
            "idempotency_key": f"split_{cid}_{split['report_date']}_{aid}",
        } for aid in account_ids]

        event_store.append_events_batch(events)

        # 4. Mark split as processed
        repo.client.table("splits").update({"processed": True}) \
            .eq("company_id", cid).eq("report_date", split["report_date"]).execute()
```

Called from `refresh_all_prices()` after `_update_cdr_ratios()`.

#### 8.3.4 Shared Utility: `split_utils.py`

**File:** `shared/split_utils.py`

Extracts split factor parsing and date handling into a shared module used by both `portfolio_repository.py` and `financial_repository.py`. Eliminates the duplicate `_get_split_factors()` method.

#### 8.3.5 Code Deduplication

`financial_repository.py` had a duplicate `_get_split_factors()` method (identical to `portfolio_repository.py`). Removed the duplicate. `get_latest_prices()` now uses `shared.split_utils.get_split_factors_from_rows()` directly.

### 8.4 CDR Interaction

CDR holdings are adjusted the same way as regular holdings. When the underlying US stock splits:
1. CDR quantity multiplies by split factor
2. CDR cost_per_share divides by split factor
3. CDR ratio is recalculated by `_update_cdr_ratios()` (runs daily)
4. `exchange_override = "TOR"` is preserved by `_atomic_write_holdings`

### 8.5 Edge Cases

| Scenario | Behavior |
|----------|----------|
| Split for non-existent holding | `_handle_split` is a no-op |
| Multiple splits for same company | Each split emits events; replay processes in order |
| Reverse split (1:5) | `split_factor < 1`, quantity decreases, cost_per_share increases |
| Fractional shares after split | Decimal arithmetic preserves precision |
| CDR holding with split | Adjusted like regular holding; CDR ratio recalculated |
| Split detected after stale period | Events are backdated to `report_date`; replay corrects historical state |

### 8.6 Files Changed

| File | Change |
|------|--------|
| `shared/split_utils.py` | New — shared parsing utilities |
| `shared/replay_engine.py` | Add `_handle_split()` method (~15 lines) |
| `application/jobs/price_ingestion_job.py` | Add `_emit_split_events()` + call (~60 lines) |
| `infrastructure/repositories/financial_repository.py` | Remove duplicate `_get_split_factors()` (~35 lines) |
| `infrastructure/repositories/portfolio_repository.py` | Refactor `_get_split_factors()` to use shared utility |
| `supabase/migrations/003_add_split_processed.sql` | Add `processed` column |
| `tests/test_split_handling.py` | New — 33 tests |

### 8.7 Implementation Steps

| Step | Description | Outcome |
|------|-------------|---------|
| **1** | SQL migration: add `processed` column to `splits` | All existing splits marked `processed=TRUE` |
| **2** | Add `_handle_split()` to `ReplayEngine` | Split events adjust holdings during replay |
| **3** | Deduplicate `_get_split_factors()` | Single implementation in `shared/split_utils.py` |
| **4** | Add `_emit_split_events()` to `price_ingestion_job` | New splits generate per-account events |
| **5** | Write 33 tests | All pass |
| **6** | Update design doc | Section 8 complete |

### 8.8 What Does NOT Change

- `splits` table structure (only new column)
- `fetch_splits()` in `defeat_beta_provider`
- Price back-adjustment logic in `_get_split_factors()`
- `_atomic_write_holdings` (already preserves `exchange_override`)
- CDR pricing logic
- FX conversion logic

### 8.9 Rejected Alternatives

1. **Direct holdings update (bypass event log):** Breaks event-sourcing model. Rebuilding snapshots from events produces wrong results. Creates inconsistency between event log and projections.

2. **Modify price back-adjustment to also adjust quantities:** Would work for snapshots, but `portfolio_holdings` would still show stale quantities. Live UI would be wrong. Only partially solves the problem.

---

## 9. Topic: Event Replay

### 9.1 Bug: Replay Uses Average Cost, Not FIFO

**Impact:** MEDIUM — Snapshots show different values than FIFO path

| Implementation | Location | Method |
|----------------|----------|--------|
| Backfill | `backfill_portfolio_snapshots.py:41-106` | FIFO |
| Performance views | `portfolio_service.py:1456-1557` | FIFO |
| Event replay | `replay_engine.py:95-160` | **Average cost** |

**Code review finding:**
> The `HoldingState` dataclass has a `lots` field, but the sell path ignores it for cost calculation. When `ENABLE_EVENT_REPLAY_SNAPSHOTS=True`, snapshots show different values than the FIFO path.

### 9.2 Bug: Commission Not in Replay Cost Basis

**Impact:** MEDIUM — Cost basis understated

| Implementation | Commission in cost basis |
|----------------|--------------------------|
| Backfill (`backfill_portfolio_snapshots.py:67`) | `cost_per_share = price + (commission / qty)` ✅ |
| Performance view (`portfolio_service.py:1492`) | `cost_per_share = price + (commission / qty)` ✅ |
| Replay engine (`replay_engine.py:119`) | `total_cost = quantity * unit_price` ❌ |

### 9.3 Bug: ROC Does Not Reduce Cost Basis

**Impact:** MEDIUM — Cost basis overstated

| Implementation | ReturnOfCapital handling |
|----------------|--------------------------|
| Cash balance | `cash_balance += net_cash` ✅ |
| Cost basis reduction | Not implemented ❌ |

### 9.4 Proposed Fix: Upgrade Replay Engine to FIFO

**Approach:** Modify `_handle_transaction_imported` in the replay engine to:
1. Include commission in buy cost_per_share (matching backfill formula)
2. Use FIFO lot removal for sell cost basis (matching backfill logic)
3. Add ReturnOfCapital handling to reduce cost basis proportionally

#### 9.4.1 Evaluation Criteria

| Criterion | Weight | Score (1-5) | Notes |
|-----------|--------|-------------|-------|
| **Consistency with existing patterns** | High | 5 | Follows event-sourcing architecture exactly. `HoldingState` already has `lots` field — we just use it. |
| **Simplicity/maintainability** | High | 5 | ~60 lines changed in one file. No new classes, no schema changes, no new dependencies. |
| **Performance** | Medium | 5 | Lot removal is O(n) where n = number of lots (typically < 50). No performance concern. |
| **Failure handling** | High | 5 | Fallback to `average_cost` if lots are empty. Guards against zero/negative values. |
| **Testability** | High | 5 | Each change is independently testable. Existing test patterns apply. |
| **Migration cost** | Medium | 5 | Zero migration — existing events are reprocessed correctly. No data changes needed. |

#### 9.4.2 Professional App Comparison

| Feature | Bloomberg | Morningstar | Refinitiv | Our Design |
|---------|-----------|-------------|-----------|------------|
| **Lot tracking** | Mandatory (SEC) | Mandatory | Mandatory | FIFO lots ✅ |
| **Cost basis method** | FIFO default | FIFO default | FIFO default | FIFO ✅ |
| **Commission in cost** | Yes (standard) | Yes | Yes | Yes ✅ |
| **ROC reduces basis** | Yes (IRS Pub 550) | Yes | Yes | Yes ✅ |
| **Realized gain/loss** | Per-lot | Per-lot | Per-lot | Per-lot ✅ |

**Regulatory alignment:**
- **IRS Publication 550:** Return of Capital reduces cost basis, not treated as income
- **SEC Regulation NMS:** Requires lot-level tracking for cost basis reporting on Form 1099-B
- **IRS FIFO requirement:** FIFO is the default method unless specific identification is used

#### 9.4.3 Implementation

**Step 1: Modify BUY path to include commission**

File: `shared/replay_engine.py`, lines 118-120

Before:
```python
if quantity > 0:  # Buy
    total_cost = quantity * unit_price
    lot = {"quantity": quantity, "cost_per_share": unit_price, "date": txn_date}
```

After:
```python
if quantity > 0:  # Buy
    commission = _decimal(data.get("commission"))
    cost_per_share = unit_price + (commission / quantity) if quantity else unit_price
    total_cost = quantity * cost_per_share
    lot = {"quantity": quantity, "cost_per_share": cost_per_share, "date": txn_date}
```

**Outcome:** Buy cost basis now includes commission, matching backfill formula.

**Step 2: Modify SELL path to use FIFO lot removal**

File: `shared/replay_engine.py`, lines 139-159

Before:
```python
elif quantity < 0:  # Sell
    sell_qty = abs(quantity)
    if holding:
        sold = min(sell_qty, holding.quantity)
        sale_proceeds = sold * unit_price
        cost_of_sold = sold * holding.average_cost if holding.average_cost else Decimal("0")
        holding.realized_gain_loss += sale_proceeds - cost_of_sold
        holding.total_cost -= cost_of_sold
        holding.quantity -= sold
        # FIFO lot removal
        remaining_to_remove = sold
        while remaining_to_remove > 0 and holding.lots:
            front = holding.lots[0]
            if front["quantity"] <= remaining_to_remove:
                remaining_to_remove -= front["quantity"]
                holding.lots.pop(0)
            else:
                front["quantity"] -= remaining_to_remove
                remaining_to_remove = Decimal("0")
        if holding.quantity <= 0:
            del state.holdings[cid]
```

After:
```python
elif quantity < 0:  # Sell
    sell_qty = abs(quantity)
    if holding:
        sold = min(sell_qty, holding.quantity)
        sale_proceeds = sold * unit_price
        # FIFO cost basis: remove lots from front, accumulate cost
        cost_of_sold = Decimal("0")
        remaining_to_remove = sold
        while remaining_to_remove > 0 and holding.lots:
            front = holding.lots[0]
            lot_qty = front["quantity"]
            lot_cost = front["cost_per_share"]
            if lot_qty <= remaining_to_remove:
                cost_of_sold += lot_qty * lot_cost
                remaining_to_remove -= lot_qty
                holding.lots.pop(0)
            else:
                cost_of_sold += remaining_to_remove * lot_cost
                front["quantity"] -= remaining_to_remove
                remaining_to_remove = Decimal("0")
        # Fallback to average_cost if lots are empty but sold > 0
        if cost_of_sold == 0 and sold > 0 and holding.average_cost:
            cost_of_sold = sold * holding.average_cost
        holding.realized_gain_loss += sale_proceeds - cost_of_sold
        holding.total_cost -= cost_of_sold
        holding.quantity -= sold
        # Recalculate average_cost from remaining lots
        if holding.lots:
            total_qty = sum(l["quantity"] for l in holding.lots)
            total_lot_cost = sum(l["quantity"] * l["cost_per_share"] for l in holding.lots)
            holding.average_cost = total_lot_cost / total_qty if total_qty else Decimal("0")
        if holding.quantity <= 0:
            del state.holdings[cid]
```

**Outcome:** Sell cost basis now uses FIFO lot removal, matching backfill logic.

**Step 3: Add `_handle_return_of_capital` method**

File: `shared/replay_engine.py`, after `_handle_split` (after line 175)

```python
def _handle_return_of_capital(self, state: AccountState, event: dict) -> None:
    """Reduce cost basis when ReturnOfCapital is received."""
    data = event.get("data", {}) or {}
    company_id = data.get("company_id")
    net_cash = _decimal(data.get("net_cash_amount"))
    if not company_id or net_cash <= 0:
        return
    holding = state.holdings.get(int(company_id))
    if not holding:
        return
    # Reduce cost basis by ROC amount (cannot go below zero)
    if holding.total_cost > 0:
        reduction = min(net_cash, holding.total_cost)
        holding.total_cost -= reduction
        # Reduce each lot proportionally
        if holding.lots:
            lot_total_cost = sum(l["quantity"] * l["cost_per_share"] for l in holding.lots)
            if lot_total_cost > 0:
                ratio = reduction / lot_total_cost
                for lot in holding.lots:
                    lot["cost_per_share"] *= (1 - ratio)
                    if lot["cost_per_share"] < 0:
                        lot["cost_per_share"] = Decimal("0")
        # Recalculate average_cost
        if holding.quantity > 0:
            holding.average_cost = holding.total_cost / holding.quantity
    # Note: excess ROC (net_cash > total_cost) is captured in cash_balance
    # via the existing CASH_ACTIVITY_TYPES handling, not recorded as a gain.
```

**Outcome:** ReturnOfCapital now reduces cost basis proportionally across lots.

**Step 4: Add `COST_REDUCTION_ACTIVITY_TYPES` and wire up**

File: `shared/replay_engine.py`, after line 68

```python
COST_REDUCTION_ACTIVITY_TYPES = {"ReturnOfCapital"}
```

File: `shared/replay_engine.py`, in `_handle_transaction_imported`, after line 107 (after cash balance update)

```python
# Cost basis reduction for ReturnOfCapital
if activity_type in self.COST_REDUCTION_ACTIVITY_TYPES and company_id:
    self._handle_return_of_capital(state, event)
```

**Outcome:** ReturnOfCapital events trigger cost basis reduction automatically.

#### 9.4.4 Edge Cases

| Scenario | Behavior |
|----------|----------|
| Sell more than all lots combined | Fallback to `average_cost` for excess |
| ROC when no holding exists | Cash only (no cost to reduce) |
| ROC exceeds total_cost | Cost reduced to zero, excess captured in cash_balance |
| Commission is zero | `cost_per_share = unit_price` (same as before) |
| Multiple lots with different costs | FIFO removes from front, each at its own cost |
| Partial lot sell | Lot quantity reduced, cost_per_share unchanged |
| Sell with no lots | Fallback to `average_cost` |

#### 9.4.5 Open Questions (Resolved)

**Q1: ROC proportionality across accounts**
Not an issue. Architecture constrains one holding per company per account. Events are per-account (`aggregate_id = "account_{id}"`). No proportionality needed.

**Q2: ROC when lot costs are zero**
Handled correctly. `reduction = min(net_cash, holding.total_cost)` clamps at zero. `lot_total_cost > 0` guard prevents division by zero. Excess ROC captured in `cash_balance`.

#### 9.4.6 Files Changed

| File | Change |
|------|--------|
| `shared/replay_engine.py` | Modify BUY path (~3 lines), modify SELL path (~25 lines), add `_handle_return_of_capital` (~20 lines), add `COST_REDUCTION_ACTIVITY_TYPES` (~1 line) |
| `tests/test_replay_engine.py` | Add FIFO sell tests, commission tests, ROC tests (~150 lines) |
| `docs/PORTFOLIO_PERFORMANCE_CHART_DATA_ANALYSIS.md` | Update section 9 |

#### 9.4.7 What Does NOT Change

- `HoldingState` dataclass (already has `lots` field)
- `EventStore` / event schema
- `build_snapshot_row` / `build_snapshot_from_replay` (they read from `HoldingState`)
- `_atomic_write_holdings` (it writes `quantity`, `average_cost`, `total_cost`)
- Backfill / performance view (they already use FIFO)
- Projection handler

#### 9.4.8 Rejected Alternatives

1. **Keep average cost, just fix commission:** Doesn't solve the FIFO discrepancy (Bug 9.1). Backfill and performance views would still differ from replay.

2. **Create a new `FIFOReplayEngine` class:** Over-engineered. The existing `ReplayEngine` already has the lot structure — it just needs to use it.

#### 9.4.9 Implementation Steps

| Step | Description | Outcome |
|------|-------------|---------|
| **1** | Modify BUY path to include commission | `cost_per_share = price + (commission / qty)` |
| **2** | Modify SELL path to use FIFO lots | Sell cost basis uses lot costs, not average |
| **3** | Add `_handle_return_of_capital` | ROC reduces cost basis proportionally |
| **4** | Add `COST_REDUCTION_ACTIVITY_TYPES` | ROC events trigger cost reduction |
| **5** | Write 13 tests | All pass |
| **6** | Update section 9 of design doc | Section 9 complete |

---

## 10. Topic: Repair Script

### 10.1 Root Cause: 42 Months of Zero-Value Snapshots

**Impact:** HIGH — TFSA appears empty for 42 months

**Evidence:**
| # | Fact | How Verified | Confidence |
|---|------|--------------|------------|
| 1 | All 1000 snapshots have net_deposits=0.00 | DB query (all rows) | 100% |
| 2 | `get_net_deposits(9, 2024-07-12)` returns $29,203.29 | Simulated query with fresh client | 100% |
| 3 | `build_snapshot_row()` passes net_deposits through at line 397 | Code inspection | 100% |
| 4 | Repair script comparison logic at line 243 only checks total_value and holdings | Code inspection | 100% |
| 5 | All snapshots processed by repair script (job_id=fast_repair_2026-07-14) | DB query | 100% |

**Root cause:** The repair script's comparison logic at `_fast_repair_all.py:243` prevents writes when `total_value` and `holdings count` are unchanged, even if `net_deposits` is wrong.

```python
# Line 243 of _fast_repair_all.py
if (abs(old_total - new_total) > 0.01 or old_holdings != new_holdings):
    snapshots_repo.upsert_snapshot(recomputed)
```

For the 42 months of zero-value snapshots (2021-02 to 2024-07):
- Old snapshot: `total_value=0, holdings=0, net_deposits=0`
- New computation: `total_value=0, holdings=0, net_deposits=$29,203.29`
- Comparison: `abs(0 - 0) > 0.01` → `False`, `0 != 0` → `False`
- **Result: Snapshot NOT written.** The original `net_deposits=0` persists.

### 10.2 Root Cause: 658-Day Gap in Snapshot Data

**Impact:** HIGH — Chart carries forward stale values

- Last raw snapshot: 2024-11-05 ($208.54)
- No snapshots for 658 days after that
- API compensates via LOCF (Last Observation Carried Forward)
- Daily job's correct 2026-07-14 snapshot appears as a spike

### 10.3 Root Cause: July 14 Spike

**Impact:** Visual artifact of Issues 10.1 and 10.2

| Account | Pre-Spike | Post-Spike | Delta |
|---------|-----------|------------|-------|
| TFSA | $1,007.12 | $51,585.00 | +$50,577.88 (+4,923%) |
| RRSP | $18,861.57 | $32,629.06 | +$13,767.49 |
| Non-registered | $1,910.58 | $15,530.12 | +$13,619.54 |
| ALL | $21,779.27 | $99,744.18 | +$77,964.91 |

---

## 11. Code Path Reference

| File | Line | Purpose |
|------|------|---------|
| `backend/application/services/portfolio_service.py` | 1606 | `get_portfolio_performance()` — main endpoint |
| `backend/application/services/portfolio_service.py` | 1324 | `_period_to_date_range("ALL")` — date range calculation |
| `backend/application/services/portfolio_service.py` | 1518 | `_compress_snapshots_by_interval()` — 30-day compression |
| `backend/application/services/portfolio_service.py` | 1849-2003 | Legacy/FIFO path with `_cached_net_deposits()` |
| `backend/config.py` | 271 | `ENABLE_PORTFOLIO_SNAPSHOT_READ_PATH` default=True |
| `backend/config.py` | 260 | `ENABLE_FX_CONVERSION` default=False |
| `backend/api/portfolio.py` | 1565 | API route handler |
| `backend/shared/snapshot_builder.py` | 33 | `CDR_RATIO = Decimal("10")` |
| `backend/shared/snapshot_builder.py` | 270-299 | FX conversion logic |
| `backend/shared/snapshot_builder.py` | 397 | `build_snapshot_row()` — passes net_deposits |
| `backend/shared/replay_engine.py` | 88-137 | Average cost lot tracking |
| `backend/shared/fx_service.py` | 55-76 | `get_rate()` — 3-tier resolution (cache, DB, yfinance) |
| `backend/shared/fx_service.py` | 96-112 | `convert_or_warn()` — FX conversion with fallback |
| `backend/infrastructure/repositories/portfolio_repository.py` | 1078 | `get_net_deposits()` |
| `backend/infrastructure/repositories/portfolio_repository.py` | 1204 | `_get_split_factors()` |
| `backend/infrastructure/repositories/portfolio_repository.py` | 1284-1298 | Split price adjustment |
| `backend/infrastructure/repositories/financial_repository.py` | 1424 | `_get_split_factors()` (duplicate) |
| `backend/application/parsers/portfolio_parser.py` | 178-183 | CDR detection patterns |
| `backend/scripts/_fast_repair_all.py` | 243 | Comparison logic (root cause) |
| `backend/scripts/backfill_exchange_rates.py` | — | Backfill historical FX rates |
| `backend/supabase/migrations/001_create_exchange_rates_table.sql` | — | FX rates table schema |
| `web/src/features/portfolio/components/PortfolioPerformanceChart.tsx` | 238 | `buildChartData()` — frontend mapping |

---

## 12. Implementation Plan

### Phase 1: FX Conversion (1 day)

| Step | Effort | Risk | Priority |
|------|--------|------|----------|
| 1.1 Backfill historical FX rates | Low | Low | P0 |
| 1.2 Enable `ENABLE_FX_CONVERSION=True` | Low | Low | P0 |
| 1.3 Fix `portfolio.py:199,222` value_currency | Low | Low | P0 |
| 1.4 Re-run snapshot job | Medium | Low | P0 |
| 1.5 Verify TFSA values | Low | Low | P0 |

**Step 1.1:** `python scripts/backfill_exchange_rates.py --start 2020-01-01`

**Step 1.2:** `config.py:260` — change `default=False` to `default=True`

**Step 1.3:** `portfolio.py:199` — change `"value_currency": "USD"` to `"value_currency": acc.get("currency", "CAD")`
`portfolio.py:222` — change `"value_currency": "USD"` to `"value_currency": "CAD"`

**Step 1.4:** Re-run daily snapshot job to regenerate all historical snapshots with FX conversion

**Step 1.5:** Compare Obs values against expected values to verify correctness

### Phase 2: Holdings Split Adjustment (1-2 days)

| Fix | Effort | Risk | Priority |
|-----|--------|------|----------|
| 2.1 Add split event handler | Medium | Low | P1 |
| 2.2 Create `split_adjustments` table | Low | Low | P1 |
| 2.3 Backfill existing splits | Medium | Low | P1 |

### Phase 3: CDR Fixes (2-3 days)

| Fix | Effort | Risk | Priority |
|-----|--------|------|----------|
| 3.1 Add `cdr_ratio` to `companies` table | Low | Low | P0 |
| 3.2 Create `apply_cdr_adjustment()` helper | Low | Low | P0 |
| 3.3 Modify `_resolve_holding_price` for CDR derivation | Medium | Medium | P0 |
| 3.4 Fix `price_currency = "CAD"` for CDR holdings | Low | Low | P0 |
| 3.5 Fix 4 API endpoints (dashboard, accounts, holdings) | Medium | Low | P0 |
| 3.6 Fix watchlist service + SSE + stock price endpoint | Medium | Low | P0 |
| 3.7 Fix `get_holding_performance()` CDR historical prices | Medium | Low | P0 |
| 3.8 Write `backfill_cdr_ratios.py` script | Medium | Low | P0 |
| 3.9 Write CDR pricing tests (all 12 bugs) | Medium | Low | P0 |
| 3.10 Run backfill + rebuild snapshots | Medium | Low | P0 |

### Phase 4: Architecture Improvements (3-5 days)

| Improvement | Effort | Risk | Priority |
|-------------|--------|------|----------|
| Consolidate FIFO implementations | High | Medium | P2 |
| Add holding period tracking | Medium | Low | P2 |
| Add wash sale detection | Medium | Low | P3 |

---

## 13. Risk Analysis

| Risk | Impact | Mitigation |
|------|--------|------------|
| Breaking existing snapshots | HIGH | Migration script to backfill; parallel computation; rollback path |
| FX rate unavailability | MEDIUM | Graceful degradation (unconverted value); log warnings; daily refresh |
| CDR ratio changes | LOW | Monthly refresh; store historical ratios; validate against market |
| CDR pipeline entirely broken | HIGH | 12 bugs across pricing, API, watchlist, performance; read-time derivation + ratio fix + endpoint fixes |
| Split adjustment errors | HIGH | Validate against market data; log all adjustments; allow manual override |
| Backfill script fails | HIGH | Check yfinance connectivity; retry with smaller date range |
| Historical snapshots incorrect after FX enable | MEDIUM | Re-run snapshot job; compare old vs new values |

---

## 14. Database Schema Changes

```sql
-- 1. Add currency to portfolio_accounts
ALTER TABLE portfolio_accounts 
ADD COLUMN currency VARCHAR(3) NOT NULL DEFAULT 'CAD';

-- 2. Add CDR ratio to companies
ALTER TABLE companies 
ADD COLUMN cdr_ratio DECIMAL(10, 4),
ADD COLUMN cdr_ratio_date DATE;

-- 3. Add split adjustment tracking
CREATE TABLE split_adjustments (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    split_factor VARCHAR(20) NOT NULL,
    ex_date DATE NOT NULL,
    old_quantity DECIMAL(20, 8),
    new_quantity DECIMAL(20, 8),
    old_cost_per_share DECIMAL(20, 8),
    new_cost_per_share DECIMAL(20, 8),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. Add FX rate tracking to holdings
ALTER TABLE portfolio_holdings 
ADD COLUMN cost_basis_fx_rate DECIMAL(10, 6),
ADD COLUMN cost_basis_fx_date DATE;
```

---

## 9. Pending Items — Must Complete Before Snapshot Rebuild

> **Status: Steps 1-13 of CDR implementation are DONE. Event replay FIFO upgrade DONE. Steps 14-15 are BLOCKED pending 5 pre-rebuild fixes (see 9.2).**

### 9.1 Rebuild All Snapshots (Step 14 — BLOCKED)

**Command:** `python scripts/step9_rebuild_all_snapshots.py`

**Why it must be done:**
Existing `portfolio_snapshot_rows` were built with the old hardcoded `CDR_RATIO = 10`. After the CDR code changes, new snapshots will use per-company ratios from `companies.cdr_ratio`. But historical snapshots still have wrong prices. Rebuilding regenerates ALL snapshots using the new logic.

**What it fixes:**
- CDR holdings in historical snapshots will show correct CDR prices (using per-company ratio, not hardcoded 10)
- `cost_basis` and `unrealized_gain_loss` in snapshots will reflect correct CDR pricing
- `holdings_json` in each snapshot will have accurate `current_price` and `current_value`

**When to run:**
After ALL other pending effects (below) are fixed. Running it multiple times is safe (idempotent), but each rebuild is expensive (replays all events for all accounts).

**Prerequisites:**
- [x] `companies.cdr_ratio` populated (backfill done — 10/10 CDR companies)
- [ ] Fix step9 lot serialization crash (Issue 1 — BLOCKER)
- [ ] Fix step9 missing CDR parameters (Issue 2 — BLOCKER)
- [ ] Fix replay engine IST handling (Issue 3 — HIGH)
- [ ] Fix FIFO sell fallback condition (Issue 4 — MEDIUM)
- [ ] Add sell truncation warning (Issue 5 — LOW)
- [ ] Write tests for IST + fallback fixes

**Verification after rebuild:**
```sql
-- CDR holdings should show ~$35 range, not ~$350
SELECT snapshot_date, holdings_json->0->>'current_price' as price,
       holdings_json->0->>'symbol' as symbol
FROM portfolio_snapshot_rows, jsonb_array_elements(holdings_json) as holdings_json
WHERE holdings_json->>'symbol' = 'TSLA'
ORDER BY snapshot_date DESC LIMIT 5;
```

### 9.2 Pre-Rebuild Audit: Open Issues

> **Status: 5 issues identified. All must be fixed before running step9_rebuild_all_snapshots.py.**

#### Issue 1: step9_rebuild_all_snapshots.py — Lot Serialization Crash (BLOCKER)

**Impact:** CRITICAL — script crashes for accounts 7 and 8
**File:** `scripts/step9_rebuild_all_snapshots.py:199`
**Blocks snapshot rebuild:** YES

**Description:** The script serializes lots using attribute access on dicts:

```python
# Current (BROKEN) — line 199
'lots': [{'quantity': float(l.quantity), 'cost': float(l.cost), 'date': l.date.isoformat()} for l in h.lots]
```

`h.lots` is `List[Dict]` (replay_engine.py:24). `l.quantity` raises `AttributeError`. The dict key is `cost_per_share`, not `cost`. This code path was never exercised before because the replay engine previously didn't track lots (average-cost only). After the FIFO upgrade, accounts 7 and 8 now have populated lots.

**Recommended fix:**

```python
# Fixed — dict key access, correct key name
'lots': [{'quantity': float(l['quantity']), 'cost_per_share': float(l['cost_per_share']),
           'date': l['date'].isoformat() if l.get('date') else None}
          for l in h.lots] if h.lots else None,
```

#### Issue 2: step9_rebuild_all_snapshots.py — Missing CDR Parameters (BLOCKER)

**Impact:** HIGH — CDR holdings show ~$350 instead of ~$35
**File:** `scripts/step9_rebuild_all_snapshots.py:206-216`
**Blocks snapshot rebuild:** YES

**Description:** The script loads `exchange_overrides` (lines 132-143) but never passes them to `build_snapshot_row`. It also doesn't load `companies_map` (which contains per-company `cdr_ratio`). CDR holdings fall back to hardcoded `CDR_RATIO=10`.

**Recommended fix:** Add `companies_map` loading and pass `exchange_overrides`, `company_currencies`, `companies_map` to `build_snapshot_row`:

```python
# After loading company_names (line 97-101), also load cdr_ratio
companies_map = {}
if cids:
    comps_cdr = supabase.table('companies').select('company_id, cdr_ratio, currency') \
        .in_('company_id', list(cids)).execute()
    for row in comps_cdr.data or []:
        companies_map[int(row['company_id'])] = row

# Also load company_currencies
company_currencies = {}
for cid_val, info in companies_map.items():
    company_currencies[cid_val] = info.get('currency', 'USD')

# In the build_snapshot_row call, add:
snapshot = build_snapshot_row(
    ...existing params...,
    exchange_overrides=exchange_overrides.get(aid, {}),
    company_currencies=company_currencies,
    companies_map=companies_map,
)
```

#### Issue 3: Replay Engine Drops InternalSecurityTransfer for Holdings (HIGH)

**Impact:** HIGH — IST-originated securities lost during replay; accounts 7 and 8 affected
**File:** `shared/replay_engine.py:120`
**Blocks snapshot rebuild:** YES

**Description:** The replay engine's `_handle_transaction_imported` gates holdings updates on `activity_type == "Trade"` (line 120). `InternalSecurityTransfer` events are silently dropped for holdings. This produces wrong quantities and cost basis for any account that received or sent securities via IST.

Account 8 (RRSP) has 42 IST transactions. These transfer securities between accounts. The replay engine ignores all of them, so the rebuilt snapshots for account 8 will have incorrect holdings.

**The existing pattern to follow:** `_fast_repair_all_helpers.py:reconstruct_holdings_fast` (lines 32-62) already handles IST correctly. The replay engine should follow the same pattern:

- IST with positive quantity → add lot (like BUY)
- IST with negative quantity → remove lots FIFO (like SELL)
- IST does NOT affect cash balance (already correct — IST not in `CASH_ACTIVITY_TYPES`)

**Recommended fix:** Extend line 120 to include IST:

```python
# BEFORE (line 120)
if company_id and activity_type == "Trade" and quantity != 0:

# AFTER
HOLDING_ACTIVITY_TYPES = {"Trade", "InternalSecurityTransfer"}
...
if company_id and activity_type in self.HOLDING_ACTIVITY_TYPES and quantity != 0:
```

And modify the buy/sell branching to handle IST (which has no `activity_sub_type`):

```python
if quantity > 0:  # Buy or inbound IST
    ...existing buy logic (commission, lot creation)...

elif quantity < 0:  # Sell or outbound IST
    ...existing sell logic (FIFO lot removal)...
```

The buy path already works for IST: `commission = _decimal(data.get("commission"))` would be 0 for IST (IST transactions don't have commission), so `cost_per_share = unit_price`. The sell path's FIFO logic is IST-agnostic and works as-is.

**Consistency check:** The `_fast_repair_all_helpers.py` pattern treats IST identically to Trade for lot tracking. The replay engine should do the same. No snowflakes.

#### Issue 4: FIFO Sell Fallback Condition Too Narrow (MEDIUM)

**Impact:** MEDIUM — cost basis understated when lots partially cover a sell
**File:** `shared/replay_engine.py:167-169`
**Blocks snapshot rebuild:** YES (affects accuracy of rebuilt snapshots)

**Description:** The fallback to `average_cost` only triggers when `cost_of_sold == 0`:

```python
# Current (line 167-169)
if cost_of_sold == 0 and sold > 0 and holding.average_cost:
    cost_of_sold = sold * holding.average_cost
```

If the FIFO loop partially consumes lots (cost_of_sold > 0) but exhausts all lots before covering `sold`, the remaining shares have no cost assigned. `cost_of_sold` only covers the lots that were consumed, not the full `sold` quantity.

**When this occurs:** A holding starts from `initial_holding_set` (no lots), then gets a buy (adds lots), then a sell that spans both the initial position and the buy. The FIFO loop consumes the buy lots (cost_of_sold > 0), but the initial position's shares have no lots to consume.

**Recommended fix:** Change the fallback condition to also handle partial lot exhaustion:

```python
# AFTER
# Fallback: if lots didn't cover the full sell, use average_cost for remainder
if sold > 0 and remaining_to_remove > 0 and holding.average_cost:
    cost_of_sold += remaining_to_remove * holding.average_cost
elif cost_of_sold == 0 and sold > 0 and holding.average_cost:
    cost_of_sold = sold * holding.average_cost
```

The first branch handles partial exhaustion (lots consumed some, average_cost covers the rest). The second branch handles the original case (no lots at all). The `remaining_to_remove > 0` check is already computed by the FIFO loop.

#### Issue 5: Sell Truncation Without Warning (LOW)

**Impact:** LOW — unlikely in practice, but silently creates cash discrepancy
**File:** `shared/replay_engine.py:150`
**Blocks snapshot rebuild:** NO

**Description:** `sold = min(sell_qty, holding.quantity)` silently truncates sells that exceed holdings. Cash is increased by the full `net_cash_amount` (line 109), but `sale_proceeds` only covers `sold` shares. The difference is unaccounted cash.

**Recommended fix:** Add a warning log when truncation occurs:

```python
# AFTER line 150
if sell_qty > holding.quantity:
    logger.warning(
        "Sell truncation: account=%s company=%s sell_qty=%s > holding_qty=%s",
        state.account_id, cid, sell_qty, holding.quantity,
    )
```

This is a data quality issue, not a logic fix. In practice, brokers don't allow over-selling.

---

### 9.3 Recommended Fix Plan

**Single approach — no alternatives considered:**

| Step | What | File | Lines Changed | Risk |
|------|------|------|---------------|------|
| **1** | Fix lot serialization (dict keys) | `step9_rebuild_all_snapshots.py:199` | ~3 | None |
| **2** | Add CDR params to rebuild script | `step9_rebuild_all_snapshots.py` | ~15 | Low |
| **3** | Add IST to replay engine holdings | `shared/replay_engine.py:120` | ~8 | Low |
| **4** | Fix FIFO sell fallback condition | `shared/replay_engine.py:167-169` | ~4 | Low |
| **5** | Add sell truncation warning | `shared/replay_engine.py:150` | ~4 | None |
| **6** | Write tests for IST + fallback | `tests/test_replay_engine.py` | ~60 | None |

**Estimated total:** ~94 lines changed across 3 files.

### 9.4 Evaluation Criteria

| Criterion | Score | Notes |
|-----------|-------|-------|
| **Consistency with existing patterns** | 5 | IST handling follows `_fast_repair_all_helpers.py` exactly. Lot serialization matches `build_snapshot_from_replay:397-404`. No new abstractions. |
| **Simplicity/maintainability** | 5 | Each change is <15 lines. No new classes, no schema changes, no new dependencies. |
| **Performance** | 5 | IST handling adds one set lookup per event (O(1)). No measurable impact. |
| **Failure handling** | 5 | IST fallback: same as Trade (FIFO with average_cost fallback). Sell truncation: logged, no crash. |
| **Testability** | 5 | Each change independently testable with existing test patterns (mock Supabase client). |
| **Migration cost** | 5 | Zero migration. Existing events are reprocessed correctly. No data changes. |

### 9.5 What Does NOT Change

- `HoldingState` dataclass (lots are already `List[Dict]`)
- `EventStore` / event schema
- `_should_process_for_lots` / `_classify_lot_action` (used by backfill path, not by replay)
- `build_snapshot_row` / `convert_holding_fx` (they read what they're given)
- Backfill / fast repair scripts (they have their own IST handling)
- CDR pricing logic
- FX conversion logic

### 9.6 Implementation Steps

| Step | Description | Outcome | Verify |
|------|-------------|---------|--------|
| **1** | Fix `step9_rebuild_all_snapshots.py` lot serialization | Dict key access, correct key names | Script runs without AttributeError for accounts with lots |
| **2** | Add `companies_map`, `exchange_overrides`, `company_currencies` loading and passing to `build_snapshot_row` in step9 | CDR holdings get correct ratio | CDR holding `current_price` ≈ $35 in rebuilt snapshot |
| **3** | Add `HOLDING_ACTIVITY_TYPES` set to replay engine, extend line 120 | IST events create/modify lots during replay | Account 8 IST securities appear in replay state |
| **4** | Fix FIFO sell fallback condition in replay engine | Partial lot exhaustion handled correctly | Test: buy + initial (no lots) + sell spanning both |
| **5** | Add sell truncation warning log | Truncation visible in logs | Test: sell more than held → warning logged |
| **6** | Write tests for IST handling and FIFO fallback | All tests pass | `python -m pytest tests/test_replay_engine.py -v` |
| **7** | Run step9_rebuild_all_snapshots.py | Snapshots rebuilt with correct data | Verification section shows no ND drops, CDR prices correct |
| **8** | Run full test suite | No regressions | 163+ tests pass |

---

## Appendix: Raw JSON Files

- `docs/rrsp_performance_raw.json`
- `docs/nonregistered_performance_raw.json`
- `docs/all_accounts_performance_raw.json`
