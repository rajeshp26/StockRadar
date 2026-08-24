# Contract system — v1

Scope is deliberately narrow: **HTTP APIs via OpenAPI only**. Event schemas, Avro, database
contracts and service-interface contract engines are explicitly out of scope for v1. Widen
scope only after the rework-rate data shows a defect class that HTTP contracts cannot catch.

## The three artefacts per contract

| Artefact | Path | Role |
| --- | --- | --- |
| Schema | `.planning/contracts/<id>.openapi.yaml` | Source of truth for the boundary |
| Metadata | `.planning/contracts/<id>.meta.yaml` | Owner, version, consumers, compatibility |
| Tests | `tests/contract/test_<id>.py` | The executable gate |

Generated types are derived, never authored:

- `src/backend/contracts/<id>.py`
- `src/frontend/contracts/<id>.ts`

## Commands

```bash
python3 framework/contracts/validate_schema.py .planning/contracts/*.openapi.yaml
python3 framework/contracts/gen_types.py --schema .planning/contracts/api-004.openapi.yaml
python3 framework/contracts/gen_types.py --check      # drift detection
python3 tests/contract/test_api_004.py                # standalone, no pytest needed
bash framework/gates/g1_contract.sh                   # the gate
```

## What G1 enforces

1. **Schema validity** — structural check always runs; an external linter can add findings but
   never substitutes for it.
2. **Type sync** — committed generated types are diffed against a fresh generation. Drift means
   someone hand-edited types or the schema moved underneath a consumer.
3. **Change vs violation** — a modified schema is a `CONTRACT_CHANGE` routed to Architect and
   human gate H2. It is *not* an implementation defect. This precedence outranks test failure,
   because an incompatible change makes consumer tests fail by definition.
4. **Contract tests** — must exist, must contain tests, must execute. Absent tests fail the gate.

## Verified violation matrix

Each row was produced by mutating the fixture and observing the gate.

| # | Violation | Caught by | Exit |
| --- | --- | --- | --- |
| A | Implementation returns undeclared 500 | contract test | 1 |
| B | Response omits required `token_type` | response schema validation | 1 |
| C | Boundary validation removed | request schema tests | 1 |
| D | Frontend hand-edits generated types | drift check | 1 |
| E | Schema tightened incompatibly | `CONTRACT_CHANGE` → Architect + H2 | 1 |
| F | Contract present, `tests/contract` deleted | gate precondition | 1 |
| G | New contract, no generated types | drift check | 1 |
| — | Clean baseline | all three checks green | 0 |

## Design rules

**Tool unavailability is never a verdict.** A missing linter, absent pytest, or failed network
fetch reports as unavailable or is substituted. It never reads as a pass, and never as a
violation. Both directions of that confusion were real bugs found by execution.

**No optional install may be required.** Contract tests run under pytest when present and
standalone otherwise. A gate that only works after `pip install` is not a gate.

**Generated paths derive from the contract id.** A fixed output path makes the second contract
overwrite the first, which then surfaces as type drift — a failure for entirely the wrong reason.

## Adding a contract

1. Write `.planning/contracts/<id>.openapi.yaml` and its `.meta.yaml`.
2. Run `gen_types.py --schema` to produce consumer types. Commit them.
3. Write `tests/contract/test_<id>.py` asserting implementation against schema, following the
   API-004 pattern: derive expectations from the contract, never restate them.
4. Run `bash framework/gates/g1_contract.sh` and confirm green.
5. Mutate the implementation once and confirm the gate goes red. An untested gate is a decoration.
