#!/usr/bin/env bash
# G-ENTRY -- pre-dispatch entry contract gate.
#
# Refuses task delegation until the plan satisfies the entry contract: an approved
# plan that declares files_or_components and acceptance_criteria, with no unresolved
# open questions. A task with no plan context and no trivial exemption is a routing
# defect, not a valid dispatch.
#
# Team Lead runs this BEFORE every task(...) dispatch (team-lead.md, "Entry contract
# before dispatch"). G9 remains the post-hoc scope check; this gate is the pre-flight
# half of the same contract.
#
# Exit: 0 entry contract complete -- dispatch allowed
#       1 named missing prerequisite -- NO TASK DISPATCH
#       2 BLOCKED (python3 absent / state unreadable -- never a pass)
#       4 NOT_APPLICABLE (ENTRY_EXEMPT=TRIVIAL -- trivial ask, no plan required)
GATE_NAME="g_entry"
. "$(dirname "$0")/_lib.sh"

NOT_APPLICABLE=4
BLOCKED=2

ENTRY_PLAN="${ENTRY_PLAN:-}"
ENTRY_TASK="${ENTRY_TASK:-}"
ENTRY_EXEMPT="${ENTRY_EXEMPT:-}"

# Trivial-request exemption: team-lead.md's trivial-request gate classifies the ask as
# single-step and unambiguous, so no plan is required. The exemption is an explicit
# decision (ENTRY_EXEMPT=TRIVIAL), never an implicit skip.
if [ -n "$ENTRY_EXEMPT" ]; then
  log "NOT_APPLICABLE  entry contract exempted: $ENTRY_EXEMPT"
  exit $NOT_APPLICABLE
fi

have python3 || { log "BLOCKED  python3 unavailable -- entry contract unreadable"; persist blocked "no python3"; exit $BLOCKED; }

if [ -z "$ENTRY_PLAN" ] && [ -n "$ENTRY_TASK" ]; then
  # plan-path emits host-native separators and CRLF line endings: under the
  # Windows-python shim that is backslash paths plus a trailing \r that bash
  # [ -f ] cannot stat. Normalize both -- same class as the CRLF strip below
  # (G8 pattern).
  ENTRY_PLAN="$(python3 framework/adapters/gsd_state.py plan-path --task "$ENTRY_TASK" 2>/dev/null | tr -d '\r' || true)"
  ENTRY_PLAN="${ENTRY_PLAN//\\//}"
fi

if [ ! -f "$ENTRY_PLAN" ]; then
  persist fail "no plan context (ENTRY_PLAN/ENTRY_TASK unset or plan not found); NO TASK DISPATCH"
  fail "no plan context (ENTRY_PLAN/ENTRY_TASK unset or plan not found); NO TASK DISPATCH"
fi

# CR-strip the plan -- a Windows CRLF checkout must not change the verdict (G8 pattern).
plan="$(cat "$ENTRY_PLAN" | tr -d '\r')"

# 1. Approved: an explicit, TOP-LEVEL approval token only (status: approved |
# approved: true | accepted: true). Anchored to column 0 -- a nested block
# (e.g. under `review:`) must not spoof approval (EXT-CRITIQUE-03).
approved="$(printf '%s' "$plan" | grep -iE '^status:[[:space:]]+approved|^(approved|accepted):[[:space:]]*true' | head -n1)"
if [ -z "$approved" ]; then
  persist fail "plan not approved (no status: approved / approved: true / accepted: true)"
  fail "plan not approved (no status: approved / approved: true / accepted: true)"
fi

