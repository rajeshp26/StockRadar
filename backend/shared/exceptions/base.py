from typing import Any, Dict, Optional

class AppException(Exception):
    """Base exception for all application exceptions"""
    status_code: int = 500
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

class BusinessLogicError(AppException):
    """Business rule violations"""
    status_code = 400

class ValidationError(BusinessLogicError):
    """Input validation errors"""
    pass

class NotFoundError(AppException):
    """Resource not found"""
    status_code = 404

class ConflictError(AppException):
    """Resource conflict (e.g., duplicate)"""
    status_code = 409

class UnauthorizedError(AppException):
    """Authentication failed"""
    status_code = 401

class ForbiddenError(AppException):
    """Authorization failed"""
    status_code = 403

class ExternalServiceError(AppException):
    """External service failures"""
    status_code = 503
