from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from application.services.edgar_filing_service import EdgarFilingService
from application.services.moat_analysis_service import _SECTOR_MOAT_ADJUSTMENTS, MoatAnalysisService
from application.services.moat_keyword_analyzer import MoatKeywordAnalyzer
from application.services.moat_wacc_service import MoatWaccService


class TestMoatAnalysisService:
    @pytest.mark.asyncio
    async def test_get_moat_analysis_compute(self, mock_moat_repo):
        wacc = MoatWaccService(mock_moat_repo)
        edgar = EdgarFilingService()
        analyzer = MoatKeywordAnalyzer()
        svc = MoatAnalysisService(mock_moat_repo, wacc, edgar, analyzer)

        result = await svc.get_moat_analysis("AAPL")
        assert result.symbol == "AAPL"
        assert result.company_id == 1
        assert result.valuation.roic is not None
        assert result.valuation.wacc is not None
        assert result.valuation.moat_score is not None
        assert result.valuation.moat_category in ("Wide", "Narrow", "None", "Unknown")

    @pytest.mark.asyncio
    async def test_get_moat_analysis_cached(self, mock_moat_repo):
        mock_moat_repo.get_moat_analysis = AsyncMock(
            return_value={
                "company_id": 1,
                "symbol": "AAPL",
                "roic": 0.32,
                "wacc": 0.10,
                "roic_minus_wacc": 22.0,
                "moat_score": 85.0,
                "moat_category": "Wide",
                "fiscal_years_used": 5,
                "data_sources": "database",
                "quarters_used": 0,
                "fallbacks_used": False,
                "computed_at": datetime.utcnow().isoformat(),
                "text_analysis_available": False,
                "keyword_matches_count": 0,
                "sector": "Technology",
                "sector_adjustment": 0.0,
                "ai_narrative_available": False,
            }
        )
        wacc = MoatWaccService(mock_moat_repo)
        svc = MoatAnalysisService(mock_moat_repo, wacc)
        result = await svc.get_moat_analysis("AAPL")
        assert result.symbol == "AAPL"
        assert result.valuation.moat_score == 85.0

    @pytest.mark.asyncio
    async def test_get_moat_analysis_unknown_symbol(self, mock_moat_repo):
        mock_moat_repo.get_company_context = MagicMock(return_value=None)
        wacc = MoatWaccService(mock_moat_repo)
        svc = MoatAnalysisService(mock_moat_repo, wacc)
        with pytest.raises(ValueError, match="not found"):
            await svc.get_moat_analysis("UNKNOWN")

    @pytest.mark.asyncio
    async def test_moat_category_wide(self, mock_moat_repo):
        wacc = MoatWaccService(mock_moat_repo)
        svc = MoatAnalysisService(mock_moat_repo, wacc)
        result = await svc.get_moat_analysis("AAPL")
        assert result.valuation.moat_category == "Wide"

    def test_categorize_score_wide(self):
        assert MoatAnalysisService._categorize_score(85) == "Wide"
        assert MoatAnalysisService._categorize_score(70) == "Wide"

    def test_categorize_score_narrow(self):
        assert MoatAnalysisService._categorize_score(55) == "Narrow"
        assert MoatAnalysisService._categorize_score(40) == "Narrow"

    def test_categorize_score_none(self):
        assert MoatAnalysisService._categorize_score(25) == "None"
        assert MoatAnalysisService._categorize_score(10) == "None"

    def test_categorize_score_unknown(self):
        assert MoatAnalysisService._categorize_score(5) == "Unknown"

    def test_compute_std(self):
        values = [10, 20, 30, 40, 50]
        std = MoatAnalysisService._compute_std(values)
        assert std > 0

    def test_compute_std_single_value(self):
        assert MoatAnalysisService._compute_std([42]) == 0.0

    def test_compute_stability_score_low_volatility(self):
        score = MoatAnalysisService._compute_stability_score(0.01, [0.15, 0.14, 0.16])
        assert score == 95.0

    def test_compute_stability_score_high_volatility(self):
        score = MoatAnalysisService._compute_stability_score(0.50, [0.50, 0.01, 0.99])
        assert score < 50.0

    def test_compute_capital_efficiency_score_high(self):
        score = MoatAnalysisService._compute_capital_efficiency_score(
            asset_turnover=1.5, roic=0.25, wacc=0.10
        )
        assert score is not None
        assert score > 50

    def test_compute_capital_efficiency_score_low(self):
        score = MoatAnalysisService._compute_capital_efficiency_score(
            asset_turnover=0.1, roic=0.03, wacc=0.10
        )
        assert score is not None
        assert score < 50

    def test_compute_capital_efficiency_score_none(self):
        score = MoatAnalysisService._compute_capital_efficiency_score(
            asset_turnover=None, roic=None, wacc=None
        )
        assert score is None

    def test_generate_flags_roic_below_wacc(self):
        flags = MoatAnalysisService._generate_flags(
            latest_roic=0.05, wacc=0.10, roic_5y_std=0.02, asset_turnover=0.5, sector="Technology"
        )
        codes = [f.code for f in flags]
        assert "MOAT-ROIC-BELOW-WACC" in codes

    def test_generate_flags_high_volatility(self):
        flags = MoatAnalysisService._generate_flags(
            latest_roic=0.15, wacc=0.10, roic_5y_std=0.15, asset_turnover=0.5, sector="Technology"
        )
        codes = [f.code for f in flags]
        assert "MOAT-ROIC-HIGH-VOLATILITY" in codes

    def test_generate_flags_low_asset_turnover(self):
        flags = MoatAnalysisService._generate_flags(
            latest_roic=0.15, wacc=0.10, roic_5y_std=0.05, asset_turnover=0.1, sector="Technology"
        )
        codes = [f.code for f in flags]
        assert "MOAT-LOW-ASSET-TURNOVER" in codes

    def test_generate_flags_regulated_sector(self):
        flags = MoatAnalysisService._generate_flags(
            latest_roic=0.15, wacc=0.10, roic_5y_std=0.05, asset_turnover=0.5, sector="Financials"
        )
        codes = [f.code for f in flags]
        assert "MOAT-SECTOR-REGULATED" in codes

    @pytest.mark.asyncio
    async def test_get_moat_evidence_not_found(self, mock_moat_repo):
        mock_moat_repo.get_company_context = MagicMock(return_value=None)
        wacc = MoatWaccService(mock_moat_repo)
        svc = MoatAnalysisService(mock_moat_repo, wacc)
        with pytest.raises(ValueError, match="not found"):
            await svc.get_moat_evidence("UNKNOWN")

    @pytest.mark.asyncio
    async def test_get_moat_evidence_empty(self, mock_moat_repo):
        wacc = MoatWaccService(mock_moat_repo)
        svc = MoatAnalysisService(mock_moat_repo, wacc)
        result = await svc.get_moat_evidence("AAPL")
        assert result.text_analysis_available is False
        assert result.total_keyword_matches == 0

    @pytest.mark.asyncio
    async def test_run_text_analysis_no_edgar(self, mock_moat_repo):
        wacc = MoatWaccService(mock_moat_repo)
        svc = MoatAnalysisService(mock_moat_repo, wacc)
        result = await svc.run_text_analysis("AAPL")
        assert result.text_analysis_available is False

    @pytest.mark.asyncio
    async def test_get_moat_ai_narrative_cached(self, mock_moat_repo):
        mock_moat_repo.get_moat_ai_narrative = AsyncMock(
            return_value={
                "narrative": "Apple has a wide moat.",
                "model": "openrouter/default",
                "generated_at": "2025-01-01T00:00:00Z",
                "generation_time_ms": 1500,
            }
        )
        wacc = MoatWaccService(mock_moat_repo)
        svc = MoatAnalysisService(mock_moat_repo, wacc)
        result = await svc.get_moat_ai_narrative("AAPL")
        assert result.available is True
        assert "wide moat" in result.narrative.narrative

    @pytest.mark.asyncio
    async def test_get_moat_ai_narrative_not_cached(self, mock_moat_repo):
        wacc = MoatWaccService(mock_moat_repo)
        svc = MoatAnalysisService(mock_moat_repo, wacc)
        result = await svc.get_moat_ai_narrative("AAPL")
        assert result.available is False

    def test_sector_adjustments_defined(self):
        assert "Technology" in _SECTOR_MOAT_ADJUSTMENTS
        assert "Financials" in _SECTOR_MOAT_ADJUSTMENTS
        assert "Utilities" in _SECTOR_MOAT_ADJUSTMENTS

    def test_compute_stage1_score(self):
        svc = MoatAnalysisService.__new__(MoatAnalysisService)
        score = svc.compute_stage1_score(
            latest_roic=0.32, wacc=0.10,
            roic_5y_avg=0.30, roic_stability_score=90.0,
            capital_efficiency_score=80.0,
            latest_gross_margin=0.43, latest_net_margin=0.25,
        )
        assert 0 <= score <= 100
        assert score > 60

    def test_compute_stage1_score_low_values(self):
        svc = MoatAnalysisService.__new__(MoatAnalysisService)
        score = svc.compute_stage1_score(
            latest_roic=0.02, wacc=0.10,
            roic_5y_avg=0.02, roic_stability_score=20.0,
            capital_efficiency_score=10.0,
            latest_gross_margin=0.05, latest_net_margin=0.01,
        )
        assert score < 40

    def test_build_quant_summary_with_data(self):
        summary = MoatAnalysisService._build_quant_summary(
            {"moat_score": 85.0, "moat_category": "Wide", "roic": 0.32, "wacc": 0.10}
        )
        assert "85.0" in summary
        assert "Wide" in summary

    def test_build_quant_summary_without_data(self):
        summary = MoatAnalysisService._build_quant_summary(None)
        assert "No quantitative data" in summary

    def test_build_ai_prompt(self):
        prompt = MoatAnalysisService._build_ai_prompt("AAPL", "score: 85", "5 matches found")
        assert "AAPL" in prompt
        assert "score: 85" in prompt

    # ── Quant edge case tests ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_moat_analysis_missing_years(self, mock_moat_repo):
        mock_moat_repo.get_financial_ratios_history = AsyncMock(return_value=[
            {"fiscal_year": 2024, "roic": 0.15, "gross_margin": 0.40,
             "operating_margin": 0.20, "net_margin": 0.10, "asset_turnover": 0.5},
            {"fiscal_year": 2023, "roic": 0.12, "gross_margin": 0.38,
             "operating_margin": 0.18, "net_margin": 0.08, "asset_turnover": 0.48},
        ])
        wacc = MoatWaccService(mock_moat_repo)
        svc = MoatAnalysisService(mock_moat_repo, wacc)
        result = await svc.get_moat_analysis("AAPL")
        assert result.valuation.moat_score is not None
        assert result.inputs.fiscal_years_used == 2
        assert result.data_quality.last_computed_at is not None

    @pytest.mark.asyncio
    async def test_moat_analysis_economic_profit(self, mock_moat_repo):
        wacc = MoatWaccService(mock_moat_repo)
        svc = MoatAnalysisService(mock_moat_repo, wacc)
        result = await svc.get_moat_analysis("AAPL")
        assert result.valuation.roic is not None
        assert result.valuation.wacc is not None
        # ROIC minus WACC spread should be positive for the mock data (0.32 vs ~0.1)
        assert result.valuation.roic_minus_wacc is not None
        assert result.valuation.roic_minus_wacc > 0

    @pytest.mark.asyncio
    async def test_moat_analysis_incremental_roic_growth(self, mock_moat_repo):
        mock_moat_repo.get_financial_ratios_history = AsyncMock(return_value=[
            {"fiscal_year": y, "roic": 0.10 + n * 0.02,
             "gross_margin": 0.40, "operating_margin": 0.20,
             "net_margin": 0.10, "asset_turnover": 0.6}
            for n, y in enumerate(range(2019, 2025))
        ])
        wacc = MoatWaccService(mock_moat_repo)
        svc = MoatAnalysisService(mock_moat_repo, wacc)
        result = await svc.get_moat_analysis("AAPL")
        assert result.valuation.moat_score is not None
        assert result.valuation.roic_5y_avg is not None

    @pytest.mark.asyncio
    async def test_moat_analysis_incremental_roic_declining(self, mock_moat_repo):
        mock_moat_repo.get_financial_ratios_history = AsyncMock(return_value=[
            {"fiscal_year": y, "roic": 0.30 - n * 0.03,
             "gross_margin": 0.40, "operating_margin": 0.20,
             "net_margin": 0.10, "asset_turnover": 0.6}
            for n, y in enumerate(range(2019, 2025))
        ])
        wacc = MoatWaccService(mock_moat_repo)
        svc = MoatAnalysisService(mock_moat_repo, wacc)
        result = await svc.get_moat_analysis("AAPL")
        assert result.valuation.moat_score is not None
        assert result.valuation.moat_score < 70  # declining ROIC should lower score

    @pytest.mark.asyncio
    async def test_moat_analysis_fcf_negative_net_income(self, mock_moat_repo):
        mock_moat_repo.get_income_statements_annual = AsyncMock(return_value=[
            {"fiscal_year": 2024, "revenue": 100_000, "ebit": -5_000,
             "net_income": -5_000, "income_tax_expense": 0, "shares_outstanding_diluted": 1000},
        ])
        wacc = MoatWaccService(mock_moat_repo)
        svc = MoatAnalysisService(mock_moat_repo, wacc)
        result = await svc.get_moat_analysis("AAPL")
        assert result.valuation.moat_score is not None

    # ── Integration: Weak moat company ───────────────────────────────────

    @pytest.mark.asyncio
    async def test_moat_analysis_weak_moat(self, mock_moat_repo):
        mock_moat_repo.get_financial_ratios_history = AsyncMock(return_value=[
            {"fiscal_year": y, "roic": 0.03, "gross_margin": 0.15,
             "operating_margin": 0.02, "net_margin": 0.01, "asset_turnover": 0.2}
            for y in range(2019, 2025)
        ])
        wacc = MoatWaccService(mock_moat_repo)
        svc = MoatAnalysisService(mock_moat_repo, wacc)
        result = await svc.get_moat_analysis("WEAK")
        assert result.valuation.moat_category in ("None", "Narrow")
        assert result.valuation.moat_score < 50

    @pytest.mark.asyncio
    async def test_moat_analysis_force_recompute(self, mock_moat_repo):
        first = MagicMock()
        first.company_id = 1
        wacc = MoatWaccService(mock_moat_repo)
        svc = MoatAnalysisService(MagicMock(), wacc)
        mock_repo_with_cache = MagicMock()

        mock_repo_with_cache.get_company_context = MagicMock(return_value={
            "company_id": 1, "currency": "USD", "sector": "Technology",
            "industry": "Software", "ticker_symbol": "AAPL",
        })
        mock_repo_with_cache.get_financial_ratios_history = AsyncMock(return_value=[
            {"fiscal_year": 2024, "roic": 0.32, "gross_margin": 0.43,
             "operating_margin": 0.30, "net_margin": 0.25, "asset_turnover": 0.88},
        ])
        mock_repo_with_cache.get_income_statements_annual = AsyncMock(return_value=[
            {"fiscal_year": 2024, "revenue": 100_000, "ebit": 30_000,
             "net_income": 25_000, "income_tax_expense": 5_000, "shares_outstanding_diluted": 1000},
        ])
        mock_repo_with_cache.get_balance_sheet_latest = AsyncMock(return_value={
            "fiscal_year": 2024, "total_assets": 200_000,
            "shareholders_equity": 80_000, "total_debt": 40_000,
            "cash_and_cash_equivalents": 20_000,
        })
        mock_repo_with_cache.get_cash_flow_latest = AsyncMock(return_value={
            "fiscal_year": 2024, "cash_from_operating_activities": 35_000,
            "capital_expenditures": -8_000,
        })
        mock_repo_with_cache.get_company_summary_latest = AsyncMock(return_value={
            "market_cap": 500_000, "beta": 1.2,
        })
        mock_repo_with_cache.get_industry_multiples = AsyncMock(return_value=None)
        mock_repo_with_cache.get_moat_analysis = AsyncMock(return_value={
            "company_id": 1, "moat_score": 50.0, "moat_category": "Narrow",
            "computed_at": "2020-01-01T00:00:00Z", "data_sources": "test",
        })
        mock_repo_with_cache.upsert_moat_analysis = AsyncMock(return_value=True)

        svc2 = MoatAnalysisService(mock_repo_with_cache, wacc)

        result_normal = await svc2.get_moat_analysis("AAPL", force=False)
        assert result_normal is not None

        result_forced = await svc2.get_moat_analysis("AAPL", force=True)
        assert result_forced is not None

    @pytest.mark.asyncio
    async def test_moat_analysis_sector_excluded(self, mock_moat_repo):
        mock_moat_repo.get_company_context = MagicMock(return_value={
            "company_id": 1, "currency": "USD", "sector": "Financials",
            "industry": "Banking", "ticker_symbol": "JPM",
        })
        wacc = MoatWaccService(mock_moat_repo)
        svc = MoatAnalysisService(mock_moat_repo, wacc)
        result = await svc.get_moat_analysis("JPM")
        assert result is not None
        assert result.industry_context.sector == "Financials"
        assert result.valuation.moat_score is not None

    @pytest.mark.asyncio
    async def test_moat_analysis_canadian_stock(self, mock_moat_repo):
        mock_moat_repo.get_company_context = MagicMock(return_value={
            "company_id": 2, "currency": "CAD", "sector": "Technology",
            "industry": "Software", "ticker_symbol": "SHOP",
        })
        wacc = MoatWaccService(mock_moat_repo)
        svc = MoatAnalysisService(mock_moat_repo, wacc)
        result = await svc.get_moat_analysis("SHOP")
        assert result is not None
        assert result.currency == "CAD"
        assert result.valuation.moat_score is not None

    # ── NEG-01: Empty financial ratios ──────────────────────────────

    @pytest.mark.asyncio
    async def test_moat_analysis_empty_ratios(self, mock_moat_repo):
        mock_moat_repo.get_financial_ratios_history = AsyncMock(return_value=[])
        wacc = MoatWaccService(mock_moat_repo)
        svc = MoatAnalysisService(mock_moat_repo, wacc)
        result = await svc.get_moat_analysis("AAPL")
        assert result.valuation.moat_score is not None

    # ── NEG-02: Missing optional data (no BS, CF, or CS) ───────────

    @pytest.mark.asyncio
    async def test_moat_analysis_missing_optional_data(self, mock_moat_repo):
        mock_moat_repo.get_balance_sheet_latest = AsyncMock(return_value=None)
        mock_moat_repo.get_cash_flow_latest = AsyncMock(return_value=None)
        mock_moat_repo.get_company_summary_latest = AsyncMock(return_value=None)
        mock_moat_repo.get_industry_multiples = AsyncMock(return_value=None)
        wacc = MoatWaccService(mock_moat_repo)
        svc = MoatAnalysisService(mock_moat_repo, wacc)
        result = await svc.get_moat_analysis("AAPL")
        assert result is not None
        assert result.valuation.moat_score is not None

    # ── NEG-03: Extremely large ROIC ───────────────────────────────

    @pytest.mark.asyncio
    async def test_moat_analysis_extreme_roic(self, mock_moat_repo):
        mock_moat_repo.get_financial_ratios_history = AsyncMock(return_value=[
            {"fiscal_year": y, "roic": 5.0, "gross_margin": 0.90,
             "operating_margin": 0.80, "net_margin": 0.70, "asset_turnover": 2.5}
            for y in range(2019, 2025)
        ])
        wacc = MoatWaccService(mock_moat_repo)
        svc = MoatAnalysisService(mock_moat_repo, wacc)
        result = await svc.get_moat_analysis("AAPL")
        assert result.valuation.moat_score == 99.2

    # ── NEG-04: All zero values ────────────────────────────────────

    @pytest.mark.asyncio
    async def test_moat_analysis_all_zeros(self, mock_moat_repo):
        mock_moat_repo.get_financial_ratios_history = AsyncMock(return_value=[
            {"fiscal_year": y, "roic": 0.0, "gross_margin": 0.0,
             "operating_margin": 0.0, "net_margin": 0.0, "asset_turnover": 0.0}
            for y in range(2019, 2025)
        ])
        wacc = MoatWaccService(mock_moat_repo)
        svc = MoatAnalysisService(mock_moat_repo, wacc)
        result = await svc.get_moat_analysis("AAPL")
        assert result is not None
        assert result.valuation.moat_score >= 0

    # ── NEG-05: Unknown symbol raises ValueError ───────────────────

    @pytest.mark.asyncio
    async def test_moat_analysis_unknown_symbol(self, mock_moat_repo):
        mock_moat_repo.get_company_context = MagicMock(return_value=None)
        wacc = MoatWaccService(mock_moat_repo)
        svc = MoatAnalysisService(mock_moat_repo, wacc)
        with pytest.raises(ValueError, match="Symbol.*not found"):
            await svc.get_moat_analysis("NONEXIST")
