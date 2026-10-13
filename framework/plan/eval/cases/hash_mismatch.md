<!-- expect: PL08 -->
status: approved
approval_hash: 32578ad0d9c8d70836d8524efc2086bb9ffafa1b561f405a3afa38994b5f01e7
title: Bound how stale a price may be before valuation uses it
files_or_components:
  - framework/claims/ledger.py
  - framework/adapters/code_intel.py
acceptance_criteria:
  - AC-1 [unit] resolve_price (edited after approval) returns None when the newest price is more than 30 days old
  - AC-2 [integration] a stale price is rejected with reason code STALE_PRICE and no row is written to the claims ledger
  - AC-3 [data-invariant] for every position in the real account-9 snapshot, valuation equals the sum of lot quantity times price within 0.01, with no mocking
discovery:
  - code [VERIFIED: framework/claims/ledger.py:1-20] current price resolution reads the newest row only; no age check exists
  - architecture [VERIFIED: framework/adapters/code_intel.py:1-20] valuation is called only from the snapshot builder
  - design [NA: no ui or design change involved] pure backend rule
  - environment [VERIFIED: python3 --version] interpreter and flags confirmed in this run
  - data [VERIFIED: CLM-001] row counts and age distribution queried from the real database
reuse:
  - age bound for prices -> framework/claims/ledger.py
