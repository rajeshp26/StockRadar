# Security-Audit Integration — design + validation record

Status: **non-plane parts implemented and tested; plane wiring staged for apply.**
Scope: adopt the Cloudflare `security-audit` skill (MIT) into this framework and wire it
into the lifecycle so vulnerabilities are hunted **during** development.

> Delivery note. The wiring artifacts (skill, agent, rule, routing, `opencode.json`,
> `framework/security/sandbox_policy.yaml`) live inside the **enforcement plane**
> (`framework/security/enforcement_plane.yaml`), which `opencode.json:22-32` makes
> agent-immutable. They are staged under `docs/security-audit-integration/` with an
> `APPLY.md`; a human applies them. See "Why the plane split" below.

---

## 1. Objective

Catch security flaws in the **design** and **review** phases, not after release, and make
"audit this for vulnerabilities" an explicit, reproducible capability rather than a hope —
without weakening the framework's controls.

## 2. What the skill is, and what the framework is

They are **orthogonal**, and that is why they compose:

| | Cloudflare skill | This framework |
|---|---|---|
| Kind | vulnerability **discovery** domain knowledge | **governance / control plane** |
| Unit | hunting method + report schema | gates, evidence, delegation |
| Output | `findings.json`, `coverage-ledger.json` | verdicts, blockers, provenance |

Shared spine: **evidence over assertion, adversarial independence, fail-closed.** The skill
requires a non-empty `observed_result` for a `confirmed` finding
(`report-schema.json`); the framework already has a claim ledger and `VERIFIED`/`does_not_prove`
provenance. Those are the same rule expressed twice.

## 3. Decisions

- **D-001 — Design time is threat modeling, not auditing.** There is no source to trace at
  design time, so a `confirmed` finding is impossible. Design time feeds the *taxonomy*
  (attack classes) into the existing `PLAN.md` `<threat_model>` STRIDE register. No audit
  workflow runs here.
- **D-002 — Review time is a scoped audit of the diff, on security-sensitive impact only.**
  Triggered when the change touches a trust boundary, auth, a contract, or data handling.
  Run by a **fresh agent that is not the implementer** (adversarial independence).
- **D-003 — Execution is a gated host capability.** Target code runs only inside an
  OS-enforced sandbox, or not at all. Backend selected and proven: WSL2 + bubblewrap +
  `systemd-run --user` cgroups + rlimits/timeout. Fail-closed to **source-only** when
  unenforceable.
- **D-004 — A confirmed high/critical finding blocks completion** via G18, in the same shape
  G7/G8 already use.

Three trigger points: **design** (taxonomy → threat model), **review** (scoped audit on
security-sensitive impact), **on demand** (`/security-audit`).

## 4. Architecture

### 4.1 Components

| Component | Plane? | Location | Role |
|---|---|---|---|
| `security-audit` skill | yes | `framework/opencode/skills/security-audit/` | hunting method + validators (vendored, MIT) |
| `security-auditor` agent | yes | `framework/opencode/agents/security-auditor.md` | the hunter/verifier; not the implementer |
| `security-audit` rule | yes | `framework/opencode/rules/security-audit.md` | when the skill is (and is not) invoked |
| `/security-audit` command | yes | `framework/opencode/commands/security-audit.md` | explicit on-demand entry point |
| routing | yes | `framework/opencode/skill-routing.md` | replaces the dangling `security-research` |
| sandbox launcher | **no** | `framework/adapters/sandbox.py` | probes + runs commands in the sandbox |
| sandbox readiness gate | **no** | `framework/gates/g_sandbox.sh` | refuses execution unless enforceable |
| audit-artifact gate | **no** | `framework/gates/g18_security_audit.sh` | validates artifacts; blocks on confirmed high/critical |
| sandbox policy | yes | `framework/security/sandbox_policy.yaml` | declared controls + limits |
| agent permissions | yes | `opencode.json` | the `security-auditor` block |

### 4.2 Data flow

