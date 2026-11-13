---
name: contract-authoring
description: Create or change an HTTP API contract. Use when a task adds an endpoint, alters a request or response shape, or when G1 reports CONTRACT_CHANGE. Covers OpenAPI authoring, type generation, contract tests, ownership, and the H2 human gate.
---

# Contract authoring

v1 scope is HTTP APIs only — OpenAPI, generated types, contract tests. Event schemas, Avro,
database contracts, and service-interface contracts are deliberately out of scope. Do not
introduce them.

## Anatomy

Each contract is three files under the state root's `contracts/`:

- `api-NNN.openapi.yaml` — the schema, the single source of truth
- `api-NNN.meta.yaml` — `id`, `version`, `status`, `owner`, `consumers`
- generated types in `backend/contracts/` and `web/src/contracts/`

Regenerate after any schema edit:

```bash
python3 framework/contracts/gen_types.py --schema <path-to-openapi>
bash framework/gates/g1_contract.sh
```

## A contract without tests is not a gate

G1 fails when `backend/tests/contract/` is absent for a changed contract. Informational YAML was the
original design flaw; the test suite is what makes the boundary real. Every contract needs
tests covering: each declared status, required-field rejection, optional-field omission, and
the absence of undeclared responses.

## Changing an existing contract

G1 distinguishes a *violation* (implementation drifted from schema) from a *change* (schema
itself moved) by diffing the schema against `HEAD`. A change:

1. routes to the Architect, who owns contract versions
2. requires human gate **H2** when incompatible
3. invalidates in-flight parallel work against the old version — the Team Lead re-plans
   affected tasks rather than letting a consumer discover it at integration

Bump `version` in the meta file. Never edit a shipped version in place.

## Ownership

`owner` in the meta file is authoritative. A consumer agent may not change a contract to suit
its implementation; that inverts the boundary. Hand back to the Team Lead instead.
