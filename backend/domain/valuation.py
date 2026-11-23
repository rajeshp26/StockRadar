"""Pure valuation kernel.

Every consumer — snapshots, replay, live portfolio, watchlist, quote endpoint and SSE —
must call this module. CDR ratios are applied to prices before quantity multiplication and
only for the CDR leg; FX is applied once afterwards.

shortcut: FX rates are caller-supplied rather than resolved from exchange_rates here; upgrade when a reporting-currency request needs automatic rate lookup.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable


class ValuationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ValuedLot:
    security_id: int
    symbol: str
    exchange: str
    kind: str
    currency: str
    quantity: Decimal
    price: Decimal
    effective_price: Decimal
    native_value: Decimal
    fx_rate: Decimal
    reporting_value: Decimal
    cdr_ratio_applied: Decimal | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "security_id": self.security_id,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "kind": self.kind,
            "currency": self.currency,
            "quantity": float(self.quantity),
            "price": float(self.price),
            "effective_price": float(self.effective_price),
            "native_value": float(self.native_value),
            "fx_rate": float(self.fx_rate),
            "reporting_value": float(self.reporting_value),
            "cdr_ratio_applied": float(self.cdr_ratio_applied) if self.cdr_ratio_applied else None,
        }


@dataclass(frozen=True)
class PortfolioValue:
    lots: tuple[ValuedLot, ...]
    native_value: Decimal
    reporting_value: Decimal

    def as_dict(self) -> dict[str, Any]:
        return {
            "lots": [lot.as_dict() for lot in self.lots],
            "native_value": float(self.native_value),
            "reporting_value": float(self.reporting_value),
        }


def _dec(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def price_for_listing(security: dict[str, Any], price: Any) -> tuple[Decimal, Decimal | None]:
    """Return (effective price, applied ratio) for one listing's native quote."""
    if price is None:
        raise ValuationError("MISSING_PRICE", "A security cannot be valued without a quote")
    effective = _dec(price)
    ratio: Decimal | None = None
    if str(security.get("kind", "")).upper() == "CDR":
        raw = security.get("cdr_ratio")
        if raw is None:
            raise ValuationError("MISSING_CDR_RATIO", "CDR security has no structural ratio")
        ratio = _dec(raw)
        if ratio <= 0:
            raise ValuationError("INVALID_CDR_RATIO", "CDR ratio must be positive")
        effective = effective / ratio
    return effective, ratio


def value_security(
    security: dict[str, Any],
    quantity: Any,
    price: Any,
    fx_rate: Any = 1,
) -> ValuedLot:
    """Value exactly one security lot. No I/O, no provider rules, no hidden state."""
    effective, ratio = price_for_listing(security, price)
    qty = _dec(quantity)
    rate = _dec(fx_rate)
    native = qty * effective
    return ValuedLot(
        security_id=int(security["security_id"]),
        symbol=str(security.get("symbol", "")),
        exchange=str(security.get("exchange", "")),
        kind=str(security.get("kind", "COMMON")).upper(),
        currency=str(security.get("currency", "USD")),
        quantity=qty,
        price=_dec(price),
        effective_price=effective,
        native_value=native,
        fx_rate=rate,
        reporting_value=native * rate,
        cdr_ratio_applied=ratio,
    )


def value_lots(lots: Iterable[ValuedLot]) -> PortfolioValue:
    values = tuple(lots)
    return PortfolioValue(
        lots=values,
        native_value=sum((lot.native_value for lot in values), Decimal(0)),
        reporting_value=sum((lot.reporting_value for lot in values), Decimal(0)),
    )
