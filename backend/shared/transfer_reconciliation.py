"""
Import-time reconciliation of ``InternalSecurityTransfer`` events.

A security transfer has two legs: securities leave one account and arrive in
another. The brokerage CSV export carries no counterparty or transfer id, so
the only way to pair the legs is to match them on the attributes that *are*
present -- symbol, currency and absolute quantity.

Why this matters
----------------
A batch containing only the outbound legs makes the portfolio look like it lost
value, because the cash moved but the securities never arrived. On 2024-12-23
65 such legs (-1,376.47 shares, -27,874.86 USD) landed in accounts 8 and 9
with no inbound leg in the same window, which surfaced as an artificial -32.39%
Q4 drop. Nothing in the import result said so; it had to be reconstructed after
the fact.

Design constraints
------------------
* **Advisory, never fatal.** A transfer whose counterparty is simply not in the
  imported data is normal (the other leg may arrive in a later export, or live
  in an account this user does not track). Reconciliation reports; it never
  raises and never blocks an import.
* **Pure.** No database client, no network. Callers supply already-loaded
  events, optionally including prior imports so a leg can pair across files.
* **Honest about limits.** Matching on (symbol, currency, quantity) can pair the
  wrong leg when two identical transfers of the same symbol and size cross in
  the same window. It establishes *that* a counterpart exists, not its identity.
  A real ``transfer_id`` would be required for that, and the source export does
  not contain one -- so this module deliberately never invents one.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

__all__ = [
    "TRANSFER_ACTIVITY_TYPE",
    "TransferReconciliation",
    "UnpairedTransfer",
    "pair_key",
    "reconcile_transfers",
]

TRANSFER_ACTIVITY_TYPE = "InternalSecurityTransfer"

#: Quantities are compared after rounding so float noise (e.g. -4.0 vs -4.0000001)
#: does not present an otherwise exact pair as unmatched.
_QUANTITY_PRECISION = 6


@dataclass(frozen=True)
class UnpairedTransfer:
    """A transfer leg with no counterpart among the events supplied."""

    account_id: int | None
    symbol: str | None
    currency: str | None
    quantity: float | None
    net_cash_amount: float | None
    transaction_date: str | None
    reason: str

    def as_warning(self) -> str:
        quantity = self.quantity
        leg = "outbound" if (quantity or 0) < 0 else "inbound"
        parts = [f"{TRANSFER_ACTIVITY_TYPE} {leg} leg unpaired", self.symbol or "?"]
        if self.account_id is not None:
            parts.append(f"account {self.account_id}")
        if quantity is not None:
            parts.append(f"qty {quantity:+g}")
        if self.currency:
            parts.append(self.currency)
        if self.net_cash_amount is not None:
            parts.append(f"net {self.net_cash_amount:+g}")
        if self.transaction_date:
            parts.append(f"dated {self.transaction_date}")
        parts.append(f"({self.reason})")
        return " ".join(parts)


@dataclass(frozen=True)
class TransferReconciliation:
    """Outcome of pairing transfer legs across a set of events."""

    transfer_count: int = 0
    paired_count: int = 0
    paired_keys: frozenset[tuple[Any, ...]] = frozenset()
    unpaired: tuple[UnpairedTransfer, ...] = ()

    @property
    def unpaired_count(self) -> int:
        return len(self.unpaired)

    @property
    def warnings(self) -> list[str]:
        return [t.as_warning() for t in self.unpaired]

    def summary(self) -> str:
        if self.transfer_count == 0:
            return "No security transfers in this import."
        if not self.unpaired:
            return f"All {self.transfer_count} security transfer leg(s) paired."
        return (
            f"{self.paired_count}/{self.transfer_count} security transfer leg(s) "
            f"paired; {len(self.unpaired)} unpaired -- the counterparty leg is not "
            "present in the imported data (it may arrive in a later export)."
        )


def _payload_of(item: Any) -> Mapping[str, Any] | None:
    """Accept either a full event envelope or a bare ``data`` payload."""
    if not isinstance(item, Mapping):
        return None
    data = item.get("data")
    if isinstance(data, Mapping):
        return data
    return item


def _quantity(payload: Mapping[str, Any]) -> float | None:
    raw = payload.get("quantity")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _pair_key(payload: Mapping[str, Any]) -> tuple[Any, ...] | None:
    quantity = _quantity(payload)
    if quantity is None:
        return None
    currency = payload.get("currency") or ""
    return (
        payload.get("symbol"),
        str(currency).upper(),
        round(abs(quantity), _QUANTITY_PRECISION),
    )


def pair_key(payload: Mapping[str, Any]) -> tuple[Any, ...] | None:
    """Public pairing identity of a transfer payload.

    ``(symbol, currency, |quantity| rounded to 6dp)``, or None when the quantity
    is missing or unparseable. Exposed so consumers (the replay engine's IST
    relocation) key events with exactly the identity reconciliation paired its
    legs on, instead of re-deriving a private copy.
    """
    return _pair_key(payload)


def _unpaired(payload: Mapping[str, Any], reason: str) -> UnpairedTransfer:
    return UnpairedTransfer(
        account_id=payload.get("account_id"),
        symbol=payload.get("symbol"),
        currency=payload.get("currency"),
        quantity=_quantity(payload),
        net_cash_amount=payload.get("net_cash_amount"),
        transaction_date=payload.get("transaction_date"),
        reason=reason,
    )


def reconcile_transfers(
    events: Iterable[Any],
    *,
    prior_events: Iterable[Any] | None = None,
) -> TransferReconciliation:
    """Pair ``InternalSecurityTransfer`` legs by symbol, currency and quantity.

    ``prior_events`` lets a leg pair against an earlier import, so a transfer
    whose two legs arrive in different exports still reconciles. Prior events are
    consumed first so the current batch is matched against established history
    before legs are paired among themselves.

    Never raises: malformed entries are reported as unpaired rather than
    aborting the caller's import.
    """
    transfers: list[Mapping[str, Any]] = []
    for source in (prior_events or (), events):
        for item in source:
            payload = _payload_of(item)
            if payload is None:
                continue
            if payload.get("activity_type") != TRANSFER_ACTIVITY_TYPE:
                continue
            transfers.append(payload)

    if not transfers:
        return TransferReconciliation()

    outbound: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    inbound: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    degenerate: list[Mapping[str, Any]] = []

    for payload in transfers:
        key = _pair_key(payload)
        quantity = _quantity(payload)
        if key is None or quantity == 0:
            degenerate.append(payload)
            continue
        (outbound if quantity < 0 else inbound)[key].append(payload)

    paired_legs = 0
    paired_keys: set[tuple[Any, ...]] = set()
    unpaired: list[UnpairedTransfer] = []

    for key in set(outbound) | set(inbound):
        outs = outbound.get(key, [])
        ins = inbound.get(key, [])
        pairs = min(len(outs), len(ins))
        if pairs:
            paired_keys.add(key)
        paired_legs += pairs * 2
        if pairs < len(outs):
            unpaired.extend(
                _unpaired(p, "no matching inbound leg in the imported data")
                for p in outs[pairs:]
            )
        if pairs < len(ins):
            unpaired.extend(
                _unpaired(p, "no matching outbound leg in the imported data")
                for p in ins[pairs:]
            )

    unpaired.extend(
        _unpaired(p, "missing or zero quantity; cannot be paired")
        for p in degenerate
    )
    unpaired.sort(
        key=lambda t: (t.transaction_date or "", t.symbol or "", t.account_id or 0)
    )

    return TransferReconciliation(
        transfer_count=len(transfers),
        paired_count=paired_legs,
        paired_keys=frozenset(paired_keys),
        unpaired=tuple(unpaired),
    )
