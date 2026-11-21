"""Shared CDR detection utilities - single source of truth for CDR classification.

Every CDR decision point in the system (parser, holding backfill, snapshot
rebuild, event projection, price monitor) derives from the same name patterns
and the same transaction-derived per-(account, company) classification, so the
signal can never drift between layers the way it did in the original bug
(parser detected the CDR, the import dropped it, holdings stayed NULL, pricing
never fired).

The canonical truth for whether a (account, company) pair is held as a CDR is
the raw transaction data: `portfolio_transactions.raw_data` (the original CSV
row, stored as JSON, with the full security `name`) and/or the
`security_name` column. This is exactly the signal the parser keys on when it
sets `exchange_override = "TOR"` per transaction.

Nothing in this module reads from `portfolio_holdings.exchange_override`;
holdings are an OUTPUT of this signal, never an input.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from shared.split_utils import split_adjustment_factor, split_schedule_from_rows

logger = logging.getLogger("stockerpro.cdr")

# CDR suffix patterns (Canadian Depositary Receipts). Order matters -
# most specific first. Matches Wealthsimple export naming:
#   "TSLA CDR (CAD Hedged)", "NFLX CDR (Hedged)", "AAPL CDR"
CDR_PATTERNS = [
    r"\s+CDR\s*\(CAD Hedged\)",
    r"\s+CDR\s*\(Hedged\)",
    r"\s+CDR",
]

# The exchange override value marking a holding as priced on TSX (CDR).
EXCHANGE_OVERRIDE_TOR = "TOR"

# Structural CDR ratio: 1 CDR = 1/10 of an underlying US share.
CDR_RATIO = 10.0
# I3: the trace compares this ratio against the value that reached pricing.
# Comparing the two as floats is an exact-equality test on binary noise: a ratio
# that drifted to 9.999999999999999 cannot be classified deterministically.
# str() preserves the intended decimal instead of the binary expansion.
CDR_RATIO_DECIMAL = Decimal(str(CDR_RATIO))


def matches_cdr_name(name: str | None) -> bool:
    """True if a raw symbol / security name carries a CDR marker.

    Case-insensitive, mirrors the parser's detection exactly (any pattern hit).
    """
    if not name:
        return False
    return any(re.search(p, name, re.IGNORECASE) for p in CDR_PATTERNS)


def extract_security_name(raw_data: Any, security_name: str | None) -> str | None:
    """Resolve the display security name from raw_data (JSON str/dict) or the column."""
    name = None
    if raw_data is not None:
        if isinstance(raw_data, dict):
            name = raw_data.get("name")
        elif isinstance(raw_data, str):
            try:
                parsed = json.loads(raw_data)
            except (ValueError, TypeError):
                parsed = None
            if isinstance(parsed, dict):
                name = parsed.get("name")
        if name:
            return str(name)
    return security_name


def is_cdr_transaction(raw_data: Any, security_name: str | None) -> bool:
    """True if a stored transaction row is a CDR trade (raw_data + security_name)."""
    return matches_cdr_name(extract_security_name(raw_data, security_name))


def iter_transactions(client, select_cols: list[str], account_id: int | None = None):
    """Yield ALL portfolio_transactions rows, paginated past the 1000-row cap.

    Pagination is mandatory: Supabase defaults to a 1000-row page and silently
    truncates otherwise. Optional eq filter on account_id for targeted scans.
    """
    step = 1000
    start = 0
    select = ",".join(select_cols)
    while True:
        q = client.table("portfolio_transactions").select(select)
        if account_id is not None:
            q = q.eq("account_id", account_id)
        q = q.order("transaction_id").range(start, start + step - 1)
        batch = q.execute()
        rows = batch.data or []
        yield from rows
        if len(rows) < step:
            break
        start += step


def derive_account_cdr_companies(client, account_id: int) -> set[int]:
    """Company_ids traded as CDRs in an account, derived from transaction names.

    Includes sold positions (e.g. AMD/NVDA in account 7), so snapshot rebuilds
    over historical dates apply the CDR override to every window where the CDR
    was held, not just current holdings.
    """
    cdr_cids: set[int] = set()
    for row in iter_transactions(
        client, ["company_id", "security_name", "raw_data"], account_id=account_id
    ):
        cid = row.get("company_id")
        if cid is None:
            continue
        if is_cdr_transaction(row.get("raw_data"), row.get("security_name")):
            cdr_cids.add(int(cid))
    return cdr_cids


def derive_cdr_companies_by_account(client) -> dict[int, set[int]]:
    """account_id -> set of company_ids traded as CDRs, across ALL accounts.

    One paginated scan of every transaction row; the classification-per-account
    is what the holding backfill keys on, so a company can be CDR in one
    account and direct in another (e.g. AAPL: CDR in acct 7, direct in
    accts 10/11) and each account's holdings get the correct flag.
    """
    out: dict[int, set[int]] = {}
    for row in iter_transactions(
        client, ["account_id", "company_id", "security_name", "raw_data"]
    ):
        aid = row.get("account_id")
        cid = row.get("company_id")
        if aid is None or cid is None:
            continue
        if is_cdr_transaction(row.get("raw_data"), row.get("security_name")):
            out.setdefault(int(aid), set()).add(int(cid))
    return out


# Activity types that move SHARES. This set is the one the replay engine applies to
# holdings, deliberately shared rather than re-declared: `quantity` in a Wealthsimple
# export carries a CASH amount for every other activity type (dividend, interest, fee,
# withholding tax, return of capital, non-cash distribution), so summing it as a share
# movement corrupts the position. Live evidence: account 7 / ETHY (company 3157) holds
# 80 shares, while summing every non-Dividend row yields 90.616 because its
# ReturnOfCapital and NonCashDistribution rows were counted as shares.
SHARE_MOVEMENT_ACTIVITY_TYPES = frozenset({"Trade", "InternalSecurityTransfer"})


def load_split_schedule(client) -> dict[int, list[tuple[date, Decimal]]]:
    """The whole `splits` table as ``{company_id: [(date, multiplier)]}``.

    One paginated read. Imported lazily because split_sync owns split reconciliation
    and this module is imported by everything that needs a lot total.
    """
    from shared.split_sync import fetch_all_splits

    return split_schedule_from_rows(fetch_all_splits(client))


def _as_of_date(as_of: str) -> date | None:
    try:
        return date.fromisoformat(str(as_of)[:10])
    except (TypeError, ValueError):
        logger.warning(
            "lot replay: as_of %r is not an ISO date; split adjustment skipped", as_of
        )
        return None


def _movement_date(raw: Any) -> date | None:
    if isinstance(raw, date):
        return raw
    if raw is None:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except (TypeError, ValueError):
        return None


def _accumulate_lots(
    rows,
    as_of: str,
    splits_by_company: dict[int, list[tuple[date, Decimal]]] | None = None,
) -> dict[int, dict[str, Decimal]]:
    """Shared lot arithmetic. `rows` is an iterable of transaction dicts.

    Signed share movements are accumulated per (company, lot kind) up to `as_of`.
    Quantities are already signed (sales and transfer-outs are negative), so the
    running total IS the position held on that date -- no separate lot ledger.

    Two rules make this agree with the stored position, and both were missing:

    1. Only SHARE_MOVEMENT_ACTIVITY_TYPES move shares. Every other activity type puts a
       cash amount in `quantity`; counting it (the old rule was "anything except
       Dividend") inflated positions by the sum of their dividends, fees, return of
       capital and non-cash distributions.
    2. Movements are restated into `as_of` units using the split schedule
       (split_utils.split_adjustment_factor). The stored position is split-adjusted
       because the replay engine applies `split` events; raw transaction quantities are
       not. Comparing the two without adjusting is what made every split company
       disagree -- SPCE 30 vs 1.5, NFLX 73 vs 730, NYCB 30 vs 9.9999.

    `splits_by_company` is required for a split-adjusted answer; the callers pass it
    from one batched read, and passing None keeps the old raw semantics (used only by
    tests that assert on unadjusted arithmetic).
    """
    as_of_date = _as_of_date(as_of)
    totals: dict[int, dict[str, Decimal]] = {}
    for row in rows:
        cid = row.get("company_id")
        if cid is None:
            continue
        if str(row.get("transaction_date") or "")[:10] > as_of:
            continue
        if str(row.get("activity_type") or "") not in SHARE_MOVEMENT_ACTIVITY_TYPES:
            continue
        try:
            qty = Decimal(str(row["quantity"]))
        except (TypeError, ValueError, ArithmeticError):
            continue
        factor = Decimal(1)
        if as_of_date is not None and splits_by_company:
            factor = split_adjustment_factor(
                splits_by_company.get(int(cid)),
                _movement_date(row.get("transaction_date")),
                as_of_date,
            )
            if factor <= 0:
                # A non-positive multiplier cannot come from a real split (it would
                # erase the holding), so treat it as absence of evidence rather than
                # as a position change: the movement is kept unadjusted and visible.
                logger.warning(
                    "lot replay: company %s has a non-positive split multiplier %s; "
                    "leaving its movements unadjusted",
                    cid,
                    factor,
                )
                factor = Decimal(1)
        bucket = (
            "cdr"
            if is_cdr_transaction(row.get("raw_data"), row.get("security_name"))
            else "direct"
        )
        lots = totals.setdefault(int(cid), {"cdr": Decimal(0), "direct": Decimal(0)})
        lots[bucket] += qty * factor
    return {
        cid: {kind: qty for kind, qty in lots.items() if qty != 0}
        for cid, lots in totals.items()
        if any(qty != 0 for qty in lots.values())
    }


_LOT_COLUMNS = [
    "company_id",
    "transaction_date",
    "activity_type",
    "quantity",
    "security_name",
    "raw_data",
]


def derive_account_cdr_lots_as_of(
    client, account_id: int, as_of: str
) -> dict[int, dict[str, Decimal]]:
    """Per-company signed share totals split by lot kind, replayed to a date.

    derive_account_cdr_companies() answers "was this company EVER traded as a CDR
    in this account" -- one company-level answer carrying no date dimension. It
    therefore cannot express a company held as BOTH CDR and direct shares, nor a
    window in which only the direct lot was held, so applying it divides the
    direct lot as well.

    This replays the signed share movements instead. Quantities are already signed
    (sales and transfer-outs are negative), so accumulating up to a date yields the
    position held on that date without maintaining a separate lot ledger.

    Only share movements are summed (SHARE_MOVEMENT_ACTIVITY_TYPES) and every
    movement is restated into `as_of` units through the split schedule, so the
    result is directly comparable with the split-adjusted stored holding. Both
    rules live in _accumulate_lots().

    Returns company_id -> {"cdr": Decimal, "direct": Decimal}, omitting any company
    or bucket that nets to zero.
    """
    return _accumulate_lots(
        iter_transactions(client, _LOT_COLUMNS, account_id=account_id),
        as_of,
        load_split_schedule(client),
    )


def derive_cdr_lots_by_account_as_of(
    client, as_of: str
) -> dict[int, dict[int, dict[str, Decimal]]]:
    """account_id -> company_id -> lot kind -> signed total, from ONE scan.

    The batched counterpart of derive_account_cdr_lots_as_of(), and it exists for
    the same reason derive_cdr_companies_by_account() does: a per-account call
    re-reads the whole paginated transaction table once per account, so a
    six-account snapshot run would scan it six times. Writers that handle a batch
    of accounts in one pass must use this form.
    """
    grouped: dict[int, list[dict]] = {}
    for row in iter_transactions(client, ["account_id", *_LOT_COLUMNS]):
        aid = row.get("account_id")
        if aid is None:
            continue
        grouped.setdefault(int(aid), []).append(row)
    splits = load_split_schedule(client)
    return {
        aid: _accumulate_lots(rows, as_of, splits) for aid, rows in grouped.items()
    }


def derive_cdr_lots_by_account_at_dates(
    client, dates: list[str]
) -> dict[str, dict[int, dict[int, dict[str, Decimal]]]]:
    """date -> account_id -> company_id -> lot kind -> signed total, from ONE scan.

    Gap repair needs the as-of lot truth for every date it is about to rebuild, not
    just for today. Calling derive_cdr_lots_by_account_as_of() once per gap date would
    re-read the whole paginated transaction table per date, so a six-account run with a
    ten-date gap pays sixty full scans -- minutes of pure I/O on the path that has to
    finish before today's row can be spike-checked against its own baseline.

    The scan is the expensive half and it is date-independent, so it happens once here
    and the per-date arithmetic reuses _accumulate_lots() in memory. That keeps this
    function's semantics identical to the single-date one by construction rather than
    by a parallel reimplementation of the rule.
    """
    wanted = sorted({str(d)[:10] for d in dates})
    if not wanted:
        return {}

    grouped: dict[int, list[dict]] = {}
    for row in iter_transactions(client, ["account_id", *_LOT_COLUMNS]):
        aid = row.get("account_id")
        if aid is None:
            continue
        grouped.setdefault(int(aid), []).append(row)
    splits = load_split_schedule(client)

    out: dict[str, dict[int, dict[int, dict[str, Decimal]]]] = {d: {} for d in wanted}
    for aid, rows in grouped.items():
        for as_of in wanted:
            lots = _accumulate_lots(rows, as_of, splits)
            if lots:
                out[as_of][aid] = lots
    return out



# A replayed lot total and the stored holding quantity are two independent
# derivations. They agree to well within any rounding either could carry; a
# disagreement beyond this means one of them is wrong, and guessing which would
# silently invent share counts, so the caller falls back instead.
LOT_QUANTITY_TOLERANCE = Decimal("0.000001")


def _lot_override(kind: str, cached_override: Any) -> str | None:
    """The exchange_override a leg must carry for build_snapshot_row's lot mode.

    In lot mode _is_cdr is exactly `exchange_override == "TOR"` on the holding row,
    so this value IS the verdict. A direct leg therefore never carries "TOR": a
    cached value the lot evidence contradicts is stripped rather than echoed,
    mirroring _applied_override in snapshot_builder, because a TOR price fetch
    against an unadjusted underlying is the 10x error this module exists to
    prevent.
    """
    if kind == "cdr":
        return EXCHANGE_OVERRIDE_TOR
    return None if cached_override == EXCHANGE_OVERRIDE_TOR else cached_override


def _decimal_quantity(value: Any) -> Decimal:
    """Quantity/cost as its intended decimal, never its binary float expansion (I3)."""
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"not a decimal quantity: {value!r}") from exc


def classify_lot_legs(
    quantity: Decimal,
    total_cost: Decimal,
    lots: dict[str, Decimal] | None,
    company_is_cdr: bool,
    context: str = "",
) -> tuple[list[tuple[str, Decimal, Decimal]], list[str]]:
    """Decide the CDR/direct legs for one holding. BLK-027. The single rule set.

    Returns ``(legs, notes)``, each leg being ``(kind, quantity, cost)`` with kind
    ``"cdr"`` or ``"direct"``. Every writer calls this: the dict-based daily writer
    via :func:`split_holdings_by_cdr_lot`, and the replay engine, whose in-memory lots
    carry no CDR label at all (stored transaction_imported events have no
    security_name, so the lot provenance can only come from portfolio_transactions).
    Two implementations of these rules would drift apart and one would silently
    re-price a mixed position, which is the defect this exists to prevent.

    ``lots`` is the transaction-derived lot map for the company as of the snapshot
    date, or None/empty when there is no lot evidence. Rules, in priority order:

    1. No evidence -> one leg on the company-keyed verdict. Absence of evidence must
       never mean "not a CDR": doing so overvalues a CDR tenfold.
    2. Evidence present but its total disagrees with the stored quantity -> one leg
       on the company-keyed verdict plus a note. Shares are never invented to force
       a match.
    3. Evidence present and reconciling -> one leg per non-zero bucket. A uniform
       position yields a single leg identical to the company-keyed row; a mixed one
       splits cost pro rata by quantity, with the final leg absorbing the residual
       so the leg costs sum to ``total_cost`` exactly.
    """
    company_kind = "cdr" if company_is_cdr else "direct"

    # I3: both production callers supply Decimal, but this is the point where the
    # tolerance is applied, so enforce the type at the boundary. A float reaching
    # here would carry binary noise (1/3 -> 0.3333333333333333) and make the
    # tolerance unfalsifiable. str() keeps the intended decimal, not the binary
    # expansion Decimal(float) would preserve.
    quantity = _decimal_quantity(quantity)
    total_cost = _decimal_quantity(total_cost)
    lots = {kind: _decimal_quantity(q) for kind, q in lots.items()} if lots else lots

    if not lots:
        return [(company_kind, quantity, total_cost)], []

    lot_total = sum(lots.values())
    if abs(lot_total - quantity) > LOT_QUANTITY_TOLERANCE:
        prefix = f"{context}: " if context else ""
        return [(company_kind, quantity, total_cost)], [
            f"{prefix}lot replay totals {lot_total} but stored quantity is "
            f"{quantity}; kept the company-keyed classification instead of splitting"
        ]

    kinds = sorted(lots.items(), key=lambda kv: (kv[0] != "cdr", kv[0]))
    if len(kinds) == 1:
        kind, leg_qty = kinds[0]
        return [(kind, leg_qty, total_cost)], []

    per_share = total_cost / quantity
    allocated = Decimal(0)
    legs: list[tuple[str, Decimal, Decimal]] = []
    for i, (kind, leg_qty) in enumerate(kinds):
        leg_cost = (
            total_cost - allocated
            if i == len(kinds) - 1
            else (per_share * leg_qty)
        )
        allocated += leg_cost
        legs.append((kind, leg_qty, leg_cost))
    return legs, []


def _leg_row(
    row: dict,
    cached_override: Any,
    kind: str | None,
    leg_qty: Decimal,
    leg_cost: Decimal,
) -> dict:
    """One holding row restated as a single CDR/direct leg.

    Takes the source row as a parameter rather than closing over it: a closure
    defined inside the caller's loop would capture the loop variable, so every leg
    built after the loop advanced would be a copy of the wrong holding.
    """
    leg = dict(row)
    leg["quantity"] = leg_qty
    leg["total_cost"] = leg_cost
    if kind is not None:
        leg["exchange_override"] = _lot_override(kind, cached_override)
    return leg


def split_holdings_by_cdr_lot(
    holdings_state: list[dict],
    lots_by_company: dict[int, dict[str, Decimal]] | None,
    derived_cdr_companies: set[int],
) -> tuple[list[dict], list[str]]:
    """Expand one row per company into one row per CDR lot, where evidence exists.

    BLK-027. The CDR adjustment lands on the PRICE, not the quantity
    (snapshot_builder: `raw_value = qty * current_price`), so a single per-company
    price cannot value two lots held on different scales. Account 9 / META holds 25
    CDR + 2 direct shares; classifying the company as CDR divides the direct leg too.

    Contract, in priority order, per holding:

    1. No lot evidence for the company -> emit ONE row carrying the company-keyed
       verdict, reproducing today's valuation exactly. A company with no
       transactions at or before the date is ABSENT from the lot map, and in lot
       mode the fallback is the holding's own cached flag -- which is NULL for
       accounts whose flag was never populated. Falling back to the flag there
       would treat a CDR as direct and overvalue it 10x, which is the original
       defect. Absence of evidence must never mean "not a CDR".
    2. Lot evidence present but its total disagrees with the stored quantity ->
       one row, company-keyed, plus a note. Never reconcile by inventing shares.
    3. Lot evidence present and reconciling -> one row per non-zero lot, each with
       its own override and a pro-rata share of cost_basis. For a single-bucket
       position this is byte-identical to the company-keyed row, so uniform
       positions (the overwhelming majority) are untouched.

    Cost is split pro rata by quantity and the final leg absorbs the rounding
    residual, so sum(leg total_cost) == the original total_cost exactly. Total
    quantity is likewise preserved: the legs sum to the stored quantity.

    `derived_cdr_companies` is REQUIRED, not optional, and must be the company-keyed
    verdict for the same date. Defaulting it to None would make every holding look
    direct, which strips the cached "TOR" off every leg and re-creates the 10x
    overvaluation this function exists to fix. Every writer already holds the
    company-keyed truth, so there is no caller for whom omitting it is reasonable.
    """
    notes: list[str] = []
    if not holdings_state:
        return [], notes
    lots_by_company = lots_by_company or {}
    out: list[dict] = []

    for h in holdings_state:
        cid = h.get("company_id")
        try:
            qty = Decimal(str(h.get("quantity") or 0))
        except (TypeError, ValueError, ArithmeticError):
            out.append(dict(h))
            continue
        if qty <= 0:
            out.append(dict(h))
            continue

        cost = Decimal(str(h.get("total_cost") or 0))
        cached = h.get("exchange_override")
        company_is_cdr = bool(cid is not None and cid in derived_cdr_companies)

        lots = lots_by_company.get(int(cid)) if cid is not None else None
        legs, leg_notes = classify_lot_legs(
            quantity=qty,
            total_cost=cost,
            lots=lots,
            company_is_cdr=company_is_cdr,
            context=f"company {cid} ({h.get('symbol', '?')})",
        )
        notes.extend(leg_notes)
        for kind, leg_qty, leg_cost in legs:
            out.append(_leg_row(h, cached, kind, leg_qty, leg_cost))

    return out, notes


def _decimal_ratio(ratio: Any) -> Decimal:
    """Ratio as the decimal it was meant to be, never its binary expansion (I3)."""
    try:
        return Decimal(str(ratio))
    except (InvalidOperation, ValueError, TypeError):
        # An unparseable ratio is certainly not the structural constant; the
        # caller's WARNING is the correct, deterministic verdict.
        return Decimal("-1")


def trace_division(
    layer: str,
    company_id: int,
    price_in: float,
    ratio: float,
    price_out: float,
    *,
    account_id: int | None = None,
    price_source: str | None = None,
) -> None:
    """Emit one structured record of a CDR division at a decision point.

    Every layer that divides a price by a CDR ratio routes its trace through
    here so the fields are identical and the output is greppable across layers.
    Divergent CDR behaviour between layers is otherwise invisible: each layer
    looks locally correct while disagreeing with the others.

    WARNING-level when the applied ratio departs from the structural constant,
    because only the structural constant is legitimate. That case means a
    non-structural ratio reached pricing, which is a defect.
    """
    level = (
        logging.WARNING
        if _decimal_ratio(ratio) != CDR_RATIO_DECIMAL
        else logging.DEBUG
    )
    logger.log(
        level,
        "[CDR-DIVIDE] layer=%s company_id=%s account_id=%s ratio=%s "
        "price_in=%s price_out=%s source=%s",
        layer, company_id, account_id, ratio, price_in, price_out, price_source,
    )
