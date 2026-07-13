from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict
import bisect
import logging

from shared.time_utils import now_utc

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


def _resolve_holding_price(
    company_id: int,
    symbol: str,
    avg_cost: Optional[Decimal],
    latest_prices: Dict[int, Dict],
    price_history: Dict[int, List[tuple]],
    snapshot_date: date,
    stale_threshold_days: int = 30,
    exchange_override: Optional[str] = None,
) -> Tuple[Optional[Decimal], PriceTier, Optional[date]]:
    """4-tier price cascade.
    
    Tier 1 (CURRENT) only used if price_date is recent enough (<= stale_threshold_days old).
    Otherwise falls through to Tier 2 (forward-fill) for accurate historical pricing.
    
    When exchange_override="TOR": market-sourced prices (Tiers 1 & 2) come from US exchanges
    and must be divided by CDR_RATIO (10) to get the correct CDR price.
    Tier 3 (cost_basis) is NOT adjusted — CDR purchase prices are already at actual CDR cost.
    
    Returns (price, tier, price_date). Returns (None, UNAVAILABLE, None) if no price is usable.
    """
    is_cdr = exchange_override == "TOR"
    # Tier 1: current market price — only for recent snapshots
    info = latest_prices.get(company_id, {})
    if info.get("price") is not None:
        pd = info.get("price_date")
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
                        price = price / CDR_RATIO
                    return price, PriceTier.CURRENT, pd
            else:
                # current price is from before or same as snapshot — safe to use
                price = Decimal(str(info["price"]))
                if is_cdr:
                    price = price / CDR_RATIO
                return price, PriceTier.CURRENT, pd
        else:
            # no price_date — use current price as best-effort
            price = Decimal(str(info["price"]))
            if is_cdr:
                price = price / CDR_RATIO
            return price, PriceTier.CURRENT, None

    # Tier 2: forward-fill from price_history (most recent price <= snapshot_date)
    result = resolve_price_forward_filled(company_id, snapshot_date, price_history)
    if result is not None and result.get("price") is not None:
        price = Decimal(str(result["price"]))
        if is_cdr:
            price = price / CDR_RATIO
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
    used_tiers: List[PriceTier],
) -> List[str]:
    """Post-computation validation. Returns list of warning strings.
    
    W1: Zero market value with non-zero holdings
    W2: Negative total with positive holdings value
    W3: Cash too negative relative to cost basis (possible missing deposits)
    """
    warnings: List[str] = []

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


def _classify_lot_action(txn: dict) -> Optional[str]:
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
    price_map: Dict[int, List[tuple]],
) -> Optional[Dict]:
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
    holdings_state: List[Dict],
    cash_balance: Decimal,
    net_deposits: Decimal,
    prices_by_company: Dict[int, Dict],
    job_id: str,
    stale_threshold_days: int = 30,
    account_currency: str = "CAD",
    fx_service: Optional[Any] = None,
    price_history: Optional[Dict[int, List[tuple]]] = None,
) -> Dict[str, Any]:
    from config import settings
    enable_fx = getattr(settings, "ENABLE_FX_CONVERSION", False)
    total_market_value = Decimal("0.00")
    total_cost = Decimal("0.00")
    holdings_detail = []
    used_tiers: List[PriceTier] = []
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
        exch_override = h.get("exchange_override")
        current_price, tier, resolved_price_date = _resolve_holding_price(
            company_id=cid,
            symbol=h.get("symbol", ""),
            avg_cost=avg_cost if avg_cost > 0 else None,
            latest_prices=prices_by_company,
            price_history=price_history or {},
            snapshot_date=snapshot_date,
            stale_threshold_days=stale_threshold_days,
            exchange_override=exch_override,
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

        needs_fx = (
            enable_fx
            and price_currency.upper() != account_currency.upper()
        )
        if needs_fx:
            _fx_svc = fx_service
            if _fx_svc is None:
                from database import supabase
                from shared.fx_service import FXService
                _fx_svc = FXService(supabase)
            try:
                conv_val, _ = _fx_svc.convert_or_warn(
                    raw_value, price_currency, account_currency,
                    as_of=snapshot_date, holding_id=str(cid),
                )
                if cost > 0:
                    conv_cost, _ = _fx_svc.convert_or_warn(
                        cost, price_currency, account_currency,
                        as_of=snapshot_date, holding_id=str(cid),
                    )
                    cost = conv_cost
                current_value = conv_val
            except Exception:
                logger.warning(
                    "FX conversion failed for %s on %s; using unconverted value",
                    cid, snapshot_date,
                )
                current_value = raw_value
        else:
            current_value = raw_value

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
    previous: Dict[str, Any],
    current: Dict[str, Any],
    threshold: float = 0.20,
) -> Optional[Dict[str, Any]]:
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
