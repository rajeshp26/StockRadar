"""
Canonical ``transaction_imported`` event payload construction.

Single source of truth for the ``data`` payload of ``transaction_imported``
events. Every write path (CSV import, manual entry, backfill) MUST build its
payload through :func:`build_transaction_event_data`.

Why this module exists
----------------------
Four independent write paths each hand-rolled this dict, and each dropped a
different subset of the fields the parser had already produced:

* CSV import (``portfolio_service._process_import_background``) dropped
  ``settlement_date``, ``activity_sub_type`` and ``direction``.
* Manual entry (``portfolio_service.add_manual_transaction``) dropped
  ``currency``, ``security_name``, ``exchange_override``, ``settlement_date``,
  ``activity_sub_type`` and ``direction``.
* Backfill (``scripts/backfill_events_from_transactions.build_event_from_transaction``)
  dropped ``security_name``, ``exchange_override``, ``settlement_date``,
  ``activity_sub_type`` and ``direction``.

Two concrete defects resulted.

1. Transfer provenance was destroyed. 65 outbound ``InternalSecurityTransfer``
   events dated 2024-12-23 could not be paired with their inbound legs because
   ``direction`` / ``activity_sub_type`` had been discarded, which surfaced as an
   artificial -32.39% Q4 portfolio drop that had to be reconstructed by hand
   from the raw CSV export.
2. CDR override derivation broke for backfilled events.
   ``services/event_projection_handler._derive_cdr_overrides`` reads
   ``exchange_override`` and ``security_name`` to decide the TOR override; the
   backfill payload omitted both, so backfilled CDR symbols lost their pricing
   venue.

Adding keys is backward compatible: consumers read payloads with
``data.get(...)``, and events already in the store simply report ``None`` for
the new keys. Nothing re-reads history on write, so stored events stay valid.

Fields deliberately NOT persisted
---------------------------------
``commission``
    ``shared/replay_engine`` reads ``data["commission"]`` to compute
    ``cost_per_share = unit_price + commission / quantity``. CSV imports parse
    commission but historically dropped it, so every imported trade's cost basis
    silently ignored commission. Emitting the key here would immediately change
    cost basis -- and therefore every historical valuation and performance
    figure the user sees. That is a correctness improvement but a *behavioural*
    change to reported numbers, so it is a separate, explicitly-approved change
    rather than a side effect of a provenance fix.

``raw_data``
    The full original CSV row. It retains brokerage account identifiers (PII)
    and would multiply event-store row size substantially. Every field needed
    for reconciliation is parsed explicitly, so the raw row adds no downstream
    value.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "CANONICAL_TRANSACTION_EVENT_FIELDS",
    "build_transaction_event_data",
]

#: The exact key set every ``transaction_imported`` payload carries. Uniform
#: shape matters: consumers such as the CDR override derivation index these keys
#: directly, and a missing key is indistinguishable from an absent value.
CANONICAL_TRANSACTION_EVENT_FIELDS: tuple[str, ...] = (
    "account_id",
    "company_id",
    "transaction_date",
    "settlement_date",
    "activity_type",
    "activity_sub_type",
    "direction",
    "symbol",
    "security_name",
    "exchange_override",
    "quantity",
    "unit_price",
    "net_cash_amount",
    "currency",
    "notes",
)


def build_transaction_event_data(
    *,
    account_id: int | None,
    company_id: int | None,
    transaction_date: str | None,
    activity_type: str | None,
    settlement_date: str | None = None,
    activity_sub_type: str | None = None,
    direction: str | None = None,
    symbol: str | None = None,
    security_name: str | None = None,
    exchange_override: str | None = None,
    quantity: float | None = None,
    unit_price: float | None = None,
    net_cash_amount: float | None = None,
    currency: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Build the canonical ``transaction_imported`` event ``data`` payload.

    Always emits every key in :data:`CANONICAL_TRANSACTION_EVENT_FIELDS`, using
    ``None`` for absent values, so stored events share one shape.

    ``transaction_date`` and ``settlement_date`` must be ISO-8601 strings.
    Callers holding ``date``/``datetime`` objects must convert first -- this
    keeps the builder free of import-time dependencies and trivially testable.
    """
    return {
        "account_id": account_id,
        "company_id": company_id,
        "transaction_date": transaction_date,
        "settlement_date": settlement_date,
        "activity_type": activity_type,
        "activity_sub_type": activity_sub_type,
        "direction": direction,
        "symbol": symbol,
        "security_name": security_name,
        "exchange_override": exchange_override,
        "quantity": quantity,
        "unit_price": unit_price,
        "net_cash_amount": net_cash_amount,
        "currency": currency,
        "notes": notes,
    }