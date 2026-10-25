"""
OpenCode integration for keep-alive functionality.
Production-grade implementation with proper error handling, logging, and configuration.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from framework.integrations.base import (
    IntegrationHealth,
    IntegrationStatus,
    KeepAliveStrategy,
)


class OpenCodeKeepAliveStrategy(KeepAliveStrategy):
    """OpenCode-specific keep-alive strategy using location lease eviction."""
    
    DEFAULT_INTERVAL = 2700  # 45 minutes
    MIN_INTERVAL = 60
    MAX_INTERVAL = 3540  # Just under 60 minutes
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        super().__init__(config, logger)
        self._process: Optional[subprocess.Popen] = None
        self._pid_file: Optional[Path] = None
        self._cli_path: Optional[str] = None
    
    def is_enabled(self) -> bool:
        """Check if OpenCode keep-alive is enabled in configuration."""
        integrations = self.config.get("integrations", {})
        opencode = integrations.get("opencode", {})
        keepalive = opencode.get("keepalive", {})
        return bool(keepalive.get("enabled", False))
    
    def detect(self) -> bool:
        """Detect if OpenCode is available in the environment."""
        self._cli_path = self._find_cli()
        if not self._cli_path:
            self.logger.debug("OpenCode CLI not found")
            return False
        
        if not self._verify_api_available():
            self.logger.debug("OpenCode CLI found but API not available")
            return False
        
        self.logger.debug(f"OpenCode detected: {self._cli_path}")
        return True
    
    def _find_cli(self) -> Optional[str]:
        """Find OpenCode CLI with API support."""
        config_paths = []
        integrations = self.config.get("integrations", {})
        opencode = integrations.get("opencode", {})
        keepalive = opencode.get("keepalive", {})
        if keepalive.get("cli_path"):
            config_paths.append(keepalive.get("cli_path"))
        
        # Try config, common locations, then PATH
        candidates = config_paths + [
            os.environ.get("OPENCODE_CLI_PATH", ""),
            r"C:\nvm4w\nodejs\node_modules\@opencode\cli\bin\opencode.exe",
            "/usr/local/bin/opencode",
            "/usr/bin/opencode",
        ]
        
        for cand in candidates:
            if cand and os.path.isfile(cand):
                return cand
        
        # Try PATH but verify it's the right one
        on_path = shutil.which("opencode")
        if on_path:
            return on_path
        
        return None
    
    def _verify_api_available(self) -> bool:
        """Verify the CLI has the API subcommand."""
        if not self._cli_path:
            return False
        try:
            result = subprocess.run(
                [self._cli_path, "api", "get", "/api/info"],
                capture_output=True,
                text=True,
                timeout=10,
                env=dict(os.environ),
            )
            return result.returncode == 0 and "version" in result.stdout
        except (OSError, subprocess.SubprocessError):
            return False
    
    def _get_interval(self) -> int:
        """Get refresh interval from config."""
        integrations = self.config.get("integrations", {})
        opencode = integrations.get("opencode", {})
        keepalive = opencode.get("keepalive", {})
        interval = keepalive.get("interval_seconds", self.DEFAULT_INTERVAL)
        # Enforce bounds
        if interval < self.MIN_INTERVAL:
            interval = self.MIN_INTERVAL
        elif interval >= 3600:
            interval = self.MAX_INTERVAL
        return interval
    
    def _get_locations(self) -> List[str]:
        """Get locations to keep fresh."""
        integrations = self.config.get("integrations", {})
        opencode = integrations.get("opencode", {})
        keepalive = opencode.get("keepalive", {})
        locations = keepalive.get("locations", [])
        if not locations:
            locations = [os.getcwd()]
        return locations
    
    def start(self) -> bool:
        """Start the keep-alive daemon."""
        if not self.is_enabled():
            self.logger.warning("OpenCode keep-alive is disabled in configuration")
            return False
        
        if not self.detect():
            self.logger.error("OpenCode not detected or API not available")
            return False
        
        if self._running:
            self.logger.warning("OpenCode keep-alive already running")
            return True
        
        try:
            # Use the production script
            script_path = Path(__file__).parent.parent.parent / "scripts" / "opencode_ttl_refresh.py"
            if not script_path.exists():
                self.logger.error(f"Keep-alive script not found: {script_path}")
                return False
            
            interval = self._get_interval()
            locations = self._get_locations()
            
            args = [str(script_path), "--interval", str(interval)]
            for loc in locations:
                args.extend(["--locations", loc])
            if self._cli_path:
                args.extend(["--exe", self._cli_path])
            
            # Start as daemon (detached process)
            if os.name == 'nt':
                # Windows
                self._process = subprocess.Popen(
                    [sys.executable, *args],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                )
            else:
                # Unix
                self._process = subprocess.Popen(
                    [sys.executable, *args],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            
            self._running = True
            self.logger.info(f"OpenCode keep-alive started (interval={interval}s, pid={self._process.pid})")
            return True
        except Exception as e:
            self.logger.error(f"Failed to start OpenCode keep-alive: {e}", exc_info=True)
            return False
    
    def stop(self) -> bool:
        """Stop the keep-alive daemon."""
        if not self._running:
            return True
        
        try:
            if self._process:
                if os.name == 'nt':
                    self._process.terminate()
                else:
                    self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    if os.name == 'nt':
                        self._process.kill()
                    else:
                        self._process.kill()
                self._process = None
            
            self._running = False
            self.logger.info("OpenCode keep-alive stopped")
            return True
        except Exception as e:
            self.logger.error(f"Failed to stop OpenCode keep-alive: {e}", exc_info=True)
            return False
    
    def health(self) -> IntegrationHealth:
        """Get health status."""
        if not self.is_enabled():
            return IntegrationHealth(
                status=IntegrationStatus.DISABLED,
                healthy=True,
                message="OpenCode keep-alive disabled in configuration"
            )
        
        if not self.detect():
            return IntegrationHealth(
                status=IntegrationStatus.NOT_DETECTED,
                healthy=False,
                message="OpenCode not detected or API not available"
            )
        
        if self._running and self._process:
            if self._process.poll() is None:
                return IntegrationHealth(
                    status=IntegrationStatus.RUNNING,
                    healthy=True,
                    message=f"Running (pid={self._process.pid})",
                    details={"cli_path": self._cli_path, "interval": self._get_interval()}
                )
            else:
                self._running = False
                return IntegrationHealth(
                    status=IntegrationStatus.ERROR,
                    healthy=False,
                    message="Process died unexpectedly"
                )
        
        return IntegrationHealth(
            status=IntegrationStatus.STOPPED,
            healthy=True,
            message="Configured but not running"
        )


import sys  # Add at end for type checking
