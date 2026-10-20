"""Event-replay engine: rebuild portfolio state from immutable event log."""

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, ClassVar

from infrastructure.repositories.event_store import EventStore
from shared import debug_trace
from shared.cdr_utils import EXCHANGE_OVERRIDE_TOR, classify_lot_legs
from shared.fx_service import UNSTAMPED_CURRENCY, convert_cash_map, normalize_currency
from shared.snapshot_builder import (
    TIER_QUALITY_MAP,
    PriceTier,
    _resolve_holding_price,
    convert_holding_fx,
)
from shared.split_utils import extract_event_date
from shared.transfer_reconciliation import pair_key, reconcile_transfers

logger = logging.getLogger(__name__)


@dataclass
class HoldingState:
    company_id: int
    symbol: str
    quantity: Decimal
    total_cost: Decimal
    average_cost: Decimal
    realized_gain_loss: Decimal = Decimal("0")
    trade_date: date | None = None
    lots: list[dict] = field(default_factory=list)


@dataclass
class AccountState:
    account_id: int
    cash_balance: Decimal = Decimal("0.00")
    net_deposits: Decimal = Decimal("0.00")
    holdings: dict[int, HoldingState] = field(default_factory=dict)
    checkpoint_date: date | None = None
    cash_by_currency: dict[str, Decimal] = field(default_factory=dict)
    net_deposits_by_currency: dict[str, Decimal] = field(default_factory=dict)
    #: None = not yet computed; empty = computed, no pairs. replay_to_date
    #: precomputes it; manual dispatch fills it lazily on first IST leg.
    ist_paired_keys: frozenset[tuple[Any, ...]] | None = None
    relocated_basis: dict[tuple[Any, ...], list[dict]] = field(default_factory=dict)


@dataclass
class ComparisonResult:
    match: bool
    delta_total_value: Decimal
    delta_cash: Decimal
    delta_cost: Decimal
    replay: dict
    stored: dict
    differences: list[str]


def _parse_account_id(aggregate_id: str) -> int | None:
    if aggregate_id and aggregate_id.startswith("account_"):
        try:
            return int(aggregate_id.split("_")[1])
        except (IndexError, ValueError):
            return None
    return None


def _decimal(val: Any) -> Decimal:
    return Decimal(str(val)) if val is not None else Decimal("0")


def _bucket(target: dict[str, Decimal], code: str, amount: Decimal) -> None:
    target[code] = target.get(code, Decimal("0.00")) + amount


def _load_cash_from_checkpoint(state: AccountState, data: dict) -> None:
    """Reset cash from a checkpoint, bucketing it as UNSTAMPED.

    A checkpoint stores a single already-currency-aware total, so there is no
    currency to attribute it to. It resets rather than accumulates because the
    checkpoint is a state projection, not a historical fact.
    """
    state.cash_balance = _decimal(data.get("cash_balance"))
    state.net_deposits = _decimal(data.get("net_deposits"))
    state.cash_by_currency = {}
    state.net_deposits_by_currency = {}
    if state.cash_balance != 0:
        state.cash_by_currency[UNSTAMPED_CURRENCY] = state.cash_balance
    if state.net_deposits != 0:
        state.net_deposits_by_currency[UNSTAMPED_CURRENCY] = state.net_deposits


def _cash_view(
    by_currency: dict[str, Decimal], scalar: Decimal
) -> dict[str, Decimal]:
    """Never let a populated scalar fall through an empty currency map.

    Callers and tests construct AccountState directly with only `cash_balance`.
    Treating an absent map as zero cash would silently zero those snapshots, so an
    unmapped scalar is attributed to the account currency rather than discarded.
    """
    if by_currency:
        return by_currency
    return {UNSTAMPED_CURRENCY: scalar} if scalar != 0 else {}


