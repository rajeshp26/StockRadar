---
name: performance-testing
description: Conditional skill for measuring and validating performance. Covers baseline establishment, workload definition, measurement, comparison, and regression detection. Use when performance is a material requirement or when changes may impact latency, throughput, memory, or resource consumption.
---

# Performance Testing

"This should improve performance" is not evidence. Measurements are evidence.

## Activation triggers (load when ANY are true)

- Performance is an explicit requirement
- High-volume data processing
- Latency-sensitive operations
- Throughput-critical paths
- Large dataset handling
- Concurrent access patterns
- Database-heavy operations
- Memory-sensitive operations
- CPU-intensive computation
- Known regression risk

## Mandatory workflow

```
Performance requirement (from REQ or acceptance criteria)
        ↓
Define metric (what to measure)
        ↓
Define workload (what inputs produce what load)
        ↓
Establish baseline (current performance)
        ↓
Execute baseline measurement
        ↓
Record baseline results
        ↓
Implement change
        ↓
Execute same workload on changed code
        ↓
Record new results
        ↓
Compare baseline vs new
        ↓
Determine: regression | improvement | no change
        ↓
Document results with evidence
```

## Required output

```yaml
performance_validation:
  requirement_id: REQ-XXX
  metrics:
    - name: [metric name]
      unit: [ms | ops/sec | MB | %]
      threshold: [acceptable value]
      measurement_method: [how it is measured]
  workload:
    description: [what the workload represents]
    dataset:
      size: [volume]
      source: [synthetic | production-sample]
    concurrency: [number of concurrent operations]
    duration: [how long the test runs]
  baseline:
    measurement_date: [date]
    environment: [where measured]
    results:
      - metric: [name]
        value: [measured value]
        command: [exact command used]
        exit_code: [exit code]
  post_change:
    measurement_date: [date]
    environment: [same as baseline]
    results:
      - metric: [name]
        value: [measured value]
        command: [exact command used]
        exit_code: [exit code]
  comparison:
    - metric: [name]
      baseline: [value]
      new: [value]
      delta: [absolute]
      delta_percent: [percentage]
      verdict: [improved | unchanged | regressed]
  regression: [true | false]
  regression_details: [if regressed, what and why]
  tool_evidence:
    - tool: [measurement tool]
      command: [exact command]
      output: [key output]
```

## Measurement rules

1. **Same environment** — baseline and post-change must use the same hardware, same dataset, same configuration
2. **Same workload** — identical inputs, identical concurrency, identical duration
3. **Warm-up** — allow JIT/cache warm-up before measuring
4. **Multiple runs** — minimum 3 runs, report median
5. **Isolated** — no other workloads during measurement
6. **Recorded** — exact commands, exact output, exact exit codes

## What requires escalation

- Regression detected → escalate to Team Lead
- Baseline cannot be established → escalate to Team Lead
- Measurement environment unavailable → record as unverifiable
- Performance requirement without clear threshold → ask for clarification

## Integration with other skills

- Requires: `software-architecture-design` output (what performance-sensitive paths exist)
- Requires: `database-schema-design` output (query performance implications)
- Feeds: `verifier` (performance evidence for verification)
- Feeds: `reviewer` (performance impact assessment)
