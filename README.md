# OpenCode Agentic Engineering Framework v1.0 — scaffold

Runtime OpenCode. Workflow and state GSD. Seven agents. Skills for specialisation. Code
intelligence as an accelerator. Contracts as integration boundaries. Gates as objective proof.

## Install

```bash
cp -r . /path/to/your/repo/        # merge into the repository root
cd /path/to/your/repo
bash framework/bootstrap.sh        # detect, resolve, emit, validate
opencode --agent team-lead
```

Bootstrap is sequential and stops on the first failed stage. Stage 3 prints the
adopt-before-extend audit — complete it before implementing Reviewer, Verifier profiles, or
graph access.

## Layout

```
opencode.json                     runtime config, agents, permissions, skills paths
AGENTS.md                         stable global rules only (rule zero, do-not-invoke, evidence)
.opencode/
  rules/                          evidence applicability, DoD vs verification, handoff shape
  agents/                         seven agent definitions
  tools/context-builder.ts        pointer resolver, capped excerpts
  plugin/telemetry.ts             v2 collector, one record per session
  skills/                         framework-authored: frontend-react, backend-python, contract-authoring,
                                  browser-verification; plus ~71 gsd-* distribution skills
  adapters/gsd_state.py           GSD state adapter (installed distribution only in v1)
  adapters/code_intel.py          capability interface with the 4-tier priority ladder
  adapters/host.py                runtime-neutral host interface (THE only host-aware component)
  adapters/hosts/opencode.py      OpenCode backend — fully implemented
  adapters/hosts/dsh.py           DeepSeek Harness — DECLARED, NOT SUPPORTED (runtime peer)
  adapters/opencode_detect.py     DEPRECATED shim -> host.py
  audit_check.py                  adopt-before-extend audit completeness (exit 3 = undecided)
  gates/EXIT_CODES.md             AUTHORITATIVE gate exit contract; docs must match this
  gates/g1..g8                    executable gates, real exit codes
  verifier/profiles.yaml          profiles and impact-to-gate mapping
  architecture_rules.yaml         declared boundaries for G3
  retry_policy.yaml               bounded retries, named escalation
  ADOPT_AUDIT.md                  required install step
  bootstrap.sh / validate.py      install and validation suite
```

Model tuning and reporting live in `framework/`: `models/profiles.sh` switches
per-agent models by profile (`baseline | tiered | cheap | reset`), and
`telemetry/report.py` aggregates session records into cost, rework, and
bottleneck reports.


## The two governing rules

Non-duplication. Do not rebuild what OpenCode, GSD, the code intelligence provider, Git, or the
host already provides. Wrap it.

Do not invoke gratuitously. Name the specific need an agent satisfies that the active agent, a
skill, GSD, the provider, or a gate cannot. No need, no delegation.

## Two axes, not one

Complexity governs planning depth. Impact governs verification breadth.

```yaml
complexity: L0 | L1 | L2 | L3 | L4
impact:
  scope: local | component | cross_component | system
  contract_change: false
  public_api_change: false     # forces at least cross_component
  data_change: false
  security_sensitive: false
```

Impact is re-derived from the actual diff after implementation. A wider class triggers expansion
and the gates it requires. Unknown impact is never no impact.

## What v1 deliberately does not do

Contracts cover HTTP APIs only. Event, database, and service-interface contracts are
documentation-only and no gate enforces them. The GSD adapter supports the installed distribution
only; a second distribution is a conformance target proven by `gsd_state.py selftest`. There is no
project memory system, no orchestration layer, no graph store, no task tracker, and no second
context manager — GSD, Git, and the provider already own those.

## Rollout

One vertical slice, one repository. Five agents active, contracts on your single real
frontend/backend seam, G1 and G4 wired. Twenty real tasks. Read rework rate and defect-catch
location from `<state_root>/telemetry/records.jsonl`.

Add a capability only when a named defect class escaped and no existing agent, skill, or gate
could have caught it.