def _cdr_lot_legs(
    holdings: dict[int, HoldingState],
    cdr_lots: dict[int, dict[str, Decimal]] | None,
    derived_cdr_companies: set[int] | None,
) -> list[tuple[int, HoldingState, str | None]]:
    """Expand replayed holdings into per-lot legs where lot evidence exists. BLK-027.

    Replay cannot label its own lots: stored ``transaction_imported`` events carry no
    ``security_name`` or ``exchange_override``, so every event lot looks direct. Taking
    that at face value undervalues every CDR tenfold, which is the mirror image of the
    defect being fixed. Lot provenance therefore comes from ``portfolio_transactions``
    and must be passed in.

    A leg kind of None means "no lot evidence for this company", and leaves the caller
    on its company-keyed path, so omitting ``cdr_lots`` preserves existing behaviour
    exactly.
    """
    legs: list[tuple[int, HoldingState, str | None]] = []
    for cid, holding in holdings.items():
        lots = cdr_lots.get(cid) if cdr_lots else None
        if not lots:
            legs.append((cid, holding, None))
            continue

        leg_defs, notes = classify_lot_legs(
            quantity=holding.quantity,
            total_cost=holding.total_cost,
            lots=lots,
            company_is_cdr=bool(derived_cdr_companies and cid in derived_cdr_companies),
            context=f"company {cid} ({holding.symbol})",
        )
        for note in notes:
            logger.warning("Replay lot split declined: %s", note)

        for kind, leg_qty, leg_cost in leg_defs:
            legs.append(
                (
                    cid,
                    HoldingState(
                        company_id=holding.company_id,
                        symbol=holding.symbol,
                        quantity=leg_qty,
                        total_cost=leg_cost,
                        average_cost=leg_cost / leg_qty if leg_qty else Decimal("0"),
                        realized_gain_loss=holding.realized_gain_loss,
                        trade_date=holding.trade_date,
                        lots=holding.lots,
                    ),
                    kind,
                )
            )
    return legs


def _fifo_cost_and_removed(
    lots: list[dict],
    qty: Decimal,
    fallback_average_cost: Decimal,
) -> tuple[Decimal, list[dict], Decimal]:
    """Remove ``qty`` shares FIFO from ``lots`` in place.

    Mirrors the sell loop exactly: full lots are popped, a partially consumed
    front lot is reduced in place, and any quantity the lots could not cover is
    priced at ``fallback_average_cost``. Returns
    ``(cost_of_sold, removed_fragments, leftover_qty)`` where ``removed_fragments``
    are *copies* of the consumed lot pieces (full or partial) and ``leftover_qty``
    is the uncovered remainder after the fallback is priced in --, so a relocation
    can park the fragments plus a synthetic fallback lot without aliasing the
    live lots.
    """
    cost_of_sold = Decimal("0")
    remaining_to_remove = qty
    removed_fragments: list[dict] = []
    while remaining_to_remove > 0 and lots:
        front = lots[0]
        lot_qty = front["quantity"]
        lot_cost = front["cost_per_share"]
        if lot_qty <= remaining_to_remove:
            cost_of_sold += lot_qty * lot_cost
            remaining_to_remove -= lot_qty
            removed_fragments.append(dict(front))
            lots.pop(0)
        else:
            cost_of_sold += remaining_to_remove * lot_cost
            removed_fragments.append({**front, "quantity": remaining_to_remove})
            front["quantity"] -= remaining_to_remove
            remaining_to_remove = Decimal("0")
    leftover_qty = remaining_to_remove
    if qty > 0 and leftover_qty > 0 and fallback_average_cost:
        cost_of_sold += leftover_qty * fallback_average_cost
    elif cost_of_sold == 0 and qty > 0 and fallback_average_cost:
        cost_of_sold = qty * fallback_average_cost
    return cost_of_sold, removed_fragments, leftover_qty


