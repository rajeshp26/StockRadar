import bisect
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any

from shared.time_utils import now_utc


def _normalise_trade_date(val: Any) -> date | None:
    """Convert trade_date from string or date to date object."""
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, str):
        try:
            return date.fromisoformat(val)
        except (ValueError, TypeError):
            return None
    return None


def convert_holding_fx(
    holding: dict,
    raw_value: Decimal,
    total_cost: Decimal,
    account_currency: str,
    fx_service: Any,
    snapshot_date: date,
    enable_fx: bool = True,
) -> tuple[Decimal, Decimal]:
    """Convert holding values from price_currency to account_currency.

    Single source of truth for FX conversion at the holding level.
    Used by build_snapshot_row, build_snapshot_from_replay, and live API enrichment.

    Rules:
      - Market value is converted at snapshot_date (the price is current).
      - Cost basis is converted per-lot at each lot's trade_date when lots exist.
      - Cost basis is converted at trade_date (earliest lot) when lots are absent.
      - If FX rate is unavailable, the unconverted value is returned with a warning.

    Args:
        holding: dict with at least price_currency/currency, and optionally lots, trade_date
        raw_value: market value in price_currency (qty * current_price)
        total_cost: cost basis in price_currency
        account_currency: target currency (e.g. "CAD")
        fx_service: FXService instance (may be None if enable_fx is False)
        snapshot_date: date for market value FX rate
        enable_fx: whether FX conversion is enabled globally

    Returns:
        (converted_value, converted_cost) — both Decimal, in account_currency.
    """
    price_currency = (holding.get("price_currency") or holding.get("currency") or "USD").upper()
    acct = account_currency.upper()

    needs_fx = enable_fx and price_currency != acct and fx_service is not None

    if not needs_fx:
        return raw_value, total_cost

    # Market value: always at snapshot_date (current price)
    converted_value = raw_value
    if raw_value > 0:
        conv_val, _ = fx_service.convert_or_warn(
            raw_value, price_currency, acct,
            as_of=snapshot_date, holding_id=str(holding.get("company_id")),
        )
        converted_value = conv_val

    # Cost basis: per-lot when lots exist, single-date fallback otherwise
    converted_cost = total_cost
    if total_cost > 0:
        lots = holding.get("lots") or []
        if lots:
            total_cost_converted = Decimal("0")
            for lot in lots:
                lot_cost = Decimal(str(lot["quantity"])) * Decimal(str(lot["cost_per_share"]))
                lot_date = _normalise_trade_date(lot.get("date")) or snapshot_date
                lot_fx_rate = fx_service.get_rate(price_currency, acct, lot_date)
                if lot_fx_rate is not None:
                    total_cost_converted += lot_cost * lot_fx_rate
                else:
                    total_cost_converted += lot_cost
            converted_cost = total_cost_converted
        else:
            cost_fx_date = _normalise_trade_date(holding.get("trade_date")) or snapshot_date
            conv_cost, _ = fx_service.convert_or_warn(
                total_cost, price_currency, acct,
                as_of=cost_fx_date, holding_id=str(holding.get("company_id")),
            )
            converted_cost = conv_cost

    return converted_value, converted_cost

logger = logging.getLogger(__name__)


class PriceTier(Enum):
    CURRENT = "CURRENT"
    FORWARD_FILL = "FORWARD"
    COST_BASIS = "COST_FALLBACK"
    UNAVAILABLE = "UNAVAILABLE"


TIER_QUALITY_MAP = {
    PriceTier.CURRENT: "OK",
    PriceTier.FORWARD_FILL: "STALE_PRICE",
    PriceTier.COST_BASIS: "COST_FALLBACK",
    PriceTier.UNAVAILABLE: "INCOMPLETE",
}
"""Maps each price tier to the worst quality flag it produces."""

TIER_ORDER = [PriceTier.CURRENT, PriceTier.FORWARD_FILL,
              PriceTier.COST_BASIS, PriceTier.UNAVAILABLE]


CDR_RATIO = Decimal("10")
"""CDR ratio for CIBC CAD-Hedged CDRs. A CDR represents 1/CDR_RATIO of the underlying US share.
Applies when holding.exchange_override == "TOR" and the company's primary exchange is US-listed."""


