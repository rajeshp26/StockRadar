"""
Base classes for framework integrations.
All integrations must be opt-in, configurable, and follow production-grade patterns.
"""
from __future__ import annotations

import abc
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class IntegrationStatus(Enum):
    """Integration status."""
    UNKNOWN = "unknown"
    NOT_DETECTED = "not_detected"
    DISABLED = "disabled"
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"


@dataclass
class IntegrationHealth:
    """Health information for an integration."""
    status: IntegrationStatus
    healthy: bool
    message: str = ""
    details: Optional[Dict[str, Any]] = None


class KeepAliveStrategy(abc.ABC):
    """Abstract base class for keep-alive strategies."""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        self.config = config
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self._running = False
    
    @abc.abstractmethod
    def detect(self) -> bool:
        """Detect if this integration is applicable in the current environment."""
        raise NotImplementedError
    
    @abc.abstractmethod
    def is_enabled(self) -> bool:
        """Check if this integration is enabled in configuration."""
        raise NotImplementedError
    
    @abc.abstractmethod
    def start(self) -> bool:
        """Start the keep-alive strategy. Returns True if started successfully."""
        raise NotImplementedError
    
    @abc.abstractmethod
    def stop(self) -> bool:
        """Stop the keep-alive strategy. Returns True if stopped successfully."""
        raise NotImplementedError
    
    @abc.abstractmethod
    def health(self) -> IntegrationHealth:
        """Get health status of the strategy."""
        raise NotImplementedError
    
    @property
    def is_running(self) -> bool:
        return self._running