```
                 ┌── design ─────────────────────────────────────────────┐
 taxonomy ──────►│ attack classes → PLAN.md <threat_model> (STRIDE)       │  (no execution)
                 └───────────────────────────────────────────────────────┘

                 ┌── review (security-sensitive impact only) ────────────┐
 diff ──────────►│ team-lead (sole delegator) ──► security-auditor        │
                 │                                      │                │
                 │                     g_sandbox.sh ────┤ (capability)   │
                 │                                      ▼                │
                 │            sandbox.py run  ──►  target under test      │
                 │                                      │                │
                 │                findings.json + coverage-ledger.json   │
                 │                                      ▼                │
                 │              g18_security_audit.sh ──► pass / BLOCK   │
                 └───────────────────────────────────────────────────────┘
```

### 4.3 The sandbox as a declared host capability

Modelled the same way `framework/adapters/host.py` reports capability — **it reports, it does
not grant**. `sandbox.py probe` measures, and classifies a failure into exactly one of:

- **`missing`** — a required capability is absent (no bubblewrap, no user namespaces, not
  Linux). Execution is **refused**; the audit degrades to source-only. →
  `g_sandbox.sh` exit **3**.
- **`violation`** — a control failed *when attempted* (e.g. the target was writable, or
  egress succeeded). Isolation is broken. → `g_sandbox.sh` exit **1**.
- **skipped / unjudged** — a required control was not evaluated. **Never a pass.**

Native-backend probe controls: `bwrap`, `userns` (unprivileged user+mount+net+pid),
`bwrap_start`, `fs_ro_scratch_rw`, `net_isolation`, `env_allowlist` (required); `socat`,
`cgroup_user` (optional).

### 4.4 Two enforcement backends, and one of them supplies the toolchain

`probe()` tries **native** (bubblewrap) first and falls back to **container**. A host with
neither is unenforceable and execution is refused. The container is not a nested sandbox — it
*is* the boundary: `--network=none --read-only --cap-drop=ALL --security-opt no-new-privileges`
plus bounded pids/memory/fsize. Because Docker cannot unset an image's own `ENV`, the target
starts under `env -i` with only the allowlist — the container's `--clearenv`. Its probe
controls are `container_engine`, `container_image`, `container_start`, `container_binds`,
`fs_ro_scratch_rw`, `net_isolation`, `env_allowlist`.

The same image is also the **toolchain provider**: it carries POSIX `node` >=18, `python3` and
`git`, so a fresh project gets what the audit tier needs by building one image instead of
provisioning the host. `g18` uses it to obtain a POSIX `node` when the host's `node.exe`
cannot judge (no `O_NOFOLLOW`). That is the portable answer to "how are the native
dependencies provisioned" — see `framework/docs/CONTAINER_TOOLCHAIN.md`.

## 5. Exit-code contracts (new gates)

Per `framework/gates/EXIT_CODES.md` semantics, and each gate documents its own contract in
its header.

**`g_sandbox.sh`** (readiness pre-flight): `0` enforceable via the chosen backend / `1`
isolation violated / `2` BLOCKED (python3 or probe unreadable) / `3` capability missing
(neither bubblewrap/user-namespaces nor a usable container) / `4` NOT_APPLICABLE
(`SANDBOX_EXEC_REQUIRED=0`).

**`g18_security_audit.sh`** (artifact gate): `0` valid + no open confirmed high/critical /
`1` invalid artifacts, or an open confirmed high/critical / `2` BLOCKED (run dir or artifact
missing) / `3` UNVERIFIABLE (validators absent, or no interpreter could judge — native node
lacks POSIX `O_NOFOLLOW`, and the container is unavailable) / `4` NOT_APPLICABLE (no audit run).

## 6. Validation record

### 6.1 Sandbox feasibility (POC)

`framework/experiments/sandbox-poc/probe.sh` → **VERDICT: ENFORCEABLE, exit 0**, 14/14 probes.
Evidence persisted: `framework/experiments/sandbox-poc/RESULT.txt`, `RESULT.json`.
Host: Windows + WSL2, `Linux 6.6.x-microsoft-standard`, non-root `uid=1000`,
bubblewrap 0.9.0, socat 1.8.0.0. `userns_full` passed — the unshare-EPERM risk did **not**
materialise on this host.

### 6.2 Sandbox capability + gate