def get_cdr_ratio_for_company(
    company_id: int,
    companies_map: dict[int, dict] | None = None,
) -> Decimal | None:
    """Look up per-company CDR ratio from the companies table.

    Returns the ratio if found, None otherwise (callers should fall back to CDR_RATIO constant).
    """
    if companies_map and company_id in companies_map:
        info = companies_map[company_id]
        ratio = info.get("cdr_ratio")
        if ratio is not None:
            return Decimal(str(ratio))
    return None


def _resolve_holding_price(
    company_id: int,
    symbol: str,
    avg_cost: Decimal | None,
    latest_prices: dict[int, dict],
    price_history: dict[int, list[tuple]],
    snapshot_date: date,
    stale_threshold_days: int = 30,
    exchange_override: str | None = None,
    cdr_ratio: Decimal | None = None,
    company_currency: str | None = None,
    price_source: str | None = None,
    fx_service: Any | None = None,
) -> tuple[Decimal | None, PriceTier, date | None]:
    """4-tier price cascade.

    Tier 1 (CURRENT) only used if price_date is recent enough (<= stale_threshold_days old).
    Otherwise falls through to Tier 2 (forward-fill) for accurate historical pricing.

    When exchange_override="TOR": market-sourced prices (Tiers 1 & 2) come from US exchanges
    and must be divided by cdr_ratio (per-company, fallback to CDR_RATIO=10).

    Source-aware CDR logic:
      - price_source="yfinance_tor": price is TSX share price in CAD → divide by ratio only.
      - price_source="price_history" or other: price is US stock in USD → divide by ratio AND
        multiply by FX (USD→CAD) to get CDR price in CAD.
      - fx_service: FXService instance for FX rate lookup (required for non-yfinance_tor sources).

    Tier 3 (cost_basis) is NOT adjusted — CDR purchase prices are already at actual CDR cost.

    Returns (price, tier, price_date). Returns (None, UNAVAILABLE, None) if no price is usable.
    """
    is_cdr = exchange_override == "TOR"
    effective_ratio = cdr_ratio if cdr_ratio is not None else CDR_RATIO

    def _apply_cdr(price_val: Decimal, src: str | None = None) -> Decimal:
        """Apply CDR ratio (and FX if needed) to convert market price to CDR price in CAD."""
        result = price_val / effective_ratio
        # For price_history source: price is US USD, need FX to convert to CAD
        if is_cdr and src == "price_history" and fx_service is not None:
            fx_rate = fx_service.get_rate("USD", "CAD", snapshot_date)
            if fx_rate is not None:
                result = result * fx_rate
        return result

    # Tier 1: current market price — only for recent snapshots
    info = latest_prices.get(company_id, {})
    if info.get("price") is not None:
        pd = info.get("price_date")
        tier1_source = info.get("source") or price_source
        if pd is not None:
            if isinstance(pd, str):
                pd = date.fromisoformat(pd)
            elif isinstance(pd, datetime):
                pd = pd.date()
            if pd > snapshot_date:
                max_age = timedelta(days=stale_threshold_days)
                if (pd - snapshot_date) <= max_age:
                    price = Decimal(str(info["price"]))
                    if is_cdr:
                        price = _apply_cdr(price, tier1_source)
                    return price, PriceTier.CURRENT, pd
            else:
                # current price is from before or same as snapshot — safe to use
                price = Decimal(str(info["price"]))
                if is_cdr:
                    price = _apply_cdr(price, tier1_source)
                return price, PriceTier.CURRENT, pd
        else:
            # no price_date — use current price as best-effort
            price = Decimal(str(info["price"]))
            if is_cdr:
                price = _apply_cdr(price, tier1_source)
            return price, PriceTier.CURRENT, None

    # Tier 2: forward-fill from price_history (most recent price <= snapshot_date)
    result = resolve_price_forward_filled(company_id, snapshot_date, price_history)
    if result is not None and result.get("price") is not None:
        price = Decimal(str(result["price"]))
        if is_cdr:
            price = _apply_cdr(price, "price_history")
        result_date = result.get("price_date")
        if isinstance(result_date, str):
            result_date = date.fromisoformat(result_date)
        elif isinstance(result_date, datetime):
            result_date = result_date.date()
        return price, PriceTier.FORWARD_FILL, result_date

    # Tier 3: average_cost as price proxy — DISABLED.
    # Using cost basis as a price produces wildly incorrect values (e.g., TNXP
    # cost $0.28 vs real price $13.91). Holdings without market prices are
    # marked UNAVAILABLE and excluded from the snapshot value. The daily job
    # will capture them once current_market_data has their prices.

    # Tier 4: unavailable — skip this holding entirely
    return None, PriceTier.UNAVAILABLE, None


