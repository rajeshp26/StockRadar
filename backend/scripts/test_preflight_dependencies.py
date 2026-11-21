"""Prove preflight_dependencies.py detects the exact outage it was written for.

A check that has never failed is not a verified check. Reinstalling duckdb 1.4.3
to test it for real would break the environment this work just repaired, so the
detector is exercised directly against the drifted pair via a stub metadata
module -- proving the comparison and the FATAL classification, not the pip state.

Red->green: the check must FAIL (exit 1, FATAL) when duckdb/defeatbeta-api are
drifted, and PASS (exit 0) when they match the declared pins.

Run:  python scripts/test_preflight_dependencies.py
"""
from __future__ import annotations

import importlib.util
import io
import os
import sys
from importlib import metadata
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
TARGET = SCRIPTS / "preflight_dependencies.py"
REQ = SCRIPTS.parent / "requirements.txt"
ENV_KEY = "PRICE_PREFLIGHT_FATAL"


def _pins() -> dict[str, str]:
    """Parse the declared pins using the target module's own parser."""
    spec = importlib.util.spec_from_file_location("_pf_parse", TARGET)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod._parse_pins(REQ)  # type: ignore[attr-defined]


def _load(stub_versions: dict[str, str], *, fatal: bool):
    """Load the target module with metadata.version and PRICE_PREFLIGHT_FATAL
    stubbed for the WHOLE subsequent call. Caller must restore via context."""
    real = metadata.version

    def fake(name: str) -> str:
        if name in stub_versions:
            v = stub_versions[name]
            if v is None:
                raise metadata.PackageNotFoundError(name)
            return v
        return real(name)

    spec = importlib.util.spec_from_file_location("_pf", TARGET)
    mod = importlib.util.module_from_spec(spec)

    had_env = ENV_KEY in os.environ
    old_env = os.environ.get(ENV_KEY)
    metadata.version = fake  # type: ignore[assignment]
    if fatal:
        os.environ[ENV_KEY] = "1"
    elif had_env:
        os.environ.pop(ENV_KEY, None)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod, real, had_env, old_env


def _restore(real, had_env, old_env) -> None:
    metadata.version = real  # type: ignore[assignment]
    if had_env:
        os.environ[ENV_KEY] = old_env  # type: ignore[assignment]
    else:
        os.environ.pop(ENV_KEY, None)


def _run_main(stub_versions: dict[str, str]) -> int:
    """Return the exit code of main() under the stubbed environment."""
    mod, real, had_env, old_env = _load(stub_versions, fatal=False)
    argv = sys.argv
    buf, real_out = io.StringIO(), sys.stdout
    sys.argv = ["preflight"]
    sys.stdout = buf
    try:
        return mod.main()
    finally:
        sys.stdout = real_out
        sys.argv = argv
        _restore(real, had_env, old_env)


def _startup(stub_versions: dict[str, str], *, fatal: bool) -> tuple[bool | None, str | None]:
    """Return (return_value, fatal_message). fatal_message is set if it raised."""
    mod, real, had_env, old_env = _load(stub_versions, fatal=fatal)
    try:
        try:
            result = mod.startup_check()
            return result, None
        except RuntimeError as exc:
            return None, str(exc)
    finally:
        _restore(real, had_env, old_env)


def main() -> int:
    failures: list[str] = []

    # ── Case 1: the historical drift -> must fail with the FATAL banner ──
    code = _run_main({"duckdb": "1.4.3", "defeatbeta-api": "0.0.50"})
    if code != 1:
        failures.append(f"drifted duckdb/defeatbeta-api: expected exit 1, got {code}")

    # ── Case 2: correct pins -> must pass ──
    # Stub EVERY pinned package to its declared version, otherwise unrelated
    # real drift in this environment fails the check regardless and the case
    # proves nothing about the duckdb detection under test.
    code = _run_main(dict(_pins()))
    if code != 0:
        failures.append(f"all pins correct: expected exit 0, got {code}")

    # ── Case 3: a pipeline-critical package missing entirely -> must fail ──
    code = _run_main({"duckdb": None})  # type: ignore[dict-item]
    if code != 1:
        failures.append(f"missing duckdb: expected exit 1, got {code}")

    # ── Case 4: unrelated package drifting must still be caught by main() ──
    code = _run_main({"click": "0.0.1"})
    if code != 1:
        failures.append(f"drifted click: expected exit 1, got {code}")

    # ── Case 5 (I11): extras-suffixed pins must be parsed and checked ──
    # requirements.txt declares `httpx[http2]==0.28.1`. The old regex ignored
    # any pin with `[extras]`, so drift in those packages was invisible.
    pins = _pins()
    for extras_pkg in ("httpx", "pyjwt", "urllib3"):
        if extras_pkg not in pins:
            failures.append(f"extras pin {extras_pkg!r} missing from parsed pins")
    code = _run_main({"httpx": "0.0.1"})
    if code != 1:
        failures.append(f"drifted extras-pinned httpx: expected exit 1, got {code}")

    # ── Case 6 (I11): critical drift is ALWAYS fatal without the flag ──
    result, msg = _startup({"duckdb": "1.4.3"}, fatal=False)
    if result is not None or not msg or "pipeline-critical" not in msg:
        failures.append(f"critical drift without flag: expected fatal raise, got {result!r}/{msg!r}")

    # ── Case 7 (I11): the flag makes NON-critical drift fatal ──
    # The old nested `if critical` was unreachable here, so this was silent.
    result, msg = _startup({"click": "0.0.1"}, fatal=True)
    if result is not None or not msg or "click" not in msg:
        failures.append(f"non-critical drift with flag: expected fatal raise naming click, got {result!r}/{msg!r}")

    # ── Case 8: non-critical drift WITHOUT the flag stays non-fatal ──
    result, msg = _startup({"click": "0.0.1"}, fatal=False)
    if result is not False or msg is not None:
        failures.append(f"non-critical drift without flag: expected (False, None), got ({result!r}, {msg!r})")

    if failures:
        print("TEST FAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("test_preflight_dependencies: 8/8 cases behaved as specified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
