# LEDGER PERFORMANCE LANDING KIT

Produced 2026-09-20 by the analysis phase (post-compaction continuation).
Every OLD block below was re-verified verbatim against the current files in this run — none is
reconstructed from memory. New files (gates g11/g14/g16) are provided as complete contents.

**Application gate:** `framework/**`, `.opencode/**`, `opencode.json`, `AGENTS.md` are the
enforcement plane — no agent may edit them. This kit is therefore a hand-apply document for a
human (or an approved release process). Apply in the order of section 2, then run section 4.

---

## 0. Five-Whys recap — why this kit exists

The triggering symptom was a season of slow dispatch/supervision runs. The analysis collapsed
to one defect class: **unbounded-growth read paths in state readers**, reached along five steps:

1. **Why slow?** Every framework state read re-parsed whole files: the claim-ledger scan inside
   each `append`, the full event-stream parse inside each `task-event`, and the whole live
   telemetry file on every report/rollup run.
2. **Why whole-file reads?** The three hot paths were designed as "authoritative full reads":
   `_next_claim_id(load())` for highest-number continuation, `len(_task_events(...)) + 1` for the
   event seq, and read-all/rewrite-all for telemetry aggregation.
3. **Why those designs?** They predate delegated-task supervision, heartbeat telemetry, and the
   claim ledger as hot paths — legacy decisions from when counts were small and writes rare.
4. **Why did nothing re-examine them?** No gate or metric watched *read amplification*;
   telemetry watched content (unfinalized sessions, anomalies), not per-read cost, and each site
   looked fine in isolation.
5. **Why fix now?** Seasonal growth (tasks × events × claims × heartbeats) turned the fixed
   overheads into quadratic reads sitting on the dispatch/supervision/proof path — the exact
   path G11/G14, `task-event`, and `report.py` stand on.

The seven items below land the O(1) primitives that bound or eliminate those reads.

---

## 1. Behavior-change notes (accept each consciously)

| # | Change | Who is affected |
|---|---|---|
| B1 | `CLM-NNN` sequential ids → `CLM-<20-digit ns-epoch>`. Still monotonically increasing integers; anything that parses `claim_id` numerically is unaffected. Anything matching `^CLM-\d{3}$` is not. | claim consumers, README updated |
| B2 | After a task reaches `COMPLETED` or `CANCELLED`, its event stream is coalesced **in place** to the last 3 lines. History of a terminal task is no longer readable. `FAILED`/`LOST` streams are **never** compacted (retry/audit trail). | supervisors, watchers reading full histories |
| B3 | `GSD_STATE_ROOT` env is now honored by `ledger._state_root()` when it names an **absolute** path (drive-letter `X:` or `/`-anchored). A bare `.planning` is never an override. `gsd_state.py` still resolves via its probe/cwd — the two agree whenever the env equals the cwd-resolved root. | build boxes, test harnesses |
| B4 | Live telemetry rotates to `telemetry/archive/records-<UTCstamp>.jsonl` at 16 MiB. `report.py` now reads archive segments + live tail; a consumer reading **only** `records.jsonl` no longer sees full history. | anyone reading telemetry directly |
| B5 | `rollup` rewrites the live telemetry file atomically (staged temp + `os.replace`) instead of truncating in place. | concurrent readers (telemetry plugin, report.py) |
| B6 | New adapter command `state-health` + new gate **G16** (`g16_state_health.sh`), on the `functional` profile and in EXIT_CODES. Judgment: task contract + event-tail readability and claim-ledger tail parseability; empty store → NOT_APPLICABLE (4). | release-gate runners |
| B7 | `task_event`/`cancel_task` on a corrupt stream tail raise `TASK_BLOCKED` (same guard the full read enforced); seq numbering is read from the stream tail (O(1)) instead of a full parse. | same as before, just faster |

Non-changes (deliberately left alone): `ledger.py load()` stays as a public convenience reader
(it is no longer called by `append`); g14's EXIT_CODES row text (machine-checked literal) is
untouched; FAILED/LOST compaction is not implemented.

---

## 2. Application order (dependency-sorted)

1. `framework/claims/ledger.py` — H1..H4 (stateless ids, env root)
2. `framework/adapters/gsd_state.py` — H5..H9 (tail seq, compaction, rotation, state-health)
3. `framework/adapters/control.py` — C1..C2 (atomic rollup rewrite)
4. `framework/telemetry/report.py` — R1..R2 (team reads: archive + live)
5. Gates — G11 replacement, G14 replacement, **new** G16 (complete files)
6. Wiring — EXIT_CODES.md row, `profiles.yaml` membership, `validate.py` block [35]
7. Tests + docs — `test_ledger_rules.py` additions, `framework/claims/README.md` doc hunks

**Line endings are part of the contract.** The assembled bash gates (`g11_evidence.sh`,
`g14_integrity.sh`, the new `g16_state_health.sh`) are not CRLF-tolerant: a Windows
text-mode write that emits `\r\n` breaks `. _lib.sh` sourcing and the `case` verdict
(`$'\r': command not found`, `_lib.sh\r: No such file or directory`). Write every hunk
with LF only — paste tools that normalize newlines, or editors with "smart" newline
handling, must be configured off. Verified by the assembled behavioral smoke (see section 6).

