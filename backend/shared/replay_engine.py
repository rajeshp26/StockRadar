"""Event-replay engine: rebuild portfolio state from immutable event log."""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from infrastructure.repositories.event_store import EventStore
from shared.snapshot_builder import PriceTier, _resolve_holding_price, TIER_QUALITY_MAP


@dataclass
class HoldingState:
    company_id: int
    symbol: str
    quantity: Decimal
    total_cost: Decimal
    average_cost: Decimal
    realized_gain_loss: Decimal = Decimal("0")


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

    def __init__(self, event_store: EventStore):
        self.event_store = event_store

    def _handle_initial_holding_set(self, state: AccountState, event: dict) -> None:
        """Set initial holdings from an initial_holding_set event (used for accounts without transaction history)."""
        data = event.get("data", {}) or {}
        state.cash_balance = _decimal(data.get("cash_balance"))
        state.net_deposits = _decimal(data.get("net_deposits"))
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
                )

    def _handle_transaction_imported(self, state: AccountState, event: dict) -> None:
        data = event.get("data", {})
        activity_type = data.get("activity_type", "")
        net_cash = _decimal(data.get("net_cash_amount"))
        symbol = data.get("symbol")
        company_id = data.get("company_id")
        quantity = _decimal(data.get("quantity"))
        unit_price = _decimal(data.get("unit_price"))

        # Cash
        if activity_type in self.CASH_ACTIVITY_TYPES:
            state.cash_balance += net_cash

        # Deposits
        if activity_type in self.DEPOSIT_ACTIVITY_TYPES and net_cash > 0:
            state.net_deposits += net_cash

        # Holdings
        if company_id and activity_type == "Trade" and quantity != 0:
            cid = int(company_id)
            holding = state.holdings.get(cid)

            if quantity > 0:  # Buy
                total_cost = quantity * unit_price
                if holding:
                    new_qty = holding.quantity + quantity
                    new_cost = holding.total_cost + total_cost
                    holding.quantity = new_qty
                    holding.total_cost = new_cost
                    holding.average_cost = new_cost / new_qty if new_qty else Decimal("0")
                else:
                    state.holdings[cid] = HoldingState(
                        company_id=cid,
                        symbol=symbol or "?",
                        quantity=quantity,
                        total_cost=total_cost,
                        average_cost=unit_price if quantity else Decimal("0"),
                    )

            elif quantity < 0:  # Sell
                sell_qty = abs(quantity)
                if holding:
                    sold = min(sell_qty, holding.quantity)
                    sale_proceeds = sold * unit_price
                    cost_of_sold = sold * holding.average_cost if holding.average_cost else Decimal("0")
                    holding.realized_gain_loss += sale_proceeds - cost_of_sold
                    holding.total_cost -= cost_of_sold
                    holding.quantity -= sold
                    if holding.quantity <= 0:
                        del state.holdings[cid]

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
    ) -> dict:
        """Build a snapshot dict from replay state (compatible with build_snapshot_row output).

        Args:
            exchange_overrides: Optional dict mapping company_id → exchange_override
                (e.g. {42: "TOR"} for CDR holdings). Used to apply CDR ratio in pricing.
        """
        state = self.replay_to_date(account_id, target_date)

        holdings_list = []
        total_market_value = Decimal("0.00")
        total_cost = Decimal("0.00")
        used_tiers: List[PriceTier] = []

        for cid, holding in state.holdings.items():
            qty = holding.quantity
            total_cost += holding.total_cost

            exch_override = exchange_overrides.get(cid) if exchange_overrides else None
            price, tier, resolved_price_date = _resolve_holding_price(
                company_id=cid,
                symbol=holding.symbol,
                avg_cost=holding.average_cost if holding.average_cost > 0 else None,
                latest_prices=prices_by_company,
                price_history=price_history or {},
                snapshot_date=target_date,
                exchange_override=exch_override,
            )
            used_tiers.append(tier)

            if tier == PriceTier.UNAVAILABLE:
                current_value = Decimal("0")
                current_price = Decimal("0")
                pos_quality = "UNAVAILABLE"
            else:
                current_price = price
                current_value = qty * current_price
                total_market_value += current_value
                # Context-aware quality: FORWARD_FILL with small gap is OK
                if tier == PriceTier.COST_BASIS:
                    pos_quality = "COST_FALLBACK"
                elif tier == PriceTier.FORWARD_FILL:
                    price_age = (target_date - resolved_price_date).days if resolved_price_date else None
                    pos_quality = "STALE_PRICE" if (price_age is not None and price_age > 30) else "OK"
                else:
                    pos_quality = TIER_QUALITY_MAP.get(tier, "OK")

            holdings_list.append({
                "company_id": cid,
                "symbol": holding.symbol,
                "quantity": float(qty),
                "current_price": float(current_price),
                "current_value": float(current_value),
                "cost_basis": float(holding.total_cost),
                "unrealized_gain_loss": float(current_value - holding.total_cost),
                "unrealized_gain_loss_pct": float(
                    (current_value - holding.total_cost) / holding.total_cost * 100
                ) if holding.total_cost > 0 else 0.0,
                "price_age_days": None,
                "price_data_quality": pos_quality,
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
    ) -> ComparisonResult:
        """Compare replay result with a stored portfolio_snapshot row."""
        replay = self.build_snapshot_from_replay(
            account_id=account_id,
            target_date=snapshot_date,
            prices_by_company=prices_by_company,
            price_history=price_history,
            account_currency=account_currency,
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