def _validate_snapshot(
    total_value: Decimal,
    holdings_market_value: Decimal,
    cash_balance: Decimal,
    cost_basis: Decimal,
    holdings_count: int,
    used_tiers: list[PriceTier],
) -> list[str]:
    """Post-computation validation. Returns list of warning strings.
    
    W1: Zero market value with non-zero holdings
    W2: Negative total with positive holdings value
    W3: Cash too negative relative to cost basis (possible missing deposits)
    """
    warnings: list[str] = []

    if holdings_count > 0 and holdings_market_value <= 0:
        warnings.append(
            f"Zero holdings market value despite {holdings_count} non-zero holdings"
        )

    if total_value < 0 and holdings_market_value > 0:
        warnings.append(
            f"Negative total {float(total_value):.2f} despite "
            f"positive holdings value {float(holdings_market_value):.2f}"
        )

    if cash_balance < 0 and cost_basis > 0:
        max_negative = -cost_basis * Decimal("0.7")
        if cash_balance < max_negative:
            warnings.append(
                f"Cash balance {float(cash_balance):.2f} exceeds max negative "
                f"{float(max_negative):.2f} (cost_basis={float(cost_basis):.2f}). "
                f"Possible missing deposit transactions."
            )

    return warnings


def _should_process_for_lots(txn: dict) -> bool:
    activity_type = (txn.get("activity_type") or "").upper()
    activity_sub_type = (txn.get("activity_sub_type") or "").upper()
    if activity_type != "TRADE":
        return False
    if activity_sub_type not in ("BUY", "SELL"):
        return False
    return True


def _classify_lot_action(txn: dict) -> str | None:
    if not _should_process_for_lots(txn):
        return None
    sub = (txn.get("activity_sub_type") or "").upper()
    qty = Decimal(str(txn.get("quantity") or 0))
    if sub == "BUY" and qty > 0:
        return "BUY"
    elif sub == "SELL" and qty < 0:
        return "SELL"
    return None


def resolve_price_forward_filled(
    company_id: int,
    target_date: date,
    price_map: dict[int, list[tuple]],
) -> dict | None:
    prices = price_map.get(company_id, [])
    if not prices:
        return None
    i = bisect.bisect_right(prices, (target_date, float("inf"))) - 1
    if i >= 0:
        pd, pr = prices[i]
        return {"price": pr, "price_date": pd}
    return None


