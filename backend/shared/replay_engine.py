"""Event-replay engine: rebuild portfolio state from immutable event log."""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from infrastructure.repositories.event_store import EventStore
from shared.snapshot_builder import PriceTier, _resolve_holding_price, TIER_QUALITY_MAP, convert_holding_fx

logger = logging.getLogger(__name__)


@dataclass
class HoldingState:
    company_id: int
    symbol: str
    quantity: Decimal
    total_cost: Decimal
    average_cost: Decimal
    realized_gain_loss: Decimal = Decimal("0")
    trade_date: Optional[date] = None
    lots: List[Dict] = field(default_factory=list)


@dataclass
class AccountState:
    account_id: int
    cash_balance: Decimal = Decimal("0.00")
    net_deposits: Decimal = Decimal("0.00")
    holdings: Dict[int, HoldingState] = field(default_factory=dict)


@dataclass
class ComparisonResult:
    match: bool
    delta_total_value: Decimal
    delta_cash: Decimal
    delta_cost: Decimal
    replay: dict
    stored: dict
    differences: List[str]


def _parse_account_id(aggregate_id: str) -> Optional[int]:
    if aggregate_id and aggregate_id.startswith("account_"):
        try:
            return int(aggregate_id.split("_")[1])
        except (IndexError, ValueError):
            return None
    return None


def _decimal(val: Any) -> Decimal:
    return Decimal(str(val)) if val is not None else Decimal("0")


