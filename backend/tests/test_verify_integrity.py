"""Tests for the corporate-action integrity logic in verify_snapshot_history.py.

Pins the checks added during the split-integrity closure (todo #7/#8):
  - account_spikes classifies a stored-row spike as baseline when the account's
    event stream explains it (InternalSecurityTransfer / initial_holding_set
    within +/-3 days, impact >= 10% of the unexplained delta; split events and
    plain trades NEVER explain)
  - split_price_gaps emits SPLIT_PRICE_GAP only for splits whose report_date
    falls inside a test account's holding window and which have no price_history
    row within [rd, rd+40d] (40d sized to the monthly-close feed cadence),
    deduped by (company_id, report_date)
  - replicate_merge carries un-suppressed spikes as {"date", "delta"} dicts so
    the merged-loop classification can consume them
"""
import os
import sys
from datetime import date
from unittest.mock import MagicMock

# verify_snapshot_history imports sibling scripts as top-level modules
# (e.g. `import rebuild_account_snapshots`) via repo-root-relative sys.path
# inserts; under pytest (CWD = backend/) those resolve only if we add the
# absolute backend/scripts dir ourselves.
_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for _p in (_BACKEND, os.path.join(_BACKEND, "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from scripts.verify_snapshot_history import (
    account_spikes,
    replicate_merge,
    split_price_gaps,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _snap(account_id, d, total, nd=0.0, flag="OK"):
    return {
        "account_id": account_id,
        "snapshot_date": d,
        "total_value": total,
        "net_deposits": nd,
        "cost_basis": 0.0,
        "cash_balance": 0.0,
        "data_quality_flag": flag,
        "holdings_json": [],
    }


def _transfer_event(tdate, quantity, unit_price, cid=1117):
    return {
        "event_type": "transaction_imported",
        "aggregate_id": "account_7",
        "aggregate_type": "account",
        "data": {
            "account_id": 7,
            "company_id": cid,
            "activity_type": "InternalSecurityTransfer",
            "quantity": quantity,
            "unit_price": unit_price,
            "transaction_date": tdate,
        },
        "created_at": f"{tdate}T00:00:00+00:00",
    }


def _trade_event(tdate, cid=1117):
    return {
        "event_type": "transaction_imported",
        "aggregate_id": "account_7",
        "aggregate_type": "account",
        "data": {
            "account_id": 7,
            "company_id": cid,
            "activity_type": "Trade",
            "quantity": 10,
            "unit_price": 100.0,
            "net_cash_amount": -1000.0,
            "transaction_date": tdate,
        },
        "created_at": f"{tdate}T00:00:00+00:00",
    }


def _ihs_event(cids, created):
    return {
        "event_type": "initial_holding_set",
        "aggregate_id": "account_7",
        "aggregate_type": "account",
        "data": {
            "cash_balance": 0,
            "net_deposits": 0,
            "holdings": [
                {"company_id": cid, "quantity": 10, "average_cost": 100.0, "total_cost": 1000.0}
                for cid in cids
            ],
        },
        "created_at": created,
    }


def _split_event(cid, rd, factor="10.0"):
    return {
        "event_type": "split",
        "aggregate_id": "account_7",
        "aggregate_type": "account",
        "data": {"company_id": cid, "split_factor": factor, "report_date": rd},
        "created_at": f"{rd}T00:00:00+00:00",
    }


def _price_client(pages):
    """FIFO price_history client: each .execute() pops the next page.

    split_price_gaps fires two queries per covered split (in-window, then
    next-price) on the same builder chain, so page order must match call order.
    """
    client = MagicMock()
    t = MagicMock()
    t.select.return_value = t
    t.eq.return_value = t
    t.gte.return_value = t
    t.lte.return_value = t
    t.gt.return_value = t
    t.order.return_value = t
    t.limit.return_value = t
    t.execute.side_effect = (
        lambda _pages=pages: MagicMock(data=_pages.pop(0) if _pages else [])
    )
    client.table.return_value = t
    return client


# ---------------------------------------------------------------------------
# account_spikes: spike classification via event stream
# ---------------------------------------------------------------------------


class TestAccountSpikesClassification:
    def test_unexplained_real_spike_is_failure(self):
        rows = [
            _snap(7, "2026-01-01", 1000.0),
            _snap(7, "2026-01-02", 20000.0),
        ]
        spikes, baseline = account_spikes(rows, 0.20, events=[])
        assert len(spikes) == 1
        assert spikes[0]["date"] == "2026-01-02"
        assert baseline == []

    def test_events_none_keeps_spikes(self):
        rows = [
            _snap(7, "2026-01-01", 1000.0),
            _snap(7, "2026-01-02", 20000.0),
        ]
        spikes, baseline = account_spikes(rows, 0.20, events=None)
        assert len(spikes) == 1
        assert baseline == []

    def test_internal_security_transfer_explains(self):
        rows = [
            _snap(7, "2026-01-01", 1000.0),
            _snap(7, "2026-01-02", 20000.0),
        ]
        # delta 19000; transfer impact 1000 * 120 = 120000 >= 10% * 19000
        events = [_transfer_event("2026-01-02", quantity=1000, unit_price=120.0)]
        spikes, baseline = account_spikes(rows, 0.20, events=events)
        assert spikes == []
        assert len(baseline) == 1
        assert baseline[0]["date"] == "2026-01-02"
        assert baseline[0].get("explained") is True

    def test_transfer_below_materiality_not_explained(self):
        rows = [
            _snap(7, "2026-01-01", 1000.0),
            _snap(7, "2026-01-02", 20000.0),
        ]
        # impact 10 * 120 = 1200 < 1900 (10% of 19000) -> spike stays
        events = [_transfer_event("2026-01-02", quantity=10, unit_price=120.0)]
        spikes, baseline = account_spikes(rows, 0.20, events=events)
        assert len(spikes) == 1
        assert baseline == []

    def test_transfer_outside_tolerance_window_not_explained(self):
        rows = [
            _snap(7, "2026-01-01", 1000.0),
            _snap(7, "2026-01-02", 20000.0),
        ]
        # transfer 10 days before the spike -> outside +/-3 days
        events = [_transfer_event("2025-12-23", quantity=1000, unit_price=120.0)]
        spikes, baseline = account_spikes(rows, 0.20, events=events)
        assert len(spikes) == 1
        assert baseline == []

    def test_initial_holding_set_explains(self):
        rows = [
            _snap(7, "2026-01-01", 1000.0),
            _snap(7, "2026-01-02", 20000.0),
        ]
        events = [_ihs_event([1117], "2026-01-01T00:00:00+00:00")]
        spikes, baseline = account_spikes(rows, 0.20, events=events)
        assert spikes == []
        assert len(baseline) == 1
        assert baseline[0].get("explained") is True

    def test_split_event_never_explains(self):
        rows = [
            _snap(7, "2026-01-01", 1000.0),
            _snap(7, "2026-01-02", 20000.0),
        ]
        events = [_split_event(1117, "2026-01-02")]
        spikes, baseline = account_spikes(rows, 0.20, events=events)
        assert len(spikes) == 1
        assert baseline == []

    def test_plain_trade_never_explains(self):
        rows = [
            _snap(7, "2026-01-01", 1000.0),
            _snap(7, "2026-01-02", 20000.0),
        ]
        events = [_trade_event("2026-01-02")]
        spikes, baseline = account_spikes(rows, 0.20, events=events)
        assert len(spikes) == 1
        assert baseline == []

    def test_incomplete_pair_is_baseline_without_explained(self):
        rows = [
            _snap(7, "2026-01-01", 1000.0),
            _snap(7, "2026-01-02", 20000.0, flag="INCOMPLETE"),
        ]
        spikes, baseline = account_spikes(rows, 0.20, events=[])
        assert spikes == []
        assert len(baseline) == 1
        assert baseline[0].get("explained") is not True


# ---------------------------------------------------------------------------
# split_price_gaps: SPLIT_PRICE_GAP detection
# ---------------------------------------------------------------------------


class TestSplitPriceGaps:
    SPLIT = {"company_id": 1117, "report_date": "2022-06-29", "split_factor": "10:1"}

    def _covered_events(self, lo="2020-01-01", hi="2023-01-01"):
        # holding evidence window [lo, hi] covering rd 2022-06-29
        return {
            7: [
                _ihs_event([1117], f"{lo}T00:00:00+00:00"),
                _trade_event(hi),
            ]
        }

    def test_covered_split_with_price_in_window_no_gap(self):
        client = _price_client([
            [{"price_date": "2022-06-30"}],  # in-window hit
        ])
        gaps = split_price_gaps(
            client, [self.SPLIT], self._covered_events(), [7], date(2026, 1, 1)
        )
        assert gaps == []

    def test_covered_split_missing_price_reports_gap_with_next_price(self):
        # 40d window from rd 2022-06-29 ends 2022-08-08; a genuine void has its
        # next price outside it. Mirrors cid=3107 (rd 2023-06-26, next 2026-07-17).
        client = _price_client([
            [],                                     # in-window miss
            [{"price_date": "2022-09-30"}],          # next price beyond hi
        ])
        gaps = split_price_gaps(
            client, [self.SPLIT], self._covered_events(), [7], date(2026, 1, 1)
        )
        assert len(gaps) == 1
        g = gaps[0]
        assert g["class"] == "SPLIT_PRICE_GAP"
        assert g["date"] == "2022-06-29"
        assert g["price_date"] == "2022-09-30"

    def test_monthly_close_cadence_next_close_within_window_no_gap(self):
        # Regression for the 4d-window false positives: the feed's month-end
        # closes are 28-33d apart, so a mid-month split's next close (~30d
        # later) must fall inside the 40d window and fire no gap.
        client = _price_client([
            [{"price_date": "2022-07-29"}],          # next monthly close, rd+30d
        ])
        gaps = split_price_gaps(
            client, [self.SPLIT], self._covered_events(), [7], date(2026, 1, 1)
        )
        assert gaps == []

    def test_no_holding_evidence_not_checked(self):
        client = _price_client([])
        gaps = split_price_gaps(
            client, [self.SPLIT], {}, [7], date(2026, 1, 1)
        )
        assert gaps == []

    def test_split_outside_holding_window_not_checked(self):
        # window ends 2021-01-01, split is 2022-06-29 -> not covered
        client = _price_client([])
        events = {
            7: [
                _ihs_event([1117], "2019-01-01T00:00:00+00:00"),
                _trade_event("2021-01-01"),
            ]
        }
        gaps = split_price_gaps(client, [self.SPLIT], events, [7], date(2026, 1, 1))
        assert gaps == []

    def test_dedup_by_company_and_report_date(self):
        client = _price_client([
            [],                                     # in-window miss (first row)
            [{"price_date": "2022-09-30"}],          # next price beyond hi (first row)
            # second identical row must be skipped by the seen set
        ])
        splits = [dict(self.SPLIT), dict(self.SPLIT)]
        gaps = split_price_gaps(
            client, splits, self._covered_events(), [7], date(2026, 1, 1)
        )
        assert len(gaps) == 1

    def test_split_past_max_date_skipped(self):
        client = _price_client([])
        gaps = split_price_gaps(
            client, [self.SPLIT], self._covered_events(), [7], date(2022, 1, 1)
        )
        assert gaps == []

    def test_missing_company_id_skipped(self):
        client = _price_client([])
        gaps = split_price_gaps(
            client, [{"report_date": "2022-06-29"}], self._covered_events(), [7],
            date(2026, 1, 1),
        )
        assert gaps == []


# ---------------------------------------------------------------------------
# replicate_merge: un-suppressed spike shape
# ---------------------------------------------------------------------------


class TestReplicateMergeUnsuppressedSpikes:
    def test_middle_spike_carries_date_and_delta(self):
        raw = [
            _snap(7, "2026-01-01", 1000.0),
            _snap(7, "2026-01-02", 50000.0),
            _snap(7, "2026-01-03", 50000.0),
        ]
        merged, meta = replicate_merge(raw, threshold=0.20)
        assert meta["un_suppressed_spikes"] == [
            {"date": "2026-01-02", "delta": 49000.0}
        ]

    def test_locf_spike_is_suppressed_not_unsuppressed(self):
        # account 8 spikes on d2; account 7 has no d2 row -> LOCF spike must be
        # suppressed, never surfaced as an un-suppressed (user-visible) spike.
        raw = [
            _snap(7, "2026-01-01", 1000.0),
            _snap(7, "2026-01-03", 1000.0),
            _snap(8, "2026-01-01", 200.0),
            _snap(8, "2026-01-02", 50000.0),
            _snap(8, "2026-01-03", 200.0),
        ]
        merged, meta = replicate_merge(raw, threshold=0.20)
        assert "2026-01-02" in meta["suppressed_dates"]
        assert meta["un_suppressed_spikes"] == []