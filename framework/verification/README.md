# Verification Module

Implements ARIS-inspired verification patterns for robust evidence-based verification.

## Components

### Suspicion Log (`suspicion_log.py`)

Persistent reviewer memory that tracks concerns across review rounds. From ARIS patterns:
- Reviewers record suspicions about evidence, claims, or verification results
- Suspicions persist across rounds and must be explicitly resolved
- Open suspicions block task completion

**Usage:**
```bash
# Add a suspicion
python3 framework/verification/suspicion_log.py add --json '{
    "task_id": "05-01",
    "reviewer": "reviewer",
    "suspicion": "G4 may have been reported from stale test output",
    "evidence_requested": "fresh test invocation + timestamp + git SHA"
}'

# Check if task has open suspicions
python3 framework/verification/suspicion_log.py check --task-id 05-01

# Resolve a suspicion
python3 framework/verification/suspicion_log.py resolve --id SUSP-001 \
    --resolved-by "verifier" \
    --resolution-evidence "test re-run with exit code 0, SHA abc123"
```

### Review Loop (`review_loop.py`)

Bounded review/fix/re-review cycles with MAX_ROUNDS. From ARIS patterns:
- Maximum 4 review rounds (configurable)
- Stops when findings drop below threshold
- Tracks all rounds and their outcomes

**Usage:**
```bash
# Start a review loop
python3 framework/verification/review_loop.py start --task-id 05-01

# Record a round's results
python3 framework/verification/review_loop.py record-round \
    --task-id 05-01 --round 1 --findings 3

# Check if more rounds are allowed
python3 framework/verification/review_loop.py check --task-id 05-01

# Manually complete with disposition
python3 framework/verification/review_loop.py complete \
    --task-id 05-01 --disposition "ALL_FINDINGS_ADDRESSED"
```

## Integration with Gates

These components integrate with the gate system:

- **G8 (Blockers)**: Open suspicions create blockers
- **G11 (Evidence)**: Suspicion resolution requires evidence
- **G14 (Integrity)**: New gate for evidence integrity checks

## State Files

All state is stored under `<state_root>/verification/`:
- `suspicion_log.jsonl` - Append-only suspicion records
- `review_state.json` - Current review loop states
