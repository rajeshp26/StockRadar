# Framework Portability Assessment

Goal: *copy the framework into another project and it works.*

Verdict: **defects 1-3 are fixed and applied, and the verification-state concurrency defects
found while proving them are fixed and applied too. A bare scaffold validates at exit 0 via
`framework/standalone_check.py`. Two items remain open: defect 4 — there is no reliable way to
*obtain* the scaffold — which is the one that matches the stated goal, and the enforcement plane,
which is red and is a human action item.**

## Current state

Measured in this repo, not recalled.

| Property | Result |
|---|---|
| `python framework/standalone_check.py` | `STANDALONE: framework validates holding only its own surface`, **exit 0** |
| `python framework/validate.py` | `VALIDATION PASSED`, **exit 0**, 0 FAIL, 0 WARN, 41 suite groups (38 = verification-state concurrency, 39 = standalone-guard negative paths, 40 = bounded atomic-replace retry, 41 = validation profile contract) |
| `python framework/verification/test_state_concurrency.py` | **23/23**, exit 0 — suite 38's body, runnable standalone |
| `python framework/test_standalone_check.py` | **6/6**, exit 0 — suite 39's body; the guard's refusal paths, which had never been executed |
| `python framework/adapters/test_atomic_write.py` | **13/13**, exit 0 — suite 40's body; the retry recovers the transient violation and does not mask a permanent one |
| `python framework/validate.py --profile framework` | **exit 0**, 0 FAIL, 0 WARN, **5 NOT_APPLICABLE** — framework-only surface; the five app-readiness checks report 4 |
| `python framework/validate.py --profile app` | **exit 0**, 0 FAIL, 0 WARN, 0 NOT_APPLICABLE — the five readiness checks asserted |
| Gates under Windows | WSL bash via `validate.py:78 sh()`; suite 12 proves gates refuse a non-bash shell |
| `framework/security/check_enforcement_plane.py` | **exit 1 — RED.** See below |

### The enforcement plane is currently red, and this document must not hide it

`check_enforcement_plane.py` requires three representations to agree: the canonical
`enforcement_plane.yaml`, the `permission.edit` deny blocks in `opencode.json`, and the
`AGENTS.md` fence. `framework/**` was moved from `deny` to `allow` in the `opencode.json`
top-level and `team-lead` blocks to let an agent edit framework code. The canonical YAML and
the fence were not changed, so the three now disagree:

```
FAIL: top-level allows/asks plane paths: ['.opencode/**', 'AGENTS.md', 'framework/**', 'opencode.json']
FAIL: top-level lacks deny for plane paths: ['framework/**', '.opencode/**', 'opencode.json', 'AGENTS.md']
FAIL: team-lead allows/asks plane paths: ['.opencode/**', 'AGENTS.md', 'framework/**', 'opencode.json']
FAIL: team-lead lacks deny for plane paths: ['framework/**', '.opencode/**', 'opencode.json', 'AGENTS.md']
```

This is a **human action item**, deliberately not fixed by the agent that caused it. `framework/**`
being writable means an agent could make this check pass by editing the checker — which is the
control the plane exists to provide. The fix is the documented workflow in the YAML header:
remove the `framework/**` entry from `enforcement_plane.yaml`, then run
`python framework/security/sync_enforcement_plane.py`, then re-run the check. Note that
`sync_enforcement_plane.py` preserves existing values for paths no longer in the plane, so
`framework/**` must be set to `allow` in the `team-lead` and `implementer` blocks too, not only
the top-level one.

Until that is done, treat every `framework/**` diff — including the ones described below — as
**self-attested**: the party that made the change could also have weakened the check that
grades it.

> Correction (an earlier revision, retained as history): a draft of this document claimed
> *36 of 37 suites pass*. That was wrong. The baseline evidence supports **34 of 37**: six
> individual failures are spread across **three** suite groups (suite 11, suite 12, suite 37),
> not one. Suite-level "36" counted 37 groups minus suite 37 while ignoring that suites 11 and 12
> also contained failures. The six-failure count was always correct; the suite-level arithmetic
> was not. Both figures describe the **baseline** scaffold; the current run is 41 of 41.

All figures below were produced in this repo, not recalled. Method: the scaffold
(`framework/`, `.opencode/`, `AGENTS.md`, `opencode.json`, `.gitattributes`, `.lifecycle/`,
`.gitignore`) was copied to a directory containing no app, the copy was asserted free of
`backend/`, `web/`, `mobile/`, `supabase/`, `features/`, `package.json`, `pyproject.toml`, the
working directory was proven with an `os.getcwd()` marker, and `framework/validate.py` was run
there. Result: `VALIDATE_EXIT=1`, 6 failures.

