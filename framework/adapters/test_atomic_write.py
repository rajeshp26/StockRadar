#!/usr/bin/env python3
"""Regression tests for the bounded retry in execute.py::_replace_with_retry.

os.replace raises PermissionError on Windows when the target is held open without
FILE_SHARE_DELETE. _atomic_write had no retry, so every caller of the shared primitive
inherited the flakiness. These pin both halves of the fix: a transient violation
recovers, and a permanent OSError is neither retried nor masked.

Run: python framework/adapters/test_atomic_write.py
"""
from __future__ import annotations

import contextlib
import errno
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import execute  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))


def _temps(root: Path) -> list[str]:
    return sorted(p.name for p in root.iterdir() if p.name.endswith(".tmp"))


@contextlib.contextmanager
def _fake_replace(outcome):
    """Swap os.replace for a fake driven by outcome(attempt) -> None | BaseException.

    Only the replace step is faked. The temp file, the write, and the failure cleanup
    all run for real, so they are exercised rather than assumed.
    """
    real = os.replace
    calls: list[tuple[str, str]] = []

    def fake(src, dst):
        calls.append((str(src), str(dst)))
        err = outcome(len(calls) - 1)
        if err is not None:
            raise err
        return real(src, dst)

    os.replace = fake
    try:
        yield calls
    finally:
        os.replace = real


def _attempt(fn) -> BaseException | None:
    try:
        fn()
    except BaseException as exc:  # noqa: BLE001 - the raise IS the assertion
        return exc
    return None


def t_happy_path_writes_once() -> None:
    root = Path(tempfile.mkdtemp(prefix="atomic-happy-"))
    try:
        target = root / "state.json"
        with _fake_replace(lambda _n: None) as calls:
            execute._atomic_write(target, '{"a": 1}')
        check("clean write performs exactly one replace", len(calls) == 1, f"got {len(calls)}")
        check("clean write lands the body",
              target.read_text(encoding="utf-8") == '{"a": 1}')
        check("clean write leaves no temp file", _temps(root) == [], f"got {_temps(root)}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_transient_violation_recovers() -> None:
    root = Path(tempfile.mkdtemp(prefix="atomic-transient-"))
    try:
        target = root / "state.json"
        err = PermissionError(13, "Access is denied", str(target))
        with _fake_replace(lambda n: err if n < 2 else None) as calls:
            execute._atomic_write(target, "recovered")
        check("two transient violations are retried, not raised",
              target.read_text(encoding="utf-8") == "recovered")
        check("recovery costs one extra attempt per transient failure",
              len(calls) == 3, f"got {len(calls)}")
        check("recovery leaves no temp file", _temps(root) == [], f"got {_temps(root)}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_permanent_error_is_not_retried() -> None:
    root = Path(tempfile.mkdtemp(prefix="atomic-permanent-"))
    try:
        target = root / "state.json"
        err = OSError(errno.ENOSPC, "No space left on device")
        with _fake_replace(lambda _n: err) as calls:
            raised = _attempt(lambda: execute._atomic_write(target, "payload"))
        check("ENOSPC propagates as a plain OSError, not a PermissionError",
              isinstance(raised, OSError) and not isinstance(raised, PermissionError),
              f"got {type(raised).__name__ if raised else None}")
        check("a permanent failure is not retried (this is what blocks masking)",
              len(calls) == 1, f"got {len(calls)}")
        check("failed write leaves no temp file", _temps(root) == [], f"got {_temps(root)}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_persistent_violation_reraises_and_cleans_up() -> None:
    root = Path(tempfile.mkdtemp(prefix="atomic-persistent-"))
    try:
        target = root / "state.json"
        err = PermissionError(13, "Access is denied", str(target))
        with _fake_replace(lambda _n: err) as calls:
            raised = _attempt(lambda: execute._atomic_write(target, "payload"))
        check("a violation that never clears is re-raised, not swallowed",
              isinstance(raised, PermissionError),
              f"got {type(raised).__name__ if raised else None}")
        check("the retry bound is finite",
              len(calls) == execute._REPLACE_ATTEMPTS, f"got {len(calls)}")
        check("an exhausted retry does not publish a partial file", not target.exists())
        check("exhausted retry leaves no temp file", _temps(root) == [], f"got {_temps(root)}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main() -> int:
    for fn in (
        t_happy_path_writes_once,
        t_transient_violation_recovers,
        t_permanent_error_is_not_retried,
        t_persistent_violation_reraises_and_cleans_up,
    ):
        try:
            fn()
        except Exception as exc:  # a crashing test is a failing test
            check(fn.__name__, False, f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")

    failed = [r for r in RESULTS if not r[1]]
    for name, ok, detail in RESULTS:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not ok else ""))
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} atomic write tests passed")
    print("ATOMIC-WRITE-TESTS: " + ("PASS" if not failed else "FAIL"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
