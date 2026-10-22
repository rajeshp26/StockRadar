# scheduler_health.py
# READ-ONLY. Dumps scheduler_state + recent jobs/run_history to answer:
# is the scheduler running, and why does price_history stop at 2026-09-30?
from __future__ import annotations

import sys
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from dotenv import load_dotenv

load_dotenv(_backend / ".env")

from database import supabase  # noqa: E402


def safe(table: str, cols: str, order: str | None = None,
         desc: bool = True, lim: int = 50) -> list[dict]:
    try:
        q = supabase.table(table).select(cols)
        if order:
            q = q.order(order, desc=desc)
        if lim:
            q = q.limit(lim)
        return q.execute().data or []
    except Exception as e:  # table may not exist
        print(f"  [{table}] query failed: {e}")
        return []


print("=== scheduler_state (all rows) ===")
rows = safe("scheduler_state",
            "scheduler_name, last_run_at, last_success_at, next_run_at, "
            "status, last_error", lim=100)
if rows:
    keys = sorted({k for r in rows for k in r})
    print("  cols:", ", ".join(keys))
    for r in rows:
        nm = r.get("scheduler_name") or r.get("name") or r.get("id")
        print(f"  {nm}: " + ", ".join(
            f"{k}={r[k]}" for k in keys if k not in ("scheduler_name", "name", "id")))
else:
    print("  (no rows)")

print("\n=== recent jobs (price/market/snapshot related) ===")
jobs = safe("jobs", "id, job_type, status, created_at, scheduled_at, "
            "started_at, finished_at, error, last_error",
            order="created_at", lim=40)
for j in jobs:
    print("  " + ", ".join(f"{k}={j.get(k)}" for k in
          ("id", "job_type", "status", "created_at", "finished_at", "error")
          if j.get(k) is not None))

print("\n=== scheduler_run_history (recent 30) ===")
hist = safe("scheduler_run_history", "*", order="planned_at", lim=30)
for h in hist:
    print("  " + ", ".join(
        f"{k}={h.get(k)}" for k in sorted(h)
        if k in ("id", "scheduler_name", "planner_name", "planned_at",
                 "started_at", "finished_at", "status", "result", "error",
                 "trigger")))

print("\n=== jobs table: distinct job_type + status counts ===")
allj = safe("jobs", "job_type, status", order="created_at", lim=1000)
from collections import Counter  # noqa: E402
c = Counter((j.get("job_type"), j.get("status")) for j in allj)
for (jt, st), n in sorted(c.items(), key=lambda x: -x[1]):
    print(f"  {jt} / {st}: {n}")