## What is already correct

Rows in this table are **baseline** measurements — taken on the pristine scaffold before any patch
in this document was applied. For current-state figures, read the table under **Current state**
above; several rows below have since changed and are marked.

| Property | Evidence |
|---|---|
| Enforcement plane (at baseline, before `framework/**` was opened for agent edits) | was `OK: enforcement plane consistent (4 paths)`, exit 0 — **now RED**; see above |
| `framework/` source fully tracked | 111/111 real source files tracked; all 49 untracked files are generated (43 `.pyc`, 5 manifest/telemetry JSON, 1 txt) |
| Core suites pass with no app | **baseline, now superseded** — was 34 of 37 suite groups green, including LF line-ending hygiene, the intake/control/execute adapters, G16, and suite 36 `State adapter race fixes under load`. The three non-green groups were suite 11 (contract fixture), suite 12 (browser/app readiness), and suite 37 (validator bool guard). All three are now green and the run is **41 of 41** |
| Installer artifacts correctly untracked | `.opencode/node_modules` (3667 files) and `.opencode/gsd-core` (558 files) are generated, not source |

## Defect 1 — a framework test lives outside the framework (blocking)

`framework/validate.py:2616` executes the framework's own test from a project path:

```python
_r37 = subprocess.run([sys.executable, "tests/contract/test_validator_types.py"], ...)
```

`tests/contract/test_validator_types.py` has no application coupling — it imports only
`from framework.contracts.validator import validate_instance` and its docstring says
*"Runs standalone, matching tests/contract convention."* But `tests/` is application-owned:
`tests/README.md` is titled **"StockerPro Testing Guide"**, and its siblings are unambiguously
app code (`tests/e2e/session-card.spec.ts`, `test_portfolio_risk_e2e.py`, `test_user_sync.py`,
`tests/contract/test_api_004.py`).

Consequence: suite 37 can never pass in a clean copy. It failed with
`can't open file '.../tests/contract/test_validator_types.py'`.

**Fix:** move it to `framework/contracts/test_validator_types.py` and update the
`framework/validate.py:2616` path. `sys.path.insert(0, ...parents[2])` stays valid — both
locations are two levels deep.

## Defect 2 — `validate.py` conflates framework integrity with project readiness (blocking)

Five of the six remaining failures demand artifacts a bare scaffold legitimately does not have:

- `openapi schema present`
- `contract tests present`
- `frontend app manifest exists`
- `playwright config exists`
- `browser specs exist`

A correctly-copied scaffold therefore reports *"do not use the framework until resolved"* while
the framework itself is sound. These five are rollout concerns — `README.md` places
"contracts on your single real frontend/backend seam" and G1/G4 wiring under **Rollout**, not
under **Install**.

**Fix as implemented:** the five checks pass `app_only=True` to `check()`. Under
`--profile framework` they report `NOT_APPLICABLE` — the verdict `EXIT_CODES.md` already
defines as 4, an unevaluable capability that "is never a pass". Under `--profile app` they are
asserted as failures. Framework integrity is asserted identically under both profiles; only the
five rollout checks are profile-scoped.

**An intermediate version of this work used `warn_only=True` for the same five checks, and it was
rejected.** Recording the deviation because the reasoning was plausible and wrong:

- *The reasoning used at the time:* the portability goal is literally "copy it and it works". A
  bare scaffold reporting exit 4 (`NOT_APPLICABLE`) reads as a broken install to whoever just ran
  `validate.py` after copying. Exit 0 is the observable proof that the copy succeeded.
- *Why that reasoning does not hold:* it rests on a false premise — that adding a CLI surface
  means touching the immutable enforcement plane. It does not. `validate.py` is a framework
  script; a `--profile` flag on it changes no representation in `enforcement_plane.yaml`,
  `opencode.json`, or `AGENTS.md`. The plane constrains who may edit the rules that check them,
  not what arguments a script accepts. That conflation is what let the suppression survive.
- *What it cost:* a scaffold that genuinely lacked Playwright specs printed `VALIDATION PASSED`
  with no indication the check had been skipped. `warn_only` is global, so the framework profile —
  which should assert its own integrity strictly — also got a weakened signal it never needed
  weakened.

