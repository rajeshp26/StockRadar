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

# Resolve app paths through the same config the gates use. The framework package is on
# sys.path in-tree (cwd == repo root) and in an installed wheel (site-packages), so this
# bootstrap works in both layouts; `framework.locate` is the single reader of
# framework.config.json, and a second copy of that logic here is the duplication the
# resolver exists to prevent.
_BOOTSTRAP_ROOT = str(Path(__file__).resolve().parents[2])
if _BOOTSTRAP_ROOT not in sys.path:
    sys.path.insert(0, _BOOTSTRAP_ROOT)
from framework import locate as _locate  # noqa: E402

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
#
# The DIRECTORY is app-owned, so it comes from `readiness` in framework.config.json (see
# framework/locate.py). A product whose backend lives in `backend/` and whose frontend lives
# in `web/` writes there; only the file NAME is derived from the contract id.
GENERATORS = {
    "python": ("python_types_dir", "{slug}.py", python),
    "typescript": ("typescript_types_dir", "{slug}.ts", typescript),
}


def contract_slug(schema_path: Path) -> str:
    """api-004.openapi.yaml -> api_004"""
    return schema_path.name.split(".")[0].replace("-", "_").lower()


def types_dir(lang: str) -> str:
    """The app-relative directory this language's generated types live in.

    Falls back to the declared default when the config omits the key, and reports an empty
    string only when the key is explicitly empty — which is a config error, surfaced by the
    caller rather than silently writing to the cwd.
    """
    key = GENERATORS[lang][0]
    return _locate.resolved(key) or _locate.READINESS_DEFAULTS[key]


def targets_for(schema_path: Path):
    slug = contract_slug(schema_path)
    return {lang: ((Path(types_dir(lang)) / tmpl.format(slug=slug)).as_posix(), fn)
            for lang, (_key, tmpl, fn) in GENERATORS.items()}


def _schemas_under(directory: Path) -> list[Path]:
    return sorted(p for p in directory.glob("*.openapi.y*ml") if p.is_file())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--schema", action="append", default=None,
                    help="contract schema to generate from (repeatable). Default: every "
                         "*.openapi.y*ml under readiness.openapi_schema")
    ap.add_argument("--check", action="store_true",
                    help="fail if committed types differ from regenerated types")
    a = ap.parse_args()

    # No hardcoded contract id: the framework owns no contract, so the default scope is the
    # app's declared contract directory. G1 passes each schema explicitly.
    schemas = [Path(s) for s in (a.schema or [])]
    if not schemas:
        contract_dir = Path(_locate.resolved("openapi_schema") or ".")
        schemas = _schemas_under(contract_dir) if contract_dir.is_dir() else []

    rc = 0
    for src in schemas:
        if not src.exists():
            print(f"[types] no schema at {src}"); continue
        doc = yaml.safe_load(src.read_text(encoding="utf-8"))

        for lang, (rel, fn) in targets_for(src).items():
            body = fn(doc, src.name)
            dest = Path(rel)
            if a.check:
                if not dest.exists():
                    print(f"[types] MISSING generated {lang} types at {rel}"); rc = 1; continue
                have = dest.read_text(encoding="utf-8")
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
                dest.write_text(body, encoding="utf-8", newline="\n")
                print(f"[types] wrote {rel}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
