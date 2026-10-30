#!/usr/bin/env bash
# test_g_skill_use.sh -- proves the G-SKILL-USE exit ladder, one case per condition.
#
# WHY THIS TEST IS FALSIFIABLE
#   Every case copies the REAL gate and the REAL tools into a throwaway root and runs the real
#   entry point, asserting the exit code. Nothing is stubbed except the record store, which is
#   the input. If the gate's ladder weakens, a case goes red; if the copy fails, the harness
#   errors instead of passing with zero cases.
#
#   The cases worth reading are the ones a naive implementation gets wrong -- each one is a
#   defect this gate was written to not have:
#     * an absent record store read as 4 (nothing to check) when the plan required skills
#     * a multi-block plan verified only against its first required_skills block
#     * no plan context read as 0 (a parser yielding no names makes the diff trivially empty)
#     * a skill recorded under a DIFFERENT task credited to this one
#     * `unknown` from a broken sensor counted as a loaded skill
#
# WHY A SEPARATE FILE AND NOT A `--self-test` FLAG
#   `framework/validate.py` is a plane file: a gate written by an agent cannot be wired into the
#   suite by that agent. This follows the existing convention for gate tests
#   (test_gate_verdict_contract.sh, test_g18_security_audit.sh) so it is runnable, citable and
#   independent of the gate's own argument surface.
#
# Usage: bash framework/gates/test_g_skill_use.sh
# Exit:  0 = every case matches | 1 = a case failed (the defect) | 2 = harness error
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
GATE="$HERE/g_skill_use.sh"
TOOLS="$HERE/../tools"

for f in "$GATE" "$HERE/_lib.sh" "$TOOLS/skill_use.py" "$TOOLS/skill_coverage.py"; do
  if [ ! -f "$f" ]; then
    echo "HARNESS ERROR: missing $f" >&2
    exit 2
  fi
done

root="$(mktemp -d 2>/dev/null)" || { echo "HARNESS ERROR: mktemp unavailable" >&2; exit 2; }
trap 'rm -rf "$root"' EXIT

dir=""
PLAN=""
TASK=""
pass_n=0
fail_n=0

_mk() { # a root with only what the gate legitimately needs
  dir="$root/$1"
  mkdir -p "$dir/framework/gates" "$dir/framework/tools" "$dir/framework/opencode/plugin"
  cp "$HERE/_lib.sh" "$dir/framework/gates/"
  cp "$GATE" "$dir/framework/gates/"
  cp "$TOOLS/skill_use.py" "$dir/framework/tools/"
  cp "$TOOLS/skill_coverage.py" "$dir/framework/tools/"
  : > "$dir/framework/opencode/plugin/telemetry.ts"
}

_plan()    { printf '%s\n' "$2" > "$dir/$1"; }
_mode()    { mkdir -p "$dir/framework/plan"; printf '%s\n' "$1" > "$dir/framework/plan/lint_mode"; }
_nosensor(){ rm -f "$dir/framework/opencode/plugin/telemetry.ts"; }
_records() { mkdir -p "$dir/.planning/telemetry"; printf '%s\n' "$1" > "$dir/.planning/telemetry/records.jsonl"; }
_rec()     { printf '{"kind":"final","session_id":"%s","task_id":"%s","skills_loaded":%s}\n' "$1" "$2" "$3"; }

_expect() { # <want> <label>
  local got
  ( cd "$dir" && ENTRY_TASK="$TASK" ENTRY_PLAN="$PLAN" bash "$dir/framework/gates/g_skill_use.sh" ) \
    > "$dir/out.txt" 2>&1
  got=$?
  if [ "$got" = "$1" ]; then
    pass_n=$((pass_n + 1)); printf '  PASS  %-58s exit=%s\n' "$2" "$got"
  else
    fail_n=$((fail_n + 1)); printf '  FAIL  %-58s exit=%s want=%s\n' "$2" "$got" "$1"
    sed 's/^/        | /' "$dir/out.txt" | head -n 8
  fi
  PLAN=""; TASK=""
}

