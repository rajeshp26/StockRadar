#!/usr/bin/env python3
"""Gate routing -- turn a verification matrix into the gate set that must run.

WHY THIS EXISTS
===============
``framework/verifier/profiles.yaml`` has carried an ``impact_to_gates`` table since the
framework was written. Nothing executed it: ``validate.py`` asserted the *string*
``impact_to_gates`` appeared in the file, and ``telemetry/report.py`` counted its entries.
Neither can fail when no task is routed through it, which is why a green run could prove
nothing about the product.

This module is the executable consumer. It reads the routing tables and the matrix rows
(whose gates come from ``evidence_classes.yaml``) and returns one ordered, deduplicated
gate list. ``matrix.py emit`` stores that list as ``required_gates``; ``g19_closure.sh``
judges whether it was honoured.

Two input dimensions are kept separate on purpose:

    breadth  impact_to_gates[scope]        how wide the change is
    depth    row["gates"]                  how strong the evidence for a criterion must be

Collapsing them into one flat map would lose the distinction between "this touches many
components" and "this claim needs a real browser and a real database". They are joined here,
in one function, and recorded in one artifact -- that is normalisation, not vocabulary drift.

Usage:
  python3 framework/verifier/route.py --matrix PLAN.matrix.json [--root DIR] [--json]
  python3 framework/verifier/route.py --impact cross_component --gates g6,g17 [--json]
  python3 framework/verifier/route.py --self-test
Exit: 0 routed | 1 a routing table names a gate with no implementation | 2 BLOCKED
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

PROFILES_REL = os.path.join("framework", "verifier", "profiles.yaml")
GATES_DIR_REL = os.path.join("framework", "gates")
GATE_ID_RE = re.compile(r"^g[0-9]+$|^g_entry$|^g_exec$|^g_skill_coverage$|^g_skill_use$|^g_sandbox$|^g_tool_readiness$|^g_tool_utilization$|^g_telemetry_live$")
ROUTING_KEYS = ("impact_to_gates", "shape_to_gates", "event_to_gates", "risk_signal_to_gates")


class RouteError(Exception):
    """Profiles unreadable, or a routing table that cannot be trusted."""


def load_profiles(root="."):
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RouteError("pyyaml unavailable; cannot read %s" % PROFILES_REL) from exc
    path = os.path.join(root, PROFILES_REL)
    if not os.path.isfile(path):
        raise RouteError("profiles missing: %s" % PROFILES_REL)
    try:
        with open(path, encoding="utf-8-sig") as fh:
            data = yaml.safe_load(fh) or {}
    except (OSError, ValueError) as exc:
        raise RouteError("profiles unreadable: %s" % exc) from exc
    if not isinstance(data, dict):
        raise RouteError("profiles root is not a mapping")
    return data


def _add(out, gates):
    for gate in gates or []:
        gate = str(gate).strip()
        if gate and gate not in out:
            out.append(gate)


def routed_gates(impact, rows, profiles, signals=()):
    """Ordered union of breadth gates, per-criterion gates and fired risk-signal gates."""
    out = []
    scope = (impact or {}).get("scope")
    impact_map = profiles.get("impact_to_gates") or {}
    if scope and scope not in impact_map:
        raise RouteError("impact scope %r is not a key in impact_to_gates (known: %s)"
                         % (scope, ", ".join(sorted(impact_map))))
    _add(out, impact_map.get(scope))
    for row in rows or []:
        _add(out, row.get("gates"))
    signal_map = profiles.get("risk_signal_to_gates") or {}
    for signal in signals or []:
        if signal not in signal_map:
            raise RouteError("risk signal %r is not a key in risk_signal_to_gates (known: %s)"
                             % (signal, ", ".join(sorted(signal_map))))
        _add(out, signal_map.get(signal))
    return out


def gate_implementations(root="."):
    """Gate ids that have a ``framework/gates/<id>_*.sh`` implementation."""
    gates_dir = os.path.join(root, GATES_DIR_REL)
    found = set()
    if not os.path.isdir(gates_dir):
        return found
    for name in os.listdir(gates_dir):
        if not name.endswith(".sh") or name.startswith("_"):
            continue
        if name.startswith("test_"):
            continue
        stem = name[:-3]
        found.add(stem.split("_", 1)[0] if re.match(r"^g[0-9]+_", stem) else stem)
    return found


def unknown_gates(gate_ids, root="."):
    """Routing entries that name a gate with no implementation.

    A table that routes to a gate which does not exist is a routing gap dressed as
    coverage -- the same failure as a check that cannot fail. Naming it is the point.
    """
    known = gate_implementations(root)
    out = []
    for gate in gate_ids:
        if not GATE_ID_RE.match(gate):
            out.append("%s (not a gate id)" % gate)
        elif gate not in known:
            out.append("%s (no framework/gates/%s_*.sh)" % (gate, gate))
    return out


def _self_test():
    failures = []

    def eq(name, got, want):
        if got != want:
            failures.append("%s: got %r want %r" % (name, got, want))

    profiles = {
        "impact_to_gates": {
            "local": ["g2", "g4", "g9"],
            "cross_component": ["g1", "g2", "g3", "g4", "g5", "g9"],
        },
        "risk_signal_to_gates": {"visible_behaviour": ["g6"]},
    }
    rows = [{"gates": ["g17"]}, {"gates": ["g6", "g17"]}]
    got = routed_gates({"scope": "cross_component"}, rows, profiles)
    eq("union order", got, ["g1", "g2", "g3", "g4", "g5", "g9", "g17", "g6"])

    got = routed_gates({"scope": "local"}, [], profiles, signals=["visible_behaviour"])
    eq("signal gate", got, ["g2", "g4", "g9", "g6"])

    try:
        routed_gates({"scope": "galaxy"}, [], profiles)
        failures.append("unknown scope was accepted")
    except RouteError:
        pass

    if failures:
        for f in failures:
            print("FAIL " + f)
        return 1
    print("route self-test: PASS")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="route a verification matrix to gates")
    ap.add_argument("--matrix")
    ap.add_argument("--impact")
    ap.add_argument("--gates", default="")
    ap.add_argument("--signals", default="")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)

    if a.self_test:
        return _self_test()

    try:
        profiles = load_profiles(a.root)
        if a.matrix:
            with open(a.matrix, encoding="utf-8-sig") as fh:
                matrix = json.load(fh)
            impact = matrix.get("impact") or {}
            rows = matrix.get("rows") or []
            signals = matrix.get("signals") or []
        else:
            impact = {"scope": a.impact}
            rows = [{"gates": [g.strip() for g in a.gates.split(",") if g.strip()]}]
            signals = [s.strip() for s in a.signals.split(",") if s.strip()]
        gates = routed_gates(impact, rows, profiles, signals)
    except (RouteError, OSError, ValueError) as exc:
        print("[route] BLOCKED %s" % exc)
        return 2

    unknown = unknown_gates(gates, a.root)
    if unknown:
        print("[route] FAIL routing names gate(s) with no implementation: %s" % "; ".join(unknown))
        return 1

    if a.json:
        print(json.dumps({"impact": impact, "signals": signals, "required_gates": gates}))
    else:
        print("required_gates: " + ", ".join(gates))
    return 0


if __name__ == "__main__":
    sys.exit(main())
