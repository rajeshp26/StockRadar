# Super Investor Scheduler Changes - Todo List

**Document Version:** 1.0  
**Date:** 2026-04-27  
**Status:** In Progress  

---

## Table of Contents

1. [Backfill Script Changes](#1-backfill-script-changes)
2. [Scheduler Changes (Future)](#2-scheduler-changes-future)
3. [Related Documentation](#3-related-documentation)
4. [Testing Checklist](#4-testing-checklist)

---

## 1. Backfill Script Changes

**File:** `backend/scripts/backfill_super_investors.py`

### 1.1 Resume Logic (PRIORITY: HIGH)

#### Status: ✅ COMPLETE

**Changes Made:**
- Added `get_investor_status()` function to check existing data
- Added `get_missing_filings()` function to filter SEC filings
- Updated `backfill_all_investors()` main loop with resume logic
- Added statistics tracking (complete/incomplete/new/error)

**Logic:**
1. For each investor, check DB for existing quarters via `get_investor_status()`
2. If already complete (quarter_count >= configured quarters) → skip with "COMPLETE"
3. If partial → show "INCOMPLETE" and fetch missing quarters only
4. If no record → show "NEW" and do full backfill
5. Update tracking only after fetching missing quarters

**Implementation Details:**

```python
# New function: Get investor status
def get_investor_status(supabase, cik: str) -> dict:
    """Check investor's current state in DB.
    
    Returns:
        {
            "exists": bool,
            "investor_id": int or None,
            "last_filed_period": str or None,
            "last_filed_date": str or None,
            "existing_quarters": Set[str],
            "quarter_count": int
        }
    """
```

```python
# New function: Filter to missing filings
def get_missing_filings(all_filings, existing_quarters, max_quarters):
    """Return only filings for quarters not already in DB.
    
    Args:
        all_filings: List of SEC filings (sorted by date descending)
        existing_quarters: Set of quarter dates already in DB
        max_quarters: Maximum quarters to fetch for this investor
        
    Returns:
        List of (filing, thirteenf) tuples for missing quarters
    """
```

**Example Output:**
```
[1/24] Warren Buffett (BUFFETT) - COMPLETE (20/20 quarters, skipping)
[2/24] Terry Smith (FUNDSMITH) - COMPLETE (4/4 quarters, skipping)
[5/24] Bill Ackman (ACKMAN) - INCOMPLETE (12/20 quarters, fetching 8 more)
[6/24] Carl Icahn (ICAHN) - NEW investor, fetching 20 quarters

============================================================
Backfill complete!
  COMPLETE (skipped): 5
  INCOMPLETE (fetched missing): 3
  NEW (full backfill): 16
============================================================
```

### 1.2 Progress Output Enhancement (PRIORITY: MEDIUM)

#### Status: ✅ COMPLETE

**Changes Made:**
- Added status indicators in main loop: COMPLETE, INCOMPLETE, NEW
- Shows quarter count progress for each investor
- Summary statistics at completion
- Clear visual separator lines for readability

---

## 2. Scheduler Changes (Future)

**File:** `backend/application/schedulers/super_investors_scheduler.py`

### 2.1 Company Creation Logic (PRIORITY: HIGH)

**Status:** ⏳ PENDING

**Required Change:**
The scheduler should use the same company creation logic as the backfill script:
1. Check if company exists in DB
2. If not, try to create using Yahoo Finance
3. If YF returns 404 → skip (not a valid security)
4. If YF fails other error → skip silently

**Reference:** `scripts/backfill_super_investors.py:52-101` (get_or_create_company function)

**Current Behavior (scheduler.py:336-344):**
```python
# Get company_id from ticker
company_result = supabase.table("companies").select(
    "company_id"
).eq("ticker_symbol", ticker).execute()

if not company_result.data:
    continue  # ← Just skips, doesn't create
```

**Required Behavior:**
```python
# Get or create company using YF (same as backfill)
company_id = await self._get_or_create_company(ticker)
if not company_id:
    continue  # YF 404 or other error - skip
```

### 2.2 Resume Logic in Scheduler (PRIORITY: MEDIUM)

**Status:** ⏳ PENDING

**Required Change:**
The scheduler's `_refresh_single_investor()` already has some logic, but should also check existing quarters like backfill does.

**Current Logic (scheduler.py:145-159):**
```python
last_period = result.data[0].get("last_filed_period")

# Check if new filing is due
if last_period:
    next_due = self._calculate_next_due_date(last_period)
    if datetime.now().date() < next_due:
        return False  # Skip if not due yet
```

**Required Enhancement:**
Also check quarter count to ensure backfill completeness:
```python
# Check quarter count
existing_quarters = get_quarters_in_db(investor_id)
target_quarters = info.get("quarters", 20)

if len(existing_quarters) < target_quarters:
    # Backfill needed - fetch missing quarters first
```

### 2.3 Add Change Tracking Fields (PRIORITY: LOW)

**Status:** ⏳ PENDING

**Issue:**
The history API (`super_investors.py`) expects fields that backfill doesn't populate:
- `shares_change`
- `shares_change_pct`
- `change_type`

**Current Backfill:** Only saves core fields
**History API:** Reads these with `.get()` for NULL handling

**Decision:** Can be addressed in future update. Currently handled gracefully by `.get()`.

---

## 3. Related Documentation

| Document | Path | Purpose |
|----------|------|---------|
| Background Scheduler Design | `backend/docs/BACKGROUND_SCHEDULER_DESIGN.md` | Celery migration plan |
| Background Scheduler Impact | `backend/docs/BACKGROUND_SCHEDULER_IMPACT_ANALYSIS.md` | Impact analysis |
| Super Investor Backfill | `scripts/backfill_super_investors.py` | Main backfill script |

---

## 4. Testing Checklist

### 4.1 Backfill Script Tests

- [ ] Run with `--dry-run` (if added) to see what would be skipped
- [ ] Verify COMPLETE investors are skipped (no SEC calls)
- [ ] Verify INCOMPLETE investors only fetch missing quarters
- [ ] Verify NEW investors get full backfill
- [ ] Check DB after run: all quarters saved correctly
- [ ] Check tracking fields: last_filed_period updated
- [ ] Verify no duplicate holdings (upsert works)

### 4.2 Scheduler Tests (After Updates)

- [ ] Verify scheduler doesn't create junk companies
- [ ] Verify invalid tickers (YF 404) are skipped
- [ ] Verify valid tickers are created with proper data
- [ ] Check scheduler startup: no blocking
- [ ] Test login during scheduler run: should be fast

### 4.3 Integration Tests

- [ ] Frontend SuperInvestorsTab loads correctly
- [ ] Position history chart renders
- [ ] Recent buyers/sellers display
- [ ] Quarter labels show correctly

---

## 5. Implementation Notes

### 5.1 Files Modified

| File | Change Type | Status |
|------|-------------|--------|
| `scripts/backfill_super_investors.py` | Add resume logic | ✅ Done |
| `application/schedulers/super_investors_scheduler.py` | Add company creation | ⏳ Pending |
| `application/services/super_investors_service.py` | Update quarters config | ✅ Done |

### 5.2 No Breaking Changes

- All changes are additive (new functions, new checks)
- Existing upsert logic preserved
- No schema changes required
- Backward compatible with existing data

### 5.3 Performance Impact

| Metric | Before | After |
|--------|--------|--------|
| SEC API calls (completed investor) | 100+ | 0 |
| SEC API calls (partial investor) | 100+ | 20-40 |
| Time per completed investor | 2-5 min | <1 sec (DB check only) |
| Total time (24 investors, all complete) | ~60 min | ~10 sec |
| Total time (24 investors, partial) | ~60 min | ~15-20 min |

---

## 6. Rollback Plan

If issues arise:

1. **Revert script changes:** `git checkout HEAD -- scripts/backfill_super_investors.py`
2. **Clear tracking:** `UPDATE institutional_investors SET last_filed_period = NULL WHERE is_super_investor = TRUE`
3. **Re-run:** Script will process all investors again (no flags needed now)

---

## 7. Open Questions

| Question | Decision | Notes |
|----------|----------|-------|
| Add --force flag? | Deferred | Not needed initially |
| Add --dry-run flag? | Deferred | Not needed initially |
| Add specific CIK filter? | Deferred | Not needed initially |

---

## Document History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-04-27 | Initial todo list | StockerPro |

---

**End of Document**