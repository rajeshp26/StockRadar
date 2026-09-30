#!/usr/bin/env python3
"""Shared state access for the verification modules.

Single source for the three scripts that each carried an identical copy of
state-root resolution, so a portability fix lands in one place instead of three.

Three defects lived in that copy, and all three failed SILENTLY:

1. It shelled out to a bare `python3`. The framework README documents that this
   name is not guaranteed to resolve on Windows, and when it did not resolve the
   subprocess died and the handler fell through to the fallback - so state was
   written to the wrong directory with nothing reported anywhere.
2. It addressed gsd_state.py relative to the current working directory. Run
   from anywhere but the repository root the subprocess failed for the same
   reason, landing on the same silent fallback.
3. It returned the adapter's answer verbatim, and that answer is the relative
   string ".planning". Callers append to it and write, so from any other working
   directory state landed in <cwd>/.planning - a second, entirely separate state
   root. The fallback had the same defect, so it could not be distinguished by
   return value alone. Both are now anchored to REPO_ROOT.

Defects 1 and 2 were the subprocess indirection, now replaced by a direct import
of `adapters/gsd_state.root` - the single source every consumer delegates to.
"""
from __future__ import annotations

import sys
from pathlib import Path

# framework/verification/_state.py -> framework/ -> repository root
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    # The verification scripts are runnable from any working directory, so the
    # adapter imports below cannot depend on the caller's sys.path.
    sys.path.insert(0, str(REPO_ROOT))

FALLBACK = REPO_ROOT / ".planning"


def state_root() -> Path:
    """Resolve the GSD state root, or announce the fallback.

    The fallback is reported on stderr. Resolving to a different root than the
    rest of the framework uses - silently - is how state splits across two
    directories and nobody notices until a file is missing.
    """
    try:
        # gsd_state.root() raises SystemExit (not Exception) for an AMBIGUOUS or
        # UNSUPPORTED distribution. That must propagate rather than fall back,
        # so this catch is deliberately not BaseException.
        from framework.adapters.gsd_state import root as _gsd_state_root

        resolved = Path(_gsd_state_root())
        return resolved if resolved.is_absolute() else (REPO_ROOT / resolved).resolve()
    except Exception as exc:  # any failure lands on the fallback; report it
        reason = f"{type(exc).__name__}: {exc}"
    print(
        f"WARNING: could not resolve the GSD state root ({reason}); falling back "
        f"to {FALLBACK}. State may be written to the wrong root.",
        file=sys.stderr,
    )
    return FALLBACK


def atomic_write(path: Path, body: str) -> None:
    """Replace `path` without ever exposing a truncated file to a concurrent reader.

    Reuses the framework's existing implementation (adapters/execute.py:351,
    the T-FX1 lesson) rather than adding a fourth copy of the same dance. The
    import is local so the cost is paid only by callers that actually write.
    """
    from framework.adapters.execute import _atomic_write

    _atomic_write(path, body)


def file_lock(target: Path):
    """Lock a read-modify-write critical section across threads and processes.

    Takes the TARGET and derives the sibling lock file. _file_lock opens exactly
    the path it is handed, so passing the target itself locks the file the
    critical section is about to read, and that read then fails - the mistake is
    silent, it surfaces as a PermissionError inside unrelated code. Every
    adapter caller appends ".lock" by hand (gsd_state.py:290,587,1167); deriving
    it here means no caller can forget.

    Reuses adapters/gsd_state.py:157, which is documented and proven by the
    ext-critique-01 selftest (40 concurrent writers stay gapless). A Windows
    file lock arbitrates processes only, so that implementation layers a
    per-path thread lock underneath; do not hand-roll a weaker one.
    """
    from framework.adapters.gsd_state import _file_lock

    return _file_lock(target.with_name(target.name + ".lock"))
