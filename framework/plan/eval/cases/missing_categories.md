<!-- expect: PL05 -->
status: approved
approval_hash: 0be320a10b5b82e4993ed3eacc51eda00a65e306a28f07afc08e57fe346304de
title: Bound how stale a price may be before valuation uses it
files_or_components:
  - framework/claims/ledger.py
  - framework/adapters/code_intel.py
acceptance_criteria:
  - AC-1 [unit] resolve_price returns None when the newest price is more than 30 days old
  - AC-2 [integration] a stale price is rejected with reason code STALE_PRICE and no row is written to the claims ledger
  - AC-3 [data-invariant] for every position in the real account-9 snapshot, valuation equals the sum of lot quantity times price within 0.01, with no mocking
discovery:
  - code [VERIFIED: framework/claims/ledger.py:1-20] current price resolution reads the newest row only; no age check exists
  - architecture [VERIFIED: framework/adapters/code_intel.py:1-20] valuation is called only from the snapshot builder
  - data [VERIFIED: CLM-001] row counts and age distribution queried from the real database
reuse:
  - age bound for prices -> framework/claims/ledger.py