---

## 3. The hunks

### H1 `framework/claims/ledger.py` — imports (lines 14-15)

OLD:
```python
from __future__ import annotations
import argparse, json, re, subprocess, sys
```
NEW:
```python
from __future__ import annotations
import argparse, json, os, re, subprocess, sys, time
```

### H2 `framework/claims/ledger.py` — `_state_root()` (lines 37-46)

OLD:
```python
def _state_root() -> Path:
    """Resolve the GSD state root exactly the way the rest of the framework does."""
    try:
        r = subprocess.run(["python3", "framework/adapters/gsd_state.py", "state-root"],
                           capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip())
    except Exception:
        pass
    return Path(".planning")
```
NEW:
```python
def _state_root() -> Path:
    """Resolve the GSD state root exactly the way the rest of the framework does.

    Priority: GSD_STATE_ROOT when it names an explicit path (drive-letter or
    root-anchored) -- a bare ".planning" is never an override. Without the env,
    behavior is unchanged: the adapter probe, then .planning. A caller that pins
    the env removes a subprocess-per-call from the ledger's hot path; the probe
    stays as the framework's single source of truth for the fallback.
    """
    env = os.environ.get("GSD_STATE_ROOT")
    if env and (len(env) >= 2 and env[1] == ":" or env.startswith("/")):
        return Path(env)
    try:
        r = subprocess.run(["python3", "framework/adapters/gsd_state.py", "state-root"],
                           capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip())
    except Exception:
        pass
    return Path(".planning")
```

### H3 `framework/claims/ledger.py` — stateless id (lines 361-371)

OLD:
```python
def _next_claim_id(records: list[dict]) -> str:
    """CLM-NNN continuing the highest existing number across ALL records."""
    highest = 0
    for r in records:
        cid = str(r.get("claim_id") or "")
        if cid.startswith("CLM-"):
            try:
                highest = max(highest, int(cid[4:]))
            except ValueError:
                continue
    return f"CLM-{highest + 1:03d}"
```
NEW:
```python
_last_claim_ns = 0


def _next_claim_id() -> str:
    """CLM-<20-digit ns-epoch> -- stateless, no ledger scan.

    The old id continued the highest number across ALL records, so every append
    re-read the whole ledger and the scan grew with the store (the quadratic hot
    path this change removes). A wall-clock-ns id is unique without any scan;
    _last_claim_ns keeps it strictly monotonic even across an NTP step back.
    ns-epoch is ~1.8e18 in 2026, safely under int64's 9.2e18; uniqueness does
    not rely on the file -- one process is fenced by the monotonic guard and
    cross-process ns collisions are a one-in-a-trillion race the atomic per-line
    append serialises past anyway.
    """
    global _last_claim_ns
    ns = time.time_ns()
    if ns <= _last_claim_ns:
        ns = _last_claim_ns + 1
    _last_claim_ns = ns
    return f"CLM-{ns:020d}"
```

### H4 `framework/claims/ledger.py` — `append()` (lines 375-376)

OLD:
```python
    if "claim_id" not in entry:
        entry["claim_id"] = _next_claim_id(load())
```
NEW:
```python
    if "claim_id" not in entry:
        entry["claim_id"] = _next_claim_id()
```
Note: `load()` (line 101) becomes a convenience reader with no internal callers — kept.

### H5 `framework/adapters/gsd_state.py` — `_append_task_event` rewrite (lines 481-488)

OLD:
```python
def _append_task_event(task_id: str, event: dict):
    p = _task_events_path(task_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Per-task monotonic sequence number: the event-bus ordering guarantee the
    # supervisor and watchdog rely on. Corrupt streams must block before growing.
    event["seq"] = len(_task_events(task_id)) + 1
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")
```
NEW:
```python
TAIL_READ_BYTES = 1 << 16  # 64 KiB: bounded tail read for seq/status without a full-stream scan


def _last_seq(task_id: str) -> int:
    """Sequence of the latest event, read from the stream tail alone (O(1) not O(n)).

    _task_events() parses the entire stream; calling it on every append makes a
    long task quadratic (each write re-reads everything written before). The
    stream is append-only, so the last line always carries the seq, and a bounded
    tail read is exact. A file with no terminator (torn write) is corrupt -- the
    same guard _task_events enforced -- and a missing file yields 0.
    """
    p = _task_events_path(task_id)
    if not p.exists() or p.stat().st_size == 0:
        return 0
    with p.open("rb") as fh:
        fh.seek(max(0, p.stat().st_size - TAIL_READ_BYTES))
        tail = fh.read()
    if not tail.endswith(b"\n"):
        raise SystemExit(f"TASK_BLOCKED: event stream for {task_id} corrupt (torn tail)")
    lines = [ln for ln in tail.splitlines() if ln.strip()]
    if not lines:
        return 0
    try:
        return int(json.loads(lines[-1]).get("seq") or 0)
    except (json.JSONDecodeError, ValueError):
        raise SystemExit(f"TASK_BLOCKED: event stream for {task_id} corrupt at tail")


def _append_task_event(task_id: str, event: dict):
    p = _task_events_path(task_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Per-task monotonic sequence number: the event-bus ordering guarantee the
    # supervisor and watchdog rely on. Corrupt streams must block before growing.
    event["seq"] = _last_seq(task_id) + 1
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")
```

