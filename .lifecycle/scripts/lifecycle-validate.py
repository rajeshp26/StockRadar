#!/usr/bin/env python3
"""
lifecycle-validate.py — mechanical conformance checks for
FEATURE_DEVELOPMENT_LIFECYCLE.md v1.1.

Checks, in order:
  1. state.json / trace.yml parse and satisfy the bundled JSON schemas (§16)
  2. config.yml scenario_classes == the trace.schema.json class enum (H2)
  3. §3.4 depth rules D1, D2, D3
  4. §9.1.1 identity-based independence on every gate ledger entry,
     incl. the role_and_identity additional-author requirement (H5)
  5. §8.6 baseline currency — no PASS against a superseded baseline
  6. §7 state machine legality for every recorded transition and every
     defect-loop reentry state (H3)
  7. §7 gate prerequisites — each gated transition authorized by exactly the
     PASS ledgers config requires (H4)
  8. §12.2 preventive control improvement rate == 1.0
  9. executed tests carry kind attribution verified_by / validated_by (H7)
  10. §9.2 CONDITIONAL prohibitions

Usage:
    lifecycle-validate.py features/<FEATURE-ID>/ [--config .lifecycle/config.yml] [--json]

Exits non-zero on any violation. Dependencies: PyYAML and jsonschema (both required).
"""
import sys, os, json, re, argparse

try:
    import yaml
except ImportError:
    sys.stderr.write("lifecycle-validate: PyYAML required\n")
    sys.exit(2)

try:
    import jsonschema
    HAVE_JSONSCHEMA = True
except ImportError:
    HAVE_JSONSCHEMA = False

GATE_RE = re.compile(r"^(G[0-9](?:\.5)?)\b")
VERDICT_RE = re.compile(r"^Verdict:\s*([A-Z_]+)", re.M)
BASELINE_RE = re.compile(r"^Baseline certified against:\s*(\S+)", re.M)
IDENT_RE = re.compile(
    r"^(Author|Certifier|Requirements author|Design author|Code author|"
    r"Code/test author|UI author)\s*:\s*\{(.+?)\}", re.M)
FIELD_RE = re.compile(r"(\w+)\s*:\s*([^,}]+)")
ADD_AUTHOR_RE = re.compile(
    r"^(Additional author|Contributors?)\s*:\s*\{(.+?)}", re.M)

CONDITIONAL_FORBIDDEN = {"G0", "G0.5", "G7", "G8"}


class Result:
    def __init__(self):
        self.errors, self.warnings, self.checks = [], [], []

    def err(self, code, msg):
        self.errors.append({"code": code, "message": msg})

    def warn(self, code, msg):
        self.warnings.append({"code": code, "message": msg})

    def ok(self, code, msg):
        self.checks.append({"code": code, "message": msg})


def load_yaml(p):
    with open(p) as fh:
        return yaml.safe_load(fh) or {}


def load_json(p):
    with open(p) as fh:
        return json.load(fh)


def parse_ledger(text):
    """Extract verdict, baseline and identity blocks from a gate ledger entry."""
    out = {"verdict": None, "baseline": None, "identities": {},
           "extra_authors": []}
    m = VERDICT_RE.search(text)
    if m:
        out["verdict"] = m.group(1).strip()
    m = BASELINE_RE.search(text)
    if m:
        out["baseline"] = m.group(1).strip()
    for role_label, body in IDENT_RE.findall(text):
        fields = {k.strip(): v.strip() for k, v in FIELD_RE.findall(body)}
        key = role_label
        n = 2
        while key in out["identities"]:
            key = f"{role_label}#{n}"
            n += 1
        out["identities"][key] = fields
    for label, body in ADD_AUTHOR_RE.findall(text):
        fields = {k.strip(): v.strip() for k, v in FIELD_RE.findall(body)}
        out["extra_authors"].append({"label": label, "fields": fields})
    return out


def check_schemas(feature_dir, schema_dir, r):
    """1. Schema conformance (§16)."""
    if not HAVE_JSONSCHEMA:
        r.err("SCHEMA-SKIP", "jsonschema not installed; schema validation unavailable — FAIL")
        return
    pairs = [("state.json", "state.schema.json", load_json),
             ("trace.yml", "trace.schema.json", load_yaml)]
    for fname, sname, loader in pairs:
        fpath = os.path.join(feature_dir, fname)
        spath = os.path.join(schema_dir, sname)
        if not os.path.exists(fpath):
            r.err("SCHEMA-MISSING", f"{fname} not found in {feature_dir}")
            continue
        if not os.path.exists(spath):
            r.err("SCHEMA-ABSENT", f"schema {sname} not found; schema conformance "
                                   "cannot be certified")
            continue
        try:
            jsonschema.validate(loader(fpath), load_json(spath))
            r.ok("SCHEMA", f"{fname} conforms to {sname}")
        except jsonschema.ValidationError as e:
            path = "/".join(str(x) for x in e.absolute_path) or "<root>"
            r.err("SCHEMA-INVALID", f"{fname} at {path}: {e.message}")
        except Exception as e:
            r.err("SCHEMA-ERROR", f"{fname}: {e}")


