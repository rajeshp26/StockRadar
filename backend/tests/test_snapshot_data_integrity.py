"""
End-to-end data integrity tests for portfolio_snapshots.

Connects to the real database (via `from database import supabase`) and verifies
data quality invariants that should always hold.

Run with:
    RUN_INTEGRATION_TESTS=1 python -m pytest tests/test_snapshot_data_integrity.py -v

These tests are READ-ONLY: they never write or delete rows.
"""

import os
import sys
from datetime import date, datetime
from typing import Any

# Ensure backend/ is on the path so database module can be found
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Override fake test env vars set by conftest.py with real values from .env
# (conftest sets SUPABASE_URL=http://test.db.local which blocks real DB access)
from dotenv import load_dotenv

_backend_dir = os.path.join(os.path.dirname(__file__), "..")
load_dotenv(os.path.join(_backend_dir, ".env"), override=True)

import pytest

from database import supabase
from shared.snapshot_builder import check_snapshot_spike

pytestmark = [
    pytest.mark.integration,
    pytest.mark.data_integrity,
    pytest.mark.skipif(
        not os.environ.get("RUN_INTEGRATION_TESTS"),
        reason="Set RUN_INTEGRATION_TESTS=1 to run against real Supabase",
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date(d) -> date:
    if isinstance(d, date):
        return d
    if isinstance(d, datetime):
        return d.date()
    return date.fromisoformat(d)


def _fetch_all_snapshots() -> list[dict[str, Any]]:
    PAGE_SIZE = 1000
    all_data: list[dict[str, Any]] = []
    offset = 0
    while True:
        res = (
            supabase.table("portfolio_snapshots")
            .select(
                "account_id, snapshot_date, total_value, cost_basis, "
                "cash_balance, net_deposits, job_id, data_quality_flag, "
                "holdings_market_value"
            )
            .order("account_id", desc=False)
            .order("snapshot_date", desc=False)
            .order("id", desc=False)
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        chunk = res.data or []
        if not chunk:
            break
        all_data.extend(chunk)
        if len(chunk) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return all_data


def _fetch_active_accounts() -> list[dict[str, Any]]:
    res = (
        supabase.table("portfolio_accounts")
        .select("account_id, account_name, is_active")
        .eq("is_active", True)
        .execute()
    )
    return res.data or []


def _group_by_account(snapshots: list[dict]) -> dict[int, list[dict]]:
    by_account: dict[int, list[dict]] = {}
    for s in snapshots:
        aid = s["account_id"]
        by_account.setdefault(aid, []).append(s)
    return by_account


# ---------------------------------------------------------------------------
# 1. No NULL job_ids
# ---------------------------------------------------------------------------
class TestNoNullJobIds:
    def test_all_snapshots_have_non_empty_job_id(self):
        snapshots = _fetch_all_snapshots()
        if not snapshots:
            pytest.skip("No snapshots in database")

        violations = [
            s for s in snapshots
            if not s.get("job_id") or str(s["job_id"]).strip() == ""
        ]
        print(f"\n[CHECK] No NULL/empty job_ids: {len(snapshots)} total, {len(violations)} violations")

        assert not violations, (
            f"{len(violations)} snapshot(s) have NULL or empty job_id. "
            f"First violations: {[(v['account_id'], v['snapshot_date']) for v in violations[:5]]}"
        )


# ---------------------------------------------------------------------------
# 2. No spikes in gap-filled data
# ---------------------------------------------------------------------------
class TestNoSpikesInGapFilledData:
    def test_no_unexplained_spikes_per_account(self):
        snapshots = _fetch_all_snapshots()
        if not snapshots:
            pytest.skip("No snapshots in database")

        by_account = _group_by_account(snapshots)
        all_spikes: list[dict] = []

        for aid, snaps in by_account.items():
            if len(snaps) < 2:
                continue
            # Exclude the latest snapshot per account — the daily job writes real
            # data after gap-filling creates LOCF snapshots. The read-path LOCF
            # merge suppresses the resulting spike at query time.
            for i in range(1, len(snaps) - 1):
                prev = snaps[i - 1]
                curr = snaps[i]
                spike = check_snapshot_spike(prev, curr, threshold=0.20)
                if spike is not None:
                    spike["account_id"] = aid
                    all_spikes.append(spike)

        print(f"\n[CHECK] No spikes without deposit/withdrawal: {len(all_spikes)} spike(s) detected")

        for spike in all_spikes:
            print(
                f"  SPIKE: account={spike['account_id']} "
                f"{spike['previous_date']} ${spike['previous_total']:,.2f} -> "
                f"{spike['current_date']} ${spike['current_total']:,.2f} "
                f"({spike['change_pct']:.1f}%)"
            )

        assert not all_spikes, (
            f"{len(all_spikes)} unexplained spike(s) detected. "
            f"See printed details above."
        )


# ---------------------------------------------------------------------------
# 3. No stale step9 data
# ---------------------------------------------------------------------------
class TestNoStaleStep9Data:
    def test_no_unknown_job_ids(self):
        snapshots = _fetch_all_snapshots()
        if not snapshots:
            pytest.skip("No snapshots in database")

        violations = [
            s for s in snapshots
            if str(s.get("job_id", "")).lower() == "unknown"
        ]
        print(f"\n[CHECK] No 'unknown' job_ids: {len(snapshots)} total, {len(violations)} violations")

        assert not violations, (
            f"{len(violations)} snapshot(s) have job_id='unknown' (stale step9 data). "
            f"First violations: {[(v['account_id'], v['snapshot_date']) for v in violations[:5]]}"
        )


# ---------------------------------------------------------------------------
# 4. All active accounts have snapshots
# ---------------------------------------------------------------------------
class TestActiveAccountsHaveSnapshots:
    def test_each_active_account_has_at_least_one_snapshot(self):
        active = _fetch_active_accounts()
        if not active:
            pytest.skip("No active accounts in database")

        account_ids = {a["account_id"] for a in active}
        snapshots = _fetch_all_snapshots()
        accounts_with_snapshots = {s["account_id"] for s in snapshots}

        missing = account_ids - accounts_with_snapshots
        print(
            f"\n[CHECK] Active accounts have snapshots: "
            f"{len(active)} active, {len(accounts_with_snapshots)} with snapshots, "
            f"{len(missing)} missing"
        )

        if missing:
            names = {
                a["account_id"]: a.get("account_name", "?")
                for a in active
                if a["account_id"] in missing
            }
            print(f"  Missing accounts: {names}")

        assert not missing, (
            f"{len(missing)} active account(s) have no snapshots: {missing}"
        )


# ---------------------------------------------------------------------------
# 5. Date continuity
# ---------------------------------------------------------------------------
class TestDateContinuity:
    def test_no_large_gaps_for_accounts_with_many_snapshots(self):
        snapshots = _fetch_all_snapshots()
        if not snapshots:
            pytest.skip("No snapshots in database")

        by_account = _group_by_account(snapshots)
        gap_violations: list[dict] = []

        for aid, snaps in by_account.items():
            if len(snaps) <= 10:
                continue

            for i in range(1, len(snaps) - 1):
                prev_date = _parse_date(snaps[i - 1]["snapshot_date"])
                curr_date = _parse_date(snaps[i]["snapshot_date"])
                gap_days = (curr_date - prev_date).days
                if gap_days > 30:
                    gap_violations.append({
                        "account_id": aid,
                        "from_date": str(prev_date),
                        "to_date": str(curr_date),
                        "gap_days": gap_days,
                    })

        print(
            f"\n[CHECK] Date continuity (>10 snapshots, gap <= 30 days): "
            f"{len(gap_violations)} gap(s) found"
        )

        for g in gap_violations[:10]:
            print(
                f"  GAP: account={g['account_id']} "
                f"{g['from_date']} -> {g['to_date']} ({g['gap_days']}d)"
            )

        assert not gap_violations, (
            f"{len(gap_violations)} gap(s) > 30 days found in accounts with >10 snapshots. "
            f"See printed details above."
        )


# ---------------------------------------------------------------------------
# 6. Values are reasonable
# ---------------------------------------------------------------------------
class TestReasonableValues:
    def test_no_negative_total_value(self):
        snapshots = _fetch_all_snapshots()
        if not snapshots:
            pytest.skip("No snapshots in database")

        violations = [
            s for s in snapshots
            if float(s.get("total_value") or 0) < 0
            and s.get("data_quality_flag") != "WARNING"
        ]
        print(f"\n[CHECK] No unflagged negative total_value: {len(violations)} violations")

        for v in violations[:5]:
            print(
                f"  NEGATIVE: account={v['account_id']} date={v['snapshot_date']} "
                f"total=${float(v['total_value']):,.2f} flag={v.get('data_quality_flag')}"
            )

        assert not violations, (
            f"{len(violations)} snapshot(s) have negative total_value without WARNING flag. "
            f"See printed details above."
        )

    def test_no_absurdly_large_values(self):
        snapshots = _fetch_all_snapshots()
        if not snapshots:
            pytest.skip("No snapshots in database")

        THRESHOLD = 1_000_000
        violations = [
            s for s in snapshots
            if float(s.get("total_value") or 0) > THRESHOLD
        ]
        print(f"\n[CHECK] No values > $1M individual accounts: {len(violations)} violations")

        for v in violations[:5]:
            print(
                f"  LARGE: account={v['account_id']} date={v['snapshot_date']} "
                f"total=${float(v['total_value']):,.2f}"
            )

        assert not violations, (
            f"{len(violations)} snapshot(s) exceed $1M total_value. "
            f"First: {[(v['account_id'], v['snapshot_date'], v['total_value']) for v in violations[:3]]}"
        )


# ---------------------------------------------------------------------------
# 7. Cost basis consistency
# ---------------------------------------------------------------------------
class TestCostBasisConsistency:
    def test_holdings_market_value_gte_cost_basis_mostly(self):
        snapshots = _fetch_all_snapshots()
        if not snapshots:
            pytest.skip("No snapshots in database")

        violations: list[dict] = []
        for s in snapshots:
            hmv = float(s.get("holdings_market_value") or 0)
            cb = float(s.get("cost_basis") or 0)
            if cb > 0 and hmv < cb * 0.5:
                violations.append({
                    "account_id": s["account_id"],
                    "snapshot_date": s["snapshot_date"],
                    "holdings_market_value": hmv,
                    "cost_basis": cb,
                    "ratio": hmv / cb if cb else 0,
                })

        pct = (len(violations) / len(snapshots) * 100) if snapshots else 0
        print(
            f"\n[CHECK] holdings_mv >= 0.5 * cost_basis (soft check): "
            f"{len(violations)}/{len(snapshots)} ({pct:.1f}%) violations"
        )

        for v in violations[:5]:
            print(
                f"  LOW: account={v['account_id']} date={v['snapshot_date']} "
                f"mv=${v['holdings_market_value']:,.2f} cost=${v['cost_basis']:,.2f} "
                f"ratio={v['ratio']:.2f}"
            )

        assert pct < 10, (
            f"{pct:.1f}% of snapshots have holdings_market_value < 50% of cost_basis. "
            f"This may indicate a systematic pricing issue."
        )


# ---------------------------------------------------------------------------
# Summary runner
# ---------------------------------------------------------------------------
class TestSummary:
    def test_print_summary(self):
        snapshots = _fetch_all_snapshots()
        active = _fetch_active_accounts()
        by_account = _group_by_account(snapshots)

        n_total = len(snapshots)
        n_accounts = len(by_account)
        n_active = len(active)
        n_unknown = sum(1 for s in snapshots if str(s.get("job_id", "")).lower() == "unknown")
        n_null_job = sum(1 for s in snapshots if not s.get("job_id") or str(s["job_id"]).strip() == "")
        n_negative = sum(1 for s in snapshots if float(s.get("total_value") or 0) < 0)

        print("\n" + "=" * 60)
        print("PORTFOLIO SNAPSHOT DATA INTEGRITY SUMMARY")
        print("=" * 60)
        print(f"  Total snapshots       : {n_total}")
        print(f"  Unique accounts       : {n_accounts}")
        print(f"  Active accounts       : {n_active}")
        print(f"  Null/empty job_ids    : {n_null_job}")
        print(f"  'unknown' job_ids     : {n_unknown}")
        print(f"  Negative total_value  : {n_negative}")
        print("=" * 60)
