#!/usr/bin/env python3
"""Emit the remaining enforcement-plane patches for human approval.

WHY THIS EXISTS
===============
Everything that makes skill selection *enforced* is already in the repository and runnable --
`framework/tools/skill_coverage.py`, `framework/tools/skill_use.py`, `g_skill_coverage.sh`,
`g_skill_use.sh`. Three things still sit behind the enforcement plane (`framework/opencode/**`
is edit-denied for an agent, by design), and an agent cannot apply them:

  1. `framework/opencode/agents/team-lead.md`
     The Capability Matrix table has 13 rows and names neither `apple-ui` nor
     `designmotion-design`. The matrix schema is PARSED from that table, so until the rows
     exist the check cannot demand the two design skills the whole integration is about.

  2. `framework/opencode/plugin/telemetry.ts`
     The skill recorder reads `input?.args?.name`, but args are not on `input.args` in this
     harness -- the same defect the file already documents for the `task` tool two blocks
     earlier, which is why `normalizeTaskArgs` exists and is already imported. Every skill
     call is therefore recorded as `"unknown"`, which makes `skills_loaded` useless and makes
     G-SKILL-USE unable to ever pass. One statement.

  3. `framework/opencode/agents/verifier.md`
     A gate nobody runs is documentation. G-SKILL-USE has to be in the verifier's sequence and
     in its recorded gate map, or the invocation half of the contract is still a promise.

Every target is plane-locked, so this script NEVER modifies the repository. It writes a patch a
human applies with `git apply`.

INVARIANTS ASSERTED (same discipline as emit_design_skills_integration_patch.py)
===============================================================================
- every anchor occurs exactly once after line-ending normalisation (no ambiguity)
- replacements are reversible: undoing them restores the original byte-for-byte
- each file's own line endings are preserved (CRLF detected from bytes)
- the emitted hunks, re-applied from their @@ offsets, reproduce the intended post-image
- the patched team-lead.md, parsed by the SAME function the gate uses, yields 15 dimensions
  including `apple-ui` and `designmotion-design` -- the semantic effect, not just the bytes
- the patched telemetry.ts skill block no longer reads `input?.args?.name`

Emits `framework/docs/designer-agent/remaining-plane-patches.patch`.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# Reuse the existing emitter's primitives instead of a second diff implementation.
from emit_design_skills_integration_patch import (  # noqa: E402
    apply_hunks,
    generate,
    parse,
    read_exact,
    style_of,
)
from skill_coverage import parse_schema  # noqa: E402

OUT = REPO / "docs" / "designer-agent" / "remaining-plane-patches.patch"

MATRIX = "framework/opencode/agents/team-lead.md"
SENSOR = "framework/opencode/plugin/telemetry.ts"
VERIFIER = "framework/opencode/agents/verifier.md"

EDITS: dict[str, list[tuple[str, str]]] = {}

# 1. Two Capability Matrix rows. Column 3 is the skill ID the schema parser reads, so the label
#    is free text but the backticked name must match the skill directory exactly.
EDITS[MATRIX] = [(
    "| Frontend implementation | yes/no | `frontend-react` |\n",
    "| Frontend implementation | yes/no | `frontend-react` |\n"
    "| UI design system | yes/no | `apple-ui` |\n"
    "| Interaction design | yes/no | `designmotion-design` |\n",
)]

# 2. The skill recorder. `id` first because that is the skill tool's documented parameter;
#    `name` stays as a fallback so the line is right under either shape.
EDITS[SENSOR] = [(
    '      if (input?.tool === "skill") {\n'
    '        rec.skills_loaded.add(String(input?.args?.name ?? "unknown"))\n'
    "      }\n",
    '      if (input?.tool === "skill") {\n'
    "        // Args are NOT on input.args in this harness (see the task-tool note above):\n"
    "        // reading them there recorded every skill call as \"unknown\", so skills_loaded\n"
    "        // said nothing and G-SKILL-USE could not judge. normalizeTaskArgs reads the shape\n"
    "        // the harness actually delivers; `id` is the skill tool's parameter, `name` is\n"
    "        // kept as a fallback so this line is correct under either shape.\n"
    "        const skillArgs = normalizeTaskArgs(input)\n"
    '        rec.skills_loaded.add(String(skillArgs?.id ?? skillArgs?.name ?? "unknown"))\n'
    "      }\n",
)]

# 3. Put the gate in the verifier's sequence and in its recorded gate map.
EDITS[VERIFIER] = [
    (
        "## Blocker hygiene\n",
        "## Skill-use completeness\n"
        "\n"
        "`framework/gates/g_skill_use.sh` runs for any task whose plan declares\n"
        "`required_skills`. It diffs the plan's requirement against the skills recorded as\n"
        "invoked in `.planning/telemetry/records.jsonl`, filtered to the task. Exit 0 every\n"
        "required skill was recorded as invoked, 1 one or more were not, 2 blocked (no plan\n"
        "context, unreadable store), 3 capability missing (no telemetry plugin, so nothing could\n"
        "have recorded a call), 4 not applicable (no records, or the plan requires no skills).\n"
        "\n"
        "Run it with `ENTRY_PLAN=<plan path> ENTRY_TASK=<task id>`. Exit 1 is a real finding:\n"
        "report the skill that was never loaded rather than accepting the handoff. Exit 3 and 4\n"
        "are not passes either -- 3 means the instrument is missing, 4 means there was nothing\n"
        "to judge. `SU01` (a call recorded as `unknown`) is a defect in the recorder, not a\n"
        "missing skill; report it as such and do not count it as satisfied.\n"
        "\n"
        "## Blocker hygiene\n",
    ),
    (
        "  gates: {g1:, g2:, g3:, g3_5:, g4:, g8:, g11:, g14:}",
        "  gates: {g1:, g2:, g3:, g3_5:, g4:, g8:, g11:, g14:, skill_use:}",
    ),
]


def build() -> dict[str, dict]:
    """repo-relative path -> {original, updated, style}."""
    built: dict[str, dict] = {}
    for rel, pairs in EDITS.items():
        path = REPO / rel
        if not path.exists():
            raise SystemExit("%s: target does not exist" % rel)
        original = read_exact(path)
        style = style_of(original)
        current = original
        for anchor, replacement in pairs:
            old = anchor.replace("\n", style)
            new = replacement.replace("\n", style)
            hits = current.count(old)
            if hits != 1:
                raise SystemExit("%s: anchor occurs %d times, expected exactly 1" % (rel, hits))
            if new == old:
                raise SystemExit("%s: replacement equals anchor" % rel)
            current = current.replace(old, new)
        restored = current
        for anchor, replacement in reversed(pairs):
            restored = restored.replace(
                replacement.replace("\n", style), anchor.replace("\n", style)
            )
        if restored != original:
            raise SystemExit("%s: replacement is not reversible - more changed than intended" % rel)
        built[rel] = {"original": original, "updated": current, "style": style}
    return built


def verify_effect(built: dict[str, dict]) -> list[str]:
    """Assert the patched files MEAN what they are supposed to mean, not just diff cleanly."""
    notes = []

    schema = parse_schema(built[MATRIX]["updated"])
    need = {"apple-ui", "designmotion-design"}
    absent = sorted(need - set(schema))
    if absent:
        raise SystemExit("matrix rows did not widen the schema: missing %s" % absent)
    if len(schema) != 15:
        raise SystemExit("expected 15 matrix dimensions after the patch, got %d: %s"
                         % (len(schema), schema))
    notes.append("matrix: %d dimensions, both design skills declared" % len(schema))

    sensor = built[SENSOR]["updated"]
    if "input?.args?.name" in sensor:
        raise SystemExit("telemetry.ts still reads input?.args?.name after the patch")
    if "normalizeTaskArgs(input)" not in sensor:
        raise SystemExit("telemetry.ts skill block does not use normalizeTaskArgs")
    notes.append("sensor: skill name read through normalizeTaskArgs")

    ver = built[VERIFIER]["updated"]
    if "g_skill_use.sh" not in ver or "skill_use:" not in ver:
        raise SystemExit("verifier.md does not invoke or record G-SKILL-USE")
    notes.append("verifier: gate in sequence and in the recorded gate map")
    return notes


def main() -> int:
    built = build()
    patch = generate(built)
    files = parse(patch)
    if set(files) != set(built):
        raise SystemExit("patch touches %s, expected %s" % (sorted(files), sorted(built)))

    for rel, info in files.items():
        rebuilt = apply_hunks(built[rel]["original"], info["hunks"])
        if rebuilt != built[rel]["updated"]:
            raise SystemExit("self-check FAILED: rebuilt %s != intended post-image" % rel)

    notes = verify_effect(built)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(patch, encoding="utf-8", newline="")
    hunks = sum(len(v["hunks"]) for v in files.values())
    print("wrote %s (%d bytes)" % (OUT.relative_to(REPO).as_posix(), len(patch)))
    print("files: %d, hunks: %d, self-check: OK" % (len(files), hunks))
    for n in notes:
        print("  verified: %s" % n)
    print("\napply with:  git apply --check %s  &&  git apply %s"
          % (OUT.relative_to(REPO).as_posix(), OUT.relative_to(REPO).as_posix()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
