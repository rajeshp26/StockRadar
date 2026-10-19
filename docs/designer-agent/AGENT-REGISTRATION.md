# Register the `ui-designer` agent (human action — plane-locked)

Adding a spawnable subagent requires **two** edits. Both touch the root `opencode.json`,
which is an enforcement-plane file (`opencode.json` is `edit: deny` — see the fence in
`AGENTS.md` and `framework/security/enforcement_plane.yaml`). An agent cannot make these
edits; a human must.

## 1. Add the agent entry to `opencode.json`

Merge this object into the top-level `"agent"` block (`opencode.json` begins that block at
line 72). Keep alphabetical/positional consistency with the existing entries.

```json
"ui-designer": {
  "description": "Designs UI and produces 2-3 throwaway HTML mockup variants for human approval, grounded in design/skills. Foreground only.",
  "mode": "subagent",
  "permission": {
    "edit": {
      "*": "deny",
      ".planning/**": "allow",
      ".opencode/**": "deny",
      "opencode.json": "deny",
      "AGENTS.md": "deny",
      "framework.config.json": "deny",
      "framework/opencode/**": "deny",
      "framework/plan/**": "deny",
      "framework/testing/**": "deny",
      "framework/security/**": "deny"
    },
    "task": {
      "*": "deny"
    },
    "bash": {
      "*": "deny",
      "git status*": "allow",
      "git diff*": "allow",
      "git log*": "allow",
      "git show*": "allow"
    }
  },
  "model": "opencode/big-pickle",
  "temperature": 0.3,
  "_model_rationale": "Variant generation rewards breadth: every variant is throwaway and human-reviewed, so exploration variance is cheap to absorb while a homogenised shortlist costs the project a genuinely different direction."
}
```

Design notes (verified against sibling entries):
- **`model`, `temperature` and `_model_rationale` are mandatory**, not decorative.
  `framework/validate.py:1521-1526` (check [20]) asserts all three for every name in
  `EXPECTED`, and `framework/validate.py:340-341` (check [1]) asserts that `EXPECTED`
  equals the set of keys in the config's `agent` object. Registering the agent without
  these three fields leaves the framework profile red with
  `every agent has a resolvable model id: missing: ['ui-designer']`.
  `security-auditor` (`opencode.json:73-106`) is the precedent: an auxiliary agent that is
  outside `framework/models/resolve.py:23` `AGENTS` (the seven lifecycle roles) but still
  carries all three. The model id is therefore pinned to `opencode/big-pickle`, the id
  every other entry uses, and is not profile-driven. Temperature 0.3 matches `researcher`
  (`opencode.json:186-188`), the breadth-first role.
- `edit` default `deny` plus a single `.planning/**` allow confines the agent to design
  artifacts. The plane denies are restated after the allow to satisfy the trailing-deny
  rule (`AGENTS.md`, `framework/security/enforcement_plane.yaml:10`). This mirrors
  `implementer` (`opencode.json:252-275`).
- `task: deny` matches every other subagent (`researcher` `opencode.json:165-167`). Only
  `team-lead` delegates.
- `question` is already globally `allow` (`opencode.json:16`); the headless firewall is a
  contract-level rule, not a permission, so it is enforced by the agent prompt + the
  delegation contract.
- No `tools: { "playwright*": false }` override: rendering the variants is this agent's
  whole job, so Playwright must stay available (contrast `security-auditor`
  `opencode.json:100-102`, which disables it).

## 2. Place the instruction file AND its charter

The agent is two files, not one. `framework/validate.py:2814-2828` (check [30]) requires
every core role to have a portable charter plus a thin pointer to it:

```
.lifecycle/agents/ui-designer.md               <- the charter (portable, single source)
framework/opencode/agents/ui-designer.md       <- thin pointer + OpenCode runtime bindings
```

Copy them from `docs/designer-agent/charter-ui-designer.md` and
`docs/designer-agent/ui-designer.md` respectively. The pointer body must be exactly:

```
Read `.lifecycle/agents/ui-designer.md` and act only within that charter.
```

Both files plus `framework/validate.py` (which adds `ui-designer` to `_ROLES30` and to
`EXPECTED`) are already carried in `docs/designer-agent/ui-designer.patch`, so applying the
patch performs this step.

Existing core agents live at `framework/opencode/agents/` with frontmatter `description` +
`mode` (e.g. `framework/opencode/agents/implementer.md:1-4`); the filename sets the agent
name.

## 3. Verify registration (do not skip)

After both edits, confirm the agent is actually spawnable:

- Restart the OpenCode session so config is re-read.
- Confirm `ui-designer` appears in the available subagents list.
- Spawn it once with a trivial brief and confirm it runs in the foreground and can call
  `question()`.

If it does not appear, the wire-up between a config `agent` entry and the markdown
instruction file differs in this harness from the two documented paths (`.opencode/agents/`
or GSD plugin registration) — see the open item in `docs/DESIGNER_AGENT_DESIGN.md` §10.

## 4. Verify the plane still checks out

`opencode.json` is plane-governed; after editing it, run the enforcement-plane checker and
confirm exit 0:

```bash
python framework/security/check_enforcement_plane.py
```
