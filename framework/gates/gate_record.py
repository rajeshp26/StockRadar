#!/usr/bin/env python3
"""Write a gate's own result record.

WHY THIS EXISTS
===============
`matrix.py record --gate g6` lets the CALLER name the gate. A caller that ran something which
is not g6 -- a hand-rolled Playwright invocation, a different reporter, a subset chosen after
the fact -- could still file its artifact under `g6`, and the row then carried a pass it did not
earn. That was the last hole in the verification chain (VERIFICATION-CONTRACT-DESIGN.md 12.4).

The gate writes this file at the moment it judges. `matrix.py record --from-gate` reads it and
takes the gate identity, the exit code and the artifact hashes FROM THE RECORD; the caller can
only name the criterion. In the standards vocabulary this is the "contemporaneous, attributable
record" control: the measuring instrument produces the record, not the person transcribing it.

Contract: exit 0 written | 1 the record contradicts itself (result vs exit) |
          3 written, but an artifact the gate named is missing.
"""

import argparse
import hashlib
import json
import os
import sys

SCHEMA = "gate-result/1"

# Closed vocabulary. Mirrors framework/gates/_lib.sh NON_JUDGEMENT_REASONS plus the verdicts.
RESULTS = ("pass", "fail", "unverifiable", "not_applicable", "precondition_missing",
           "capability_missing", "not_reached")

# A verdict and its exit code must agree, or the record is a claim rather than a measurement.
EXPECTED_EXIT = {"pass": 0, "fail": 1, "unverifiable": 3, "not_applicable": 4,
                 "precondition_missing": 2, "capability_missing": 3}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build(gate, name, result, exit_code, at, detail="", selection="", artifacts=()):
    """Return (record, missing). Pure, so the self-test can exercise it without a filesystem."""
    listed, missing = [], []
    for path in artifacts:
        norm = path.replace("\\", "/")
        if os.path.isfile(path):
            listed.append({"path": norm, "sha256": sha256(path)})
        else:
            # Recorded, not dropped: "the gate named an artifact that is not there" is a
            # finding a reader must be able to see, not something to hide by omission.
            listed.append({"path": norm, "sha256": None, "missing": True})
            missing.append(norm)
    record = {
        "schema": SCHEMA,
        "gate": gate,
        "name": name or gate,
        "result": result,
        "exit": int(exit_code),
        "at": at,
        "selection": selection,
        "detail": detail,
        "artifacts": listed,
    }
    return record, missing


def write(path, record):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    body = json.dumps(record, indent=2, ensure_ascii=False) + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body)


def main(argv=None):
    ap = argparse.ArgumentParser(description="write a gate result record")
    ap.add_argument("--path", required=True)
    ap.add_argument("--gate", required=True)
    ap.add_argument("--name", default="")
    ap.add_argument("--result", required=True, choices=RESULTS)
    ap.add_argument("--exit", dest="exit_code", type=int, required=True)
    ap.add_argument("--at", required=True)
    ap.add_argument("--detail", default="")
    ap.add_argument("--selection", default="")
    ap.add_argument("--artifact", action="append", default=[])
    a = ap.parse_args(argv)

    want = EXPECTED_EXIT.get(a.result)
    if want is not None and a.exit_code != want:
        print("gate_record: result=%s cannot carry exit=%d (expected %d)"
              % (a.result, a.exit_code, want), file=sys.stderr)
        return 1

    record, missing = build(a.gate, a.name, a.result, a.exit_code, a.at,
                            a.detail, a.selection, a.artifact)
    try:
        write(a.path, record)
    except OSError as exc:
        print("gate_record: cannot write %s: %s" % (a.path, exc), file=sys.stderr)
        return 2
    if missing:
        print("gate_record: artifact(s) named by the gate are missing: %s"
              % ", ".join(missing), file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
