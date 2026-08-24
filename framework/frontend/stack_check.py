#!/usr/bin/env python3
"""G5 frontend stack conformance.

Design constraints, in priority order:

1. Ratchet, not sweep. Only files changed by the current task are judged. A brownfield repo
   has pre-existing violations; blocking on those trains people to bypass the gate.
2. Tool absence is never a verdict. If we cannot read package.json, we report BLOCKED, not PASS.
   (Same failure class as the earlier pyyaml and npx bugs.)
3. Required tier is enforced. Conditional tier requires a recorded justification.
"""
from __future__ import annotations
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
STACK = ROOT / "framework/frontend_stack.yaml"
LEDGER = ROOT / "framework/frontend/effect_justifications.yaml"
BASELINE = ROOT / "framework/frontend/baseline.json"

BLOCKED, FAIL, PASS, NOT_APPLICABLE = 2, 1, 0, 4


def load_yaml(p: Path):
    try:
        import yaml
    except ImportError:
        print(f"BLOCKED: pyyaml unavailable; cannot read {p.name}. "
              "A missing parser is not conformance.", file=sys.stderr)
        sys.exit(BLOCKED)
    if not p.exists():
        print(f"BLOCKED: {p} missing.", file=sys.stderr)
        sys.exit(BLOCKED)
    return yaml.safe_load(p.read_text()) or {}


def changed_files() -> list[str]:
    """cwd-relative, tracked modifications plus untracked additions."""
    out = set()
    for cmd in (["git", "diff", "--name-only", "--relative", "HEAD"],
                ["git", "ls-files", "--others", "--exclude-standard"]):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            out.update(l for l in r.stdout.splitlines() if l.strip())
        except Exception:
            pass
    return sorted(out)


def glob_match(path: str, globs: list[str]) -> bool:
    from fnmatch import fnmatch
    return any(fnmatch(path, g) for g in globs)


def read_manifest() -> tuple[dict, str | None]:
    pj = ROOT / "package.json"
    if not pj.exists():
        return {}, "package.json absent"
    try:
        data = json.loads(pj.read_text())
    except Exception as e:
        return {}, f"package.json unparseable: {e}"
    deps = {}
    for k in ("dependencies", "devDependencies", "peerDependencies"):
        deps.update(data.get(k) or {})
    return deps, None