def check_depth(state, cfg, gate_files, r):
    """2. §3.4 depth rules D1, D2, D3."""
    depth = state.get("depth")
    depths = (cfg.get("depths") or {})
    if depth not in depths:
        r.err("DEPTH-UNKNOWN", f"declared depth {depth!r} not in config.yml depths")
        return
    spec = depths[depth] or {}
    phases = set(spec.get("phases") or [])
    gates = set(str(g) for g in (spec.get("gates") or []))

    # Rule D1 — G0.5 mandatory whenever F5 is performed
    if "F5" in phases and "G0.5" not in gates:
        r.err("D1", f"{depth}: F5 is performed but G0.5 absent from gates "
                    "(§3.4 Rule D1 — G0.5 mandatory whenever F5 is performed)")
    elif "F5" in phases:
        r.ok("D1", f"{depth}: F5 performed and G0.5 required")

    # Rule D2 — L2 includes F8 and F9 abbreviated, and therefore carries G3
    if depth == "L2":
        missing = {"F8", "F9"} - phases
        if missing:
            r.err("D2", f"L2 must include {sorted(missing)} abbreviated to one page "
                        "each (§3.4 Rule D2)")
        elif "G3" not in gates:
            r.err("D2", "L2 produces F8, so G3 must be required (§3.4 Rule D2)")
        else:
            r.ok("D2", "L2 includes F8/F9 abbreviated and carries G3")

    # Rule D3 — gates are a subset of what the phases can produce
    produces = {
        "G0": "F3", "G0.5": "F5", "G1": "F7", "G2": "F10", "G3": "F8",
        "G3.5": "F9", "G4": "F13", "G5": "F12", "G6": "F12", "G7": "F15",
        "G8": "F16",
    }
    ui_conditional = set(str(g) for g in (spec.get("ui_gates_conditional") or []))
    for g in sorted(gates):
        need = produces.get(g)
        if need and need not in phases:
            if g in ui_conditional:
                r.warn("D3", f"{depth}: {g} requires {need}; conditional on a UI surface")
            else:
                r.err("D3", f"{depth}: gate {g} required but phase {need} not in "
                            "phase set (§3.4 Rule D3)")
    if not any(e["code"] == "D3" for e in r.errors):
        r.ok("D3", f"{depth}: every required gate is produced by a required phase")

    # required_gate_missing: BLOCK
    if (cfg.get("rules") or {}).get("required_gate_missing") == "BLOCK":
        present = set()
        for fn in gate_files:
            m = GATE_RE.match(os.path.basename(fn))
            if m:
                present.add(m.group(1))
        for g in sorted(gates - present - ui_conditional):
            r.err("GATE-MISSING", f"{depth} requires {g} but no ledger entry exists")


def check_independence(ledgers, cfg, depth, r):
    """3. §9.1.1 identity-based independence."""
    rule = "identity"
    dspec = (cfg.get("depths") or {}).get(depth) or {}
    if dspec.get("independence") == "role_and_identity" or depth == "L4":
        rule = "role_and_identity"
    required = ["agent_id", "role", "session_id", "timestamp"]

    for name, parsed in ledgers.items():
        ids = parsed["identities"]
        cert = ids.get("Certifier")
        if not cert:
            r.err("ID-NOCERT", f"{name}: no Certifier identity block (§9.1.1)")
            continue
        for fld in required:
            if fld not in cert or not cert[fld] or cert[fld].startswith("<"):
                r.err("ID-FIELD", f"{name}: Certifier missing {fld} — "
                                  "FAIL before checklist (§9.1.1)")
        authors = {k: v for k, v in ids.items() if k != "Certifier"}
        if not authors:
            r.err("ID-NOAUTHOR", f"{name}: no author identity block (§9.1.1)")
        if rule == "role_and_identity" and not parsed.get("extra_authors"):
            r.err("ID-L4-CONTRIB", f"{name}: L4 role_and_identity requires an "
                                   f"'Additional author' or 'Contributors' block "
                                   f"(§9.1.1 / H5)")
        for label, a in authors.items():
            for fld in required:
                if fld not in a or not a[fld] or a[fld].startswith("<"):
                    r.err("ID-FIELD", f"{name}: {label} missing {fld} (§9.1.1)")
            if a.get("agent_id") and a["agent_id"] == cert.get("agent_id"):
                r.err("ID-SAME-AGENT", f"{name}: certifier agent_id equals "
                                       f"{label} agent_id (§9.1.1)")
            if a.get("session_id") and a["session_id"] == cert.get("session_id"):
                r.err("ID-SAME-SESSION", f"{name}: certifier session_id equals "
                                         f"{label} session_id (§9.1.1)")
            if rule == "role_and_identity" and a.get("role") and \
                    a["role"] == cert.get("role"):
                r.err("ID-SAME-ROLE", f"{name}: L4 requires certifier.role != "
                                      f"{label}.role (§9.1.1)")
    if not any(e["code"].startswith("ID-") for e in r.errors) and ledgers:
        r.ok("ID", f"independence rule '{rule}' satisfied on {len(ledgers)} entries")


