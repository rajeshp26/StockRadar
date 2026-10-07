"""Split-event reconciliation against the immutable account event stream.

Root cause this module fixes:
  price_ingestion_job._emit_split_events derived the affected account list from
  the CURRENT portfolio_holdings table, then latched splits.processed=True after
  emission. Any account that HELD the split company when the split happened but
  sold before the job ran (or before the latch flipped) was skipped forever:
  portfolio_holdings no longer mentioned the company, and the latch suppressed
  the retry. Account 7 / company 1117 (10:1 split on 2022-06-29) was the
  production casualty.

Design contract:
  - The source of truth is the portfolio_events stream - never current holdings
    and never the splits.processed latch (the reconciler ignores the latch
    entirely and fetches ALL split rows).
  - A split event "exists" when a portfolio_events row matches on the business
    fields (aggregate_id + data.company_id + data.report_date). Idempotency-key
    TEXT is never used for presence checks: account 7's historical event used a
    non-standard key (split_1117_2022-06-29_10_acct7) that a key-text lookup
    would have mis-read as a gap.
  - An account "held" company cid at split date rd when its earliest holding
    evidence date is None (unknown - treated conservatively as qualifying) or
    <= rd. Evidence = any non-split event referencing the company, either via
    top-level data.company_id or inside an initial_holding_set holdings[] list
    (nested company_id is invisible to a JSONB -> filter).
  - Emission is idempotent: EventStore.append_events_batch self-heals on
    duplicate keys. The processed latch is updated ONLY after a successful
    append and is a hint, never a gate.
  - Pure integrity helpers (holding_window_from_events, split_events_present,
    explains_spike) are shared with verify_snapshot_history.py so the verifier
    and the reconciler reason identically about the event stream.
"""
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from infrastructure.repositories.event_store import EventStore
from shared.split_utils import (
    extract_event_date,
    parse_split_date,
    parse_split_factor,
)

logger = logging.getLogger(__name__)

PAGE_SIZE = 1000

# Event types that establish a position from nothing. initial_holding_set records real
# opening history; position_state_checkpoint records a capture of current state. Both
# explain a position the account did not previously hold, so evidence queries must
# match both or a checkpoint-seeded account is misreported as unexplained.
POSITION_ANCHOR_EVENT_TYPES = ("initial_holding_set", "position_state_checkpoint")


def _account_id_from_aggregate(aggregate_id) -> int | None:
    """Parse an 'account_{id}' aggregate_id into the numeric id."""
    if not aggregate_id or not str(aggregate_id).startswith("account_"):
        return None
    try:
        return int(str(aggregate_id).split("_", 1)[1])
    except (TypeError, ValueError):
        return None


def _event_covers_company(event: dict, cid: int) -> bool:
    """True if the event references company cid, top-level or nested holdings[]."""
    data = event.get("data", {}) or {}
    try:
        if int(data.get("company_id") or -1) == cid:
            return True
    except (TypeError, ValueError):
        pass
    holdings = data.get("holdings")
    if isinstance(holdings, list):
        for h in holdings:
            if isinstance(h, dict):
                try:
                    if int(h.get("company_id") or -1) == cid:
                        return True
                except (TypeError, ValueError):
                    continue
    return False


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------
def fetch_all_splits(client, company_ids: list[int] | None = None) -> list[dict]:
    """Fetch ALL split rows (latched or not), paginated past the PostgREST cap.

    The processed latch is deliberately NOT filtered: past gaps were caused by
    latched splits, and reconciliation is latch-agnostic by design.
    """
    rows: list[dict] = []
    offset = 0
    while True:
        query = client.table("splits").select("company_id, report_date, split_factor")
        if company_ids:
            query = query.in_("company_id", company_ids)
        query = query.order("report_date")
        res = query.range(offset, offset + PAGE_SIZE - 1).execute()
        batch = res.data or []
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return rows


