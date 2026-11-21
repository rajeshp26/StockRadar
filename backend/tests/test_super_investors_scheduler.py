"""SuperInvestorsRefreshScheduler gating, self-heal, and saved-count tests."""

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.schedulers.super_investors_scheduler import InvestorRefreshStatus
from shared.time_utils import now_utc


class _FakeHoldings:
    """Stand-in for the holdings DataFrame (code only consults .empty pre-save)."""

    empty = False


class _FakeFilings:
    """List-like stand-in for an edgar Filing collection."""

    def __init__(self, filings=None):
        self._f = list(filings or [])

    def filter(self, cik=None):
        return self

    def __len__(self):
        return len(self._f)

    def __getitem__(self, i):
        return self._f[i]

    def __iter__(self):
        return iter(self._f)


def _make_filing(period, filing_date="2026-08-14", holdings=None, total_value=1_000_000.0):
    thirteenf = SimpleNamespace(
        report_period=period,
        total_value=total_value,
        holdings=holdings if holdings is not None else _FakeHoldings(),
    )
    return SimpleNamespace(obj=lambda: thirteenf, filing_date=filing_date)


def _make_scheduler(mock_financial_repo):
    from application.schedulers.super_investors_scheduler import SuperInvestorsRefreshScheduler

    sched = SuperInvestorsRefreshScheduler.__new__(SuperInvestorsRefreshScheduler)
    sched.financial_repo = mock_financial_repo
    sched._update_investor_tracking = AsyncMock()
    return sched


INFO = {"name": "Test Fund", "firm": "Test", "tag": "T", "style": ""}


class TestFetchNewFiling:
    @pytest.fixture(autouse=True)
    def _scheduler(self, mock_financial_repo):
        self.sched = _make_scheduler(mock_financial_repo)
        self.sched._save_holdings_to_db = AsyncMock(return_value=1)
        self.sched._holdings_exist_for_period = AsyncMock(return_value=True)

    async def test_advances_tracking_when_saved(self):
        filing = _make_filing(period=date(2026, 6, 30))
        with patch("edgar.get_filings", return_value=_FakeFilings([filing])):
            ok = await self.sched._fetch_new_filing("0001", INFO, None)
        assert ok == InvestorRefreshStatus.REFRESHED
        self.sched._save_holdings_to_db.assert_awaited_once()
        self.sched._update_investor_tracking.assert_awaited_once_with(
            "0001", "2026-06-30", "2026-08-14"
        )

    async def test_does_not_advance_tracking_when_nothing_saved(self):
        self.sched._save_holdings_to_db = AsyncMock(return_value=0)
        filing = _make_filing(period=date(2026, 6, 30))
        with patch("edgar.get_filings", return_value=_FakeFilings([filing])):
            ok = await self.sched._fetch_new_filing("0001", INFO, None)
        assert ok == InvestorRefreshStatus.NO_FILINGS
        self.sched._update_investor_tracking.assert_not_awaited()

    async def test_self_heals_when_tracked_period_has_no_rows(self):
        self.sched._holdings_exist_for_period = AsyncMock(return_value=False)
        filing = _make_filing(period=date(2026, 3, 31))
        with patch("edgar.get_filings", return_value=_FakeFilings([filing])):
            ok = await self.sched._fetch_new_filing("0001", INFO, "2026-03-31")
        assert ok == InvestorRefreshStatus.REFRESHED
        self.sched._save_holdings_to_db.assert_awaited_once()
        self.sched._update_investor_tracking.assert_awaited_once_with(
            "0001", "2026-03-31", "2026-08-14"
        )
        self.sched._holdings_exist_for_period.assert_awaited_once_with("0001", "2026-03-31")

    async def test_skips_when_tracked_period_already_persisted(self):
        filing = _make_filing(period=date(2026, 3, 31))
        with patch("edgar.get_filings", return_value=_FakeFilings([filing])):
            ok = await self.sched._fetch_new_filing("0001", INFO, "2026-03-31")
        assert ok == InvestorRefreshStatus.SKIPPED_NOT_DUE
        self.sched._save_holdings_to_db.assert_not_awaited()
        self.sched._update_investor_tracking.assert_not_awaited()

    async def test_year_scoped_with_previous_year_fallback(self):
        filing = _make_filing(period=date(2026, 6, 30))
        current_year = now_utc().year

        def _side_effect(year=None, form=None):
            return _FakeFilings([]) if year == current_year else _FakeFilings([filing])

        with patch("edgar.get_filings", side_effect=_side_effect) as mock_get_filings:
            ok = await self.sched._fetch_new_filing("0001", INFO, None)
        assert ok == InvestorRefreshStatus.REFRESHED
        years = [c.kwargs.get("year") for c in mock_get_filings.call_args_list]
        assert years == [current_year, current_year - 1]

    async def test_no_filings_returns_false(self):
        with patch("edgar.get_filings", return_value=_FakeFilings([])):
            ok = await self.sched._fetch_new_filing("0001", INFO, None)
        assert ok == InvestorRefreshStatus.NO_FILINGS
        self.sched._update_investor_tracking.assert_not_awaited()