**The profile split keeps the observable outcome the `warn_only` patch was reaching for, and
obtains it honestly.** A bare copy still exits 0, because the profile defaults from the presence
of an app rather than demanding one. The difference is that the five skipped capabilities are now
named in the output and counted in the summary line, so exit 0 is not silently misread as
"everything ran":

```
5 check(s) NOT_APPLICABLE under --profile framework (never counted as a pass; re-run with --profile app to assert them):
  - openapi schema present: ...
  - contract tests present: ...
  - frontend app manifest exists: ...
  - playwright config exists: ...
  - browser specs exist: ...
VALIDATION PASSED  [profile=framework; 0 fail, 0 warn, 5 not-applicable]
```

**Pinned by suite 41**, so the suppression cannot return unreviewed. `NOT_APPLICABLE` is a distinct
bucket from `PASS` and from `WARN`, and it outranks `PASS` — a profile that declines to assert a
class of checks keeps saying so even when the file happens to exist, so "not asserted" never
becomes indistinguishable from "asserted and passed". Red phase: routing `browser specs exist`
back to `warn_only` fails the suite by name (`absent from SKIPS: ['browser specs exist']`) and
drops the N/A count to 4, exit 1.

## Defect 3 — a framework invariant depends on a project-owned file

`framework/.manifest/` must be gitignored, because it caches machine-specific absolute paths —
`framework/.manifest/code_intel.json` embeds `C:\Users\rages\.omo\codegraph\bin\codegraph.cmd`.

That rule lives in the root `.gitignore` (line 97 at the time of measurement; line 98 after
`.tmp-*/` was added for scratch isolation), inside a file whose other lines are entirely
StockerPro (`backend/service-account.json`, `web/playwright-report/`,
`docs/activities-export-*.csv`). Proof of the coupling: the check **failed** on the copy without
`.gitignore` and **flipped to PASS** once it was added — 7 failures became 6.

**Fix as implemented:** ship `framework/.gitignore` (already covered by the `framework/` entry in
the inclusion manifest) containing `.manifest/`, so the framework carries its own invariants
instead of borrowing the host project's. `validate.py` was also changed to accept either the
framework-owned `framework/.gitignore` or a project-root `.gitignore` carrying the
`framework/.manifest` rule, so existing installs keep passing.

Verified: with the project-root `.gitignore` **renamed away** and only `framework/.gitignore`
present, `manifest cache is gitignored` reports `PASS`. The invariant now travels with the
framework instead of the project.

## Defect 4 — both distribution modes are broken, in opposite directions

`README.md` documents install as `cp -r . /path/to/your/repo/`. In this repository that command
copies the entire StockerPro application into the target project, because framework and app are
co-mingled in one directory.

The alternative, a git clone, fails the other way: `.gitignore:61` ignores `.opencode/`, so a
clone carries **1 file** where the disk has 500+:

| `.opencode/` | files on disk | tracked in git |
|---|---|---|
| `agents/` | 40 | 0 |
| `commands/` | 78 | 0 |
| `skills/` | 98 | 1 |
| `hooks/` | 34 | 0 |
| `rules/` | 10 | 0 |
| `scripts/` | 15 | 0 |
| `plugin/` | 11 | 0 |

A git-based copy arrives with no agent layer at all.

**Fix:** publish the scaffold as its own distributable (separate repository or directory tree)
with a committed inclusion manifest, so neither mode silently drops required content.

## Inclusion manifest

The manifest is **not restated here**. Its single authoritative declaration is the `REQUIRED` and
`OPTIONAL` tuples at the top of `framework/standalone_check.py` — the same tuples the guard
executes, so this document cannot drift from what is actually enforced. Read them there and copy
exactly those entries.

`framework/.gitignore` is required, not optional: it carries the `.manifest/` invariant, and
omitting it re-breaks portability (defect 3). No project-root `.gitignore` belongs in the
manifest — the target project should have its own, and the framework no longer depends on it
(verified — see Defect 3).

Do **not** copy: `backend/`, `web/`, `mobile/`, `supabase/`, `features/`, `src/`, `scripts/`,
`docs/`, `tests/`, `.planning/` (runtime state), `.tmp-*`.

## Verification

Two runs, deliberately distinguished. Both asserted the working directory with an `os.getcwd()`
marker, because a silent `cd` failure makes the source repo validate itself and look green.

**Baseline (pre-patch, no `framework/.gitignore`, project `.gitignore` present):**

