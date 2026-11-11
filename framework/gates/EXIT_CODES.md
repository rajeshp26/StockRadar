# Gate Exit Code Contract — AUTHORITATIVE

Machine-checked by `framework/validate.py`. If a document disagrees with this table, the
document is wrong. Generated claims about gate behaviour must cite this file.

| Gate | 0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| G-ENTRY entry | approved plan + declared scope + acceptance criteria, no open questions, routing skills required by the plan — dispatch allowed | named missing prerequisite — NO TASK DISPATCH | BLOCKED (python3 absent / unreadable) | — | NOT_APPLICABLE (ENTRY_EXEMPT=TRIVIAL) |
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
| G-T1 tool_utilization | tool evidence present in verification artifacts | tool evidence gaps found, OR no artifact where the plan requires evidence | BLOCKED (python3 absent / plan depth unreadable) | — | NOT_APPLICABLE (no artifacts and the plan does not require evidence) |
| G-SKILL-COVERAGE | every skill the plan implies by file scope and by its Capability Matrix is named in required_skills | skill coverage errors listed | BLOCKED (python3 absent / plan or schema unreadable) | — | NOT_APPLICABLE (framework/plan/lint_mode=off) |
| G-SKILL-USE | every skill the plan requires was recorded as invoked in a session attributed to the task | required skill(s) have no recorded invocation | BLOCKED (python3 absent / plan or record store unreadable) | CAPABILITY_MISSING (telemetry plugin absent — invocation unobservable) | NOT_APPLICABLE (lint_mode=off, plan requires no skills, or no telemetry records) |
| G11 evidence | claims valid, provenance present | invalid claims listed | BLOCKED (python3 absent) | — | NOT_APPLICABLE (no claims recorded) |
| G12 provider | healthy — dispatch allowed | unhealthy — NO TASK DISPATCH | BLOCKED (cannot verify provider health) | — | NOT_APPLICABLE (no model resolved) |
| G13 worker | all workers healthy or terminal | unhealthy worker(s) listed | BLOCKED (cannot read task state) | — | NOT_APPLICABLE (no tasks registered) |
| G14 evidence-integrity | all claims pass E1-E8 | integrity violation(s) listed | BLOCKED (python3 absent) | — | NOT_APPLICABLE (no claims recorded) |
| G15 tripwires | no eval tripwire hits | violations listed | BLOCKED (grep/awk absent) | — | NOT_APPLICABLE (no changed eval files) |
| G16 state-health | task/ledger store readable | broken task(s) or unreadable tail listed | BLOCKED (python3 absent / adapter error) | — | NOT_APPLICABLE (no tasks, no ledger) |
| G17 system-tests | fresh passing harness evidence for every real-stack criterion | evidence missing, stale, tampered or failing | BLOCKED (python3 / plan unreadable) | UNVERIFIABLE (stack unreachable) | NOT_APPLICABLE (no plan given, or no real-stack criteria) |
| G19 closure | every acceptance criterion has a fresh, bound, passing artifact or a human waiver | at least one criterion pending, failed or unverifiable | BLOCKED (matrix or plan unreadable, python3 absent) | UNVERIFIABLE (the matrix drifted from the plan, or the pointer names a matrix that no longer exists) | NOT_APPLICABLE (no plan and no matrix given, or the plan declares no criteria) |
| G-EXEC exec-integrity | matrix 38/38 checks pass | deviations listed | BLOCKED (python3 absent) | — | NOT_APPLICABLE (no matrix module) |
| G-SANDBOX capability | sandbox enforceable via the chosen backend (native bubblewrap or container) — target execution permitted | isolation control failed (target writable / env leaked / egress open) | BLOCKED (probe could not run) | capability missing (no enforceable native backend and no usable container) | NOT_APPLICABLE (SANDBOX_EXEC_REQUIRED=0) |
| G18 security-audit | no open confirmed high/critical finding | open confirmed high/critical finding, or findings/ledger fail validation | BLOCKED (run dir or artifact missing) | UNVERIFIABLE (validators absent, or no POSIX-capable interpreter — native node lacks O_NOFOLLOW and the container is unavailable) | NOT_APPLICABLE (no audit run dir) |

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

## G19 judges the matrix, and a lost matrix is not an empty one