class ReplayEngine:
    """Rebuild portfolio state from the immutable event log up to any date."""

    CASH_ACTIVITY_TYPES: ClassVar[set[str]] = {
        "Trade", "Deposit", "Withdrawal", "Dividend", "MoneyMovement",
        "Interest", "Fee", "WithholdingTax", "ReorganizationDividend",
        "BonusPayment", "FxExchange", "ReturnOfCapital", "Tax",
    }

    DEPOSIT_ACTIVITY_TYPES: ClassVar[set[str]] = {"MoneyMovement", "BonusPayment"}

    COST_REDUCTION_ACTIVITY_TYPES: ClassVar[set[str]] = {"ReturnOfCapital"}

    HOLDING_ACTIVITY_TYPES: ClassVar[set[str]] = {"Trade", "InternalSecurityTransfer"}

    def __init__(self, event_store: EventStore):
        self.event_store = event_store

    def _handle_initial_holding_set(self, state: AccountState, event: dict) -> None:
        """Set initial holdings from an initial_holding_set event (used for accounts without transaction history)."""
        data = event.get("data", {}) or {}
        _load_cash_from_checkpoint(state, data)
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

    def _handle_position_state_checkpoint(self, state: AccountState, event: dict) -> None:
        """Replace account state with a projection captured at this event's date.

        A checkpoint is a capture of already-computed state, not a historical fact: its
        quantities already include every trade and corporate action that preceded it. It
        therefore RESETS the account rather than adding to it, so a position fully sold
        before capture is dropped instead of lingering from replayed history.
        """
        data = event.get("data", {}) or {}
        event_date = self._get_event_date(event)

        state.holdings.clear()
        _load_cash_from_checkpoint(state, data)
        state.checkpoint_date = event_date

        for h in data.get("holdings", []) or []:
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
        currency = normalize_currency(data.get("currency"))

        # Cash
        if activity_type in self.CASH_ACTIVITY_TYPES:
            state.cash_balance += net_cash
            _bucket(state.cash_by_currency, currency, net_cash)

        # Deposits — signed net movement: contributions positive, withdrawals
        # negative. Snapshot net_deposits must mirror
        # PortfolioRepository.get_net_deposits and the live performance path
        # (_cached_net_deposits), which both sum net_cash_amount with no sign
        # guard. A positive-only guard silently drops every outflow, inflating
        # net_deposits; TWR/MWR read the period-over-period net_deposits change
        # as the period's cash flow, so a dropped withdrawal removes a negative
        # term and overstates every return.
        if activity_type in self.DEPOSIT_ACTIVITY_TYPES:
            state.net_deposits += net_cash
            _bucket(state.net_deposits_by_currency, currency, net_cash)

        # Cost basis reduction for ReturnOfCapital
        if activity_type in self.COST_REDUCTION_ACTIVITY_TYPES and company_id:
            self._handle_return_of_capital(state, event)

        # Holdings
        if company_id and activity_type in self.HOLDING_ACTIVITY_TYPES and quantity != 0:
            cid = int(company_id)
            holding = state.holdings.get(cid)

            if quantity > 0:  # Buy or inbound IST
                if (
                    activity_type == "InternalSecurityTransfer"
                    and self._is_paired_leg(state, data)
                    and self._restore_relocated(state, cid, data, txn_date)
                ):
                    return
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
                    if (
                        activity_type == "InternalSecurityTransfer"
                        and self._is_paired_leg(state, data)
                    ):
                        self._relocate_outbound(state, cid, holding, data, sell_qty)
                        return
                    sold = min(sell_qty, holding.quantity)
                    if sell_qty > holding.quantity:
                        logger.warning(
                            "Sell truncation: account=%s company=%s sell_qty=%s > holding_qty=%s",
                            state.account_id, cid, sell_qty, holding.quantity,
                        )
                    sale_proceeds = sold * unit_price
                    cost_of_sold, _, _ = _fifo_cost_and_removed(
                        holding.lots, sold, holding.average_cost
                    )
                    holding.realized_gain_loss += sale_proceeds - cost_of_sold
                    holding.total_cost -= cost_of_sold
                    holding.quantity -= sold
                    # Recalculate average_cost from remaining lots
                    if holding.lots:
                        total_qty = sum(lot["quantity"] for lot in holding.lots)
                        total_lot_cost = sum(
                            lot["quantity"] * lot["cost_per_share"]
                            for lot in holding.lots
                        )
                        holding.average_cost = total_lot_cost / total_qty if total_qty else Decimal("0")
                    if holding.quantity <= 0:
                        del state.holdings[cid]

    def _is_paired_leg(self, state: AccountState, data: dict) -> bool:
        """Whether this IST leg's pair key is in the account's paired set.

        The paired set is normally precomputed by ``replay_to_date`` from the
        account's complete log. When it is absent -- a caller drove the handler
        directly without replaying -- it is computed lazily from the account's
        full event log, so pairing is identical to a replay.
        """
        if state.ist_paired_keys is None:
            state.ist_paired_keys = self._pair_keys_for_account(state.account_id)
        key = pair_key(data)
        return key is not None and key in state.ist_paired_keys

    def _pair_keys_for_account(self, account_id: int) -> frozenset[tuple[Any, ...]]:
        """IST pair keys for an account from its complete event log."""
        events = self.event_store.get_all_events(aggregate_type="account")
        account_events = [
            ev
            for ev in events
            if _parse_account_id(ev.get("aggregate_id", "")) == account_id
        ]
        return reconcile_transfers(account_events).paired_keys

    def _take_parked(self, state: AccountState, key: tuple[Any, ...]) -> dict | None:
        """Pop the FIFO head of the parked relocation batches for a pair key."""
        batches = state.relocated_basis.get(key)
        if not batches:
            return None
        return batches.pop(0)

    def _relocate_outbound(
        self,
        state: AccountState,
        cid: int,
        holding: HoldingState,
        data: dict,
        sell_qty: Decimal,
    ) -> None:
        """Move a paired outbound IST leg out of the account without a sale.

        The securities genuinely leave the tracked account, so the portfolio dip
        at the gap date stays visible; no gain or loss is realized. The removed
        shares' original basis is parked by pair key, and the inbound leg
        restores it when it arrives.
        """
        sold = min(sell_qty, holding.quantity)
        if sell_qty > holding.quantity:
            logger.warning(
                "IST relocation truncation: account=%s company=%s sell_qty=%s > holding_qty=%s",
                state.account_id, cid, sell_qty, holding.quantity,
            )
        cost_of_sold, removed_fragments, leftover = _fifo_cost_and_removed(
            holding.lots, sold, holding.average_cost
        )
        if leftover > 0 and holding.average_cost:
            removed_fragments = [
                *removed_fragments,
                {
                    "quantity": leftover,
                    "cost_per_share": holding.average_cost,
                    "date": holding.trade_date,
                },
            ]
        key = pair_key(data)
        batches = state.relocated_basis.setdefault(key, [])
        batches.append(
            {
                "symbol": data.get("symbol"),
                "quantity": sold,
                "total_cost": cost_of_sold,
                "average_cost": cost_of_sold / sold if sold else Decimal("0"),
                "lots": removed_fragments,
                "trade_date": holding.trade_date,
            }
        )
        holding.total_cost -= cost_of_sold
        holding.quantity -= sold
        if holding.lots:
            total_qty = sum(lot["quantity"] for lot in holding.lots)
            total_lot_cost = sum(
                lot["quantity"] * lot["cost_per_share"]
                for lot in holding.lots
            )
            holding.average_cost = total_lot_cost / total_qty if total_qty else Decimal("0")
        if holding.quantity <= 0:
            del state.holdings[cid]

    def _restore_relocated(
        self,
        state: AccountState,
        cid: int,
        data: dict,
        txn_date: date | None,
    ) -> bool:
        """Restore a paired inbound IST leg from its parked basis.

        Re-applies the original lot records, total cost and trade date the
        matching outbound leg parked, so the position returns with its original
        cost basis (merged into a holding re-bought in the meantime). Returns
        False when nothing is parked yet -- e.g. the inbound leg precedes its
        outbound in the stream -- and the caller falls back to the normal
        purchase path.
        """
        key = pair_key(data)
        parked = self._take_parked(state, key)
        if parked is None:
            return False
        restored_qty = parked["quantity"]
        restored_cost = parked["total_cost"]
        lots = [dict(lot) for lot in parked.get("lots", [])]
        trade_date = parked.get("trade_date") or txn_date
        holding = state.holdings.get(cid)
        if holding:
            new_qty = holding.quantity + restored_qty
            new_cost = holding.total_cost + restored_cost
            holding.quantity = new_qty
            holding.total_cost = new_cost
            holding.average_cost = new_cost / new_qty if new_qty else Decimal("0")
            holding.lots.extend(lots)
        else:
            state.holdings[cid] = HoldingState(
                company_id=cid,
                symbol=data.get("symbol") or "?",
                quantity=restored_qty,
                total_cost=restored_cost,
                average_cost=restored_cost / restored_qty if restored_qty else Decimal("0"),
                trade_date=trade_date,
                lots=lots,
            )
        return True

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
                lot_total_cost = sum(
                    lot["quantity"] * lot["cost_per_share"] for lot in holding.lots
                )
                if lot_total_cost > 0:
                    ratio = reduction / lot_total_cost
                    for lot in holding.lots:
                        lot["cost_per_share"] *= (1 - ratio)
                        if lot["cost_per_share"] < 0:
                            lot["cost_per_share"] = Decimal("0")
            # Recalculate average_cost
            if holding.quantity > 0:
                holding.average_cost = holding.total_cost / holding.quantity

    def _get_event_date(self, event: dict) -> date | None:
        """Extract the relevant date from an event.

        Priority:
        1. data.effective_date — explicit override
        2. data.transaction_date — for trade/dividend events
        3. data.report_date — for split/corporate-action events (historical date)
        4. event.created_at — fallback (insertion timestamp)

        Delegates to shared.split_utils.extract_event_date so the replay engine
        and the split reconciler never diverge on ordering decisions.
        """
        return extract_event_date(event)

    def replay_to_date(
        self,
        account_id: int,
        target_date: date,
    ) -> AccountState:
        """Rebuild account state by replaying all events up to target_date."""
        events = self.event_store.get_all_events(
            aggregate_type="account",
        )
        all_account_events = []
        account_events = []
        for ev in events:
            ev_account_id = _parse_account_id(ev.get("aggregate_id", ""))
            if ev_account_id != account_id:
                continue
            all_account_events.append(ev)
            ev_date = self._get_event_date(ev)
            if ev_date is not None and ev_date <= target_date:
                account_events.append(ev)

        account_events.sort(key=lambda e: self._get_event_date(e) or date.min)

        state = AccountState(account_id=account_id)
        # Pairing sees the account's COMPLETE log, not just what happened by the
        # target date: the two legs of a relocation can straddle any single date,
        # and the pair decision must be identical at every replay date.
        state.ist_paired_keys = reconcile_transfers(all_account_events).paired_keys

        handled: dict[str, int] = {}
        skipped_unknown: list[str] = []
        for ev in account_events:
            event_type = ev.get("event_type", "")
            handler_name = f"_handle_{event_type}"
            handler = getattr(self, handler_name, None)
            if handler:
                handler(state, ev)
                handled[event_type] = handled.get(event_type, 0) + 1
            else:
                skipped_unknown.append(event_type)

        if debug_trace.is_enabled():
            debug_trace.trace_event(
                "replay_engine",
                "replay_to_date",
                account_id=account_id,
                target_date=target_date.isoformat(),
                fetched=len(events),
                matched=len(account_events),
                filtered_out=len(events) - len(account_events),
                handled_total=sum(handled.values()),
                handled_by_type=handled,
                skipped_unknown=skipped_unknown,
                final_holdings=len(state.holdings),
                cash_balance=state.cash_balance,
                **debug_trace.summarize_ids(
                    [str(e.get("id")) for e in account_events]
                ),
            )

        return state

    def build_snapshot_from_replay(
        self,
        account_id: int,
        target_date: date,
        prices_by_company: dict[int, dict],
        price_history: dict[int, list[tuple]] | None = None,
        account_currency: str = "CAD",
        exchange_overrides: dict[int, str | None] | None = None,
        company_currencies: dict[int, str] | None = None,
        companies_map: dict[int, dict] | None = None,
        derived_cdr_companies: set[int] | None = None,
        cdr_lots: dict[int, dict[str, Decimal]] | None = None,
    ) -> dict:
        """Build a snapshot dict from replay state (compatible with build_snapshot_row output).

        Args:
            exchange_overrides: Optional dict mapping company_id → exchange_override
                (e.g. {42: "TOR"} for CDR holdings). Used to apply CDR ratio in pricing.
            company_currencies: Optional dict mapping company_id → price currency
                (e.g. {478: "USD", 1027: "CAD"}). Used for FX conversion.
            companies_map: Optional dict mapping company_id → companies row dict
                (with cdr_ratio field). Used for per-company CDR ratio lookup.
            cdr_lots: Optional per-company lot buckets as of target_date, from
                cdr_utils.derive_account_cdr_lots_as_of. A mixed position is priced one
                leg at a time; omit it and every position keeps its company-keyed price.
        """
        from config import settings
        from database import supabase as _sb
        from shared.fx_service import FXService
        from shared.snapshot_builder import get_cdr_ratio_for_company

        enable_fx = getattr(settings, "ENABLE_FX_CONVERSION", False)
        fx_svc = FXService(_sb) if enable_fx else None

        state = self.replay_to_date(account_id, target_date)

        holdings_list = []
        total_market_value = Decimal("0.00")
        total_cost = Decimal("0.00")
        used_tiers: list[PriceTier] = []

        for cid, holding, leg_kind in _cdr_lot_legs(
            state.holdings, cdr_lots, derived_cdr_companies
        ):
            qty = holding.quantity
            cost = holding.total_cost

            if leg_kind is not None:
                exch_override = EXCHANGE_OVERRIDE_TOR if leg_kind == "cdr" else None
            else:
                exch_override = (
                    exchange_overrides.get(cid) if exchange_overrides else None
                )
                # cdr_utils owns the canonical CDR signal; the holdings flag alone can be NULL.
                if derived_cdr_companies and cid in derived_cdr_companies:
                    exch_override = EXCHANGE_OVERRIDE_TOR
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

            # Provenance for every tier, not just FORWARD_FILL: a stale price must
            # never be labelled OK. Canonical form: snapshot_builder.build_snapshot_row.
            price_age = (
                (target_date - resolved_price_date).days if resolved_price_date else None
            )

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
                "price_age_days": price_age,
                "price_data_quality": pos_quality,
                "trade_date": holding.trade_date.isoformat() if holding.trade_date else None,
                "lots": lots_out,
            })

        cash_total, cash_fx_applied = convert_cash_map(
            _cash_view(state.cash_by_currency, state.cash_balance),
            account_currency,
            target_date,
            fx_svc,
        )
        deposits_total, _ = convert_cash_map(
            _cash_view(state.net_deposits_by_currency, state.net_deposits),
            account_currency,
            target_date,
            fx_svc,
        )
        total_value = total_market_value + cash_total

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
        prices_by_company: dict[int, dict],
        price_history: dict[int, list[tuple]] | None = None,
        account_currency: str = "CAD",
        company_currencies: dict[int, str] | None = None,
        companies_map: dict[int, dict] | None = None,
        derived_cdr_companies: set[int] | None = None,
        cdr_lots: dict[int, dict[str, Decimal]] | None = None,
    ) -> ComparisonResult:
        """Compare replay result with a stored portfolio_snapshot row.

        cdr_lots must come from cdr_utils.derive_account_cdr_lots_as_of for
        snapshot_date. Omitting it compares a company-keyed replay against a
        lot-aware stored row, which reports a mismatch for every mixed position.
        """
        replay = self.build_snapshot_from_replay(
            account_id=account_id,
            target_date=snapshot_date,
            prices_by_company=prices_by_company,
            price_history=price_history,
            account_currency=account_currency,
            company_currencies=company_currencies,
            companies_map=companies_map,
            derived_cdr_companies=derived_cdr_companies,
            cdr_lots=cdr_lots,
        )

        differences: list[str] = []

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
