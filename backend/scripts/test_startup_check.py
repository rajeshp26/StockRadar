"""Verify the startup hook: clean -> True, pipeline drift -> loud + fatal option.

Run: python scripts/test_startup_check.py
"""
from __future__ import annotations

import importlib.util
import os
import sys
from importlib import metadata
from pathlib import Path

TARGET = Path(__file__).resolve().parent / "preflight_dependencies.py"
REQ = Path(__file__).resolve().parent.parent / "requirements.txt"


def _load():
    spec = importlib.util.spec_from_file_location("_pf_s", TARGET)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _with_stub(mod, stub: dict[str, str | None], fatal: str | None = None):
    """Call startup_check with metadata stubbed; return (result, raised)."""
    real = metadata.version

    def fake(name: str):
        if name in stub:
            v = stub[name]
            if v is None:
                raise metadata.PackageNotFoundError(name)
            return v
        return real(name)

    if fatal is not None:
        os.environ["PRICE_PREFLIGHT_FATAL"] = fatal
    else:
        os.environ.pop("PRICE_PREFLIGHT_FATAL", None)

    metadata.version = fake  # type: ignore[assignment]
    raised: Exception | None = None
    result = None
    try:
        result = mod.startup_check()
    except Exception as e:  # noqa: BLE001
        raised = e
    finally:
        metadata.version = real  # type: ignore[assignment]
        os.environ.pop("PRICE_PREFLIGHT_FATAL", None)
    return result, raised


def main() -> int:
    mod = _load()
    fails: list[str] = []

    # Clean: stub every pin to its declared value -> True, no raise.
    pins = mod._parse_pins(REQ)
    res, raised = _with_stub(mod, dict(pins))
    if res is not True or raised:
        fails.append(f"clean env: expected True/no-raise, got {res}/{raised!r}")

    # Pipeline drift, non-fatal (default): False, banner, no raise.
    res, raised = _with_stub(mod, {"duckdb": "1.4.3", "defeatbeta-api": "0.0.50"})
    if res is not False or raised:
        fails.append(f"duckdb drift non-fatal: expected False/no-raise, got {res}/{raised!r}")

    # Pipeline drift, PRICE_PREFLIGHT_FATAL=1: MUST raise.
    res, raised = _with_stub(
        mod, {"duckdb": "1.4.3", "defeatbeta-api": "0.0.50"}, fatal="1")
    if not isinstance(raised, RuntimeError):
        fails.append(f"duckdb drift fatal: expected RuntimeError, got {raised!r}")

    # Non-critical drift, FATAL=1: must NOT raise (click is not price-critical).
    res, raised = _with_stub(mod, {"click": "0.0.1"}, fatal="1")
    if raised is not None:
        fails.append(f"click drift fatal: expected no raise, got {raised!r}")

    if fails:
        print("TEST FAILURES:")
        for f in fails:
            print("  -", f)
        return 1
    print("test_startup_check: 4/4 cases behaved as specified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