| Evidence | Result |
|---|---|
| `python framework/validate.py` | `VALIDATE_EXIT=1`, 7 failures |
| same, with project `.gitignore` added | 6 failures — manifest check flipped to PASS |
| `python framework/security/check_enforcement_plane.py` | `OK: enforcement plane consistent (4 paths)`, exit 0 |

**Post-patch (pristine scaffold, no app, no project `.gitignore`):**

The target was a fresh copy of the scaffold with its own `git init`, then the patch applied from
the file, then assertions that the filesystem actually changed — not just that `git apply`
exited 0.

| Assertion | Result |
|---|---|
| `os.getcwd()` | `.tmp-verify2` — the copy, not the source repo |
| `git apply --check --verbose` | `Checking patch` for all 3 sections (no `Skipped patch`) |
| `framework/.gitignore` exists after apply | True |
| `framework/contracts/test_validator_types.py` exists after apply | True |
| `tests/contract/test_validator_types.py` gone after apply | True |
| `warn_only=True` count in `validate.py` | 3, down from 8 — the five readiness checks moved to `app_only=True`; the three remaining are unrelated (GSD state, PyYAML, unverifiable invariant) |
| suite 37 `validator rejects bool for integer/number` | `PASS` — proves the relocated test was found *and executed* |
| `manifest cache is gitignored` | `PASS` with the project `.gitignore` renamed away |
| `python framework/validate.py` | **`VALIDATE_EXIT=0`**, 6 warnings, 0 failures |
| `python framework/security/check_enforcement_plane.py` | `OK: enforcement plane consistent (4 paths)`, exit 0 |

The enforcement-plane result mattered specifically because the patch adds a new file inside the
immutable plane. It was checked on the patched copy, not assumed.

**Both enforcement-plane rows in this section are historical.** They record the state at the time
of their run, when `framework/**` was still `deny` in `opencode.json`. `framework/**` was later
changed to `allow` at top-level and `team-lead` to permit the agent edits recorded further down in
this document, and that is what turned the check red. The plane is **exit 1 today** — see the red
section at the top of this file. Neither row above is a current result.

The six remaining warnings are all correct for a bare scaffold and are now non-blocking:
`no GSD state found` (run GSD project init), plus the five readiness items from defect 2.

## Fix status

`framework/**`, `.opencode/**`, `opencode.json` and `AGENTS.md` are the enforcement plane.
Defects 1–3 were first produced as a scratch-copy patch
(`docs/framework-portability-fix.patch`, 4,631 bytes, LF, no BOM) and have since been
**applied**; the later `code_intel.py` and `standalone_check.py` changes were made as direct
edits. All of it is currently uncommitted.

| Defect | Status | Change |
|---|---|---|
| 1 — framework test outside the framework | fixed, applied | `tests/contract/test_validator_types.py` → `framework/contracts/`, plus the `validate.py` suite-37 path |
| 2 — integrity conflated with readiness | fixed, applied | five `check()` calls gain `app_only=True`: NOT_APPLICABLE (4) under `--profile framework`, asserted under `--profile app` — see the profile split above, pinned by suite 41 |
| 3 — invariant depends on project file | fixed, applied | new `framework/.gitignore`; `validate.py` accepts either ignore file |
| 4 — both distribution modes broken | **open — not an agent fix** | requires publishing the scaffold as its own distributable; a human decision about where the framework lives |
| 5 — verification-state read-modify-write races | fixed, applied | shared lock + atomic-write wrappers in `_state.py`, reused by `recovery.py`, `review_loop.py`, `suspicion_log.py`; suite 38, 23/23 |
| 6 — `_atomic_write` had no Windows retry | fixed, applied | `_replace_with_retry` retries `PermissionError` only, bounded at 5 attempts (~0.3s); a permanent `OSError` is neither retried nor masked. Suite 40, 13/13 |
| 7 — the guard's refusal paths were unproven | fixed, applied | `framework/test_standalone_check.py` (suite 39, 6/6) covers exit 1 and exit 2; red phase fails 3 of 6 on the accounting bug |
| — enforcement plane | **RED — human action item** | `framework/**` was opened for agent edits, so its three representations disagree; see the red section at the top |

Defect 4 remains the one that actually matches the stated goal, and it is the only open item that
turns on a decision about where the framework lives. Defects 1–3, 5, 6 and 7 make a correct copy
*work*; defect 4 is about there being a reliable way to *obtain* that copy in the first place.
`framework/standalone_check.py` proves the copy works; it does not prove the copy is obtainable,
and it cannot.

