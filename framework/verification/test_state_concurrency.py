#!/usr/bin/env python3
"""Regression tests for the verification modules' state handling.

The three verification scripts (recovery, review_loop, suspicion_log) write
shared JSON state. Three defects lived in that code and none of them was
covered by any suite:

  EXT-CRITIQUE-03  state-root resolution shelled out to a bare `python3` and
                   addressed gsd_state.py relative to CWD, falling back to
                   `.planning` in silence. On a host where `python3` is not on
                   PATH, or when run from any directory but the repo root,
                   state was written to the wrong root with nothing reported.
  EXT-CRITIQUE-04  checkpoint/state/log writes used a truncating write, so a
                   concurrent reader could observe a partial file and read it
                   as absent (load_checkpoint answers None) rather than corrupt.
  EXT-CRITIQUE-05  review_loop mutated state with load->modify->save and no
                   lock, so two writers each read the same state and the
                   second write dropped the first writer's update.

Run: python framework/verification/test_state_concurrency.py
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import recovery  # noqa: E402
import review_loop  # noqa: E402
import suspicion_log  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))


def _isolate(root: Path) -> None:
    """Point every module at a scratch state root.

    Each module binds `state_root` by value at import, so the patch must be
    applied per module rather than to `_state` itself.
    """
    for mod in (recovery, review_loop, suspicion_log):
        mod.state_root = lambda: root


def t_state_root_survives_missing_cwd() -> None:
    """EXT-CRITIQUE-03: state root must not depend on the caller's directory."""
    import contextlib
    import io
    import os
    import _state

    resolved = _state.state_root()
    # Absolute, not repo-relative: the adapter prints ".planning", so an
    # unanchored return makes every caller's `state_root() / "verification" / ...`
    # land in the CALLER's .planning. That silent split is the defect.
    check("state root is absolute, not CWD-relative",
          resolved.is_absolute(), f"resolved={resolved}")
    scratch = Path(tempfile.mkdtemp(prefix="verif-cwd-"))
    prev = os.getcwd()
    buf = io.StringIO()
    try:
        os.chdir(scratch)
        with contextlib.redirect_stderr(buf):
            from_other_cwd = _state.state_root()
    finally:
        os.chdir(prev)
        shutil.rmtree(scratch, ignore_errors=True)
    check("state root is identical from an unrelated CWD",
          from_other_cwd == resolved, f"{resolved} vs {from_other_cwd}")
    check("state root resolves from an unrelated CWD without falling back",
          "could not resolve" not in buf.getvalue(),
          buf.getvalue().strip()[:120])


def t_state_root_reports_failure() -> None:
    """EXT-CRITIQUE-03: a failing adapter must warn, not silently fall back."""
    import io
    import contextlib
    import _state
    from framework.adapters import gsd_state

    orig = gsd_state.root
    try:
        def _unresolvable():
            raise RuntimeError("state root unavailable")

        gsd_state.root = _unresolvable
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            got = _state.state_root()
        check("unresolvable state root falls back to an absolute path",
              got == _state.FALLBACK and got.is_absolute(), str(got))
        check("unresolvable state root warns on stderr (no silent split)",
              "could not resolve the GSD state root" in buf.getvalue(),
              buf.getvalue().strip()[:160])
    finally:
        gsd_state.root = orig


def _write_retrying(path: Path, body: str, attempts: int = 60) -> None:
    """atomic_write, retried on the Windows reader-contention error.

    os.replace cannot overwrite a file an open handle holds, so on Windows a
    racing reader fails the writer with PermissionError. _atomic_write in
    adapters/execute.py has NO retry, which is a real open finding; retrying
    here is what lets the truncation guarantee below be asserted at all.
    """
    for _ in range(attempts):
        try:
            recovery.atomic_write(path, body)
            return
        except PermissionError:
            time.sleep(0.005)
    recovery.atomic_write(path, body)


