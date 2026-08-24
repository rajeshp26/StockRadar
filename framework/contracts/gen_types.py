#!/usr/bin/env python3
"""Generate types from the OpenAPI contract for both consumers.

Types are GENERATED, never hand-written. `--check` regenerates into memory and diffs against
what is committed, so contract drift fails a gate instead of being discovered at runtime.
"""
import argparse
import difflib
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("BLOCKED: pyyaml required"); sys.exit(2)

PY_T = {"string": "str", "integer": "int", "number": "float",
        "boolean": "bool", "array": "list", "object": "dict"}
TS_T = {"string": "string", "integer": "number", "number": "number",
        "boolean": "boolean", "array": "unknown[]", "object": "Record<string, unknown>"}

BANNER = "# GENERATED from {src} — do not edit by hand. Regenerate: framework/contracts/gen_types.py\n"
TS_BANNER = "// GENERATED from {src} — do not edit by hand.\n"


def _schemas(doc):
    return (doc.get("components") or {}).get("schemas") or {}


def python(doc, src):
    out = [BANNER.format(src=src), "from typing import TypedDict, Literal, NotRequired\n\n"]
    for name, s in _schemas(doc).items():
        req = set(s.get("required") or [])
        out.append(f"class {name}(TypedDict):\n")
        props = s.get("properties") or {}
        if not props:
            out.append("    pass\n\n"); continue
        for pname, p in props.items():
            if "enum" in p:
                t = "Literal[" + ", ".join(repr(v) for v in p["enum"]) + "]"
            else:
                t = PY_T.get(p.get("type", "object"), "object")
            out.append(f"    {pname}: {t}\n" if pname in req
                       else f"    {pname}: NotRequired[{t}]\n")
        out.append("\n")
    return "".join(out)


def typescript(doc, src):
    out = [TS_BANNER.format(src=src), "\n"]
    for name, s in _schemas(doc).items():
        req = set(s.get("required") or [])
        out.append(f"export interface {name} {{\n")
        for pname, p in (s.get("properties") or {}).items():
            if "enum" in p:
                t = " | ".join(f'"{v}"' for v in p["enum"])
            else:
                t = TS_T.get(p.get("type", "object"), "unknown")
            out.append(f"  {pname}{'' if pname in req else '?'}: {t};\n")
        out.append("}\n\n")
    return "".join(out)


# Target paths are DERIVED from the contract id, not hardcoded. A single fixed target means
# the second contract silently overwrites the first — which reads as type drift and fails the
# gate for entirely the wrong reason.
GENERATORS = {
    "python": ("src/backend/contracts/{slug}.py", python),
    "typescript": ("src/frontend/contracts/{slug}.ts", typescript),
}


def contract_slug(schema_path: Path) -> str:
    """api-004.openapi.yaml -> api_004"""
    return schema_path.name.split(".")[0].replace("-", "_").lower()


def targets_for(schema_path: Path):
    slug = contract_slug(schema_path)
    return {lang: (tmpl.format(slug=slug), fn) for lang, (tmpl, fn) in GENERATORS.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--schema", default=".planning/contracts/api-004.openapi.yaml")
    ap.add_argument("--check", action="store_true",
                    help="fail if committed types differ from regenerated types")
    a = ap.parse_args()

    src = Path(a.schema)
    if not src.exists():
        print(f"[types] no schema at {src}"); return 0
    doc = yaml.safe_load(src.read_text())

    rc = 0
    for lang, (rel, fn) in targets_for(src).items():
        body = fn(doc, src.name)
        dest = Path(rel)
        if a.check:
            if not dest.exists():
                print(f"[types] MISSING generated {lang} types at {rel}"); rc = 1; continue
            have = dest.read_text()
            if have != body:
                print(f"[types] DRIFT in {rel} — regenerate; implementation may not match contract")
                for line in list(difflib.unified_diff(
                        have.splitlines(), body.splitlines(),
                        fromfile="committed", tofile="regenerated", lineterm=""))[:14]:
                    print(f"          {line}")
                rc = 1
            else:
                print(f"[types] {rel}: in sync")
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(body)
            print(f"[types] wrote {rel}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
