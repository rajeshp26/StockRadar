"""Console-safe import shim for the defeatbeta-api SDK.

The SDK's ``__init__`` prints an emoji banner (and downloads the nltk
``punkt_tab`` resource) at import time. On a Windows console using the cp1252
codec, printing the U+1F4C8 chart emoji raises ``UnicodeEncodeError`` and kills
the process before any provider code runs (RC9).

Every import from ``defeatbeta_api`` in StockerPro must go through this shim so
the import-time banner cannot crash the worker or the API.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

_console_guarded = False


def install_console_guard() -> None:
    """Reconfigure stdout/stderr to UTF-8 so the SDK banner cannot crash on
    cp1252 Windows consoles. Idempotent; safe when streams lack ``reconfigure``
    (e.g. some test harnesses or embedded consoles)."""
    global _console_guarded
    if _console_guarded:
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass  # encoding change is best-effort; never hard-fail on it
    _console_guarded = True


def import_ticker() -> Any:
    """Return the defeatbeta_api ``Ticker`` class after installing the console guard."""
    install_console_guard()
    from defeatbeta_api.data.ticker import Ticker

    return Ticker


def import_get_duckdb_client() -> Callable[..., Any]:
    """Return defeatbeta_api's ``get_duckdb_client`` factory after installing the
    console guard."""
    install_console_guard()
    from defeatbeta_api.client.duckdb_client import get_duckdb_client

    return get_duckdb_client


def import_sdk_module(module_name: str) -> Any:
    """Import an arbitrary top-level ``defeatbeta_api`` submodule after the guard.

    Used by call sites that reach into other SDK modules; keeps every import
    behind the same guard."""
    install_console_guard()
    import importlib

    return importlib.import_module(module_name)
