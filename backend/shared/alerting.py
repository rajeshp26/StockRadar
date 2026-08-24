"""Alerting infrastructure: Slack webhook with retry and circuit breaker."""

import logging
import time
from datetime import datetime
from typing import Any

import httpx

from config import settings

logger = logging.getLogger("stockerpro.alerting")

RETRY_DELAYS_SECONDS = [1, 4, 16]
MAX_RETRIES = len(RETRY_DELAYS_SECONDS)
CIRCUIT_BREAKER_RESET_SECONDS = 300


class AlertLevel:
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class SlackAlerter:
    """Sends alerts via Slack webhook. Implements retry with exponential backoff
    and a circuit breaker to avoid flooding a dead webhook."""

    def __init__(self, webhook_url: str | None = None):
        self.webhook_url = webhook_url or getattr(settings, "SLACK_WEBHOOK_URL", None)
        self._circuit_open_until: datetime | None = None
        self._consecutive_failures = 0

    def _circuit_is_open(self) -> bool:
        if self._circuit_open_until is None:
            return False
        if time.time() >= self._circuit_open_until:
            self._circuit_open_until = None
            self._consecutive_failures = 0
            return False
        return True

    def send_alert(
        self,
        message: str,
        level: str = AlertLevel.INFO,
        title: str | None = None,
        blocks: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Send an alert to Slack. Returns True if sent successfully."""
        if not self.webhook_url:
            logger.warning(f"Alert suppressed (no webhook): {message}")
            return False

        if self._circuit_is_open():
            logger.warning(
                f"Circuit breaker open, suppressing alert: {message[:100]}"
            )
            return False

        payload = self._build_payload(message, level, title, blocks)

        for attempt in range(MAX_RETRIES):
            try:
                with httpx.Client(timeout=10.0) as client:
                    resp = client.post(self.webhook_url, json=payload)
                if resp.status_code == 200:
                    self._consecutive_failures = 0
                    logger.info(f"Alert sent: {message[:80]}")
                    return True
                elif resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", RETRY_DELAYS_SECONDS[attempt]))
                    logger.warning(f"Rate limited, retrying in {retry_after}s")
                    time.sleep(retry_after)
                else:
                    logger.warning(
                        f"Slack returned {resp.status_code}: {resp.text[:200]}"
                    )
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAYS_SECONDS[attempt])
            except Exception as e:
                logger.error(f"Slack send attempt {attempt + 1} failed: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAYS_SECONDS[attempt])

        self._consecutive_failures += 1
        if self._consecutive_failures >= 3:
            self._circuit_open_until = time.time() + CIRCUIT_BREAKER_RESET_SECONDS
            logger.error(
                f"Circuit breaker opened after {self._consecutive_failures} failures"
            )
        return False

    def alert_critical(self, message: str, title: str | None = None) -> bool:
        return self.send_alert(message, level=AlertLevel.CRITICAL, title=title)

    def alert_warning(self, message: str, title: str | None = None) -> bool:
        return self.send_alert(message, level=AlertLevel.WARNING, title=title)

    def alert_info(self, message: str, title: str | None = None) -> bool:
        return self.send_alert(message, level=AlertLevel.INFO, title=title)

    def _build_payload(
        self,
        message: str,
        level: str,
        title: str | None = None,
        blocks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        color_map = {
            AlertLevel.CRITICAL: "danger",
            AlertLevel.WARNING: "warning",
            AlertLevel.INFO: "good",
        }
        if blocks:
            return {"blocks": blocks, "text": message}

        return {
            "attachments": [{
                "color": color_map.get(level, "good"),
                "title": title or f"StockerPro Alert [{level.upper()}]",
                "text": message,
                "ts": int(time.time()),
            }]
        }
