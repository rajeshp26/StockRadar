---
name: requirements-authoring
description: Author feature requirements in this repository. Use when creating, refining, or reviewing requirement docs for new features or changed behavior. Covers user stories, Given/When/Then acceptance criteria, environments, user personas, scenario classes, requirement shape, and verification method.
---

# Requirements authoring

Requirements live in `.planning/REQUIREMENTS.md` and are consumed by planning, gates, verification, and retrospective routing. A requirement is not a task description. It is a falsifiable statement of user value, constraints, and verification intent.

## Required format

Every requirement MUST include:

- `REQ-XXX: <Short Name>`
- `User persona`
- `User story`
- `Environments`
- `Main scenario`
- `Alternate scenarios`
- `Negative/failure scenarios`
- `Boundary/edge scenarios`
- `Out of scope`
- `Shape`
- `Acceptance criteria`
- `Verification method`

## Mandatory sections

### 1. Identity
Use a stable requirement ID.

Example:
`REQ-042: Portfolio Performance Chart`

### 2. User persona
Name the actual user role.

Examples:
- Authenticated investor
- Admin operator
- Unauthenticated guest
- API consumer

### 3. User story
Use this structure:
`As a <persona>, I want <goal>, so that <value>.`

### 4. Environments
List every environment where behavior must hold.

Examples:
- Local dev
- Preview
- Production
- Web desktop
- Web mobile
- Authenticated state
- Unauthenticated state
- Offline / degraded network
- Role-restricted environment

### 5. Scenarios
Use `Given/When/Then` for each scenario.

Required scenario classes when applicable:
- normal
- alternate
- negative
- failure
- recovery
- boundary
- security
- performance
- misuse
- interrupted
- persistence
- upgrade / downgrade / rollback

Not every class applies to every feature, but the requirement must explicitly show why a class is irrelevant when omitted.

### 6. Shape
Pick one shape that best matches the requirement.

Likely shapes in this repo:
- `visible_behaviour`
- `api_contract`
- `business_rule`
- `data_transformation`
- `system_reliability`

Shape matters because it determines verification and gating.

### 7. Acceptance criteria
Write concrete, testable criteria.

Good:
- Endpoint returns 200 with expected payload
- UI renders chart with one data point per trading day
- Invalid input returns 400 with error message

Bad:
- Should work
- Should be fast
- Should be intuitive

### 8. Verification method
Name the strongest applicable evidence.

Examples:
- browser verification
- contract test
- integration test
- unit test
- manual verification with recorded evidence

## Quality checklist

Use this before approving a requirement:
- [ ] REQ ID present
- [ ] Persona explicit
- [ ] User story written
- [ ] Environments listed
- [ ] Main scenario present
- [ ] At least one alternate scenario
- [ ] At least one negative/failure scenario
- [ ] Boundary cases considered
- [ ] Out of scope declared
- [ ] Shape chosen
- [ ] Acceptance criteria falsifiable
- [ ] Verification method named

## Enforcement rules

- Do not implement a feature without a requirement record when the change is nontrivial.
- Do not approve a requirement with only prose intent.
- Do not leave shape blank.
- Do not confuse UX preference with verifiable acceptance criteria.
- Do not omit environments that would change verification.

## Integration with repo workflow

Use this skill:
- before planning a new feature
- when refining a vague feature request
- when a requirement is missing from `.planning/REQUIREMENTS.md`
- when review finds ambiguous or incomplete requirements
- when verification routing depends on requirement shape

## Example

```markdown
## REQ-042: Portfolio Performance Chart

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

**Alternate scenarios:**
- Given partial data availability, When the user opens the view, Then available data renders with a visible partial-data state.
- Given responsive layout, When the user switches to mobile, Then the chart remains legible and interactive.

**Negative/failure scenarios:**
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
```
