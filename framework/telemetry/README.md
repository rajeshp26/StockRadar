# Telemetry and model tuning

## Turn it on

Nothing to enable. The plugin is registered in `opencode.json` and writes one record per
session to `<state-root>/telemetry/records.jsonl`.

Optional: `export TASK_ID=03-02` before a run so records carry the task they belong to.

## Read it

```bash
python3 framework/telemetry/report.py            # human report
python3 framework/telemetry/report.py --verbose  # + per-agent models, gate breakdowns
python3 framework/telemetry/report.py --json     # machine-readable aggregate
```

Exit codes: `0` report produced, `3` nothing has run yet, `2` records exist but none parse.
Exit 3 is not a failure.

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

## Deliberately not computed

`Context Efficiency = relevant / total` needs a human label for "relevant", applied after
the outcome is known. Every metric here derives from recorded facts only.

## Per-agent models

`opencode.json` sets each agent's model to `{env:OC_MODEL_*}`. Unset resolves to `""`,
which means inherit — so an unset variable is a safe no-op.

```bash
source framework/models/profiles.sh baseline   # control: one model everywhere
source framework/models/profiles.sh tiered     # cost-tiered by reasoning demand
source framework/models/profiles.sh cheap      # aggressive; expect rework to rise
source framework/models/profiles.sh reset      # back to OpenCode's default
```

Point them at models your provider exposes (`opencode models`), or override the tiers:

```bash
export OC_BIG=anthropic/claude-sonnet-4-5
export OC_MID=anthropic/claude-sonnet-4-5
export OC_SML=anthropic/claude-haiku-4-5
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
