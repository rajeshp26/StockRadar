"""Tests for shared.checkpoint_provenance.

The persisted-row check is the backstop for EventStore's write-time guard, so
these tests assert both directions: real history is not falsely flagged, and a
backdated projection import IS caught.
"""

from datetime import date, datetime

from shared.checkpoint_provenance import (
    backdated_checkpoint_findings,
    as_date,
    validate_checkpoint_provenance,
)


def event(event_type, effective_date, created_at, source="portfolio_holdings", event_id="evt-1"):
    return {
        "id": event_id,
        "event_type": event_type,
        "metadata": {"source": source} if source is not None else {},
        "data": {"effective_date": effective_date},
        "created_at": created_at,
    }


class TestAsDate:
    def test_parses_iso_string(self):
        assert as_date("2026-07-07T00:00:00+00:00") == date(2026, 7, 7)

    def test_accepts_date_and_datetime(self):
        assert as_date(date(2026, 7, 7)) == date(2026, 7, 7)
        assert as_date(datetime(2026, 7, 7, 13, 30)) == date(2026, 7, 7)

    def test_unparseable_is_none(self):
        assert as_date(None) is None
        assert as_date("not-a-date") is None


class TestValidHistoryIsNotFlagged:
    def test_migration_011_reclassified_row(self):
        """011 set effective_date = created_at::date, so equality must pass."""
        findings = validate_checkpoint_provenance(
            10, [event("position_state_checkpoint", "2026-09-25", "2026-09-25T12:00:00Z")]
        )
        assert findings == []

    def test_genuine_historical_initial_holding_set(self):
        """Historical truth is entitled to an old date and no projection marker."""
        findings = validate_checkpoint_provenance(
            7, [event("initial_holding_set", "2020-01-01", "2026-09-25T12:00:00Z", source=None)]
        )
        assert findings == []

    def test_checkpoint_effective_after_creation(self):
        findings = validate_checkpoint_provenance(
            10, [event("position_state_checkpoint", "2026-10-01", "2026-09-25T12:00:00Z")]
        )
        assert findings == []

    def test_unrelated_event_type_untouched(self):
        findings = validate_checkpoint_provenance(
            7, [event("Trade", "2021-05-05", "2021-05-06T00:00:00Z", source="user")]
        )
        assert findings == []


class TestBackdatingIsDetected:
    def test_backdated_checkpoint_is_caught(self):
        findings = validate_checkpoint_provenance(
            10, [event("position_state_checkpoint", "2020-01-01", "2026-09-25T12:00:00Z")]
        )
        assert len(findings) == 1
        assert findings[0]["class"] == "CHECKPOINT_BACKDATED"
        assert "2020-01-01" in findings[0]["detail"]

    def test_checkpoint_without_projection_marker_is_caught(self):
        findings = validate_checkpoint_provenance(
            10, [event("position_state_checkpoint", "2026-09-25", "2026-09-25T12:00:00Z", source="user")]
        )
        assert [f["class"] for f in findings] == ["CHECKPOINT_UNSOURCED"]

    def test_projection_sourced_non_checkpoint_backdating_is_caught(self):
        """Mirrors the write-time guard predicate, which covers any projected event."""
        findings = validate_checkpoint_provenance(
            7, [event("initial_holding_set", "2020-01-01", "2026-09-25T12:00:00Z")]
        )
        assert [f["class"] for f in findings] == ["CHECKPOINT_BACKDATED"]

    def test_exact_boundary_is_not_a_violation(self):
        """effective == created must pass; only strictly-earlier is a defect."""
        findings = validate_checkpoint_provenance(
            10, [event("position_state_checkpoint", "2026-09-25", "2026-09-25T23:59:59Z")]
        )
        assert findings == []


class TestMissingDataIsNotAFalsePositive:
    def test_absent_dates_are_skipped(self):
        row = {"id": "evt-2", "event_type": "position_state_checkpoint",
               "metadata": {"source": "portfolio_holdings"}, "data": {}, "created_at": None}
        assert validate_checkpoint_provenance(10, [row]) == []


class TestBackdatedCheckpointFindingsFilter:
    def test_filter_returns_only_hard_failures(self):
        events = [
            event("position_state_checkpoint", "2020-01-01", "2026-09-25T12:00:00Z", event_id="bad"),
            event("position_state_checkpoint", "2026-09-25", "2026-09-25T12:00:00Z", event_id="good"),
        ]
        all_findings = validate_checkpoint_provenance(10, events)
        filtered = backdated_checkpoint_findings(10, events)
        assert len(all_findings) == 1
        assert len(filtered) == 1
        assert filtered[0]["class"] == "CHECKPOINT_BACKDATED"
