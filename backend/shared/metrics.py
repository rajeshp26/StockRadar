# backend/shared/metrics.py
"""Minimal route-level timing without Prometheus dependency."""

import logging
import time

logger = logging.getLogger("perf.portfolio")


class RouteTimer:
    """Context manager that logs endpoint duration with metadata."""
    def __init__(self, endpoint: str, user_id: int, account_count: int = 0, holdings_count: int = 0, cache_hit: bool = False):
        self.endpoint = endpoint
        self.user_id = user_id
        self.account_count = account_count
        self.holdings_count = holdings_count
        self.cache_hit = cache_hit
        self.start: float = 0.0

    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, *args):
        elapsed = (time.perf_counter() - self.start) * 1000
        logger.info(
            f"[PERF] {self.endpoint} user={self.user_id} "
            f"accounts={self.account_count} holdings={self.holdings_count} "
            f"cache_hit={self.cache_hit} duration={elapsed:.1f}ms"
        )