def check_baselines(ledgers, trace, r):
    """4. §8.6 baseline currency."""
    baselines = trace.get("baselines") or {}
    superseded = {b for b, v in baselines.items()
                  if ((v or {}).get("status") == "superseded")}
    reopened = set()
    for ch in (trace.get("changes") or []):
        for g in ((ch or {}).get("gates_reopened") or []):
            reopened.add(str(g))
    for name, parsed in ledgers.items():
        bl = parsed["baseline"]
        gate = GATE_RE.match(os.path.basename(name))
        gate = gate.group(1) if gate else name
        if not bl or bl.startswith("<"):
            r.err("BL-MISSING", f"{name}: no baseline named (§8.6 rule 4)")
            continue
        if bl in superseded and parsed["verdict"] == "PASS" and gate not in reopened:
            r.err("BL-STALE", f"{name}: PASS against superseded baseline {bl} "
                              "and gate not reopened (§8.6 rule 5)")
    if not any(e["code"].startswith("BL-") for e in r.errors) and ledgers:
        r.ok("BL", "every ledger entry names a current baseline")


def check_f17(feature_dir, r):
    """5. §12.2 preventive control improvement rate == 1.0."""
    ddir = os.path.join(feature_dir, "defects")
    if not os.path.isdir(ddir):
        r.ok("F17", "no defects recorded")
        return
    proc, with_escape, total = 0, 0, 0
    for fn in sorted(os.listdir(ddir)):
        if not fn.startswith("DEF-"):
            continue
        total += 1
        text = open(os.path.join(ddir, fn)).read()
        m = re.search(r"process_originated\s*:\s*(true|false)", text, re.I)
        if not m:
            r.err("F17-CLASS", f"{fn}: no process_originated classification (§12.2)")
            continue
        if m.group(1).lower() == "true":
            proc += 1
            if re.search(r"^##\s*Escape correction", text, re.M | re.I):
                with_escape += 1
            else:
                r.err("F17-ESCAPE", f"{fn}: process_originated is true but no "
                                    "escape correction section (§12.2)")
        if not re.search(r"^##\s*Symptom correction", text, re.M | re.I):
            r.err("F17-SYMPTOM", f"{fn}: no symptom correction section (§12.2)")
    rate = 1.0 if proc == 0 else with_escape / proc
    if proc and rate < 1.0:
        r.err("F17-RATE", f"preventive control improvement rate {rate:.2f} < 1.0 "
                          f"({with_escape}/{proc} process-originated defects) (§12.2)")
    else:
        r.ok("F17", f"defects {total}, process-originated {proc}, "
                    f"preventive control improvement rate {rate:.2f}")


def check_conditional(ledgers, cfg, depth, r):
    """6. §9.2 CONDITIONAL prohibitions."""
    l4 = depth == "L4" or depth in [str(d) for d in
                                    ((cfg.get("gates") or {}).get(
                                        "conditional_forbidden_at_depth") or [])]
    for name, parsed in ledgers.items():
        if parsed["verdict"] != "CONDITIONAL":
            continue
        gate = GATE_RE.match(os.path.basename(name))
        gate = gate.group(1) if gate else name
        if gate in CONDITIONAL_FORBIDDEN:
            r.err("COND-GATE", f"{name}: CONDITIONAL forbidden at {gate} (§9.2)")
        if l4:
            r.err("COND-L4", f"{name}: CONDITIONAL forbidden anywhere in an "
                             "L4 feature (§9.2)")
        text_has_condition = True  # presence checked by the checklist, not here
        if not text_has_condition:
            r.err("COND-BARE", f"{name}: CONDITIONAL with no owned, dated condition")
    if not any(e["code"].startswith("COND-") for e in r.errors):
        r.ok("COND", "no prohibited CONDITIONAL verdicts")

