# APPLY — security-audit integration (plane bundle)

**Real `git apply` patches** install the plane half of this change. Apply **either** the
combined patch (one command) **or** the two granular ones — they are byte-identical in effect
(`security-audit.patch` == `install-new-files.patch` + `plane-modifications.patch`).

| Patch | Effect |
|---|---|
| `patches/security-audit.patch` | **combined** — one command, installs all 30 changes |
| `patches/install-new-files.patch` | adds **25 new files** — the vendored `security-audit` skill (21), `agents/security-auditor.md`, `rules/security-audit.md`, `commands/security-audit.md`, `security/sandbox_policy.yaml` |
| `patches/plane-modifications.patch` | modifies **5 existing files** — `opencode.json` (registers the agent) and the four files carrying the dangling `security-research` reference |
| `patches/container-backend.patch` | **incremental only** — adds the container-backend declaration to `security/sandbox_policy.yaml`. Apply this **only** if an earlier revision of this bundle is already in your tree; a fresh apply of `security-audit.patch` already contains it. |
| `patches/skill-integration-matrix.patch` | **additional, unconditional** — adds the `security-auditor` role, the audit artifacts, and the G-SANDBOX/G18 bindings to `framework/opencode/skill-integration-matrix.md`. That file is untouched by the other patches, so apply it after the bundle on any tree. |
| `patches/debt-fixes.patch` | **additional, unconditional** — pays down three pre-existing defects unrelated to this change: completes the truncated sentence in `framework/opencode/rules/definition-of-done.md` (and trims 5 stray trailing blank lines), and in `framework/opencode/skill-integration-matrix.md` replaces the drifting `EXIT_CODES.md:<line>` verdict references with stable row/section anchors and adds the missing G15/G16/G17 rows. |

Applying them is a **human** step: these paths are agent-immutable
(`framework/security/enforcement_plane.yaml`; enforced by the `opencode.json` edit denies), the
same way `sync_enforcement_plane.py` is human-run.

Everything **outside** the plane — `framework/adapters/sandbox.py`, `framework/gates/g_sandbox.sh`,
`framework/gates/g18_security_audit.sh`, their tests, and `docs/**` — is **already implemented and
tested** in this change. Nothing to apply for those.

Each patch was verified by applying it into a throwaway repo and asserting the result
(`APPLY.md` §4). Run every command from the repository root, in WSL bash.

---

## 0. Prerequisites

| Need | Why | Check |
|---|---|---|
| WSL2 | the sandbox is an OS-enforced Linux sandbox | `bash -c 'uname -a'` |
| `bubblewrap`, `socat` | the isolation primitives (native backend) | `bash framework/gates/g_sandbox.sh` → **0** |
| POSIX `node` (≥18) in WSL | the artifact validators need `O_NOFOLLOW`; Windows `node.exe` **cannot** run them | `node --version` |
| **or** Docker / Podman (Linux containers) | the container backend supplies **both** the boundary and the POSIX toolchain, so a fresh host needs no `bubblewrap` and no host `node` | `bash framework/container/build.sh` → **0** |

Provision the audit tier **either** natively (`bubblewrap` + a POSIX `node`, e.g.
`sudo apt-get install -y nodejs`) **or** with the image: `bash framework/container/build.sh`
builds `agentic-lifecycle/sandbox:1` from `framework/container/Dockerfile`, which carries
POSIX `node` ≥18, `python3` and `git`. The probe prefers native and falls back to the
container; with neither, `g18_security_audit.sh` reports exit `3` (UNVERIFIABLE) and the audit
stays source-only — never a pass, never a false fail. See `framework/docs/CONTAINER_TOOLCHAIN.md`.

To use it as the whole dev environment instead, open the repo in the shipped
`.devcontainer/devcontainer.json` (same image).

## 1. Preview (writes nothing)

Combined:
```bash
git apply --stat  framework/docs/security-audit-integration/patches/security-audit.patch
git apply --check framework/docs/security-audit-integration/patches/security-audit.patch
```
Or the two granular patches:
```bash
git apply --check framework/docs/security-audit-integration/patches/install-new-files.patch
git apply --check framework/docs/security-audit-integration/patches/plane-modifications.patch
```

Expect: 25 files created, 5 files changed; `--check` exit `0`.

If a `--check` fails because the worktree drifted, use `git apply --3way` (needs the files
tracked) and resolve the small conflict by hand.

## 2. Apply

Combined (one command):
```bash
git apply framework/docs/security-audit-integration/patches/security-audit.patch
```
Or the two granular patches:
```bash
git apply framework/docs/security-audit-integration/patches/install-new-files.patch
git apply framework/docs/security-audit-integration/patches/plane-modifications.patch
```

The skill files are LF, matching this repo's `.gitattributes` (`* text=auto eol=lf`). The four
`framework/opencode/**` files the second patch touches were already CRLF in the worktree; the
patch preserves them, changing only the one token per file.

### 2.1 Already on an earlier revision?

If `framework/security/sandbox_policy.yaml` already exists **without** a `backends:` block, the
updated new-files patch will not apply (it adds a file that is already there). Apply the
increment instead:

