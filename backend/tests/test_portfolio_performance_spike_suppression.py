"""
Regression tests for the LOCF-merge spike-suppression cascade.

Bug (Sep 2026): `get_portfolio_performance` froze the whole series at a stale
anchor whenever a legitimate real appreciation >20% (unexplained by deposits)
occurred on a NON-latest date. The suppression branch fired on dates where every
account has a real snapshot — `date_with_locf` was never checked — froze
`prev_merged` at the old anchor and reverted `last_*`, so every later real date
re-triggered the check and the series stayed frozen until the latest date.
The visible symptom was a fake "spike" between Sep 20 and Sep 21, 2026 in the
1Y/YTD timelines and a frozen ALL timeline.

Fix: gate suppression on `date_with_locf` — only gap-filled dates may be
suppressed; dates where every account has real snapshots pass through.

Run: pytest tests/test_portfolio_performance_spike_suppression.py -v -s
"""
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from application.services.portfolio_service import PortfolioService


def _snap(account_id, d, total_value, nd=0.0):
    # The supabase repo returns ISO-date strings, which the merge loop and
    # _compute_returns_from_snapshots both expect (str -> date.fromisoformat).
    return {
        "account_id": account_id,
        "snapshot_date": d.isoformat(),
        "total_value": total_value,
        "holdings_market_value": total_value,
        "cost_basis": total_value * 0.7,
        "cash_balance": 0.0,
        "net_deposits": nd,
        "data_quality_flag": "OK",
    }


def _make_service(snapshot_rows):
    """Build a PortfolioService whose snapshot repo returns `snapshot_rows`.

    Returns (service, account_ids, patchers): callers must stop each patcher
    after the test (the `with`-block form cannot span the awaited call site).
    """
    accounts = [
        {"account_id": 7, "account_name": "TFSA", "is_active": True},
        {"account_id": 8, "account_name": "RRSP", "is_active": True},
        {"account_id": 9, "account_name": "Margin", "is_active": True},
    ]
    account_ids = [7, 8, 9]

    mock_portfolio_repo = MagicMock()
    mock_portfolio_repo.get_user_accounts.return_value = accounts

    mock_financial_repo = MagicMock()
    mock_financial_repo.get_latest_prices = MagicMock()

    mock_snaps_repo = MagicMock()
    mock_snaps_repo.get_portfolio_snapshots.return_value = snapshot_rows

    patchers = []

    period_patcher = patch.object(
        PortfolioService, "_period_to_date_range",
        return_value=(date(2025, 1, 1), date(2025, 1, 4)),
    )
    period_patcher.start()
    patchers.append(period_patcher)

    settings_patcher = patch("config.settings")
    mock_settings = settings_patcher.start()
    patchers.append(settings_patcher)
    mock_settings.ENABLE_PORTFOLIO_SNAPSHOT_READ_PATH = True
    mock_settings.ENABLE_PERFORMANCE_LOCF = True
    mock_settings.SNAPSHOT_SPIKE_THRESHOLD = 0.20

    snaps_patcher = patch(
        "application.services.portfolio_service.PortfolioSnapshotsRepository",
        return_value=mock_snaps_repo,
    )
    snaps_patcher.start()
    patchers.append(snaps_patcher)

    service = PortfolioService(mock_portfolio_repo, mock_financial_repo)
    return service, account_ids, patchers


