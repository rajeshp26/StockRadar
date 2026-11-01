#!/usr/bin/env python3
"""Deterministic router for the istqb-testing skill package.

Usage:
    python3 router.py --task "design pairwise tests for checkout config"
    python3 router.py --task "boundary tests for age 18" --plain
    python3 router.py --type domain-testing --task "age and fines rule"

Procedure, fixed and nothing else:
    1. Load routing.json from the same directory as this script.
    2. Normalise the task text: lowercase, replace hyphens and
       underscores with spaces, collapse whitespace.
    3. If --type names a rule id, that rule is first, regardless of text.
    4. Scan rules in routing.json array order. Array order is priority
       order. Collect every rule whose normalised signal appears in the
       normalised task text.
    5. References are deduplicated in first-match order. The first
       reference is the primary reference.
    6. If no rule matches and no --type was given, use the fallback
       reference from routing.json and set fallback to true.

Output is JSON by default, or plain text with --plain. The script uses
only the Python standard library and reads no other file.
"""

import argparse
import json
import os
import re
import sys


def normalise(text):
    text = text.lower().replace("-", " ").replace("_", " ")
    return re.sub(r"\s+", " ", text).strip()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Route an istqb-testing task to its reference files.")
    parser.add_argument("--task", default="", help="Task text to route, for example a test design request.")
    parser.add_argument("--type", default="", dest="task_type", help="Rule id from routing.json, used as the primary rule.")
    parser.add_argument("--plain", action="store_true", help="Print plain text instead of JSON.")
    args = parser.parse_args(argv)

    if not args.task and not args.task_type:
        parser.error("--task or --type is required")

    here = os.path.dirname(os.path.abspath(__file__))
    routing_path = os.path.join(here, "routing.json")
    with open(routing_path, "r", encoding="utf-8") as handle:
        routing = json.load(handle)

    rules = routing["rules"]
    by_id = {rule["id"]: rule for rule in rules}

    matched = []
    if args.task_type:
        if args.task_type not in by_id:
            print("unknown rule id: %s" % args.task_type, file=sys.stderr)
            return 2
        matched.append(by_id[args.task_type])

    task_norm = normalise(args.task)
    for rule in rules:
        if rule in matched:
            continue
        for signal in rule["signals"]:
            if normalise(signal) in task_norm:
                matched.append(rule)
                break

    references = []
    for rule in matched:
        if rule["reference"] not in references:
            references.append(rule["reference"])

    fallback = False
    if not references:
        references = [routing["fallback"]["reference"]]
        fallback = True

    result = {
        "task": args.task,
        "task_type": args.task_type,
        "primary": references[0],
        "references": references,
        "matched_rules": [rule["id"] for rule in matched],
        "fallback": fallback,
    }

    if args.plain:
        print("primary: %s" % result["primary"])
        for reference in result["references"]:
            print("reference: %s" % reference)
        print("matched_rules: %s" % ", ".join(result["matched_rules"]) if result["matched_rules"] else "matched_rules: none")
        print("fallback: %s" % ("true" if fallback else "false"))
    else:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