```bash
git apply --check framework/docs/security-audit-integration/patches/container-backend.patch
git apply         framework/docs/security-audit-integration/patches/container-backend.patch   # +28 lines
```

Do **not** apply it after a fresh `security-audit.patch` — that already contains the block.

### 2.2 Always: the skill-integration matrix

`framework/opencode/skill-integration-matrix.md` is not touched by the other patches, so apply
its addition on every tree (fresh or already-bundled):

```bash
git apply --check framework/docs/security-audit-integration/patches/skill-integration-matrix.patch
git apply         framework/docs/security-audit-integration/patches/skill-integration-matrix.patch  # +5 rows
```

This is a CRLF-consistent patch, like the bundle's other `framework/opencode/**` hunks. If your
checkout is LF, apply with `git apply --3way`.

### 2.3 Always: pre-existing debt fixes (apply last)

`patches/debt-fixes.patch` also touches `framework/opencode/skill-integration-matrix.md`, and its
hunk carries the §2.2 rows (G-SANDBOX/G18) as context. It therefore **must be applied after
§2.2**. On a fresh tree the order is:

```bash
git apply framework/docs/security-audit-integration/patches/security-audit.patch
git apply framework/docs/security-audit-integration/patches/skill-integration-matrix.patch
git apply framework/docs/security-audit-integration/patches/debt-fixes.patch
```

It pays down two pre-existing plane defects unrelated to this change:

- `framework/opencode/rules/definition-of-done.md:7` — `Verification is **evidence** ... the exit`
  is truncated mid-sentence (the `code captured, the artifact produced` clause is missing). The
  original wording is **not recoverable** from history: the file was introduced already-truncated
  in `d1947114`. The completion is therefore a **reconstruction** from the framework's own
  phrasing — `framework/opencode/agents/verifier.md:16` ("Every claim you make has an exit code or
  an artifact") and the claim discipline in `framework/opencode/rules/evidence.md`. Five stray
  trailing blank lines are trimmed at the same time. Read the sentence before you apply it.
- `framework/opencode/skill-integration-matrix.md` §5 — the verdict sources cited
  `EXIT_CODES.md:<line>`. The table-row numbers (9-24) still resolved, but every section
  line-range had **already** drifted from the committed file: at `HEAD` the `G6 emits ONLY 0, 1, 3`
  section is at line 30, not the cited 26-31, and the `G-ENTRY` section is at line 194, not the
  cited 161-171. The fix replaces the line numbers with the contract row and section heading,
  which do not drift, and adds the missing G15/G16/G17 rows.

The third defect reported alongside these — a stray shell fragment (`; fi; done; echo ---`) in
`.gitignore` — is **not** a plane file, so it was fixed directly and needs no patch.

## 3. Verify

```bash
python3 framework/security/check_enforcement_plane.py; echo "plane exit=$?"   # expect 0
bash framework/gates/test_g_sandbox.sh;               echo "sandbox exit=$?"  # expect 0
bash framework/gates/test_g18_security_audit.sh;      echo "g18 exit=$?"      # expect 0
bash framework/gates/g_sandbox.sh;                    echo "capability exit=$?"# expect 0
```

Both suites exercise the container backend (pure argv, live probe, live enforcement, and the
`g18` POSIX-node fallback) and **skip those cases cleanly** when no engine/image is present, so
the same commands stay green on a native-only host. To force the container path explicitly:

```bash
python3 framework/adapters/sandbox.py probe --backend container; echo "container probe=$?"  # 0
python3 framework/adapters/sandbox.py run --backend container \
  --target <ro dir> --scratch <rw dir> -- node --version
```

Adding files under already-fenced trees does **not** change the plane list, so
`enforcement_plane.yaml` needs no edit. If you reformatted the top-level / team-lead /
implementer edit blocks, normalise from the canonical YAML first, then re-check:

```bash
python3 framework/security/sync_enforcement_plane.py
python3 framework/security/check_enforcement_plane.py; echo "exit=$?"
```

## 4. Verify the real validators (needs POSIX node)

```bash
AUDIT_RUN_DIR=<run dir with findings.json + coverage-ledger.json> \
  bash framework/gates/g18_security_audit.sh; echo "g18 exit=$?"
```

## 5. Rollback

Combined: `git apply -R framework/docs/security-audit-integration/patches/security-audit.patch`

Otherwise, reverse order:
```bash
git apply -R framework/docs/security-audit-integration/patches/plane-modifications.patch
git apply -R framework/docs/security-audit-integration/patches/install-new-files.patch
python3 framework/security/check_enforcement_plane.py; echo "exit=$?"   # expect 0
```

Nothing in the plane list changed, so no plane edit is needed in either direction.

---

## Provenance

`patches/opencode.agent-security-auditor.json` is the single source for the agent block that
`plane-modifications.patch` inserts into `"agent"`. `patches/skill-routing.edits.md` is the
earlier prose form of the routing changes and is **superseded** by
`plane-modifications.patch` — kept only as a readable summary.
