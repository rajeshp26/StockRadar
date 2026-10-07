"""Checkpoint provenance rules for the persisted event log.

The write-time guard in EventStore._assert_state_import_not_backdated only
protects rows appended from now on; it cannot see rows already stored. This
module re-asserts the same predicate against persisted rows so a backdated
projection import cannot survive in the log unnoticed.

Two distinct claims are kept apart on purpose:

  initial_holding_set
      A HISTORICAL claim ("on this date the account held X"). Entitled to an
      old date, and must NOT be caught by the backdating rule.

  position_state_checkpoint
      A CAPTURE ("as of this instant the account held X") read out of a live
      projection, so its effective date IS the capture date. Backdating it
      re-applies corporate actions to quantities that already include them.

Row shape (see EventStore.append_event): the effective date lives at
data.effective_date and the provenance marker at metadata.source. There is no
top-level event_date/captured_on column, so the capture instant is the row's
own created_at.
"""
from datetime import date, datetime

PROJECTION_IMPORT_SOURCE = "portfolio_holdings"
CHECKPOINT_EVENT_TYPE = "position_state_checkpoint"
HISTORICAL_EVENT_TYPE = "initial_holding_set"


def as_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def validate_checkpoint_provenance(account_id, events):
    """Return findings for checkpoint events that are unsourced or backdated.

    A position_state_checkpoint must carry the projection-import marker, and no
    projection-sourced event may carry an effective_date earlier than its own row
    creation date. Historical initial_holding_set events are never backdating
    failures; they are returned separately so a caller can still surface them.
    """
    findings = []
    for e in events:
        event_type = e.get("event_type")
        metadata = e.get("metadata") or {}
        source = metadata.get("source")
        is_checkpoint = event_type == CHECKPOINT_EVENT_TYPE
        is_projection_sourced = source == PROJECTION_IMPORT_SOURCE
        event_id = e.get("id")

        if is_checkpoint and not is_projection_sourced:
            findings.append({
                "account": account_id,
                "date": str(e.get("created_at") or "-")[:10],
                "class": "CHECKPOINT_UNSOURCED",
                "detail": (
                    f"event {event_id} type={event_type} source={source!r} is a "
                    "checkpoint without the projection-import marker"
                ),
            })

        if not (is_checkpoint or is_projection_sourced):
            continue

        effective = as_date((e.get("data") or {}).get("effective_date"))
        captured = as_date(e.get("created_at"))
        if effective is None or captured is None:
            continue
        if effective < captured:
            findings.append({
                "account": account_id,
                "date": effective.isoformat(),
                "class": "CHECKPOINT_BACKDATED",
                "detail": (
                    f"event {event_id} type={event_type} source={source!r} effective "
                    f"{effective.isoformat()} predates its own row creation date "
                    f"{captured.isoformat()}"
                ),
            })
    return findings


def backdated_checkpoint_findings(account_id, events):
    """Only the hard failures: mislabelled or backdated checkpoint rows."""
    return [f for f in validate_checkpoint_provenance(account_id, events)
            if f["class"] in ("CHECKPOINT_UNSOURCED", "CHECKPOINT_BACKDATED")]
