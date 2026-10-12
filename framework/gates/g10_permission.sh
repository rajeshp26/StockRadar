#!/usr/bin/env bash
# G10 - Permission Policy. Asserts opencode.json enforces the risk-tiered permission model:
#   * catch-all "ask" first (last-match-wins ordering)
#   * allow families: git read, test/build/lint, trusted framework scripts
#   * deny families: destructive fs, git history mutation, push
#   * negative invariants: no backend/scripts path trust, no arbitrary python allow,
#     no New-Item allow
#   * per-agent enforcement: team-lead (primary) ask default; every subagent
#     fail-fast (bash catch-all deny) with scoped allows
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
  not_applicable "opencode.json absent; nothing to judge" \
    '{"checked":"opencode.json","found":false}'
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

# DID-013 PR-G10 calibration: the per-agent bash catch-all must match the realized
# fail-fast model — team-lead (primary) may prompt (ask); every subagent defaults
# to deny and is granted scoped allows. (Staged PR-G10 originally asserted
# implementer=ask, which predates the T-05 fail-fast fix and would keep the gate red.)
for agent, expected in (
    ("team-lead", "ask"),
    ("researcher", "deny"),
    ("architect", "deny"),
    ("planner", "deny"),
    ("implementer", "deny"),
    ("reviewer", "deny"),
    ("verifier", "deny"),
):
    abash = (((cfg.get("agent") or {}).get(agent) or {}).get("permission") or {}).get("bash")
    if not isinstance(abash, dict) or abash.get("*") != expected:
        violations.append("agent '%s' bash catch-all is not '%s'" % (agent, expected))

# --- [2] edit permission schema (enforcement plane; DID-013 PR-G10) ----
# The enforcement plane is agent-immutable. Its path set is read from the canonical
# framework/security/enforcement_plane.yaml (the single source of truth), NOT a hardcoded
# tuple: the framework repo and the app repo declare different planes (the pin owns
# framework/** in the app repo). The bash checks above never see the edit plane; assert
# its shape explicitly so a config edit that opens the plane fails the gate.
edit = (cfg.get("permission") or {}).get("edit")
try:
    import yaml
    with open(root + "/framework/security/enforcement_plane.yaml", encoding="utf-8") as _pf:
        PLANE = tuple(e["path"] for e in yaml.safe_load(_pf.read())["paths"])
    if not PLANE:
        raise ValueError("empty 'paths'")
except Exception as _exc:  # noqa: BLE001 - fail closed, never pass silently
    violations.append("enforcement-plane unreadable: %s" % _exc)
    PLANE = ()
if not isinstance(edit, dict):
    violations.append("permission.edit missing or not an object")
else:
    ekeys = list(edit.keys())
    if not ekeys or ekeys[0] != "*":
        violations.append('first edit rule is not the catch-all "*" (last-match-wins ordering)')
    elif edit.get("*") != "ask":
        violations.append('edit catch-all "*" is not "ask"')
    for p in PLANE:
        if edit.get(p) != "deny":
            violations.append("enforcement-plane path '%s' not denied in permission.edit" % p)
    for pat, effect in edit.items():
        if effect not in ("allow", "deny", "ask"):
            violations.append("edit rule '%s' has unknown effect '%s'" % (pat, effect))

# reviewers/planners/researchers are read-only: bare deny, no editor surface
for agent in ("reviewer", "planner", "researcher"):
    aedit = (((cfg.get("agent") or {}).get(agent) or {}).get("permission") or {}).get("edit")
    if aedit != "deny":
        violations.append("agent '%s' edit is not bare 'deny' (got %r)" % (agent, aedit))

# architect and verifier: default-deny dict, writing only where the role owns
for agent in ("architect", "verifier"):
    aedit = (((cfg.get("agent") or {}).get(agent) or {}).get("permission") or {}).get("edit")
    if not isinstance(aedit, dict) or aedit.get("*") != "deny":
        violations.append("agent '%s' edit must be dict with '*' 'deny' (got %r)" % (agent, aedit))

# team-lead: catch-all ask + explicit plane denies (the only agent allowed to prompt)
aedit = (((cfg.get("agent") or {}).get("team-lead") or {}).get("permission") or {}).get("edit")
if not isinstance(aedit, dict) or aedit.get("*") != "ask":
    violations.append("team-lead edit must be dict with '*' 'ask' (got %r)" % aedit)
else:
    for p in PLANE:
        if aedit.get(p) != "deny":
            violations.append("team-lead edit does not deny plane path '%s'" % p)

# implementer: grants >=1 allow, never through the catch-all
aedit = (((cfg.get("agent") or {}).get("implementer") or {}).get("permission") or {}).get("edit")
if not isinstance(aedit, dict) or not any(v == "allow" for v in aedit.values()):
    violations.append("implementer edit must be dict granting >=1 allow (got %r)" % aedit)
elif aedit.get("*") == "allow":
    violations.append("implementer edit catch-all must not be 'allow'")

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