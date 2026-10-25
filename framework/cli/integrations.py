"""
CLI commands for framework integrations.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import List

from framework import locate
from framework.integrations.base import IntegrationStatus
from framework.integrations.opencode.strategy import OpenCodeKeepAliveStrategy


def load_config() -> dict:
    """Load framework configuration."""
    try:
        config_path = locate.find_config()
        if config_path and config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def cmd_opencode(args: List[str]) -> int:
    """Manage OpenCode integration."""
    logger = logging.getLogger("framework.integrations.opencode")
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    config = load_config()
    strategy = OpenCodeKeepAliveStrategy(config, logger)
    
    if not args:
        print("Usage: framework integrations opencode <start|stop|status|enable|disable>")
        return 2
    
    cmd = args[0]
    
    if cmd == "status":
        health = strategy.health()
        print(f"Status: {health.status.value}")
        print(f"Healthy: {health.healthy}")
        print(f"Message: {health.message}")
        if health.details:
            for k, v in health.details.items():
                print(f"  {k}: {v}")
        return 0
    
    elif cmd == "enable":
        # Update config to enable
        print("To enable OpenCode keep-alive, add to framework.config.json:")
        print(json.dumps({
            "integrations": {
                "opencode": {
                    "keepalive": {
                        "enabled": True,
                        "interval_seconds": 2700
                    }
                }
            }
        }, indent=2))
        print("\nThen run: framework integrations opencode start")
        return 0
    
    elif cmd == "disable":
        print("To disable OpenCode keep-alive, set enabled: false in framework.config.json")
        return 0
    
    elif cmd == "start":
        if not strategy.is_enabled():
            print("ERROR: OpenCode keep-alive is disabled. Run 'framework integrations opencode enable' for instructions.")
            return 2
        if strategy.start():
            print("OpenCode keep-alive started")
            return 0
        else:
            print("Failed to start OpenCode keep-alive")
            return 1
    
    elif cmd == "stop":
        if strategy.stop():
            print("OpenCode keep-alive stopped")
            return 0
        else:
            print("Failed to stop OpenCode keep-alive")
            return 1
    
    else:
        print(f"Unknown command: {cmd}")
        return 2


def cmd_integrations(args: List[str]) -> int:
    """Manage framework integrations."""
    if not args:
        print("Usage: framework integrations <opencode|status> [args...]")
        return 2
    
    cmd = args[0]
    rest = args[1:]
    
    if cmd == "opencode":
        return cmd_opencode(rest)
    elif cmd == "status":
        config = load_config()
        logger = logging.getLogger("framework.integrations")
        strategy = OpenCodeKeepAliveStrategy(config, logger)
        health = strategy.health()
        print(f"OpenCode keep-alive: {health.status.value} ({health.message})")
        return 0
    else:
        print(f"Unknown integration: {cmd}")
        return 2


def main(argv: List[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    return cmd_integrations(argv)


if __name__ == "__main__":
    raise SystemExit(main())
