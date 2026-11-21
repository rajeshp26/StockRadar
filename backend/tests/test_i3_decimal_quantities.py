"""I3 -- float arithmetic on financial quantities must never decide a reconciliation.

The three recorded artifacts are real share quantities from the worker log:

    9.99999999999999900
    0.333333333333333300
    0.000056249999999999943750000000

They are binary-float representations of 10, 1/3 and 0.00005625 shares. A
reconciliation that compares such values as floats, with a tolerance wide enough
to absorb the noise, cannot distinguish "correct" from "position dropped".
These tests pin the Decimal boundary that makes that check falsifiable.
"""

import logging
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from shared.cdr_utils import CDR_RATIO, classify_lot_legs, trace_division

TINY = Decimal("0.00005625")           # account 9 / company 3112, live
THIRD = Decimal("0.33333333")          # account 9 / company 3146, live
TEN = Decimal("10.00000000")           # 23 live positions


class TestUnfalsifiableFloatTolerance:
    """The defect, reproduced without a database so the verdict is deterministic."""

    def test_float_tolerance_swallows_a_real_tiny_position(self):
        # This is exactly what the old reconcile_holdings did: float subtraction
        # against a 0.0001 tolerance. A missing 0.00005625-share holding PASSES.
        old_tolerance = 0.0001
        stored_tiny = float(TINY)
        diff = abs(stored_tiny - 0.0)
        assert diff <= old_tolerance  # the check calls this "equal"

    def test_decimal_at_storage_scale_catches_the_same_position(self):
        # The fix: Decimal quantities and a tolerance at the numeric(20,8) scale.
        tol = Decimal("0.00000001")
        diff = abs(TINY - Decimal(0))
        assert diff > tol  # now the check correctly reports a mismatch

    def test_three_artifacts_convert_to_their_intended_decimals(self):
        # Decimal(str(x)) preserves the decimal the producer meant; Decimal(x)
        # would carry the binary expansion and re-introduce the noise.
        assert Decimal(str(float(TEN))) == TEN
        assert Decimal(str(1 / 3)) == Decimal("0.3333333333333333")
        assert Decimal(str(float(TINY))) == TINY


class TestReconcileHoldings:
    """The concrete reconciliation check with the unfalsifiable tolerance."""

    @staticmethod
    def _patch_repos(snap_holdings, current_holdings):
        snap_repo = MagicMock()
        snap_repo.get_latest_snapshot.return_value = {
            "snapshot_date": "2026-11-17",  # fresh, so no "too old" short-circuit
            "holdings_json": snap_holdings,
        }
        port_repo = MagicMock()
        port_repo.get_holdings.return_value = current_holdings
        return (
            patch("scripts.reconcile_holdings.PortfolioSnapshotsRepository", return_value=snap_repo),
            patch("scripts.reconcile_holdings.PortfolioRepository", return_value=port_repo),
            patch("scripts.reconcile_holdings.now_utc", return_value=MagicMock(
                date=MagicMock(return_value=date(2026, 11, 17))
            )),
        )

    def test_missing_tiny_position_fails_reconciliation(self):
        from scripts.reconcile_holdings import reconcile_holdings

        snaps = [{"company_id": 3112, "symbol": "TINY", "quantity": str(TINY)}]
        curr = []  # the position was silently dropped
        patches = self._patch_repos(snaps, curr)
        with patches[0], patches[1], patches[2]:
            passes, issues = reconcile_holdings(9)

        assert passes is False
        assert any("MISSING in holdings" in i and "3112" in i for i in issues)

    def test_exact_positions_pass_reconciliation(self):
        from scripts.reconcile_holdings import reconcile_holdings

        snaps = [
            {"company_id": 3112, "symbol": "TINY", "quantity": str(TINY)},
            {"company_id": 3146, "symbol": "THIRD", "quantity": str(THIRD)},
            {"company_id": 10, "symbol": "TEN", "quantity": str(TEN)},
        ]
        curr = [
            {"company_id": 3112, "symbol": "TINY", "quantity": float(TINY)},
            {"company_id": 3146, "symbol": "THIRD", "quantity": float(THIRD)},
            {"company_id": 10, "symbol": "TEN", "quantity": float(TEN)},
        ]
        patches = self._patch_repos(snaps, curr)
        with patches[0], patches[1], patches[2]:
            passes, issues = reconcile_holdings(9)

        assert passes is True
        assert issues == []

    def test_float_quantity_tolerance_argument_is_coerced_to_decimal(self):
        from scripts.reconcile_holdings import _decimal

        assert _decimal(0.0001) == Decimal("0.0001")
        assert _decimal("0.00000001") == Decimal("0.00000001")
        assert _decimal(Decimal("1e-8")) == Decimal("1e-8")


class TestLotReconciliationBoundary:
    """The I2-family lot check never compares a float against its tolerance."""

    def test_float_quantities_are_coerced_before_tolerance_comparison(self):
        # Feeds the float artifacts straight into the pure reconciliation. The
        # boundary must normalize them so the note text is deterministic.
        legs, notes = classify_lot_legs(
            quantity=float(TEN),
            total_cost=100.0,
            lots={"direct": float(TEN) - 0.0000001},
            company_is_cdr=False,
            context="company 10",
        )
        assert notes == []  # float noise stays within the tolerance
        # A reconciling lot supplies the leg quantity, normalized to Decimal at
        # the boundary (not the raw float 9.9999999 that came in).
        assert legs[0][1] == Decimal(str(float(TEN) - 0.0000001))

    def test_mismatched_float_lot_produces_deterministic_note(self):
        _legs, notes = classify_lot_legs(
            quantity=1 / 3,
            total_cost=10.0,
            lots={"direct": TEN},
            company_is_cdr=False,
            context="company 3146",
        )
        assert len(notes) == 1
        assert "lot replay totals 10" in notes[0]
        assert "0.3333333333333333" in notes[0]
        # No binary expansion of 10/1/3 may leak into the message.
        assert "9.999999999999998" not in notes[0]
        assert "0.33333333333333331482" not in notes[0]


class TestDecimalRatioTrace:
    def test_structural_ratio_is_debug_even_as_float(self, caplog):
        with caplog.at_level(logging.DEBUG, logger="stockerpro.cdr"):
            trace_division("test", 1, 100.0, CDR_RATIO, 10.0)
        assert any(r.levelno == logging.DEBUG for r in caplog.records)

    def test_float_noised_ratio_warns_deterministically(self, caplog):
        with caplog.at_level(logging.DEBUG, logger="stockerpro.cdr"):
            trace_division("test", 1, 100.0, 9.999999999999999, 10.0)
        assert any(r.levelno == logging.WARNING for r in caplog.records)