# 1. No plan context is a routing defect, never a pass.
_mk no_plan; _expect 2 "no ENTRY_PLAN -> BLOCKED"
# 2. A plan path that does not exist is BLOCKED too.
_mk gone; PLAN="$root/gone/nope.md"; _expect 2 "unreadable plan -> BLOCKED"
# 3. No telemetry plugin: nothing can observe a skill call.
_mk no_sensor; _nosensor; PLAN="$root/no_sensor/PLAN.md"
_plan PLAN.md "required_skills:
- apple-ui"
_expect 3 "telemetry plugin absent -> CAPABILITY_MISSING"
# 4. A plan requiring nothing leaves nothing to diff.
_mk no_req; PLAN="$root/no_req/PLAN.md"; _plan PLAN.md "files_or_components:
- backend/api/x.py"
_expect 4 "plan requires no skills -> NOT_APPLICABLE"
# 5. No records at all: the sensor has never written anything here.
_mk no_rec; PLAN="$root/no_rec/PLAN.md"; _plan PLAN.md "required_skills:
- apple-ui"
_expect 4 "no telemetry records -> NOT_APPLICABLE"
# 6. One switch turns every half of the skill contract off.
_mk off; _mode off; PLAN="$root/off/PLAN.md"; _plan PLAN.md "required_skills:
- apple-ui"
_expect 4 "lint_mode=off -> NOT_APPLICABLE"
# 7. An invalid mode is BLOCKED, never a silent default.
_mk badmode; _mode sometimes; PLAN="$root/badmode/PLAN.md"; _plan PLAN.md "required_skills:
- apple-ui"
_expect 2 "invalid lint_mode -> BLOCKED"
# 8. Records exist but nothing was loaded for this task: a verdict, not a missing input.
_mk no_load; PLAN="$root/no_load/PLAN.md"; _plan PLAN.md "required_skills:
- apple-ui"; _records "$(_rec ses_a T-01 '[]')"; TASK="T-01"
_expect 1 "required skill not recorded -> FAIL"
# 9. Clean: every required skill recorded for the task.
_mk clean; PLAN="$root/clean/PLAN.md"; _plan PLAN.md "required_skills:
- apple-ui
- frontend-react"; _records "$(_rec ses_a T-01 '["apple-ui","frontend-react"]')"; TASK="T-01"
_expect 0 "all required skills recorded -> PASS"
# 10. TEETH: a skill recorded for a DIFFERENT task does not credit this one.
_mk othertask; PLAN="$root/othertask/PLAN.md"; _plan PLAN.md "required_skills:
- designmotion-design"
_records "$(_rec ses_a T-01 '["designmotion-design"]')"; TASK="T-02"
_expect 1 "another task's session does not count -> FAIL"
# 11. TEETH: the second required_skills block is still verified. A first-block-only parser
#     passes this case without ever looking at frontend-react.
_mk multiblock; PLAN="$root/multiblock/PLAN.md"; _plan PLAN.md "required_skills:
- apple-ui
files_or_components:
- web/src/App.tsx
required_skills:
- frontend-react"
_records "$(_rec ses_a T-01 '["apple-ui"]')"; TASK="T-01"
_expect 1 "second required_skills block still verified -> FAIL"
# 12. TEETH: `unknown` is a sensor defect, never a loaded skill.
_mk unknown; PLAN="$root/unknown/PLAN.md"; _plan PLAN.md "required_skills:
- apple-ui"; _records "$(_rec ses_a T-01 '["unknown"]')"; TASK="T-01"
_expect 1 "'unknown' from a broken sensor satisfies nothing -> FAIL"
# 13. Lifecycle series for one session: the last line wins, so a skill loaded at `final` is
#     credited even though `started` carried an empty list.
_mk series; PLAN="$root/series/PLAN.md"; _plan PLAN.md "required_skills:
- apple-ui"
_records "$(printf '{"kind":"started","session_id":"s1","task_id":"T-01","skills_loaded":[]}\n')
$(_rec s1 T-01 '["apple-ui"]')"; TASK="T-01"
_expect 0 "lifecycle series collapses, last wins -> PASS"
# 14. Advisory mode reports without changing the verdict, and must not claim a clean run.
_mk warnmode; _mode warn; PLAN="$root/warnmode/PLAN.md"; _plan PLAN.md "required_skills:
- designmotion-design"; _records "$(_rec ses_a T-01 '[]')"; TASK="T-01"
_expect 0 "lint_mode=warn -> advisory, exit 0"

printf 'selftest: %d/%d pass\n' "$pass_n" "$((pass_n + fail_n))"
[ "$fail_n" -eq 0 ]