def build_snapshot_row(
    account_id: int,
    snapshot_date: date,
    holdings_state: list[dict],
    cash_balance: Decimal,
    net_deposits: Decimal,
    prices_by_company: dict[int, dict],
    job_id: str,
    stale_threshold_days: int = 30,
    account_currency: str = "CAD",
    fx_service: Any | None = None,
    price_history: dict[int, list[tuple]] | None = None,
    exchange_overrides: dict[int, str | None] | None = None,
    company_currencies: dict[int, str] | None = None,
    companies_map: dict[int, dict] | None = None,
) -> dict[str, Any]:
    from config import settings
    enable_fx = getattr(settings, "ENABLE_FX_CONVERSION", False)
    total_market_value = Decimal("0.00")
    total_cost = Decimal("0.00")
    holdings_detail = []
    used_tiers: list[PriceTier] = []
    non_zero_holdings_count = 0

    for h in holdings_state:
        cid = h.get("company_id")
        qty = Decimal(str(h.get("quantity") or 0))
        cost = Decimal(str(h.get("total_cost") or 0))
        price_currency = h.get("price_currency") or h.get("currency") or "USD"

        if cost == 0 and qty > 0:
            has_old_key = "cost_basis" in h and "total_cost" not in h
            if has_old_key:
                raise ValueError(
                    f"Holding {cid} (account {account_id}): old key 'cost_basis' used "
                    f"instead of 'total_cost'. Available keys: {sorted(h.keys())}"
                )
            logger.warning(
                "Holding %s (account %s): cost_basis=0, quantity=%s. "
                "Zero-cost holdings will show as 100%% gain.",
                cid, account_id, qty,
            )

        assert h.get("value_currency") is None, \
            f"Holding {cid} already has value_currency={h['value_currency']}; would double-convert"

        if qty == 0:
            continue

        non_zero_holdings_count += 1

        # 4-tier price resolution
        avg_cost = Decimal(str(h.get("average_cost") or 0))
        exch_override = exchange_overrides.get(cid) if exchange_overrides else None
        comp_ccy = (company_currencies.get(cid) if company_currencies else None) or h.get("price_currency") or h.get("currency") or "USD"
        # Look up per-company CDR ratio
        comp_ratio = get_cdr_ratio_for_company(cid, companies_map) if companies_map else None

        current_price, tier, resolved_price_date = _resolve_holding_price(
            company_id=cid,
            symbol=h.get("symbol", ""),
            avg_cost=avg_cost if avg_cost > 0 else None,
            latest_prices=prices_by_company,
            price_history=price_history or {},
            snapshot_date=snapshot_date,
            stale_threshold_days=stale_threshold_days,
            exchange_override=exch_override,
            cdr_ratio=comp_ratio,
            company_currency=comp_ccy,
            price_source=prices_by_company.get(cid, {}).get("source"),
            fx_service=fx_service,
        )
        used_tiers.append(tier)

        # Tier 4: UNAVAILABLE — skip this holding entirely (not counted as $0)
        if tier == PriceTier.UNAVAILABLE:
            holdings_detail.append({
                "company_id": cid,
                "symbol": h.get("symbol", "?"),
                "company_name": h.get("company_name", h.get("symbol", "?")),
                "quantity": float(qty),
                "current_price": 0.0,
                "current_value": 0.0,
                "cost_basis": float(cost),
                "unrealized_gain_loss": float(-cost),
                "unrealized_gain_loss_pct": -100.0 if cost > 0 else 0.0,
                "price_age_days": None,
                "price_data_quality": "UNAVAILABLE",
            })
            continue

        raw_value = qty * current_price

        _fx_svc = fx_service
        if _fx_svc is None and enable_fx:
            from database import supabase
            from shared.fx_service import FXService
            _fx_svc = FXService(supabase)

        # For CDR holdings: the CDR-adjusted price is already in CAD.
        # Override price_currency to prevent convert_holding_fx from re-converting.
        _orig_price_currency = h.get("price_currency")
        if exch_override == "TOR":
            h["price_currency"] = "CAD"

        try:
            current_value, cost = convert_holding_fx(
                h, raw_value, cost, account_currency,
                _fx_svc, snapshot_date, enable_fx,
            )
        except Exception:
            logger.warning(
                "FX conversion failed for %s on %s; using unconverted value",
                cid, snapshot_date,
            )
            current_value = raw_value

        # Restore original price_currency
        if exch_override == "TOR" and _orig_price_currency is not None:
            h["price_currency"] = _orig_price_currency

        total_market_value += current_value
        total_cost += cost

        # Price age for quality flag — context-aware staleness
        price_info = prices_by_company.get(cid, {})
        price_date = price_info.get("price_date")
        if price_date is None and price_history:
            ph_entries = price_history.get(cid, [])
            if ph_entries:
                last_entry = max(ph_entries, key=lambda x: x[0] if isinstance(x, (list, tuple)) else x.get("price_date", ""))
                if isinstance(last_entry, (list, tuple)):
                    price_date = last_entry[0]
        price_age_days = (snapshot_date - price_date).days if isinstance(price_date, date) else None

        # Quality flag: context-aware staleness
        # - COST_BASIS and UNAVAILABLE are always their respective flags
        # - FORWARD_FILL: OK if gap <= stale_threshold (normal for historical data),
        #   STALE_PRICE if gap is too large (price data is genuinely outdated)
        # - CURRENT: OK normally, STALE_PRICE if today's price is used for a historical
        #   snapshot (indicates the system couldn't find a proper as-of-date price)
        if tier == PriceTier.COST_BASIS:
            pos_quality = "COST_FALLBACK"
        elif tier == PriceTier.UNAVAILABLE:
            pos_quality = "INCOMPLETE"
        elif tier == PriceTier.FORWARD_FILL:
            if price_age_days is not None and price_age_days > stale_threshold_days:
                pos_quality = "STALE_PRICE"
            else:
                pos_quality = "OK"
        else:
            # CURRENT tier
            pos_quality = TIER_QUALITY_MAP.get(tier, "OK")
            if pos_quality == "OK" and price_age_days is not None and price_age_days > stale_threshold_days:
                pos_quality = "STALE_PRICE"

        holdings_detail.append({
            "company_id": cid,
            "symbol": h.get("symbol", "?"),
            "company_name": h.get("company_name", h.get("symbol", "?")),
            "quantity": float(qty),
            "current_price": float(current_price),
            "current_value": float(current_value),
            "cost_basis": float(cost),
            "unrealized_gain_loss": float(current_value - cost),
            "unrealized_gain_loss_pct":
                float((current_value - cost) / cost * 100) if cost > 0 else 0.0,
            "price_age_days": price_age_days,
            "price_data_quality": pos_quality,
        })

    total_value = total_market_value + cash_balance

    # Post-computation validation warnings
    validation_warnings = _validate_snapshot(
        total_value=total_value,
        holdings_market_value=total_market_value,
        cash_balance=cash_balance,
        cost_basis=total_cost,
        holdings_count=non_zero_holdings_count,
        used_tiers=used_tiers,
    )

    # Determine quality flag
    has_unavailable = PriceTier.UNAVAILABLE in used_tiers
    has_warnings = len(validation_warnings) > 0

    if has_unavailable:
        data_quality = "INCOMPLETE"
    elif has_warnings:
        data_quality = "WARNING"
    else:
        any_stale = any(h.get("price_data_quality") == "STALE_PRICE" for h in holdings_detail)
        any_fallback = any(h.get("price_data_quality") == "COST_FALLBACK" for h in holdings_detail)
        if any_stale:
            data_quality = "STALE_PRICE"
        elif any_fallback:
            data_quality = "COST_FALLBACK"
        else:
            data_quality = "OK"

    rounded_total = round(float(total_value), 2)
    rederived = round(float(total_market_value), 2) + round(float(cash_balance), 2)
    if abs(rounded_total - rederived) > 0.02:
        raise AssertionError(
            f"Invariant violation: total_value={rounded_total} != "
            f"holdings_market_value={round(float(total_market_value), 2)} + "
            f"cash_balance={round(float(cash_balance), 2)} = {rederived}"
        )

    return {
        "account_id": account_id,
        "snapshot_date": snapshot_date.isoformat(),
        "total_value": round(float(total_value), 2),
        "holdings_market_value": round(float(total_market_value), 2),
        "cost_basis": round(float(total_cost), 2),
        "cash_balance": round(float(cash_balance), 2),
        "net_deposits": round(float(net_deposits), 2),
        "holdings_json": holdings_detail if holdings_detail else None,
        "data_quality_flag": data_quality,
        "validation_warnings": validation_warnings,
        "job_id": job_id,
        "computed_at": now_utc().isoformat(),
    }


