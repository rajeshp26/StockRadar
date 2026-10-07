#| G-ENTRY entry | approved plan + declared scope + acceptance criteria, no open questions - dispatch allowed | named missing prerequisite - NO TASK DISPATCH | BLOCKED (python3 absent / unreadable) | - | NOT_APPLICABLE (ENTRY_EXEMPT=TRIVIAL) |
 Gate Exit Code Contract — AUTHORITATIVE

Machine-checked by `framework/validate.py`. If a document disagrees with this table, the
document is wrong. Generated claims about gate behaviour must cite this file.

| Gate | 0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| G1 contract   | valid, types in sync, tests green | validation failed / CONTRACT_CHANGE | BLOCKED (python3 absent) | — | NOT_APPLICABLE (no contracts dir) |
| G2 impact     | impact mapped to N tests | UNKNOWN_IMPACT | — | — | NOT_APPLICABLE (no changes) |
| G3 architecture | boundaries respected | boundary violation | BLOCKED (pyyaml absent) | — | NOT_APPLICABLE (no architecture rules) |
| G4 executable | N checks green, every detected language covered by static analysis | ≥1 check failed, OR a detected language had zero checks run, OR a detected language had tests/build but no static analysis | — | — | — |
| G5 stack      | conformant | violations found | BLOCKED (cannot evaluate) | — | NOT_APPLICABLE (no frontend) |
| G6 browser    | specs ran and passed | specs ran and failed | **NEVER EMITTED** | UNVERIFIABLE | — |
| G7 retro      | retros complete, no recurrence | incomplete or recurrence | BLOCKED (python3/pyyaml absent) | — | NOT_APPLICABLE (no escape trigger) |
| G8 blockers  | no open blockers | open blockers listed | BLOCKED (python3/pyyaml absent) | — | — |
| G9 scope      | within declared scope (or SKIP: no plan / no changes) | undeclared files listed | — | — | — |
| G10 permission | policy conformant | violations found | BLOCKED (python3 absent) | — | NOT_APPLICABLE (opencode.json absent) |
| G-T0 tool_readiness | tool plan exists, registry present, contracts in place | tool plan missing or tools unavailable | BLOCKED (python3 absent) | — | — |
| G-T1 tool_utilization | tool evidence present in verification artifacts | tool evidence gaps found | BLOCKED (python3 absent) | — | NO_VERIFICATION_ARTIFACTS |
| G11 evidence | claims valid, provenance present | invalid claims listed | BLOCKED (python3 absent) | — | NOT_APPLICABLE (no claims recorded) |
| G12 provider | healthy — dispatch allowed | unhealthy — NO TASK DISPATCH | BLOCKED (cannot verify provider health) | — | NOT_APPLICABLE (no model resolved) |
| G13 worker | all workers healthy or terminal | unhealthy worker(s) listed | BLOCKED (cannot read task state) | — | NOT_APPLICABLE (no tasks registered) |
| G14 evidence-integrity | all claims pass E1-E8 | integrity violation(s) listed | BLOCKED (python3 absent) | — | NOT_APPLICABLE (no claims recorded) |
| G15 tripwires | no eval tripwire hits | violations listed | BLOCKED (grep/awk absent) | — | NOT_APPLICABLE (no changed eval files) |
| G16 state-health | task/ledger store readable | broken task(s) or unreadable tail listed | BLOCKED (python3 absent / adapter error) | — | NOT_APPLICABLE (no tasks, no ledger) |
| G-EXEC exec-integrity | matrix 38/38 checks pass | deviations listed | BLOCKED (python3 absent) | — | NOT_APPLICABLE (no matrix module) |

## G6 emits ONLY 0, 1, 3

G6 has no exit 2. Any table offering "2 = BLOCKED (no driver/config)" for G6 is a bug, and a
dangerous one: it creates a second code for the condition exit 3 exists to name. A reader who
sees BLOCKED alongside UNVERIFIABLE will treat one of them as ignorable. Missing driver,
missing config, and missing specs all return **3**.

G6 also has no exit 4. When G6 has nothing to judge — no visible-behaviour requirement and no
frontend source changed — it returns **3**, not 0 and not 4. Exit 0 would be the vacuous pass
`:174` forbids; exit 4 is outside G6's vocabulary. Recording it as UNVERIFIABLE overstates the
gap slightly and fails closed, which is the correct direction for a gate that cannot judge.

## G7 exit 4 is not a pass

