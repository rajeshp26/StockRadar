"""I21 + I26 -- EDGAR client identity must not be logged raw or at INFO.

I21: ``EdgarToolsProvider created (identity=...)`` logged at INFO on every
construction (~6x/window). I26: the same line leaks the PII email
(``rajeshp01@gmail.com``) at INFO.

Professional handling: never emit the raw SEC identity (``Name local@domain``),
mask the identifying parts, and drop the per-construction line to DEBUG so it is
absent from normal INFO logs. These tests fail today (RED).
"""
from __future__ import annotations

import logging

from providers.edgar_provider import EdgarToolsProvider

PII_IDENTITY = "Rajesh rajeshp01@gmail.com"


def test_mask_identity_never_emits_local_part_or_name():
    masked = EdgarToolsProvider._mask_identity(PII_IDENTITY)
    assert "rajeshp01" not in masked
    assert "Rajesh" not in masked
    assert masked  # still useful for diagnostics (e.g. domain)


def test_construction_does_not_log_raw_identity_at_info(monkeypatch, caplog):
    # Avoid resolving real config; pass the identity explicitly.
    with caplog.at_level(logging.INFO, logger="providers.edgar_provider"):
        EdgarToolsProvider(identity=PII_IDENTITY)

    info = [r.message for r in caplog.records if r.levelno >= logging.INFO]
    assert not any("identity" in m.lower() for m in info), (
        f"raw identity logged at INFO: {info}"
    )
    assert not any("rajeshp01" in m for m in info)


def test_construction_log_is_debug_and_masked(monkeypatch, caplog):
    with caplog.at_level(logging.DEBUG, logger="providers.edgar_provider"):
        EdgarToolsProvider(identity=PII_IDENTITY)

    created = [r for r in caplog.records if "created" in r.message.lower()]
    assert created, "no construction log line at DEBUG"
    assert created[0].levelno == logging.DEBUG
    assert "rajeshp01" not in created[0].getMessage()
    assert "Rajesh" not in created[0].getMessage()


def test_set_identity_log_masks_pii(monkeypatch, caplog):
    provider = EdgarToolsProvider(identity=PII_IDENTITY)

    sent: list[str] = []

    class _FakeEdgar:
        @staticmethod
        def set_identity(identity: str) -> None:
            sent.append(identity)

    import sys

    monkeypatch.setitem(sys.modules, "edgar", _FakeEdgar)

    with caplog.at_level(logging.INFO, logger="providers.edgar_provider"):
        provider._ensure_initialized()

    # The real identity is still passed to the SDK (functionality preserved).
    assert sent == [PII_IDENTITY]
    # But no log line leaks it.
    assert not any("rajeshp01" in r.getMessage() for r in caplog.records)
    assert not any("Rajesh" in r.getMessage() for r in caplog.records)