### H6 `framework/adapters/gsd_state.py` — COMPLETED trigger in `task_event` (lines 745-746)

OLD:
```python
    _append_task_event(task_id, event)
    return task_status(task_id)
```
NEW:
```python
    _append_task_event(task_id, event)
    if state == "COMPLETED":
        # Terminal outcome: only last-event readers consume the stream from here
        # on; the full pre-terminal history has no consumer on a completed task.
        _compact_terminal_stream(task_id)
    return task_status(task_id)
```

### H7 `framework/adapters/gsd_state.py` — CANCELLED trigger in `cancel_task` (lines 758-763)

OLD:
```python
    _append_task_event(task_id, {
        "state": "CANCELLED",
        "ts": _now(),
        "emitter": str(payload.get("emitter") or "team-lead"),
    })
    return task_status(task_id)
```
NEW:
```python
    _append_task_event(task_id, {
        "state": "CANCELLED",
        "ts": _now(),
        "emitter": str(payload.get("emitter") or "team-lead"),
    })
    _compact_terminal_stream(task_id)
    return task_status(task_id)
```

### H8 `framework/adapters/gsd_state.py` — rotation + compaction + state-health (lines 1014-1015)

OLD:
```python
def write_telemetry(payload: str) -> str:
    return _write("telemetry/records.jsonl", payload.strip() + "\n", append=True)
```
NEW:
```python
def write_telemetry(payload: str) -> str:
    _rotate_telemetry()
    return _write("telemetry/records.jsonl", payload.strip() + "\n", append=True)


TELEMETRY_ROTATE_BYTES = 16 * 1024 * 1024  # 16 MiB: keep the live file a bounded working set


def _rotate_telemetry():
    """Move the live telemetry file into archive/ once it outgrows the budget.

    write_telemetry appends every heartbeat; rollup and report.py re-read the
    live file whole on every run, so an unbounded live file is a growing hot
    path. Rotation is atomic (os.replace, same volume) and best-effort: a failed
    rotation must never break a heartbeat write.
    """
    try:
        p = root() / "telemetry" / "records.jsonl"
        if not p.exists() or p.stat().st_size < TELEMETRY_ROTATE_BYTES:
            return
        arc = root() / "telemetry" / "archive"
        arc.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        os.replace(p, arc / f"records-{stamp}.jsonl")
    except OSError:
        return


TERMINAL_COMPACT_LINES = 3


def _compact_terminal_stream(task_id: str):
    """Coalesce a terminal task's event stream in place to its last N events.

    COMPLETED/CANCELLED are final: the only downstream consumers are last-event
    reads (task_status, intake._task_state), and the contract JSON outlives the
    stream. A terminal stream's earlier events have no consumer -- keeping them
    is unbounded growth across a season (every touch re-reads everything).
    FAILED/LOST are NEVER compacted: their full stream is the audit trail the
    retry ladder reads. Best-effort: a compaction failure must not break the
    terminal transition.
    """
    try:
        p = _task_events_path(task_id)
        if not p.exists():
            return
        lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if len(lines) <= TERMINAL_COMPACT_LINES:
            return
        _write(str(p.relative_to(root())), "\n".join(lines[-TERMINAL_COMPACT_LINES:]) + "\n")
    except (OSError, ValueError):
        return


STATE_HEALTH_TASK_BUDGET = 200


def _scan_task_head(task_id: str) -> bool:
    """True when a task's contract or event-tail is unreadable (readability only).

    An unreadable stream is a stall the supervisor must see. FAILED/LOST streams
    remain parseable, so a terminal task reads healthy here.
    """
    try:
        c = _task_path(task_id)
        if not c.exists():
            return True
        json.loads(c.read_text(encoding="utf-8"))
        _last_seq(task_id)          # raises SystemExit on a torn tail
        return False
    except (OSError, ValueError, SystemExit):
        return True


def state_health() -> dict:
    """One-shot health over the live GSD state: tasks and the claim-ledger tail.

    Surfaced by the `state-health` command; consumed by g16_state_health.sh.
    A task is 'broken' when its contract or event tail is unreadable. The claim
    ledger is probed for presence and tail parseability only -- validity is
    g14's jurisdiction.
    """
    tasks_total = tasks_checked = tasks_beyond_limit = broken_tasks = 0
    ledger_present = ledger_tail_parseable = False
    dir_tasks = root() / TASKS_REL
    if dir_tasks.is_dir():
        contracts = sorted(p for p in dir_tasks.glob("*.json")
                           if not p.name.endswith(".events.jsonl"))
        tasks_total = len(contracts)
        for p in contracts[:STATE_HEALTH_TASK_BUDGET]:
            if _scan_task_head(p.stem):
                broken_tasks += 1
        tasks_checked = min(len(contracts), STATE_HEALTH_TASK_BUDGET)
        tasks_beyond_limit = max(0, len(contracts) - STATE_HEALTH_TASK_BUDGET)
    ledger_file = root() / "claims" / "ledger.jsonl"
    if ledger_file.exists():
        ledger_present = True
        try:
            with ledger_file.open("rb") as fh:
                fh.seek(max(0, ledger_file.stat().st_size - TAIL_READ_BYTES))
                tail = fh.read()
            lines = [ln for ln in tail.splitlines() if ln.strip()]
            json.loads(lines[-1])
            ledger_tail_parseable = True
        except (OSError, IndexError, json.JSONDecodeError):
            ledger_tail_parseable = False
    return {
        "tasks_total": tasks_total,
        "tasks_checked": tasks_checked,
        "tasks_beyond_limit": tasks_beyond_limit,
        "broken_tasks": broken_tasks,
        "ledger_present": ledger_present,
        "ledger_tail_parseable": ledger_tail_parseable,
        "ok": broken_tasks == 0,
    }
```

