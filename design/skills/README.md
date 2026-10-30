# Imported design skills (advisory)

This directory contains third-party UI/design skills imported by
`framework/tools/import_design_skills.py`.

- They are **advisory only**. Precedence is:
  `AGENTS.md > agent definition > skill content`.
- They are **discoverable**: `opencode.json` lists this directory in `skills.paths`, so a
  role may load one by name. Discoverable is not mandatory - `framework/opencode/skill-routing.md`
  decides which skills a task *must* load, and only `apple-ui`, `frontend-react` and
  `designmotion-design` hold UI slots there.
- They are **not** rules, contracts, or verification evidence. G5/G6 still decide visual
  conformance and browser evidence.
- Some entries carry upstream pointers that do not exist here (`settigation-code`,
  `practical-ui`, `muse.*` connectors, `/opt/muse/...`). Treat those as inapplicable, not as
  files to go looking for; the repo-real targets are `frontend-react` for implementation and
  `uiux-design-foundations` for principles.
- See `ATTRIBUTION.md` for source and license.
- To add/refresh skills, re-run the importer (see its module docstring; it rewrites this file).