# 2. Declared scope: YAML block list ("- item") and/or inline "[a, b]" form (G9 awk reuse).
declared_block=$(printf '%s' "$plan" | awk '
  /^files_or_components:/ { inblock=1; next }
  inblock && /^[[:space:]]*-[[:space:]]*/ {
    item=$0; sub(/^[[:space:]]*-[[:space:]]*/, "", item); gsub(/"/, "", item)
    if (item != "") print item
    next
  }
  inblock && NF { exit }
')
declared_inline=$(printf '%s' "$plan" | sed -n 's/^files_or_components:[[:space:]]*\[\([^]]*\)\].*/\1/p' \
  | tr ',' '\n' | tr -d '"')
declared="$(printf '%s\n%s\n' "$declared_block" "$declared_inline" \
  | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' | sed '/^$/d')"

if [ -z "$declared" ]; then
  persist fail "plan declares no files_or_components; NO TASK DISPATCH"
  fail "plan declares no files_or_components; NO TASK DISPATCH"
fi

# 3. Acceptance criteria present (block or inline form).
ac_block=$(printf '%s' "$plan" | awk '
  /^acceptance_criteria:/ { inblock=1; next }
  inblock && /^[[:space:]]*-[[:space:]]*/ {
    item=$0; sub(/^[[:space:]]*-[[:space:]]*/, "", item); gsub(/"/, "", item)
    if (item != "") print item
    next
  }
  inblock && NF { exit }
')
ac_inline=$(printf '%s' "$plan" | sed -n 's/^acceptance_criteria:[[:space:]]*\[\([^]]*\)\].*/\1/p' \
  | tr ',' '\n' | tr -d '"')
acs="$(printf '%s\n%s\n' "$ac_block" "$ac_inline" \
  | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' | sed '/^$/d')"

if [ -z "$acs" ]; then
  persist fail "plan has no acceptance_criteria; NO TASK DISPATCH"
  fail "plan has no acceptance_criteria; NO TASK DISPATCH"
fi

# 4. No unresolved open_questions (block items or inline list).
oq_block=$(printf '%s' "$plan" | awk '
  /^open_questions:/ { inblock=1; next }
  inblock && /^[[:space:]]*-[[:space:]]*/ {
    item=$0; sub(/^[[:space:]]*-[[:space:]]*/, "", item); gsub(/"/, "", item)
    if (item != "") print item
    next
  }
  inblock && NF { exit }
')
oq_inline=$(printf '%s' "$plan" | sed -n 's/^open_questions:[[:space:]]*\[\([^]]*\)\].*/\1/p' \
  | tr ',' '\n' | tr -d '"')
open_qs="$(printf '%s\n%s\n' "$oq_block" "$oq_inline" \
  | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' | sed '/^$/d')"

if [ -n "$open_qs" ]; then
  persist fail "unresolved open questions block dispatch"
  fail "unresolved open questions block dispatch:"$'\n'"$open_qs"
fi

# 4b. Plan-quality lint (DID-016). Structure and cited evidence only: vague criteria, missing
# evidence class, no goal-level check, unresolved discovery, new code without a reuse record,
# unresolvable dependencies, edits after approval. The mode comes from framework/plan/lint_mode
# (enforce | warn | off; absent file = enforce). It is deliberately NOT an environment variable:
# an agent can set an env var, but framework/** is immutable to agents. An unreadable or invalid
# mode, or a missing lint script under enforce, is BLOCKED -- never a silent skip.
lint_mode="enforce"
if [ -f framework/plan/lint_mode ]; then
  lint_mode="$(grep -v '^[[:space:]]*#' framework/plan/lint_mode | tr -d '\r[:space:]' | head -n1)"
fi
case "$lint_mode" in
  off|warn|enforce) ;;
  *) persist blocked "framework/plan/lint_mode must be enforce|warn|off, got '$lint_mode'"
     log "BLOCKED  framework/plan/lint_mode must be enforce|warn|off, got '$lint_mode'"
     exit $BLOCKED ;;
esac
if [ "$lint_mode" != "off" ]; then
  if [ ! -f framework/plan/plan_lint.py ]; then
    if [ "$lint_mode" = "enforce" ]; then
      persist blocked "plan lint script missing under enforce"
      log "BLOCKED  framework/plan/plan_lint.py missing while lint_mode=enforce"
      exit $BLOCKED
    fi
  else
    lint_out="$(python3 framework/plan/plan_lint.py "$ENTRY_PLAN" 2>&1)"; lint_rc=$?
    lint_out="$(printf '%s' "$lint_out" | tr -d '\r')"
    case "$lint_rc" in
      0) printf '%s\n' "$lint_out" | grep -q 'WARN' \
           && log "WARN  plan lint advisories (non-blocking):"$'\n'"$lint_out" ;;
      1) if [ "$lint_mode" = "enforce" ]; then
           persist fail "plan lint errors block dispatch"
           fail "plan lint errors block dispatch; load skill task-breakdown, fix the plan, re-run:"$'\n'"$lint_out"
         else
           log "WARN  plan lint found errors (advisory under lint_mode=warn):"$'\n'"$lint_out"
         fi ;;
      *) if [ "$lint_mode" = "enforce" ]; then
           persist blocked "plan lint unreadable (exit $lint_rc)"
           log "BLOCKED  plan lint unreadable (exit $lint_rc)"
           exit $BLOCKED
         else
           log "WARN  plan lint unavailable (exit $lint_rc); advisory only"
         fi ;;
    esac
  fi
fi

# 4c. Skill coverage: does the plan REQUIRE the skills the routing table mandates?
# validate.py proves a skill RESOLVES; nothing proved a task SELECTS one, so a plan touching
# web/src/** could omit apple-ui/frontend-react and still dispatch -- the mandatory rows in
# skill-routing.md were unread by any machine. Composed from the standalone gate so the
# verdict is independently runnable and cannot drift from the dispatch decision.
# ENTRY_PLAN is passed through verbatim: this shell already stat'ed it above, so the child
# cannot hit a path-resolution difference of its own.
if [ "$lint_mode" != "off" ]; then
  ENTRY_TASK="" ENTRY_PLAN="$ENTRY_PLAN" bash framework/gates/g_skill_coverage.sh
  skill_rc=$?
  case "$skill_rc" in
    0) ;;
    1) if [ "$lint_mode" = "enforce" ]; then
         persist fail "skill coverage errors block dispatch"
         fail "skill coverage errors block dispatch; name the missing skill, complete the capability matrix, or change the file scope"
       fi ;;
    4) log "NOT_APPLICABLE  skill coverage: skills system not configured in this root" ;;
    *) if [ "$lint_mode" = "enforce" ]; then
         persist blocked "skill coverage unreadable (exit $skill_rc)"
         log "BLOCKED  skill coverage unreadable (exit $skill_rc)"
         exit $BLOCKED
       fi ;;
  esac
