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
bash framework/gates/g11_evidence.sh                    # gate: 0 valid | 1 invalid | 2 blocked | 4 no claims
```

`append` prints the assigned `claim_id` as JSON on stdout and exits 0. On validation failure
it prints one error code on stdout and exits 1 (never 2). If no `claim_id` is supplied it
auto-assigns `CLM-NNN`, continuing the highest existing number across all records.

## Record schema

| field | required | meaning |
| --- | --- | --- |
| `claim_id` | auto or supplied | `CLM-NNN` or a caller-supplied id; multiple records per id are history, latest wins |
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
| `created` | auto | ISO-8601 timestamp added by `append` |

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
| `CLAIM_FACT_UNVERIFIED` | classification `FACT` with status other than `VERIFIED` |
| `CLAIM_VERIFIED_NO_COMMAND` | status `VERIFIED` (or `PARTIALLY_VERIFIED`) without `verified_by` |
| `CLAIM_VERIFIED_NO_PROVENANCE` | status `VERIFIED` without evidence naming runtime + entry_point with `reproduced: true`; `PARTIALLY_VERIFIED` without evidence whose result is pass or fail |
| `CLAIM_VERIFIED_NO_INDEPENDENT_CHECK` | status `VERIFIED`, impact `high`, no `independent_check` |
| `CLAIM_REFUTED_NO_EVIDENCE` | status `REFUTED` without evidence with `result: fail` and both `expected` and `actual` |
| `CLAIM_ENV_UNKNOWN` | an evidence `env` names a canonical `ENV-` id that does not resolve to a recorded command environment |
| `CLAIM_BAD_DISCONFIRMATION` | an evidence `disconfirmation` is outside `confirmed` \| `refuted` \| `inconclusive` |
| `CLAIM_DISCONFIRMED_BUT_VERIFIED` | status `VERIFIED` while an evidence entry carries `disconfirmation: refuted` |
| `CLAIM_STORED_CONFIDENCE` | the record carries a `confidence` field — confidence is derived at analyse, never stored |

`HYPOTHESIS` / `ASSUMPTION` / `UNKNOWN` with status `UNVERIFIED` are legal and need no
evidence. The default classification for anything not reproduced is `UNKNOWN`.

## Exit codes

| command | 0 | 1 | 3 |
| --- | --- | --- | --- |
| `append` | accepted, claim_id printed | validation code printed | — |
| `analyse` | all latest records valid | invalid records found | ledger empty or missing |

`analyse` never exits 2. The G11 gate maps its exit 3 to NOT_APPLICABLE (4): no claims
recorded means nothing to judge, which is never a pass.

## Rules

The behavioural contract for claims lives in `.opencode/rules/evidence-provenance.md`:
claim classes, the VERIFIED controlled term, verification levels L1/L2/L3, runtime-scoped
claims, and the two log rules. Insufficient provenance is blocker signal
`EVIDENCE_INSUFFICIENT` (retry action `gather_provenance_or_downgrade_claim`).