@pytest.mark.anyio
async def test_real_data_jump_never_suppressed():
    """A >20% real jump on a fully-real date must NOT freeze the series."""
    rows = []
    # D1..D4, every account has real data on every date. D3 jumps +25%
    # flat (unexplained by deposits) on a NON-latest date.
    for d_i, d in enumerate([date(2025, 1, 1), date(2025, 1, 2),
                             date(2025, 1, 3), date(2025, 1, 4)]):
        if d_i < 2:
            vals = {7: 100.0, 8: 200.0, 9: 300.0}
        else:
            # +25% jump on D3 (non-latest), +small on D4 (latest)
            vals = {7: 150.0, 8: 250.0, 9: 350.0} if d_i == 2 else {7: 155.0, 8: 260.0, 9: 360.0}
        for aid in (7, 8, 9):
            rows.append(_snap(aid, d, vals[aid]))

    service, account_ids, patchers = _make_service(rows)
    try:
        result = await service.get_portfolio_performance(1, "1W", account_ids)
    finally:
        for p in patchers:
            p.stop()

    assert result["success"]
    snaps = result["snapshots"]
    # Period 1W: no compression — every merged date appears in order.
    dates = [s["date"] for s in snaps]
    assert dates == ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04"], dates
    values = [s["value"] for s in snaps]
    # True sums: 600, 600, 750, 775. Suppression-free output must show them all.
    assert values == [600.0, 600.0, 750.0, 775.0], values
    assert result["spike_detected"] is False


@pytest.mark.anyio
async def test_gap_filled_date_still_suppressed():
    """A spike on a genuinely gap-filled date (LOCF) is still suppressed."""
    rows = []
    # Acct 8 is missing on D3 -> LOCF carries its D2 value forward on D3.
    # Acct 7 real data jumps 100 -> 300 on D3: an unexplained >20% merged jump
    # on a date where one account was gap-filled — must be suppressed.
    d1, d2, d3, d4 = date(2025, 1, 1), date(2025, 1, 2), date(2025, 1, 3), date(2025, 1, 4)
    for aid, present_on in ((7, [d1, d2, d3, d4]), (8, [d1, d2, d4]), (9, [d1, d2, d3, d4])):
        for d in present_on:
            if aid == 7:
                val = 100.0 if d in (d1, d2) else (300.0 if d == d3 else 305.0)
            else:
                val = 100.0
            rows.append(_snap(aid, d, val))

    service, account_ids, patchers = _make_service(rows)
    try:
        result = await service.get_portfolio_performance(1, "1W", account_ids)
    finally:
        for p in patchers:
            p.stop()

    assert result["success"]
    snaps = result["snapshots"]
    dates = [s["date"] for s in snaps]
    assert dates == ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04"], dates
    values = [s["value"] for s in snaps]
    # D1=300, D2=300, D3 would be 500 (acct7=300 real + acct8 LOCF 100 + acct9 100)
    # but it's a gap-filled date -> suppressed to 300. D4 (latest) = 505 real.
    assert values == [300.0, 300.0, 300.0, 505.0], values
    assert result["spike_detected"] is True


@pytest.mark.anyio
async def test_fx_unconverted_date_spike_suppressed():
    """A spike onto an FX-unconverted date (fx_applied False) is suppressed."""
    rows = []
    d1, d2, d3, d4 = date(2025, 1, 1), date(2025, 1, 2), date(2025, 1, 3), date(2025, 1, 4)
    for d_i, d in enumerate([d1, d2, d3, d4]):
        if d_i < 2:
            vals = {7: 100.0, 8: 200.0, 9: 300.0}
        elif d_i == 2:
            # +100% jump on D3, but every holding carries fx_applied=False (artifact, not a market move)
            vals = {7: 300.0, 8: 400.0, 9: 500.0}
        else:
            vals = {7: 155.0, 8: 260.0, 9: 360.0}
        for aid in (7, 8, 9):
            snap = _snap(aid, d, vals[aid])
            if d_i == 2:
                snap["holdings_json"] = [{"fx_applied": False}]
            rows.append(snap)

    service, account_ids, patchers = _make_service(rows)
    try:
        result = await service.get_portfolio_performance(1, "1W", account_ids)
    finally:
        for p in patchers:
            p.stop()

    assert result["success"]
    snaps = result["snapshots"]
    dates = [s["date"] for s in snaps]
    assert dates == ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04"], dates
    values = [s["value"] for s in snaps]
    # D3's real-but-fx-flawed value (1200) is suppressed to D2's 600; D4 (latest) = 775 real.
    assert values == [600.0, 600.0, 600.0, 775.0], values
    assert result["spike_detected"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])