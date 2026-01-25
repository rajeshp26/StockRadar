"""
Custom exception hierarchy for Defeat Beta integration.
Organized by context: data fetching, validation, refresh, and provider-specific errors.
"""


class StockerProException(Exception):
    """Base exception for all StockerPro custom exceptions."""
    
    def __init__(self, message: str, error_code: str = None, details: dict = None):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)
    
    def __str__(self):
        if self.error_code:
            return f"[{self.error_code}] {self.message}"
        return self.message


# ============================================================================
# DATA FETCH EXCEPTIONS
# ============================================================================

class DataFetchException(StockerProException):
    """Base exception for all data fetch failures."""
    pass


# ============================================================================
# DEFEAT BETA PROVIDER EXCEPTIONS
# ============================================================================

class DefeatBetaException(DataFetchException):
    """Base exception for defeat-beta related errors."""
    pass


class FinancialsFetchTimeoutError(DefeatBetaException):
    """Raised when defeat-beta request times out."""
    
    def __init__(self, symbol: str, statement_type: str, timeout_seconds: int):
        super().__init__(
            message=f"Defeat-beta {statement_type} fetch for {symbol} timed out after {timeout_seconds}s",
            error_code="DEFEAT_BETA_TIMEOUT",
            details={
                "symbol": symbol,
                "statement_type": statement_type,
                "timeout_seconds": timeout_seconds
            }
        )


class PartialDataError(DefeatBetaException):
    """Raised when some financial statements succeed but others fail."""
    
    def __init__(self, symbol: str, succeeded: list[str], failed: list[str]):
        super().__init__(
            message=f"Partial data fetch for {symbol}: succeeded={len(succeeded)}, failed={len(failed)}",
            error_code="DEFEAT_BETA_PARTIAL_DATA",
            details={
                "symbol": symbol,
                "succeeded": succeeded,
                "failed": failed,
                "partial": True
            }
        )


class NoDataError(DefeatBetaException):
    """Raised when all financial fetch attempts fail."""
    
    def __init__(self, symbol: str, statement_types: list[str]):
        super().__init__(
            message=f"Failed to fetch any financial data for {symbol}. Attempted: {statement_types}",
            error_code="DEFEAT_BETA_NO_DATA",
            details={"symbol": symbol, "attempted_statements": statement_types}
        )


class DefeatBetaNetworkError(DefeatBetaException):
    """Raised when defeat-beta encounters network/connection issues."""
    
    def __init__(self, symbol: str, original_error: Exception):
        super().__init__(
            message=f"Network error fetching financials for {symbol}: {str(original_error)}",
            error_code="DEFEAT_BETA_NETWORK_ERROR",
            details={"symbol": symbol, "original_error": str(original_error)}
        )


class InvalidDefeatBetaResponse(DefeatBetaException):
    """Raised when defeat-beta returns unexpected data format."""
    
    def __init__(self, symbol: str, statement_type: str, reason: str):
        super().__init__(
            message=f"Invalid {statement_type} response for {symbol}: {reason}",
            error_code="DEFEAT_BETA_INVALID_RESPONSE",
            details={
                "symbol": symbol,
                "statement_type": statement_type,
                "reason": reason
            }
        )


class NextEarningsDateNotFoundError(DefeatBetaException):
    """Raised when defeat-beta calendar is empty."""
    
    def __init__(self, symbol: str):
        super().__init__(
            message=f"No next earnings date found for {symbol}",
            error_code="DEFEAT_BETA_NO_NEXT_EARNINGS",
            details={"symbol": symbol}
        )


# ============================================================================
# REFRESH & SCHEDULER EXCEPTIONS
# ============================================================================

class RefreshException(StockerProException):
    """Base exception for all refresh/scheduler failures."""
    pass


class SchedulerRefreshError(RefreshException):
    """Raised when scheduler fails to refresh a company."""
    
    def __init__(self, company_id: int, symbol: str, original_error: Exception):
        super().__init__(
            message=f"Scheduler refresh failed for {symbol} (ID: {company_id}): {str(original_error)}",
            error_code="SCHEDULER_REFRESH_ERROR",
            details={
                "company_id": company_id,
                "symbol": symbol,
                "original_error": str(original_error)
            }
        )


class CompanyNotFoundError(RefreshException):
    """Raised when attempting to refresh a company that doesn't exist."""
    
    def __init__(self, company_id: int, symbol: str = None):
        msg = f"Company not found: {symbol or f'ID {company_id}'}"
        super().__init__(
            message=msg,
            error_code="COMPANY_NOT_FOUND",
            details={"company_id": company_id, "symbol": symbol}
        )


class MaxRetriesExceededError(RefreshException):
    """Raised when max retry attempts exceeded."""
    
    def __init__(self, company_id: int, symbol: str, attempts: int, last_error: Exception):
        super().__init__(
            message=f"Max retries ({attempts}) exceeded for {symbol}: {str(last_error)}",
            error_code="MAX_RETRIES_EXCEEDED",
            details={
                "company_id": company_id,
                "symbol": symbol,
                "attempts": attempts,
                "last_error": str(last_error)
            }
        )


# ============================================================================
# DATA VALIDATION EXCEPTIONS
# ============================================================================

class DataValidationException(StockerProException):
    """Base exception for data validation failures."""
    pass


class InvalidFiscalPeriodError(DataValidationException):
    """Raised when fiscal period data is invalid."""
    
    def __init__(self, fiscal_year: int, fiscal_quarter: int = None):
        quarter_str = f"Q{fiscal_quarter}" if fiscal_quarter else "Annual"
        super().__init__(
            message=f"Invalid fiscal period: {quarter_str} {fiscal_year}",
            error_code="INVALID_FISCAL_PERIOD",
            details={"fiscal_year": fiscal_year, "fiscal_quarter": fiscal_quarter}
        )


class DuplicateDataError(DataValidationException):
    """Raised when attempting to store duplicate financial data."""
    
    def __init__(self, company_id: int, fiscal_year: int, fiscal_quarter: int = None):
        quarter_str = f"Q{fiscal_quarter}" if fiscal_quarter else "Annual"
        super().__init__(
            message=f"Duplicate data for {company_id}: {quarter_str} {fiscal_year}",
            error_code="DUPLICATE_DATA",
            details={
                "company_id": company_id,
                "fiscal_year": fiscal_year,
                "fiscal_quarter": fiscal_quarter
            }
        )