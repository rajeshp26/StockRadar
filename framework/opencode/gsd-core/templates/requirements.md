# Requirements Template

Template for `.planning/REQUIREMENTS.md` — checkable requirements that define "done."

<template>

```markdown
# Requirements: [Project Name]

**Defined:** [date]
**Core Value:** [from PROJECT.md]

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### [Category 1]

#### REQ-01: [Short Name]

**User persona:** [who]

**User story:**
As a <persona>,
I want <goal>,
So that <value>.

**Environments:**
- [env1]
- [env2]

**Main scenario (Given/When/Then):**
Given [precondition],
When [action],
Then [expected outcome].

**Alternate scenarios (Given/When/Then):**
- Given ... When ... Then ...
- Given ... When ... Then ...

**Negative/failure scenarios (Given/When/Then):**
- Given ... When ... Then ...

**Boundary/edge scenarios:**
- ...

**Out of scope:**
- ...

**Shape:** [visible_behaviour | api_contract | business_rule | data_transformation | system_reliability]

**Acceptance criteria:**
- [falsifiable condition 1]
- [falsifiable condition 2]

**Verification method:** [browser verification | contract test | unit test | integration test | manual verification]

---

### [Category 2]

#### REQ-02: [Short Name]

**User persona:** [who]

**User story:**
As a <persona>,
I want <goal>,
So that <value>.

**Environments:**
- ...

**Main scenario (Given/When/Then):**
Given ...
When ...
Then ...

**Alternate scenarios (Given/When/Then):**
- ...

**Negative/failure scenarios (Given/When/Then):**
- ...

**Boundary/edge scenarios:**
- ...

**Out of scope:**
- ...

**Shape:** ...

**Acceptance criteria:**
- ...

**Verification method:** ...

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### [Category]

- **REQ-03**: [Short description]
- **REQ-04**: [Short description]

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| [Feature] | [Why excluded] |
| [Feature] | [Why excluded] |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| REQ-01 | Phase 1 | Pending |
| REQ-02 | Phase 1 | Pending |

**Coverage:**
- v1 requirements: [X] total
- Mapped to phases: [Y]
- Unmapped: [Z] ⚠️

---
*Requirements defined: [date]*
*Last updated: [date] after [trigger]*
```

</template>

<guidelines>

**Requirement Format:**
- ID: `REQ-[NUMBER]` (REQ-01, REQ-02, REQ-03)
- Every v1 requirement MUST include:
  - user persona
  - user story
  - environments
  - main scenario
  - alternate scenarios
  - negative/failure scenarios
  - boundary/edge scenarios
  - out of scope
  - shape
  - acceptance criteria
  - verification method

**Categories:**
- Derive from research FEATURES.md categories
- Keep consistent with domain conventions

**v1 vs v2:**
- v1: Committed scope, will be in roadmap phases
- v2: Acknowledged but deferred, not in current roadmap
- Moving v2 → v1 requires roadmap update

**Out of Scope:**
- Explicit exclusions with reasoning
- Prevents "why didn't you include X?" later

**Traceability:**
- Empty initially, populated during roadmap creation
- Each requirement maps to exactly one phase
- Unmapped requirements = roadmap gap

**Status Values:**
- Pending: Not started
- In Progress: Phase is active
- Complete: Requirement verified
- Blocked: Waiting on external factor

**Scenario coverage:**
- Not every scenario class applies to every requirement
- When a class is omitted, the requirement should state why it is irrelevant
- Use Given/When/Then for all functional scenarios

**Shape routing:**
- Shape determines verification and gating
- Do not leave shape blank

</guidelines>

<evolution>

**After each phase completes:**
1. Mark covered requirements as Complete
2. Update traceability status
3. Note any requirements that changed scope

**After roadmap updates:**
1. Verify all v1 requirements still mapped
2. Add new requirements if scope expanded
3. Move requirements to v2/out of scope if descoped

**Requirement completion criteria:**
- Requirement is "Complete" when:
  - Feature is implemented
  - Feature is verified against acceptance criteria and scenario evidence
  - Feature is committed

</evolution>

<example>

```markdown
# Requirements: StockerPro Feature Pack

**Defined:** 2026-09-04
**Core Value:** Improve investor decision-making with clearer portfolio insight

## v1 Requirements

### Portfolio Analytics

#### REQ-042: Portfolio Performance Chart

**User persona:** Authenticated investor

**User story:**
As an authenticated investor,
I want a performance chart for my portfolio over the last 90 days,
So that I can assess recent trends before making decisions.

**Environments:**
- Authenticated web desktop
- Authenticated web mobile
- Production and preview

**Main scenario (Given/When/Then):**
Given the user has portfolio history,
When the user opens the performance view,
Then the chart renders one data point per trading day with correct axes.

**Alternate scenarios (Given/When/Then):**
- Given partial data availability, When the user opens the view, Then available data renders with a visible partial-data state.
- Given responsive layout, When the user switches to mobile, Then the chart remains legible and interactive.

**Negative/failure scenarios (Given/When/Then):**
- Given no portfolio history, When the user opens the view, Then an empty state explains why data is unavailable.
- Given backend failure, When the user opens the view, Then a retry path is shown.

**Boundary/edge scenarios:**
- Exact 90-day range boundaries
- Weekend/holiday date handling
- Zero-position account

**Out of scope:**
- Export functionality
- Custom date range picker

**Shape:** visible_behaviour

**Acceptance criteria:**
- Chart renders with data points for each trading day
- X-axis shows dates, Y-axis shows portfolio value
- Mobile and desktop layouts pass responsive checks
- Loading state is shown while data loads
- Empty and error states are explicitly handled

**Verification method:** browser verification + unit tests for data formatting

---

## v2 Requirements

### Notifications

- **REQ-050**: User receives alert when holdings cross predefined thresholds
- **REQ-051**: User can configure alert preferences

## Out of Scope

| Feature | Reason |
|---------|--------|
| Custom export | Not core to initial insight flow |
| Mobile-native app | Web-first delivery |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| REQ-042 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 1 total
- Mapped to phases: 1
- Unmapped: 0

---
*Requirements defined: 2026-09-04*
*Last updated: 2026-09-04 after authoring standardization*
```

</example>
