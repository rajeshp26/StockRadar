#!/usr/bin/env bash
# G3 — Architecture validation. Required for cross_component and system impact.
GATE_NAME=g3_architecture
source "$(dirname "$0")/_lib.sh"
rc=0

RULES="framework/architecture_rules.yaml"
[ -f "$RULES" ] || { persist skip "no architecture rules"; skip "no $RULES"; }

# Forbidden import edges, declared not inferred.
set +e
python3 - "$RULES" <<'PY'
import sys, subprocess, re, pathlib
try:
    import yaml
except ImportError:
    print("[g3] pyyaml missing; cannot enforce declared boundaries"); sys.exit(2)
rules = yaml.safe_load(pathlib.Path(sys.argv[1]).read_text()) or {}
changed = sorted(set(
    subprocess.run(["git","diff","--name-only","HEAD"],capture_output=True,text=True).stdout.split()
  + subprocess.run(["git","ls-files","--others","--exclude-standard"],capture_output=True,text=True).stdout.split()
))
if not changed:
    print("[g3] no changed files"); sys.exit(0)
bad = []
for rule in rules.get("forbidden_imports", []):
    frm, imports = rule["from"], rule["must_not_import"]
    for f in changed:
        if not f.startswith(frm): continue
        try: body = pathlib.Path(f).read_text()
        except Exception: continue
        for target in imports:
            if re.search(rf"(import|from|require).*{re.escape(target)}", body):
                bad.append(f"{f} imports forbidden {target}")
for b in bad: print(f"[g3] VIOLATION {b}")
sys.exit(1 if bad else 0)
PY
prc=$?
set -e
if [ $prc -eq 2 ]; then persist blocked "pyyaml missing"; fail "cannot enforce boundaries: install pyyaml"; fi
[ $prc -eq 0 ] || rc=1

# Active decisions must not be silently contradicted.
DEC="$STATE_ROOT/decisions"
if [ -d "$DEC" ]; then
  log "$(find "$DEC" -name '*.md' | wc -l | tr -d ' ') decision records present"
fi

# ─ Architecture design checklist ──────────────────────────────────────────────────────────────
# The Architect's output is a DECISION; no artefact exists for a gate to execute against.
# The checklist fills that gap, and a disposition is what makes it verifiable. Loading the
# checklist is not compliance — a per-item verdict is.
#
# Owed ONLY when this task produced architecture work. RETRO_TASK is set by the Team Lead for
# a task routed through the Architect. Absent it, there is no design decision to disposition
# and the checklist does not apply — a gate that demands dispositions for a typo fix gets
# routed around, and a gate that gets routed around enforces nothing.
CHECKLIST="framework/architecture/checklist_check.py"
if [ -f "$CHECKLIST" ] && [ -n "${RETRO_TASK:-}" ] && [ "${ARCHITECTURE_TASK:-}" = "1" ]; then
  set +e
  python3 "$CHECKLIST" structure >/dev/null 2>&1; crc=$?
  set -e
  if [ $crc -eq 2 ]; then persist blocked "pyyaml missing for checklist"; fail "cannot evaluate design checklist: install pyyaml"; fi
  if [ $crc -eq 1 ]; then
    python3 "$CHECKLIST" structure || true
    persist fail "design checklist structurally invalid"
    fail "design checklist invalid — fix before it is used as evidence"
  fi
  set +e
  cout=$(python3 "$CHECKLIST" dispositions --task "$RETRO_TASK" 2>&1); drc=$?
  set -e
  if [ $drc -ne 0 ]; then
    echo "$cout"
    if [ $drc -eq 3 ]; then
      persist fail "design checklist disposition owed for $RETRO_TASK"
      fail "design checklist disposition OWED — architecture work without a recorded verdict"
    fi
    persist fail "design checklist disposition invalid for $RETRO_TASK"
    fail "design checklist disposition invalid"
  fi
  log "design checklist dispositioned for $RETRO_TASK"
elif [ -f "$CHECKLIST" ]; then
  log "design checklist not applicable (no architecture task in scope)"
fi

[ $rc -eq 0 ] && { persist pass "boundaries respected"; pass "architecture gate green"; }
persist fail "architecture boundary violation"
fail "architecture violation"
