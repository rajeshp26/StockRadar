import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from datetime import date

from application.services.edgar_filing_service import EdgarFilingService, FilingSection


class MockTenK:
    def __init__(self):
        self.business = "Apple designs and manufactures smartphones. The company's proprietary iOS ecosystem creates significant switching costs. Apple holds a large patent portfolio."
        self.risk_factors = "The company faces intense competition. Rapid technological change could disrupt the business."
        self.management_discussion = "Revenue grew 8%. Customer retention rates remain above 90%. Operating margins improved."


@pytest.fixture(autouse=True)
def mock_edgar():
    """Mock edgar.Company and edgar.set_identity for all tests."""
    with patch("edgar.Company") as mock_company_cls, patch("edgar.set_identity"):
        mock_company = MagicMock()

        mock_filing = MagicMock()
        mock_filing.filing_date = date(2025, 9, 15)
        mock_filing.accession_number = "0000320193-25-000001"

        mock_tenk = MockTenK()
        mock_filing.obj.return_value = mock_tenk

        mock_filings = MagicMock()
        mock_filings.__getitem__.return_value = mock_filing
        mock_filings.__len__.return_value = 1
        mock_company.get_filings.return_value = mock_filings

        mock_company_cls.return_value = mock_company

        yield {
            "company_cls": mock_company_cls,
            "company": mock_company,
            "filing": mock_filing,
        }


class TestEdgarFilingService:
    def setup_method(self):
        self.service = EdgarFilingService()

    @pytest.mark.asyncio
    async def test_fetch_tenk_sections_returns_sections(self, mock_edgar):
        sections = await self.service.fetch_tenk_sections("AAPL")
        assert len(sections) >= 3
        assert "item_1_business" in sections
        assert "item_1a_risk_factors" in sections
        assert "item_7_mda" in sections
        assert len(sections["item_1_business"].text) > 50

    @pytest.mark.asyncio
    async def test_fetch_tenk_sections_no_filings(self, mock_edgar):
        mock_edgar["company"].get_filings.return_value = None
        sections = await self.service.fetch_tenk_sections("UNKNOWN")
        assert sections == {}

    @pytest.mark.asyncio
    async def test_fetch_tenk_sections_empty_filings(self, mock_edgar):
        empty = MagicMock()
        empty.__len__.return_value = 0
        empty.__getitem__.side_effect = IndexError("No items")
        mock_edgar["company"].get_filings.return_value = empty
        sections = await self.service.fetch_tenk_sections("EMPTY")
        assert sections == {}

    @pytest.mark.asyncio
    async def test_extract_item_1_business(self, mock_edgar):
        sections = await self.service.fetch_tenk_sections("AAPL")
        sec = sections.get("item_1_business")
        assert sec is not None
        assert "proprietary iOS ecosystem" in sec.text
        assert "switching costs" in sec.text

    @pytest.mark.asyncio
    async def test_extract_item_1a_risk_factors(self, mock_edgar):
        sections = await self.service.fetch_tenk_sections("AAPL")
        sec = sections.get("item_1a_risk_factors")
        assert sec is not None
        assert "competition" in sec.text.lower()

    @pytest.mark.asyncio
    async def test_extract_item_7_mda(self, mock_edgar):
        sections = await self.service.fetch_tenk_sections("AAPL")
        sec = sections.get("item_7_mda")
        assert sec is not None
        assert "retention" in sec.text.lower()

    @pytest.mark.asyncio
    async def test_fetch_tenk_text_combines_sections(self, mock_edgar):
        text = await self.service.fetch_tenk_text("AAPL")
        assert text is not None
        assert "Business" in text
        assert "Risk Factors" in text
        assert "switching costs" in text

    @pytest.mark.asyncio
    async def test_fetch_tenk_text_no_filing(self, mock_edgar):
        mock_edgar["company"].get_filings.return_value = None
        text = await self.service.fetch_tenk_text("UNKNOWN")
        assert text is None

    @pytest.mark.asyncio
    async def test_get_latest_filing_date(self, mock_edgar):
        result = await self.service.get_latest_filing_date("AAPL")
        assert result == date(2025, 9, 15)

    @pytest.mark.asyncio
    async def test_get_latest_filing_date_no_filing(self, mock_edgar):
        mock_edgar["company"].get_filings.return_value = None
        result = await self.service.get_latest_filing_date("UNKNOWN")
        assert result is None

    def test_filing_section_creation(self):
        section = FilingSection(
            section_id="item_1_business",
            label="Business",
            text="Company description text",
            filing_date=date(2025, 9, 15),
            accession_number="ACC-123",
        )
        assert section.section_id == "item_1_business"
        assert section.label == "Business"
        assert section.text == "Company description text"
        assert section.filing_date == date(2025, 9, 15)
        assert section.accession_number == "ACC-123"

    # ── NEG-EDGAR-01: Company with no filings ───────────────────────

    @pytest.mark.asyncio
    async def test_fetch_tenk_sections_company_not_found(self, mock_edgar):
        mock_edgar["company_cls"].side_effect = Exception("Company not found")
        sections = await self.service.fetch_tenk_sections("NONEXIST")
        assert sections == {}

    # ── NEG-EDGAR-02: Filing object has no obj method ──────────────

    @pytest.mark.asyncio
    async def test_fetch_tenk_sections_missing_obj(self, mock_edgar):
        mock_edgar["filing"].obj.side_effect = AttributeError("No obj method")
        sections = await self.service.fetch_tenk_sections("AAPL")
        assert sections == {}

    # ── NEG-EDGAR-03: get_filings raises exception ─────────────────

    @pytest.mark.asyncio
    async def test_fetch_tenk_sections_edgar_timeout(self, mock_edgar):
        mock_edgar["company"].get_filings.side_effect = TimeoutError("EDGAR timeout")
        sections = await self.service.fetch_tenk_sections("AAPL")
        assert sections == {}