G19 closes the loop the decision chain was missing: every acceptance criterion the plan
declares must have a fresh, bound, passing artifact or an explicit human waiver. The matrix
is produced by `matrix.py emit` at dispatch (`g_entry.sh` block 4d) and pointed at by
`<state_root>/verification/current.json`.

Two consequences worth stating, because both were bugs:

* **A pointer whose matrix no longer exists is UNVERIFIABLE (3), not NOT_APPLICABLE.** The
  pointer names a decision; if the artifact is gone, the decision was lost. Reporting
  "nothing to close" would let a deleted matrix read as a clean task.
* **NOT_APPLICABLE (4) requires that there was nothing to judge in the first place** — no
  plan and no matrix given at all, or a plan that declares no criteria. A task with a plan
  and no matrix is a FAILURE (1): `g_entry` was supposed to emit one.

The matrix is also how a gate learns *why* it was routed. `matrix.py required-gates` prints
the artifact's `required_gates`, and `g6` uses it to decide whether the task has a
visible-behaviour requirement. That replaced an environment variable, because on a Windows
host the only bash is WSL, which does **not** inherit the caller's environment — a
PowerShell `$env:REQUIREMENT_SHAPE` is empty inside `bash -c`, so the documented input read
as absent and the gate fell back to guessing.

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

## G-SANDBOX refuses target execution it cannot enforce

G-SANDBOX measures the host's sandbox capability before any untrusted target runs. Exit 0 means
the isolation primitives are present AND an enforcement probe proved them (read-only target,
writable scratch, cleared environment, no external egress) — execution is permitted. The probe
picks a backend: **native** (bubblewrap + unprivileged user namespaces) is preferred, and the
**container** backend (`framework/container/`) is the fallback and the toolchain provider. Exit 1
means a control that was required did not hold: the sandbox is not a sandbox, and the run must
abort rather than fall back to an unsandboxed one. Exit 3 means no backend is enforceable
(bubblewrap/user namespaces absent and no usable container): the audit proceeds **source-only**
and the gap is recorded, never waived. Exit 4 means target execution was not required
(`SANDBOX_EXEC_REQUIRED=0`). A skipped check is never a pass: G-SANDBOX reports DOWNGRADE, it does
not grant the capability.

## G18 blocks completion on an open confirmed high/critical finding

G18 judges a security-audit run directory (`AUDIT_RUN_DIR`), delegating artifact validity to the
vendored skill's own validators. Exit 0 means the artifacts validate and no confirmed finding is
high or critical. Exit 1 means completion is refused: either an artifact failed validation, or a
`confirmed` finding carries severity high/critical. A `needs_validation` critical is NOT a
confirmed finding and does not block. Exit 2 means the run dir or an artifact is missing — the
audit did not happen, which is not a pass. Exit 3 means the validators are absent, or no
interpreter could judge: Windows `node.exe` cannot enforce no-follow input, and the container
fallback was unavailable. It tries native `node` first and falls through to the sandbox
container's POSIX `node`, so a host with the image reaches a real verdict instead of exit 3. It is
UNVERIFIABLE, never a false FAIL. Exit 4 means no audit run dir was given — nothing to judge.

## G19 closes the requirement, not the diff

G19 judges the verification matrix written by `framework/verifier/matrix.py emit` at dispatch:
one row per acceptance criterion, carrying the method, gates and skills its evidence class
derived (`framework/verifier/evidence_classes.yaml`) and the impact scope that set the gate
breadth (`framework/verifier/profiles.yaml`). Exit 0 means every row is `pass` with a bound
artifact, or `waived` by a named human with a reason. Exit 1 means at least one row is
`pending`, `fail` or `unverifiable` -- and `unverifiable` is never a pass, so a green gate that
could not confirm the real stack was reached refuses completion. Exit 3 means the matrix no
longer matches the plan's digest: the plan changed after emission, so the recorded evidence
does not correspond to the approved requirements. Exit 4 means there was nothing to judge.

This is the gate that makes `AC-n` the unit of completion. Before it existed, a criterion could
be tagged `[e2e]` and no component downstream of the plan lint ever asked whether it had
evidence.

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

## G-SKILL-COVERAGE separates resolution from selection

`validate.py` proves a skill RESOLVES: its directory exists on a configured `skills.paths`
root, its frontmatter parses, its `name:` matches the directory, and every skill named in
`skill-routing.md` is found. Resolution is not selection. A skill can resolve perfectly and
never be required by any task, which is how a routing table becomes decoration.

