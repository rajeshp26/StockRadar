---
name: instinct
description: Instinct-based learning system that captures session lessons as atomic instincts with confidence scoring, stores them project-scoped, and evolves high-confidence clusters into skills, commands, and agents under framework/opencode/skills/. Use when capturing lessons from a session, managing instincts, evolving them into skills, or promoting project instincts to global scope.
metadata:
  version: 2.1.0
  origin: ECC
  port: opencode-instinct 1.0
  provenance: ported from ecc-homunculus continuous-learning-v2 by the fact-check port (see framework/claims ledger CLM-0xx series)
---

# Instinct — Continuous Learning Loop

Turns sessions into reusable knowledge through atomic "instincts" — small learned
behaviors with confidence scoring. Project-scoped: React patterns stay in the React
project, Python conventions stay in the Python project, universal patterns (like
"always validate input") are shared globally.

**Port provenance.** This skill is a port of the ECC `continuous-learning-v2` system
(instinct-cli.py v2.1) into this repository's skill layout, with two porting edits
required by the fact-check: the POSIX-only `fcntl` lock was replaced with a
cross-platform lock (`fcntl.flock` where available, `msvcrt.locking` on Windows,
documented no-op where neither exists), and the deployment target for evolved
artifacts was swapped from `~/.claude/skills` to `framework/opencode/skills/`.

## When to Activate

- Setting up automatic learning from sessions
- Configuring instinct-based behavior extraction
- Tuning confidence thresholds for learned behaviors
- Reviewing, exporting, or importing instinct libraries
- Evolving instincts into full skills, commands, or agents
- Managing project-scoped vs global instincts
- Promoting instincts from project to global scope

## Installed location

This skill is installed at `framework/opencode/skills/instinct/` — skills are loaded by
`name` + `description` frontmatter, so the skill is inert on disk without those
two fields. The behavior engine is `scripts/instinct-cli.py`.

## The Instinct Model

An instinct is a small learned behavior:

```yaml
---
id: prefer-functional-style
trigger: "when writing new functions"
confidence: 0.7
domain: "code-style"
source: "session-observation"
scope: project
project_id: "a1b2c3d4e5f6"
project_name: "my-react-app"
---

# Prefer Functional Style

## Action
Use functional patterns over classes when appropriate.

## Evidence
- Observed 5 instances of functional pattern preference
- User corrected class-based approach to functional on 2025-01-15
```

**Properties:**
- **Atomic** — one trigger, one action
- **Confidence-weighted** — 0.3 = tentative, 0.9 = near certain
- **Domain-tagged** — code-style, testing, git, debugging, workflow, etc.
- **Evidence-backed** — tracks what observations created it
- **Scope-aware** — `project` (default) or `global`

## How It Works

```
Session Activity (in a git repo)
      |
      | observer captures prompts + tool use + project context (git remote / repo path)
      v
projects/<project-hash>/observations.jsonl
      |
      | instinct analysis (background observer or manual)
      v
instincts/ (personal + inherited)          confidence-scored, domain-tagged
      |
      | evolve (clusters related instincts by trigger keyword overlap)
      v
evolved/ (skills, commands, agents)        generated candidates with provenance
      |
      | promote (seen in 2+ projects, confidence >= 0.8)
      v
global/ (instincts + evolved candidates)
```

## Storage

Instinct data lives outside the enforcement plane (`.opencode/`, `framework/`), in
order of precedence:

1. `CLV2_HOMUNCULUS_DIR` when set to an absolute path
2. `$XDG_DATA_HOME/ecc-homunculus`
3. `$HOME/.local/share/ecc-homunculus`

Repository layout under the homunculus root:

```
ecc-homunculus/
|-- instincts/            global personal + inherited instincts
|-- evolved/              global evolved candidates (skills, commands, agents)
|-- observations.jsonl    global observation stream
`-- projects/
    |-- projects.json     registry (id, name, root, remote, last_seen)
    `-- <hash>/           per-project: instincts/, evolved/, observations.jsonl
```

The evolved candidates are generated into the homunculus `evolved/` staging area.
To deploy a generated candidate into the harness, copy it to `framework/opencode/skills/<name>/`
(for skills) or the corresponding command/agent registry — never write to the
enforcement plane from the script itself.

## Commands

| Command | Description |
|---------|-------------|
| `python3 scripts/instinct-cli.py status` | Show all instincts (project-scoped + global) with confidence |
| `python3 scripts/instinct-cli.py import <file>` | Import instincts with scope control |
| `python3 scripts/instinct-cli.py export` | Export instincts (filterable by scope/domain) |
| `python3 scripts/instinct-cli.py evolve [--generate]` | Cluster related instincts into skills/commands, suggest promotions |
| `python3 scripts/instinct-cli.py promote [id]` | Promote project instincts to global scope |
| `python3 scripts/instinct-cli.py projects` | List all known projects and their instinct counts |
| `python3 scripts/instinct-cli.py prune` | Delete pending instincts older than 30 days (TTL) |

## Configuration

Edit `config.json` to control the background observer:

```json
{
  "version": "2.1",
  "observer": {
    "enabled": false,
    "run_interval_minutes": 5,
    "min_observations_to_analyze": 20
  }
}
```

| Key | Default | Description |
|-----|---------|-------------|
| `observer.enabled` | `false` | Enable the background observer agent |
| `observer.run_interval_minutes` | `5` | How often the observer analyzes observations |
| `observer.min_observations_to_analyze` | `20` | Minimum observations before analysis runs |

Other behavior (observation capture, instinct thresholds, project scoping, promotion
criteria) is configured via code defaults in `instinct-cli.py`.

### Observer platform support

The background observer requires WSL2, Linux, or macOS. On native Windows
(Git Bash / MSYS2) it starts and reports success, but the process is killed
when the spawning hook exits and its Job Object closes, so no analysis ever
runs — setting `observer.enabled: true` there is effectively a no-op.

The interactive CLI (`status`/`evolve`/`promote`/`import`/`export`/`prune`) is
cross-platform and is the supported path for this repository (CI host is Windows).

## Verification

- `python3 -m py_compile scripts/instinct-cli.py` — ported script is import-clean.
- `status` with a populated homunculus dir shows project + global instincts.
- Evolved candidates carry provenance (source-instinct ids, avg confidence).