def main() -> int:
    stack = load_yaml(STACK)
    ledger = load_yaml(LEDGER)
    fglobs = stack.get("frontend_globs", [])
    prim = stack.get("primitive_dirs", [])
    required = stack["tiers"]["required"]
    conditional = stack["tiers"]["conditional"]

    changed = [f for f in changed_files() if glob_match(f, fglobs)]
    findings: list[str] = []
    notes: list[str] = []

    deps, dep_err = read_manifest()

    # --- Is there a frontend application at all? -----------------------------------
    # A generated contract type file is not an application. Reporting PASS when nothing
    # was evaluated is a vacuous pass — the exact failure class this framework exists to
    # prevent. Distinguish "nothing to judge" (NOT_APPLICABLE) from "judged, conformant".
    has_components = any(ROOT.glob("src/frontend/**/*.tsx"))
    has_manifest = (ROOT / "package.json").exists()
    frontend_exists = has_components or has_manifest
    if not frontend_exists:
        print("NOT_APPLICABLE: no frontend application present "
              "(no *.tsx under src/frontend, no package.json). Nothing was evaluated.")
        return NOT_APPLICABLE

    if dep_err:
        print(f"BLOCKED: cannot evaluate required stack — {dep_err}", file=sys.stderr)
        return BLOCKED

    if True:
        for spec in required:
            concern, tool = spec["concern"], spec["tool"]
            pkg = spec.get("package")
            if pkg and pkg not in deps:
                findings.append(f"{concern}: required tool {tool} ({pkg}) not in package.json")
            mf = spec.get("marker_file")
            if mf and not (ROOT / mf).exists():
                findings.append(f"{concern}: required tool {tool} missing marker file {mf}")
            for alt in spec.get("forbidden_alternates", []):
                if alt in deps:
                    findings.append(
                        f"{concern}: forbidden alternate '{alt}' present; standard is {tool}")

    # --- shadcn config assertions --------------------------------------------------
    cj = ROOT / "components.json"
    sc = stack.get("shadcn_config", {})
    if cj.exists():
        try:
            cjd = json.loads(cj.read_text())
            want_icon = sc.get("require_icon_library")
            if want_icon and cjd.get("iconLibrary") != want_icon:
                findings.append(
                    f"components.json iconLibrary is {cjd.get('iconLibrary')!r}, expected {want_icon!r}")
            if sc.get("require_empty_tailwind_config"):
                tw = (cjd.get("tailwind") or {}).get("config", "")
                if tw:
                    findings.append(
                        f"components.json tailwind.config is {tw!r}; Tailwind v4 requires it empty")
        except Exception as e:
            print(f"BLOCKED: components.json unparseable: {e}", file=sys.stderr)
            return BLOCKED

    # --- Responsive validation: viewports must actually be configured --------------
    rv = next((s for s in required if s["concern"] == "responsive_validation"), None)
    if rv:
        cfg = next((p for p in (ROOT / "playwright.config.ts", ROOT / "playwright.config.js")
                    if p.exists()), None)
        if cfg is None:
            findings.append("responsive_validation: no playwright.config found")
        else:
            txt = cfg.read_text()
            # Count PROJECTS, not keyword occurrences. A single project containing both
            # `devices[...]` and `viewport:` scored 2 under naive keyword counting, so a
            # one-viewport config passed a >=2 requirement. Each project must carry a
            # distinct rendered width for a responsive claim to mean anything.
            block = ""
            if "projects:" in txt:
                block = txt.split("projects:", 1)[1]
            widths, projects = set(), 0
            for m in re.finditer(r"\{\s*name\s*:\s*[\"'\`]([^\"'\`]+)", block):
                projects += 1
                tail = block[m.end():m.end() + 400]
                w = re.search(r"width\s*:\s*(\d+)", tail)
                dev = re.search(r"devices\[\s*[\"'\`]([^\"'\`]+)", tail)
                widths.add(w.group(1) if w else (dev.group(1) if dev else f"proj{projects}"))
            need = int(rv.get("min_viewports", 2))
            if len(widths) < need:
                findings.append(
                    f"responsive_validation: {len(widths)} distinct viewport(s) across "
                    f"{projects} project(s), need >= {need}")

    # --- Conditional tier: require a ledger entry ---------------------------------
    entries = ledger.get("entries") or []
    justified = {}
    for e in entries:
        justified.setdefault(str(e.get("tool", "")).lower(), []).append(e)

    changed_text = {f: (ROOT / f).read_text(errors="replace")
                    for f in changed for _ in [0] if (ROOT / f).exists()}

    for spec in conditional:
        tool = spec["tool"]
        pkgs = spec.get("packages", [])
        markers = spec.get("import_markers", []) + pkgs
        present_dep = [p for p in pkgs if p in deps]
        used_in = [f for f, t in changed_text.items() if any(m in t for m in markers)]
        if not present_dep and not used_in:
            continue
        ent = justified.get(tool.lower(), [])
        if not ent:
            where = ", ".join(used_in) if used_in else f"dependency {present_dep}"
            findings.append(
                f"conditional tool {tool} used ({where}) with no entry in "
                f"framework/frontend/effect_justifications.yaml")
            continue
        for field in spec.get("extra_fields", []):
            if not any(str(e.get(field, "")).strip() for e in ent):
                findings.append(
                    f"conditional tool {tool}: ledger entry missing required field '{field}'")
        for e in ent:
            if not str(e.get("requirement", "")).strip():
                findings.append(f"conditional tool {tool}: ledger entry names no requirement")
            if not str(e.get("approved_by", "")).strip():
                findings.append(f"conditional tool {tool}: ledger entry has no approver")
            scope = e.get("scope") or []
            if scope and used_in:
                stray = [f for f in used_in if not glob_match(f, scope)]
                if stray:
                    findings.append(
                        f"conditional tool {tool} used outside approved scope: {stray}")

    # --- Mechanical file rules, changed files only (ratchet) ----------------------
    baseline = {}
    if BASELINE.exists():
        try:
            baseline = json.loads(BASELINE.read_text())
        except Exception:
            baseline = {}

    for rule in stack.get("file_rules", []):
        pat = re.compile(rule["pattern"])
        exempt = prim if rule.get("exempt_dirs_key") == "primitive_dirs" else []
        hatch = rule.get("escape_hatch")
        for f, text in changed_text.items():
            if any(f.startswith(d) for d in exempt):
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if not pat.search(line):
                    continue
                if hatch and hatch in line:
                    notes.append(f"{f}:{i} {rule['id']} waived inline")
                    continue
                key = f"{f}:{rule['id']}"
                if key in baseline:
                    notes.append(f"{f} {rule['id']} pre-existing (baseline)")
                    continue
                findings.append(f"{f}:{i} {rule['id']}: {rule['message']}")

    scope_note = f"{len(changed)} changed frontend file(s)"
    if notes:
        print(f"notes: {len(notes)} waived/baseline occurrence(s)")
    if findings:
        print(f"FAIL frontend stack conformance ({scope_note}):")
        for x in findings:
            print(f"  - {x}")
        return FAIL
    print(f"PASS frontend stack conformance ({scope_note})")
    return PASS


if __name__ == "__main__":
    sys.exit(main())