def check_snapshot_spike(
    previous: dict[str, Any],
    current: dict[str, Any],
    threshold: float = 0.20,
) -> dict[str, Any] | None:
    """Compare consecutive snapshots and detect suspicious value spikes.

    A spike is detected when total_value changes by more than `threshold`
    (fractional) AND net_deposits did not change proportionally — i.e., the
    jump is NOT explained by a deposit or withdrawal.

    Returns a dict with spike metadata if detected, None otherwise.
    """
    prev_total = float(previous.get("total_value", 0))
    curr_total = float(current.get("total_value", 0))
    prev_nd = float(previous.get("net_deposits", 0))
    curr_nd = float(current.get("net_deposits", 0))

    if prev_total <= 0:
        return None

    change = curr_total - prev_total
    change_pct = abs(change) / prev_total

    if change_pct <= threshold:
        return None

    nd_change = abs(curr_nd - prev_nd)
    if nd_change > 0.01:
        return None

    return {
        "previous_date": previous.get("snapshot_date"),
        "current_date": current.get("snapshot_date"),
        "previous_total": round(prev_total, 2),
        "current_total": round(curr_total, 2),
        "change": round(change, 2),
        "change_pct": round(change_pct * 100, 2),
        "message": (
            f"Value spike detected: ${prev_total:,.2f} to ${curr_total:,.2f} "
            f"({change_pct:.1%} change) with no deposit/withdrawal activity"
        ),
    }