fi

# 5. ASK coverage (DID-012 PR-D1 / invariant I1): an executable task must be bound to a
# durable ASK record before dispatch. A terminal task is not executable, so the adapter
# reports NOT_APPLICABLE (4) and the gate continues. Unbound is a hard refusal; an
# unreadable adapter is BLOCKED -- never a pass.
if [ -n "$ENTRY_TASK" ]; then
  vt_out="$(python3 framework/adapters/intake.py verify-task --id "$ENTRY_TASK" 2>/dev/null)"
  rc=$?
  case $rc in
    0) # DID-017: the plan must name the ask it serves, so ASK completion can be bound to the
       # plan's system-test evidence. Governed by the same framework/plan/lint_mode.
       if [ "$lint_mode" != "off" ]; then
         bound_ask="$(printf '%s' "$vt_out" | tr -d '\r' | sed -n 's/.*bound to \([A-Za-z0-9_-]*\).*/\1/p' | head -n1)"
         plan_ask="$(tr -d '\r' < "$ENTRY_PLAN" | sed -n 's/^ask_id:[[:space:]]*\([A-Za-z0-9_-]*\).*/\1/p' | head -n1)"
         if [ -n "$bound_ask" ] && [ "$plan_ask" != "$bound_ask" ]; then
           if [ "$lint_mode" = "enforce" ]; then
             persist fail "plan does not declare ask_id: $bound_ask"
             fail "plan must declare 'ask_id: $bound_ask' (the ask task $ENTRY_TASK is bound to); found '${plan_ask:-none}'"
           else
             log "WARN  plan does not declare ask_id: $bound_ask (found '${plan_ask:-none}')"
           fi
         fi
       fi ;;
    4) log "NOT_APPLICABLE  ask coverage: task $ENTRY_TASK is terminal (not executable)" ;;
    1) persist fail "ask coverage: executable task $ENTRY_TASK has no durable ASK_ID (I1)"
       fail "ask coverage: executable task $ENTRY_TASK has no durable ASK_ID; NO TASK DISPATCH" ;;
    *) persist blocked "ask coverage unreadable (intake adapter exit $rc)"
       log "BLOCKED  ask coverage unreadable (intake adapter exit $rc)"
       exit $BLOCKED ;;
  esac
fi

persist pass "entry contract complete"
pass "entry contract complete; dispatch allowed"