def t_atomic_write_never_truncates() -> None:
    """EXT-CRITIQUE-04: a reader must never see a partial file."""
    root = Path(tempfile.mkdtemp(prefix="verif-atomic-"))
    try:
        _isolate(root)
        target = root / "probe.json"
        target.write_text(json.dumps({"v": "original"}), encoding="utf-8")

        observed: list[str] = []
        stop = False

        def writer() -> None:
            for i in range(60):
                _write_retrying(target, json.dumps({"v": "x" * 4000, "i": i}))

        def reader() -> None:
            nonlocal stop
            # Bounded and yielding: an unbounded busy-loop starves the writers
            # on the GIL and never lets the pool drain.
            n = 0
            while not stop and n < 500:
                n += 1
                time.sleep(0.001)
                try:
                    observed.append(target.read_text(encoding="utf-8"))
                except PermissionError:
                    # Windows: os.replace cannot overwrite a file another handle
                    # holds open, so an unsynchronised reader can fail the writer
                    # outright. Losing a sample is fine - the property under test
                    # is that no sample is ever a partial file.
                    continue

        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = [ex.submit(writer) for _ in range(3)]
            rf = ex.submit(reader)
            for f in futs:
                f.result()
            stop = True
            rf.result()

        bad = [o for o in observed if o and not _parses(o)]
        check("concurrent readers never observe a truncated write",
              not bad, f"{len(bad)} partial read(s), e.g. {bad[0][:80]!r}" if bad else "clean")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_atomic_write_after_reader_closes() -> None:
    """An open reader blocks os.replace on Windows; the write lands once it closes.

    The contention is platform-dependent, so it is recorded rather than
    asserted. What must hold everywhere is that the write completes and leaves
    a whole, current file once the reader is done.
    """
    root = Path(tempfile.mkdtemp(prefix="verif-winlock-"))
    try:
        target = root / "held.json"
        target.write_text(json.dumps({"v": 0}), encoding="utf-8")
        contended = False
        with target.open("r", encoding="utf-8") as held:
            held.read()
            try:
                recovery.atomic_write(target, json.dumps({"v": 1}))
            except PermissionError:
                contended = True
        recovery.atomic_write(target, json.dumps({"v": 2}))
        final = json.loads(target.read_text(encoding="utf-8"))
        check("write completes and leaves a whole file once the reader is closed",
              final.get("v") == 2, f"final={final} contended={contended}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _parses(raw: str) -> bool:
    try:
        json.loads(raw)
        return True
    except json.JSONDecodeError:
        return False


def t_recovery_roundtrip_and_unicode() -> None:
    """Atomic write must also survive non-ASCII state (write_text used locale encoding)."""
    root = Path(tempfile.mkdtemp(prefix="verif-recovery-"))
    try:
        _isolate(root)
        state = {"note": "resum\u00e9 \u2014 \u65e5\u672c\u8a9e", "round": 2}
        recovery.save_checkpoint("05-01", state)
        got = recovery.load_checkpoint("05-01")
        check("checkpoint round-trips", got is not None and got["state"] == state, str(got)[:120])
        check("checkpoint survives non-ASCII state", got is not None
              and got["state"]["note"] == state["note"], "utf-8 preserved")

        recovery.save_last_known_good("05-01", state)
        lkg = recovery.load_last_known_good("05-01")
        check("last-known-good round-trips", lkg is not None and lkg["state"] == state, str(lkg)[:120])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_review_loop_concurrent_writers() -> None:
    """EXT-CRITIQUE-05: concurrent round recordings must not drop updates."""
    root = Path(tempfile.mkdtemp(prefix="verif-reviewloop-"))
    try:
        _isolate(root)
        review_loop.start_review("05-02")

        def record(i: int) -> None:
            review_loop.record_round("05-02", 1, 1, [{"finding": f"f{i}"}])

        with ThreadPoolExecutor(max_workers=8) as ex:
            list(ex.map(record, range(24)))

        state = review_loop.load_state()
        rounds = state.get("05-02", {}).get("rounds", [])
        check("24 concurrent record-round calls keep all 24 rounds",
              len(rounds) == 24, f"got {len(rounds)}")
        findings = [f for r in rounds for f in r.get("findings", [])]
        check("no writer's finding was dropped",
              len(findings) == 24, f"got {len(findings)}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_review_loop_duplicate_start() -> None:
    root = Path(tempfile.mkdtemp(prefix="verif-dupstart-"))
    try:
        _isolate(root)
        review_loop.start_review("05-03")
        again = review_loop.start_review("05-03")
        check("second start on an in-progress loop is refused",
              "error" in again, str(again)[:120])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_suspicion_log_add_and_resolve() -> None:
    """A rewrite must not erase records that were appended before it."""
    root = Path(tempfile.mkdtemp(prefix="verif-suspicion-"))
    try:
        _isolate(root)
        first = suspicion_log.add({
            "suspicion_id": "SUSP-001", "task_id": "05-04", "reviewer": "reviewer",
            "suspicion": "stale evidence", "evidence_requested": "fresh run",
        })
        second = suspicion_log.add({
            "suspicion_id": "SUSP-002", "task_id": "05-04", "reviewer": "reviewer",
            "suspicion": "borrowed evidence", "evidence_requested": "fresh run",
        })
        check("two suspicions recorded", first == "SUSP-001" and second == "SUSP-002",
              f"{first},{second}")

        ok = suspicion_log.resolve("SUSP-001", "verifier", "re-run exit 0")
        records = suspicion_log.load()
        check("resolve returns True for an open suspicion", ok, str(ok))
        check("resolve preserves the other record (no truncation loss)",
              len(records) == 2, f"got {len(records)}")
        by_id = {r["suspicion_id"]: r for r in records}
        check("resolved suspicion is marked RESOLVED",
              by_id.get("SUSP-001", {}).get("status") == "RESOLVED",
              str(by_id.get("SUSP-001", {}).get("status")))
        check("untouched suspicion stays OPEN",
              by_id.get("SUSP-002", {}).get("status") == "OPEN",
              str(by_id.get("SUSP-002", {}).get("status")))
        check("open suspicion blocks completion",
              suspicion_log.check_task("05-04")["blocks_completion"] is True,
              "expected blocked")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_suspicion_log_concurrent_add_and_resolve() -> None:
    """Concurrent adds must mint unique ids, and a resolve must not drop an add.

    Both are read-modify-write hazards: add() derives its id from the highest
    existing SUSP-NNN, and resolve() rewrites the whole file.
    """
    root = Path(tempfile.mkdtemp(prefix="verif-suspicion-race-"))
    try:
        _isolate(root)
        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(
                lambda i: suspicion_log.add({
                    "task_id": "05-05", "reviewer": "reviewer",
                    "suspicion": f"concurrent {i}", "evidence_requested": "fresh run",
                }),
                range(24)))
        check("24 concurrent adds all survive", len(suspicion_log.load()) == 24,
              f"got {len(suspicion_log.load())}")
        check("24 concurrent adds mint 24 unique ids",
              len(set(ids)) == 24, f"{len(set(ids))} unique of {len(ids)}")

        with ThreadPoolExecutor(max_workers=8) as pool:
            futs = [pool.submit(suspicion_log.resolve, ids[0], "verifier", "exit 0")]
            futs += [pool.submit(suspicion_log.add, {
                "task_id": "05-05", "reviewer": "reviewer",
                "suspicion": f"late {i}", "evidence_requested": "fresh run",
            }) for i in range(12)]
            for f in futs:
                f.result()

        records = suspicion_log.load()
        late = [r for r in records if str(r.get("suspicion", "")).startswith("late ")]
        check("an add racing a resolve is not lost", len(late) == 12,
              f"got {len(late)} of 12")
        check("all 36 records survive the resolve rewrite", len(records) == 36,
              f"got {len(records)}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main() -> int:
    for fn in (
        t_state_root_survives_missing_cwd,
        t_state_root_reports_failure,
        t_atomic_write_never_truncates,
        t_atomic_write_after_reader_closes,
        t_recovery_roundtrip_and_unicode,
        t_review_loop_concurrent_writers,
        t_review_loop_duplicate_start,
        t_suspicion_log_add_and_resolve,
        t_suspicion_log_concurrent_add_and_resolve,
    ):
        try:
            fn()
        except Exception as exc:  # a crashing test is a failing test
            check(fn.__name__, False, f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")

    failed = [r for r in RESULTS if not r[1]]
    for name, ok, detail in RESULTS:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not ok else ""))
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} verification state tests passed")
    print("VERIFICATION-STATE-TESTS: " + ("PASS" if not failed else "FAIL"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