class TestFetchHistoricalData:
    @pytest.fixture(autouse=True)
    def _scheduler(self, mock_financial_repo):
        self.sched = _make_scheduler(mock_financial_repo)

    async def test_tracks_latest_period_overall(self):
        p1 = _make_filing(period=date(2025, 9, 30), filing_date="2025-11-14")
        p2 = _make_filing(period=date(2025, 12, 31), filing_date="2026-02-13")
        p3 = _make_filing(period=date(2026, 3, 31), filing_date="2026-05-15")

        def _save(cik, info, holdings_df, period, filing_date, total_value_dollars=None):
            return 1

        self.sched._save_holdings_to_db = AsyncMock(side_effect=_save)
        with patch("edgar.get_filings", return_value=_FakeFilings([p3, p2, p1])):
            ok = await self.sched._fetch_historical_data("0001", INFO, 10)
        assert ok == InvestorRefreshStatus.REFRESHED
        self.sched._update_investor_tracking.assert_awaited_once_with(
            "0001", "2026-03-31", "2026-05-15"
        )

    async def test_tracks_only_periods_that_saved_rows(self):
        older = _make_filing(period=date(2025, 12, 31), filing_date="2026-02-13")
        newer = _make_filing(period=date(2026, 3, 31), filing_date="2026-05-15")

        def _save(cik, info, holdings_df, period, filing_date, total_value_dollars=None):
            return 2 if period == "2025-12-31" else 0

        self.sched._save_holdings_to_db = AsyncMock(side_effect=_save)
        with patch("edgar.get_filings", return_value=_FakeFilings([newer, older])):
            ok = await self.sched._fetch_historical_data("0001", INFO, 10)
        assert ok == InvestorRefreshStatus.REFRESHED
        self.sched._update_investor_tracking.assert_awaited_once_with(
            "0001", "2025-12-31", "2026-02-13"
        )

    async def test_no_tracking_when_nothing_saved(self):
        self.sched._save_holdings_to_db = AsyncMock(return_value=0)
        filing = _make_filing(period=date(2026, 3, 31))
        with patch("edgar.get_filings", return_value=_FakeFilings([filing])):
            ok = await self.sched._fetch_historical_data("0001", INFO, 20)
        assert ok == InvestorRefreshStatus.NO_FILINGS
        self.sched._update_investor_tracking.assert_not_awaited()


class TestSaveHoldingsToDb:
    @pytest.fixture(autouse=True)
    def _scheduler(self, mock_financial_repo):
        self.sched = _make_scheduler(mock_financial_repo)

    @staticmethod
    def _supabase_chain():
        sb = MagicMock()
        t = MagicMock()
        sb.table.return_value = t
        t.select.return_value = t
        t.eq.return_value = t
        t.lt.return_value = t
        t.order.return_value = t
        t.limit.return_value = t
        t.update.return_value = t
        t.insert.return_value = t
        return sb, t

    async def test_counts_updates_and_inserts(self):
        import pandas as pd

        sb, t = self._supabase_chain()
        # Per holding row the code fires 4 executes: company lookup, prev-quarter
        # lookup, existing lookup, then the write (update/insert) whose response
        # is discarded. Two rows => 1 (investor) + 4 + 4 = 9 side_effect entries.
        t.execute.side_effect = [
            MagicMock(data=[{"investor_id": 26}]),          # investor lookup
            MagicMock(data=[{"company_id": 111}]),          # AAA company lookup
            MagicMock(data=[]),                             # AAA prev quarter (none)
            MagicMock(data=[{"holding_id": 500}]),          # AAA existing -> UPDATE
            MagicMock(data=[]),                             # AAA update write (discarded)
            MagicMock(data=[{"company_id": 222}]),          # BBB company lookup
            MagicMock(data=[]),                             # BBB prev quarter (none)
            MagicMock(data=[]),                             # BBB existing -> INSERT
            MagicMock(data=[]),                             # BBB insert write (discarded)
        ]
        holdings_df = pd.DataFrame([
            {"Ticker": "AAA", "SharesPrnAmount": 100, "Value": 1_000.0},
            {"Ticker": "BBB", "SharesPrnAmount": 200, "Value": 2_000.0},
        ])
        with patch("database.supabase", sb):
            saved = await self.sched._save_holdings_to_db(
                "0001", INFO, holdings_df, "2026-03-31", "2026-05-15", total_value_dollars=3_000.0
            )
        assert saved == 2

    async def test_skips_unknown_tickers_returns_zero(self):
        import pandas as pd

        sb, t = self._supabase_chain()
        t.execute.side_effect = [
            MagicMock(data=[{"investor_id": 26}]),
            MagicMock(data=[]),
        ]
        holdings_df = pd.DataFrame([{"Ticker": "ZZZ", "SharesPrnAmount": 10, "Value": 10.0}])
        with patch("database.supabase", sb):
            saved = await self.sched._save_holdings_to_db(
                "0001", INFO, holdings_df, "2026-03-31", "2026-05-15", total_value_dollars=10.0
            )
        assert saved == 0


class TestNormalizePeriod:
    @staticmethod
    def _sched():
        from application.schedulers.super_investors_scheduler import SuperInvestorsRefreshScheduler
        return SuperInvestorsRefreshScheduler.__new__(SuperInvestorsRefreshScheduler)

    def test_date_datetime_str_and_none(self):
        s = self._sched()
        assert s._normalize_period(date(2026, 3, 31)) == "2026-03-31"
        assert s._normalize_period(datetime(2026, 3, 31, 14, 30)) == "2026-03-31"
        assert s._normalize_period("2026-03-31") == "2026-03-31"
        assert s._normalize_period(None) is None
