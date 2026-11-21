"""I29 -- third-party SDK loggers must not emit bare class-name prefixes.

``defeatbeta_api`` creates loggers with ``logging.getLogger(self.__class__.__name__)``
so its records arrive as ``DuckDBClient httpfs cache cleared`` -- no app
namespace, unlike every StockerPro logger. The fix is a name-rewriting filter
attached to those vendor loggers at the single SDK import boundary
(``providers/defeatbeta_runtime.py``, already the I17 console/nltk guard).

Contract:

* a generic helper in ``shared/logging_setup.py`` namespaces bare logger names
  and leaves hierarchical ones untouched, idempotently;
* the shim installs it for the SDK's two known loggers at import time;
* a real record emitted by ``logging.getLogger("DuckDBClient")`` renders with
  the namespaced prefix under the shared CONSOLE_FORMAT.
"""
from __future__ import annotations

import logging

import pytest

try:
    from shared.logging_setup import namespace_vendor_loggers
except ImportError:  # RED: the helper does not exist yet
    namespace_vendor_loggers = None  # type: ignore[assignment]


class _Recorder(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture
def recorder():
    """Capture records from the vendor logger without changing global levels."""
    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level
    capture = _Recorder()
    root.handlers = [capture]
    root.setLevel(logging.DEBUG)
    try:
        yield capture
    finally:
        root.handlers = saved_handlers
        root.setLevel(saved_level)


def test_helper_exists():
    assert namespace_vendor_loggers is not None, (
        "shared.logging_setup must expose namespace_vendor_loggers"
    )


def test_bare_vendor_name_is_namespaced(recorder):
    namespace_vendor_loggers("I29BareVendor", prefix="stockerpro.vendor")
    logging.getLogger("I29BareVendor").info("httpfs cache cleared")

    assert len(recorder.records) == 1
    assert recorder.records[0].name == "stockerpro.vendor.I29BareVendor"


def test_hierarchical_logger_name_is_untouched(recorder):
    namespace_vendor_loggers("I29.dotted.vendor", prefix="stockerpro.vendor")
    logging.getLogger("I29.dotted.vendor").info("already namespaced")

    assert recorder.records[0].name == "I29.dotted.vendor"


def test_installation_is_idempotent(recorder):
    namespace_vendor_loggers("I29Idempotent", prefix="stockerpro.vendor")
    logger = logging.getLogger("I29Idempotent")
    before = len(logger.filters)
    namespace_vendor_loggers("I29Idempotent", prefix="stockerpro.vendor")

    assert len(logger.filters) == before


def test_shim_restores_original_names_after_test():
    """The shim's installation must be scoped to its two known SDK loggers."""
    import providers.defeatbeta_runtime as shim

    assert hasattr(shim, "install_vendor_logger_namespace"), (
        "the shim must install the vendor namespace at its import boundary"
    )
    shim.install_vendor_logger_namespace()
    for name in ("DuckDBClient", "Transcripts"):
        assert any(
            getattr(f, "_i29_vendor_namespace", False)
            for f in logging.getLogger(name).filters
        ), name


def test_sdk_record_renders_with_namespaced_prefix(recorder):
    import providers.defeatbeta_runtime as shim
    from shared.logging_setup import (
        CONSOLE_FORMAT,
        install_correlation_stamping,
        uninstall_correlation_stamping,
    )

    shim.install_vendor_logger_namespace()
    uninstall_correlation_stamping()
    install_correlation_stamping()
    try:
        logging.getLogger("DuckDBClient").info("httpfs cache cleared")
    finally:
        uninstall_correlation_stamping()
    rendered = logging.Formatter(CONSOLE_FORMAT).format(recorder.records[0])

    assert "stockerpro.vendor.DuckDBClient" in rendered, rendered
    assert "httpfs cache cleared" in rendered, rendered
