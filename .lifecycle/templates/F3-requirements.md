# F3 — Requirements

```
Charter: <authoring charter>
Agent-Id: <...>
Role: <...>
Session-Id: <...>
Feature: <FEATURE-ID>
Depth: <L0..L4>
Phase: F3
Baseline: <BL-id assigned at G0>
Timestamp: <ISO 8601 with offset>
```

Spec: §5.3. Four mandatory categories. A feature with only functional requirements fails G0.

## 1. Functional

```
US-001  As a <customer>
        I want to <capability>
        so that <outcome>.

AC-001-1  Given <precondition>
          When <action>
          Then <observable outcome>
          And <second observable outcome>.
```

## 2. Negative

```
AC-001-4  Given <the thing is unavailable / absent / invalid>
          When <the operation is requested>
          Then the system shall <defined behaviour>
          And shall <report or surface the condition>.
```

## 3. Boundary

```
AC-001-7  Given <the minimum or maximum supported value or count>
          When <the operation is performed>
          Then <every element is handled>
          And nothing is silently dropped.
```

## 4. Non-functional

Each `NFR-*` needs a **measurable threshold** and a **measurement method**. "Fast" is a G0 failure.

| Id | Statement | Threshold | Measurement method | Measured at |
|---|---|---|---|---|
| NFR-1 | | | | G7 / G8 Part B |

Categories to consider: latency, throughput, availability, memory, CPU, power, startup impact, reliability, security, privacy, accessibility, localization, logging, observability, diagnosability.

## 5. Rules check

- [ ] Every `AC-*` is independently verifiable
- [ ] No `AC-*` describes implementation
- [ ] Every `AC-*` maps back to a `UC-*`
- [ ] Every `SCN-*` maps to at least one `AC-*` or has a recorded deferral
- [ ] All four categories present

## 6. Amendments from F5 missing-scenario findings

The F5→F3 loop is blocking (§5.5). Record each amendment.

| Finding | Amendment | New/changed AC | F5 re-derived |
|---|---|---|---|

## 7. Audio Settings instantiation

- [ ] Each setting names its control scope: vehicle, seat or shared_vehicle
- [ ] `shared_vehicle` criteria state who may override whom, and the arbitration
- [ ] Applicable user roles named per criterion
- [ ] **Audible-outcome criteria stated separately from state-readback criteria**
- [ ] Persistence criteria cover read and write paths
- [ ] Focus-loss and focus-regain behaviour specified, not only acquire
- [ ] Where audibility of an alert or chime is in scope, §11 hazard and misuse requirements appear as first-class `AC-*`

## 8. Baseline

Requirements baseline created at G0 (§8.6 rule 1).

```yaml
baseline:
  id: BL-REQ-<nnn>
  kind: requirements
  created: <iso>
  approved_by: <certifier agent_id>
  git_commit: <sha>
  status: current
```
