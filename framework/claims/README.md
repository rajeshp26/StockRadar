# Claim ledger — evidence provenance

Answers one question: **what was actually verified, and how?**

A claim is the unit of truth-used-in-decisions. Every conclusion an agent reports should be
traceable to a claim recorded in the ledger with the provenance that lets a second agent
reproduce it. The ledger is append-only JSONL under the GSD state root; the G11 gate judges
its validity on every functional run.

## Layout

```
<state_root>/claims/ledger.jsonl     append-only claim records, one JSON object per line
```

The state root is resolved exactly like the rest of the framework
(`python3 framework/adapters/gsd_state.py state-root`), so the ledger lives beside
`retro/`, `blockers.yaml`, and the other GSD state.

## Usage

```bash
python3 framework/claims/ledger.py path                 # print the resolved ledger path
python3 framework/claims/ledger.py append --json '{...}'  # validate, timestamp, append
python3 framework/claims/ledger.py analyse              # judge the latest record per claim_id
python3 framework/claims/ledger.py integrity         # E1-E8 check: evidence is real, on-task, reviewed, not reused
bash framework/gates/g14_integrity.sh                    # gate: 0 integrity ok | 1 violations | 2 blocked | 4 no claims
bash framework/gates/g11_evidence.sh                    # gate: 0 valid | 1 invalid | 2 blocked | 4 no claims
```

`append` prints the assigned `claim_id` as JSON on stdout and exits 0. On validation failure
it prints one error code on stdout and exits 1 (never 2). If no `claim_id` is supplied it
auto-assigns `CLM-<20-digit ns-epoch>` -- a strictly increasing id clock that needs no
ledger scan, so append cost is independent of the store size.

## Record schema

| field | required | meaning |
| --- | --- | --- |
| `claim_id` | auto or supplied | `CLM-<20-digit ns-epoch>` or a caller-supplied id; ids are monotonically increasing, and multiple records per id are history, latest wins |
| `task_id` | yes | task that produced the claim |
| `agent` | yes | agent that recorded it |
| `statement` | yes | the claim, in one sentence |
| `claim_type` | yes | `environment` \| `behavioral` \| `data` \| `causal` |
| `classification` | yes | `FACT` \| `HYPOTHESIS` \| `ASSUMPTION` \| `UNKNOWN` |
| `status` | yes | `UNVERIFIED` \| `VERIFIED` \| `REFUTED` \| `PARTIALLY_VERIFIED` |
| `impact` | yes | `high` \| `medium` \| `low` |
| `evidence` | no | list of `{id, kind, command, runtime, entry_point, reproduced, expected, actual, result, env, disconfirmation}` |
| `verified_by` | no | the command that verified the claim |
| `independent_check` | no | a second, different verification command (required for high impact) |
| `does_not_prove` | no for v1, yes for v2 | what this evidence does **not** establish. Required for every v2 `VERIFIED` claim; must be a non-empty string |
| `schema_version` | stamped | the rule set in force when the record was written. `append` stamps the current version on every write, unconditionally, so a caller cannot declare a weaker rule set for itself. An absent value means v1 |
| `git_sha` | no | git SHA for evidence provenance tracking |
| `execution_timestamp` | no | ISO-8601 timestamp of when evidence was generated |
| `created` | auto | ISO-8601 timestamp added by `append` |

## Extended Evidence Taxonomy

From Aetox Senior Architect Agent patterns, evidence can be classified by its provenance strength:

| Kind | Meaning | When to Use |
| --- | --- | --- |
| `DIRECT` | Direct artifact/execution evidence observed firsthand | Test output, build logs, runtime output |
| `DERIVED` | Computed from direct evidence | Analysis results, aggregations |
| `INFERRED` | Reasonable conclusion but not directly observed | Code inspection, pattern matching |
| `ASSERTED` | Agent claims it happened but evidence insufficient | Agent summary without proof |
| `UNOBSERVED` | Required evidence cannot establish the result | Missing test, no execution record |
| `CONTRADICTED` | Evidence actively conflicts with the claim | Conflicting test results |

The taxonomy determines confidence derivation: DIRECT > DERIVED > INFERRED > ASSERTED. UNOBSERVED and CONTRADICTED are never acceptable for VERIFIED claims.

Evidence entries may additionally bind a command environment and a disconfirmation
verdict:

| evidence field | meaning |
| --- | --- |
| `env` | canonical command-environment id (`ENV-0001`) that must resolve to a recorded `record-env` row in `<state_root>/contexts/environments.jsonl`; free-form strings (legacy) stay legal |
| `disconfirmation` | structured refutation verdict: `confirmed` \| `refuted` \| `inconclusive` |

Confidence is **derived, never stored**: `analyse` computes a per-claim confidence
(LOW / MEDIUM / HIGH / VERY_HIGH) from evidence structure — provenance present, verdict
present, independent check present — and reports it in `by_confidence`. A record that
carries a `confidence` field is refused (`CLAIM_STORED_CONFIDENCE`); there is no field
to game.

## Validation rules

Append-time and analyse-time validation are the same rules, so a hand-edited or corrupt
store is caught exactly like a rejected append:

