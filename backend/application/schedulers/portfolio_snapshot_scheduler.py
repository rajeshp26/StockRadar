import logging
from datetime import date
from typing import Any, Dict, List

from shared.time_utils import now_utc

logger = logging.getLogger("stockerpro.portfolio.snapshot_scheduler")


class PortfolioSnapshotScheduler:
    """Plans portfolio snapshot jobs. Runs daily at 23:00 UTC."""

    @property
    def interval_hours(self) -> int:
        return 24

    async def plan(self) -> List[Dict[str, Any]]:
        """Plan a single batch job for all active accounts."""
        return [{
            "job_type": "portfolio_snapshot",
            "dedupe_key": f"snapshot_{now_utc().date().isoformat()}",
            "priority": 50,
            "payload": {"date": now_utc().date().isoformat()},
        }]
