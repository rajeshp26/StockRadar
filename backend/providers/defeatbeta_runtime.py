"""Console-safe import shim for the defeatbeta-api SDK.

The SDK's ``__init__`` prints an emoji banner (and downloads the nltk
``punkt_tab`` resource) at import time. On a Windows console using the cp1252
codec, printing the U+1F4C8 chart emoji raises ``UnicodeEncodeError`` and kills
the process before any provider code runs (RC9). The nltk download is refused by
NLTK's proxy/SSRF guard in this environment, leaves empty dirs in temp and is
retried every boot; StockerPro never uses the SDK transcripts that need it (I17).

Every import from ``defeatbeta_api`` in StockerPro must go through this shim so
the import-time banner cannot crash the worker or the API, and the wasted nltk
download does not run.

Set ``DEFEATBETA_NLTK_DOWNLOAD=1`` to opt back into the SDK's download (for a
deployment that does use transcript analysis).
"""

from __future__ import annotations

import os
import sys
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from shared.logging_setup import namespace_vendor_loggers

if TYPE_CHECKING:
    from collections.abc import Callable

_console_guarded = False
_NLTK_OPT_IN_ENV = "DEFEATBETA_NLTK_DOWNLOAD"
# Both SDK loggers use logging.getLogger(self.__class__.__name__), so without
# I29 their records appear as bare "DuckDBClient" / "Transcripts" prefixes.
_VENDOR_LOGGERS = ("DuckDBClient", "Transcripts")
_VENDOR_NAMESPACE = "stockerpro.vendor"


def install_vendor_logger_namespace() -> None:
    """Namespace the SDK's bare class-name loggers (I29). Idempotent."""
    namespace_vendor_loggers(*_VENDOR_LOGGERS, prefix=_VENDOR_NAMESPACE)


install_vendor_logger_namespace()


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
            # Encoding change is best-effort; never hard-fail on it.
            with suppress(Exception):
                reconfigure(encoding="utf-8", errors="replace")
    _console_guarded = True


def _guarded_sdk_import(do_import: Callable[[], Any]) -> Any:
    """Run an SDK import with the console guard and (by default) no punkt_tab fetch.

    The SDK calls ``nltk.download('punkt_tab', download_dir=<temp>)`` at import.
    StockerPro never uses the transcript analysis that consumes punkt_tab, the
    download fails behind the proxy, and the result is never validated -- so we
    no-op it for the duration of the import and restore the real function after.
    The opt-in env var leaves the SDK's behaviour untouched for deployments that
    do need transcripts.
    """
    install_console_guard()
    if os.environ.get(_NLTK_OPT_IN_ENV, "").strip().lower() in ("1", "true", "yes"):
        return do_import()

    try:
        import nltk
    except ImportError:
        return do_import()  # no nltk -> SDK import will report its own error

    real_download = nltk.download

    def _no_download(*_args: Any, **_kwargs: Any) -> bool:
        return True

    nltk.download = _no_download  # type: ignore[assignment]
    try:
        return do_import()
    finally:
        nltk.download = real_download  # type: ignore[assignment]


def import_ticker() -> Any:
    """Return the defeatbeta_api ``Ticker`` class after installing the guards."""
    return _guarded_sdk_import(lambda: __import__(
        "defeatbeta_api.data.ticker", fromlist=["Ticker"]
    ).Ticker)


def import_get_duckdb_client() -> Callable[..., Any]:
    """Return defeatbeta_api's ``get_duckdb_client`` factory after the guards."""
    return _guarded_sdk_import(lambda: __import__(
        "defeatbeta_api.client.duckdb_client", fromlist=["get_duckdb_client"]
    ).get_duckdb_client)


def import_sdk_module(module_name: str) -> Any:
    """Import an arbitrary top-level ``defeatbeta_api`` submodule behind the guards.

    Used by call sites that reach into other SDK modules; keeps every import
    behind the same guard."""
    import importlib

    return _guarded_sdk_import(lambda: importlib.import_module(module_name))
