#!/usr/bin/env bash
# G10 - Permission Policy. Asserts opencode.json enforces the risk-tiered permission model:
#   * catch-all "ask" first (last-match-wins ordering)
#   * allow families: git read, test/build/lint, trusted framework scripts
#   * deny families: destructive fs, git history mutation, push
#   * negative invariants: no backend/scripts path trust, no arbitrary python allow,
#     no New-Item allow
#   * per-agent enforcement: reviewer deny-only, implementer ask default
# A gate cannot drive opencode's interactive ask/allow engine; it asserts the policy
# structure that produces those behaviours. Interactive silence/prompt/deny is verified
# by the manual smoke commands in EXIT_CODES.md.
# Exit: 0 conformant | 1 violations | 2 BLOCKED (python3 absent) | 4 NOT_APPLICABLE
set -uo pipefail

GATE_NAME="g10_permission"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lib.sh
source "$SCRIPT_DIR/_lib.sh"

if ! have python3; then
  persist blocked "python3 absent; cannot parse opencode.json"
  exit 2
fi

if [ ! -f opencode.json ]; then
  persist skip "opencode.json absent; nothing to judge"
  exit 4
fi

out="$(python3 - "$PWD" <<'PY' 2>&1 || true
import json, sys

root = sys.argv[1]
violations = []

try:
    with open(root + "/opencode.json", encoding="utf-8-sig") as fh:
        cfg = json.load(fh)
except FileNotFoundError:
    print(json.dumps({"violations": ["opencode.json not found"], "config_scanned": False}))
    sys.exit(0)
except Exception as exc:  # noqa: BLE001 - any parse failure must fail the gate
    print(json.dumps({"violations": ["opencode.json unparsable: %s" % exc]}))
    sys.exit(0)

bash = (cfg.get("permission") or {}).get("bash")
if not isinstance(bash, dict):
    print(json.dumps({"violations": ["permission.bash missing or not an object"]}))
    sys.exit(0)

keys = list(bash.keys())
if not keys or keys[0] != "*":
    violations.append('first bash rule is not the catch-all "*" (last-match-wins ordering)')
elif bash.get("*") != "ask":
    violations.append('catch-all "*" is not "ask"')

allow = {k: v for k, v in bash.items() if v == "allow"}
deny = {k: v for k, v in bash.items() if v == "deny"}

def has_any(family, mapping, label, minimum):
    found = [p for p in family if p in mapping]
    if len(found) < minimum:
        violations.append("%s: expected >= %d of %s, found %s" % (label, minimum, family, found))

has_any(["git status*", "git diff*", "git log*", "git show*"], allow, "git read allow family", 3)
has_any(["npm test*", "npm run build*", "npm run lint*", "pytest*", "tsc*", "eslint*", "ruff*", "mypy*"], allow, "test/build/lint allow family", 3)
has_any(["python3 framework/*", "python framework/*", "bash framework/*", "./framework/*"], allow, "trusted framework allow", 1)
has_any(["Remove-Item*", "rm *", "del *", "rmdir*", "rd *"], deny, "destructive fs deny family", 2)
has_any(["git push*", "git reset*", "git clean*", "git checkout*", "git restore*", "git rebase*", "git merge*", "git cherry-pick*"], deny, "git write deny family", 4)

for pat in allow:
    if "backend/scripts" in pat or "backend\\scripts" in pat:
        violations.append("path trust hole: allow '%s' covers mixed-risk backend/scripts" % pat)
    if pat.startswith(("python", "python3")) and "framework/" not in pat:
        violations.append("arbitrary python allow: '%s' not scoped to framework/" % pat)
    if pat.startswith("New-Item"):
        violations.append("forbidden New-Item allow: '%s' (native Write/Edit tools cover creation)" % pat)

for pat, effect in bash.items():
    if effect not in ("allow", "deny", "ask"):
        violations.append("rule '%s' has unknown effect '%s'" % (pat, effect))

for agent, expected in (("reviewer", "deny"), ("implementer", "ask")):
    abash = (((cfg.get("agent") or {}).get(agent) or {}).get("permission") or {}).get("bash")
    if not isinstance(abash, dict) or abash.get("*") != expected:
        violations.append("agent '%s' bash catch-all is not '%s'" % (agent, expected))

print(json.dumps({"violations": violations, "config_scanned": True}))
PY
)"

status="$(printf '%s' "$out" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("OK" if not d.get("violations") else "VIOLATIONS")' 2>/dev/null || echo PARSE_ERR)"
if [ "$status" = "OK" ]; then
  persist pass "permission policy conformant"
  pass "permission policy conformant"
elif [ "$status" = "VIOLATIONS" ]; then
  printf '%s' "$out" | python3 -c 'import json,sys; [print("  - "+v) for v in json.load(sys.stdin)["violations"]]' >&2
  persist fail "permission policy violations"
  fail "permission policy violations (see list above)"
else
  persist blocked "gate output unparsable"
  exit 2
fi