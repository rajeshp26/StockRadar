import logging
from typing import Any

from shared.time_utils import now_utc

logger = logging.getLogger("stockerpro.portfolio.benchmark_series_scheduler")


class BenchmarkSeriesRefreshScheduler:
    """Plans the materialised-benchmark refresh job.

    Runs every 24h. It is deliberately NOT the snapshot scheduler: the refresh
    must read the day's snapshots and price rows, so it has to land after them.
    Ordering is expressed by the plan payload (the refresh job is scheduled on
    its own interval and simply reads whatever exists), and the guard inside
    the job tolerates an early run by advancing only what is available.
    """

    @property
    def interval_hours(self) -> int:
        return 24

    async def plan(self) -> list[dict[str, Any]]:
        """Plan one refresh per day for the current date."""
        return [{
            "job_type": "benchmark_series_refresh",
            "dedupe_key": f"benchmark_series_{now_utc().date().isoformat()}",
            "priority": 60,
            "payload": {"date": now_utc().date().isoformat()},
        }]
