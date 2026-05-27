from __future__ import annotations
import logging
from datetime import date
from typing import Any, Dict, List, Optional

from config import settings

logger = logging.getLogger(__name__)


class FilingSection:
    def __init__(
        self,
        section_id: str,
        label: str,
        text: str,
        filing_date: Optional[date] = None,
        accession_number: Optional[str] = None,
    ) -> None:
        self.section_id = section_id
        self.label = label
        self.text = text
        self.filing_date = filing_date
        self.accession_number = accession_number


class EdgarFilingService:
    def __init__(self) -> None:
        self._identity = settings.EDGAR_IDENTITY or "StockerPro user@example.com"

    async def fetch_tenk_sections(
        self, symbol: str, year: Optional[int] = None
    ) -> Dict[str, FilingSection]:
        try:
            from edgar import Company, set_identity

            set_identity(self._identity)
            company = Company(symbol)
            filings = company.get_filings(form="10-K")
            if not filings:
                logger.warning("No 10-K filings found for %s", symbol)
                return {}

            filing = filings[0]
            filing_date = None
            accession_number = None
            try:
                filing_date = filing.filing_date
                accession_number = filing.accession_number
            except Exception:
                pass

            sections: Dict[str, FilingSection] = {}

            obj = filing.obj()
            if obj is None:
                logger.warning("10-K object is None for %s", symbol)
                return {}

            for section_id, attr_name in [
                ("item_1_business", "business"),
                ("item_1a_risk_factors", "risk_factors"),
                ("item_7_mda", "management_discussion"),
            ]:
                try:
                    section_obj = getattr(obj, attr_name, None)
                    if section_obj is not None:
                        text = str(section_obj)
                        if len(text) > 50:
                            sections[section_id] = FilingSection(
                                section_id=section_id,
                                label=attr_name.replace("_", " ").title(),
                                text=text,
                                filing_date=filing_date,
                                accession_number=accession_number,
                            )
                except Exception as e:
                    logger.debug(
                        "Could not extract section %s for %s: %s",
                        section_id,
                        symbol,
                        e,
                    )

            proxy = self._fetch_proxy_statement(symbol, filings)
            if proxy:
                sections["proxy_statement"] = proxy

            return sections
        except ImportError:
            logger.warning("edgartools not installed; cannot fetch 10-K sections")
            return {}
        except Exception as e:
            logger.error(
                "fetch_tenk_sections failed for %s: %s", symbol, e, exc_info=True
            )
            return {}

    def _fetch_proxy_statement(
        self, symbol: str, filings: Any
    ) -> Optional[FilingSection]:
        try:
            from edgar import Company

            company = Company(symbol)
            proxy_filings = company.get_filings(form="DEF 14A")
            if not proxy_filings:
                return None
            proxy = proxy_filings[0]
            proxy_obj = proxy.obj()
            if proxy_obj is None:
                return None
            text = str(proxy_obj)
            if len(text) <= 50:
                return None
            filing_date = None
            accession_number = None
            try:
                filing_date = proxy.filing_date
                accession_number = proxy.accession_number
            except Exception:
                pass
            return FilingSection(
                section_id="proxy_statement",
                label="Proxy Statement",
                text=text,
                filing_date=filing_date,
                accession_number=accession_number,
            )
        except Exception as e:
            logger.debug("Could not fetch DEF 14A for %s: %s", symbol, e)
            return None

    async def fetch_tenk_text(
        self, symbol: str, year: Optional[int] = None
    ) -> Optional[str]:
        sections = await self.fetch_tenk_sections(symbol, year)
        if not sections:
            return None
        parts = []
        for section_id in ["item_1_business", "item_1a_risk_factors", "item_7_mda"]:
            sec = sections.get(section_id)
            if sec and sec.text:
                parts.append(f"=== {sec.label} ===\n{sec.text}")
        proxy = sections.get("proxy_statement")
        if proxy and proxy.text:
            parts.append(f"=== {proxy.label} ===\n{proxy.text}")
        return "\n\n".join(parts) if parts else None

    async def get_latest_filing_date(
        self, symbol: str
    ) -> Optional[date]:
        try:
            from edgar import Company, set_identity

            set_identity(self._identity)
            company = Company(symbol)
            filings = company.get_filings(form="10-K")
            if not filings:
                return None
            filing = filings[0]
            return filing.filing_date
        except Exception as e:
            logger.debug("get_latest_filing_date failed for %s: %s", symbol, e)
            return None
