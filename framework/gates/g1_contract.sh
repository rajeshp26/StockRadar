#!/usr/bin/env bash
# G1 — Contract validation. V1 enforces HTTP API contracts only (OpenAPI + generated types
# + contract tests). Event schemas, DB contracts and service-interface contracts are
# explicitly out of scope for v1.
#
# Three independent checks, each of which can fail the gate:
#   1. Schema is structurally valid.
#   2. Generated types are in sync with the schema (drift = implementation may not match).
#   3. Contract tests execute and pass.
#
# A missing toolchain never reads as a pass. A tool that cannot run reports BLOCKED.
GATE_NAME=g1_contract
source "$(dirname "$0")/_lib.sh"

CONTRACT_DIR="$STATE_ROOT/contracts"
[ -d "$CONTRACT_DIR" ] || { persist skip "no contracts dir"; skip "no contracts directory"; }

SCHEMAS=$(find "$CONTRACT_DIR" -name '*.openapi.y*ml' 2>/dev/null | sort || true)
[ -n "$SCHEMAS" ] || { persist skip "no openapi schemas"; skip "no OpenAPI schemas"; }

have python3 || { persist blocked "python3 unavailable"; fail "BLOCKED: python3 required for G1"; }

rc=0
contract_changed=0

# ── 1. Schema validity ─────────────────────────────────────────────────────────
# shellcheck disable=SC2086
if ! python3 framework/contracts/validate_schema.py $SCHEMAS; then
  log "schema validation failed"; rc=1
fi

# ── 2. Generated type drift ────────────────────────────────────────────────────
# Types are generated from the contract. If the committed types differ from a fresh
# generation, an implementer edited types by hand or the schema moved underneath them.
for s in $SCHEMAS; do
  if ! python3 framework/contracts/gen_types.py --schema "$s" --check; then
    log "generated types out of sync with $s"; rc=1
  fi
done

# ── 3. Contract change vs contract violation ───────────────────────────────────
# A change is legitimate but requires Architect + human gate H2. A violation is a defect.
# These are different outcomes and must not collapse into one exit code.
CHANGED_CONTRACTS=$(changed_files | grep -F "$CONTRACT_DIR" || true)
for s in $CHANGED_CONTRACTS; do
  # "HEAD:path" resolves from the REPO ROOT; "HEAD:./path" resolves from CWD. In a monorepo
  # subdirectory the former silently fails, making every changed contract look brand new.
  if git show "HEAD:./$s" >/dev/null 2>&1; then
    log "CONTRACT_CHANGE in $s — route to Architect; human gate H2 if incompatible"
    contract_changed=1
  else
    log "new contract added: $s (no consumers to invalidate yet)"
  fi
done

# ── 4. Contract tests are the actual gate ──────────────────────────────────────
if [ ! -d tests/contract ]; then
  log "FAIL no tests/contract directory — a contract without tests is not a gate"
  rc=1
else
  TESTS=$(find tests/contract -name 'test_*.py' 2>/dev/null | sort || true)
  if [ -z "$TESTS" ]; then
    log "FAIL tests/contract exists but contains no test_*.py — not a gate"
    rc=1
  elif have pytest; then
    pytest -q tests/contract || { log "contract tests failed (pytest)"; rc=1; }
  else
    # Standalone fallback. Contract tests must be runnable without an optional install.
    log "pytest unavailable; running contract tests standalone"
    for t in $TESTS; do
      python3 "$t" || { log "contract tests failed: $t"; rc=1; }
    done
  fi
fi

# Precedence: CONTRACT_CHANGE outranks test failure. An incompatible schema change causes
# test failures by definition. Reporting the symptom would route to Implementer; the change
# itself must route to Architect + H2. Different owner, different remedy.
if [ "$contract_changed" = "1" ]; then
  persist changed "contract change requires architect review + H2"
  [ $rc -ne 0 ] && log "note: consumers currently fail against the changed schema — expected until re-planned"
  fail "CONTRACT_CHANGE detected — Architect review + human gate H2 required"
fi

case $rc in
  0) persist pass "schemas valid, types in sync, contract tests green"
     pass "contract gate green" ;;
  *) persist fail "contract validation failed"
     fail "contract validation failed" ;;
esac
