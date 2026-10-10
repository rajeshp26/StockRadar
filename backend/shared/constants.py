# backend/shared/constants.py

# HTTP Headers
AUTHORIZATION_HEADER = "Authorization"
BEARER_PREFIX = "Bearer "

# ---------------------------------------------------------------------------
# Delisted / renamed symbols that must never hit a live quote provider.
# These tickers are permanently dead on Yahoo Finance (404 / no data) and
# would otherwise spin retries + timeout spam on every refresh cycle.
# Merged with the SKIPPED_TICKER_SYMBOLS env var by get_effective_skipped_symbols().
#
# NOTE: BK is intentionally NOT here — it is Canadian Banc Corp Class A
# (trades as BK.TO on TSX), a live listing, not the delisted BNY Mellon.
# ---------------------------------------------------------------------------
DELISTED_SYMBOLS: frozenset[str] = frozenset({"NYCB", "CS", "CMA", "WBA", "PSYK", "HYLD"})


def get_effective_skipped_symbols() -> set[str]:
    """Union of env-configured and hardcoded delisted/renamed symbols.

    Single source of truth consumed by both the market-data scheduler and
    the price-ingestion job so delisted tickers are filtered in one place.
    """
    from config import settings  # local import avoids any config->shared cycle

    env_skipped = {
        s.strip().upper()
        for s in getattr(settings, "SKIPPED_TICKER_SYMBOLS", "").split(",")
        if s.strip()
    }
    return env_skipped | set(DELISTED_SYMBOLS)
