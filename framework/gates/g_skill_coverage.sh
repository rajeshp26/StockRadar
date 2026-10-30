#!/usr/bin/env bash
# G-SKILL-COVERAGE -- does the plan REQUIRE the skills the routing table mandates?
#
# WHY THIS GATE EXISTS
# ====================
# `framework/validate.py` proves every skill RESOLVES (name, frontmatter, root). It cannot
# prove a task SELECTS one. Those are different claims, and only resolution was checked:
# `apple-ui` resolves, so every check was green, while a plan touching `web/src/**` named
# no design skill and the implementer was never told to load the design system. The routing
# table had a mandatory row; no machine read it. A skill that is never selected is a skill
# lying around.
#
# The plan is the only place selection can be forced BEFORE work starts. This gate is the
# pre-flight half; the post-hoc half is T-G1/T-G2 in g_tool_utilization.sh.
#
# WHAT IT CHECKS (see framework/tools/skill_coverage.py for the rule bodies)
#   SC01 every required_skills entry resolves on a configured skills path (phantom = error)
#   SC02 a plan touching UI paths requires apple-ui + frontend-react (skill-routing.md:24)
#   SC03 a plan creating a NEW UI surface requires designmotion-design     (skill-routing.md:22)
#   SC04 code plan with no required_skills at all                           (warning)
#   SC05 a required skill that no routing row names                         (warning)
#   CM00 Capability Matrix schema unreadable from team-lead.md              (error)
#   CM01 a matrix omits a dimension the Capability Matrix declares          (error)
#   CM02 a matrix verdict is not yes/no, or scope is not task/phase         (error)
#   CM03 a matrix names a dimension that is not a Capability Matrix row     (warning)
#   CM04 matrix says yes but no required_skills entry names that skill      (error)
#   CM05 no CAPABILITY-MATRIX.yaml next to the plan                         (warning)
#
# Modelled on the DID-016 plan lint: same mode file, same exit contract, so a plan cannot
# satisfy one half of the dispatch contract and fail the other silently.
#
# Exit: 0 coverage complete -- dispatch allowed
#       1 coverage errors -- NO TASK DISPATCH (under lint_mode=enforce)
#       2 BLOCKED (python3 absent / plan unreadable / invalid mode -- never a pass)
#       4 NOT_APPLICABLE (lint_mode=off)
GATE_NAME="g_skill_coverage"
. "$(dirname "$0")/_lib.sh"

NOT_APPLICABLE=4
BLOCKED=2

ENTRY_PLAN="${ENTRY_PLAN:-}"
ENTRY_TASK="${ENTRY_TASK:-}"

have python3 || { log "BLOCKED  python3 unavailable -- skill coverage unreadable"; persist blocked "no python3"; exit $BLOCKED; }

# Mode is shared with the plan lint on purpose: one switch disables both halves of the
# pre-dispatch contract, so "temporarily advisory" cannot mean two different things.
# The mode lives in framework/** (agent-immutable), never in an environment variable.
mode="enforce"
if [ -f framework/plan/lint_mode ]; then
  mode="$(grep -v '^[[:space:]]*#' framework/plan/lint_mode | tr -d '\r[:space:]' | head -n1)"
fi
case "$mode" in
  off) log "NOT_APPLICABLE  skill coverage disabled by framework/plan/lint_mode=off"
       persist not_applicable "lint_mode=off"
       not_applicable "skill coverage disabled by framework/plan/lint_mode=off" \
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
  # No plan context is NOT "nothing to check": this gate is only meaningful with a plan, and
  # g_entry refuses dispatch without one. Reporting a non-judgement here would let a caller
  # that forgot to pass the plan read "not applicable" as clean.
  persist blocked "no plan context (ENTRY_PLAN/ENTRY_TASK unset)"
  log "BLOCKED  no plan context (ENTRY_PLAN/ENTRY_TASK unset)"
  exit $BLOCKED
fi

if [ ! -f "$ENTRY_PLAN" ]; then
  persist blocked "plan not readable: $ENTRY_PLAN"
  log "BLOCKED  plan not readable: $ENTRY_PLAN"
  exit $BLOCKED
fi

if [ ! -f framework/tools/skill_coverage.py ]; then
  if [ "$mode" = "enforce" ]; then
    persist blocked "framework/tools/skill_coverage.py missing under enforce"
    log "BLOCKED  framework/tools/skill_coverage.py missing while lint_mode=enforce"
    exit $BLOCKED
  fi
  log "NOT_APPLICABLE  skill_coverage.py missing while lint_mode=warn"
  persist not_applicable "skill_coverage.py missing under warn"
  not_applicable "skill_coverage.py missing under lint_mode=warn" \
    '{"script":"framework/tools/skill_coverage.py","lint_mode":"warn"}'
fi

out="$(python3 framework/tools/skill_coverage.py "$ENTRY_PLAN" --root . 2>&1)"; rc=$?
out="$(printf '%s' "$out" | tr -d '\r')"

case "$rc" in
  0) if printf '%s\n' "$out" | grep -q 'WARN'; then
       log "WARN  skill coverage advisories (non-blocking):"$'\n'"$out"
     else
       log "PASS  skill coverage: every routed skill this plan implies is required"
     fi
     persist pass "skill coverage clean"
     pass "skill coverage complete for $ENTRY_PLAN" ;;
  1) if [ "$mode" = "enforce" ]; then
       persist fail "skill coverage errors block dispatch"
       fail "skill coverage errors block dispatch; name the missing skill in required_skills or change the file scope:"$'\n'"$out"
     else
       log "WARN  skill coverage errors (advisory under lint_mode=warn):"$'\n'"$out"
       persist warn "skill coverage advisory (lint_mode=warn)"
     fi ;;
  4) log "NOT_APPLICABLE  $out"
     persist not_applicable "skills system not configured in this root"
     not_applicable "skills system not configured in this root" \
       '{"opencode.json":"absent"}' ;;
  *) if [ "$mode" = "enforce" ]; then
       persist blocked "skill coverage unreadable (exit $rc)"
       log "BLOCKED  skill coverage unreadable (exit $rc):"$'\n'"$out"
       exit $BLOCKED
     else
       log "WARN  skill coverage unavailable (exit $rc); advisory only"
     fi ;;
esac
