# Evidence provenance

Claims are the unit of truth-used-in-decisions; the claim ledger is the store. A conclusion
that is not recorded as a claim with reproducible provenance is not a conclusion â€” it is an
unverified observation.

## Claim classes

| class | meaning |
| --- | --- |
| environment | a fact about the runtime, toolchain, or configuration the work ran under |
| behavioral | what a system or component does when exercised |
| data | a fact about a dataset, record, or value |
| causal | a claim that one thing caused another |

## Classification vocabulary

`FACT | HYPOTHESIS | ASSUMPTION | UNKNOWN`. The default for anything not reproduced is
`UNKNOWN`. An agent may not silently promote a claim to a higher certainty class without the
evidence the class requires.

## The VERIFIED controlled term

A claim is `VERIFIED` only when it was confirmed under the canonical runtime (the same code
path the finding is about), is reproducible, names the exact command, has provenance
(evidence with `runtime` + `entry_point` + `reproduced: true`), and records expected vs
actual â€” plus an `independent_check` for high-impact claims. For provider-chain bugs the
canonical runtime is end-to-end (L3), not a unit harness.

## Scope limits are required, not optional

A `VERIFIED` claim must also carry `does_not_prove`: the specific thing this evidence
does **not** establish. Append rejects a `VERIFIED` claim without it
(`CLAIM_VERIFIED_NO_SCOPE_LIMIT`).

It is required because the failure it prevents is mechanical. E2 proves a cited path
resolves on disk; it cannot prove the citation supports the claim. Every error this rule
exists for was "cited path exists, conclusion does not follow" â€” a stale exit code, a file
that exists for a different reason than claimed, a line that exists but does not say what
was reported. Naming the limit forces that gap to be stated instead of passed over.

`does_not_prove` records the limit, it does not police it. `"does_not_prove": "nothing"`
satisfies the check and defeats the intent; treat a rising rate of empty scope limits as
a review signal, the way a rising rate of `none_human_judgement` is one.

Use `UNKNOWN` for a limit you have not measured. "Not checked" is a valid scope limit;
"nothing" is not an answer.

## Verification levels

- **L1 static** â€” types/compile/config inspection.
- **L2 behavioral** â€” targeted test/harness reproduction.
- **L3 end-to-end** â€” full flow through the provider chain.

L3 is the default for provider-chain bugs; a lower level must be justified in the claim.

## Runtime-scoped claims

A claim names the runtime it was verified under; it is not automatically true for other
runtimes.

## Logs are not evidence of behaviour

"Do not infer system behavior from logs when the behavior can be directly tested."

"A log entry is evidence of what was logged, not necessarily evidence of what happened upstream or downstream."

## Ledger usage

Agents append claims via `python3 framework/claims/ledger.py append --json '{...}'`; the G11
gate judges ledger validity on every functional run; G-VERIFY (team-lead rule) is the gate on
findings; insufficient provenance is blocker signal `EVIDENCE_INSUFFICIENT` (retry action:
`gather_provenance_or_downgrade_claim`).
