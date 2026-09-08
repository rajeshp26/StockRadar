"""Correct the mis-budgeted T-06 registration.

T-06 inherited the implement-type default (900s wall) but the registered
objective is the full DID-007 delta, which T-05 carried with an explicit
2400s budget. Contracts are immutable -> supervisor-cancel the never-started
T-06 and register T-07 (retry_of T-06) with the explicit 2400s budget.
"""
import json
import subprocess
import sys

ADAPTER = [sys.executable, "framework/adapters/gsd_state.py"]


def run(*args, expect_ok=False):
    p = subprocess.run([*ADAPTER, *args], capture_output=True, text=True)
    print("$ gsd_state.py", " ".join(args))
    if p.stdout.strip():
        print(p.stdout.strip())
    if p.stderr.strip():
        print("STDERR:", p.stderr.strip())
    if p.returncode != 0:
        print("EXIT", p.returncode)
        if expect_ok:
            sys.exit(p.returncode)
    return p.returncode


# 1. Supervisor-cancel the never-started, mis-budgeted T-06
run("task-cancel", "--id", "T-06", "--json", json.dumps({
    "emitter": "team-lead",
    "detail": "cancelled before start: inherited 900s implement-type budget is too tight for the registered DID-007 delta objective; re-registered as T-07 with explicit 2400s",
}), expect_ok=True)

# 2. Register T-07 with explicit budgets, retry_of T-06
t07 = {
    "type": "implement",
    "agent": "implementer",
    "objective": (
        "Implement the DID-007 approved delta for the provenance/observability "
        "control plane: ENV- command-environment capture (record-env/check-env + "
        "execution_context.yaml canonical declarations), evidence env binding + "
        "disconfirmation vocab + derived confidence in claims ledger, "
        "background_task_id capture in task supervision, C0-C8 checkpoint "
        "vocabulary in task_types + delegation-protocol, behavioral tests in "
        "validate.py; full suite green"
    ),
    "expected_artifact": (
        "validate.py full suite exit 0 with new behavioral sections; "
        "execution_context.py record-env/check-env; claims/ledger.py ENV- "
        "validation + disconfirmation + confidence; gsd_state.py background_task_id "
        "+ write-decision id guard + list_tasks contract-peer exclusion; "
        "task_types.yaml checkpoints; delegation-protocol.md C0-C8"
    ),
    "session_id": "",
    "checkpoints": [
        "execution_context record-env/check-env + canonical yaml",
        "claims ledger env binding/disconfirmation/confidence",
        "gsd_state background_task_id + guards",
        "task_types + delegation-protocol vocab",
        "validate.py behavioral tests green",
    ],
    "allowed_tools": [
        "read", "edit", "write", "glob", "grep", "bash",
        "lsp_diagnostics", "lsp_symbols",
    ],
    "completion_criteria": [
        "record-env writes ENV- rows to contexts/environments.jsonl (interpreter path/version, cwd, git commit, dirty, os)",
        "check-env exits 0 match / 1 mismatch / 3 no canonical against execution_context.yaml",
        "ledger refuses unresolved ENV- ref (CLAIM_ENV_UNKNOWN); disconfirmation vocab enforced (CLAIM_BAD_DISCONFIRMATION, CLAIM_DISCONFIRMED_BUT_VERIFIED)",
        "confidence derived at analyse from evidence structure (LOW/MEDIUM/HIGH/VERY_HIGH), never stored",
        "task-register stores background_task_id; task-status surfaces it",
        "write-decision refuses a missing id (nonzero exit naming the arg)",
        "list_tasks enumerates no *.contract.json peers",
        "task_types.yaml per-type default checkpoints; delegation-protocol.md documents C0-C8 + background_task_id rule",
        "validate.py new behavioral sections pass; full suite exit 0; g11/g13 consistent with EXIT_CODES.md",
        "additive schema only; existing records stay readable",
    ],
    "failure_criteria": [
        "validate.py regression not fixable without breaking the EXIT_CODES contract",
        "edit permission denied",
        "unresolvable design ambiguity",
    ],
    "progress_timeout_s": 120,
    "max_duration_s": 2400,
    "retry_of": "T-06",
}
run("task-register", "--id", "T-07", "--json", json.dumps(t07), expect_ok=True)

print("EMIT_OK")