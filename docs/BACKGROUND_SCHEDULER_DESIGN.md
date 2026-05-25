# Background Task Scheduler Architecture Redesign
## StockerPro Celery + Redis Implementation

**Document Version:** 1.0  
**Date:** 2026-04-26  
**Status:** Design Complete  
**Author:** StockerPro Team  

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Current Architecture Analysis](#3-current-architecture-analysis)
4. [Proposed Architecture](#4-proposed-architecture)
5. [Detailed Design](#5-detailed-design)
6. [Implementation Plan](#6-implementation-plan)
7. [Rollback Strategy](#7-rollback-strategy)
8. [Testing Strategy](#8-testing-strategy)

---

## 1. Executive Summary

### Background

The StockerPro backend currently runs the Super Investors scheduler synchronously within the FastAPI event loop, which blocks all HTTP requests including user login. This design flaw causes the application to become unresponsive during scheduler execution, leading to:

- Login timeouts and failures
- Poor user experience
- Potential revenue impact

### Solution Overview

Migrate from synchronous in-process scheduling to a production-ready distributed task queue using **Celery + Redis**:

| Aspect | Current | Proposed |
|--------|---------|----------|
| Execution Location | FastAPI event loop | Separate worker process |
| HTTP Blocking | Yes (entire app) | No (isolated) |
| Retries | None | Automatic (3 retries) |
| Monitoring | Logs only | Flower web UI |
| Scalability | None | Horizontal |
| Recovery on Crash | Lost | Automatic |

### Impact Summary

| Component | Change Level | Effort |
|-----------|------------|--------|
| New Redis dependency | HIGH | 2 hours |
| Celery task conversion | MEDIUM | 4 hours |
| Configuration updates | LOW | 1 hour |
| Testing & validation | MEDIUM | 3 hours |
| Total | | ~10 hours |

---

## 2. Problem Statement

### 2.1 The Core Issue

The Super Investors scheduler runs synchronously within the FastAPI process, executing 40+ investor data fetches sequentially. Each fetch involves:

1. SEC EDGAR API calls (slow, rate-limited)
2. Multiple database writes per investor
3. Connection pool usage

This blocks the FastAPI event loop, causing all incoming HTTP requests to wait.

### 2.2 Observed Symptoms

When the scheduler runs on application startup:

```
User Login Request → FastAPI → BLOCKED (waiting for scheduler to complete)
                                           ↓
                             SEC API fetch for Investor 1...
                                           ↓
                             SEC API fetch for Investor 2...
                                           ↓
                             ... (40+ investors total)
                                           ↓
                             DB writes → Connection pool exhausted
                                           ↓
                             Login times out → User sees error
```

### 2.3 Business Impact

| Metric | Impact |
|--------|-------|
| Login Failure Rate | 100% during scheduler runs |
| User Experience | App appears broken |
| Trust | Users question app reliability |
| Support Tickets | Increased |

### 2.4 Why Current Approach Failed

The original design assumed:
- Scheduler runs quickly
- FastAPI can handle both HTTP and background tasks
- Database connections are unlimited

Reality:
- SEC API is slow (multiple seconds per request)
- 40+ investors × ~5 seconds = 200+ seconds
- Connection pool exhaustion affects all DB operations

---

## 3. Current Architecture Analysis

### 3.1 Current Flow Diagram

```
┌──────────────────────────────────────���──────────────────────────┐
│                      FastAPI Application                      │
├──────────────────────────────────────────────────────┤
│                                                          │
│  ┌─────────────────┐     ┌──────────────────────────┐   │
│  │   HTTP API     │     │  Super Investors      │   │
│  │   Endpoints   │     │  Scheduler           │   │
│  │               │     │                      │   │
│  │  /login  ─────│     │  _refresh_all()      │   │
│  │  /analysis    │     │     ↓                │   │
│  │  /holdings   │     │  Investor 1          │   │
│  │  /valuations │     │  Investor 2          │   │
│  │  ...         │     │  ...                 │   │
│  │               │     │  Investor 40+        │   │
│  └───────┬───────┘     └──────────┬───────────┘   │
│          │                        │                │
│          │    BLOCKS HERE         │                │
│          ▼                       ▼                │
│  ┌─────────────────────────────────────────┐     │
│  │         Supabase Connection Pool         │     │
│  │              (shared)                 │     │
│  └─────────────────────────────────────────┘     │
│                       │                           │
│                       ▼                           │
│  ┌─────────────────────────────────────────┐     │
│  │              PostgreSQL                  │     │
│  │           (Supabase)                  │     │
│  └─────────────────────────────────────────┘     │
└─────────────────────────────────────────────────┘
```

### 3.2 Key Components

| Component | File | Issue |
|-----------|------|-------|
| SuperInvestorsRefreshScheduler | `application/schedulers/super_investors_scheduler.py` | Runs in event loop |
| FastAPI Lifespan | `main.py:114-124` | Starts scheduler on app init |
| Settings | `config.py:219-231` | No separation of concerns |
| Database Connections | Shared pool | Exhaustion during scheduler runs |

### 3.3 Code References

**Scheduler initialization in main.py:**
```python
# Lines 114-124
if getattr(settings, "ENABLE_SUPER_INVESTORS_SCHEDULER", True):
    super_investors_sched = SuperInvestorsRefreshScheduler()
    await super_investors_sched.start()
    app.state.schedulers["super_investors"] = super_investors_sched
```

**Scheduler execution (super_investors_scheduler.py:76-88):**
```python
async def _run_loop(self) -> None:
    while self.is_running:
        try:
            await self._refresh_all_investors()  # ← BLOCKS HERE
        except Exception as e:
            logger.error(f"Scheduler cycle failed: {e}")
        
        sleep_seconds = self.interval_hours * 3600
        await asyncio.sleep(sleep_seconds)
```

### 3.4 Performance Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Login latency | 200+ seconds (timeout) | < 2 seconds |
| Scheduler impact on API | Full blocking | None |
| Failed retries | 0% | 100% (3 auto-retries) |
| Monitoring | Logs only | Flower UI |

---

## 4. Proposed Architecture

### 4.1 Architecture Diagram

```
┌────────────────────────────────────────────────────────────────────────────┐
│                        Production Architecture                        │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────────┐     ┌──────────────────┐                    │
│  │  FastAPI       │     │  Celery         │                    │
│  │  (uvicorn)    │     │  Worker        │                    │
│  │               │     │  (separate    │                    │
│  │  HTTP API    │     │   process)    │                    │
│  │  Endpoints   │     │              │                    │
│  │              │     │  ┌─────────┐ │                    │
│  │  /login    │     │  │Task 1  │ │                    │
│  │  /analysis │     │  │Task 2  │ │                    │
│  │  /holdings │     │  │...     │ │                    │
│  │  ...      │     │  └─────────┘ │                    │
│  └─────▲─────┘     └──────┬──────┘                    │
│        │                   │                              │
│        │                   │  ⬆                         │
│        │              ┌────┴────┐                        │
│        │              │         │                        │
│        │              ▼         ▼                        │
│        │         ┌──────────────────┐                   │
│        └────────│    Redis        │                   │
│                │  (Broker +      │                   │
│                │   Result       │                   │
│                │   Backend)     │                   │
│                └──────┬───────┘                   │
│                       │                           │
│                ┌──────┴───────┐                   │
│                │              │                           │
│                ▼              ▼                       │
│  ┌──────────────────┐  ┌──────────────────┐            │
│  │  Flower UI    │  │  PostgreSQL   │            │
│  │  (monitor)  │  │  (Supabase) │            │
│  └──────────────────┘  └──────────────────┘            │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 Component Responsibilities

| Component | Responsibility | Process |
|-----------|--------------|---------|
| FastAPI (uvicorn) | Handle HTTP requests | 1 |
| Celery Worker | Execute background tasks | Separate |
| Redis | Message broker + result storage | Separate |
| Flower | Task monitoring web UI | Separate |
| Supabase | Database | External |

### 4.3 New Components

| Component | File | Purpose |
|-----------|------|---------|
| Celery App | `application/celery_app.py` | Celery configuration |
| Tasks | `application/tasks/*.py` | Celery tasks |
| Worker startup | `worker.py` | Worker entry point |
| Flower config | `flowerconfig.py` | Monitoring config |

### 4.4 Data Flow

**Task Submission:**
```
1. FastAPI receives HTTP request
2. Endpoint calls task.delay() or task.apply_async()
3. Task ID returned immediately (fast response)
4. Task queued in Redis
5. HTTP response sent to client
```

**Task Execution:**
```
1. Celery worker polls Redis for tasks
2. Worker picks up task from queue
3. Executes task logic
4. Writes result to Redis
5. Updates task status
```

**Result Retrieval:**
```
1. Client calls /status/{task_id}
2. FastAPI checks AsyncResult
3. Result retrieved from Redis
4. Response sent to client (or pending status)
```

---

## 5. Detailed Design

### 5.1 Configuration Design

**Environment Variables (.env):**

```env
# ============================================================
# Celery Configuration
# ============================================================

# Redis connection (message broker)
CELERY_BROKER_URL=redis://localhost:6379/0

# Redis connection (result backend)
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Flower monitoring
FLOWER_URL=http://localhost:5555
```

**Settings Class (config.py):**

```python
class Settings(BaseSettings):
    # ... existing settings ...
    
    # Celery Configuration
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    FLOWER_URL: str = "http://localhost:5555"
```

### 5.2 Celery Application Design

**File: `application/celery_app.py`**

```python
"""
Celery application configuration.

This module defines the Celery app instance that all tasks will use.
It connects to Redis as both broker and result backend.
"""

from celery import Celery
from config import settings

celery_app = Celery(
    "stockerpro",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# Celery configuration
celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json",
    
    # Timezone
    timezone="UTC",
    enable_utc=True,
    
    # Task routing
    task_routes={
        "super_investors_refresh": {"queue": "super_investors"},
    },
    
    # Worker configuration
    worker_prefetch_multiplier=1,      # Prevent worker starvation
    task_acks_late=True,           # Acknowledge after completion
    worker_max_tasks_per_child=100, # Prevent memory leaks
    
    # Result configuration
    result_expires=3600,           # Results expire after 1 hour
    task_track_started=True,          # Track task start time
)
```

### 5.3 Task Design

**File: `application/tasks/super_investors_tasks.py`**

```python
"""
Celery tasks for Super Investors background processing.
"""

import asyncio
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,  # 5 minutes
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def super_investors_refresh(self):
    """
    Refresh all super investor holdings.
    
    This task:
    - Runs in a separate Celery worker process
    - Won't block FastAPI HTTP requests
    - Automatically retries on failure (3 attempts)
    - Logs progress for monitoring
    
    Retry Strategy:
    - Attempt 1: Immediate execution
    - Attempt 2: After 5 minutes
    - Attempt 3: After 10 minutes (exponential backoff)
    """
    logger.info(f"Starting super investors refresh (attempt {self.request.retries + 1})")
    
    async def _run():
        from application.schedulers.super_investors_scheduler import (
            SuperInvestorsRefreshScheduler,
        )
        
        scheduler = SuperInvestorsRefreshScheduler()
        result = await scheduler._refresh_all_investors()
        return result
    
    try:
        result = asyncio.run(_run())
        logger.info(f"Super investors refresh completed: {result}")
        return result
    except Exception as exc:
        logger.error(f"Super investors refresh failed: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True)
def refresh_single_investor(self, cik: str):
    """
    Refresh a single investor's holdings.
    
    Args:
        cik: SEC CIK number
        
    Returns:
        dict: Result with 'refreshed' boolean
    """
    logger.info(f"Refreshing investor {cik}")
    
    async def _run():
        from application.schedulers.super_investors_scheduler import (
            SuperInvestorsRefreshScheduler,
        )
        from application.services.super_investors_service import SUPER_INVESTORS
        
        if cik not in SUPER_INVESTORS:
            return {"error": f"Unknown CIK: {cik}"}
        
        scheduler = SuperInvestorsRefreshScheduler()
        refreshed = await scheduler._refresh_single_investor(cik, SUPER_INVESTORS[cik])
        return {"cik": cik, "refreshed": refreshed}
    
    try:
        result = asyncio.run(_run())
        return result
    except Exception as exc:
        logger.error(f"Failed to refresh {cik}: {exc}")
        raise
```

### 5.4 API Endpoints Design

**File: `api/scheduler_control.py` (new)**

```python
"""
API endpoints for scheduler control.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from application.celery_app import celery_app
from auth import get_current_user

router = APIRouter(prefix="/scheduler", tags=["Scheduler"])


class TriggerTaskResponse(BaseModel):
    task_id: str
    status: str
    message: str


@router.post("/super-investors/trigger", response_model=TriggerTaskResponse)
async def trigger_super_investors_refresh(current_user: dict = Depends(get_current_user)):
    """
    Manually trigger a super investors refresh.
    
    Returns immediately with task_id. Use /scheduler/status/{task_id} to check progress.
    """
    task = super_investors_refresh.delay()
    
    return TriggerTaskResponse(
        task_id=task.id,
        status="queued",
        message="Super investors refresh started",
    )


@router.get("/super-investors/status/{task_id}")
async def get_task_status(task_id: str):
    """
    Get the status of a background task.
    
    Returns current state: PENDING, STARTED, SUCCESS, FAILURE, RETRY
    """
    from celery.result import AsyncResult
    
    result = AsyncResult(task_id, app=celery_app)
    
    return {
        "task_id": task_id,
        "status": result.state,
        "result": result.result if result.ready() else None,
        "info": result.info if result.info else None,
    }


@router.post("/trigger", response_model=TriggerTaskResponse)
async def trigger_all_schedulers(current_user: dict = Depends(get_current_user)):
    """
    Trigger all enabled schedulers manually.
    
    Convenience endpoint to manually trigger all background refresh tasks.
    """
    tasks = []
    
    # Super investors
    si_task = super_investors_refresh.delay()
    tasks.append(f"super_investors: {si_task.id}")
    
    return TriggerTaskResponse(
        task_id=", ".join(tasks),
        status="queued",
        message="All schedulers triggered",
    )
```

### 5.5 Worker Startup Design

**File: `worker.py`** (at backend root)

```python
"""
Celery worker startup script.

Usage:
    # Start worker
    python worker.py
    
    # Start with Flower monitoring
    python worker.py --flower
    
    # Start multiple workers (for scaling)
    python worker.py --concurrency=4
"""

import os
import sys
import argparse
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

from celery import Celery
from application.celery_app import celery_app
from application.tasks import super_investors_tasks


def main():
    parser = argparse.ArgumentParser(description="StockerPro Celery Worker")
    parser.add_argument(
        "--flower",
        action="store_true",
        help="Start Flower monitoring UI",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=2,
        help="Number of worker processes",
    )
    parser.add_argument(
        "--queue",
        default="celery",
        help="Queue to consume from",
    )
    
    args = parser.parse_args()
    
    # Start worker
    worker_args = [
        "-A", "application.celery_app.celery",
        "--loglevel=info",
        f"--concurrency={args.concurrency}",
        f"--queue={args.queue}",
    ]
    
    if args.flower:
        # Start both worker and Flower
        import subprocess
        flower_proc = subprocess.Popen(
            ["celery", "-A", "application.celery_app.celery", "flower", 
             "--port=5555"]
        )
        print(f"Flower started at http://localhost:5555")
    
    # Start Celery worker
    os.execv(sys.executable, [sys.executable, "-m", "celery"] + worker_args)


if __name__ == "__main__":
    main()
```

### 5.6 Modified Main.py Design

**File: `main.py` - Changes**

```python
# Remove scheduler import and startup (lines 114-124)

// OLD (to be removed):
# if getattr(settings, "ENABLE_SUPER_INVESTORS_SCHEDULER", True):
#     super_investors_sched = SuperInvestorsRefreshScheduler()
#     await super_investors_sched.start()

// NEW - Add manual trigger endpoints:
from api.scheduler_control import router as scheduler_router
app.include_router(scheduler_router)
```

### 5.7 Company Creation Logic (Critical)

The Celery task MUST use the same company creation logic as the backfill script.

**Key Requirement:** When saving holdings, create missing companies using Yahoo Finance. Skip only if YF returns 404 (not a valid security).

**Reference:** `scripts/backfill_super_investors.py:52-101`

**Implementation in task:**
```python
async def _get_or_create_company(self, ticker: str) -> Optional[int]:
    """Get existing company_id or create new one using Yahoo Finance.
    
    Logic matches backfill_super_investors.py:
    1. Check if company exists in DB
    2. If not, try to create using Yahoo Finance
    3. If YF returns 404 (invalid security), skip
    4. Otherwise, log error and skip
    """
    from database import supabase
    from shared.providers.yfinance import YFinanceProvider
    
    if not ticker or not isinstance(ticker, str):
        return None
    
    ticker_upper = ticker.upper().strip()
    if not ticker_upper:
        return None
    
    # Step 1: Check existing
    result = supabase.table("companies").select("company_id").eq(
        "ticker_symbol", ticker_upper
    ).execute()
    
    if result.data and len(result.data) > 0:
        return result.data[0]["company_id"]
    
    # Step 2: Try to create with Yahoo Finance
    if YFinanceProvider is None:
        logger.warning(f"No YFinance provider for {ticker_upper}, skipping")
        return None
    
    try:
        provider = YFinanceProvider()
        sd = provider.get_stock_details(ticker_upper)
    except Exception as e:
        if "404" in str(e):
            logger.warning(f"Skipping {ticker_upper}: YF not found (404)")
            return None
        logger.warning(f"YF API failed for {ticker_upper}: {e}")
        return None
    
    if not sd:
        logger.warning(f"Skipping {ticker_upper}: No YF data")
        return None
    
    # Step 3: Create company
    payload = {
        "ticker_symbol": ticker_upper,
        "company_name": sd.long_name,
        "exchange": sd.exchange,
        "sector": sd.sector,
        "industry": sd.industry,
        "currency": sd.currency,
        "description": sd.description,
        "website": sd.website,
    }
    
    insert_result = supabase.table("companies").insert(payload).execute()
    if insert_result.data and len(insert_result.data) > 0:
        logger.info(f"Created company: {ticker_upper}")
        return insert_result.data[0]["company_id"]
    
    logger.error(f"Failed to create company for {ticker_upper}")
    return None
```

**Updated `_save_holdings_to_db` in the task:**
Replace lines 336-344 in current scheduler with:
```python
# Get company_id (create if missing, skip if YF 404)
company_id = await self._get_or_create_company(ticker)
if not company_id:
    logger.warning(f"Could not create company for {ticker}, skipping holding")
    continue

company_id = company_id  # Now we have a valid company_id
```

**This ensures:**
- Existing companies are reused
- New tickers get created with full metadata from YF
- Invalid securities (YF 404) are skipped - not added to DB
- Consistent behavior between backfill and scheduled refresh

### 5.8 Docker Compose Design

**File: `docker-compose.yml`** (new or update)

```yaml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: >
      redis-server
      --appendonly yes
      --maxmemory 1gb
      --maxmemory-policy allkeys-lru
      --save 900 1
      --save 300 10
      --save 60 10000

  backend:
    build: ./backend
    command: uvicorn main:app --host 0.0.0.0 --port 8000
    ports:
      - "8000:8000"
    depends_on:
      - redis
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/0

  worker:
    build: ./backend
    command: celery -A application.celery_app.celery worker --loglevel=info --concurrency=2
    depends_on:
      - redis
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/0

  flower:
    image: mher/flower
    command: flower --broker=redis://redis:6379/0 --port=5555
    ports:
      - "5555:5555"
    depends_on:
      - redis

volumes:
  redis_data:
```

---

## 6. Implementation Plan

### 6.1 Phase 1: Infrastructure Setup

**Task 1.1: Install Dependencies**
```bash
pip install celery[redis] redis flower
```

**Task 1.2: Update Configuration**
- Add Celery settings to `.env`
- Add Celery settings to `config.py`

**Task 1.3: Start Redis**
```bash
# Development
docker run -d --name stockerpro-redis -p 6379:6379 redis:7

# Or install locally
# Windows: https://redis.io/docs/install/install-redis/
# Mac: brew install redis
```

### 6.2 Phase 2: Celery Setup

**Task 2.1: Create Celery App**
- Create `application/celery_app.py`

**Task 2.2: Create Tasks**
- Create `application/tasks/` directory
- Create `application/tasks/__init__.py`
- Create `application/tasks/super_investors_tasks.py`
- **CRITICAL:** Implement company creation logic (see Section 5.7)

### 6.3 Phase 3: API Integration

**Task 3.1: Add Scheduler Endpoints**
- Create `api/scheduler_control.py`

**Task 3.2: Update Main.py**
- Remove synchronous scheduler startup
- Add new endpoints

### 6.4 Phase 4: Worker Setup

**Task 4.1: Create Worker Script**
- Create `worker.py`

**Task 4.2: Test Local Worker**
```bash
python worker.py --flower
```

### 6.5 Phase 5: Testing & Validation

**Task 5.1: Unit Tests**
- Test task functions individually

**Task 5.2: Integration Tests**
- Test API endpoints
- Test worker execution

**Task 5.3: Load Tests**
- Concurrent task submission
- Worker scaling

### 6.6 Implementation Checklist

| Phase | Task | Status | Notes |
|-------|------|--------|-------|
| 1 | Install dependencies | ☐ | |
| 1 | Start Redis | ☐ | |
| 2 | Create Celery app | ☐ | |
| 2 | Create tasks | ☐ | |
| 3 | Add API endpoints | ☐ | |
| 3 | Update main.py | ☐ | |
| 4 | Create worker script | ☐ | |
| 4 | Test worker | ☐ | |
| 5 | Unit tests | ☐ | |
| 5 | Integration tests | ☐ | |
| 5 | Load tests | ☐ | |

---

## 7. Rollback Strategy

### 7.1 Quick Rollback (Development)

If Celery integration fails:

1. **Stop Celery workers:**
```bash
pkill -f "celery worker"
```

2. **Re-enable synchronous scheduler:**
```bash
# In .env
ENABLE_SUPER_INVESTORS_SCHEDULER=true
```

3. **Restart FastAPI:**
```bash
uvicorn main:app --reload
```

### 7.2 Rollback (Production)

If critical issues arise:

1. **Stop new services:**
```bash
docker-compose down
```

2. **Restore previous configuration:**
```bash
git checkout HEAD~1 -- backend/
```

3. **Re-deploy:**
```bash
docker-compose up
```

### 7.3 Graceful Degradation

If worker is down but API should work:

1. **Ensure Redis connects:**
```bash
redis-cli ping
```

2. **Verify task queue:**
```bash
celery -A application.celery_app.celery inspect active
```

3. **Manual execution if needed:**
```bash
python -c "
import asyncio
from application.schedulers.super_investors_scheduler import SuperInvestorsRefreshScheduler
asyncio.run(SuperInvestorsRefreshScheduler()._refresh_all_investors())
"
```

---

## 8. Testing Strategy

### 8.1 Unit Tests

**Test task creation:**
```python
def test_task_creation():
    from application.tasks.super_investors_tasks import super_investors_refresh
    assert super_investors_refresh.name == "super_investors_refresh"
    assert super_investors_refresh.max_retries == 3
```

**Test Celery app:**
```python
def test_celery_app_config():
    from application.celery_app import celery_app
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.result_serializer == "json"
```

### 8.2 Integration Tests

**Test task execution:**
```python
def test_task_execution():
    task = super_investors_refresh.delay()
    result = task.get(timeout=300)
    assert result is not None
    assert "investors_found" in result
```

**Test API endpoints:**
```python
def test_trigger_endpoint(client, auth_token):
    response = client.post(
        "/scheduler/super-investors/trigger",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert response.status_code == 200
    assert "task_id" in response.json()
```

### 8.3 Performance Tests

**Test blocking behavior:**
```python
def test_login_not_blocked(client, auth_token):
    # Start long-running task
    client.post("/scheduler/super-investors/trigger", 
               headers={"Authorization": f"Bearer {auth_token}"})
    
    # Immediately try login
    start = time.time()
    response = client.post("/auth/login", json={...})
    elapsed = time.time() - start
    
    assert response.status_code == 200
    assert elapsed < 2  # Should be fast, not blocked
```

---

## Appendix A: Commands Reference

### Starting Services

```bash
# Start Redis
docker run -d --name stockerpro-redis -p 6379:6379 redis:7

# Start Celery worker
celery -A application.celery_app.celery worker --loglevel=info

# Start Flower monitoring
celery -A application.celery_app.celery flower --port=5555

# Start FastAPI
uvicorn main:app --reload --port 8000
```

### Monitoring

```bash
# Check worker status
celery -A application.celery_app.celery inspect active

# Check queue depth
celery -A application.celery_app.celery inspect queue

# View Flower UI
# Open http://localhost:5555
```

### Troubleshooting

```bash
# Check Redis connection
redis-cli ping

# View worker logs
celery -A application.celery_app.celery worker --loglevel=debug

# Purge queue
celery -A application.celery_app.celery purge
```

---

## Appendix B: Files to Create/Modify

### New Files

| File | Purpose |
|------|---------|
| `application/celery_app.py` | Celery configuration |
| `application/tasks/__init__.py` | Task imports |
| `application/tasks/super_investors_tasks.py` | Celery tasks |
| `api/scheduler_control.py` | API endpoints |
| `worker.py` | Worker startup script |

### Modified Files

| File | Changes |
|------|---------|
| `.env` | Add Celery settings |
| `config.py` | Add Celery settings |
| `main.py` | Remove sync scheduler, add endpoints |
| `requirements.txt` | Add celery, redis, flower |

### Deleted Files (after migration)

| File | Reason |
|------|-------|
| `application/schedulers/super_investors_scheduler.py` | Replaced by tasks |

---

## Appendix C: Security Considerations

1. **Redis Access Control**
   - Use password for Redis in production
   - Bind to localhost only (or internal network)

2. **API Authentication**
   - All scheduler trigger endpoints require authentication
   - Use Firebase token validation

3. **Worker Resource Limits**
   - Set `--concurrency` based on available CPU
   - Limit with `worker_max_tasks_per_child`

4. **Task Timeouts**
   - Set reasonable timeouts to prevent hung tasks
   - Monitor via Flower

---

## Document History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-04-26 | Initial design document | StockerPro Team |

---

## Approval

This design document has been reviewed and approved:

- [ ] Technical Lead
- [ ] Product Owner
- [ ] Security Review

---

**End of Document**