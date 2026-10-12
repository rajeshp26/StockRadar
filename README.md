# OpenCode Agentic Engineering Framework v1.0 — scaffold

Runtime OpenCode. Workflow and state GSD. Forty agents (7 core + 33 GSD distribution). Skills
for specialisation. Code intelligence as an accelerator. Contracts as integration boundaries.
Gates as objective proof. An agent-immutable enforcement plane as the security boundary.

Full walkthrough of every component and flow: **`docs/AGENTIC_ARCHITECTURE.md`** (read that
first if you want the whole picture).

## Install

The framework is a package. Install it, then bind an application repository to it with
`framework init`, which materialises the framework's OpenCode surface into the app's
`.opencode/` with every include path rewritten to the app root — so nothing resolves against
the machine the package was built on.

```bash
pip install "agentic-lifecycle @ git+https://github.com/<org>/agentic-lifecycle@v0.1.0"
cd /path/to/your/app
framework init            # bind this repo (alias: framework bootstrap)
framework validate --profile app
opencode --agent team-lead
```

`framework init` writes `framework.config.json`, scaffolds `.framework/state/{decisions,contracts}`,
materialises the OpenCode surface (`gsd-core`, `skills`, `commands`, `agents`, `rules`) under
`.opencode/`, installs `.opencode/plugins/bootstrap.ts`, and migrates any legacy
`.planning/{decisions,contracts}`. The materialised surface is generated and its `@`-includes are
rewritten to the app root; the plugin resolves this app-local surface first (falling back to the
installed package) at startup, never a hard-coded path, so it is safe to commit. Restart OpenCode
after init. The command is idempotent — re-run it after an upgrade to refresh the surface.

`framework standalone` proves the installed wheel binds and validates a bare consumer app.

### Prerequisites

- **python3 on PATH** — the CLI and the gates resolve their interpreter at runtime, and the OpenCode
  plugin shells out to locate the installed package (it tries `python` then `python3`, so either
  works on Windows). Gate invocations are the documented contract — see `framework/gates/EXIT_CODES.md`.
- **bash** — the gates (`framework/gates/*.sh`) are bash scripts and refuse to run under `sh`
  or PowerShell (exit 2, BLOCKED). On Windows use Git Bash or WSL.
- **LF line endings** — the repo is stored LF (`* text=auto eol=lf` in `.gitattributes`); a
  machine-global `core.autocrlf=true` rewrites checked-out files to CRLF even though nothing is
  committed CRLF. If a working tree shows CRLF after clone, run `git add --renormalize .` once.

## Layout

```
opencode.json                     runtime config: model, instructions, permissions, agents,
                                  MCP servers, references, skills paths, plugin, compaction
AGENTS.md                         stable global rules only (rule zero, do-not-invoke, evidence)
                                  + the enforcement-plane fence
framework/
  opencode/                       THE OpenCode surface, authored here. `framework init`
                                  materialises it into an app's `.opencode/`, rewriting every
                                  include to the app root.
    agents/                       40 agent definitions (7 core + 33 gsd-*)
    rules/                        evidence applicability, DoD vs verification, handoff shape,
                                  blockers, bash hygiene, background tasks, delegation protocol,
                                  retrospective, evidence provenance (9 rules)
    skills/                       86 skills (15 framework-authored + 71 gsd-* distribution)
    skill-routing.md              central registry: condition -> skill -> agent
    skill-integration-matrix.md   binding contract: role -> skill -> artifact -> gate
    tools/context-builder.ts      pointer resolver, capped excerpts
    plugin/telemetry.ts           v2 collector, one record per session
    plugin/bootstrap.ts           startup surface resolver (materialised to the app)
    commands/ hooks/ scripts/     OpenCode project configuration (skills-as-commands, hooks)
  gates/                          EXIT_CODES.md (AUTHORITATIVE contract) + 20 executable gates:
                                  g1_contract, g2_impact, g3_architecture, g4_executable,
                                  g5_frontend_stack, g6_browser, g7_retro, g8_blockers,
                                  g9_scope, g10_permission, g_tool_readiness (G-T0),
                                  g_tool_utilization (G-T1), g11_evidence, g12_provider,
                                  g13_worker, g14_integrity, g15_eval_tripwires,
                                  g16_state_health, g_entry (G-ENTRY), g_exec (G-EXEC),
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
  cli.py / init.py / __main__.py  the `framework` CLI: bind an app, validate a wheel
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