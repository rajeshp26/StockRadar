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
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from shared.time_utils import now_utc

logger = logging.getLogger(__name__)

CACHE_TTL = timedelta(seconds=300)
NONE_CACHE_TTL = timedelta(seconds=60)
# as_of older than this never triggers a network fetch (rebuilds stay offline)
LIVE_FETCH_WINDOW_DAYS = 45

# Sentinel bucket for cash whose currency the event never recorded.
#
# Position checkpoints (initial_holding_set / position_state_checkpoint) carry a
# bare `cash_balance` with no currency. That value is not an unknown currency --
# it was produced by an already-currency-aware snapshot, so it is by construction
# denominated in the account's functional currency. It is bucketed separately
# rather than guessed into a real code so the distinction stays auditable.
UNSTAMPED_CURRENCY = "UNSTAMPED"


def normalize_currency(value: Any) -> str:
    """Uppercase a currency code; None is an expected input, not an error.

    Events written before currency provenance was preserved have no `currency` key.
    """
    if value is None:
        return UNSTAMPED_CURRENCY
    code = str(value).strip().upper()
    return code or UNSTAMPED_CURRENCY


def convert_cash_map(
    cash_by_currency: Mapping[str, Decimal],
    account_currency: str,
    as_of: date,
    fx_service: "FXService | None",
) -> tuple[Decimal, bool | None]:
    """Collapse a per-currency cash map into one account-currency total.

    This is the cash-side equivalent of `convert_holding_fx`, and deliberately
    shares its rate policy: FXService resolves "last close on or before as_of",
    so a historical total is reproducible and cannot drift when a new rate lands.

    Args:
        cash_by_currency: currency code -> amount. The UNSTAMPED bucket is
            treated as already being in `account_currency` and passes through.
        account_currency: presentation currency for the account.
        as_of: valuation date; selects the rate for every bucket.
        fx_service: None when FX conversion is disabled repo-wide.

    Returns:
        (total, fx_applied) where fx_applied is:
          None -> conversion was not attempted (FX disabled); caller must not
                  treat the total as unconverted, or every snapshot would be
                  flagged and LOCF step-suppression would fire everywhere.
          True -> every non-account bucket was converted at a real rate.
          False -> at least one bucket had no available rate and passed through
                   unconverted. The total is then a mixed-currency sum and MUST
                   be surfaced, never silently charted.
    """
    target = normalize_currency(account_currency)
    total = Decimal("0.00")
    attempted = fx_service is not None
    fx_applied = True

    for code, amount in cash_by_currency.items():
        amount = Decimal(str(amount))
        if amount == 0:
            continue
        if code in (target, UNSTAMPED_CURRENCY):
            total += amount
            continue
        if fx_service is None:
            total += amount
            fx_applied = False
            continue
        converted, applied = fx_service.convert_or_warn(
            amount, code, target, as_of=as_of, holding_id=f"cash:{code}"
        )
        total += converted
        fx_applied = fx_applied and applied

    return total, (fx_applied if attempted else None)


