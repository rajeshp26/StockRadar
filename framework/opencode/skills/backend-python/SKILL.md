---
name: backend-python
description: Implement or modify Python backend code in this repository. Use when the task touches src/backend, an API endpoint, business logic, persistence, or validation at a service boundary. Covers contract-driven boundary validation and the tests that prove it.
---

# Backend Python implementation

## Boundary validation is contract-driven

A service boundary validates against the generated contract module, never against a
hand-written copy of the same shape. `src/backend/contracts/` is generated and carries a
do-not-edit banner; G1 detects hand edits as drift.

See `src/backend/auth_service.py` for the pattern: import the generated model, validate the
request against it, and construct the response through it.

## Rules

- Never widen a response beyond what the contract declares. An undeclared status code or an
  extra field is a contract violation, and G1 catches it.
- Never remove boundary validation to make a test pass. That is the failure the gate exists
  to detect.
- A required field stays required. Tightening or loosening a schema is a contract change: it
  routes to the Architect and human gate H2, not a quiet edit.

## Tests

Contract tests live in `tests/contract/` and run under pytest when available, standalone
otherwise — a gate that needs `pip install` first is not a gate. Keep that property when
adding tests: no import of a library that may be absent without a fallback.

## Architecture boundaries

`framework/architecture_rules.yaml` declares forbidden imports and G3 enforces them. Notably
`src/domain/` may not import `requests`, `axios`, `psycopg`, or `fetch` — domain logic stays
transport-free. A boundary not written in that file is not enforced; if you need a new one,
hand back to the Architect rather than inventing it.
