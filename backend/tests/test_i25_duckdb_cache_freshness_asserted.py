"""I25 -- the DuckDB cache-freshness decision must be asserted, not just logged.

The worker log contains the SDK line::

    [INFO] DuckDBClient: Cache is up-to-date. Update time: <ts>

That line is *reported* by ``DuckDBClient._validate_httpfs_cache`` (installed
SDK ``defeatbeta_api/client/duckdb_client.py:64-94``). Before this file there was
no assertion anywhere in the suite that the decision behind that line actually
happens — yet I9 removed the application's own cache clear and declared the
SDK's init-time validation "the legitimate freshness mechanism". A log line is
not evidence of behaviour; this module makes the relied-on decision executable.

These tests pass against the installed SDK as-is: I25 is a verification gap,
not a behavioural defect. The correct closure is an executed assertion (the
same shape as I19), not a speculative change to third-party code. No runtime
freshness threshold is asserted because I19 established the daily publish lag
is expected; only the decision itself and the app path that triggers it are.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from providers.defeatbeta_runtime import import_sdk_module

_SDK_MODULE = "defeatbeta_api.client.duckdb_client"
_REMOTE_TS = "2026-11-14T05:08:50Z"


def _bare_client(logger: logging.Logger):
    """A real SDK client object without running its network-backed __init__."""
    module = import_sdk_module(_SDK_MODULE)
    client = module.DuckDBClient.__new__(module.DuckDBClient)
    client.logger = logger
    return client


def _remote_spec(value=_REMOTE_TS, side_effect=None):
    hf = MagicMock()
    getter = hf.return_value.get_data_update_time
    if side_effect is not None:
        getter.side_effect = side_effect
    else:
        getter.return_value = value
    return hf


def test_matching_cached_spec_is_accepted_without_clear(caplog):
    client = _bare_client(logging.getLogger("DuckDBClient"))
    with (
        patch(f"{_SDK_MODULE}.HuggingFaceClient", _remote_spec()),
        patch.object(client, "_read_cached_spec_update_time", return_value=_REMOTE_TS),
        patch.object(client, "_clear_cache") as clear,
        patch.object(client, "query") as query,
        caplog.at_level(logging.INFO, logger="DuckDBClient"),
    ):
        client._validate_httpfs_cache()

    clear.assert_not_called()
    query.assert_not_called()
    assert "Cache is up-to-date" in caplog.text
    assert _REMOTE_TS in caplog.text


def test_stale_cached_spec_is_cleared_and_redownloaded(caplog):
    client = _bare_client(logging.getLogger("DuckDBClient"))
    with (
        patch(f"{_SDK_MODULE}.HuggingFaceClient", _remote_spec()),
        patch.object(client, "_read_cached_spec_update_time", return_value="2026-10-01T00:00:00Z"),
        patch.object(client, "_clear_cache") as clear,
        patch.object(client, "query") as query,
        caplog.at_level(logging.INFO, logger="DuckDBClient"),
    ):
        client._validate_httpfs_cache()

    clear.assert_called_once_with()
    query.assert_called_once()
    assert "Cache refreshed" in caplog.text
    assert _REMOTE_TS in caplog.text


def test_remote_spec_failure_is_not_silently_accepted(caplog):
    """A failed freshness probe must raise, never log a false 'up-to-date'."""
    client = _bare_client(logging.getLogger("DuckDBClient"))
    with (
        patch(f"{_SDK_MODULE}.HuggingFaceClient", _remote_spec(side_effect=RuntimeError("HF down"))),
        patch.object(client, "_read_cached_spec_update_time", return_value=_REMOTE_TS),
        patch.object(client, "_clear_cache") as clear,
        patch.object(client, "query") as query,
        caplog.at_level(logging.INFO, logger="DuckDBClient"),
        pytest.raises(RuntimeError, match="HF down"),
    ):
        client._validate_httpfs_cache()

    clear.assert_not_called()
    query.assert_not_called()
    assert "Cache is up-to-date" not in caplog.text


async def test_app_warm_cache_triggers_the_validating_client_init():
    """The app path behind the log line reaches client init (where validation runs)."""
    from providers.defeat_beta_provider import DefeatBetaProvider

    fake_factory = MagicMock()
    with patch(
        "providers.defeatbeta_runtime.import_get_duckdb_client",
        return_value=fake_factory,
    ):
        await DefeatBetaProvider.warm_cache()

    fake_factory.assert_called_once_with()