class FXService:
    """Single concern: convert amounts between currencies using exchange rates."""

    MAX_STALE_DAYS = 7

    def __init__(self, supabase_client):
        self._client = supabase_client
        self._cache: dict[tuple[str, str, str], tuple[Decimal | None, datetime]] = {}
        # I4: at most one gap-heal fetch per pair per service instance. An
        # FXService is created per request/snapshot rebuild, so a rebuild that
        # resolves hundreds of dates never turns this into hundreds of fetches.
        self._healed_pairs: set[tuple[str, str]] = set()
        # I31: the stale-rate condition is identified by the close being
        # forward-filled, not by the query date. A rebuild resolves hundreds of
        # as_of dates against the same stale close; warn once for that close.
        # A different close (ingestion landed a new rate) warns again.
        self._warned_stale_closes: set[tuple[str, str, date]] = set()
        self.stale_warning_suppressed: int = 0

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
        """Resolve effective rate for as_of: past (forward-filled) -> future -> live fetch.

        The effective rate on date D is the last close on or before D; when none
        exists (D precedes all stored rates) the nearest future close is used.
        For recent as_of dates with no stored rate at all, a short yfinance
        history slice is fetched and persisted under its actual close dates, so
        the gap heals permanently. Historical as_of dates (outside the live
        window) never touch the network.
        """
        as_of = as_of or now_utc().date()
        cache_key = (base.upper(), target.upper(), as_of.isoformat())

        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        if cache_key in self._cache:
            return None

        # I4: forward-fill is the valuation policy, but it must not be a trap.
        # A rate older than MAX_STALE_DAYS used to be returned here immediately,
        # which short-circuited every gap-healing path below: once ingestion
        # stopped, the same stale close was reused forever (57 days locally).
        # Try one bounded refresh over the missing range first, then fall back
        # to the stale rate with the usual warning if the fetch is unavailable.
        b, t = base.upper(), target.upper()
        record = self._query_cached_rate_record(b, t, as_of)
        if record is not None:
            rate, rate_date = record
            if (as_of - rate_date).days > self.MAX_STALE_DAYS:
                healed = self._heal_stale_rate(b, t, as_of, rate_date)
                if healed is not None:
                    rate = healed
                else:
                    self._warn_stale_rate(b, t, as_of, rate_date)
            self._cache_set(cache_key, rate)
            return rate

        inverse_rate = self._query_cached_rate(target.upper(), base.upper(), as_of)
        if inverse_rate is not None and inverse_rate > 0:
            computed = Decimal("1") / inverse_rate
            self._cache_set(cache_key, computed)
            return computed

        rate = self._query_future_rate(base.upper(), target.upper(), as_of)
        if rate is not None:
            self._cache_set(cache_key, rate)
            return rate
        inverse_rate = self._query_future_rate(target.upper(), base.upper(), as_of)
        if inverse_rate is not None and inverse_rate > 0:
            computed = Decimal("1") / inverse_rate
            self._cache_set(cache_key, computed)
            return computed

        today = now_utc().date()
        if as_of <= today and (today - as_of).days <= LIVE_FETCH_WINDOW_DAYS:
            self._fetch_and_persist_history(
                base.upper(), target.upper(), as_of - timedelta(days=7), today
            )
            rate = self._query_cached_rate(base.upper(), target.upper(), as_of)
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

    def _query_cached_rate_record(
        self, base: str, target: str, as_of: date
    ) -> tuple[Decimal, date] | None:
        """The nearest-past rate and its close date, or None. Forward-fill raw material."""
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
            return Decimal(str(row["rate"])), date.fromisoformat(row["rate_date"])
        return None

    def _warn_stale_rate(
        self, base: str, target: str, as_of: date, rate_date: date
    ) -> None:
        """Freshness signal: a stale rate is still used, but never silently (I4).

        I31: emitted once per (pair, stale close) per service instance. The
        message text is unchanged so a single occurrence still reads exactly
        as I4's contract asserts.
        """
        days_stale = (as_of - rate_date).days
        if days_stale > self.MAX_STALE_DAYS:
            key = (base, target, rate_date)
            if key in self._warned_stale_closes:
                self.stale_warning_suppressed += 1
                return
            self._warned_stale_closes.add(key)
            logger.warning(
                "FX rate %s->%s is %d days old (beyond %d-day freshness "
                "window); forward-filling it rather than dropping the conversion",
                base, target, days_stale, self.MAX_STALE_DAYS,
            )

    def _heal_stale_rate(
        self, base: str, target: str, as_of: date, rate_date: date
    ) -> Decimal | None:
        """Try one bounded fetch over the gap; return a fresher rate if one landed.

        I4: a stopped ingestion job used to leave every CAD holding valued at a
        54-day-old close. The refresh is deliberately conservative:

        * at most one fetch per pair per service instance (a rebuild resolves
          hundreds of dates; it must not become hundreds of network calls);
        * only for as_of dates inside the existing LIVE_FETCH_WINDOW_DAYS, so
          historical rebuilds stay offline;
        * failure is non-fatal -- the caller falls back to the stale rate and
          warns, preserving the "never drop the conversion" policy.
        """
        pair = (base, target)
        if pair in self._healed_pairs:
            return None
        self._healed_pairs.add(pair)

        today = now_utc().date()
        if as_of > today or (today - as_of).days > LIVE_FETCH_WINDOW_DAYS:
            return None
        if rate_date >= today:
            return None

        try:
            self._fetch_and_persist_history(
                base, target, rate_date + timedelta(days=1), today
            )
        except Exception as exc:  # provider/network failure is a fallback, not a crash
            logger.warning("FX gap refresh failed for %s->%s: %s", base, target, exc)
            return None

        record = self._query_cached_rate_record(base, target, as_of)
        if record is None or record[1] <= rate_date:
            return None
        return record[0]

    def _query_cached_rate(
        self, base: str, target: str, as_of: date
    ) -> Decimal | None:
        """Check exchange_rates table for nearest-past rate (any age).

        Forward-fill semantics: the last close on or before as_of is the
        effective rate regardless of age. Rates older than MAX_STALE_DAYS log
        a warning (freshness signal) but are still used - dropping them is what
        produced unconverted values and the Jul->Aug spike. Returns None only
        when no past rate exists at all.
        """
        record = self._query_cached_rate_record(base, target, as_of)
        if record is None:
            return None
        rate, rate_date = record
        self._warn_stale_rate(base, target, as_of, rate_date)
        return rate

    def _query_future_rate(
        self, base: str, target: str, as_of: date
    ) -> Decimal | None:
        """Find nearest-FUTURE rate, for as_of dates before the earliest known close."""
        res = (
            self._client.table("exchange_rates")
            .select("rate, rate_date")
            .eq("base_currency", base)
            .eq("target_currency", target)
            .gte("rate_date", as_of.isoformat())
            .order("rate_date", asc=True)
            .limit(1)
            .execute()
        )
        if res.data:
            return Decimal(str(res.data[0]["rate"]))
        return None

    def _fetch_and_persist_history(
        self, base: str, target: str, start_date: date, end_date: date
    ) -> int:
        """Live-fetch daily closes over [start_date, end_date] and persist each.

        Each close is stored under its actual calendar date (never 'today'),
        permanently healing gaps. Returns the number of rows persisted (0 on
        failure or when nothing new was available).
        """
        from providers.fx_provider import fetch_fx_history
        rows = fetch_fx_history(base, target, start_date, end_date)
        persisted = 0
        for rate_date, rate in rows:
            try:
                self._cache_rate(base, target, rate, rate_date)
                persisted += 1
            except ValueError:
                continue
        return persisted

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
