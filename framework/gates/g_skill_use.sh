#!/usr/bin/env bash
# G-SKILL-USE -- did the agent actually LOAD the skill the plan REQUIRED it to?
#
# WHY THIS GATE EXISTS
# ====================
# G-ENTRY and G-SKILL-COVERAGE force a plan to NAME its required skills before dispatch. They
# cannot prove the agent READ one after dispatch, and "required_skills lists apple-ui" is not
# the claim "the implementer loaded apple-ui". This is the only gate that diffs INTENT (the
# plan) against OBSERVED BEHAVIOUR (the session's recorded skill tool calls).
#
# EVIDENCE SOURCE -- the already-installed sensor, not a new one
# =============================================================
# `framework/opencode/plugin/telemetry.ts` captures the `skill` tool call into each session
# record's `skills_loaded` and flushes it on every heartbeat/final through write-telemetry.
# This gate reads `.planning/telemetry/records.jsonl` through `framework/tools/skill_use.py`.
# A separate recorder log would be a second source of truth for one fact (the duplication the
# framework forbids) and would sit in agent-writable space, where the thing being measured can
# edit the measurement. The plugin is a plane file: the agent cannot edit what it emits.
#
# TRUST BOUNDARY (stated, not papered over)
# =========================================
# The record store is append-only and written by the plugin, so it says what the plugin logged.
# It is not an observation by a third party. Read a PASS as "a skill call was recorded", never
# as "the skill's instructions reached the model's context".
#
# VERDICT LADDER -- every non-pass is classified, never silent
# ============================================================
#   0 PASS              every required skill appears in the records for this task
#   1 FAIL              a required skill has no recorded invocation (incl. a plan that
#                       requires skills and has no attributed session at all)
#   2 BLOCKED           no/unreadable plan context, invalid framework/plan/lint_mode
#   3 CAPABILITY_MISSING the telemetry plugin is absent -- nothing can observe a skill call
#   4 NOT_APPLICABLE    lint_mode=off, plan requires no skills, or no telemetry records exist
#
# A sensor defect is surfaced, never absorbed: when the recorder writes `unknown` instead of a
# skill name (the argument-key defect telemetry.ts:275 documents), `skill_use.py` emits SU01.
# An `unknown` entry NEVER satisfies a required skill, because then a broken sensor would read
# as a clean run.
#
# Tests: bash framework/gates/test_g_skill_use.sh (14 cases, one per edge above).
GATE_NAME="g_skill_use"

case "${1:-}" in
  -h|--help) printf 'usage: ENTRY_PLAN=<plan> [ENTRY_TASK=<id>] bash framework/gates/g_skill_use.sh\n'; exit 0 ;;
esac

. "$(dirname "$0")/_lib.sh"

NOT_APPLICABLE=4
BLOCKED=2

ENTRY_PLAN="${ENTRY_PLAN:-}"
ENTRY_TASK="${ENTRY_TASK:-}"

have python3 || { log "BLOCKED  python3 unavailable -- cannot read the plan or the records"
                  persist blocked "no python3"; exit $BLOCKED; }

# Sensor presence is checked BEFORE any verdict: with no plugin there is no evidence class
# available at all, and an empty store would be indistinguishable from "no skill was invoked".
SENSOR="framework/opencode/plugin/telemetry.ts"
if [ ! -f "$SENSOR" ]; then
  persist capability_missing "telemetry plugin absent: $SENSOR"
  capability_missing "no telemetry plugin: skill invocation is unobservable in this root" \
    '{"plugin":"framework/opencode/plugin/telemetry.ts","present":false}'
fi

# Mode is shared with the plan lint and G-SKILL-COVERAGE: one switch disables every half of
# the skill contract, so "temporarily advisory" cannot mean three different things.
mode="enforce"
if [ -f framework/plan/lint_mode ]; then
  mode="$(grep -v '^[[:space:]]*#' framework/plan/lint_mode | tr -d '\r[:space:]' | head -n1)"
fi
case "$mode" in
  off) persist not_applicable "lint_mode=off"
       not_applicable "skill-use check disabled by framework/plan/lint_mode=off" \
         '{"lint_mode":"off","script":"framework/plan/lint_mode"}' ;;
  warn|enforce) ;;
  *) persist blocked "framework/plan/lint_mode must be enforce|warn|off, got '$mode'"
     log "BLOCKED  framework/plan/lint_mode must be enforce|warn|off, got '$mode'"
     exit $BLOCKED ;;
esac

if [ -z "$ENTRY_PLAN" ] && [ -n "$ENTRY_TASK" ]; then
  # plan-path emits host-native separators and CRLF: normalize both before stat (G8 pattern).
  ENTRY_PLAN="$(python3 framework/adapters/gsd_state.py plan-path --task "$ENTRY_TASK" 2>/dev/null | tr -d '\r' || true)"
  ENTRY_PLAN="${ENTRY_PLAN//\\//}"
fi

if [ -z "$ENTRY_PLAN" ]; then
  # No plan context is NOT "nothing to check": the required_skills being verified live in the
  # plan, so without it this gate has no input and must refuse rather than read clean.
  persist blocked "no plan context (ENTRY_PLAN/ENTRY_TASK unset)"
  log "BLOCKED  no plan context (ENTRY_PLAN/ENTRY_TASK unset)"
  exit $BLOCKED
fi

if [ ! -f "$ENTRY_PLAN" ]; then
  persist blocked "plan not readable: $ENTRY_PLAN"
  log "BLOCKED  plan not readable: $ENTRY_PLAN"
  exit $BLOCKED
fi

out="$(python3 framework/tools/skill_use.py "$ENTRY_PLAN" --task "$ENTRY_TASK" \
  --state-root "$STATE_ROOT" 2>&1)"; rc=$?
out="$(printf '%s' "$out" | tr -d '\r')"

case "$rc" in
  0) if printf '%s\n' "$out" | grep -q 'WARN'; then
       log "WARN  skill use advisories (non-blocking):"$'\n'"$out"
     else
       log "PASS  every skill the plan requires was recorded as invoked"
     fi
     persist pass "skill use complete"
     pass "skill use verified for $ENTRY_PLAN" ;;
  1) if [ "$mode" = "enforce" ]; then
       persist fail "required skills were not invoked"
       fail "the plan requires skills that were never invoked:"$'\n'"$out"
     fi
     # Advisory mode keeps the evidence and drops the veto. It does NOT claim a pass: the last
     # line states what was found and that the verdict was not enforced.
     log "WARN  skill use gaps (advisory under lint_mode=warn):"$'\n'"$out"
     persist warn "skill use advisory (lint_mode=warn)"
     log "PASS-WITH-WARNINGS  lint_mode=warn; not enforced"
     gate_result pass 0
     exit 0 ;;
  4) persist not_applicable "nothing to judge"
     not_applicable "no telemetry records, or the plan requires no skills" \
       '{"plan":"'"$ENTRY_PLAN"'","reason":"'"$(printf '%s' "$out" | head -n1 | sed 's/"/\\"/')"'"}' ;;
  *) persist blocked "skill use unreadable (exit $rc)"
     log "BLOCKED  skill use unreadable (exit $rc):"$'\n'"$out"
     exit $BLOCKED ;;
esac
