# backend/application/parsers/portfolio_parser.py
"""
Portfolio CSV Parser Framework

Architecture:
- Base parser interface defines common contract
- Each brokerage has a concrete parser (WealthsimpleParser, IBKRParser, etc.)
- Parsers normalize CSV data into standard transaction format
- Symbol mapping: CDR tickers (TSLA CDR) → underlying US ticker (TSLA)
"""

import csv
import io
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from shared.cdr_utils import CDR_PATTERNS as _SHARED_CDR_PATTERNS
from shared.portfolio_event_payload import csv_row_fingerprint

logger = logging.getLogger(__name__)


@dataclass
class ParsedTransaction:
    """Normalized transaction after parsing (before DB insertion)"""

    # Transaction identification
    transaction_date: date
    settlement_date: date | None
    account_external_id: str
    account_type: str  # TFSA, RRSP, non-registered, etc.

    # Activity classification
    activity_type: str  # Trade, MoneyMovement, BonusPayment, LegacyCorporateAction
    activity_sub_type: str | None  # BUY, SELL, EFT, TRANSFER, SPLIT
    direction: str | None  # LONG, SHORT

    # Security details (None for non-trade activities)
    symbol: str | None
    security_name: str | None

    # Financial details
    currency: str
    quantity: Decimal | None
    unit_price: Decimal | None
    commission: Decimal
    net_cash_amount: Decimal

    # Metadata
    raw_data: dict[str, Any]  # Original CSV row

    # Exchange override (e.g., "TOR" for CDR symbols detected during parsing)
    exchange_override: str | None = None

    # Stable identity for resumable imports (populated by the parser)
    row_fingerprint: str = ""
    fingerprint_occurrence: int = 0


@dataclass
class ParseResult:
    """Result of parsing a CSV file"""
    success: bool
    transactions: list[ParsedTransaction]
    errors: list[str]
    warnings: list[str]
    total_rows: int
    parsed_rows: int
    skipped_rows: int
    account_type_summary: dict[str, int]  # {account_type: count}


class PortfolioParserBase(ABC):
    """
    Base class for brokerage CSV parsers.
    
    Responsibilities:
    - Validate CSV structure
    - Parse rows into ParsedTransaction objects
    - Normalize symbols (CDR → underlying ticker)
    - Handle different account types
    - Validate data integrity
    """

    SUPPORTED_ACCOUNT_TYPES: list[str] = []
    REQUIRED_COLUMNS: list[str] = []

    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    @abstractmethod
    def parse_csv(self, csv_content: str, user_account_filter: list[str] | None = None) -> ParseResult:
        """
        Parse CSV content into transactions.
        
        Args:
            csv_content: Raw CSV file content as string
            user_account_filter: List of account types to import (e.g., ['TFSA', 'RRSP'])
                                If None, imports all supported account types
        
        Returns:
            ParseResult with transactions and any errors/warnings
        """
        pass

    @abstractmethod
    def normalize_symbol(self, symbol: str, security_name: str) -> str:
        """
        Normalize ticker symbol to match companies table.
        
        Examples:
            - "TSLA CDR (CAD Hedged)" → "TSLA"
            - "BBD.A" → "BBD-A" (if that's the format in companies)
        """
        pass

    def _parse_date(self, date_str: str | None) -> date | None:
        """Parse date string to date object. Returns None if empty/invalid."""
        if not date_str or not date_str.strip():
            return None
        try:
            return datetime.strptime(date_str.strip(), "%Y-%m-%d").replace(tzinfo=UTC).date()
        except ValueError:
            self.warnings.append(f"Invalid date format: {date_str}")
            return None

    def _parse_decimal(self, value: str | None) -> Decimal | None:
        """Parse numeric string to Decimal. Returns None if empty/invalid."""
        if not value or not str(value).strip():
            return None
        try:
            return Decimal(str(value).strip())
        except Exception:
            self.warnings.append(f"Invalid numeric value: {value}")
            return None

    def _validate_columns(self, headers: list[str]) -> bool:
        """Check if CSV has all required columns."""
        missing = set(self.REQUIRED_COLUMNS) - set(headers)
        if missing:
            self.errors.append(f"Missing required columns: {', '.join(missing)}")
            return False
        return True