### H9 `framework/adapters/gsd_state.py` — CMDS entry (after line 1288)

OLD:
```python
    "task-list": lambda a: list_tasks(),
    "task-summary": lambda a: task_summary(),
```
NEW:
```python
    "task-list": lambda a: list_tasks(),
    "task-summary": lambda a: task_summary(),
    "state-health": lambda a: state_health(),
```

### C1 `framework/adapters/control.py` — imports (lines 68-73)

OLD:
```python
import argparse
import datetime
import json
import os
import sys
from pathlib import Path
```
NEW:
```python
import argparse
import datetime
import json
import os
import sys
import tempfile
from pathlib import Path
```

### C2 `framework/adapters/control.py` — atomic rollup rewrite (lines 601-603)

OLD:
```python
            with telemetry.open("w", encoding="utf-8") as fh:
                for rec in keep:
                    fh.write(json.dumps(rec, sort_keys=True) + "\n")
```
NEW:
```python
            # Atomic live rewrite: a plain open("w") truncates before writing, so
            # a concurrent reader (telemetry plugin, report.py) can observe an
            # empty file -- the anomaly detectors flag exactly that as an early
            # death. Stage to a sibling temp then os.replace.
            fd, tmp = tempfile.mkstemp(dir=str(telemetry.parent),
                                       prefix=f".{telemetry.name}.",
                                       suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    for rec in keep:
                        fh.write(json.dumps(rec, sort_keys=True) + "\n")
                os.replace(tmp, telemetry)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
```

### R1 `framework/telemetry/report.py` — team reads, inserted before `def main` (line 911)

OLD:
```python
def main(argv=None):
    ap = argparse.ArgumentParser()
```
NEW:
```python
def _team_paths(path=None, live=None):
    """Ordered telemetry sources: archived rotation segments then the live file.

    Rotation (gsd_state._rotate_telemetry) plus rollup archiving spreads the full
    series across telemetry/archive/records-*.jsonl and the live tail, newest
    last. --path pins one file explicitly; otherwise the sorted archive segments
    plus the live file are the full series.
    """
    if path:
        return [path]
    current = live or os.path.join(state_root(), "telemetry", "records.jsonl")
    archive_dir = os.path.join(os.path.dirname(current), "archive")
    hits = sorted(glob.glob(os.path.join(archive_dir, "records-*.jsonl")))
    return hits + ([current] if os.path.exists(current) else [])


def _load_team(paths):
    """Load every source in order and merge to one stream (recs, bad, torn_offsets).

    A rotated series is the concatenation of its segments newest-last; torn lines
    recovered in one segment keep their byte offsets in torn_offsets as usual.
    """
    recs, bad, torn_offsets = [], 0, []
    for p in paths:
        r, b, t = load(p)
        recs.extend(r)
        bad += b
        torn_offsets.extend(t)
    return recs, bad, torn_offsets


def main(argv=None):
    ap = argparse.ArgumentParser()
```

### R2 `framework/telemetry/report.py` — main read path (lines 918-921)

OLD:
```python
    a = ap.parse_args(argv)

    path = a.path or os.path.join(state_root(), "telemetry", "records.jsonl")
    recs, bad, torn_offsets = load(path)
```
NEW:
```python
    a = ap.parse_args(argv)

    paths = _team_paths(a.path)
    path = paths[0] if len(paths) == 1 else ", ".join(paths)
    recs, bad, torn_offsets = _load_team(paths)
```
(`path` is kept as the display name used by the report messages below.)

### G11 `framework/gates/g11_evidence.sh` — complete replacement

Replaces the current 64-line gate with a single-pass classifier (one interpreter per run
instead of five re-parses) plus verbatim raw-report pass-through on FAIL. External behavior is
identical: exit 0 valid / 1 invalid (named) / 2 BLOCKED / 4 NOT_APPLICABLE; `validate.py` block
[22] stays green. Required literals preserved: `GATE_NAME="g11_evidence"`, `ledger.py analyse`,
`exit $NOT_APPLICABLE`.