Exit 4 from G7 means no defect-escape trigger was recorded, so there was nothing to retrospect.
That is the normal case for a clean task. It is not evidence that the framework is learning —
only that nothing escaped this time. Do not report it as a passed retrospective.

## G8 blocks completion on open blockers

A non-complete stop (CONTEXT_INSUFFICIENT, BLOCKED, UNKNOWN_IMPACT, ...) recorded in
<state_root>/blockers.yaml stays open until explicitly resolved. While any open record
exists, G8 returns exit 1 and completion is refused -- the same enforcement shape G7
applies to retrospectives. Exit 0 means zero open records; exit 2 means the store could
not be read (python3/pyyaml absent or unparsable state), which is never read as zero.

## G9 skips are not silent passes

G9 judges changed source files against the plan's declared files_or_components. With no plan
context or no source changes it logs SKIP and exits 0 -- that is "nothing was judged", not
"scope respected". A skip must be reported as skipped, never counted as a passed check.


## G10 asserts policy structure, not interactive behaviour

G10 checks that opencode.json expresses the risk-tiered permission model: catch-all "ask"
first (last-match-wins ordering), the allow families (git read, test/build/lint, trusted
framework scripts), the deny families (destructive fs, git history mutation, push), and the
negative invariants (no `backend/scripts/` path trust, no arbitrary python allow, no
`New-Item`). A gate cannot drive opencode's interactive ask/allow engine, so it asserts the
policy structure that produces those behaviours; the behavioural smoke test is manual. Run
G10 whenever a permission rule changes:

    bash framework/gates/g10_permission.sh   # expect exit 0 (conformant)
    git status                                # expect no prompt (allow)
    python -c "print(1)"                      # expect prompt (ask)
    Remove-Item somefile                      # expect denied (deny)
    git push                                  # expect denied (deny)

A skipped G10 (exit 4, no opencode.json to judge) must be reported as skipped, never as
conformant.

## G-T0 verifies tool readiness before work

G-T0 checks that the tool lifecycle infrastructure is in place: the tool registry exists,
team-lead.md has Tool Applicability Analysis, and core agents have Tool Contracts. This
is a pre-flight check, not a tool usage check. Exit 0 means the infrastructure is ready;
exit 1 means pieces are missing; exit 2 means python3 is unavailable.

## G-T1 verifies tool utilization after work

G-T1 checks that verification artifacts contain tool evidence. It looks for tool_evidence,
tool, exit_code, or command patterns in verification files. Exit 0 means evidence is present;
exit 1 means evidence gaps exist; exit 4 means no verification artifacts to check (skip).
A skip is not a pass -- it means there was nothing to judge.

## Tool gates are infrastructure gates

G-T0 and G-T1 are infrastructure gates, not code quality gates. They verify that the
framework's tool lifecycle is operational, not that the code is correct. They complement
G1-G9 which verify code quality and correctness.

## G11 validates claims, not prose

G11 does not judge whether a conclusion is true; it judges whether conclusions were recorded
as ledger claims with sufficient, reproducible provenance. Claims without provenance are
failures, not caveated passes.

## G12 is a pre-flight gate — it refuses dispatch, it does not report it

G12 runs BEFORE any task() dispatch. A model that has not passed a lightweight invocation
health check during the current execution context has no dispatch right: the first dispatch
in a window is the probe, its outcome is recorded, and a blocking outcome (QUOTA_FAILURE,
AUTH_FAILURE, MODEL_UNAVAILABLE, PROVIDER_TIMEOUT, PROVIDER_NETWORK_FAILURE) refuses the NEXT
dispatch with exit 1 and NO TASK DISPATCH. Exit 4 means no model resolved — nothing to
dispatch; it is a skip, not a pass. Exit 2 means provider health could not be verified
(missing python3, unreadable inventory, unparsable report) — never read as pass. G12 has no
exit 3: every cannot-verify condition is a toolchain failure (2), and an absent model to
judge is NOT_APPLICABLE (4), so the two capabilities exit 3 exists to separate are already
distinct.

## G13 is an observability gate — it refuses completion on an unhealthy worker

G13 judges the task event stream, not the contract file. A registered task whose worker
has gone silent past its budgets (STALLED, OVERDUE), failed unresolved, was declared
LOST by the supervisor, or left an unreadable event stream is a supervision debt; exit 1
names each task WITH its recovery route (recovery_action plus the type's
recovery_policy), and the gate keeps failing until the supervisor acts. Exit 4 means no
tasks were registered — nothing to observe; a skip, not a pass. Exit 2 means task state
could not be read (missing python3, unparsable summary) — never a pass. WARNING (silent
past the progress timeout, probe-and-continue) is healthy; only recovery_level >= 2
escalates.

