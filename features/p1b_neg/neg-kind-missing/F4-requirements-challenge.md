# F4 — Independent Requirements Challenge

Feature: FEAT-2026-001

```yaml
participants:
  - { agent_id: ver-2e88, role: verifier, session_id: s-2026-08-25-c }
  - { agent_id: rev-7f2a, role: reviewer, session_id: s-2026-08-26-a }
requirements_author: { agent_id: res-9b41, session_id: s-2026-08-24-b }
independence: both challengers differ from the author in agent_id and session_id
```

## Findings

| id | Finding | Class | Owner | Resolution |
|---|---|---|---|---|
| CHF-1 | "supported value" in AC-001-1 is unbounded | blocking | res-9b41 | AC-001-8 added with an explicit range and reject code |
| CHF-2 | No statement of what happens to a losing concurrent writer | blocking | res-9b41 | AC-001-9 extended with the supersede notification |
| CHF-3 | Reapply order relative to first audio output unstated | blocking | res-9b41 | AC-001-11 added, ordering made explicit |
| CHF-4 | Rollback direction absent; only upgrade considered | blocking | res-9b41 | AC-001-12 extended to cover rollback readability |
| CHF-5 | Alert-path exclusion asserted in F1 but not required anywhere | blocking | res-9b41 | folded into AC-001-7 as a verifiable clause |
| CHF-6 | NFR-1 said "promptly" with no method | blocking | res-9b41 | threshold and measurement method added |
| CHF-7 | Offset unit not stated — dB or scalar step | non-blocking | res-9b41 | dB confirmed; recorded in the glossary |

## Risk score review (§5.2.2)

SCN-6 detectability lowered from 3 to 1 by the Verifier: a concurrent-write defect across the IPC boundary will not surface without a targeted test. Score moved 24 → 40, band medium → high, which earns it an F15 case. SCN-13 impact raised 3 → 4; seat cross-talk is a customer-visible correctness failure. The author's own scores were not accepted unchanged.

Zero unresolved ambiguities remain. All six blocking findings closed by amendment to F3.
