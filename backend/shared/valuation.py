"""Single source of truth for CDR + FX price adjustment.

Every layer that turns a raw market quote into a CDR unit price routes through
:func:`adjust_cdr_price`. Before this module the rule was copied into
``shared.snapshot_builder``, ``shared.replay_engine``,
``application.services.portfolio_service._enrich_holdings``,
``api.portfolio.apply_cdr_adjustment``, ``shared.price_utils`` and
``application.services.watchlist_service``, and the copies drifted: the snapshot
applied the USD->CAD FX step for US-sourced CDR prices and the live/overview
copies did not, so the Overview card understated every CDR holding by the FX
factor.

The rule, in one place:

  * not a CDR             -> the raw price is returned unchanged.
  * CDR, CAD-native price -> ``raw / ratio``   (already in account currency).
  * CDR, US/USD price     -> ``(raw / ratio) * fx_rate``
                             (``fx_rate`` None -> ``raw / ratio`` fallback).

"CAD-native" is decided by the caller's ``price_source`` (a ``yfinance_tor`` feed
is the CDR's own TSX price, already CAD) or by ``price_currency`` already
equalling the account currency. This generalises the pre-existing snapshot
decision (``source == "price_history"`` -> apply FX) so the live paths can make
the exact same decision instead of silently omitting FX.

The function is pure: it performs no I/O and takes the FX rate as an argument.
Callers own rate lookup (per the "convert at the edge" rule in
``docs/FX_CURRENCY_CONVERSION_DESIGN.md``) and pass it in.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from shared.cdr_utils import CDR_RATIO, EXCHANGE_OVERRIDE_TOR, trace_division

#: Sources whose raw price is already the CDR's own account-currency (CAD) quote.
#: Anything else is treated as the underlying US (USD) price and FX-converted
#: after the ratio division.
CAD_NATIVE_SOURCES = frozenset({"yfinance_tor", "cdr_feed"})

DEFAULT_ACCOUNT_CURRENCY = "CAD"


def _decimal(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


@dataclass(frozen=True)
class AdjustedPrice:
    """Result of the CDR transform.

    ``price`` is expressed in ``account_currency`` (CAD for this platform).
    ``cdr_ratio_applied`` and ``fx_rate_applied`` are the exact factors used, so
    a stored row reconciles offline as ``raw_price / ratio * fx``; both are None
    for a non-CDR holding.
    """

    price: Decimal
    cdr_ratio_applied: Decimal | None = None
    fx_rate_applied: Decimal | None = None
    is_cdr: bool = False


def resolve_cdr_ratio(
    cdr_ratio: Decimal | float | None,
    fallback: Decimal | float | None = None,
) -> Decimal:
    """Per-company ratio when present, else the structural constant.

    The CDR ratio is a fixed structural property (1 CDR = 1/ratio of the
    underlying US share); a None value must fall back to the constant, never to
    "assume not a CDR" -- doing so divided a CDR tenfold (the original defect).
    """
    ratio = _decimal(cdr_ratio)
    if ratio is not None and ratio > 0:
        return ratio
    fallback_d = _decimal(fallback)
    if fallback_d is not None and fallback_d > 0:
        return fallback_d
    return _decimal(CDR_RATIO) or Decimal("10")


def is_cad_native_source(
    price_source: str | None,
    price_currency: str | None,
    account_currency: str = DEFAULT_ACCOUNT_CURRENCY,
) -> bool:
    """True when the raw price is already in account currency (no FX needed)."""
    if price_source and price_source in CAD_NATIVE_SOURCES:
        return True
    if price_currency:
        return price_currency.upper() == account_currency.upper()
    return False


def adjust_cdr_price(
    raw_price: Decimal | float,
    *,
    is_cdr: bool,
    cdr_ratio: Decimal | float | None = None,
    price_source: str | None = None,
    price_currency: str | None = None,
    account_currency: str = DEFAULT_ACCOUNT_CURRENCY,
    fx_rate: Decimal | float | None = None,
    layer: str = "unknown",
    company_id: int | None = None,
) -> AdjustedPrice:
    """Apply the single CDR valuation rule to one raw price.

    Args:
        raw_price: the raw quote (US price for a US source, CAD for a
            ``yfinance_tor`` source).
        is_cdr: whether this holding is a CDR (from ``cdr_utils`` canonical
            classification, or the holding's own resolved override).
        cdr_ratio: per-company ratio; None falls back to the structural constant.
        price_source: e.g. ``"price_history"``, ``"yfinance_tor"``,
            ``"current_market_data"``.
        price_currency: native currency of ``raw_price`` (e.g. ``"USD"``).
        account_currency: target currency (default ``"CAD"``).
        fx_rate: ``price_currency -> account_currency`` rate for the valuation
            date; None means unavailable and the ratio-only fallback is used.

    Returns:
        :class:`AdjustedPrice` in ``account_currency``.
    """
    price = _decimal(raw_price)
    if price is None:
        return AdjustedPrice(price=Decimal("0"), is_cdr=is_cdr)

    if not is_cdr:
        return AdjustedPrice(price=price, is_cdr=False)

    ratio = resolve_cdr_ratio(cdr_ratio)
    adjusted = price / ratio
    fx_applied: Decimal | None = None

    if not is_cad_native_source(price_source, price_currency, account_currency):
        rate = _decimal(fx_rate)
        if rate is not None and rate > 0:
            adjusted = adjusted * rate
            fx_applied = rate

    trace_division(
        layer,
        company_id if company_id is not None else 0,
        float(price),
        float(ratio),
        float(adjusted),
        price_source=price_source or "unknown",
    )
    return AdjustedPrice(
        price=adjusted,
        cdr_ratio_applied=ratio,
        fx_rate_applied=fx_applied,
        is_cdr=True,
    )


def is_cdr_override(exchange_override: str | None) -> bool:
    """Holding-level CDR flag; the only value that means "priced on TSX"."""
    return exchange_override == EXCHANGE_OVERRIDE_TOR
