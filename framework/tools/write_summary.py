"""Plain-arg task summary writer.

Wrapper around `gsd_state.py write-summary` that builds the YAML payload
programmatically, so PowerShell 5.1 can never mangle quoted JSON/YAML (the
same failure mode the task_event.py and append_claim.py wrappers avoid).

Strict I8 seam (DID-012): the SUMMARY is a RENDER of derived state.
`status`, `position`, `derived_state`, and `next_action` are DERIVED by the
execution-position adapter from the task's lifecycle events -- never authored
here (there is deliberately no --status/--next-action flag; an authored field
is rejected, exit 1). Register the task first (task-register): write-summary
requires the contract (NOT_FOUND otherwise).

Usage (worker-facing - safe under PowerShell 5.1):
  python framework/tools/write_summary.py --task-id T-07 --agent implementer \
      --summary "..." \
      --files-changed "a.py,b.py" --tests-run "python framework/validate.py" \
      --tests-result pass
"""
import argparse
import subprocess
import sys

ADAPTER = [sys.executable, "framework/adapters/gsd_state.py"]


def _list(value: str) -> list:
    return [v.strip() for v in value.split(",") if v.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description="write a task summary")
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--agent", required=True)
    ap.add_argument("--summary", required=True)
    ap.add_argument("--files-changed", default="")
    ap.add_argument("--symbols-changed", default="")
    ap.add_argument("--contracts-touched", default="")
    ap.add_argument("--decisions-created", default="")
    ap.add_argument("--tests-added", default="")
    ap.add_argument("--tests-run", default="")
    ap.add_argument("--tests-result", default="pass", choices=("pass", "fail"))
    ap.add_argument("--evidence", default="")
    ap.add_argument("--impact-scope", default="local",
                    choices=("local", "component", "cross_component", "system"))
    ap.add_argument("--contract-change", default="false", choices=("true", "false"))
    ap.add_argument("--public-api-change", default="false", choices=("true", "false"))
    ap.add_argument("--risks", default="")
    ap.add_argument("--blockers", default="")
    a = ap.parse_args()

    lines = [
        f"task_id: {a.task_id}",
        f"agent: {a.agent}",
        f"summary: {a.summary}",
        f"files_changed: {_list(a.files_changed)}",
        f"symbols_changed: {_list(a.symbols_changed)}",
        f"contracts_touched: {_list(a.contracts_touched)}",
        f"decisions_created: {_list(a.decisions_created)}",
        "tests: {added: %s, run: %s, result: %s}"
        % (_list(a.tests_added), _list(a.tests_run), a.tests_result),
        f"evidence: {_list(a.evidence)}",
        "impact_rederived: {scope: %s, contract_change: %s, public_api_change: %s}"
        % (a.impact_scope, a.contract_change, a.public_api_change),
        f"risks: {_list(a.risks)}",
        f"blockers: {_list(a.blockers)}",
    ]
    payload = "\n".join(lines)

    p = subprocess.run(
        [*ADAPTER, "write-summary", "--task", a.task_id, "--json", payload],
        capture_output=True,
        text=True,
    )
    if p.stdout:
        sys.stdout.write(p.stdout)
    if p.stderr:
        sys.stderr.write(p.stderr)
    return p.returncode


if __name__ == "__main__":
    raise SystemExit(main())