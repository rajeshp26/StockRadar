# Retrospective intelligence

Answers one question after a defect escapes: **what gap in the framework let it through?**

The defect is already fixed by the time this runs. Its root cause is in the code. The root
cause of the *escape* is in the framework, and that is a separate finding with a separate fix.

## Why this is arithmetic, not an opinion

The weakness of every retrospective process is that its output degrades into "be more careful."
That is unfalsifiable, so it cannot be verified, so nothing changes.

Three constraints prevent it here:

1. **The escape path is computed.** Given where a defect was injected and where it was caught,
   the checkpoints it passed through are determined by position in the pipeline. An agent cannot
   argue the list shorter or pad it longer.
2. **Recommendations come from a closed list.** `containment_map.yaml` enumerates every fix
   target, each one a file plus a check that proves the change landed. Prose is not an option.
3. **Recurrence is detected structurally.** The ledger signature is built from injection phase,
   defect class, primary gap, and escaped checkpoints — never from the task id or the written
   description. A rephrased finding for the same structural gap still collides.

## Routing gap versus containment miss

The single most useful distinction in the subsystem.

| | Meaning | Fix |
| --- | --- | --- |
| **routing gap** | the checkpoint catches this class but never ran | the routing |
| **containment miss** | the checkpoint ran and missed it | the check |

Routing gaps take precedence, because activating an existing gate is cheaper and more reliable
than making an active gate smarter — and it usually closes a class rather than an instance.

Worked example. A misaligned button reaches production. G6 exists and would have caught it, but
the requirement carried no `visible_behaviour` shape, so `shape_to_gates` never appended G6. The
naive finding is "write better Playwright assertions." The computed finding is a routing gap
whose fix is the requirement shape. Different fix, different cost, different outcome.

## Usage

```bash
# 1. Compute the escape path using the task's ORIGINAL classification
python3 framework/retro/escape_path.py \
  --injected implementation --caught production \
  --defect-class visible_behaviour_defect --scope component --frontend
# exit 0 actionable gap | 1 bad input | 4 no gap (caught at first capable checkpoint)

# 2. Record the finding and the fix
python3 framework/retro/ledger.py append --json '{...}'

# 3. Prove the retrospective is complete
bash framework/gates/g7_retro.sh
# exit 0 complete | 1 incomplete or recurrence | 2 blocked | 4 no trigger

# 4. Trend analysis
python3 framework/retro/ledger.py analyse
```

## What is deliberately not here

No new agent. Retrospective analysis is an Implementer skill, the Verifier runs G7, and the Team
Lead opens triggers. Adding a "Retrospective Agent" would violate the rule that an agent must
not exist merely because a concern exists.

No separate memory system. The ledger lives in GSD state under `retro/`.

No retrospective on every task. A defect caught at the first checkpoint capable of catching it
is the framework working. Recording that produces paperwork and trains everyone to ignore the
ledger, which is how this kind of subsystem usually dies.

## Runtime ownership of the background-task contract

The `task` and `background_output` tools are provided by the OpenCode runtime
(oh-my-opencode), not by this repository. The runtime still allows the polling
anti-pattern: calling `background_output` on a `bg_xxx` task before the
`<system-reminder>` notification, or using `block=true` as a proxy for waiting.

This framework cannot remove those paths from the tool. What it can do, and does:

* `.opencode/rules/background-tasks.md` declares the contract: fire -> END RESPONSE
  -> wait for system-reminder -> collect.
* `.opencode/plugin/telemetry.ts` measures `bg_poll_total` per session, classifying
  every background_output call as poll or collect.
* `framework/validate.py` section 15c checks the rule, the telemetry field, and the
  agent instruction surface all exist.

Upstream improvements (removing `block=false`, adding a task-level timeout) belong
in oh-my-opencode. Until they land, measurement + declaration is the enforceable
surface, and a rising `bg_poll_total` in the telemetry report is the failure signal.

## Honest limits

`injected_at` and `defect_class` are human or agent judgements. Everything downstream is
computed, but a wrong injection phase yields a wrong escape path — garbage in, arithmetic out.
Review those two fields.

`none_human_judgement` is a valid outcome. A rising rate of it is a signal worth watching: it
may mean the framework has reached the limit of what static checks can express, or it may mean
retrospectives are being waved through. The ledger reports the rate; a human interprets it.
