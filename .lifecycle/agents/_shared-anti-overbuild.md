# Shared constraint — Anti-overbuild

Referenced by: `implementer.md`, `architect.md`
Rationale: v1.2 addendum, self-optimization roadmap Tier 3 #8.

## Why this file exists

Every `retrospective` finding that lands tightens the framework — adds a
checklist item, a routing rule, a required gate. `gate_value_report.py`
(Tier 1 #3) balances that at the framework level. This file is the same
idea at the level of a single agent's output: an accumulating pile of past
findings creates real pressure to over-defend the *next* piece of work
speculatively, in a way no single retrospective asked for and no gate
checks for. Left unaddressed, defensiveness compounds the same way
under-defense does — just less visibly, because nothing currently fails a
gate for it.

## The four failure modes this bounds

**Hashing** — introducing checksums, integrity verification, or defensive
serialization for data that has no adversarial input path and no corruption
history. `evidence.checksum_algorithm: sha256` in `config.yml` is a real,
scoped requirement for immutable evidence references (§9.1.2); it is not
license to hash everything that moves.

**Edge cases** — handling inputs or states that cannot occur given the
contracts and environment baseline already established at F1/F7, "just in
case" a future change makes them possible. If the edge case cannot occur
today, name the future change that would make it possible and route it to
F10 impact analysis when that change actually happens — do not pre-build for
a scenario with no `SCN-*` and no `AC-*`.

**Rubrics** — inventing new checklist items, scoring rubrics, or acceptance
thresholds beyond what the gate's own checklist (`.lifecycle/checklists/`)
already requires, in response to a past finding that was actually specific
to a different feature. A rubric earned by one retrospective's `fix_target`
belongs in the checklist file itself, reviewed and landed the normal way
(see `retrospective` skill, "From finding to fix") — not silently
re-invented per-feature by whichever agent remembers the old finding.

**Overbuild** — implementing generality, configurability, or abstraction
beyond what the current `AC-*` set requires, justified by "this will
probably need to be flexible later." §6.7 (reuse before invention) already
requires a recorded search before introducing a new mechanism; this rule
adds the mirror-image requirement — do not introduce a *more general*
mechanism than the current requirement needs without the same recorded
justification §6.8 requires for a pattern choice.

## The test

Before adding anything defensive that no `AC-*`, no contract clause, and no
*currently open* retrospective finding requires, name:

1. the specific input, actor, or future change this defends against
2. why it cannot be handled later, at the point it actually becomes possible
3. the cost of being wrong in each direction (missing it now vs. building it now)

If (1) cannot be named concretely, the defense does not go in. This is not a
prohibition on caution — it is a prohibition on *unnamed* caution, which is
indistinguishable from padding once a codebase gets large enough that no one
reviewer can hold all of it in their head. Bulk without evidence, whether it
is speculative code or speculative process, is the same failure mode the
gate-value counterweight polices at the framework level.

## The other half: finish the change

A ceiling on speculative addition is not permission to leave a change
half-applied. Deliberate minimalism is about the *solution*, never about the
*change* — the smallest diff that still produces every mandated artifact
(tests, `VERIFICATION.md`, evidence), never a diff that starves one:

- **Finish every caller, test, and fixture the change breaks.** If the change
  alters a signature, a return shape, a config key, or an error contract,
  update every site that depends on it in the same change. A green build with a
  stale caller is not done.
- **Before editing a shared function, grep every caller.** If the defect lives
  in the shared code, fix the root cause once there; do not patch one caller
  and leave the rest broken. A guard duplicated into a single caller is the
  wrong shape — it belongs in the shared function.
- **Code that moves or merges keeps its validation and error handling.** A
  refactor does not get to silently drop a check; if that check is genuinely
  dead, removing it is its own named change with its own justification.

## What this does not change

This file bounds what an agent may add *unprompted*. It does not lower the
bar for what a gate, contract, or checklist item *requires* — G4's unit-test
negative/boundary coverage, G1's reliability-semantics declarations, and
every existing prohibition in the Implementer and Architect charters stand
exactly as written. Anti-overbuild is a ceiling on speculative addition, not
a floor reduction on required rigor.