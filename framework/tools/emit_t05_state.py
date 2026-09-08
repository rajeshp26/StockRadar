"""One-shot state records for the T-05 background-worker incident.

Calls the gsd_state adapter with json.dumps payloads - the proven transport,
because PowerShell 5.1 mangles inline --json '{...}' single-quote JSON
(BLOCKER_INVALID_JSON / TASK_INVALID_JSON previously).

Records:
  1. write-blocker WORKER_STALLED on T-05 (the frozen background worker)
  2. task-event BLOCKED on T-05 (supervisor emits on the worker's behalf)
  3. task-register T-06 as a fresh id with retry_of: T-05
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


# 1. WORKER_STALLED blocker on T-05
bl = {
    "signal": "WORKER_STALLED",
    "task_id": "T-05",
    "agent": "team-lead",
    "missing_item": (
        "implementer bg_9ece9acd froze inside a bash tool call at 00:20:18Z "
        "(the pre-change baseline run) - implementer bash ruleset had '*': 'ask' "
        "and no 'python framework/*' allow, so the command resolved to permission "
        "'ask' and a headless background session has no interactive approver -> "
        "tool call never resolves -> worker silently frozen. Telemetry had no "
        "record of the subagent session (framework can't see it)."
    ),
    "tried": (
        "root fix applied to opencode.json: every background subagent bash "
        "default changed ask->deny (fail-fast instead of silent hang); allowlists "
        "gained python framework/*, bash framework/*, ./framework/* AFTER the '*' "
        "rule so findLast resolves the specific working allow; verifier npm ci* "
        "deny->allow; duplicate team-lead git push* allow removed (push now "
        "deny, matching global). Re-delegating as T-06 to prove the fix."
    ),
}
run("write-blocker", "--json", json.dumps(bl), expect_ok=True)

# 2. BLOCKED event on T-05 (legal from STARTED; supervisor emitter)
ev = {
    "state": "BLOCKED",
    "emitter": "team-lead",
    "detail": (
        "worker frozen on permission-ask for python framework/* command; "
        "root fix applied in opencode.json; retry registered as T-06"
    ),
}
run("task-event", "--id", "T-05", "--json", json.dumps(ev), expect_ok=True)

# 3. Register T-06 as retry_of T-05 (same DID-007 delta contract)
t06 = {
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
    "retry_of": "T-05",
}
run("task-register", "--id", "T-06", "--json", json.dumps(t06), expect_ok=True)

print("EMIT_OK")