# Security audit

When the `security-audit` skill is invoked — and when it is not.

## Invoke

- **On demand** — the user asks to find vulnerabilities, audit, or pen-test. Entry point:
  `/security-audit`.
- **Review** — a change touches a trust boundary, authentication/authorization, a data
  handling or isolation path, or an API contract (a contract change is security-sensitive by
  default).
- **Design** — to derive the plan's `<threat_model>` register from the skill's attack-class
  taxonomy (`ATTACK-CLASSES.md`).

## Do not invoke

- For ordinary feature work with no boundary/auth/contract/data impact.
- To satisfy a checklist. The skill rejects checklist-as-finding, and so must you.

## How

- **Design time** — translate attack classes into the plan's `<threat_model>` (STRIDE).
  There is no execution and no audit run: with no source to trace, a `confirmed` finding is
  impossible.
- **Review time** — `team-lead` (the sole delegator) dispatches a **fresh** `security-auditor`.
  The implementer must never audit their own change.
- **Execution** — only through `bash framework/gates/g_sandbox.sh` and
  `python3 framework/adapters/sandbox.py`. If the sandbox is not enforceable, the audit is
  **source-only** and must say so.
- **Completion** — `bash framework/gates/g18_security_audit.sh` must pass. A confirmed
  high/critical finding blocks completion until resolved or explicitly accepted by a human.
