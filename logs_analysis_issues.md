# Issues Analysis from Logs - StockerPro Worker

## Issue 1: Massive Dependency Version Drift (CRITICAL)

### Symptoms from logs
```
DEPENDENCY DRIFT DETECTED - installed environment != requirements.txt
  DRIFT defeatbeta-api: declared 0.0.61, installed 0.0.50 (historically)
  ... 80+ packages with version mismatches
  DRIFT duckdb: declared 1.5.3, installed 1.4.3 (historically)
```
Preflight reports drift but worker continues because `PRICE_PREFLIGHT_FATAL` not set.

### Root Cause
1. **Environment not synced**: Virtual environment has packages installed at different versions than `backend/requirements.txt` (which is pip-compiled)
2. **Non-fatal by design**: `startup_check()` logs errors but returns `False` without crashing unless `PRICE_PREFLIGHT_FATAL=1` and it's a critical package
3. **DuckDB/defeatbeta-api version coupling**: As noted in preflight comments, defeatbeta-api 0.0.50 pins duckdb 1.4.3 which doesn't have cache_httpfs extension on community repo causing silent price pipeline failure
4. **No enforcement**: Dev environment setup not enforced, no lockfile validation in CI

### Professional-Grade Solution

#### Immediate (Fix Now)
```bash
# Create clean venv or update existing
cd backend
python -m pip install --upgrade pip
pip install -r requirements.txt
```

#### Short-term (Robust)
1. **Make critical drift fatal by default in all environments**:
```python
# In startup_check, for critical packages make it fatal regardless of env var
critical = {n for n, _, _ in drift} & set(PIPELINE_CRITICAL)
if critical:
    raise RuntimeError(f"Critical dependency drift: {critical}. Run: pip install -r requirements.txt")
```

2. **Add hash checking** using `pip install --require-hashes` with `requirements.txt` containing hashes (pip-tools can generate)
3. **Use `uv` or `poetry`** for deterministic dependency resolution

#### Long-term (Production-grade)
1. **Pin all transitive deps with hashes** - generate with `pip-compile --generate-hashes`
2. **CI check**: Add step to verify installed deps match requirements
3. **Docker multi-stage build** with cached deps layer
4. **Use dependency lock files** committed to repo
5. **Automated dependency updates** with Dependabot/Renovate + tests

**Comparison to professional apps**: Google, Meta, Netflix fail fast on dependency mismatches. Stripe uses lockfiles. The current non-fatal behavior is dangerous for data pipelines.

---

## Issue 2: All company_refresh Jobs Failing with code_exception (CRITICAL)

### Symptoms from logs
```
[ENGINE] Job 7aaa4c72-... (company_refresh) failed after 0ms: code_exception → pending
[ENGINE] Job 1ff21c48-... (company_refresh) failed after 0ms: code_exception → pending
... (hundreds of jobs)
[ENGINE] Job 7aaa4c72-... (company_refresh) moved to dead_letter after 3 attempts
```

### Root Cause
**Bug in `reconciliation_scheduler.py` line ~127-144**: When enqueuing financial refresh jobs for companies missing periods, the payload only contains `scopes` and `reasons` but is missing required fields.

The handler `handle_company_refresh` calls `_handle_company_refresh_financials` which requires:
```python
payload = job.get("payload", {})
company_id = payload.get("company_id")
symbol = payload.get("ticker_symbol")
if not company_id or not symbol:
    raise ValueError(f"Missing company_id or ticker_symbol in job payload: {payload}")
```

But reconciliation does:
```python
"payload": {
    "scopes": FINANCIAL_SCOPES,
    "reasons": [FINANCIAL_REASON],
},
```

Compare to correct implementations in `earnings_scheduler.py` and `market_data_scheduler.py` which include `company_id`, `ticker_symbol`, etc.

Also the dedupe key is set correctly but payload is incomplete.

### Professional-Grade Solution

#### Fix 1: Correct reconciliation scheduler
```python
jobs.append({
    "job_type": FINANCIAL_JOB_TYPE,
    "dedupe_key": FINANCIAL_DEDUPE_TEMPLATE.format(company_id=cid),
    "resource_type": "company",
    "resource_id": str(cid),
    "payload": {
        "company_id": cid,
        "ticker_symbol": candidate.get("ticker_symbol"),  # Need to ensure this is fetched
        "scopes": FINANCIAL_SCOPES,
        "reasons": [FINANCIAL_REASON],
    },
    "priority": FINANCIAL_PRIORITY,
    "max_attempts": FINANCIAL_MAX_ATTEMPTS,
    "not_before": now_iso(),
})
```

But need to verify `get_financial_candidates()` returns ticker_symbol. Let us check - looking at how it's used elsewhere, probably needs to join companies table.