class WealthsimpleParser(PortfolioParserBase):
    """
    Parser for Wealthsimple CSV exports.
    
    CSV Format (as of 2026):
        transaction_date,settlement_date,account_id,account_type,activity_type,
        activity_sub_type,direction,symbol,name,currency,quantity,unit_price,
        commission,net_cash_amount
    
    Account Types:
        - TFSA
        - RRSP
        - Non-registered
        - FHSA (First Home Savings Account, Canada)
    
    Activity Types:
        - Trade (BUY/SELL)
        - MoneyMovement (EFT, TRANSFER)
        - BonusPayment (AFFILIATE, REFERRAL)
        - LegacyCorporateAction (SPLIT)
        - Dividend (DIV, DIST)
    
    Symbol Normalization:
        - CDR tickers: "TSLA CDR (CAD Hedged)" → "TSLA"
        - Class shares: "BBD.A" → "BBD-A" (convert dot to hyphen)
    """

    SUPPORTED_ACCOUNT_TYPES = ["TFSA", "RRSP", "Non-registered", "FHSA"]

    # Wealthsimple renamed ``transaction_date`` to ``effective_date`` and added
    # ``effective_time`` / ``description`` columns. Both header generations are
    # accepted; whichever date column is present is resolved once per file.
    DATE_COLUMNS = ("transaction_date", "effective_date")
    REQUIRED_COLUMNS = [
        "account_id", "account_type", "activity_type", "currency", "net_cash_amount"
    ]

    # Rows of these types carry no cash amount. They are skipped with a warning
    # instead of failing the whole file; the replay engine cannot apply them to
    # holdings or cash, and silently coercing them to zero would hide that fact.
    NON_CASH_ACTIVITY_TYPES = frozenset({
        "CorporateAction", "LegacyCorporateAction", "Split", "StockDividend",
        "Correction", "OptionAssign", "OptionExpiry", "NonCashDistribution",
    })

    # CDR suffix patterns (Canadian Depositary Receipts)
    # Single source of truth: backend/shared/cdr_utils.py
    CDR_PATTERNS = _SHARED_CDR_PATTERNS

    def parse_csv(self, csv_content: str, user_account_filter: list[str] | None = None) -> ParseResult:
        """Parse Wealthsimple CSV export."""
        self.errors = []
        self.warnings = []
        transactions: list[ParsedTransaction] = []
        account_summary: dict[str, int] = {}
        fingerprint_counts: dict[str, int] = {}

        try:
            # A UTF-8 BOM is common in brokerage exports and would otherwise
            # turn the first header into "\ufeffeffective_date".
            csv_file = io.StringIO(csv_content.lstrip("\ufeff"))
            reader = csv.DictReader(csv_file)

            if not reader.fieldnames:
                return ParseResult(
                    success=False,
                    transactions=[],
                    errors=["CSV file is empty or has no headers"],
                    warnings=[],
                    total_rows=0,
                    parsed_rows=0,
                    skipped_rows=0,
                    account_type_summary={},
                )

            headers = list(reader.fieldnames)
            date_column = self._resolve_date_column(headers)
            if not date_column or not self._validate_columns(headers):
                return ParseResult(
                    success=False,
                    transactions=[],
                    errors=self.errors,
                    warnings=self.warnings,
                    total_rows=0,
                    parsed_rows=0,
                    skipped_rows=0,
                    account_type_summary={},
                )

            total_rows = 0
            skipped_rows = 0

            for row in reader:
                total_rows += 1

                # Skip empty rows
                if not any(row.values()):
                    skipped_rows += 1
                    continue

                # Skip CSV footer row ("As of 2026-05-10 13:55 GMT-04:00")
                raw_date = (row.get(date_column) or "").strip()
                if not re.match(r"^\d{4}-\d{2}-\d{2}", raw_date):
                    skipped_rows += 1
                    continue

                activity_type = (row.get("activity_type") or "").strip()
                account_type = (row.get("account_type") or "").strip()

                # Filter by account type
                if user_account_filter and account_type not in user_account_filter:
                    skipped_rows += 1
                    continue

                # Corporate actions have always been skipped: the replay engine
                # cannot apply them and they need manual adjustment.
                if activity_type in {"LegacyCorporateAction", "CorporateAction", "Split", "StockDividend"}:
                    self._warn_non_cash_row(activity_type, row)
                    skipped_rows += 1
                    continue

                # Other non-cash rows (quantity corrections, option events,
                # legacy actions) used to raise and abort the entire file.
                if (
                    activity_type in self.NON_CASH_ACTIVITY_TYPES
                    and not (row.get("net_cash_amount") or "").strip()
                ):
                    self._warn_non_cash_row(activity_type, row)
                    skipped_rows += 1
                    continue

                # Track account types
                account_summary[account_type] = account_summary.get(account_type, 0) + 1

                # Parse transaction
                try:
                    tx = self._parse_row(row, date_column=date_column)
                    occurrence = fingerprint_counts.get(tx.row_fingerprint, 0)
                    fingerprint_counts[tx.row_fingerprint] = occurrence + 1
                    tx.fingerprint_occurrence = occurrence
                    transactions.append(tx)
                except Exception as e:
                    self.errors.append(f"Row {total_rows}: {e!s}")
                    skipped_rows += 1

            success = len(self.errors) == 0
            parsed_rows = len(transactions)

            logger.info(
                f"Wealthsimple parse complete: {parsed_rows}/{total_rows} rows parsed, "
                f"{skipped_rows} skipped, {len(self.errors)} errors"
            )

            return ParseResult(
                success=success,
                transactions=transactions,
                errors=self.errors,
                warnings=self.warnings,
                total_rows=total_rows,
                parsed_rows=parsed_rows,
                skipped_rows=skipped_rows,
                account_type_summary=account_summary,
            )

        except Exception as e:
            logger.error(f"Wealthsimple parser failed: {e}")
            return ParseResult(
                success=False,
                transactions=[],
                errors=[f"Parse error: {e!s}"],
                warnings=self.warnings,
                total_rows=0,
                parsed_rows=0,
                skipped_rows=0,
                account_type_summary={},
            )

    def _resolve_date_column(self, headers: list[str]) -> str | None:
        """Return the date column used by this export, or record an error."""
        for column in self.DATE_COLUMNS:
            if column in headers:
                return column
        supported = ", ".join(self.DATE_COLUMNS)
        self.errors.append(f"Missing required columns: one of {supported}")
        return None

    def _warn_non_cash_row(self, activity_type: str, row: dict[str, str]) -> None:
        raw_symbol = (row.get("symbol") or "").strip() or None
        activity_sub = (row.get("activity_sub_type") or "").strip() or None
        self.warnings.append(
            f"Non-cash {activity_type} skipped (row: {activity_type}/{activity_sub} "
            f"for {raw_symbol or 'N/A'}) — manual adjustment may be needed"
        )

    def _parse_row(
        self, row: dict[str, str], *, date_column: str = "transaction_date"
    ) -> ParsedTransaction:
        """Parse a single CSV row into ParsedTransaction."""

        # Required fields
        transaction_date = self._parse_date(row.get(date_column))
        if not transaction_date:
            raise ValueError("Missing or invalid transaction_date")

        account_external_id = (row.get("account_id") or "").strip()
        if not account_external_id:
            raise ValueError("Missing account_id")

        account_type = (row.get("account_type") or "").strip()
        if not account_type:
            raise ValueError("Missing account_type")

        activity_type = (row.get("activity_type") or "").strip()
        if not activity_type:
            raise ValueError("Missing activity_type")

        currency = (row.get("currency") or "").strip() or "CAD"

        # Optional fields
        settlement_date = self._parse_date(row.get("settlement_date"))
        activity_sub_type = (row.get("activity_sub_type") or "").strip() or None
        direction = (row.get("direction") or "").strip() or None

        # Security details (only for trades)
        raw_symbol = (row.get("symbol") or "").strip() or None
        security_name = (row.get("name") or "").strip() or None

        # Detect CDR pattern in raw symbol or security name for exchange override
        exchange_override = None
        for candidate in [raw_symbol, security_name]:
            if candidate:
                for pattern in self.CDR_PATTERNS:
                    if re.search(pattern, candidate, re.IGNORECASE):
                        exchange_override = "TOR"
                        break
            if exchange_override:
                break

        # Normalize symbol (strips CDR suffix, converts dots to hyphens)
        symbol = None
        if raw_symbol:
            symbol = self.normalize_symbol(raw_symbol, security_name or "")

        # Financial details
        quantity = self._parse_decimal(row.get("quantity"))
        unit_price = self._parse_decimal(row.get("unit_price"))
        commission = self._parse_decimal(row.get("commission")) or Decimal("0")

        net_cash = self._parse_decimal(row.get("net_cash_amount"))
        if net_cash is None:
            raise ValueError("Missing or invalid net_cash_amount")

        identity = {
            "account_external_id": account_external_id,
            "transaction_date": transaction_date.isoformat(),
            "effective_time": (row.get("effective_time") or "").strip() or None,
            "activity_type": activity_type,
            "activity_sub_type": activity_sub_type,
            "direction": direction,
            "symbol": symbol,
            "security_name": security_name,
            "currency": currency,
            "quantity": quantity,
            "unit_price": unit_price,
            "commission": commission,
            "net_cash_amount": net_cash,
            "description": (row.get("description") or "").strip() or None,
        }

        return ParsedTransaction(
            transaction_date=transaction_date,
            settlement_date=settlement_date,
            account_external_id=account_external_id,
            account_type=account_type,
            activity_type=activity_type,
            activity_sub_type=activity_sub_type,
            direction=direction,
            symbol=symbol,
            security_name=security_name,
            currency=currency,
            quantity=quantity,
            unit_price=unit_price,
            commission=commission,
            net_cash_amount=net_cash,
            exchange_override=exchange_override,
            raw_data=dict(row),  # Store original row
            row_fingerprint=csv_row_fingerprint(identity),
        )

    def normalize_symbol(self, symbol: str, security_name: str) -> str:
        """
        Normalize Wealthsimple ticker symbols.
        
        Rules:
        1. Remove CDR suffixes: "TSLA CDR (CAD Hedged)" → "TSLA"
        2. Convert dots to hyphens: "BBD.A" → "BBD-A"
        3. Uppercase and trim
        
        Args:
            symbol: Raw ticker from CSV
            security_name: Full security name (used for context)
        
        Returns:
            Normalized ticker symbol
        """
        normalized = symbol.strip().upper()

        # Remove CDR suffixes
        for pattern in self.CDR_PATTERNS:
            normalized = re.sub(pattern, "", normalized, flags=re.IGNORECASE)

        # Convert dots to hyphens (for class shares like BBD.A → BBD-A)
        normalized = normalized.replace(".", "-")

        # Trim again after replacements
        normalized = normalized.strip()

        if not normalized:
            logger.warning(f"Symbol normalization resulted in empty string: {symbol}")
            return symbol.upper().strip()

        logger.debug(f"Symbol normalized: {symbol} → {normalized}")
        return normalized


