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

# 1. Approved: an explicit approval token (status: approved | approved: true | accepted: true).
approved="$(printf '%s' "$plan" | grep -iE '^[[:space:]]*status:[[:space:]]+approved|^[[:space:]]*(approved|accepted):[[:space:]]*true' | head -n1)"
if [ -z "$approved" ]; then
  persist fail "plan not approved (no status: approved / approved: true / accepted: true)"
  fail "plan not approved (no status: approved / approved: true / accepted: true)"
fi

# 2. Declared scope: YAML block list ("- item") and/or inline "[a, b]" form (G9 awk reuse).
declared_block=$(printf '%s' "$plan" | awk '
  /^[[:space:]]*files_or_components:/ { inblock=1; next }
  inblock && /^[[:space:]]*-[[:space:]]*/ {
    item=$0; sub(/^[[:space:]]*-[[:space:]]*/, "", item); gsub(/"/, "", item)
    if (item != "") print item
    next
  }
  inblock && NF { exit }
')
declared_inline=$(printf '%s' "$plan" | sed -n 's/.*files_or_components:[[:space:]]*\[\([^]]*\)\].*/\1/p' \
  | tr ',' '\n' | tr -d '"')
declared="$(printf '%s\n%s\n' "$declared_block" "$declared_inline" \
  | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' | sed '/^$/d')"

if [ -z "$declared" ]; then
  persist fail "plan declares no files_or_components; NO TASK DISPATCH"
  fail "plan declares no files_or_components; NO TASK DISPATCH"
fi

# 3. Acceptance criteria present (block or inline form).
ac_block=$(printf '%s' "$plan" | awk '
  /^[[:space:]]*acceptance_criteria:/ { inblock=1; next }
  inblock && /^[[:space:]]*-[[:space:]]*/ {
    item=$0; sub(/^[[:space:]]*-[[:space:]]*/, "", item); gsub(/"/, "", item)
    if (item != "") print item
    next
  }
  inblock && NF { exit }
')
ac_inline=$(printf '%s' "$plan" | sed -n 's/.*acceptance_criteria:[[:space:]]*\[\([^]]*\)\].*/\1/p' \
  | tr ',' '\n' | tr -d '"')
acs="$(printf '%s\n%s\n' "$ac_block" "$ac_inline" \
  | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' | sed '/^$/d')"

if [ -z "$acs" ]; then
  persist fail "plan has no acceptance_criteria; NO TASK DISPATCH"
  fail "plan has no acceptance_criteria; NO TASK DISPATCH"
fi

# 4. No unresolved open_questions (block items or inline list).
oq_block=$(printf '%s' "$plan" | awk '
  /^[[:space:]]*open_questions:/ { inblock=1; next }
  inblock && /^[[:space:]]*-[[:space:]]*/ {
    item=$0; sub(/^[[:space:]]*-[[:space:]]*/, "", item); gsub(/"/, "", item)
    if (item != "") print item
    next
  }
  inblock && NF { exit }
')
oq_inline=$(printf '%s' "$plan" | sed -n 's/.*open_questions:[[:space:]]*\[\([^]]*\)\].*/\1/p' \
  | tr ',' '\n' | tr -d '"')
open_qs="$(printf '%s\n%s\n' "$oq_block" "$oq_inline" \
  | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' | sed '/^$/d')"

if [ -n "$open_qs" ]; then
  persist fail "unresolved open questions block dispatch"
  fail "unresolved open questions block dispatch:"$'\n'"$open_qs"
fi

# 5. ASK coverage (DID-012 PR-D1 / invariant I1): an executable task must be bound to a
# durable ASK record before dispatch. A terminal task is not executable, so the adapter
# reports NOT_APPLICABLE (4) and the gate continues. Unbound is a hard refusal; an
# unreadable adapter is BLOCKED -- never a pass.
if [ -n "$ENTRY_TASK" ]; then
  python3 framework/adapters/intake.py verify-task --id "$ENTRY_TASK" >/dev/null 2>&1
  rc=$?
  case $rc in
    0) : ;;
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