```bash
#!/usr/bin/env bash
# G11 -- Evidence provenance.
#
# Judges the claim ledger, not the code: every conclusion an agent reports should rest on a
# claim recorded with reproducible provenance. This gate refuses completion while any
# latest-per-id claim record is invalid -- a claim without provenance is a failure, not a
# caveated pass.
#
# Exit: 0 claims valid | 1 invalid claims listed | 2 BLOCKED | 4 NOT_APPLICABLE (no claims)
GATE_NAME="g11_evidence"
. "$(dirname "$0")/_lib.sh"

NOT_APPLICABLE=4
BLOCKED=2

have python3 || { log "BLOCKED  python3 unavailable -- claim ledger unreadable"; persist blocked "no python3"; exit $BLOCKED; }

# Windows python prints CRLF through interop pipes; $( ) strips the \n but keeps
# the stray CR, which makes [ -eq ] reject digits as garbage. Never read dirty bytes.
raw=$(python3 framework/claims/ledger.py analyse 2>&1)
rc=$?
out=$(printf '%s' "$raw" | tr -d '\r')

# Single classification pass: one interpreter, one parse. The raw report is echoed
# verbatim on the FAIL path so named claim ids stay visible to the caller
# (validate.py asserts on them).
verdict=$(printf '%s' "$out" | python3 -c "
import json, sys
rc = int(sys.argv[1])
if rc == 3:
    print('NOT_APPLICABLE|no claims recorded -- nothing to judge')
    sys.exit(0)
try:
    d = json.load(sys.stdin)
except Exception:
    print('BLOCKED|unparsable claim ledger output -- refusing to read as valid')
    sys.exit(0)
status = d.get('status')
invalid = d.get('invalid') or []
if status == 'ok' and not invalid:
    print('PASS|%s' % d.get('claims', 0))
    sys.exit(0)
lines = ['%d invalid claim(s) in ledger:' % len(invalid)]
for inv in invalid:
    lines.append('%s  status=%s  classification=%s  problems=%s' % (
        inv.get('claim_id'), inv.get('status'), inv.get('classification'),
        ','.join(inv.get('problems', []))))
print('FAIL|' + chr(10).join(lines))
" "$rc")

case "${verdict%%|*}" in
  PASS)
    n=${verdict#*|}
    persist pass "$n claim(s) valid with provenance"
    pass "claim ledger valid: $n claim(s), provenance present"
    ;;
  NOT_APPLICABLE)
    log "NOT_APPLICABLE  ${verdict#*|}"
    exit $NOT_APPLICABLE
    ;;
  FAIL)
    printf '%s\n' "$out"
    tail=${verdict#*|}
    first=${tail%%$'\n'*}; first=${first%% *}
    while IFS= read -r line; do
      [ -n "$line" ] && log "FAIL  $line"
    done <<EOF
$tail
EOF
    persist fail "$first invalid claim(s)"
    fail "claim ledger invalid: $first claim(s) lack provenance"
    ;;
  BLOCKED)
    log "BLOCKED  ${verdict#*|}"
    printf '%s\n' "$out"
    persist blocked "unparsable claim ledger output"
    exit $BLOCKED
    ;;
esac
```

### G14 `framework/gates/g14_integrity.sh` — complete replacement

Same single-pass treatment. Validated behaviors (validate.py block [28]) preserved: empty store
→ rc 4 NOT_APPLICABLE; clean → rc 0 PASS; violations → rc 1 with `EVIDENCE_*` codes and
`CLM-xxx` ids visible. Required literals preserved: `GATE_NAME="g14_integrity"`,
`ledger.py integrity`, `exit $NOT_APPLICABLE`.

```bash
#!/usr/bin/env bash
# G14 -- Evidence integrity.
#
# Judges whether evidence is authentic: it exists (E2), belongs to the task (E3),
# was actually produced with a receipt present (E5/E6), has no open reviewer
# suspicion or unfinished review blocking a VERIFIED claim (E7), and has not been
# reused verbatim across tasks (E8). Record-structure integrity (E1/E3/E4/E5)
# shares the ledger's own validate_record codes.
#
# Distinct from G11 (record validity): a fabricated or borrowed claim can be
# perfectly well-formed, and G14 exists to catch that class.
#
# Data source: `python3 framework/claims/ledger.py integrity` (latest claim per id).
# Exit: 0 all claims pass E1-E8 | 1 violations listed | 2 BLOCKED | 4 NOT_APPLICABLE (no claims)

GATE_NAME="g14_integrity"
. "$(dirname "$0")/_lib.sh"

NOT_APPLICABLE=4
BLOCKED=2

if ! have python3; then
  log "BLOCKED  python3 unavailable -- integrity check unreadable"
  persist blocked "no python3"
  exit $BLOCKED
fi

raw=$(python3 framework/claims/ledger.py integrity 2>&1)
rc=$?
out=$(printf '%s' "$raw" | tr -d '\r')

# Single classification pass; raw report echoed verbatim on the FAIL path so the
# E-codes and claim ids validate.py asserts on stay visible.
verdict=$(printf '%s' "$out" | python3 -c "
import json, sys
rc = int(sys.argv[1])
if rc == 3:
    print('NOT_APPLICABLE|no claims recorded -- nothing to check integrity')
    sys.exit(0)
try:
    d = json.load(sys.stdin)
except Exception:
    print('BLOCKED|unparsable integrity report -- refusing to judge')
    sys.exit(0)
status = d.get('status')
violations = d.get('violations') or []
if status == 'ok' and not violations:
    print('PASS|%s' % d.get('claims', 0))
    sys.exit(0)
lines = ['%d evidence integrity violation(s) across %s claim(s):' % (
    len(violations), d.get('claims', 0))]
for v in violations:
    lines.append('%s  %s  %s' % (v.get('claim_id'), v.get('check'), v.get('message')))
print('FAIL|' + chr(10).join(lines))
" "$rc")

case "${verdict%%|*}" in
  PASS)
    n=${verdict#*|}
    persist pass "$n claim(s) passed evidence integrity E1-E8"
    pass "evidence integrity: $n claim(s), all E-checks pass"
    ;;
  NOT_APPLICABLE)
    log "NOT_APPLICABLE  ${verdict#*|}"
    exit $NOT_APPLICABLE
    ;;
  FAIL)
    printf '%s\n' "$out"
    tail=${verdict#*|}
    first=${tail%%$'\n'*}; first=${first%% *}
    while IFS= read -r line; do
      [ -n "$line" ] && log "FAIL  $line"
    done <<EOF
$tail
EOF
    persist fail "$first evidence integrity violation(s)"
    fail "evidence integrity: $first violation(s) found"
    ;;
  BLOCKED)
    log "BLOCKED  ${verdict#*|}"
    printf '%s\n' "$out"
    persist blocked "unparsable integrity report"
    exit $BLOCKED
    ;;
esac
```

