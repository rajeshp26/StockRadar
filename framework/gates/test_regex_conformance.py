#!/usr/bin/env python3
"""Conformance test for the canonical [gate] line protocol.

WHY THIS EXISTS
    The parser change lives in .opencode/plugin/gates.mjs, whose suite
    (gates.test.mjs) requires node. Node is absent in this environment
    (verified: Test-Path "C:\\Program Files\\nodejs\\node.exe" -> False), so
    that suite cannot execute here. An unrunnable test is not evidence.

    This transliterates GATE_LINE_RE into Python's `re` -- faithfully, with no
    simplification -- and exercises it against lines captured from the REAL
    staged framework/gates/_lib.sh. That proves the property that actually
    matters and that hand-written fixtures would miss: the emitter and the
    parser agree on the wire format.

FALSIFIABILITY
    Two independent directions, both must hold:

      1. NEGATIVE (old parser). The pre-patch regex REJECTS every classified
         line the patched emitter produces. If the old regex accepted them,
         the parser patch would be unnecessary and this test fails.
      2. POSITIVE (new parser). The post-patch regex ACCEPTS them and recovers
         the evidence field.

    A test that only asserted (2) would pass even if the emitter and parser had
    both drifted together into a mutually-inconsistent private format.

SCOPE LIMIT -- read before treating this as a pass
    This proves the wire format, not the JavaScript. Specifically NOT proven:
      - that gates.mjs behaves identically to this transliteration (JS RegExp
        and Python re agree on these constructs -- no lookbehind, no unicode
        property classes -- but they are different engines);
      - that gates.test.mjs passes, which needs node;
      - that telemetry.ts propagates evidence onward, which it currently does
        not (parseGateResult builds detail without it).
    Therefore the parser patch is UNVERIFIABLE (exit 3) in this environment,
    not verified. This test raises confidence in the format; it does not close
    the requirement.

Exit: 0 = format conforms, 1 = conformance violated, 2 = harness error
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))


def resolve_gates_dir():
    """Locate framework/gates. GATES_DIR wins; otherwise walk up to the repo root.

    Walk-up rather than a fixed relative path so this file runs identically from
    .planning/patches/ (staging) and from framework/gates/ (shipped).
    """
    env = os.environ.get("GATES_DIR")
    if env:
        return env
    probe = HERE
    while probe and probe != os.path.dirname(probe):
        candidate = os.path.join(probe, "framework", "gates")
        if os.path.isfile(os.path.join(candidate, "_lib.sh")):
            return candidate
        probe = os.path.dirname(probe)
    return os.path.join(HERE, "framework", "gates")


LIB = os.path.join(resolve_gates_dir(), "_lib.sh")

# Transliteration of the PRE-patch regex (.opencode/plugin/gates.mjs:73).
OLD_RE = re.compile(
    r"^\[gate\]\s+([A-Za-z0-9_-]+)\s+"
    r"result=(pass|fail|unverifiable|not_reached|started)"
    r"(?:\s+exit=(\d+))?(?:\s+ms=(\d+))?$",
    re.M,
)

# Transliteration of the POST-patch regex. Group 5 (evidence) is new; the
# three classified tokens are new; everything else is byte-identical.
NEW_RE = re.compile(
    r"^\[gate\]\s+([A-Za-z0-9_-]+)\s+"
    r"result=(pass|fail|unverifiable|not_applicable|precondition_missing|"
    r"capability_missing|not_reached|started)"
    r"(?:\s+exit=(\d+))?(?:\s+ms=(\d+))?(?:\s+evidence=(.+))?$",
    re.M,
)

CLASSIFIED = {"not_applicable", "precondition_missing", "capability_missing"}

# message, evidence, expected exit -- mirrors the wrappers in the staged _lib.sh
CASES = [
    ("not_applicable", "no changed source files", '{"changed_source_files": 0}', 4),
    (
        "precondition_missing",
        "changed files exist but no plan context",
        '{"SCOPE_PLAN": null, "changed_source_files": 207}',
        2,
    ),
    ("capability_missing", "playwright absent", '{"required_tool": "playwright"}', 3),
    ("unverifiable", "evidence not produced", '{"attempted": "chromium launch"}', 3),
]

# TRANSPORT, measured on this host rather than assumed. `shutil.which("bash")`
# resolves to C:\Windows\system32\bash.EXE -- WSL bash (uname=Linux, cwd reported
# as /mnt/c/...), NOT Git Bash. Two interop facts follow, both measured:
#
#   1. `bash -c '<script>' name args...` DROPS the [name [args...]] tail across the
#      Win32->WSL boundary, so "$1"/"$@" arrive EMPTY. The old harness relied on
#      exactly that shape, so `. "$1"` failed and every case reported rc=127
#      "command not found" -- a FAILURE OF THE GATE UNDER TEST rather than a
#      broken harness, which is the wrong direction for a diagnostic.
#      Measured: bash -c 'echo "[$1] $#"' _ A B   =>   [] 0
#   2. A WSL child receives NO inherited variable that is not NAMED in WSLENV.
#      Measured: env={GATE_*=...} alone arrives with all four empty; the same env
#      plus "WSLENV=GATE_LIB:..." arrives intact, including JSON whose value
#      contains double quotes and spaces.
#
# Facts 1 and 2 reproduce with `python .planning/patches/probe_transport.py`
# (run from the repo root; it prints the same matrix as this comment).
# A third constraint, measured by probe_path.py: a forward-slash WINDOWS path is
# rejected both as argv and as a WSLENV-delivered value (`C:/.../x.sh: No such
# file or directory`), which is why the library is sourced by bare name from cwd
# rather than passed as an absolute path.
#
# Hence: the payload goes on STDIN (`bash -s`, so there is no argv tail to lose),
# the library is sourced by BARE NAME from cwd (so there is no path to translate),
# and the values ride in WSLENV-listed variables. Every one of these is already
# correct on POSIX -- `bash -s` reads stdin, variables are inherited natively,
# WSLENV is inert -- so no dialect is hard-coded and this is not a WSL fix that
# breaks Git Bash or the reverse.
_EMIT_RUNNER = '. _lib.sh\n"$GATE_WRAPPER" "$GATE_MESSAGE" "$GATE_EVIDENCE"\n'


def emit(wrapper, message, evidence):
    """Capture the real [gate] line the staged _lib.sh produces for this verdict.

    Arguments are passed as positional parameters rather than interpolated into
    the script text: the evidence is JSON containing double quotes, and building
    the command by concatenation would terminate the shell quoting.

    Returns (line, diagnostic). The diagnostic carries stderr and the exit code
    so a failed capture reports WHY instead of printing "no line" -- a silent
    empty result is indistinguishable from a real absence, which is the exact
    confusion this repair exists to eliminate.
    """
    env = {
        **os.environ,
        "GATE_NAME": "g_conformance",
        "GATE_WRAPPER": wrapper,
        "GATE_MESSAGE": message,
        "GATE_EVIDENCE": evidence,
    }
    # WSL interop forwards ONLY the variables NAMED in WSLENV; anything else
    # passed in env= is dropped at the Win32->WSL boundary (measured: all four
    # arrive empty without this, intact with it). An inherited WSLENV is
    # preserved rather than clobbered. Inert on POSIX, where variables are
    # inherited natively, so this costs nothing off Windows.
    env["WSLENV"] = ":".join(
        filter(None, [env.get("WSLENV"), "GATE_NAME", "GATE_WRAPPER",
                      "GATE_MESSAGE", "GATE_EVIDENCE"])
    )
    proc = subprocess.run(
        [shutil.which("bash") or "bash", "-s"],
        input=_EMIT_RUNNER.encode("utf-8"),
        cwd=os.path.dirname(LIB),
        capture_output=True,
        # bytes, NOT text=True: measured, text=True delivers the payload as ONE
        # line with a literal backslash-n, so bash reports `_lib.sh\n` as a
        # filename and fails. The identical bytes with text=False run correctly.
        text=False,
        env=env,
    )
    # Decoded explicitly because the transport above is bytes. "replace" keeps a
    # malformed byte from turning a diagnostic into a second, louder failure.
    out = proc.stdout.decode("utf-8", "replace")
    err = proc.stderr.decode("utf-8", "replace")
    for line in out.splitlines():
        if line.startswith("[gate] "):
            return line, ""
    return None, "rc=%s stdout=%r stderr=%r" % (proc.returncode, out.strip(), err.strip()[:400])


def parse(line):
    """Mirror of the patched parseGateLine, including the evidence refusal."""
    m = NEW_RE.search(line)
    if not m:
        return None
    if m.group(2) in CLASSIFIED and m.group(5) is None:
        return None
    out = {
        "name": m.group(1),
        "result": m.group(2),
        "exit": int(m.group(3)) if m.group(3) is not None else None,
        "ms": int(m.group(4)) if m.group(4) is not None else None,
    }
    if m.group(5) is not None:
        out["evidence"] = m.group(5)
    return out


def main():
    if not os.path.isfile(LIB):
        sys.stderr.write("HARNESS ERROR: _lib.sh not found at %s\n" % LIB)
        return 2

    failed = 0

    print("== C1: real emitted classified lines are REJECTED by the old parser ==")
    for wrapper, message, evidence, _ in CASES:
        line, why = emit(wrapper, message, evidence)
        if line is None:
            print("FAIL C1 %s: staged _lib.sh emitted no [gate] line (%s)" % (wrapper, why))
            failed = 1
            continue
        if OLD_RE.search(line):
            print("FAIL C1 %s: old parser already accepts %r" % (wrapper, line))
            failed = 1
        else:
            print("ok   C1 %s rejected by old parser (patch is necessary)" % wrapper)

    print("\n== C2: the new parser ACCEPTS them and recovers evidence + exit ==")
    for wrapper, message, evidence, exit_code in CASES:
        line, why = emit(wrapper, message, evidence)
        if line is None:
            print("FAIL C2 %s: staged _lib.sh emitted no [gate] line (%s)" % (wrapper, why))
            failed = 1
            continue
        parsed = parse(line)
        if parsed is None:
            print("FAIL C2 %s: new parser refused a well-formed line %r" % (wrapper, line))
            failed = 1
            continue
        problems = []
        if parsed["result"] != wrapper:
            problems.append("result %r != %r" % (parsed["result"], wrapper))
        if parsed["exit"] != exit_code:
            problems.append("exit %r != %r" % (parsed["exit"], exit_code))
        if parsed.get("evidence") != evidence:
            problems.append("evidence %r != %r" % (parsed.get("evidence"), evidence))
        if problems:
            print("FAIL C2 %s: %s" % (wrapper, "; ".join(problems)))
            failed = 1
        else:
            print("ok   C2 %s exit=%s evidence recovered" % (wrapper, exit_code))

    print("\n== C3: a classified verdict stripped of evidence is REFUSED ==")
    for wrapper in sorted(CLASSIFIED):
        parsed = parse("[gate] g9 result=%s exit=4 ms=7" % wrapper)
        if parsed is not None:
            print("FAIL C3 %s: bare classified verdict was accepted" % wrapper)
            failed = 1
        else:
            print("ok   C3 %s refused without evidence -> UNOBSERVED" % wrapper)

    print("\n== C4: pre-existing verdict shapes are unchanged ==")
    legacy = {
        "[gate] g8 result=pass exit=0 ms=123": ("pass", 0, 123),
        "[gate] g2 result=fail exit=1 ms=45": ("fail", 1, 45),
        "[gate] g6 result=unverifiable exit=3 ms=0": ("unverifiable", 3, 0),
    }
    for line, (result, exit_code, ms) in legacy.items():
        parsed = parse(line)
        if parsed is None:
            print("FAIL C4: new parser broke a pre-existing line %r" % line)
            failed = 1
            continue
        if "evidence" in parsed:
            print("FAIL C4: evidence key appeared on a line without evidence: %r" % line)
            failed = 1
            continue
        if parsed["result"] != result or parsed["exit"] != exit_code or parsed["ms"] != ms:
            print("FAIL C4: mis-parsed %r -> %r" % (line, parsed))
            failed = 1
        else:
            print("ok   C4 %s keeps its four-key shape" % result)

    parsed = parse("[gate] g3 result=not_reached")
    if parsed is None or parsed["result"] != "not_reached" or "evidence" in parsed:
        print("FAIL C4: not_reached disposal line mis-parsed -> %r" % (parsed,))
        failed = 1
    else:
        print("ok   C4 not_reached disposal line needs no evidence")

    print("")
    if failed:
        print("FAIL: canonical-line conformance violated.")
        return 1
    print("PASS: canonical-line format conforms.")
    print("NOTE: proves the wire format only -- gates.test.mjs still requires node.")
    return 0


if __name__ == "__main__":
    sys.exit(main())