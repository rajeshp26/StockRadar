# Git runner discipline

Rules for any agent or script that shells out to `git` on behalf of g13-family
workers (oauth, background delegates, verification runs). Ported from the ECC
`worktree-lifecycle` library (`git.js`, `lifecycle.js`);
external-source provenance, not in-repo [VERIFIED] citations. The worktree
adoption itself was not ported — these are the discipline patterns.

## Hermetic git environment

A runner spawning `git` must not inherit ambient git overrides from the caller.
Before the first child invocation, scrub these variables from the environment:

    GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_PREFIX

Leaving them in place redirects every subsequent git command into whatever
repository the caller was operating on — status, diff, and commit targets all
silently point elsewhere. This is the class of bug that produces "clean tree"
reports on a dirty worktree and commits that land in the wrong repository.

## Stdout-empty is an error, not a clean result

Rule: a non-zero exit with empty stdout must be treated as failure, and the
diagnostic read from stderr — never reported as "no output / clean".

When a `git` (or any tool) invocation exits non-zero:

1. If stdout is empty, read stderr for the `fatal:` diagnostic before anything
   else.
2. Never fall back to a legacy path that interprets empty output as success.
3. Never report a clean tree or empty result list from an invocation that did
   not exit 0.

The failure mode this prevents: a failed `git status --porcelain` (e.g. repo
missing, bad env) returns empty stdout, and the caller misreads the empty
string as "no changes". The empty output is a symptom, not a verdict.

## Plan cleanup ladder

When a plan/branch/workspace lifecycle ends, follow the decision ladder — each
route is a decision, never a default:

| State | Action |
| --- | --- |
| `main`/protected branch | skip — never touch |
| merged (no open work) | remove the branch/worktree |
| dirty (uncommitted changes present) | keep — never auto-GC a dirty worktree |
| stale, unmerged work | salvage first: push to a backup ref or bundle, then remove |
| unmerged but active | keep — removal only after explicit disposal |

The two hard rules: a dirty worktree is never garbage-collected, and unmerged
work is never removed without a salvage (push/bundle) step first.

## Validation

A rule is not "followed" because it is written here; it is followed because the
runner's contract enforces it. Before porting any of this discipline into a
runner, read `framework/gates/g13_worker.sh` (the g13 contract) and confirm the
change implements the g13 contract rather than extending it in a fork.