import logging
from datetime import UTC, datetime
from typing import Any

from shared.time_utils import now_utc

logger = logging.getLogger("stockerpro.price.scheduler")


class PriceIngestionScheduler:
    """Plans price ingestion jobs with market-hours awareness.
    
    Schedule (ET):
    - 09:30-16:00 (trading hours): every 5 min
    - 07:00-09:30, 16:00-20:00 (pre/post market): every 30 min
    - 20:00-07:00 (closed): suspended
    """

    def __init__(self) -> None:
        # In-memory cadence gate: tracks when the last job was enqueued so
        # plan() can refuse to emit another until the current interval window
        # has elapsed (5 min trading / 30 min pre-post).  The planner ticks
        # every 60s, so without this gate the job would be re-enqueued every
        # tick once the prior run completes (Sep-2026 defect S1).
        self._last_enqueued_at: datetime | None = None

    @property
    def interval_hours(self) -> float:
        """Current interval in hours (0 = suspended, 5/60 = trading, 30/60 = pre/post)."""
        return self._current_interval_minutes() / 60.0

    def _current_interval_minutes(self) -> int:
        now_et = datetime.now(UTC)
        hour = now_et.hour - 4
        minute = now_et.minute
        total_minutes = hour * 60 + minute

        if 570 <= total_minutes < 960:
            return 5
        elif 420 <= total_minutes < 570 or 960 <= total_minutes < 1200:
            return 30
        else:
            return 0

    async def plan(self) -> list[dict[str, Any]]:
        interval = self._current_interval_minutes()
        if interval == 0:
            return []

        now = now_utc()
        if self._last_enqueued_at is not None:
            elapsed_min = (now - self._last_enqueued_at).total_seconds() / 60.0
            if elapsed_min < interval:
                logger.debug(
                    "[PRICE] Within %d-min window (%.1f min since last job) — skip",
                    interval, elapsed_min,
                )
                return []

        self._last_enqueued_at = now

        # Windowed dedupe_key: bucket time to the interval so consecutive planner
        # ticks within the same window (5min trading / 30min pre-post) produce the
        # same key and the enqueue dedup layer merges them.  Previously the key
        # used second-granularity timestamps, so every planner tick enqueued a
        # fresh job regardless of the computed interval (Sep-2026 defect S1).
        minute_of_day = now.hour * 60 + now.minute
        bucket = minute_of_day // interval
        dedupe_key = f"price_ingestion_{interval}m_{bucket}"

        return [{
            "job_type": "price_ingestion",
            "dedupe_key": dedupe_key,
            "priority": 40,
            "payload": {"interval_minutes": interval},
        }]