### G16 `framework/gates/g16_state_health.sh` — NEW file

```bash
#!/usr/bin/env bash
# G16 -- State health.
#
# One-shot health over the live GSD state: every registered task's contract must
# be readable and its event stream's tail parseable, and the claim ledger's tail
# must parse as JSON. Broken task state blocks completion -- an unreadable stream
# is a stall that must be fixed, not worked around. FAILED/LOST tasks are not
# broken: a terminal task with a readable stream is healthy.
#
# Data source: `python3 framework/adapters/gsd_state.py state-health`.
# Exit: 0 healthy | 1 broken task(s) | 2 BLOCKED | 4 NOT_APPLICABLE (no tasks, no ledger)

GATE_NAME="g16_state_health"
. "$(dirname "$0")/_lib.sh"

NOT_APPLICABLE=4
BLOCKED=2

have python3 || { log "BLOCKED  python3 unavailable -- state unreadable"; persist blocked "no python3"; exit $BLOCKED; }

out=$(python3 framework/adapters/gsd_state.py state-health 2>&1)
rc=$?
out=$(printf '%s' "$out" | tr -d '\r')

if [ "$rc" -ne 0 ]; then
  log "BLOCKED  state-health exited $rc -- refusing to judge"
  printf '%s\n' "$out"
  persist blocked "state-health exit $rc"
  exit $BLOCKED
fi

verdict=$(printf '%s' "$out" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print('BLOCKED|state-health output is not a JSON object')
    sys.exit(0)
broken = d.get('broken_tasks', 0)
if broken:
    print('FAIL|%d broken task(s) in store' % broken)
    sys.exit(0)
if d.get('tasks_total', 0) == 0 and not d.get('ledger_present', False):
    print('NOT_APPLICABLE|no tasks, no ledger')
    sys.exit(0)
print('PASS|%d task(s), 0 broken, ledger %s' % (
    d.get('tasks_total', 0),
    'present+parseable' if d.get('ledger_tail_parseable', False) else 'present'))
")

case "${verdict%%|*}" in
  PASS)
    msg=${verdict#*|}
    persist pass "$msg"
    pass "state health ok: $msg"
    ;;
  NOT_APPLICABLE)
    log "NOT_APPLICABLE  ${verdict#*|}"
    exit $NOT_APPLICABLE
    ;;
  FAIL)
    printf '%s\n' "$out"
    msg=${verdict#*|}
    persist fail "$msg"
    fail "state health: $msg"
    ;;
  BLOCKED)
    log "BLOCKED  ${verdict#*|}"
    persist blocked "${verdict#*|}"
    exit $BLOCKED
    ;;
esac
```

### W1 `framework/gates/EXIT_CODES.md` — G16 row (insert between lines 25 and 26)

OLD:
```
| G15 tripwires | no eval tripwire hits | violations listed | BLOCKED (grep/awk absent) | — | NOT_APPLICABLE (no changed eval files) |
| G-EXEC exec-integrity | matrix 38/38 checks pass | deviations listed | BLOCKED (python3 absent) | — | NOT_APPLICABLE (no matrix module) |
```
NEW:
```
| G15 tripwires | no eval tripwire hits | violations listed | BLOCKED (grep/awk absent) | — | NOT_APPLICABLE (no changed eval files) |
| G16 state-health | task/ledger store readable | broken task(s) or unreadable tail listed | BLOCKED (python3 absent / adapter error) | — | NOT_APPLICABLE (no tasks, no ledger) |
| G-EXEC exec-integrity | matrix 38/38 checks pass | deviations listed | BLOCKED (python3 absent) | — | NOT_APPLICABLE (no matrix module) |
```

### W2 `framework/verifier/profiles.yaml` — functional profile (line 6)

OLD:
```yaml
    commands: ["./framework/gates/g4_executable.sh", "./framework/gates/g8_blockers.sh", "./framework/gates/g9_scope.sh", "./framework/gates/g11_evidence.sh", "./framework/gates/g14_integrity.sh"]
```
NEW:
```yaml
    commands: ["./framework/gates/g4_executable.sh", "./framework/gates/g8_blockers.sh", "./framework/gates/g9_scope.sh", "./framework/gates/g11_evidence.sh", "./framework/gates/g14_integrity.sh", "./framework/gates/g16_state_health.sh"]
```

