---
name: api-design
description: Design HTTP API endpoints before implementation. Sits between software architecture and contract-authoring. Covers endpoint responsibility, consumer identification, input/output/error contracts, security, idempotency, versioning, and backward compatibility. Use when adding or modifying API endpoints.
---

# API Design

API design is the boundary between what the system does and what consumers see. Design the boundary before implementing the body.

## Position in workflow

```
software-architecture-design
         ↓
     api-design (this skill)
         ↓
    contract-authoring
         ↓
     implementer
```

## Mandatory sequence

```
Requirement
    ↓
API responsibility (what this endpoint does)
    ↓
Consumer identification (who calls this)
    ↓
Input contract (request shape)
    ↓
Output contract (response shape)
    ↓
Error contract (failure shapes)
    ↓
Side effects (what changes beyond the response)
    ↓
Security (auth, authz, rate limiting)
    ↓
Idempotency (safe to retry?)
    ↓
Versioning strategy
    ↓
Backward compatibility
    ↓
Contract test requirements
```

## Required output

```yaml
api_design:
  requirement_id: REQ-XXX
  endpoint:
    method: [GET | POST | PUT | PATCH | DELETE]
    path: [/api/v1/resource]
    purpose: [single sentence]
  consumers:
    - consumer: [who calls this]
      use_case: [why they call it]
  request:
    path_params:
      - name: [param]
        type: [type]
        description: [what it is]
    query_params:
      - name: [param]
        type: [type]
        required: [true | false]
        description: [what it is]
    body:
      content_type: [application/json]
      schema:
        fields:
          - name: [field]
            type: [type]
            required: [true | false]
            description: [what it is]
            constraints: [validation rules]
  response:
    success:
      status: [200 | 201 | 204]
      schema:
        fields:
          - name: [field]
            type: [type]
            description: [what it is]
    errors:
      - status: [400 | 401 | 403 | 404 | 500]
        condition: [when this error occurs]
        body:
          error_code: [machine-readable code]
          message: [human-readable message]
  side_effects:
    - [what changes beyond the response]
  security:
    authentication: [required | none]
    authorization: [role-based | resource-based | none]
    rate_limiting: [none | per-user | global]
  idempotency:
    idempotent: [true | false]
    mechanism: [if-none-match | idempotency-key | natural]
  versioning:
    strategy: [url | header | query]
    backward_compatible: [true | false]
  contract_tests:
    - test: [what the contract test proves]
      method: [test method]
```

## Design principles

1. **Consumer-driven** — design for how consumers need to use it, not how the implementation works
2. **Consistent** — follow existing API patterns in the repo
3. **Minimal** — expose only what consumers need, not implementation details
4. **Typed** — every field has a type and constraints
5. **Versioned** — breaking changes get a new version

## Integration with other skills

- Requires: `software-architecture-design` output (system context)
- Feeds: `contract-authoring` (API shape → OpenAPI schema)
- Feeds: `implementer` (API design → implementation)
- Requires: `technical-validation` when API behavior assumptions exist
- Requires: `database-schema-design` when API depends on data model changes
