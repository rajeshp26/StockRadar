"""
FX conversion service.

Provides currency conversion at the holding level using cached exchange
rates from the exchange_rates table, falling back to live yfinance fetch.

Caching strategy:
  - Instance-level dict with TTL (300s) — NOT a module global.
  - Each request/snapshot-rebuild creates its own FXService.
  - None results are cached briefly (60s) to avoid thundering herds.
"""

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from shared.time_utils import now_utc

logger = logging.getLogger(__name__)

CACHE_TTL = timedelta(seconds=300)
NONE_CACHE_TTL = timedelta(seconds=60)


class FXService:
    """Single concern: convert amounts between currencies using exchange rates."""

    MAX_STALE_DAYS = 7

    def __init__(self, supabase_client):
        self._client = supabase_client
        self._cache: dict[tuple[str, str, str], tuple[Decimal | None, datetime]] = {}

    def _cache_get(self, key: tuple[str, str, str]) -> Decimal | None:
        if key not in self._cache:
            return None
        val, ts = self._cache[key]
        ttl = NONE_CACHE_TTL if val is None else CACHE_TTL
        if now_utc() - ts > ttl:
            del self._cache[key]
            return None
        return val

    def _cache_set(self, key: tuple[str, str, str], val: Decimal | None) -> None:
        self._cache[key] = (val, now_utc())

    def get_rate(
        self, base: str, target: str, as_of: date | None = None
    ) -> Decimal | None:
        """Look up cached rate; fall back to live fetch (today only)."""
        as_of = as_of or now_utc().date()
        cache_key = (base.upper(), target.upper(), as_of.isoformat())

        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        if cache_key in self._cache:
            return None

        rate = self._query_cached_rate(base.upper(), target.upper(), as_of)
        if rate is not None:
            self._cache_set(cache_key, rate)
            return rate

        inverse_rate = self._query_cached_rate(target.upper(), base.upper(), as_of)
        if inverse_rate is not None and inverse_rate > 0:
            computed = Decimal("1") / inverse_rate
            self._cache_set(cache_key, computed)
            return computed

        if as_of == now_utc().date():
            rate = self._fetch_and_cache_today(base.upper(), target.upper())
            if rate is not None:
                self._cache_set(cache_key, rate)
                return rate

        self._cache_set(cache_key, None)
        return None

    def convert(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
        as_of: date | None = None,
    ) -> Decimal | None:
        """Convert amount. Returns None if no rate is available."""
        if from_currency.upper() == to_currency.upper():
            return amount
        rate = self.get_rate(from_currency, to_currency, as_of)
        if rate is None:
            return None
        return amount * rate

    def convert_or_warn(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
        as_of: date | None = None,
        holding_id: str | None = None,
    ) -> tuple[Decimal, bool]:
        """Convert or warn. Returns (converted_amount, fx_applied)."""
        result = self.convert(amount, from_currency, to_currency, as_of)
        if result is not None:
            return (result, True)
        logger.warning(
            "FX rate unavailable for %s->%s as_of %s (holding %s); using unconverted value",
            from_currency, to_currency, as_of, holding_id,
        )
        return (amount, False)

    def _query_cached_rate(
        self, base: str, target: str, as_of: date
    ) -> Decimal | None:
        """Check exchange_rates table for nearest-past rate within staleness limit."""
        res = (
            self._client.table("exchange_rates")
            .select("rate, rate_date")
            .eq("base_currency", base)
            .eq("target_currency", target)
            .lte("rate_date", as_of.isoformat())
            .order("rate_date", desc=True)
            .limit(1)
            .execute()
        )
        if res.data:
            row = res.data[0]
            rate_date = date.fromisoformat(row["rate_date"])
            days_stale = (as_of - rate_date).days
            if days_stale > self.MAX_STALE_DAYS:
                logger.warning(
                    "Cached FX rate %s->%s is %d days stale (max %d); ignoring",
                    base, target, days_stale, self.MAX_STALE_DAYS,
                )
                return None
            return Decimal(str(row["rate"]))
        return None

    def _fetch_and_cache_today(self, base: str, target: str) -> Decimal | None:
        """Live fetch via yfinance, cache under today's date only."""
        from providers.fx_provider import fetch_fx_rate
        rate = fetch_fx_rate(base, target)
        if rate is not None:
            today = now_utc().date()
            self._cache_rate(base, target, rate, today)
            return rate
        return None

    def _cache_rate(self, base: str, target: str, rate: Decimal, rate_date: date) -> None:
        """Upsert rate into exchange_rates. Raises if rate_date is in the future."""
        if rate_date > now_utc().date():
            raise ValueError(
                f"Refusing to cache rate dated in the future: {rate_date}"
            )
        self._client.table("exchange_rates").upsert({
            "base_currency": base,
            "target_currency": target,
            "rate": str(rate),
            "rate_date": rate_date.isoformat(),
            "source": "yfinance",
            "fetched_at": now_utc().isoformat(),
        }, on_conflict="base_currency,target_currency,rate_date").execute()