class ReplayEngine:
    """Rebuild portfolio state from the immutable event log up to any date."""

    CASH_ACTIVITY_TYPES = {
        "Trade", "Deposit", "Withdrawal", "Dividend", "MoneyMovement",
        "Interest", "Fee", "WithholdingTax", "ReorganizationDividend",
        "BonusPayment", "FxExchange", "ReturnOfCapital", "Tax",
    }

    DEPOSIT_ACTIVITY_TYPES = {"MoneyMovement", "BonusPayment"}

    COST_REDUCTION_ACTIVITY_TYPES = {"ReturnOfCapital"}

    HOLDING_ACTIVITY_TYPES = {"Trade", "InternalSecurityTransfer"}

    def __init__(self, event_store: EventStore):
        self.event_store = event_store

    def _handle_initial_holding_set(self, state: AccountState, event: dict) -> None:
        """Set initial holdings from an initial_holding_set event (used for accounts without transaction history)."""
        data = event.get("data", {}) or {}
        state.cash_balance = _decimal(data.get("cash_balance"))
        state.net_deposits = _decimal(data.get("net_deposits"))
        event_date = self._get_event_date(event)
        holdings = data.get("holdings", []) or []
        for h in holdings:
            cid = int(h["company_id"])
            qty = _decimal(h.get("quantity"))
            avg_cost = _decimal(h.get("average_cost"))
            total_cost = _decimal(h.get("total_cost"))
            if qty > 0 and cid:
                state.holdings[cid] = HoldingState(
                    company_id=cid,
                    symbol=h.get("symbol", "?"),
                    quantity=qty,
                    total_cost=total_cost if total_cost > 0 else qty * avg_cost,
                    average_cost=avg_cost,
                    trade_date=event_date,
                )

    def _handle_transaction_imported(self, state: AccountState, event: dict) -> None:
        data = event.get("data", {})
        activity_type = data.get("activity_type", "")
        net_cash = _decimal(data.get("net_cash_amount"))
        symbol = data.get("symbol")
        company_id = data.get("company_id")
        quantity = _decimal(data.get("quantity"))
        unit_price = _decimal(data.get("unit_price"))
        txn_date = self._get_event_date(event)

        # Cash
        if activity_type in self.CASH_ACTIVITY_TYPES:
            state.cash_balance += net_cash

        # Deposits
        if activity_type in self.DEPOSIT_ACTIVITY_TYPES and net_cash > 0:
            state.net_deposits += net_cash

        # Cost basis reduction for ReturnOfCapital
        if activity_type in self.COST_REDUCTION_ACTIVITY_TYPES and company_id:
            self._handle_return_of_capital(state, event)

        # Holdings
        if company_id and activity_type in self.HOLDING_ACTIVITY_TYPES and quantity != 0:
            cid = int(company_id)
            holding = state.holdings.get(cid)

            if quantity > 0:  # Buy or inbound IST
                if activity_type == "InternalSecurityTransfer":
                    # IST: derive cost from net_cash_amount (value of securities transferred)
                    nca = abs(_decimal(data.get("net_cash_amount")))
                    cost_per_share = nca / quantity if quantity else unit_price
                else:
                    commission = _decimal(data.get("commission"))
                    cost_per_share = unit_price + (commission / quantity) if quantity else unit_price
                total_cost = quantity * cost_per_share
                lot = {"quantity": quantity, "cost_per_share": cost_per_share, "date": txn_date}
                if holding:
                    new_qty = holding.quantity + quantity
                    new_cost = holding.total_cost + total_cost
                    holding.quantity = new_qty
                    holding.total_cost = new_cost
                    holding.average_cost = new_cost / new_qty if new_qty else Decimal("0")
                    holding.lots.append(lot)
                else:
                    state.holdings[cid] = HoldingState(
                        company_id=cid,
                        symbol=symbol or "?",
                        quantity=quantity,
                        total_cost=total_cost,
                        average_cost=cost_per_share if quantity else Decimal("0"),
                        trade_date=txn_date,
                        lots=[lot],
                    )

            elif quantity < 0:  # Sell or outbound IST
                sell_qty = abs(quantity)
                if holding:
                    sold = min(sell_qty, holding.quantity)
                    if sell_qty > holding.quantity:
                        logger.warning(
                            "Sell truncation: account=%s company=%s sell_qty=%s > holding_qty=%s",
                            state.account_id, cid, sell_qty, holding.quantity,
                        )
                    sale_proceeds = sold * unit_price
                    # FIFO cost basis: remove lots from front, accumulate cost
                    cost_of_sold = Decimal("0")
                    remaining_to_remove = sold
                    while remaining_to_remove > 0 and holding.lots:
                        front = holding.lots[0]
                        lot_qty = front["quantity"]
                        lot_cost = front["cost_per_share"]
                        if lot_qty <= remaining_to_remove:
                            cost_of_sold += lot_qty * lot_cost
                            remaining_to_remove -= lot_qty
                            holding.lots.pop(0)
                        else:
                            cost_of_sold += remaining_to_remove * lot_cost
                            front["quantity"] -= remaining_to_remove
                            remaining_to_remove = Decimal("0")
                    # Fallback: if lots didn't cover the full sell, use average_cost for remainder
                    if sold > 0 and remaining_to_remove > 0 and holding.average_cost:
                        cost_of_sold += remaining_to_remove * holding.average_cost
                    elif cost_of_sold == 0 and sold > 0 and holding.average_cost:
                        cost_of_sold = sold * holding.average_cost
                    holding.realized_gain_loss += sale_proceeds - cost_of_sold
                    holding.total_cost -= cost_of_sold
                    holding.quantity -= sold
                    # Recalculate average_cost from remaining lots
                    if holding.lots:
                        total_qty = sum(l["quantity"] for l in holding.lots)
                        total_lot_cost = sum(l["quantity"] * l["cost_per_share"] for l in holding.lots)
                        holding.average_cost = total_lot_cost / total_qty if total_qty else Decimal("0")
                    if holding.quantity <= 0:
                        del state.holdings[cid]

    def _handle_split(self, state: AccountState, event: dict) -> None:
        """Adjust holdings for a stock split event."""
        data = event.get("data", {}) or {}
        company_id = data.get("company_id")
        split_factor = _decimal(data.get("split_factor"))
        if not company_id or split_factor <= 0 or split_factor == 1:
            return
        holding = state.holdings.get(int(company_id))
        if not holding:
            return
        holding.quantity *= split_factor
        holding.average_cost /= split_factor
        for lot in holding.lots:
            lot["quantity"] *= split_factor
            lot["cost_per_share"] /= split_factor

    def _handle_return_of_capital(self, state: AccountState, event: dict) -> None:
        """Reduce cost basis when ReturnOfCapital is received."""
        data = event.get("data", {}) or {}
        company_id = data.get("company_id")
        net_cash = _decimal(data.get("net_cash_amount"))
        if not company_id or net_cash <= 0:
            return
        holding = state.holdings.get(int(company_id))
        if not holding:
            return
        # Reduce cost basis by ROC amount (cannot go below zero)
        if holding.total_cost > 0:
            reduction = min(net_cash, holding.total_cost)
            holding.total_cost -= reduction
            # Reduce each lot proportionally
            if holding.lots:
                lot_total_cost = sum(l["quantity"] * l["cost_per_share"] for l in holding.lots)
                if lot_total_cost > 0:
                    ratio = reduction / lot_total_cost
                    for lot in holding.lots:
                        lot["cost_per_share"] *= (1 - ratio)
                        if lot["cost_per_share"] < 0:
                            lot["cost_per_share"] = Decimal("0")
            # Recalculate average_cost
            if holding.quantity > 0:
                holding.average_cost = holding.total_cost / holding.quantity

    def _get_event_date(self, event: dict) -> Optional[date]:
        """Extract the relevant date from an event — prefers data.effective_date / transaction_date over created_at."""
        data = event.get("data", {}) or {}
        eff_date = data.get("effective_date")
        if eff_date:
            if isinstance(eff_date, date):
                return eff_date
            if isinstance(eff_date, str):
                try:
                    return date.fromisoformat(eff_date)
                except (ValueError, TypeError):
                    pass
        txn_date = data.get("transaction_date")
        if txn_date:
            if isinstance(txn_date, date):
                return txn_date
            if isinstance(txn_date, str):
                try:
                    return date.fromisoformat(txn_date)
                except (ValueError, TypeError):
                    pass
        created_str = event.get("created_at", "")
        if created_str:
            try:
                return datetime.fromisoformat(created_str.replace("Z", "+00:00")).date()
            except (ValueError, TypeError):
                pass
        return None

    def replay_to_date(
        self,
        account_id: int,
        target_date: date,
    ) -> AccountState:
        """Rebuild account state by replaying all events up to target_date."""
        events = self.event_store.get_all_events(
            aggregate_type="account",
        )
        account_events = []
        for ev in events:
            ev_account_id = _parse_account_id(ev.get("aggregate_id", ""))
            if ev_account_id != account_id:
                continue
            ev_date = self._get_event_date(ev)
            if ev_date is not None and ev_date <= target_date:
                account_events.append(ev)

        account_events.sort(key=lambda e: self._get_event_date(e) or date.min)

        state = AccountState(account_id=account_id)

        for ev in account_events:
            event_type = ev.get("event_type", "")
            handler_name = f"_handle_{event_type}"
            handler = getattr(self, handler_name, None)
            if handler:
                handler(state, ev)
            else:
                pass  # Unknown event types are skipped

        return state

    def build_snapshot_from_replay(
        self,
        account_id: int,
        target_date: date,
        prices_by_company: Dict[int, Dict],
        price_history: Optional[Dict[int, List[tuple]]] = None,
        account_currency: str = "CAD",
        exchange_overrides: Optional[Dict[int, Optional[str]]] = None,
        company_currencies: Optional[Dict[int, str]] = None,
        companies_map: Optional[Dict[int, Dict]] = None,
    ) -> dict:
        """Build a snapshot dict from replay state (compatible with build_snapshot_row output).

        Args:
            exchange_overrides: Optional dict mapping company_id → exchange_override
                (e.g. {42: "TOR"} for CDR holdings). Used to apply CDR ratio in pricing.
            company_currencies: Optional dict mapping company_id → price currency
                (e.g. {478: "USD", 1027: "CAD"}). Used for FX conversion.
            companies_map: Optional dict mapping company_id → companies row dict
                (with cdr_ratio field). Used for per-company CDR ratio lookup.
        """
        from config import settings
        from shared.fx_service import FXService
        from database import supabase as _sb
        from shared.snapshot_builder import get_cdr_ratio_for_company

        enable_fx = getattr(settings, "ENABLE_FX_CONVERSION", False)
        fx_svc = FXService(_sb) if enable_fx else None

        state = self.replay_to_date(account_id, target_date)

        holdings_list = []
        total_market_value = Decimal("0.00")
        total_cost = Decimal("0.00")
        used_tiers: List[PriceTier] = []

        for cid, holding in state.holdings.items():
            qty = holding.quantity
            cost = holding.total_cost

            exch_override = exchange_overrides.get(cid) if exchange_overrides else None
            comp_ccy = (company_currencies.get(cid) if company_currencies else None) or "USD"
            comp_ratio = get_cdr_ratio_for_company(cid, companies_map) if companies_map else None

            price, tier, resolved_price_date = _resolve_holding_price(
                company_id=cid,
                symbol=holding.symbol,
                avg_cost=holding.average_cost if holding.average_cost > 0 else None,
                latest_prices=prices_by_company,
                price_history=price_history or {},
                snapshot_date=target_date,
                exchange_override=exch_override,
                cdr_ratio=comp_ratio,
                company_currency=comp_ccy,
                price_source=prices_by_company.get(cid, {}).get("source"),
                fx_service=fx_svc,
            )
            used_tiers.append(tier)

            if tier == PriceTier.UNAVAILABLE:
                current_value = Decimal("0")
                current_price = Decimal("0")
                pos_quality = "UNAVAILABLE"
            else:
                current_price = price
                raw_value = qty * current_price

                price_currency = "USD"
                if company_currencies and cid in company_currencies:
                    price_currency = company_currencies[cid]

                holding_dict = {
                    "company_id": cid,
                    "price_currency": price_currency,
                    "lots": [
                        {
                            "quantity": lot["quantity"],
                            "cost_per_share": lot["cost_per_share"],
                            "date": lot.get("date"),
                        }
                        for lot in holding.lots
                    ] if holding.lots else [],
                    "trade_date": holding.trade_date,
                }
                # For CDR holdings: CDR-adjusted price is already in CAD.
                # Override price_currency to prevent convert_holding_fx from re-converting.
                if exch_override == "TOR":
                    holding_dict["price_currency"] = "CAD"

                try:
                    current_value, cost = convert_holding_fx(
                        holding_dict, raw_value, cost, account_currency,
                        fx_svc, target_date, enable_fx,
                    )
                except Exception:
                    logger.warning(
                        "FX conversion failed for %s on %s; using unconverted value",
                        cid, target_date,
                    )
                    current_value = raw_value

                total_market_value += current_value
                total_cost += cost
                if tier == PriceTier.COST_BASIS:
                    pos_quality = "COST_FALLBACK"
                elif tier == PriceTier.FORWARD_FILL:
                    price_age = (target_date - resolved_price_date).days if resolved_price_date else None
                    pos_quality = "STALE_PRICE" if (price_age is not None and price_age > 30) else "OK"
                else:
                    pos_quality = TIER_QUALITY_MAP.get(tier, "OK")

            lots_out = [
                {
                    "quantity": float(lot["quantity"]),
                    "cost_per_share": float(lot["cost_per_share"]),
                    "date": lot["date"].isoformat() if lot.get("date") else None,
                }
                for lot in holding.lots
            ] if holding.lots else []

            holdings_list.append({
                "company_id": cid,
                "symbol": holding.symbol,
                "quantity": float(qty),
                "current_price": float(current_price),
                "current_value": float(current_value),
                "cost_basis": float(cost),
                "unrealized_gain_loss": float(current_value - cost),
                "unrealized_gain_loss_pct": float(
                    (current_value - cost) / cost * 100
                ) if cost > 0 else 0.0,
                "price_age_days": None,
                "price_data_quality": pos_quality,
                "trade_date": holding.trade_date.isoformat() if holding.trade_date else None,
                "lots": lots_out,
            })

        total_value = total_market_value + state.cash_balance

        # Quality flag
        has_unavailable = PriceTier.UNAVAILABLE in used_tiers
        if has_unavailable:
            data_quality = "INCOMPLETE"
        elif total_value < 0 and total_market_value > 0:
            data_quality = "WARNING"
        else:
            any_stale = any(h["price_data_quality"] == "STALE_PRICE" for h in holdings_list)
            any_fallback = any(h["price_data_quality"] == "COST_FALLBACK" for h in holdings_list)
            if any_stale:
                data_quality = "STALE_PRICE"
            elif any_fallback:
                data_quality = "COST_FALLBACK"
            else:
                data_quality = "OK"

        return {
            "account_id": account_id,
            "snapshot_date": target_date.isoformat(),
            "total_value": round(float(total_value), 2),
            "holdings_market_value": round(float(total_market_value), 2),
            "cost_basis": round(float(total_cost), 2),
            "cash_balance": round(float(state.cash_balance), 2),
            "net_deposits": round(float(state.net_deposits), 2),
            "holdings_json": holdings_list if holdings_list else None,
            "data_quality_flag": data_quality,
        }

    def compare_with_snapshot(
        self,
        account_id: int,
        snapshot_date: date,
        stored_snapshot: dict,
        prices_by_company: Dict[int, Dict],
        price_history: Optional[Dict[int, List[tuple]]] = None,
        account_currency: str = "CAD",
        company_currencies: Optional[Dict[int, str]] = None,
        companies_map: Optional[Dict[int, Dict]] = None,
    ) -> ComparisonResult:
        """Compare replay result with a stored portfolio_snapshot row."""
        replay = self.build_snapshot_from_replay(
            account_id=account_id,
            target_date=snapshot_date,
            prices_by_company=prices_by_company,
            price_history=price_history,
            account_currency=account_currency,
            company_currencies=company_currencies,
            companies_map=companies_map,
        )

        differences: List[str] = []

        def delta(key: str) -> Decimal:
            r = _decimal(replay.get(key, 0))
            s = _decimal(stored_snapshot.get(key, 0))
            return r - s

        d_total = delta("total_value")
        d_cash = delta("cash_balance")
        d_cost = delta("cost_basis")

        if abs(d_total) > Decimal("0.01"):
            differences.append(
                f"total_value: replay={replay['total_value']} "
                f"stored={stored_snapshot.get('total_value')} delta={float(d_total):.2f}"
            )
        if abs(d_cash) > Decimal("0.01"):
            differences.append(
                f"cash_balance: replay={replay['cash_balance']} "
                f"stored={stored_snapshot.get('cash_balance')} delta={float(d_cash):.2f}"
            )
        if abs(d_cost) > Decimal("0.01"):
            differences.append(
                f"cost_basis: replay={replay['cost_basis']} "
                f"stored={stored_snapshot.get('cost_basis')} delta={float(d_cost):.2f}"
            )

        return ComparisonResult(
            match=len(differences) == 0,
            delta_total_value=d_total,
            delta_cash=d_cash,
            delta_cost=d_cost,
            replay=replay,
            stored=stored_snapshot,
            differences=differences,
        )
