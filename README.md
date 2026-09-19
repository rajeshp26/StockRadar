# OpenCode Agentic Engineering Framework v1.0 — scaffold

Runtime OpenCode. Workflow and state GSD. Forty agents (7 core + 33 GSD distribution). Skills
for specialisation. Code intelligence as an accelerator. Contracts as integration boundaries.
Gates as objective proof. An agent-immutable enforcement plane as the security boundary.

Full walkthrough of every component and flow: **`docs/AGENTIC_ARCHITECTURE.md`** (read that
first if you want the whole picture).

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
opencode.json                     runtime config: model, instructions, permissions, agents,
                                  MCP servers, references, skills paths, plugin, compaction
AGENTS.md                         stable global rules only (rule zero, do-not-invoke, evidence)
                                  + the enforcement-plane fence
.opencode/
  agents/                         40 agent definitions (7 core + 33 gsd-*)
  rules/                          evidence applicability, DoD vs verification, handoff shape,
                                  blockers, bash hygiene, background tasks, delegation protocol,
                                  retrospective, evidence provenance (9 rules)
  skills/                         86 skills (15 framework-authored + 71 gsd-* distribution)
  skill-routing.md                central registry: condition -> skill -> agent
  skill-integration-matrix.md     binding contract: role -> skill -> artifact -> gate
  tools/context-builder.ts        pointer resolver, capped excerpts
  plugin/telemetry.ts             v2 collector, one record per session
  commands/ hooks/ scripts/       OpenCode project configuration (skills-as-commands, hooks)
framework/
  gates/                          EXIT_CODES.md (AUTHORITATIVE contract) + 19 executable gates:
                                  g1_contract, g2_impact, g3_architecture, g4_executable,
                                  g5_frontend_stack, g6_browser, g7_retro, g8_blockers,
                                  g9_scope, g10_permission, g_tool_readiness (G-T0),
                                  g_tool_utilization (G-T1), g11_evidence, g12_provider,
                                  g13_worker, g14_integrity, g15_eval_tripwires,
                                  g_entry (G-ENTRY), g_exec (G-EXEC),
                                  + _lib.sh shared library
  adapters/                       gsd_state.py (GSD state + task supervision), host.py,
                                  hosts/opencode.py + hosts/dsh.py, code_intel.py,
                                  failure_injection.py (G-EXEC matrix), opencode_detect.py (deprecated)
  security/                       enforcement_plane.yaml (canonical), sync + check scripts
  claims/ledger.py                claim ledger (append/analyse/integrity E1-E8)
  retro/                          escape_path.py, containment_map.yaml
  telemetry/                      report.py, browser/mcp output dir
  verifier/profiles.yaml          profiles and impact-to-gate mapping
  tasks/task_types.yaml           task types, budgets, checkpoint vocabulary, recovery routes
  retry_policy.yaml               bounded retries, named escalation
  providers/healthcheck.py        provider health pre-flight (G12)
  architecture_rules.yaml         declared boundaries for G3
  execution_context.yaml          canonical runtime declarations
  models/profiles.sh              model profile switching (baseline | tiered | cheap | reset)
  audit_check.py                  adopt-before-extend audit completeness (exit 3 = undecided)
  ADOPT_AUDIT.md                  required install step
  bootstrap.sh / validate.py      install and validation suite
.lifecycle/                       feature-development lifecycle integration (G0/G0.5/G3.5/G7/G8,
                                  human gates H1-H3; config.yml, INTEGRATION.md)
.planning/                        GSD state root (phases, plans, decisions, contracts,
                                  telemetry, tasks, blockers, retro triggers, claims)
```

Model tuning and reporting live in `framework/`: `models/profiles.sh` switches per-agent
models by profile (`baseline | tiered | cheap | reset`), and `telemetry/report.py` aggregates
session records into cost, rework, and bottleneck reports.

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

## Gates are objective proof

Every gate is an executable script returning a real exit code: 0 pass / 1 fail / 2 BLOCKED
(could not evaluate — never a pass) / 3 UNVERIFIABLE (could not produce evidence — never a
pass) / 4 NOT_APPLICABLE (skip — never a pass). `framework/gates/EXIT_CODES.md` is the
authoritative contract; if any document disagrees with it, the document is wrong.

G-ENTRY and G12 run **before** every task dispatch (approved plan + healthy provider). G9
judges scope after the fact. G6 (browser) emits only 0/1/3. G7 blocks completion on open
retrospectives, G8 on open blockers, G13 on unhealthy workers, G14 on borrowed or stale
evidence.

## The enforcement plane is agent-immutable

`framework/**`, `.opencode/**`, `opencode.json`, and `AGENTS.md` are the enforcement plane —
no agent may edit them (permission denies in `opencode.json`, verified by
`framework/security/check_enforcement_plane.py`, which must exit 0). Canonical source:
`framework/security/enforcement_plane.yaml`. Agents never change the rules that check them.

## What v1 deliberately does not do

Contracts cover HTTP APIs only. Event, database, and service-interface contracts are
documentation-only and no gate enforces them. The GSD adapter supports the installed distribution
only; a second distribution is a conformance target proven by `gsd_state.py selftest`. There is no
project memory system, no orchestration layer, no graph store, and no second context
manager — GSD, Git, and the provider already own those. Delegated-task supervision
(`task-register`/`task-event`/`task-status`) tracks worker liveness only; it is not a
project task tracker, which GSD phases and plans own.

## Rollout

One vertical slice, one repository. The seven core agents (team-lead, researcher, architect,
planner, implementer, reviewer, verifier), contracts on your single real frontend/backend seam,
G1 and G4 wired. Twenty real tasks. Read rework rate and defect-catch location from
`<state_root>/telemetry/records.jsonl`.

Add a capability only when a named defect class escaped and no existing agent, skill, or gate
could have caught it.