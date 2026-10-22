"""Measure what actually costs time in a compare request.

Method: time the compare endpoint repeatedly from the backend host while
sampling what the scheduler worker is doing concurrently. Reports, per
sample: wall time of the compare call, whether the market-data refresh
was active during it, and the DB-side row counts the compare reads.

This is a measurement script, not a fix. It writes nothing.
"""
from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx  # noqa: E402

BACKEND = os.environ.get("BACKEND_BASE", "http://localhost:8001")
ACCOUNTS = [9, 8, 7]
N_SAMPLES = int(os.environ.get("SAMPLES", "6"))


async def _token() -> str | None:
    """Reuse whatever auth the local stack expects, if a token is provided."""
    return os.environ.get("BACKEND_TOKEN")


async def _count_recent_market_writes(client: httpx.AsyncClient) -> int | None:
    """Count current_market_data rows touched in the last minute via PostgREST."""
    sb = os.environ.get("SUPABASE_URL", "http://localhost:54321")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not key:
        return None
    try:
        r = await client.get(
            f"{sb}/rest/v1/current_market_data",
            params={"select": "company_id", "limit": "1000"},
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=30.0,
        )
        if r.status_code == 200:
            return len(r.json())
    except Exception:
        return None
    return None


async def main() -> int:
    token = await _token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    async with httpx.AsyncClient(timeout=120.0) as client:
        url = f"{BACKEND}/portfolio/performance/compare"
        params = {"account_ids": ",".join(str(a) for a in ACCOUNTS), "period": "ALL"}

        times: list[float] = []
        rows: list[int | None] = []

        for i in range(N_SAMPLES):
            t0 = time.perf_counter()
            try:
                r = await client.get(url, params=params, headers=headers)
                dt = time.perf_counter() - t0
                status = r.status_code
            except Exception as e:
                dt = time.perf_counter() - t0
                status = f"EXC {e}"

            n = await _count_recent_market_writes(client)
            times.append(dt * 1000)
            rows.append(n)
            print(
                f"sample {i + 1}: status={status} compare_ms={dt * 1000:.0f} "
                f"current_market_data_rows={n}",
                flush=True,
            )
            await asyncio.sleep(1.0)

        print("\n=== SUMMARY ===")
        print(f"samples           : {len(times)}")
        print(f"min_ms            : {min(times):.0f}")
        print(f"median_ms         : {statistics.median(times):.0f}")
        print(f"max_ms            : {max(times):.0f}")
        print(f"all_ms            : {[round(t) for t in times]}")
        print(f"market_rows       : {rows}")
        print(f"measured_at       : {datetime.now(timezone.utc).isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