def fetch_existing_split_events(client, cid: int) -> list[dict]:
    """Fetch every split event stored for company cid (paged)."""
    rows: list[dict] = []
    offset = 0
    while True:
        res = (
            client.table("portfolio_events")
            .select("aggregate_id, event_type, data, created_at")
            .eq("event_type", "split")
            .eq("data->>company_id", str(cid))
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        batch = res.data or []
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return rows


def accounts_with_holding_evidence(client, cid: int) -> dict[int, date | None]:
    """{account_id: earliest_holding_evidence_date | None} for company cid.

    Evidence = any non-split event referencing the company. A split event does
    NOT establish a holding - using it as evidence would mask missing events
    for other splits of the same company.
    """
    best: dict[int, date | None] = {}

    def _absorb(ev: dict) -> None:
        if ev.get("event_type") == "split":
            return
        if not _event_covers_company(ev, cid):
            return
        aid = _account_id_from_aggregate(ev.get("aggregate_id"))
        if aid is None:
            return
        ev_date = extract_event_date(ev)
        prev = best.get(aid)
        if prev is None or (ev_date is not None and ev_date < prev):
            best[aid] = ev_date

    # 1. events with top-level data.company_id == cid (excludes splits)
    offset = 0
    while True:
        res = (
            client.table("portfolio_events")
            .select("aggregate_id, event_type, data, created_at")
            .eq("data->>company_id", str(cid))
            .neq("event_type", "split")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        batch = res.data or []
        for ev in batch:
            _absorb(ev)
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    # 2. position anchors (nested holdings[] company_id)
    offset = 0
    while True:
        res = (
            client.table("portfolio_events")
            .select("aggregate_id, event_type, data, created_at")
            .in_("event_type", list(POSITION_ANCHOR_EVENT_TYPES))
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        batch = res.data or []
        for ev in batch:
            _absorb(ev)
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    return best


# ---------------------------------------------------------------------------
# Gap detection
# ---------------------------------------------------------------------------
def split_event_present(
    existing_events: list[dict],
    account_id: int,
    cid: int,
    report_date: date,
) -> bool:
    """Field-match presence: aggregate + company + report_date. Never key text."""
    expected_agg = f"account_{account_id}"
    rd_iso = report_date.isoformat()
    for ev in existing_events:
        if ev.get("aggregate_id") != expected_agg:
            continue
        data = ev.get("data", {}) or {}
        try:
            if int(data.get("company_id") or -1) != cid:
                continue
            if parse_split_date(data.get("report_date")).isoformat() != rd_iso:
                continue
        except (TypeError, ValueError):
            continue
        return True
    return False


def find_missing_split_events(
    client,
    splits: list[dict],
    account_ids: list[int] | None = None,
    company_ids: list[int] | None = None,
    max_date: date | None = None,
) -> tuple[list[dict], int]:
    """Return (gaps, checked).

    gaps: one dict per (company, account) that should have a split event but
    does not. Keys: company_id, report_date, split_factor, account_id,
    evidence_date.

    checked: number of (company, qualifying-account) pairs considered.
    """
    gaps: list[dict] = []
    checked = 0
    account_filter = set(account_ids or [])
    company_filter = set(company_ids or [])
    existing_cache: dict[int, list[dict]] = {}
    evidence_cache: dict[int, dict[int, date | None]] = {}

    for split in splits:
        cid = split.get("company_id")
        if cid is None or (company_filter and cid not in company_filter):
            continue
        try:
            rd = parse_split_date(split["report_date"])
        except (KeyError, ValueError, TypeError):
            continue
        if max_date is not None and rd > max_date:
            continue
        factor = parse_split_factor(split.get("split_factor") or "")
        if factor <= 0 or factor == 1:
            continue

        if cid not in existing_cache:
            existing_cache[cid] = fetch_existing_split_events(client, cid)
        if cid not in evidence_cache:
            evidence_cache[cid] = accounts_with_holding_evidence(client, cid)

        evidence = evidence_cache[cid]
        for account_id, ev_date in sorted(evidence.items()):
            if account_filter and account_id not in account_filter:
                continue
            # Earliest involvement after the split date means the account was
            # not a holder at split time -> no event owed.
            if ev_date is not None and ev_date > rd:
                continue
            checked += 1
            if split_event_present(existing_cache[cid], account_id, cid, rd):
                continue
            gaps.append({
                "company_id": cid,
                "report_date": rd,
                "split_factor": split.get("split_factor"),
                "account_id": account_id,
                "evidence_date": ev_date,
            })

    gaps.sort(key=lambda g: (g["company_id"], g["report_date"], g["account_id"]))
    return gaps, checked


def build_split_event(gap: dict) -> dict[str, Any]:
    """Build an event row in the exact historical shape.

    split_factor is stored as a string number (e.g. "10.0") so the replay
    engine's _decimal(data.get("split_factor")) parses it - the raw "10:1"
    splice string would not.
    """
    cid = gap["company_id"]
    rd = gap["report_date"]
    account_id = gap["account_id"]
    factor = parse_split_factor(gap.get("split_factor") or "")
    return {
        "event_type": "split",
        "event_version": 1,
        "aggregate_id": f"account_{account_id}",
        "aggregate_type": "account",
        "data": {
            "company_id": cid,
            "split_factor": str(factor),
            "report_date": rd.isoformat(),
        },
        "metadata": {},
        "idempotency_key": f"split_{cid}_{rd.isoformat()}_{account_id}",
    }


# ---------------------------------------------------------------------------
# Reconcile entry point
# ---------------------------------------------------------------------------
@dataclass
class ReconcileReport:
    checked_splits: int = 0
    missing_events: int = 0
    emitted_events: int = 0
    companies_with_gaps: set[int] = field(default_factory=set)
    error: str | None = None


def reconcile_split_events(
    client,
    dry_run: bool = True,
    account_ids: list[int] | None = None,
    company_ids: list[int] | None = None,
    max_date: date | None = None,
) -> ReconcileReport:
    """Reconcile the split-event log against the splits table.

    dry_run=True (default) only discovers gaps. dry_run=False appends missing
    events via EventStore.append_events_batch (idempotent self-heal on
    duplicate keys) and, only after a successful append, updates the processed
    latch as a hint. A non-duplicate failure leaves the latch untouched so the
    gap is re-detected on the next run.
    """
    report = ReconcileReport()
    try:
        splits = fetch_all_splits(client, company_ids=company_ids)
    except Exception as e:
        report.error = f"failed to fetch splits: {e}"
        return report
    if not splits:
        return report

    gaps, checked = find_missing_split_events(
        client,
        splits,
        account_ids=account_ids,
        company_ids=company_ids,
        max_date=max_date,
    )
    report.checked_splits = checked
    report.missing_events = len(gaps)
    report.companies_with_gaps = {g["company_id"] for g in gaps}
    if dry_run or not gaps:
        return report

    events = [build_split_event(g) for g in gaps]
    try:
        EventStore(client=client).append_events_batch(events)
    except Exception as e:
        if "duplicate key" in str(e).lower():
            report.error = (
                "duplicate-key during batch append (self-heal did not resolve): "
                f"{e}"
            )
        else:
            report.error = f"failed to append split events: {e}"
        return report

    report.emitted_events = len(events)
    for cid in sorted(report.companies_with_gaps):
        try:
            client.table("splits").update({"processed": True}).eq("company_id", cid).execute()
        except Exception as e:
            logger.warning("[SPLIT-SYNC] failed to mark company %d processed: %s", cid, e)
    return report


# ---------------------------------------------------------------------------
# Pure integrity helpers (shared with verify_snapshot_history.py)
# ---------------------------------------------------------------------------
def holding_window_from_events(events: list[dict], cid: int) -> tuple[date, date] | None:
    """Earliest..latest holding evidence for cid in an account's event stream.

    Split events are EXCLUDED as evidence: a split event does not establish a
    holding, and using it would mask missing events for other splits.
    Returns None when no non-split evidence references the company.
    """
    dates: list[date] = []
    for ev in events:
        if ev.get("event_type") == "split":
            continue
        if not _event_covers_company(ev, cid):
            continue
        d = extract_event_date(ev)
        if d is not None:
            dates.append(d)
    if not dates:
        return None
    return min(dates), max(dates)


def split_events_present(events: list[dict], cid: int, report_date: date) -> bool:
    """Field-match presence of a split event for (cid, report_date)."""
    rd_iso = report_date.isoformat()
    for ev in events:
        if ev.get("event_type") != "split":
            continue
        data = ev.get("data", {}) or {}
        try:
            if int(data.get("company_id") or -1) != cid:
                continue
            if parse_split_date(data.get("report_date")).isoformat() != rd_iso:
                continue
        except (TypeError, ValueError):
            continue
        return True
    return False


def explains_spike(
    events: list[dict],
    spike_date: date,
    delta: float,
    tol_days: int = 3,
    materiality: float = 0.10,
) -> bool:
    """Does the account's event stream explain a value spike of |delta|?

    Rules (mirrors how the production merge nets deposits and how value moves):
      - split events NEVER explain (they change quantity, not value)
      - position anchors explain (initial_holding_set or position_state_checkpoint:
        a position established from nothing)
      - InternalSecurityTransfer explains when its value impact
        (|quantity * unit_price|) is >= materiality * |delta|
      - Trade and cash-only types are excluded: deposits are already netted by
        check_snapshot_spike's deposits_delta, and a large trade is a price
        move, not a value transfer into the account.
    """
    try:
        abs_delta = abs(float(delta or 0))
    except (TypeError, ValueError):
        return False
    if abs_delta <= 0:
        return False
    threshold = materiality * abs_delta
    for ev in events:
        ev_type = ev.get("event_type")
        if ev_type == "split":
            continue
        data = ev.get("data", {}) or {}
        ev_date = extract_event_date(ev)
        if ev_date is None or abs((ev_date - spike_date).days) > tol_days:
            continue
        if ev_type in POSITION_ANCHOR_EVENT_TYPES:
            return True
        if (
            ev_type == "transaction_imported"
            and data.get("activity_type") == "InternalSecurityTransfer"
        ):
            try:
                impact = abs(
                    float(data.get("quantity") or 0) * float(data.get("unit_price") or 0)
                )
            except (TypeError, ValueError):
                impact = 0.0
            if impact >= threshold:
                return True
    return False
