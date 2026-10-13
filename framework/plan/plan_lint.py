#!/usr/bin/env python3
"""Plan lint -- DID-016. Deterministic checks on a plan file before dispatch.

Purpose: a plan can satisfy g_entry (approved, scope declared, criteria present) and still be
a bad breakdown: vague criteria, no evidence class, no real-stack check, unknowns never
gathered, new code with no reuse search, unresolvable dependencies, edits after approval.
This script checks those properties mechanically. It judges STRUCTURE and CITED EVIDENCE;
it cannot judge whether a criterion is the RIGHT one. That stays with the reviewer.

Stdlib only (no pyyaml): runs on a clean Windows PowerShell 5.1 host. The plan parser mirrors
g_entry.sh (top-level `key:` at column 0, block `- item` list or one-line `[a, b]` list) so the
lint sees exactly what the gate sees.

Exit: 0 no errors (warnings allowed) | 1 one or more errors | 2 BLOCKED (plan unreadable)
Output: one line per finding:  [plan_lint] ERROR|WARN <RULE> <where>: <message>

Usage:
  python3 framework/plan/plan_lint.py PLAN.md [--root DIR] [--state-root DIR] [--json]
  python3 framework/plan/plan_lint.py PLAN.md --stamp     # write approval_hash (human step)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys

# Tunable limits. Warnings, not errors: size is a judgement call the reviewer finishes.
MAX_FILES = 10
MAX_CRITERIA = 8
EVIDENCE_TAGS = ("unit", "integration", "e2e", "browser", "contract", "data-invariant",
                 "static", "manual")
GOAL_TAGS = ("e2e", "browser", "data-invariant")
REAL_TAGS = ("integration", "e2e", "browser", "data-invariant")
DISCOVERY_CATEGORIES = ("code", "architecture", "design", "environment", "data")
SKILL = "see skill task-breakdown"

VAGUE = [
    r"\bworks?\s+(correctly|properly|as expected|fine|well)\b",
    r"\bproperly\b", r"\bas expected\b", r"\bis\s+(correct|fine|good|working)\b",
    r"\bshould work\b", r"\bappropriately\b", r"\bgracefully\b", r"\blooks?\s+(good|right)\b",
    r"\buser[- ]friendly\b", r"\brobust\b", r"\bintuitive\b", r"\ball\s+(cases|scenarios)\b",
]
COMPARATORS = (r"\b(equals?|exceeds?|at most|at least|no more than|no less than|within|"
               r"returns?|raises?|rejects?|emits?|records?|persists?|displays?|renders?|"
               r"matches|differs?|unchanged|identical|greater|less|between|only|never|"
               r"exactly|per|for every|for each)\b")
MOCK = re.compile(r"(?<!no )(?<!without )(?<!not )(?<!zero )\b(mock(?:ed|s|ing)?|stub(?:bed|s)?|"
                  r"fake[ds]?|patch(?:ed|es)?)\b", re.I)
SKIP_DIRS = {".git", "node_modules", ".planning", ".lifecycle", ".opencode", "__pycache__",
             "dist", "build", ".venv", "venv", "archive"}
CODE_EXT = (".py", ".js", ".ts", ".tsx", ".mjs", ".sql", ".sh")
STOP = {"which", "their", "these", "those", "there", "where", "shared", "common", "helper",
        "utility", "function", "module", "class", "should", "using", "with", "from", "into"}


# ---------------------------------------------------------------- parsing (mirrors g_entry)
def _clean(item):
    item = item.strip()
    if len(item) >= 2 and item[0] == item[-1] and item[0] in "\"'":
        item = item[1:-1]
    return item.strip()


def parse_plan(text):
    """Return {key: {"items": [...], "inline": bool, "scalar": str}} for top-level keys."""
    lines = text.replace("\r", "").split("\n")
    keys = {}
    i = 0
    key_re = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):[ \t]*(.*)$")
    while i < len(lines):
        m = key_re.match(lines[i])
        if not m:
            i += 1
            continue
        key, rest = m.group(1), m.group(2).strip()
        entry = {"items": [], "inline": False, "scalar": rest}
        if rest.startswith("["):
            inner = re.match(r"^\[([^\]]*)\]", rest)  # g_entry stops at the first ']'
            if inner:
                entry["inline"] = True
                entry["items"] = [_clean(x) for x in inner.group(1).split(",") if _clean(x)]
        elif rest == "":
            j = i + 1
            while j < len(lines):
                ln = lines[j]
                bm = re.match(r"^[ \t]*-[ \t]+(.*)$", ln)
                if bm:
                    it = _clean(bm.group(1))
                    if it:
                        entry["items"].append(it)
                elif ln.strip():
                    break  # g_entry's awk exits on the first non-list, non-blank line
                j += 1
        keys[key] = entry
        i += 1
    return keys


def approval_digest(text):
    kept = []
    for ln in text.replace("\r", "").split("\n"):
        if re.match(r"^(approval_hash|status|approved|accepted):", ln, re.I):
            continue
        kept.append(ln.rstrip())
    return hashlib.sha256("\n".join(kept).strip().encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- findings
class Findings:
    def __init__(self):
        self.rows = []

    def add(self, sev, rule, where, msg):
        self.rows.append({"severity": sev, "rule": rule, "where": where, "message": msg})

    def err(self, rule, where, msg):
        self.add("ERROR", rule, where, msg + " (" + SKILL + ")")

    def warn(self, rule, where, msg):
        self.add("WARN", rule, where, msg + " (" + SKILL + ")")


# ---------------------------------------------------------------- criteria rules
CRIT_RE = re.compile(r"^(AC-\d+)\s+\[([A-Za-z0-9-]+)\]\s+(.*)$")


def check_criteria(keys, f):
    ac = keys.get("acceptance_criteria", {"items": [], "inline": False})
    items = ac["items"]
    if ac.get("inline") and items:
        f.warn("PL00", "acceptance_criteria",
               "one-line list form splits on commas and stops at the first ']'; use a "
               "block list (one '- AC-n [tag] text' per line) so criteria stay intact")
    if len(items) > MAX_CRITERIA:
        f.warn("PL02", "acceptance_criteria",
               "%d criteria (> %d): the plan is probably several tasks; split it" %
               (len(items), MAX_CRITERIA))
    tags_seen = []
    seen_ids = set()
    for n, raw in enumerate(items, 1):
        m = CRIT_RE.match(raw)
        where = m.group(1) if m else "criterion %d" % n
        if not m:
            f.err("PL03", where, "criterion lacks '<AC-n> [evidence-tag]' prefix: %r" %
                  raw[:70])
            body, tag = raw, None
        else:
            cid, tag, body = m.group(1), m.group(2).lower(), m.group(3)
            if cid in seen_ids:
                f.err("PL03", where, "duplicate criterion id")
            seen_ids.add(cid)
            if tag not in EVIDENCE_TAGS:
                f.err("PL03", where, "unknown evidence tag [%s]; allowed: %s" %
                      (tag, ", ".join(EVIDENCE_TAGS)))
            elif tag == "manual":
                f.warn("PL03", where, "[manual] is reasoning, not executable evidence "
                       "(AGENTS.md Evidence); justify or choose an executable class")
            tags_seen.append(tag)
        low = body.lower()
        vague = any(re.search(p, low) for p in VAGUE)
        anchored = bool(re.search(r"\d", body) or re.search(r"[`'\"]", body)
                        or re.search(COMPARATORS, low)
                        or re.search(r"[A-Za-z]+_[A-Za-z]+|\w+\(\)|/|\.py\b|[a-z][A-Z]", body))
        if vague and not anchored:
            f.err("PL01", where, "vague and unobservable: %r. State the input, the "
                  "observable output or value, and a threshold" % body[:80])
        elif len(body.split()) < 5:
            f.warn("PL01", where, "very short criterion; is it observable? %r" % body[:60])
        if low.count(" and ") >= 3 or body.count(";") >= 2:
            f.warn("PL02", where, "compound criterion (several outcomes in one); split it")
        if tag in REAL_TAGS and MOCK.search(body):
            f.err("PL04", where, "tagged [%s] but the text relies on mocks/stubs/fakes; "
                  "mocked evidence is [unit], not real-stack evidence" % tag)
    if items and not any(t in GOAL_TAGS for t in tags_seen if t):
        f.err("PL04", "acceptance_criteria",
              "no goal-level criterion: need at least one tagged [e2e], [browser] or "
              "[data-invariant] that exercises the real stack and states the user-visible outcome")


# ---------------------------------------------------------------- discovery (unknowns)
DISC_RE = re.compile(r"^(code|architecture|design|environment|data)\s+\[([^\]]+)\]\s*(.*)$",
                     re.I)


def check_discovery(keys, f, root):
    if "discovery" not in keys:
        f.err("PL05", "discovery",
              "no discovery block: record, per category (%s), what you verified about the "
              "CURRENT state, or an explicit NA with a reason" % ", ".join(DISCOVERY_CATEGORIES))
        return
    seen = set()
    for raw in keys["discovery"]["items"]:
        m = DISC_RE.match(raw)
        if not m:
            f.err("PL05", "discovery", "malformed entry %r; use '<category> [OPEN | "
                  "VERIFIED: <ref> | NA: <reason>] <what>'" % raw[:60])
            continue
        cat, status, what = m.group(1).lower(), m.group(2).strip(), m.group(3)
        seen.add(cat)
        up = status.upper()
        if up == "OPEN":
            f.err("PL05", cat, "unresolved discovery blocks planning: %s" % (what or "(no text)"))
        elif up.startswith("VERIFIED"):
            ref = status.split(":", 1)[1].strip() if ":" in status else ""
            toks = ref.split()
            path_like = bool(re.search(r"/|\.[A-Za-z]{1,5}(:|$)", ref)) or bool(
                re.search(r"CLM-\d+", ref))
            command_like = len(toks) >= 2 and toks[0].lower() not in (
                "i", "we", "yes", "done", "checked", "confirmed", "ok", "verified")
            if not ref or not (path_like or command_like):
                f.err("PL05", cat, "VERIFIED needs a reference (path:lines, a command that "
                      "was run, or a claim id), not an assertion")
            else:
                path = re.split(r":\d", ref, 1)[0].strip()
                if "/" in path and not re.search(r"\s", path) and not os.path.exists(
                        os.path.join(root, path)):
                    f.err("PL05", cat, "cited evidence path does not exist: %s" % path)
        elif up.startswith("NA"):
            reason = status.split(":", 1)[1].strip() if ":" in status else ""
            if len(reason.split()) < 3:
                f.err("PL05", cat, "NA needs a reason of at least three words")
        else:
            f.err("PL05", cat, "status must be OPEN, VERIFIED: <ref> or NA: <reason>, got %r"
                  % status[:30])
    missing = [c for c in DISCOVERY_CATEGORIES if c not in seen]
    if missing:
        f.err("PL05", "discovery", "no entry for: %s" % ", ".join(missing))


# ---------------------------------------------------------------- reuse
def _identifiers(text):
    toks = re.findall(r"[A-Za-z][A-Za-z0-9_]{4,}", text)
    return [t for t in dict.fromkeys(toks) if t.lower() not in STOP]


def _search(root, toks, limit=3):
    if not toks:
        return []
    hits = {}
    scanned = 0
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for fn in files:
            if not fn.endswith(CODE_EXT):
                continue
            p = os.path.join(d, fn)
            try:
                if os.path.getsize(p) > 512 * 1024:
                    continue
                body = open(p, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            scanned += 1
            n = sum(1 for t in toks if re.search(r"\b" + re.escape(t) + r"\b", body))
            if n:
                hits[os.path.relpath(p, root).replace("\\", "/")] = n
            if scanned > 5000:
                break
    need = 2 if len(toks) >= 2 else 1
    ranked = sorted((k for k, v in hits.items() if v >= need), key=lambda k: -hits[k])
    return ranked[:limit]


def check_reuse(keys, f, root):
    files = keys.get("files_or_components", {"items": []})["items"]
    new_paths = [p for p in files if "/" in p and not os.path.exists(os.path.join(root, p))]
    reuse = keys.get("reuse", {"items": []})["items"]
    if new_paths and not reuse:
        f.err("PL06", "reuse", "plan creates new components (%s) but has no reuse record; "
              "search the repo first and record '<need> -> <existing path | NEW: reason>'"
              % ", ".join(new_paths[:3]))
    for raw in reuse:
        parts = re.split(r"\s*(?:->|\u2192)\s*", raw, maxsplit=1)
        if len(parts) != 2 or not parts[1].strip():
            f.err("PL06", "reuse", "malformed entry %r; use '<need> -> <path | NEW: reason>'" %
                  raw[:60])
            continue
        need, target = parts[0].strip(), parts[1].strip()
        if target.upper().startswith("NEW"):
            reason = target.split(":", 1)[1].strip() if ":" in target else ""
            if len(reason.split()) < 4:
                f.err("PL06", need[:30], "NEW needs a reason (>= 4 words) saying why no "
                      "existing code can be extended")
            cands = _search(root, _identifiers(need))
            if cands:
                f.warn("PL06", need[:30], "possible existing implementation: %s; justify or reuse"
                       % ", ".join(cands))
        else:
            path = re.split(r":\d", target, 1)[0].strip()
            if not os.path.exists(os.path.join(root, path)):
                f.err("PL06", need[:30], "reuse target does not exist: %s" % path)


# ---------------------------------------------------------------- dependencies
def _known_ids(state_root):
    ids = {}
    for sub in ("plans", "phases", "tasks"):
        base = os.path.join(state_root, sub)
        for d, _dirs, files in os.walk(base):
            for fn in files:
                stem = fn.split(".")[0]
                ids[stem] = os.path.join(d, fn)
    return ids


def check_dependencies(keys, f, plan_path, state_root):
    deps = keys.get("depends_on", {"items": []})["items"]
    if not deps:
        return
    me = os.path.basename(plan_path).split(".")[0]
    known = _known_ids(state_root)
    graph = {}
    for dep in deps:
        if dep == me:
            f.err("PL07", dep, "plan depends on itself")
        elif dep not in known:
            f.err("PL07", dep, "dependency does not resolve to a plan or task record")
    graph[me] = deps

    def edges(node):
        if node in graph:
            return graph[node]
        p = known.get(node)
        if p and p.endswith(".md"):
            try:
                return parse_plan(open(p, encoding="utf-8", errors="ignore").read()).get(
                    "depends_on", {"items": []})["items"]
            except OSError:
                return []
        return []

    def cyc(node, stack):
        if node in stack:
            return stack[stack.index(node):] + [node]
        for nxt in edges(node):
            r = cyc(nxt, stack + [node])
            if r:
                return r
        return None
    r = cyc(me, [])
    if r and len(r) > 2:
        f.err("PL07", me, "dependency cycle: " + " -> ".join(r))


# ---------------------------------------------------------------- approval drift
def check_approval(keys, text, f):
    h = keys.get("approval_hash", {}).get("scalar", "").strip()
    if not h:
        f.warn("PL08", "approval_hash", "approval is not bound to the plan content; a human "
               "should run: python3 framework/plan/plan_lint.py <plan> --stamp")
    elif h.lower() != approval_digest(text):
        f.err("PL08", "approval_hash", "plan content changed after approval; re-review and "
              "re-stamp")


def check_files(keys, f):
    n = len(keys.get("files_or_components", {"items": []})["items"])
    if n > MAX_FILES:
        f.warn("PL02", "files_or_components",
               "%d files/components (> %d): likely several tasks; split into vertical slices" %
               (n, MAX_FILES))


# ---------------------------------------------------------------- main
def lint(plan_path, root, state_root):
    text = open(plan_path, encoding="utf-8-sig").read()
    keys = parse_plan(text)
    f = Findings()
    check_criteria(keys, f)
    check_files(keys, f)
    check_discovery(keys, f, root)
    check_reuse(keys, f, root)
    check_dependencies(keys, f, plan_path, state_root)
    check_approval(keys, text, f)
    return f.rows


def stamp(plan_path):
    text = open(plan_path, encoding="utf-8-sig").read()
    digest = approval_digest(text)
    lines = text.replace("\r", "").split("\n")
    lines = [ln for ln in lines if not ln.lower().startswith("approval_hash:")]
    at = next((i for i, ln in enumerate(lines) if re.match(r"^status:", ln, re.I)), None)
    new = "approval_hash: " + digest
    if at is None:
        lines.insert(0, new)
    else:
        lines.insert(at + 1, new)
    with open(plan_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))
    return digest


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("plan")
    ap.add_argument("--root", default=".")
    ap.add_argument("--state-root", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--stamp", action="store_true")
    a = ap.parse_args(argv)
    if not os.path.isfile(a.plan):
        print("[plan_lint] BLOCKED plan not readable: %s" % a.plan)
        return 2
    try:
        if a.stamp:
            print("[plan_lint] stamped approval_hash " + stamp(a.plan))
            return 0
        rows = lint(a.plan, a.root, a.state_root or os.path.join(a.root, ".planning"))
    except (OSError, UnicodeDecodeError) as exc:
        print("[plan_lint] BLOCKED %s" % exc)
        return 2
    errors = [r for r in rows if r["severity"] == "ERROR"]
    if a.json:
        print(json.dumps({"errors": len(errors), "findings": rows}, indent=1))
    else:
        for r in rows:
            print("[plan_lint] %s %s %s: %s" % (r["severity"], r["rule"], r["where"], r["message"]))
        print("[plan_lint] %d error(s), %d warning(s)" % (len(errors), len(rows) - len(errors)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