### W3 `framework/validate.py` — block [35] (insert after line 2472, before line 2474)

Mirrors the tail-block style ([33]/[34]): static pulls + an isolated-store behavioral run that
pins `GSD_STATE_ROOT` to the temp root (exercising H2's new env path end-to-end).

```python
print("\n[35] G16 state-health gate (task/ledger tail readability)")
_g1635 = Path("framework/gates/g16_state_health.sh")
check("framework/gates/g16_state_health.sh exists",
      _g1635.exists(), "missing: framework/gates/g16_state_health.sh")
if _g1635.exists():
    _g16text = _g1635.read_text(encoding="utf-8")
    check("g16 self-identifies as g16_state_health",
          'GATE_NAME="g16_state_health"' in _g16text, "GATE_NAME literal missing")
    check("g16 reads the adapter state-health command",
          "state-health" in _g16text, "state-health invocation missing")
    check("g16 has an explicit NOT_APPLICABLE exit",
          "exit $NOT_APPLICABLE" in _g16text, "NOT_APPLICABLE literal missing")
    check("g16 is on the functional profile",
          "./framework/gates/g16_state_health.sh" in
          Path("framework/verifier/profiles.yaml").read_text(encoding="utf-8"),
          "profile membership missing")
    check("EXIT_CODES documents G16",
          "| G16 state-health" in
          Path("framework/gates/EXIT_CODES.md").read_text(encoding="utf-8"),
          "EXIT_CODES row missing")
    check("gsd_state exposes state-health",
          "def state_health()" in
          Path("framework/adapters/gsd_state.py").read_text(encoding="utf-8"),
          "state_health missing")
    import shutil, tempfile
    _d35 = Path(tempfile.mkdtemp(prefix="val35_g16_"))
    try:
        shutil.copytree("framework", _d35 / "framework")
        _env35 = dict(os.environ, GSD_STATE_ROOT=str(_d35 / ".planning"))
        _r35a = subprocess.run(["bash", "framework/gates/g16_state_health.sh"],
                               cwd=str(_d35), env=_env35, capture_output=True, text=True,
                               timeout=180)
        check("empty store -> NOT_APPLICABLE (4) with no tasks and no ledger",
              _r35a.returncode == 4 and "NOT_APPLICABLE" in _r35a.stdout,
              f"rc={_r35a.returncode} out={_r35a.stdout[-400:]}")
        _r35b = subprocess.run([sys.executable, "framework/adapters/gsd_state.py",
                                "task-register", "--id", "V35-001", "--json",
                                json.dumps({"objective": "g16 probe", "agent": "verifier",
                                            "expected_artifact": "rc 0", "headless": True})],
                               cwd=str(_d35), env=_env35, capture_output=True, text=True,
                               timeout=180)
        check("task-register in the isolated root exits 0",
              _r35b.returncode == 0, (_r35b.stdout + _r35b.stderr)[-400:])
        _r35c = subprocess.run(["bash", "framework/gates/g16_state_health.sh"],
                               cwd=str(_d35), env=_env35, capture_output=True, text=True,
                               timeout=180)
        check("store with one registered task -> PASS (0)",
              _r35c.returncode == 0 and "PASS" in _r35c.stdout,
              f"rc={_r35c.returncode} out={_r35c.stdout[-400:]}")
    finally:
        shutil.rmtree(_d35, ignore_errors=True)
```

### T1 `framework/claims/test_ledger_rules.py` — append tests (append to end of file)

```python
def test_auto_claim_id_is_20_digit_ns_epoch():
    ledger._last_claim_ns = 0
    cid = ledger._next_claim_id()
    assert cid.startswith("CLM-") and len(cid) == 4 + 20 and cid[4:].isdigit()


def test_auto_claim_id_strictly_monotonic_on_clock_step_back(monkeypatch):
    ledger._last_claim_ns = 0
    clock = [1_700_000_000_000_000_000]
    monkeypatch.setattr(ledger.time, "time_ns", lambda: clock[0])
    a = ledger._next_claim_id()
    clock[0] -= 1          # NTP step-back: wall clock goes backwards
    b = ledger._next_claim_id()
    assert b > a


def test_append_auto_ids_without_scanning_existing_records(monkeypatch, tmp_path):
    # The old id continued the highest existing number (a full-ledger scan on
    # every append); the new id is clock-only, so the store size cannot change it.
    ledger._last_claim_ns = 0
    monkeypatch.setattr(ledger, "_state_root", lambda: tmp_path)
    rec = _claim("DIRECT")
    del rec["claim_id"]            # append must auto-assign
    cid = ledger.append(rec)
    assert cid.startswith("CLM-")
    got = ledger.load()
    assert len(got) == 1 and got[0]["claim_id"] == cid
```

### D1 `framework/claims/README.md` — auto-assign doc (lines 32-33)

OLD:
```
it prints one error code on stdout and exits 1 (never 2). If no `claim_id` is supplied it
auto-assigns `CLM-NNN`, continuing the highest existing number across all records.
```
NEW:
```
it prints one error code on stdout and exits 1 (never 2). If no `claim_id` is supplied it
auto-assigns `CLM-<20-digit ns-epoch>` -- a strictly increasing id clock that needs no
ledger scan, so append cost is independent of the store size.
```

### D2 `framework/claims/README.md` — schema row (line 39)

OLD:
```
| `claim_id` | auto or supplied | `CLM-NNN` or a caller-supplied id; multiple records per id are history, latest wins |
```
NEW:
```
| `claim_id` | auto or supplied | `CLM-<20-digit ns-epoch>` or a caller-supplied id; ids are monotonically increasing, and multiple records per id are history, latest wins |
```

---

## 4. Post-apply verification (run in order; record every exit code)

1. **Unit tests** — `python3 -m pytest framework/claims/test_ledger_rules.py -q` → 0
   (covers H3/H4 incl. monotonicity and no-scan append).
2. **Adapters selftest** — `python3 framework/adapters/gsd_state.py selftest`, and
   `python3 framework/adapters/control.py selftest`, `python3 framework/adapters/execute.py
   selftest` → all 0.
3. **Gates on the live store** — `bash framework/gates/g11_evidence.sh`,
   `bash framework/gates/g14_integrity.sh`, `bash framework/gates/g16_state_health.sh` →
   each 0 (G16 may be 4 if the store is empty; 4 is NOT_APPLICABLE, not a pass).
4. **Full validator** — `python3 framework/validate.py` → 0 (now includes block [35], which
   re-exercises G16 in an isolated store and the GSD_STATE_ROOT env path).
5. **GSD_STATE_ROOT smoke** — with an absolute `GSD_STATE_ROOT` set,
   `python3 framework/claims/ledger.py path` must print `<root>/claims/ledger.jsonl`; with a
   relative value (e.g. `x`) it must NOT be honored.
6. **Terminal compaction smoke** — register a task, emit 5 PROGRESS events + COMPLETED, then
   count lines in `tasks/<id>.events.jsonl` → exactly 3; emit FAILED on a second task and
   confirm its stream is not compacted.
7. **Rotation smoke** — with `TELEMETRY_ROTATE_BYTES` temporarily lowered, confirm
   `write_telemetry` moves the live file to `telemetry/archive/records-<stamp>.jsonl` and
   `report.py` still returns 0 with the archive segment included.
8. **Perf smoke (the point)** — time `task-event` × 1000 and `ledger.py append` × 1000 before
   and after on a populated store; the quadratic growth must be gone.

Rollback: all changes are in 11 files (ledger.py, gsd_state.py, control.py, report.py,
g11_evidence.sh, g14_integrity.sh, EXIT_CODES.md, profiles.yaml, validate.py,
test_ledger_rules.py, README.md) + 1 new gate (g16_state_health.sh); `git checkout -- <file>`
per hunk or revert the commit. There is no migration: existing streams, claims, and telemetry
remain readable (B2 only trims streams on the *next* terminal event).

---

## 5. Compatibility checklist (what the kit deliberately does not break)

- `validate.py` blocks [21]/[22]/[28] (g11/g14 static + behavioral): literals and observable
  stdout preserved by the replacements.
- EXIT_CODES G14 row literal `NOT_APPLICABLE (no claims recorded)`: untouched.
- `task_status` / `intake._task_state`: last-event reads; compaction keeps the terminal line.
- `TERMINAL_STATE` guard and `INVALID_TRANSITION`: read `events[-1]` — still present after
  compaction.
- `report.py --path <file>`: pinned to one file exactly as before.
- Claims/telemetry/tasks schema: no field added or removed anywhere.

---

## 6. Pre-apply validation record (2026-09-20)

Dry-run applied every hunk to scratch copies (never the enforcement plane) and
syntax-checked the assembled files:

- `python3 kit_dryrun.py` (scratch, outside the working tree) → exit 0,
  26/26 rows PASS (every OLD block matches the live file exactly once; every assembled
  NEW file parses via py_compile / bash -n / yaml.safe_load; G16 required literals
  present; W3 anchor lines 2473-2474 confirmed).
- `python3 kit_asm_smoke.py` (scratch, outside the working tree) → exit 0,
  9/9 rows PASS (assembled behavioral smoke on a full scratch framework/ tree: selftest,
  `state-health` JSON contract with ok=true, G16 gate PASS with a claim present,
  stateless `CLM-<20-digit>` append, absolute GSD_STATE_ROOT honored / relative rejected,
  terminal compaction to 3 lines, telemetry rotation to archive/).
- Claim ledger records: `CLM-054`, `CLM-055`, `CLM-056` (all VERIFIED, behavioral,
  command_run evidence).
- Enforcement plane untouched at validation time — only pre-existing untracked
  `.bak-d*` backups present; the plane's check script still exits 0.

The behavioral smoke caught one thing the dry-run could not: **bash gates must be written
with LF only.** The dry-run pipe-fed assembled content to `bash -n` via stdin, so a CRLF
on-disk file still parsed; the smoke ran the assembled gate on disk and CRLF broke
`. _lib.sh` sourcing (`_lib.sh\r: No such file or directory`) and the `case` verdict.
Every apply step must preserve LF (see section 2).

This de-risks the hand-apply: a hunk failing to match or a NEW block failing to parse
would have surfaced here, in scratch space, before any real file was touched.