# The brokerages table contains legacy labels such as ``WS_TRADE`` while the
# parser registry and the stable CSV idempotency keys use ``wealthsimple``.
# Canonicalising here means selecting "Wealthsimple Trade" in the UI imports
# through the same brokerage/parser and resumes against the same events instead
# of creating a second copy of every row.
_BROKERAGE_ALIASES = {
    "ws_trade": "wealthsimple",
    "wealthsimple_trade": "wealthsimple",
}


def canonical_brokerage_code(brokerage_code: str) -> str:
    """Return the canonical code used for lookup, parsing and event keys."""
    normalized = re.sub(r"[\s\-]+", "_", (brokerage_code or "").strip().lower())
    return _BROKERAGE_ALIASES.get(normalized, normalized)


# Factory function for getting the correct parser
def get_parser(brokerage_code: str) -> PortfolioParserBase:
    """
    Factory function to get the appropriate parser for a brokerage.
    
    Args:
        brokerage_code: Brokerage identifier ('wealthsimple', 'ibkr', etc.)
    
    Returns:
        Parser instance
    
    Raises:
        ValueError: If brokerage is not supported
    """
    parsers = {
        "wealthsimple": WealthsimpleParser,
        # Add more as they're implemented:
        # "ibkr": IBKRParser,
        # "questrade": QuestradeParser,
    }

    parser_class = parsers.get(canonical_brokerage_code(brokerage_code))
    if not parser_class:
        raise ValueError(
            f"Unsupported brokerage: {brokerage_code}. "
            f"Supported: {', '.join(parsers.keys())}"
        )

    return parser_class()
