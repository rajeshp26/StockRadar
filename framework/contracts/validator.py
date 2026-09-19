"""Minimal JSON-Schema subset validator for contract tests.

Supports the OpenAPI 3 subset the contracts actually use: type, required,
additionalProperties, enum, minLength, minimum, $ref. Uses `jsonschema` when installed.
Kept small deliberately — this validates contracts, it is not a general schema engine.
"""
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

try:
    import jsonschema  # noqa
    _HAVE_JSONSCHEMA = True
except ImportError:
    _HAVE_JSONSCHEMA = False

# DID-013 PR-B: the active engine must be observable. A run without jsonschema
# is a subset-mode run, never an indistinguishable "validated" run — repo rule
# "tool unavailability is never a verdict": unavailable must be explicit, never
# silent. The mode is emitted once per process, on first validation, to stderr.
VALIDATOR_MODE = "jsonschema" if _HAVE_JSONSCHEMA else "subset"
_MODE_EMITTED = False


def validator_mode() -> str:
    """Return the active validation engine: 'jsonschema' or 'subset'."""
    return VALIDATOR_MODE


def _emit_mode_once():
    global _MODE_EMITTED
    if not _MODE_EMITTED:
        _MODE_EMITTED = True
        print(f"[contract-validator] mode: {VALIDATOR_MODE}", file=sys.stderr)


_TYPES = {"string": str, "integer": int, "number": (int, float),
          "boolean": bool, "array": list, "object": dict}


def _deref(schema, doc):
    seen = 0
    while isinstance(schema, dict) and "$ref" in schema and seen < 10:
        node, seen = doc, seen + 1
        for part in schema["$ref"].lstrip("#/").split("/"):
            node = (node or {}).get(part)
        schema = node
    return schema or {}


def validate_instance(inst, schema, doc, path="$"):
    """Return a list of violation strings. Empty means valid."""
    _emit_mode_once()
    schema = _deref(schema, doc)
    errs = []

    if _HAVE_JSONSCHEMA:
        import jsonschema
        resolver = jsonschema.RefResolver.from_schema(doc)
        v = jsonschema.Draft7Validator(schema, resolver=resolver)
        return [f"{'.'.join(str(p) for p in e.absolute_path) or '$'}: {e.message}"
                for e in v.iter_errors(inst)]

    t = schema.get("type")
    if t and t in _TYPES:
        if t == "integer" and isinstance(inst, bool):
            return [f"{path}: expected integer, got bool"]
        if not isinstance(inst, _TYPES[t]):
            return [f"{path}: expected {t}, got {type(inst).__name__}"]

    if "enum" in schema and inst not in schema["enum"]:
        errs.append(f"{path}: {inst!r} not in enum {schema['enum']}")
    if isinstance(inst, str) and "minLength" in schema and len(inst) < schema["minLength"]:
        errs.append(f"{path}: shorter than minLength {schema['minLength']}")
    if isinstance(inst, (int, float)) and not isinstance(inst, bool) and "minimum" in schema \
            and inst < schema["minimum"]:
        errs.append(f"{path}: below minimum {schema['minimum']}")

    if isinstance(inst, dict):
        props = schema.get("properties") or {}
        for req in schema.get("required") or []:
            if req not in inst:
                errs.append(f"{path}: missing required '{req}'")
        if schema.get("additionalProperties") is False:
            for extra in set(inst) - set(props):
                errs.append(f"{path}: additional property '{extra}' not permitted")
        for k, v in inst.items():
            if k in props:
                errs += validate_instance(v, props[k], doc, f"{path}.{k}")

    if isinstance(inst, list) and "items" in schema:
        for i, item in enumerate(inst):
            errs += validate_instance(item, schema["items"], doc, f"{path}[{i}]")
    return errs


@dataclass
class Contract:
    doc: dict

    def statuses(self, path, method):
        return list((((self.doc.get("paths") or {}).get(path) or {})
                     .get(method) or {}).get("responses", {}).keys())

    def response_schema(self, path, method, status):
        resp = ((((self.doc.get("paths") or {}).get(path) or {})
                 .get(method) or {}).get("responses") or {}).get(status)
        if not resp:
            return None
        for media in (resp.get("content") or {}).values():
            if "schema" in media:
                return media["schema"]
        return None

    def request_schema(self, path, method):
        rb = (((self.doc.get("paths") or {}).get(path) or {})
              .get(method) or {}).get("requestBody") or {}
        for media in (rb.get("content") or {}).values():
            if "schema" in media:
                return media["schema"]
        return None


def load_contract(path) -> Contract:
    return Contract(yaml.safe_load(Path(path).read_text()))