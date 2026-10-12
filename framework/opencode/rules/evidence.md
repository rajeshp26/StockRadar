# Evidence applicability

| Requirement shape | Strongest applicable evidence |
| --- | --- |
| API returns a status for given input | Contract test or integration test, with exit code |
| Business rule produces a value | Unit test |
| Type or interface correctness | Type check and build |
| Visual alignment or styling | Browser screenshot plus DOM/runtime inspection |
| Interaction flow end to end | Browser navigation and interaction, with console output |
| No unauthorised dependency | Dependency and security scanner |
| Authorisation denies a role | Integration test against a running system |
| Latency budget | Measured benchmark on representative data |
| Migration applies and rolls back | Executed migration in a disposable environment |
| Responsive layout at a width | Playwright run under a project with that viewport |
| Mandated tool/library is used | G5 stack conformance exit code |
| Conditional visual tool is permitted | Ledger entry naming requirement and approver |

Name the applicable class per requirement before running anything. Record why any class was
judged inapplicable.

## Unverifiable is not pass

When the applicable evidence class cannot be produced — no browser driver, no benchmark
harness, no disposable environment — record the requirement as **unverifiable** and name what
is missing. A gate that cannot run reports exit 2 (blocked) or 3 (unverifiable), never 0.

Three failure modes this rule exists to prevent, each of which was a real bug in this
framework: a missing YAML parser reading as architectural compliance; an unavailable schema
validator reading as an invalid schema; an absent test runner reducing the required check
count to zero and passing.

## Browser evidence is mandatory for visible behaviour

Visual alignment, interaction flow, and responsive layout cannot be proven by a unit test.
`framework/gates/g6_browser.sh` is the evidence. Authoring a spec with the Playwright MCP
server does not count — MCP output is a conversation transcript and gets pruned. Committed
specs plus an exit code are the durable artefact.

## Claim discipline

Unverified observations are claims, classified HYPOTHESIS/UNKNOWN, recorded in the claim
ledger; they are never conclusions. See framework/opencode/rules/evidence-provenance.md.