`bash framework/gates/test_g_sandbox.sh` → **PASS**. Covers: pure argv construction (read-only
target, read-write scratch, `--unshare-net`, `--unshare-pid`, `--clearenv`, allowlisted env);
the readiness probe reporting ENFORCEABLE; **real** enforcement (`READ_OK`,
`WRITE_SCRATCH_OK`, `TARGET_READONLY`, `ENV_CLEAR`, no `TARGET_WRITABLE`); external egress
blocked; `g_sandbox.sh` exit `0` when enforceable and `4` under `SANDBOX_EXEC_REQUIRED=0`.
The container backend is covered the same way: pure argv invariants
(`--network=none`/`--read-only`/`--cap-drop=ALL`/`no-new-privileges`/`--pids-limit`/`env -i`),
a live `probe --backend container` reporting ENFORCEABLE, and live enforcement
(`READ_OK`, `WRITE_SCRATCH_OK`, `TARGET_READONLY`, `ENV_CLEAR`). The live container checks
skip cleanly when no engine/image is present.

### 6.3 Audit-artifact gate

`bash framework/gates/test_g18_security_audit.sh` → **PASS** (14 cases). Covers the full exit
contract (4/2/2/2/3/3/0/1/1/1/0/1) including `needs_validation` critical is **not** a
confirmed finding (pass) and a confirmed high among many still blocks, plus the **container
fallback**: with every native interpreter shadowed by one that refuses input protection, the
container's POSIX `node` judges valid artifacts (exit `0`) and refuses completion on a
confirmed high (exit `1`).

### 6.4 The vendored validators

The skill's own `node:test` suites were run against the clone. Direct-call tests pass; the
**CLI-path** tests fail on Windows `node.exe` with `OS no-follow and nonblocking input
protection is unavailable` — Windows lacks `O_NOFOLLOW`. **This is an interpreter limitation,
not a schema failure**, and it is load-bearing: it is why `g18` maps a non-POSIX interpreter
to exit **3**, never a false FAIL.

The container **resolves** that limitation: run with the sandbox image as the interpreter, the
same validators judge normally. Verified on this host (repo-side run dir, real vendored
validators): `[]` → exit `0`; a malformed or schema-incomplete artifact → exit `1`; with
`SANDBOX_ALLOW_CONTAINER=0` the same inputs return exit `3`. So `g18` now reaches a real
verdict where it previously could only report UNVERIFIABLE.

## 7. Why the plane split

`framework/opencode/**`, `framework/security/**`, `opencode.json`, `AGENTS.md`,
`.opencode/**`, `framework/plan/**`, `framework/testing/**` are agent-immutable
(`enforcement_plane.yaml`; enforced by `opencode.json` edit denies). The audit wiring lands
inside those trees, so an agent may not write it. The plane *list* needs no change — the
target trees are already fenced — but the *files* do, and that is a human step, exactly as
`sync_enforcement_plane.py` is.

Non-plane (agent-writable, implemented here): `framework/adapters/sandbox.py`,
`framework/gates/g_sandbox.sh`, `framework/gates/g18_security_audit.sh`, their tests,
`framework/container/**`, `.devcontainer/**`, and `docs/**`.

## 8. Known limitations / follow-ups

1. **POSIX node is a prerequisite for audit-artifact validation — now provisioned by the
   container.** Windows `node.exe` cannot run the validators (no `O_NOFOLLOW`). The sandbox
   image supplies a POSIX `node`, so `g18` reaches a real verdict where it previously could
   only report exit `3`. A host with neither a POSIX `node` nor a usable container still
   reports exit `3` — never a pass, never a false fail.
2. **The promotion step is specified, not yet built.** The POC proved the *primitives*
   (bind/namespace/limit enforcement). The discipline that promotes a finding from
   `needs_validation` to `confirmed` (race-safe, no-follow) is the skill's own workflow.
3. **`sandbox.py run` uses rlimits + wall-clock timeout**; cgroup memory/pids limits via
   `systemd-run --user` are wired for `--mem-mb`/`--pids` and the probe confirms the
   capability, but the default path is rlimits.
4. **Incidental, pre-existing, unverified:** `framework.config.json` is referenced by
   `enforcement_plane.yaml:24-25`, the AGENTS.md fence, and `opencode.json:27` but does not
   exist; `framework/opencode/rules/definition-of-done.md:7` is truncated mid-sentence.

## 9. Apply

See `framework/docs/security-audit-integration/APPLY.md`.