G-SKILL-COVERAGE closes selection at the plan, the last point before work starts, and it
reads two independent sources:

| Source | Rule | What it proves |
|---|---|---|
| declared file scope | SC02, SC03 | a plan touching UI paths names `apple-ui` + `frontend-react`; a plan creating a new UI surface also names `designmotion-design` (skill-routing.md:22-24) |
| declared file scope (tests) | SC06 | a plan touching test files names `istqb-testing`, the technique layer over any test a task writes or changes (skill-routing.md:19) |
| the ask's Capability Matrix | CM01-CM05 | every dimension the team-lead matrix declares has a verdict, and every `yes` appears in some task's `required_skills` |

The dimension list is not duplicated in code: it is read from the Capability Matrix table in
`team-lead.md`, so adding a row to the doc changes what the check demands. An unknown
dimension in a matrix is a warning (a typo), a missing one is an error (an unanswered claim).

A matrix is optional today (CM05 is a warning): no plan in flight has one, and making its
absence fatal would block dispatch on a document nobody has written yet. The upgrade path is
to flip CM05 to an error once every active phase carries a matrix; that switch is a code
change in `framework/tools/skill_coverage.py`, not a config toggle, so it cannot be relaxed
by an agent at runtime.

G-SKILL-COVERAGE shares `framework/plan/lint_mode` with the DID-016 plan lint on purpose:
one switch disables both halves of the pre-dispatch contract, so "temporarily advisory"
cannot mean two different things in two gates.

## G-SKILL-USE separates requirement from invocation

G-SKILL-COVERAGE proves a plan REQUIRED a skill. It cannot prove the skill was ever loaded.
That gap is what G-SKILL-USE closes, and it is the only gate in the family that reads
behaviour instead of intent:

| Question | Artifact | Gate |
|---|---|---|
| does the skill resolve and parse? | skill directory + frontmatter | `validate.py` |
| does the plan require it? | `required_skills` + Capability Matrix | G-SKILL-COVERAGE |
| was it actually invoked? | `skills_loaded` in the session record | G-SKILL-USE |

It reads `.planning/telemetry/records.jsonl` through `framework/tools/skill_use.py`. There is
no separate recorder: `framework/opencode/plugin/telemetry.ts` already captures the `skill`
tool call into `skills_loaded` and flushes it on every heartbeat and final write. A second log
would be a second source of truth for one fact, and it would put the sensor in agent-writable
space, where whatever is being measured could edit the measurement.

Only records attributed to the task count. A skill loaded while working on task `T-01` is not
evidence for task `T-02`, so the gate passes `--task` and filters. With no task id it judges
every session in the store and says so in its evidence, which is a weaker claim made openly
rather than a stronger one assumed.

**`unknown` is a sensor defect, not a skill** (SU01). `telemetry.ts` falls back to `unknown`
when it cannot read the skill name off the tool call. SU01 reports that, and an `unknown`
entry never satisfies a required skill: otherwise a broken sensor would read as a clean run.
SU01 is a warning because it is a finding about the instrument, not about the task; SU02 is
the error, and it names the skill that was never invoked.

Exit 4 covers three distinct non-judgements (mode off, plan requires nothing, store empty).
Each is emitted with evidence naming which one it was. Exit 3 is reserved for a missing
telemetry plugin, where no skill call could have been recorded at all: that is a capability
gap, not a clean run, and it is never reported as 0.

## G-T1: an absent artifact is a failure when the plan required evidence

G-T1 used to report SKIP/pass when no verification artifact existed, making "nothing to
check" indistinguishable from "checked and clean". It now derives the required depth from the
plan (`framework/tools/evidence_level.py`) and splits three ways:

| Plan declares | No artifact found | Exit |
|---|---|---|
| complexity L2-L4, or any `integration` / `e2e` / `browser` / `data-invariant` criterion | the work asserted more than it proved | 1 FAIL |
| L0/L1 with only unit/static/manual/contract criteria | nothing was claimed that needs an artifact | 4 NOT_APPLICABLE |
| no `ENTRY_PLAN` given | depth is underivable, so the gate refuses to guess | 4 NOT_APPLICABLE (evidence names `plan_context: absent`) |

The caller passes `ENTRY_PLAN`; the gate never reads an environment variable for policy,
because an agent can set one and the plan is the artifact under review.
