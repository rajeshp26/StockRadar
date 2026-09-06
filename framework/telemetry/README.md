# Telemetry and model tuning

## Turn it on

Nothing to enable. The plugin is registered in `opencode.json` and writes a lifecycle
series per session — `started` at session creation, `heartbeat` every 60s and on
context compaction, `final` at idle/deleted — to `<state-root>/telemetry/records.jsonl`.
The report collapses each series to one record (last wins).

Optional: `export TASK_ID=03-02` before a run so records carry the task they belong to.

## Read it

```bash
python3 framework/telemetry/report.py            # human report
python3 framework/telemetry/report.py --verbose  # + per-agent models, gate breakdowns
python3 framework/telemetry/report.py --json     # machine-readable aggregate
python3 framework/validate.py --models   # resolve every slot, print source attribution, write the snapshot
```

Exit codes: `0` report produced, `1` report produced but session(s) never reached a
final record (died before SESSION_FINALIZED, named in the output), `3` nothing has run
yet, `2` records exist but none parse. Exit 3 is not a failure.

## What the sections answer

| Section | Question |
|---|---|
| COST | Where do tokens go? Input-heavy means retrieval; output-heavy means generation. |
| TOKENS BY AGENT | Which agent to try on a cheaper model first. |
| BOTTLENECKS | Which tool dominates wall-clock. Usually `bash`, i.e. gates. |
| GATES | Which gate fails or is slow. Unverifiable is listed apart from pass. |
| CONTEXT | Materialised chars, cap truncations, expansions, tier-4 fallbacks. |
| REWORK RATE | The primary decision metric. |
| DURATION | Median and worst-case session length. |
| TELEMETRY HEALTH | Unfinalized sessions, poll totals, stale background tasks, worker supervision counters — the collector's own liveness. |
| MODEL RESOLUTION | Which layer resolved each agent's model (override/profile/default) and whether any failed closed. |

## Deliberately not computed

`Context Efficiency = relevant / total` needs a human label for "relevant", applied after
the outcome is known. Every metric here derives from recorded facts only.

## Per-agent models

`opencode.json` now bakes concrete model IDs into every agent. `OC_MODEL_*` env overrides still win when exported.
WARNING: an unset override is NOT a no-op — `{env:X}` resolving to `""` sends an EMPTY model id to the runner, every subagent fails to resolve its model and stalls until the inactivity timeout.

```bash
source framework/models/profiles.sh baseline   # control: one model everywhere
source framework/models/profiles.sh tiered     # cost-tiered by reasoning demand
source framework/models/profiles.sh cheap      # aggressive; expect rework to rise
source framework/models/profiles.sh reset      # back to OpenCode's default
```

Point them at models your provider exposes (`opencode models`), or override the tiers:

```bash
export OC_BIG=opencode/big-pickle
export OC_MID=opencode/big-pickle
export OC_SML=opencode/big-pickle
```

### Why these tiers

| Agent | Tier | Reason |
|---|---|---|
| implementer | high | Writes all code and does root-cause debugging. |
| architect | high | A wrong boundary is expensive to unwind. |
| reviewer | high | A missed finding costs more than the tokens saved. |
| researcher | mid | Findings are re-checked downstream. |
| team-lead | low | Table-driven routing and classification. |
| planner | low | Decomposes an already-approved design. |
| verifier | low | Runs gates and transcribes exit codes. |

Verifier is deliberately low despite being late in the pipeline: it produces evidence by
running commands, and the gates do the judging.

## Model resolution diagnostics

`python3 framework/validate.py --models` resolves every agent slot from the live
environment through `framework/models/resolve.py`. Precedence per slot is explicit
override (`OC_MODEL_*` env) > sourced profile > framework default > fail closed. It
prints the per-agent source attribution, writes `framework/telemetry/models-resolved.json`,
and exits 1 if any slot failed to resolve — an unresolved model stalls the subagent at
spawn, so failures are loud, never silent.

`report.py` reads that snapshot and shows the same attribution in the MODEL RESOLUTION
section. A report exits 1 while the snapshot records failures. No snapshot yet
(preflight never ran) is reported as absent, never as a pass.

## Measurement protocol

1. `source framework/models/profiles.sh baseline`, run ~20 tasks, save the report.
2. `source framework/models/profiles.sh tiered`, run ~20 comparable tasks.
3. Compare tokens per session **and** rework rate together.

A token saving with a higher rework rate is a loss. Under ~20 sessions the report says so
rather than implying the numbers are decisive.

Revert with `reset` — no config edit required.

## Known limits

- Token fields vary across OpenCode versions. Extraction tries several shapes and falls
  back to 0. If COST reports zero on a real run, the shape changed; fix the extraction
  rather than trusting the zero.
- Gate results are parsed from the stable `[gate] PASS|FAIL|...` stdout line, because exit
  codes are not exposed on `tool.execute.after` in all versions.
- Agent attribution follows the `task` tool. Work the Team Lead does itself attributes
  to `team-lead`.