#### Fix 2: Make handler more defensive (defensive programming)
```python
async def _handle_company_refresh_financials(job: dict[str, Any]) -> dict[str, Any]:
    payload = job.get("payload", {})
    company_id = payload.get("company_id")
    symbol = payload.get("ticker_symbol")
    
    if not company_id:
        raise ValueError(f"Missing company_id in job payload: {payload}")
    
    if not symbol:
        # Fallback: fetch from DB
        from infrastructure.repositories.financial_repository import SupabaseFinancialRepository
        repo = SupabaseFinancialRepository()
        company = await repo.get_company_by_id(company_id)
        if not company or not company.get("ticker_symbol"):
            raise ValueError(f"Cannot resolve ticker_symbol for company_id={company_id}")
        symbol = company["ticker_symbol"]
        payload["ticker_symbol"] = symbol  # Update for downstream use
```

#### Fix 3: Add payload validation with Pydantic
Create schema for job payloads and validate in job engine before dispatch.

#### Fix 4: Better error classification
Don't classify missing required fields as retryable code_exception in the same way - or make them fail fast to dead letter without retries. But better to fix the root cause.

**Comparison to professional apps**: Airflow, Celery have strict task schemas. Temporal validates inputs. This is a classic case of missing required data in job payload.

---

## Issue 3: PRUNE jobs_succeeded returning URI too long error

### Symptoms from logs
```
infrastructure.repositories.scheduler_repository [PRUNE] jobs_succeeded: {'message': 'JSON could not be generated', 'code': 414, 'hint': 'Refer to full message for details', 'details': "b'URI too long\\n'"}
```

### Root Cause
In `_delete_prunable_jobs`:
```python
r = supabase.table(self.JOBS_TABLE) \
    .select("id") \
    .eq("status", status) \
    .lt("updated_at", cutoff) \
    .execute()
job_ids = [row["id"] for row in (r.data or [])]
if not job_ids:
    return 0

supabase.table(self.JOB_ATTEMPTS_TABLE) \
    .delete() \
    .in_("job_id", job_ids) \  # Passing potentially thousands of IDs in IN clause
    .execute()
r = supabase.table(self.JOBS_TABLE) \
    .delete() \
    .in_("id", job_ids) \
    .execute()
```

If there are thousands of old jobs to prune, the IN clause with all those UUIDs creates a very long URL/query that exceeds HTTP URI limits (414 Request-URI Too Long). PostgREST/Supabase has limits on URL length.

### Professional-Grade Solution

#### Fix 1: Batch deletes
```python
def _delete_prunable_jobs(self, status: str, cutoff_days: int) -> int:
    cutoff = (now_utc() - timedelta(days=cutoff_days)).isoformat()
    total_deleted = 0
    batch_size = 100  # Small batches to avoid URI limits
    
    while True:
        r = supabase.table(self.JOBS_TABLE) \
            .select("id") \
            .eq("status", status) \
            .lt("updated_at", cutoff) \
            .limit(batch_size) \
            .execute()
        job_ids = [row["id"] for row in (r.data or [])]
        if not job_ids:
            break
        
        # Delete attempts in batches
        for i in range(0, len(job_ids), 50):
            batch = job_ids[i:i+50]
            try:
                supabase.table(self.JOB_ATTEMPTS_TABLE) \
                    .delete() \
                    .in_("job_id", batch) \
                    .execute()
            except Exception:
                pass
        
        try:
            r = supabase.table(self.JOBS_TABLE) \
                .delete() \
                .in_("id", job_ids) \
                .execute()
            total_deleted += len(r.data or [])
        except Exception:
            break
    
    return total_deleted
```

#### Fix 2: Use RPC function with temp tables or direct SQL
Better to create a Postgres function that does the deletion in a single transaction without passing all IDs through HTTP.

#### Fix 3: Delete by range/chunk differently
Use `DELETE ... WHERE id IN (SELECT id FROM jobs WHERE ...)` via RPC or use multiple smaller queries.

**Comparison to professional apps**: AWS RDS, Cloud SQL have similar limits. Proper solutions use batching or server-side functions.

---

## Issue 4: Job Engine - Immediate Failures (0ms)

All company_refresh jobs fail after 0ms which means exceptions happen before/during handler dispatch or very early. This confirms the payload validation issue - the handler raises ValueError immediately.

Also need to look at how the error is caught and logged.

---

## Issue 5: Dependency preflight continues on drift

As discussed in Issue 1 - should be fatal for critical deps.

---

## Issue 6: Price ingestion seems to be working (166/166 prices refreshed)

The price ingestion jobs are completing successfully with good performance (~4s each). So the price pipeline might be okay despite drift? Or maybe it recovered. But the drift is still concerning.

---

## Recommendations

### Immediate Actions (Today)
1. **Fix reconciliation scheduler** - add company_id and ticker_symbol to payload (I already started this)
2. **Fix get_financial_candidates** to ensure it returns ticker_symbol
3. **Fix prune logic** to batch deletes
4. **Make preflight fatal for critical deps** or set env var

### Code Changes Needed

Let us fix the remaining issues.