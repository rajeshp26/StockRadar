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

    @property
    def interval_hours(self) -> int:
        return 0

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

        return [{
            "job_type": "price_ingestion",
            "dedupe_key": f"price_ingestion_{now_utc().isoformat()}",
            "priority": 40,
            "payload": {},
        }]
