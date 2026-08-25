#!/usr/bin/env bash
# G9 - Scope Discipline. Fails when a changed source file was not declared in the plan.
set -uo pipefail

GATE_NAME="g9_scope"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lib.sh
source "$SCRIPT_DIR/_lib.sh"

SCOPE_PLAN="${SCOPE_PLAN:-}"
SCOPE_TASK="${SCOPE_TASK:-}"

if [ -z "$SCOPE_PLAN" ] && [ -n "$SCOPE_TASK" ]; then
  SCOPE_PLAN="$(python3 framework/adapters/gsd_state.py plan-path --task "$SCOPE_TASK" 2>/dev/null || true)"
fi

if [ ! -f "$SCOPE_PLAN" ]; then
  persist skip "no plan context"
  skip "no plan context (SCOPE_PLAN/SCOPE_TASK unset or plan not found); scope not judged"
fi

# Declared scope: YAML block list ("- item") and/or inline "[a, b]" form of files_or_components.
declared_block=$(awk '
  /^[[:space:]]*files_or_components:/ { inblock=1; next }
  inblock && /^[[:space:]]*-[[:space:]]*/ {
    item=$0; sub(/^[[:space:]]*-[[:space:]]*/, "", item); gsub(/"/, "", item)
    if (item != "") print item
    next
  }
  inblock && NF { exit }
' "$SCOPE_PLAN")

declared_inline=$(sed -n 's/.*files_or_components:[[:space:]]*\[\([^]]*\)\].*/\1/p' "$SCOPE_PLAN" \
  | tr ',' '\n' | tr -d '"' )

declared="$(printf '%s\n%s\n' "$declared_block" "$declared_inline" \
  | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' | sed '/^$/d')"

if [ -z "$declared" ]; then
  persist fail "plan declares no files_or_components"
  fail "plan declares no files_or_components; scope cannot be judged"
fi

changed="$(changed_source_files)"
if [ -z "$changed" ]; then
  persist skip "no source changes"
  skip "no source changes; scope not judged"
fi

violations=""
while IFS= read -r file; do
  [ -z "$file" ] && continue
  matched=""
  while IFS= read -r d; do
    [ -z "$d" ] && continue
    case "$file" in
      "$d"|"$d"/*) matched=1 ;;
      "$d".py|"$d".ts|"$d".tsx|"$d".js|"$d".jsx|"$d".go|"$d".rs) matched=1 ;;
    esac
    [ -n "$matched" ] && break
  done <<EOF_D
$declared
EOF_D
  [ -n "$matched" ] || violations+="${file}"$'\n'
done <<EOF_C
$changed
EOF_C

if [ -n "$violations" ]; then
  persist fail "changes outside declared scope"
  fail "changes outside declared scope:"$'\n'"$violations"
fi

persist pass "all changed files within declared scope"
pass "all changed files within declared scope"
