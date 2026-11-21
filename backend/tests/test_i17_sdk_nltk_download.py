"""I17 -- the SDK's import-time punkt_tab download must not run for StockerPro.

`defeatbeta_api/__init__.py` unconditionally calls
``nltk.download('punkt_tab', download_dir=<temp>)`` at import time. In this
environment the download is refused by NLTK's SSRF/proxy guard, leaves empty
directory trees in temp, and is retried every process boot. StockerPro never
uses the SDK's transcript analysis (the only consumer of punkt_tab), so this is
pure overhead and log noise. The SDK import boundary is `defeatbeta_runtime`,
so the suppression must live there.

These tests drive a fresh SDK import with a spy on nltk.download so they are
valid before and after the fix.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock


def _clear_sdk_modules() -> None:
    for name in [n for n in sys.modules if n == "defeatbeta_api" or n.startswith("defeatbeta_api.")]:
        del sys.modules[name]


def _fresh_import_via_shim() -> None:
    _clear_sdk_modules()
    from providers.defeatbeta_runtime import import_ticker

    import_ticker()


def test_sdk_import_via_shim_does_not_call_nltk_download():
    """RED: a fresh SDK import through the shim must not download punkt_tab."""
    import nltk

    spy = MagicMock(name="nltk.download")
    real = nltk.download
    try:
        nltk.download = spy  # type: ignore[assignment]
        _fresh_import_via_shim()
    finally:
        nltk.download = real  # type: ignore[assignment]

    spy.assert_not_called()


def test_shim_restores_nltk_download_after_import():
    """The shim must not leave nltk.download patched for unrelated callers."""
    import nltk

    real = nltk.download
    _fresh_import_via_shim()
    assert nltk.download is real


def test_opt_in_lets_sdk_download_run(monkeypatch):
    """DEFEATBETA_NLTK_DOWNLOAD=1 preserves the SDK's own behaviour."""
    import nltk

    spy = MagicMock(name="nltk.download")
    real = nltk.download
    monkeypatch.setenv("DEFEATBETA_NLTK_DOWNLOAD", "1")
    try:
        nltk.download = spy  # type: ignore[assignment]
        _clear_sdk_modules()
        from providers.defeatbeta_runtime import import_ticker

        import_ticker()
    finally:
        nltk.download = real  # type: ignore[assignment]

    spy.assert_called_once()