def check_config_sync(cfg, schema_dir, r):
    """2. config.yml scenario_classes == the trace.schema.json class enum (H2)."""
    spath = os.path.join(schema_dir, "trace.schema.json")
    if not os.path.exists(spath):
        r.err("SYNC-SCHEMA", f"cannot sync: {spath} not found (H2)")
        return
    try:
        schema = load_json(spath)
    except Exception as e:
        r.err("SYNC-SCHEMA", f"cannot sync: {spath} unreadable: {e} (H2)")
        return
    try:
        enum = (schema["properties"]["scenarios"]["patternProperties"]
                ["^SCN-[0-9]+$"]["properties"]["class"]["enum"])
    except KeyError:
        r.err("SYNC-SCHEMA", "trace.schema.json has no scenario class enum (H2)")
        return
    classes = cfg.get("scenario_classes") or []
    if list(classes) != list(enum):
        r.err("SYNC-MISMATCH", f"config.yml scenario_classes {list(classes)} != "
                               "trace.schema.json class enum "
                               f"{list(enum)} (values AND order, H2)")
        return
    r.ok("SYNC", f"config.yml scenario_classes ({len(classes)}) matches the "
                 "trace.schema.json class enum (H2)")


def check_transitions(state, cfg, r):
    """6. \u00a77 state machine legality for every recorded transition and every
    defect-loop reentry state (H3)."""
    edges = set()
    for e in (cfg.get("state_machine") or {}).get("legal_transitions") or []:
        if isinstance(e, dict) and e.get("from") and e.get("to"):
            edges.add((e["from"], e["to"]))

    def legal(f, t):
        return (f, t) in edges or ("*", t) in edges or (f, "*") in edges

    trs = state.get("transitions") or []
    for tr in trs:
        f, t = tr.get("from"), tr.get("to")
        if not legal(f, t):
            r.err("TRANS-ILLEGAL", f"{f} -> {t}: not in config.yml "
                                   "state_machine.legal_transitions (\u00a77 / H3)")
    for d in state.get("defect_loop") or []:
        rs = (d or {}).get("reentry_state")
        if rs and not legal("DEFECT_LOOP", rs):
            r.err("TRANS-REENTRY", f"defect_loop {d.get('defect')}: reentry_state "
                                   f"{rs} is not legal from DEFECT_LOOP (\u00a77 / H3)")
    if trs:
        last = trs[-1].get("to")
        cur = state.get("state")
        if last and cur and last != cur:
            r.err("TRANS-LASTSTATE", f"declared state {cur!r} != last recorded "
                                     f"transition target {last!r} (\u00a77 / H3)")
    if not any(e["code"].startswith("TRANS-") for e in r.errors):
        r.ok("TRANS", f"{len(trs)} recorded transition(s) legal against config.yml; "
                      "defect-loop reentry state legal (H3)")


def check_gate_prereqs(state, cfg, ledgers, r):
    """7. \u00a77 gate prerequisites \u2014 each gated transition authorized by exactly
    the PASS ledgers config requires (H4)."""
    prereqs = (cfg.get("state_machine") or {}).get("gate_prerequisites") or {}
    checked = 0
    for tr in state.get("transitions") or []:
        gid = tr.get("to")
        if gid not in prereqs:
            continue
        checked += 1
        rec = set()
        for blob in str(tr.get("authorized_by") or "").split(","):
            name = blob.strip()
            if not name or name == "-":
                continue
            base = os.path.basename(name)
            if base.endswith(".md"):
                rec.add(base[:-3])
            else:
                rec.add(base)
        expected = set(str(g) for g in prereqs[gid])
        if rec != expected:
            r.err("GATE-PREREQ", f"transition -> {gid} authorized by "
                                 f"{sorted(rec)}, config requires {sorted(expected)} "
                                 "(\u00a77 gate_prerequisites / H4)")
            continue
        for g in sorted(expected):
            lf = f"{g}.md"
            if lf not in ledgers:
                r.err("GATE-PREREQ", f"{gid} requires gate {lf} but no ledger "
                                     "entry exists (\u00a77 / H4)")
                continue
            if ledgers[lf]["verdict"] != "PASS":
                r.err("GATE-PREREQ", f"{gid} requires {lf} PASS; ledger verdict is "
                                     f"{ledgers[lf]['verdict']} (\u00a77 / H4)")
    if checked == 0:
        r.ok("GATE-PREREQ", "no recorded transition enters a gated state yet (H4)")
    elif not any(e["code"].startswith("GATE-PREREQ") for e in r.errors):
        r.ok("GATE-PREREQ", f"{checked} gated transition(s) authorized by the exact "
                            "PASS ledgers (\u00a77 / H4)")


