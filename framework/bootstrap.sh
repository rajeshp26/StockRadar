#!/usr/bin/env bash
# Bootstrap. Sequential with validation after each stage. Do not proceed on failure.
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p framework/.manifest

# Manifests are environment-specific caches: absolute paths plus the detected
# host. One that ships with the distribution (or survives an OS switch) points
# at the BUILD machine and is trusted blindly by gsd_state.py manifest(), which
# is how a /home/<build-user>/... state root once poisoned G1 on a fresh
# install. Purge both so every bootstrap re-detects THIS environment.
rm -f framework/.manifest/host.json framework/.manifest/gsd.json

step() { printf '\n=== %s ===\n' "$*"; }
die()  { printf 'BLOCKED: %s\n' "$*" >&2; exit 1; }

step "1/7 Detect agent runtime host"
python3 framework/adapters/host.py describe > /dev/null || die "host detection failed"
python3 -c "
import json;m=json.load(open('framework/.manifest/host.json'))
print(' host:', m['host'], '/', m['version'] or 'not on PATH')
print(' permissions:', m['capabilities']['permission_enforcement'])
print(' agent format:', m['agent_def_format']['kind'])
print(' host-neutral:', str(m['portability']['host_neutral_pct'])+'%')
d=m.get('DOWNGRADE')
print(' DOWNGRADE:', d) if d else None"
python3 framework/adapters/host.py downgrade > /dev/null 2>&1 || \
  echo " WARNING: active host cannot enforce permissions — star topology is advisory here."

step "2/7 Detect GSD distribution and instantiate state adapter"
python3 framework/adapters/gsd_state.py detect || die "gsd detection failed"
python3 framework/adapters/gsd_state.py manifest > /dev/null
STATE_ROOT=$(python3 framework/adapters/gsd_state.py state-root)
echo " state root: $STATE_ROOT"
mkdir -p "$STATE_ROOT/contracts" "$STATE_ROOT/decisions" "$STATE_ROOT/telemetry"

step "3/7 Adopt-before-extend audit"
python3 framework/audit_check.py; AUDIT_RC=$?
case "$AUDIT_RC" in
  0) echo " audit complete — every overlap has a recorded decision." ;;
  3) echo " -> REQUIRED STEP, not a defect. Fill each Decision cell in framework/ADOPT_AUDIT.md"
     echo "    with adopt | wrap | replace. 'replace' needs a named defect class GSD cannot catch."
     echo "    Unexamined overlap is how a 7-agent framework silently becomes a 13-agent one." ;;
  *) die "audit check failed (rc=$AUDIT_RC) — see output above" ;;
esac

step "4/7 Resolve code intelligence capabilities"
python3 framework/adapters/code_intel.py resolve | python3 -c "
import json,sys
m=json.load(sys.stdin)
print(' provider:', m['provider'] or 'none (tier 4 fallback)')
for cap,info in m['capabilities'].items():
    w=' <- '+info['warning'] if 'warning' in info else ''
    print(f\"  {cap:<16} tier {info['tier']} via {info['via']}{w}\")
"

step "5/7 Agent, tool, plugin and permission artifacts"
for f in opencode.json AGENTS.md framework/opencode/tools/context-builder.ts framework/opencode/plugin/telemetry.ts; do
  [ -e "$f" ] || die "missing $f"
done
ls framework/opencode/agents/*.md | wc -l | xargs printf ' agent definitions: %s\n'
chmod +x framework/gates/*.sh framework/adapters/*.py framework/*.sh 2>/dev/null || true

step "6/7 Skills and rules"
ls -1 framework/opencode/skills | xargs printf ' skill: %s\n'
ls -1 framework/opencode/rules | xargs printf ' rule: %s\n'
chmod +x framework/retro/*.py 2>/dev/null || true
printf ' gates: '; ls -1 framework/gates/g*.sh | wc -l | tr -d "\n"; printf ' (g1-g8)\n'
# Retro subsystem: report open defect-escape triggers so an install inherits nothing silently.
_sr="$(python3 framework/adapters/gsd_state.py state-root 2>/dev/null || echo .planning)"
if [ -d "$_sr/retro/triggers" ] && [ -n "$(ls -A "$_sr/retro/triggers" 2>/dev/null)" ]; then
  printf ' OPEN retro triggers: %s (g7 will block completion until discharged)\n' \
    "$(ls -1 "$_sr/retro/triggers" | wc -l | tr -d ' ')"
else
  printf ' retro triggers: none open\n'
fi
# Blocker escalation: report open blockers so an install inherits nothing silently.
_open_blk=$(python3 framework/adapters/gsd_state.py list-blockers 2>/dev/null | python3 -c "
import sys, json
try:
    print(len(json.load(sys.stdin)))
except Exception:
    print(chr(63))" 2>/dev/null)
[ -n "$_open_blk" ] || _open_blk="?"
if [ "$_open_blk" = "?" ]; then
  printf ' blockers: UNREADABLE -- refusing to read as zero (check python3/pyyaml)\n'
elif [ "$_open_blk" -eq 0 ]; then
  printf ' open blockers: none\n'
else
  printf ' OPEN blockers: %s -- g8 blocks completion until resolved\n' "$_open_blk"
fi

step "7/7 Validate"
python3 framework/validate.py || die "validation failed"
printf '\nBootstrap complete. Start with: opencode --agent team-lead\n'