| code | condition |
| --- | --- |
| `CLAIM_INCOMPLETE` | a required top-level field is missing, empty, or None |
| `CLAIM_BAD_VOCAB` | a vocabulary value is outside its list (claim_type / classification / status / impact / evidence kind / result; `reproduced` must be bool) |
| `CLAIM_BAD_SCHEMA_VERSION` | `schema_version` is present but is not an int >= 1 (`"2"`, `true`, `0`, `2.0`, `null`). An **absent** value is legal and means v1; a **malformed** value is a defect, because coercing it to v1 exempts the record from the very rules it claims to satisfy |
| `CLAIM_FACT_UNVERIFIED` | classification `FACT` with status other than `VERIFIED` |
| `CLAIM_CAUSAL_NO_RUNTIME` | claim_type `causal`, classification `FACT`, without evidence of a runtime-backed kind (`DIRECT` \| `DERIVED` \| `command_run` \| `artifact` \| `observation`) carrying runtime + entry_point with `reproduced: true` — static configuration, code inspection, logs, or plausibility cannot establish causation |
| `CLAIM_VERIFIED_NO_COMMAND` | status `VERIFIED` (or `PARTIALLY_VERIFIED`) without `verified_by` |
| `CLAIM_VERIFIED_NO_PROVENANCE` | status `VERIFIED` without evidence naming runtime + entry_point with `reproduced: true`; `PARTIALLY_VERIFIED` without evidence whose result is pass or fail |
| `CLAIM_VERIFIED_NO_INDEPENDENT_CHECK` | status `VERIFIED`, impact `high`, no `independent_check` |
| `CLAIM_VERIFIED_NO_SCOPE_LIMIT` | status `VERIFIED` whose `does_not_prove` is missing, empty, blank, or not a string. A `VERIFIED` claim that states no limit is a claim that proves everything |
| `CLAIM_REFUTED_NO_EVIDENCE` | status `REFUTED` without evidence with `result: fail` and both `expected` and `actual` |
| `CLAIM_ENV_UNKNOWN` | an evidence `env` names a canonical `ENV-` id that does not resolve to a recorded command environment |
| `CLAIM_BAD_DISCONFIRMATION` | an evidence `disconfirmation` is outside `confirmed` \| `refuted` \| `inconclusive` |
| `CLAIM_DISCONFIRMED_BUT_VERIFIED` | status `VERIFIED` while an evidence entry carries `disconfirmation: refuted` |
| `CLAIM_STORED_CONFIDENCE` | the record carries a `confidence` field — confidence is derived at analyse, never stored |

`HYPOTHESIS` / `ASSUMPTION` / `UNKNOWN` with status `UNVERIFIED` are legal and need no
evidence. The default classification for anything not reproduced is `UNKNOWN`.

## Rule evolution

Adding a rule is a schema decision, not only a code change. Every rule carries a class,
and the class decides what happens to claims already in the store.

| class | what it judges | history |
| --- | --- | --- |
| `DERIVABLE` | something the ledger computes from the record itself -- a required field, a vocabulary value, an internal inconsistency | applies at every version, v1 included. A v1 record that violates it was always invalid |
| `AUTHOR_SUPPLIED` | information only the recording agent has -- whether an independent check happened, what the evidence does not establish | applies from the version that introduced it. Earlier records are grandfathered, not re-judged |

The mechanism:

- `LEDGER_SCHEMA_VERSION` is the current version; a record with no `schema_version` is v1.
- `append` stamps the current version on every write, unconditionally. A rule added today
  cannot become a retroactive verdict on a record written before it.
- `skipped_rules(record)` returns the `AUTHOR_SUPPLIED` rules that did not apply because
  the record predates them, so `analyse` reports them as grandfathered instead of silently
  passing them.
- `_rule_applies` resolves a code through the registry and raises `KeyError` for an
  unregistered one. It never defaults a missing code to "applies to everything": that
  fallback would let a typo retroactively judge the whole store, silently, because a
  mistyped code has no other symptom.

### Adding a rule

1. Classify it `DERIVABLE` or `AUTHOR_SUPPLIED`. If the judgement requires knowledge only
   the recording agent has, it is `AUTHOR_SUPPLIED`.
2. Add it to `LEDGER_RULES` in `ledger.py` with `cls` and `since`. Bump
   `LEDGER_SCHEMA_VERSION` when the rule needs information older records cannot hold.
3. Document the code in the table above, and add it to `_RULE_TARGETS` if it is measured.
4. Add tests to `framework/claims/test_ledger_rules.py` for the v2 case, the v1
   grandfathered case, and the DERIVABLE case where applicable.
5. Run `python3 framework/claims/ledger.py analyse` against the real store and confirm
   `invalid` is still empty. A rule that invalidates existing records is a migration, not
   a patch.
6. Confirm `registry_gaps()` is empty -- a code emitted anywhere but registered here is an
   unroutable rule.

## Exit codes

| command | 0 | 1 | 3 |
| --- | --- | --- | --- |
| `append` | accepted, claim_id printed | validation code printed | — |
| `analyse` | all latest records valid | invalid records found | ledger empty or missing |
| `integrity` | all latest claims pass E1-E8 | E-code violations listed | ledger empty or missing |

`analyse` never exits 2. The G11 gate maps its exit 3 to NOT_APPLICABLE (4): no claims
recorded means nothing to judge, which is never a pass.

## Rules

The behavioural contract for claims lives in `.opencode/rules/evidence-provenance.md`:
claim classes, the VERIFIED controlled term, verification levels L1/L2/L3, runtime-scoped
claims, and the two log rules. Insufficient provenance is blocker signal
`EVIDENCE_INSUFFICIENT` (retry action `gather_provenance_or_downgrade_claim`).

