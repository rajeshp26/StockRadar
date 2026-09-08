"""Plain-arg claim ledger appender.

Wrapper around `ledger.py append` that builds the --json payload with
json.dumps, so PowerShell 5.1 can never mangle quoted JSON (the same
failure mode the task_event.py emitter was built to avoid).

Usage (worker-facing - safe under PowerShell 5.1):
  python framework/tools/append_claim.py --task-id T-07 --agent implementer \
      --statement "..." --claim-type behavioral --classification FACT \
      --status VERIFIED --impact medium \
      --evidence-file C:/path/evidence.json \
      --verified-by "python framework/validate.py"

Evidence file: a JSON array of evidence dicts, one per line or a single array.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

LEDGER = [sys.executable, "framework/claims/ledger.py"]
CLAIM_TYPES = ("environment", "behavioral", "data", "causal")
CLASSIFICATIONS = ("FACT", "HYPOTHESIS", "ASSUMPTION", "UNKNOWN")
STATUSES = ("UNVERIFIED", "VERIFIED", "REFUTED", "PARTIALLY_VERIFIED")
IMPACTS = ("high", "medium", "low")


def main() -> int:
    ap = argparse.ArgumentParser(description="append a claim to the ledger")
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--agent", required=True)
    ap.add_argument("--statement", required=True)
    ap.add_argument("--claim-type", required=True, choices=CLAIM_TYPES)
    ap.add_argument("--classification", required=True, choices=CLASSIFICATIONS)
    ap.add_argument("--status", required=True, choices=STATUSES)
    ap.add_argument("--impact", required=True, choices=IMPACTS)
    ap.add_argument("--evidence-file", default="", help="JSON file with an evidence list")
    ap.add_argument("--verified-by", default="")
    ap.add_argument("--independent-check", default="")
    a = ap.parse_args()

    payload = {
        "task_id": a.task_id,
        "agent": a.agent,
        "statement": a.statement,
        "claim_type": a.claim_type,
        "classification": a.classification,
        "status": a.status,
        "impact": a.impact,
    }
    if a.evidence_file:
        p = Path(a.evidence_file)
        if not p.exists():
            print(json.dumps({"error": f"evidence file not found: {p}"}))
            return 1
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(json.dumps({"error": f"bad evidence json: {e}"}))
            return 1
        if not isinstance(data, list):
            print(json.dumps({"error": "evidence file must contain a JSON array"}))
            return 1
        payload["evidence"] = data
    if a.verified_by:
        payload["verified_by"] = a.verified_by
    if a.independent_check:
        payload["independent_check"] = a.independent_check

    r = subprocess.run(
        [*LEDGER, "append", "--json", json.dumps(payload)],
        capture_output=True,
        text=True,
    )
    if r.stdout:
        sys.stdout.write(r.stdout)
    if r.stderr:
        sys.stderr.write(r.stderr)
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())