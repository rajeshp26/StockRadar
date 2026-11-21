"""
Test buy_quarter_index computation with realistic scenarios.
Simulates Ford (purchased years ago → buy_quarter_index = 0)
vs a recently purchased stock (buy_quarter_index > 0).
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

# ── Helper: build a FundamentalsService with a mocked repo ─────────────

async def run_scenario(quarters_data, purchase_date_str):
    """
    Simulate FundamentalsService.get_fundamentals() with given data.
    Returns (has_portfolio_position, buy_quarter_index, purchase_period).
    """
    from application.services.fundamentals_service import FundamentalsService
    from infrastructure.repositories.fundamentals_repository import FundamentalsRepository

    repo = MagicMock(spec=FundamentalsRepository)
    repo.get_company_by_symbol = AsyncMock(return_value={
        "company_id": 1, "company_name": "TestCo"
    })
    # Build quarter data: return tuples (fiscal_year, fiscal_quarter)
    repo.get_quarterly_financial_ratios = AsyncMock(return_value=[
        {"fiscal_year": fy, "fiscal_quarter": fq}
        for fy, fq in quarters_data
    ])
    repo.get_quarterly_income_statements = AsyncMock(return_value=[])
    repo.get_quarterly_cash_flows = AsyncMock(return_value=[])
    repo.get_company_summary_history = AsyncMock(return_value=[])
    repo.get_latest_valuation_overview = AsyncMock(return_value=None)
    repo.get_valuation_snapshots = AsyncMock(return_value={})
    repo.get_earnings_history = AsyncMock(return_value=[])
    repo.get_current_market_price = AsyncMock(return_value=100.0)
    repo.get_buy_anchor = AsyncMock(return_value={
        "transaction_date": purchase_date_str,
        "unit_price": 10.0,
    })

    svc = FundamentalsService(repo)
    result = await svc.get_fundamentals("TEST", user_id="42")
    return result.has_portfolio_position, result.buy_quarter_index, result.purchase_period


class TestBuyQuarterIndexScenarios:

    @pytest.mark.asyncio
    async def test_old_purchase_all_quarters_after_purchase(self):
        """
        Ford scenario: purchased long before earliest financial data.
        Financial data: Q2'23 → Q1'26  (13 quarters, 2023-2026)
        Purchase: 2020-01-15 (years before any data)
        Expected: buy_quarter_index = 0 (all data is post-purchase)
        """
        quarters = [(2023, 2), (2023, 3), (2023, 4), (2024, 1),
                     (2024, 2), (2024, 3), (2024, 4), (2025, 1),
                     (2025, 2), (2025, 3), (2025, 4), (2026, 1)]
        held, idx, period = await run_scenario(quarters, "2020-01-15")

        assert held is True, "Stock should be reported as held"
        assert idx == 0, (
            f"Ford bought in 2020, earliest data is Q2'23 — "
            f"all quarters are post-purchase, so index should be 0, got {idx}"
        )
        assert period == "2020-01"

    @pytest.mark.asyncio
    async def test_recent_purchase_some_quarters_before(self):
        """
        Recent purchase: data spans Q1'22 → Q1'26, purchased in Q4'24.
        Expected: buy_quarter_index = index of first quarter ≥ Q4'24
        Quarters: (2022,1), (2022,2), (2022,3), (2022,4),
                  (2023,1), (2023,2), (2023,3), (2023,4),
                  (2024,1), (2024,2), (2024,3), (2024,4), (2025,1)
        Purchase: 2024-10-15 → fiscal year 2024, quarter 4
        Index should be 11 (the 12th quarter, 0-indexed: 2024,4)
        """
        quarters = []
        for y in range(2022, 2026):
            for q in range(1, 5):
                quarters.append((y, q))
        # 16 quarters: (2022,1) through (2025,4)
        quarters = quarters[:13]  # trim to Q1'25

        held, idx, _period = await run_scenario(quarters, "2024-10-15")

        assert held is True
        # (2022,1)=0, (2022,2)=1, ..., (2024,3)=10, (2024,4)=11, (2025,1)=12
        assert idx == 11, (
            f"Purchase 2024-10-15 (Q4'24), index should be 11 (2024,Q4), got {idx}"
        )

    @pytest.mark.asyncio
    async def test_purchase_exactly_at_first_quarter_boundary(self):
        """
        Purchase date matches the first financial data quarter.
        Data: Q1'22 → ...  Purchase: mid Q1'22
        Expected: index = 0 (the purchase quarter is the first quarter)
        """
        quarters = [(2022, 1), (2022, 2), (2022, 3), (2022, 4)]
        held, idx, _period = await run_scenario(quarters, "2022-02-15")

        assert held is True
        assert idx == 0, (
            f"Purchase in Q1'22, first data is Q1'22, index should be 0, got {idx}"
        )

    @pytest.mark.asyncio
    async def test_annual_frequency_purchase_index(self):
        """
        With annual frequency, fiscal_quarter is 0.
        Purchase in June 2023 → first full year AFTER purchase is 2024 (index 3).
        Annual mode uses strict fy > pd_year (no partial-year inclusion).
        """
        from application.services.fundamentals_service import FundamentalsService
        from infrastructure.repositories.fundamentals_repository import FundamentalsRepository

        repo = MagicMock(spec=FundamentalsRepository)
        repo.get_company_by_symbol = AsyncMock(return_value={
            "company_id": 1, "company_name": "TestCo"
        })
        repo.get_annual_financial_ratios = AsyncMock(return_value=[
            {"fiscal_year": 2021, "fiscal_quarter": None},
            {"fiscal_year": 2022, "fiscal_quarter": None},
            {"fiscal_year": 2023, "fiscal_quarter": None},
            {"fiscal_year": 2024, "fiscal_quarter": None},
        ])
        repo.get_annual_income_statements = AsyncMock(return_value=[])
        repo.get_annual_cash_flows = AsyncMock(return_value=[])
        repo.get_company_summary_history = AsyncMock(return_value=[])
        repo.get_latest_valuation_overview = AsyncMock(return_value=None)
        repo.get_valuation_snapshots = AsyncMock(return_value={})
        repo.get_earnings_history = AsyncMock(return_value=[])
        repo.get_current_market_price = AsyncMock(return_value=100.0)
        repo.get_buy_anchor = AsyncMock(return_value={
            "transaction_date": "2023-06-15",
            "unit_price": 10.0,
        })

        svc = FundamentalsService(repo)
        result = await svc.get_fundamentals("TEST", user_id="42", frequency="annual")
        assert result.has_portfolio_position is True
        # Years: 2021(0), 2022(1), 2023(2), 2024(3)
        # Annual mode: fy > pd_year = fy > 2023 → first match is 2024 at index 3
        assert result.buy_quarter_index == 3, (
            f"Annual: purchase 2023, first full year after is 2024 (index 3), got {result.buy_quarter_index}"
        )

    @pytest.mark.asyncio
    async def test_annual_purchase_early_year(self):
        """
        Purchase in January 2023 (early in the year).
        Still uses fy > pd_year, so first full year after purchase is 2024.
        """
        from application.services.fundamentals_service import FundamentalsService
        from infrastructure.repositories.fundamentals_repository import FundamentalsRepository

        repo = MagicMock(spec=FundamentalsRepository)
        repo.get_company_by_symbol = AsyncMock(return_value={
            "company_id": 1, "company_name": "TestCo"
        })
        repo.get_annual_financial_ratios = AsyncMock(return_value=[
            {"fiscal_year": 2021, "fiscal_quarter": None},
            {"fiscal_year": 2022, "fiscal_quarter": None},
            {"fiscal_year": 2023, "fiscal_quarter": None},
            {"fiscal_year": 2024, "fiscal_quarter": None},
        ])
        repo.get_annual_income_statements = AsyncMock(return_value=[])
        repo.get_annual_cash_flows = AsyncMock(return_value=[])
        repo.get_company_summary_history = AsyncMock(return_value=[])
        repo.get_latest_valuation_overview = AsyncMock(return_value=None)
        repo.get_valuation_snapshots = AsyncMock(return_value={})
        repo.get_earnings_history = AsyncMock(return_value=[])
        repo.get_current_market_price = AsyncMock(return_value=100.0)
        repo.get_buy_anchor = AsyncMock(return_value={
            "transaction_date": "2023-01-15",
            "unit_price": 10.0,
        })

        svc = FundamentalsService(repo)
        result = await svc.get_fundamentals("TEST", user_id="42", frequency="annual")
        assert result.has_portfolio_position is True
        # Even for January 2023 purchase, annual mode still demands fy > pd_year
        # so first shown is 2024 (index 3)
        assert result.buy_quarter_index == 3
