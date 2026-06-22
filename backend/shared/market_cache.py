# backend/shared/market_cache.py
"""Thread-safe TTL cache for current_market_data lookups."""

import asyncio
import time
import logging
from typing import Dict, List
from database import supabase


logger = logging.getLogger(__name__)

_cache: Dict[str, any] = {"data": {}, "expires_at": 0.0}
TTL_SECONDS = 30
_lock = asyncio.Lock()


MAX_CACHE_SIZE = 5000

async def get_cached_prices(company_ids: List[int]) -> Dict[int, float]:
    now = time.time()
    if now <= _cache["expires_at"]:
        return {cid: _cache["data"][cid] for cid in company_ids if cid in _cache["data"]}

    async with _lock:
        if now <= _cache["expires_at"]:
            return {cid: _cache["data"][cid] for cid in company_ids if cid in _cache["data"]}

        res = (
            supabase.table("current_market_data")
            .select("company_id, current_price")
            .execute()
        )
        _cache["data"] = {
            row["company_id"]: float(row["current_price"])
            for row in (res.data or [])
            if row.get("current_price") is not None
        }
        if not res.data:
            logger.warning("[CACHE] current_market_data returned empty — keeping stale cache")

        if len(_cache["data"]) > MAX_CACHE_SIZE:
            _cache["data"] = {}
            logger.warning(f"[CACHE] Flushed ({MAX_CACHE_SIZE} entries exceeded)")

        _cache["expires_at"] = time.time() + TTL_SECONDS
        logger.debug(f"[CACHE] Refreshed {len(_cache['data'])} companies")

    return {cid: _cache["data"][cid] for cid in company_ids if cid in _cache["data"]}