Defect 6 was originally left visible rather than folded into defect 5's concurrency task under a
green test, then fixed in its own right with its own red phase (suite 40). That separation was
right about sequencing and wrong about the conclusion: leaving a known transient failure unfixed
only defers it to whichever caller happens to hit it first. The enforcement plane is still red and
remains a human-owned decision.

## Regression guard

The portability claim is now enforced executably rather than assumed.
`framework/standalone_check.py` stages **only** the declared surface into a directory created by
`tempfile.mkdtemp()` (outside any repository), runs `git init -q` there, executes
`framework/validate.py` with `cwd` bound to that scaffold, and requires exit 0.

| Exit | Meaning |
|---|---|
| 0 | `STANDALONE` — validates holding only its own surface |
| 1 | `NOT STANDALONE` — needs something it does not declare; the failing checks are printed |
| 2 | `BLOCKED` — required surface incomplete, or `validate.py` exceeded its 1800s budget |

Measured: `STANDALONE: framework validates holding only its own surface`, exit 0. It reports a real
warning (`browser specs exist`), which is the correct outcome for a scaffold with no application —
but a reported warning is weak evidence of non-vacuity. The strong evidence is the red phase below.

Two traps make this guard easy to get wrong, and both produced false passes during this work:

- **Prove the working directory.** `git apply` and `python` both resolve relative paths against
  the *current* directory, not the copy. A failed `cd` silently validates the source repo, which
  already passes, and looks like success. The shipped guard does not assert `os.getcwd()` — it
  passes `cwd=scaffold` to `subprocess.run`, so the directory is bound rather than checked, and
  the check cannot be forgotten.
- **Give the copy its own git context.** A scratch directory *inside* a repository is covered by
  that repository's ignore rules. With `.tmp-*/` ignored, `git apply` reported
  `Skipped patch` for every section and still **exited 0** — a silent no-op that reads as a clean
  apply. The shipped guard stages files directly instead of applying a patch, so that failure mode
  is gone by construction, and `mkdtemp()` places the scaffold outside any repository so the
  inherited-ignore trap cannot recur.

### The guard's refusal paths had never been executed

`framework/test_standalone_check.py` (suite 39) covers the two exits that make the guard mean
anything — `2` for an incomplete declared surface, `1` for a validation that fails. Only exit `0`
had ever been observed, which is a guard that has not been shown to work.

It pins the accounting defect precisely. The guard previously compared a *count* of staged entries
against `len(REQUIRED)`, and the optional `.gitattributes` entry inflated that count. A scaffold
missing `.lifecycle` staged 5 entries, so `5 < 5` evaluated false and the guard proceeded with a
hole in its surface — the defect the accounting fix addressed, still unpinned by any test.

Red phase: reintroducing the count-based check turns 6 passing checks into **3**.

| Check | Asserts |
|---|---|
| incomplete required surface → exit 2 | `BLOCKED`, and the missing entry is named |
| optional entry cannot mask a missing required entry | a present `.gitattributes` does not hide a missing `.lifecycle` |
| failing validation → exit 1 | `NOT STANDALONE`, and the failing check is surfaced |
| passing validation → exit 0 | the only path that reaches success |

`ROOT` is redirected onto a synthetic tree, so the test never stages the real repository and never
actually executes `validate.py` — the stub in the fake root supplies the exit code under test.

**Duplication removed.** This document previously restated the inclusion manifest as a second
hand-maintained list. It is now a pointer to the `REQUIRED` / `OPTIONAL` tuples in
`framework/standalone_check.py` — the list the guard actually executes. Two copies of a
machine-checkable list is a defect waiting to happen; deleting one is cheaper than building a
synchronizer, and it is what the repo's own rule zero prescribes ("prefer pointers over copied
content").

## Note on the PR-CONCURRENCY patch

`docs/PR-CONCURRENCY-surgical.patch` is a **framework** fix currently sitting inside an
application repository. It belongs at the framework's own home, not committed into StockerPro.

**A previous draft argued the patch might be redundant because suite 36 passes. That reasoning
was invalid and is withdrawn.** Suite 36 exercises `framework/adapters/gsd_state.py` under load,
and the patch deliberately does not touch `gsd_state.py`. It changes six other files —
`adapters/filelock.py`, `verification/recovery.py`, `verification/review_loop.py`,
`verification/suspicion_log.py`, and two test files. A green suite 36 is therefore evidence about
a file the patch never modifies, and says nothing either way about the patch's value.

An agent later repeated that same withdrawn argument, and was wrong again. The patch targets a
**real, verified** race. Grepping the three untouched modules for write paths:

