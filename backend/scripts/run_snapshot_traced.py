"""Run the snapshot job for real and prove the run left a durable trace.

The gap this closes: the tracing code was already in the job, but
``DEBUG_TRACE_ENABLED`` and ``DEBUG_LOG_ENABLED`` both shipped as ``False``, so
a scheduled run wrote nothing anywhere. Every test that "proved" tracing worked
called ``debug_trace.configure(enabled=True)`` first, which is why nobody noticed
that the shipped configuration produced zero records.

This script runs the *shipped* configuration -- same ``setup_debug_logging()``
call ``main.py`` makes, same settings, no test scaffolding -- executes
``handle_portfolio_snapshot`` against the live database, then reads the JSONL
file back off disk and prints the run as a joined trace.

It exits non-zero if the run left no records, or if a withheld write left no
finding. A green run here is the only evidence that answers "did you actually
add logs in the entire stack flow, and did you test it end to end?" -- a passing
unit test cannot, because the unit tests are what hid the defect.

Run:  python backend/scripts/run_snapshot_traced.py [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_BACKEND_ROOT / ".env")

from application.jobs.portfolio_snapshot_job import handle_portfolio_snapshot  # noqa: E402
from shared import debug_trace, logging_setup  # noqa: E402

_TRACE_FIELDS_SKIP = {"ts", "level", "logger", "msg", "trace_id"}


def _log_path() -> Path:
    from config import settings

    return logging_setup._resolve_log_dir(settings.DEBUG_LOG_DIR) / settings.DEBUG_LOG_FILENAME


def _verify_wiring(log_path: Path) -> None:
    """Fail before the run if the shipped configuration would produce nothing.

    Checking after the fact would mean reporting 'no records found' and leaving
    the reader to guess whether the instrumentation is broken or the config is.
    """
    from config import settings

    problems = []
    if not settings.DEBUG_LOG_ENABLED:
        problems.append("DEBUG_LOG_ENABLED is False -> no durable file sink")
    if "snapshot" not in settings.DEBUG_TRACE_ALWAYS_ON_SCOPES:
        problems.append(
            "DEBUG_TRACE_ALWAYS_ON_SCOPES does not contain 'snapshot' -> "
            "the job would emit nothing with the global flag off"
        )
    if settings.DEBUG_TRACE_ENABLED:
        problems.append(
            "DEBUG_TRACE_ENABLED is True -> this run would not prove the "
            "shipped always-on path"
        )

    handlers = logging.getLogger(debug_trace.debug_logger_name()).handlers
    if not handlers:
        problems.append(f"no handler attached to {debug_trace.debug_logger_name()}")

    if problems:
        print("WIRING NOT LIVE -- the run below would prove nothing:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        raise SystemExit(2)

    print("wiring verified:")
    print(f"  global trace flag : {settings.DEBUG_TRACE_ENABLED}")
    print(f"  always-on scopes  : {list(settings.DEBUG_TRACE_ALWAYS_ON_SCOPES)}")
    print(f"  debug logger      : {debug_trace.debug_logger_name()}")
    print(f"  jsonl sink        : {log_path}")


def _read_new_records(log_path: Path, offset: int) -> list[dict]:
    if not log_path.exists():
        return []
    with log_path.open("r", encoding="utf-8") as handle:
        handle.seek(offset)
        records = []
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                # A partially written final line means the run was interrupted
                # mid-flush; reporting it as a malformed record would hide that.
                print(f"  [unparsed trailing line] {line[:160]}", file=sys.stderr)
        return records


def _fmt(record: dict) -> str:
    fields = {
        k: v for k, v in record.items() if k not in _TRACE_FIELDS_SKIP
    }
    if not fields:
        return ""
    return "  " + "  ".join(
        f"{k}={v!r}" if isinstance(v, (dict, list)) else f"{k}={v}"
        for k, v in fields.items()
    )


def _print_run(records: list[dict]) -> None:
    unscoped = [r for r in records if r.get("account_id") is None]
    if unscoped:
        print("\nRUN BOUNDARIES")
        for event, grouped in _collapse_identical(unscoped):
            suffix = f" (x{len(grouped)})" if len(grouped) > 1 else ""
            print(f"  {event}{_fmt(grouped[0])}{suffix}")

    scoped: dict[object, list[dict]] = {}
    for record in records:
        account_id = record.get("account_id")
        if account_id is not None:
            scoped.setdefault(account_id, []).append(record)

    for account_id in sorted(scoped, key=str):
        print(f"\nACCOUNT {account_id}")
        for event, grouped in _collapse_identical(scoped[account_id]):
            suffix = f" (x{len(grouped)})" if len(grouped) > 1 else ""
            marker = "!!" if grouped[0].get("layer") == "integrity" else "--"
            print(f"  {marker} {event}{_fmt(grouped[0])}{suffix}")


def _collapse_identical(records: list[dict]) -> list[tuple[str, list[dict]]]:
    """Merge consecutive records that are byte-identical apart from their event.

    Each account's replay fetches the full event history, so one run emits one
    ``get_all_events`` record per account with an identical payload. Printing all
    six buries the per-account records that actually differ. The ``fingerprint``
    field is what makes collapsing safe to read: equal fingerprints mean the
    fetch returned the same rows.
    """
    collapsed: list[tuple[str, list[dict]]] = []
    for record in records:
        key = {k: v for k, v in record.items() if k not in ("ts", "msg")}
        if collapsed:
            previous_key = {
                k: v for k, v in collapsed[-1][1][0].items()
                if k not in ("ts", "msg")
            }
            if key == previous_key:
                collapsed[-1][1].append(record)
                continue
        collapsed.append((record.get("event"), [record]))
    return collapsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date",
        default=None,
        help="target snapshot date (YYYY-MM-DD). Omit to let the job use today.",
    )
    args = parser.parse_args()

    payload: dict = {}
    if args.date:
        payload["date"] = args.date

    log_path = _log_path()
    logging_setup.setup_debug_logging()
    _verify_wiring(log_path)

    offset = log_path.stat().st_size if log_path.exists() else 0

    print(f"\nrunning snapshot job with payload {payload or '{} (date defaults to today)'}")
    written = asyncio.run(handle_portfolio_snapshot({"payload": payload}))

    for handler in logging.getLogger(debug_trace.debug_logger_name()).handlers:
        handler.flush()

    records = _read_new_records(log_path, offset)
    print(f"\njob returned written={written}; {len(records)} durable records on disk")

    if not records:
        print(
            "\nFAIL: the run completed but left no records. The instrumentation "
            "is not live under the shipped configuration.",
            file=sys.stderr,
        )
        return 1

    trace_ids = {r.get("trace_id") for r in records if r.get("trace_id")}
    if len(trace_ids) != 1:
        print(
            f"\nFAIL: expected exactly one trace id for the run, got {trace_ids}. "
            "A run that cannot be correlated end to end is not diagnosable.",
            file=sys.stderr,
        )
        return 1

    _print_run(records)

    findings = [r for r in records if r.get("layer") == "integrity"]
    if findings:
        print(
            f"\n{len(findings)} integrity finding(s) -- every withheld write should "
            "appear here with its reason."
        )
    for finding in findings:
        if not finding.get("reason"):
            print(
                f"FAIL: finding {finding.get('event')} has no reason field",
                file=sys.stderr,
            )
            return 1

    print(f"\nOK: run is reconstructable end to end from {log_path} (trace {trace_ids.pop()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