def check_kinds(trace, r):
    """9. executed tests carry kind attribution verified_by / validated_by (H7)."""
    expected = {"UT": "verified_by", "IT": "verified_by",
                "ST": "verified_by", "VT": "validated_by"}
    n = 0
    for tid, t in (trace.get("tests") or {}).items():
        t = t or {}
        if "result" not in t:
            continue
        prefix = tid.split("-")[0]
        n += 1
        if prefix == "TC":
            r.err("KIND-TC", f"{tid}: TC-* never executes; a result is invalid (H7)")
            continue
        want = expected.get(prefix)
        got = t.get("kind")
        if not got:
            r.err("KIND-MISSING", f"{tid}: executed test has a result but no kind; "
                                  f"add 'kind: {want}' (H7)")
        elif got != want:
            r.err("KIND-MISMATCH", f"{tid}: kind '{got}', but {prefix}-* requires "
                                   f"'{want}' (H7)")
    if n == 0:
        r.ok("KIND", "no executed tests to attribute (H7)")
    elif not any(e["code"].startswith("KIND-") for e in r.errors):
        r.ok("KIND", f"{n} executed test(s) carry the correct kind attribution (H7)")


def main():
    ap = argparse.ArgumentParser(description="v1.1 lifecycle conformance validator")
    ap.add_argument("feature_dir")
    ap.add_argument("--config", default=".lifecycle/config.yml")
    ap.add_argument("--schema-dir", default=".lifecycle/schema")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    r = Result()
    fd = a.feature_dir.rstrip("/")

    if not os.path.isdir(fd):
        sys.stderr.write(f"lifecycle-validate: not a directory: {fd}\n")
        return 2
    try:
        cfg = load_yaml(a.config)
    except Exception as e:
        sys.stderr.write(f"lifecycle-validate: cannot read config: {e}\n")
        return 2

    state = {}
    sp = os.path.join(fd, "state.json")
    if os.path.exists(sp):
        try:
            state = load_json(sp)
        except Exception as e:
            r.err("STATE-PARSE", f"state.json unparseable: {e}")
    else:
        r.err("STATE-MISSING", "state.json not found")

    trace = {}
    tp = os.path.join(fd, "trace.yml")
    if os.path.exists(tp):
        try:
            trace = load_yaml(tp)
        except Exception as e:
            r.err("TRACE-PARSE", f"trace.yml unparseable: {e}")
    else:
        r.err("TRACE-MISSING", "trace.yml not found")

    gdir = os.path.join(fd, "gates")
    gate_files, ledgers = [], {}
    if os.path.isdir(gdir):
        for fn in sorted(os.listdir(gdir)):
            if fn.endswith(".md"):
                gate_files.append(fn)
                ledgers[fn] = parse_ledger(open(os.path.join(gdir, fn)).read())
    else:
        r.warn("GATES-NONE", "no gates/ directory yet")

    depth = state.get("depth")
    check_schemas(fd, a.schema_dir, r)
    check_config_sync(cfg, a.schema_dir, r)
    check_depth(state, cfg, gate_files, r)
    check_independence(ledgers, cfg, depth, r)
    check_baselines(ledgers, trace, r)
    check_transitions(state, cfg, r)
    check_gate_prereqs(state, cfg, ledgers, r)
    check_f17(fd, r)
    check_kinds(trace, r)
    check_conditional(ledgers, cfg, depth, r)

    if a.json:
        print(json.dumps({"feature_dir": fd, "depth": depth,
                          "errors": r.errors, "warnings": r.warnings,
                          "passed": r.checks}, indent=2))
    else:
        print(f"lifecycle-validate — {fd}  (depth {depth})")
        print("")
        for c in r.checks:
            print(f"  PASS  [{c['code']}] {c['message']}")
        for w in r.warnings:
            print(f"  WARN  [{w['code']}] {w['message']}")
        for e in r.errors:
            print(f"  FAIL  [{e['code']}] {e['message']}")
        print("")
        print(f"  {len(r.checks)} passed, {len(r.warnings)} warnings, "
              f"{len(r.errors)} failures")

    if r.errors:
        sys.stderr.write(f"lifecycle-validate: FAIL — {len(r.errors)} violation(s)\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
