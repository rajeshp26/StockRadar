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
import sys
from importlib import metadata
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
TARGET = SCRIPTS / "preflight_dependencies.py"
REQ = SCRIPTS.parent / "requirements.txt"


def _pins() -> dict[str, str]:
    """Parse the declared pins using the target module's own parser."""
    spec = importlib.util.spec_from_file_location("_pf_parse", TARGET)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod._parse_pins(REQ)  # type: ignore[attr-defined]


def _run_with(stub_versions: dict[str, str]) -> int:
    """Run the check with importlib.metadata.version stubbed for the WHOLE call.

    The stub must stay active while main() executes -- loading the module and
    then restoring metadata in a finally block leaves main() running against the
    real environment, which silently defeats every case.
    """
    import io
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

    metadata.version = fake  # type: ignore[assignment]
    argv = sys.argv
    sys.argv = ["preflight"]
    buf, real_out = io.StringIO(), sys.stdout
    sys.stdout = buf
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod.main()
    finally:
        sys.stdout = real_out
        sys.argv = argv
        metadata.version = real  # type: ignore[assignment]


def main() -> int:
    failures: list[str] = []

    # ── Case 1: the historical drift -> must fail with the FATAL banner ──
    code = _run_with({"duckdb": "1.4.3", "defeatbeta-api": "0.0.50"})
    if code != 1:
        failures.append(f"drifted duckdb/defeatbeta-api: expected exit 1, got {code}")

    # ── Case 2: correct pins -> must pass ──
    # Stub EVERY pinned package to its declared version, otherwise unrelated
    # real drift in this environment (e.g. click) fails the check regardless and
    # the case proves nothing about the duckdb detection under test.
    code = _run_with(dict(_pins()))
    if code != 0:
        failures.append(f"all pins correct: expected exit 0, got {code}")

    # ── Case 3: a pipeline-critical package missing entirely -> must fail ──
    code = _run_with({"duckdb": None})  # type: ignore[dict-item]
    if code != 1:
        failures.append(f"missing duckdb: expected exit 1, got {code}")

    # ── Case 4: unrelated package drifting must still be caught ──
    code = _run_with({"click": "0.0.1"})
    if code != 1:
        failures.append(f"drifted click: expected exit 1, got {code}")

    if failures:
        print("TEST FAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("test_preflight_dependencies: 4/4 cases behaved as specified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
