#!/usr/bin/env bash
# G15 — eval-harness syntactic tripwires. Ported from the ECC eval-harness
# DEFAULT_TRIPWIRES (external-source provenance; ECC node regexes adapted to ERE
# for this repo's Python + TypeScript stack). Purpose: fail eval-scoped changes
# that silently establish capabilities that corrupt the evaluation — hidden
# network access, process spawning, sandbox weakening, gate probing, parent
# escape. Referenced by impact_to_gates for component and wider changes.
GATE_NAME=g15-eval-tripwires
source "$(dirname "$0")/_lib.sh"

# Scope: changed test/eval/harness/candidate/variant files only. Gate output and
# framework bookkeeping are excluded by changed_source_files() itself.
changed="$(changed_source_files | grep -E '(^|/)(test|tests|eval|evaluation|harness|benchmark|candidate|variant)(/|_|-|\.)' || true)"
if [ -z "$changed" ]; then
  not_applicable "no changed test/eval/harness files — nothing to scan" \
    '{"changed_files":0,"scope":"test|tests|eval|evaluation|harness|benchmark|candidate|variant"}'
fi

if ! have grep || ! have awk; then
  persist blocked "grep/awk unavailable — tripwire scan cannot run"
  log "BLOCKED  tripwire scan could not run (grep/awk missing) — treat as unverified, not conformant"
  exit 2
fi

# A tripwire is rule -> ERE. A hit on any rule fails the gate. Hits are emitted
# as rule|file|line:content so the model can reason about each violation without
# parsing the whole gate output.
tripwire() {  # rule pattern file
  local name="$1" pat="$2" f="$3"
  grep -nE "$pat" "$f" 2>/dev/null | awk -v n="$name" -v file="$f" 'BEGIN{OFS="|"} {print n, file, $0}'
}

scan_one() {  # file -> hits on stdout
  local f="$1"
  tripwire hidden_network    "(^|[^[:alnum:]_])(import|from)[[:space:]]+(http|https|urllib|socket|ssl|xmlrpc)([[:space:].]|$)" "$f"
  tripwire hidden_network    "require\(['\"](node:)?(http|https|net|tls|dgram|dns|http2)['\"]\)" "$f"
  tripwire hidden_network    "fetch[[:space:]]*\(" "$f"
  tripwire process_spawn     "(^|[^[:alnum:]_])(import|from)[[:space:]]+subprocess([[:space:].]|$)" "$f"
  tripwire process_spawn     "os[[:space:]]*\.[[:space:]]*(system|popen)[[:space:]]*\(" "$f"
  tripwire process_spawn     "child_process" "$f"
  tripwire sandbox_weakening "Module[[:space:]]*\._load|--no-sandbox|NODE_OPTIONS|effect-fence|ECC_EFFECT_FENCE" "$f"
  tripwire checker_probe     "taskset|expected_output|gate-marker|gate-receipt|ECC_GATE_|(^|[^[:alnum:]_])GATE[[:alnum:]_]*[[:space:]]*=" "$f"
  tripwire parent_escape     "(^|[^.[:alnum:]_])\.\.([\\/]|['\"\`])" "$f"
}

all_hits=""
for f in $changed; do
  [ -f "$f" ] || continue
  one="$(scan_one "$f")"
  if [ -n "$one" ]; then
    all_hits="$all_hits
$one"
  fi
done

if [ -n "$all_hits" ]; then
  persist fail "eval tripwire hits"
  log "FAIL  eval tripwire violations (rule|file|line:content):"
  printf '%s\n' "$all_hits"
  fail "eval tripwire violations (see above)"
fi

persist pass "no eval tripwire hits"
pass "no eval tripwire hits"