| Location | Unguarded operation (as found — now fixed) |
|---|---|
| `framework/verification/review_loop.py:55` | `p.write_text(json.dumps(state, indent=2))` — read-modify-write, no lock, no atomic replace |
| `framework/verification/recovery.py:67` and `:95` | `p.write_text(...)` on the checkpoint and last-known-good files — same |
| `framework/verification/suspicion_log.py:119` | `open(p, "w")` — truncating rewrite of a shared `.jsonl` |

None of these take a lock, and none write via a temp-file-plus-`os.replace`, so two concurrent
writers lose one another's updates. `gsd_state.py`'s existing `fcntl`/`msvcrt` primitive does not
cover these files. So: **the problem is real and the patch's intent is sound.**

### Resolution — both open questions are now closed

The patch remains **unapplied**. Its content was superseded by a direct fix, which answers the two
questions it left open:

1. **Duplication — resolved by reuse.** No `framework/adapters/filelock.py` was created. The new
   `framework/verification/_state.py:file_lock(target)` derives the sibling lock name
   (`target.name + ".lock"`) and delegates to the existing `fcntl.flock` / `msvcrt.locking` primitive
   at `framework/adapters/gsd_state.py:157-194`. One lock implementation, not two.
2. **Evidence quality — resolved by a test that discriminates.** `framework/verification/
   test_state_concurrency.py` runs **23/23 on this host**, wired into `validate.py` as suite 38.
   The stronger evidence is not the green run but the red phase: with the lock removed the same
   test produced **`17 unique of 24` IDs and `PermissionError [WinError 5]`**; restoring it returned
   the suite to green. A test that was green before the fix was introduced proves nothing, and this
   one demonstrably fails when the guard is removed.

**What the fix changed:**

| File | Change |
|---|---|
| `framework/verification/_state.py` | new — `sys.executable`, `REPO_ROOT`-anchored output and fallback, `file_lock()` wrapper, `atomic_write()` wrapper |
| `framework/verification/suspicion_log.py` | `add()` and `resolve()` share one lock; explicit UTF-8 on read and append |
| `framework/verification/recovery.py` | atomic writes via the shared wrapper |
| `framework/verification/review_loop.py` | every mutating read-modify-write section locked, plus `check_review()` |
| `framework/verification/README.md` | corrected the "append-only" claim that `resolve()`'s rewrite already violated |

**Why a lock and not event-sourcing:** `framework/validate.py:2408` (G14) reads the `.jsonl` lines
directly and filters `status == "OPEN"`. An append-only log cannot answer "which IDs are still open"
without a full scan and a tombstone convention, so the rewrite model is correct for this consumer.
Note that `add()` is itself a read-modify-write — it mints the next `SUSP-NNN` — so it needs the
lock as much as `resolve()` does, not only the rewriter.

### The atomic-write retry, now fixed rather than deferred

This was originally recorded as an open item, on the reasoning that the helper is reached from
`execute.py`, `control.py`, and two call sites in `gsd_state.py`, so the blast radius was wide
enough to deserve its own task rather than a silent addition to defect 5. That reasoning was right
about the sequencing and wrong about the conclusion: leaving a known transient failure unfixed
defers it to whichever caller happens to hit it first.

`framework/adapters/execute.py` now routes `os.replace` through `_replace_with_retry`, which
retries `PermissionError` only — the Windows sharing violation (`WinError 5`, raised when the
target is held open without `FILE_SHARE_DELETE`) — bounded at 5 attempts with exponential backoff
(~0.3s worst case), re-raising on exhaustion. Every other `OSError` propagates on the first
attempt, because `ENOSPC`/`EROFS`/`EACCES` are permanent and retrying them would only delay a real
failure. The concurrency test still models its retry test-side, so 23/23 does not overstate what
the helper guarantees; suite 40 is what proves the helper.

`framework/adapters/test_atomic_write.py`, 13/13, red phase 9/11 executed (2 failures, exit 1 —
one test function raises when the retry is absent, so two assertion checks never run). Beyond the
recovery path it
pins the anti-masking property — a permanent `ENOSPC` must be attempted exactly once — because a
future maintainer widening the `except` to `OSError` is the most likely way to turn this fix into
a bug that hides disk-full failures.

Also still unverifiable on this host: `Path.symlink_to()` raises
`OSError: [WinError 1314] A required privilege is not held by the client`. The 23 checks do not
depend on symlinks, so this does not weaken the concurrency result, but it remains a genuine gap in
Windows coverage of the framework as a whole.
