#!/usr/bin/env python3
"""OpenAPI structural validator. Dependency-light on purpose.

Uses redocly or openapi-spec-validator when present, otherwise falls back to a structural
check using only PyYAML. A gate that cannot run without a toolchain install is not a gate.
"""
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("BLOCKED: pyyaml required to validate contracts"); sys.exit(2)

REQUIRED_TOP = ["openapi", "info", "paths"]
HTTP_METHODS = {"get", "put", "post", "delete", "patch", "options", "head", "trace"}


# Exit codes / output that mean "the tool could not run", NOT "the contract is invalid".
# Conflating the two makes a missing toolchain read as a contract violation, or worse, a
# network failure read as a verdict. Tool unavailability must degrade, never decide.
_UNAVAILABLE_MARKERS = (
    "could not determine executable",
    "npm error",
    "ENOTFOUND",
    "ETIMEDOUT",
    "EAI_AGAIN",
    "network",
    "getaddrinfo",
    "command not found",
    "No matching version",
)


def _ran_successfully(r) -> bool:
    """True only if the tool actually executed and produced a verdict."""
    blob = (r.stdout + r.stderr).lower()
    if any(m.lower() in blob for m in _UNAVAILABLE_MARKERS):
        return False
    # A real linter reports findings. Silence plus nonzero exit is a launch failure.
    return bool(blob.strip()) or r.returncode == 0


def _try(cmd, label, timeout):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if not _ran_successfully(r):
        return None
    return (r.returncode == 0, label, (r.stdout + r.stderr).strip())


def _external(path: Path):
    """Return (ok, tool, output) or None when no external validator could run."""
    if shutil.which("redocly"):
        got = _try(["redocly", "lint", str(path)], "redocly", 180)
        if got:
            return got
    if shutil.which("openapi-spec-validator"):
        got = _try(["openapi-spec-validator", str(path)], "openapi-spec-validator", 120)
        if got:
            return got
    # Only reach for the network-fetching path if a local node_modules copy exists.
    if shutil.which("npx") and Path("node_modules/@redocly/cli").exists():
        got = _try(["npx", "--no-install", "@redocly/cli", "lint", str(path)], "redocly", 180)
        if got:
            return got
    return None


def _resolve(ref: str, doc: dict):
    node = doc
    for part in ref.lstrip("#/").split("/"):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def structural(path: Path) -> list[str]:
    errs = []
    try:
        doc = yaml.safe_load(path.read_text())
    except Exception as e:
        return [f"unparseable: {e}"]
    if not isinstance(doc, dict):
        return ["document is not a mapping"]

    for key in REQUIRED_TOP:
        if key not in doc:
            errs.append(f"missing top-level '{key}'")
    if not str(doc.get("openapi", "")).startswith("3."):
        errs.append(f"unsupported openapi version: {doc.get('openapi')!r}")

    for p, item in (doc.get("paths") or {}).items():
        if not p.startswith("/"):
            errs.append(f"path '{p}' must start with /")
        ops = {k: v for k, v in (item or {}).items() if k in HTTP_METHODS}
        if not ops:
            errs.append(f"path '{p}' declares no operations")
        for method, op in ops.items():
            where = f"{method.upper()} {p}"
            if not op.get("operationId"):
                errs.append(f"{where}: missing operationId")
            responses = op.get("responses") or {}
            if not responses:
                errs.append(f"{where}: no responses declared")
            for code, resp in responses.items():
                if not str(code).isdigit():
                    errs.append(f"{where}: non-numeric response '{code}'")
                for ct, media in ((resp or {}).get("content") or {}).items():
                    schema = (media or {}).get("schema") or {}
                    if "$ref" in schema and _resolve(schema["$ref"], doc) is None:
                        errs.append(f"{where} {code}: unresolvable $ref {schema['$ref']}")

    for name, schema in ((doc.get("components") or {}).get("schemas") or {}).items():
        if not isinstance(schema, dict):
            errs.append(f"schema '{name}' is not a mapping"); continue
        props = schema.get("properties") or {}
        for req in schema.get("required") or []:
            if req not in props:
                errs.append(f"schema '{name}': required '{req}' is not a declared property")
    return errs


def main(paths):
    rc = 0
    for raw in paths:
        p = Path(raw)
        if not p.exists():
            print(f"[schema] BLOCKED: {p} does not exist"); rc = 1; continue

        # Structural check ALWAYS runs. An external linter can add findings but can never
        # excuse us from the checks we control.
        errs = structural(p)
        if errs:
            print(f"[schema] {p.name}: INVALID")
            for e in errs:
                print(f"          - {e}")
            rc = 1
            continue

        ext = _external(p)
        if ext:
            ok, via, out = ext
            print(f"[schema] {p.name}: {'valid' if ok else 'INVALID'} (structural + {via})")
            if not ok:
                for line in out.splitlines()[:12]:
                    print(f"          {line}")
                rc = 1
        else:
            print(f"[schema] {p.name}: valid (structural; no external linter available)")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) if len(sys.argv) > 1 else 2)
