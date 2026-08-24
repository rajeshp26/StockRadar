#!/usr/bin/env python3
"""Adopt-before-extend audit completeness check.

Enforces PRESENCE of a decision per row, never correctness. A framework installed with an
empty audit was installed without checking whether it duplicates the workflow engine it
sits on. That is the most likely path back to thirteen agents.
"""
import sys
from pathlib import Path

AUDIT = Path("framework/ADOPT_AUDIT.md")
VALID = {"adopt", "wrap", "replace"}


def rows():
    if not AUDIT.exists():
        return None
    out = []
    for line in AUDIT.read_text().splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 5 or cells[0].startswith("---") or cells[0] == "GSD capability":
            continue
        out.append(cells)
    return out


def main():
    r = rows()
    if r is None:
        print("BLOCKED: framework/ADOPT_AUDIT.md missing.", file=sys.stderr)
        return 2
    undecided = [c for c in r if not c[3]]
    invalid = [c for c in r if c[3] and c[3].split()[0].lower() not in VALID]
    unjustified = [c for c in r
                   if c[3] and c[3].split()[0].lower() == "replace" and not c[4]]

    print(f"audit rows: {len(r)}  decided: {len(r) - len(undecided)}")
    if invalid:
        for c in invalid:
            print(f"  INVALID  {c[0]}: '{c[3]}' not in {sorted(VALID)}", file=sys.stderr)
        return 1
    if unjustified:
        for c in unjustified:
            print(f"  UNJUSTIFIED  {c[0]}: 'replace' requires a named defect class "
                  f"the GSD capability cannot catch", file=sys.stderr)
        return 1
    if undecided:
        for c in undecided:
            print(f"  UNDECIDED  {c[0]} (overlaps {c[2]})")
        print(f"\n{len(undecided)} row(s) undecided. This is expected on a fresh install and "
              f"is a required step, not a defect.", file=sys.stderr)
        return 3
    print("audit complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