## G14 is an evidence-integrity gate — it refuses completion on borrowed or stale evidence

G14 judges the claim store, not the record format. E1-E5 (evidence present, bound to the
task, git_sha-consistent, timestamp-sane) share the ledger's own validate_record checks;
E2 (a repo-relative entry_point must exist on disk), E6 (a gate named in evidence must have
a receipt in VERIFICATION.md), E7 (no open reviewer suspicion or unfinished review may sit
on a VERIFIED claim), and E8 (no identical evidence payload may be reused across tasks) are
G14's own. Exit 4 means no claims exist — nothing to judge; a skip, not a pass. Exit 2 means
integrity could not be computed (missing python3, unparsable report) — never read as pass.
The gate wraps `python3 framework/claims/ledger.py integrity`, which exits 3 when the ledger
is empty; the gate maps that to NOT_APPLICABLE.

## G15 is an eval-integrity gate — it refuses completion on tripwire hits in changed eval-scoped code

G15 scans changed test/eval/harness/candidate/variant files for syntactic
tripwires ported from the ECC eval-harness DEFAULT_TRIPWIRES : hidden network
access, process spawning, sandbox weakening, gate probing, and parent escape.
Exit 1 lists each hit as rule|file:line:content. Exit 4 means no eval-scoped
files changed — nothing to scan; a skip, not a pass. Exit 2 means the scan could
not run (grep/awk absent) — never read as pass. G15 covers the agent-written
eval code that the stack-conformance gate (G5) does not: it judges behaviour-
relevant imports and probes, not the declared stack.

## G-EXEC asserts execution integrity against the failure-injection matrix

G-EXEC wraps `python3 framework/adapters/failure_injection.py`, the adversarial
E/G matrix that drives a delegated-task lifecycle through injected deviations:
wrong budgets, out-of-order lifecycle events, THINKING while paused, leaked
supervision state. Exit 0 means all checks behaved as the framework declares;
exit 1 lists the deviations; exit 2 means the matrix could not run (missing
python3 or unreadable state root) — never a pass; exit 4 means the matrix
module is absent — nothing to judge. The matrix is self-cleaning: residue
left in the task store after a run is itself a deviation. G-EXEC complements
G13 (worker observability) and G14 (evidence integrity) as the gate that tests
the framework's own execution contract instead of trusting it.

## Exit 3 is the most important code in the framework

Exit 3 means "we could not look." It is never read as "it looks right."

On exit 3 you may NOT claim the requirement is verified, and you may NOT claim it is
violated. Record it as `unverifiable` and name what is missing.

## Universal rules

| Rule | Meaning |
|---|---|
| Never pass vacuously | zero checks executed is FAIL, never pass (G4) |
| Missing tool is never a pass | substitute it, or report BLOCKED / UNVERIFIABLE |
| SKIP ≠ PASS | skip means no artefact of that class exists to judge |
| CONTRACT_CHANGE outranks test failure | a schema change causes test failure by definition; route the cause to Architect, not the symptom to Implementer |
| UNKNOWN_IMPACT is not "no impact" | zero tests found at tier 4 escalates |

## Non-zero codes are not interchangeable

BLOCKED (2) means the gate could not evaluate — a toolchain problem. UNVERIFIABLE (3) means
the gate evaluated its preconditions correctly and found no way to produce evidence — a
capability problem. NOT_APPLICABLE (4) means there is nothing of this class to judge. Only
FAIL (1) is a verdict about the code.


## G-ENTRY is a pre-flight gate - it refuses dispatch, it does not report it

G-ENTRY runs BEFORE any task() dispatch, mirroring G12. A task whose plan does not satisfy
the entry contract - an approval token (status: approved | approved: true | accepted: true),
declared files_or_components, acceptance_criteria, and no unresolved open_questions - has no
dispatch right. Exit 1 names the missing prerequisite and dispatch is refused; fix the plan
first. A task with no plan context and no ENTRY_EXEMPT is a routing defect: exit 1, never a
skip, and never a pass. ENTRY_EXEMPT=TRIVIAL is the only documented bypass (team-lead's
trivial-request gate) and returns 4 NOT_APPLICABLE - a recorded exemption, not a verdict on
the plan. Exit 2 means python3 was unavailable; it is never read as pass. G9 remains the
post-hoc scope check; G-ENTRY is its pre-flight half.
