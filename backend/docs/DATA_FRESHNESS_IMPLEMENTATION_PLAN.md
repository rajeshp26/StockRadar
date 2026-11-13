# Data Freshness Implementation Plan

> **Strategy:** Fix confirmed root causes first (planner crash, observability gaps).
> Then fix independent issues (super investors, dead letter, quarantine).
> Avoid speculative fixes for unconfirmed causes until confirmed.

---

## Phase 0: Fix the Planner Crash (1 day)

### 0a — Make datetime comparison type-safe (`planner.py:69-73`)

Current code wraps comparison in `try/except TypeError` which doesn't reliably prevent propagation. Replace with explicit type guard:

```python
def to_utc(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

# In _check_and_plan():
now = datetime.now(timezone.utc)
next_due = to_utc(next_due)
if next_due and now < next_due:
    continue
```

No more `try/except TypeError` around comparisons.

### 0b — Fix `upsert_scheduler_state` in error handler

The error handler writes state without all required fields, causing silent failure. Change to PATCH (partial update) instead of upsert:

```python
# Use update (not upsert) for error state
self._repo.update_scheduler_state(
    scheduler_name=name,
    updates={"last_status": "failed", "last_error": str(e)[:500]},
)
```

Or merge with existing state before upserting.

### Validation

- `scheduler_run_history` no longer shows new failures
- `scheduler_state.last_status` changes from `'unknown'` to `'succeeded'` or `'failed'`

---

## Phase 1: Observability (1 day)

### 1a — Decorate attempt from success

New columns on `companies`:
- `last_price_attempt_at timestamptz` — set before every price fetch
- `last_price_success_at timestamptz` — set only when data returned
- `consecutive_price_failures int DEFAULT 0` — increments on empty, resets on success

### 1b — Auto-quarantine after N failures (solves delisted ETFs)

After 5 consecutive price failures, set `coverage_status='quarantined'` and skip in refresh cycles. Re-probe weekly.

### 1c — Janitor cleanup

- Delete heartbeats where `hostname='shutdown'` or `last_hb_at < 1 hour ago`
- Release resource locks where `expires_at < now()`

### 1d — Dead letter re-queue endpoint

Admin API: `POST /admin/jobs/{id}/requeue`. Also add `requeue_dead_letters()` to janitor for automated replay after configurable cooldown.

---

## Phase 2: Process Backlog (automatic after Phase 0)

Once the planner runs successfully, `plan()` for market_data will return all 172 active companies. Workers (5 concurrent) will process them over multiple cycles. 22 INITIAL stocks will get financial data via the existing bootstrap logic (step 5c in `_process_company`).

No code changes needed for this phase.

---

## Phase 3: Super Investors (1 day)

### 3a — Investigate why it was disabled

```bash
git log --all -p -- backend/.env | grep ENABLE_SUPER_INVESTORS
```

Check commit message for reason. Likely candidates: SEC EDGAR rate limits, API cost, incomplete implementation.

### 3b — Re-enable with backfill guard

Only after confirming the original reason and ensuring it's resolved:
- Rate-limit to 10 req/sec (EDGAR limit)
- Filter in `plan()` to only enqueue due investors (not all 24 every cycle)
- Monitor `scheduler_run_history` for failures

---

## Phase 4: Dead Letter & Schema (1 day)

### 4a — Identify TNXP overflow field

Query the raw provider output for TNXP to identify which financial field exceeds NUMERIC(12,4). Inspect `payload` in the dead_letter job for context.

### 4b — Fix schema or add clamping

Either increase column precision or add input validation to prevent overflow.

---

## Phase 5: Provider Investigations (1 day)

### 5a — Direct provider probes

Test PSYK, HYLD, CMA, NYCB, WBA, RSLS via raw yfinance outside the pipeline to determine if:
- Delisted/renamed (no data from any source) → quarantine
- Symbol resolution issue (works with different suffix) → fix resolution
- Provider gap (works with different provider) → add fallback

### 5b — Price history retry

Add exponential backoff retry to `fetch_price_history()` (same pattern as `get_all_financials_optimized()`).

---

## Phase 6: Monitoring & Alerting (1 day)

- `GET /health/freshness` — per-scheduler status, stale counts, dead letters
- Alert if any enabled scheduler's `last_succeeded_at > 2× interval`
- Alert if `consecutive_price_failures > 5` for any active company
- Alert if dead letter count exceeds threshold

---

## Implementation Order

```
Phase 0: Fix planner crash  ─────────── Critical path (blocks everything)
    │
Phase 1: Observability     ─────────── Do before any scheduling changes
    │
Phase 2: Backlog (auto)    ─────────── Unblocks after Phase 0 completes
    │
├── Phase 3: Super investors
├── Phase 4: Dead letter         ←── Independent, can be parallelized
├── Phase 5: Provider probes
│
Phase 6: Monitoring        ─────────── Depends on Phase 0-1
```

---

## What NOT to Do

- **Don't add retry to price history** (Phase 5) until provider probes (Phase 5a) determine whether failures are transient (retry helps) or permanent (quarantine instead)
- **Don't rebuild the bootstrap logic** (step 5c in `_process_company`) — it already handles INITIAL → COMPLETE transition. Just let the planner run.
- **Don't manually exclude delisted ETFs** — auto-quarantine (Phase 1b) solves this automatically after N failures
- **Don't touch the earnings date Catch-22** — 22 active INITIAL companies will get data via market_data bootstrap when the planner runs. The earnings-dependency is only for the earnings scheduler itself.
