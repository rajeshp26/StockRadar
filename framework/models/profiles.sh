#!/usr/bin/env bash
# Model profiles. Source this, then run opencode.
#
#   source framework/models/profiles.sh baseline    # all agents on one model (control)
#   source framework/models/profiles.sh tiered      # cost-tiered by reasoning demand
#   source framework/models/profiles.sh cheap       # aggressive; expect rework to rise
#
# WHY ENV VARS: opencode.json reads {env:OC_MODEL_*}. Unset yields "", and "" means inherit,
# so an unset variable is a safe no-op. That makes every profile reversible with `unset`
# rather than a config edit -- which matters because you must be able to revert instantly
# when rework rate moves.
#
# MEASUREMENT PROTOCOL: run `baseline` for ~20 tasks, record the report, then run `tiered`
# for ~20 more on comparable work. Compare tokens per session AND rework rate together.
# A token saving with higher rework is a loss.

_p() { export OC_MODEL_DEFAULT="$1" OC_MODEL_SMALL="$2" OC_MODEL_LEAD="$3" \
       OC_MODEL_RESEARCH="$4" OC_MODEL_ARCHITECT="$5" OC_MODEL_PLANNER="$6" \
       OC_MODEL_IMPLEMENT="$7" OC_MODEL_REVIEW="$8" OC_MODEL_VERIFY="$9"; }

# Replace these identifiers with models your provider actually exposes: `opencode models`.
BIG="${OC_BIG:-anthropic/claude-sonnet-4-5}"
MID="${OC_MID:-anthropic/claude-sonnet-4-5}"
SML="${OC_SML:-anthropic/claude-haiku-4-5}"

case "${1:-}" in
  baseline)
    # Control. Everything on one model so a later comparison has a reference point.
    _p "$BIG" "$SML" "$BIG" "$BIG" "$BIG" "$BIG" "$BIG" "$BIG" "$BIG"
    echo "[models] baseline: all agents -> $BIG" ;;
  tiered)
    # Implementer, Architect and Reviewer keep the strong model: code, boundaries, and
    # independent judgement are where a cheap model's errors are most expensive.
    # Team Lead, Planner and Verifier drop: table-driven routing, decomposition of an
    # approved design, and exit-code transcription.
    _p "$MID" "$SML" "$SML" "$MID" "$BIG" "$SML" "$BIG" "$BIG" "$SML"
    echo "[models] tiered: implement/architect/review -> $BIG | lead/plan/verify -> $SML" ;;
  cheap)
    # Only the Implementer stays strong. Expect rework to rise; the report will show it.
    _p "$SML" "$SML" "$SML" "$SML" "$MID" "$SML" "$MID" "$MID" "$SML"
    echo "[models] cheap: minimal spend -- watch rework rate closely" ;;
  reset|off)
    unset OC_MODEL_DEFAULT OC_MODEL_SMALL OC_MODEL_LEAD OC_MODEL_RESEARCH \
          OC_MODEL_ARCHITECT OC_MODEL_PLANNER OC_MODEL_IMPLEMENT OC_MODEL_REVIEW OC_MODEL_VERIFY
    echo "[models] reset: all agents inherit OpenCode's configured default" ;;
  *)
    echo "usage: source framework/models/profiles.sh {baseline|tiered|cheap|reset}"
    echo "override tiers with OC_BIG / OC_MID / OC_SML"
    return 2 2>/dev/null || exit 2 ;;
esac

echo "[models] active:"
for v in DEFAULT LEAD RESEARCH ARCHITECT PLANNER IMPLEMENT REVIEW VERIFY; do
  n="OC_MODEL_$v"; printf '  %-22s %s\n' "$n" "${!n:-<inherit>}"
done
