# Routing edits — replace the dangling `security-research` skill reference

`security-research` is referenced but does not exist (no `SKILL.md` under that name). The
adopted skill is `security-audit`. These four files are **plane** files; apply by hand (or
with your editor) after copying the bundle.

| File | Line | Before | After |
|---|---|---|---|
| `framework/opencode/skill-routing.md` | 20 | ``| Security concern | `security-research` | Researcher | Threat modeling, vulnerability assessment |`` | ``| Security concern | `security-audit` | security-auditor | Threat modeling, vulnerability assessment |`` |
| `framework/opencode/agents/architect.md` | 24 | ``- `security-research` <em-dash> when architecture introduces security-sensitive boundaries`` | ``- `security-audit` — when architecture introduces security-sensitive boundaries`` |
| `framework/opencode/agents/planner.md` | 28 | ``| Security-sensitive | `security-research`, `unit-test-authoring` |`` | ``| Security-sensitive | `security-audit`, `unit-test-authoring` |`` |
| `framework/opencode/agents/team-lead.md` | 32 | ``| Security research | yes/no | `security-research` |`` | ``| Security research | yes/no | `security-audit` |`` |

Notes:

- In `architect.md:24` the em-dash is currently a **mojibake** sequence (`â€”`) — a pre-existing
  encoding defect. Replace the whole line as shown rather than only the skill name.
- `skill-routing.md:20` also names the agent column; update `Researcher` → `security-auditor`
  now that a dedicated agent exists.
- A non-plane copy of the same dangling reference lives in `framework/docs/AGENTIC_ARCHITECTURE.md`
  (lines 389, 417, 419); it is corrected in this change already.

Optional (recommended): add `security-audit` to the framework's surfacing profile so it is
discoverable, mirroring how other skills are surfaced.
