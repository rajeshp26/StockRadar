# Test Analyst Chapter 3.2: Behaviour-Based Test Techniques

Use this reference for CRUD testing, state transition testing at Test Analyst depth, and scenario-based testing. For Foundation state transition testing, use `references/test-techniques.md` first, then come here for extended machines, guards, and switch coverage.

## 3.2.1 CRUD testing

### When to use it

Use CRUD testing when data is created, read, updated, and deleted, and you need to check that every operation works and that reads reflect every change. Examples: user accounts, orders, bookings, and any record that lives in a database and is changed over time.

CRUD stands for Create, Read, Update, Delete. Some systems also have other operations, such as search, list, or archive, but CRUD is the core set to check first.

### Steps, in order

1. Build a CRUD matrix: rows are data entities (for example user, order, booking), columns are operations (create, read, update, delete), and each cell says whether that operation is allowed for that entity, and by whom.
2. Check matrix completeness: every entity should have at least one create and one read, unless the entity is read-only or system-created. An entity with no read, or with delete but no create, is a specification defect, not just a missing test.
3. Design tests for each allowed cell: create a record, read it back, update it, read it again, delete it, and read it again to confirm deletion.
4. Check consistency, not only completeness: after every change, every read that should reflect the change must reflect it, and every read that should not reflect it must not. Completeness asks "did we test every operation?" Consistency asks "do the operations agree with each other?"
5. Test error cases per cell: create a duplicate, read a missing record, update a deleted record, delete a record that is in use, and check that each is rejected with a clear message and no partial change.

### Worked example, original

Entity: library loan. Operations: create a loan, read a loan, update a loan (extend due date), delete a loan (return the book).

- Create a loan for a member and a book, then read it: expect the loan exists with the correct member, book, and due date.
- Update the due date, then read again: expect the new due date, and no other field changed.
- Delete the loan (return), then read again: expect not found, and the book available again.
- Consistency checks: after update, a list of overdue loans must reflect the new due date, not the old one. After delete, a member's active loan count must fall by one.
- Error checks: create a loan for a book already on loan (expect reject), update a returned loan (expect reject), delete a loan twice (second delete must reject, not silently succeed).

### Strengths, limits, and mistakes

- Strengths: systematic for data-heavy systems, catches missing operations and inconsistent reads, and the matrix itself finds specification defects.
- Limits: does not test business rules that are not CRUD operations (use decision tables or scenarios for those), and does not test state-dependent behaviour deeply (use state transition testing for that).
- Mistakes: testing create, read, update, and delete in isolation, without reading after every change; and checking completeness (every cell tested) without checking consistency (reads agree after changes).

## 3.2.2 State transition testing, at Test Analyst depth

### When to use it

Use state transition testing when behaviour depends on current state, and events move the system between states, sometimes only if a guard condition holds. Examples: orders, bookings, login sessions, devices, and workflows. Foundation `references/test-techniques.md` covers the basic method. This reference adds extended machines, guards, and switch coverage.

### Extended finite state machines

A basic state machine has states, events, and transitions. An extended finite state machine (EFSM) adds variables and guard conditions: a transition happens only if its guard holds, and it may update variables that affect later transitions. Example: an order can move from Paid to Shipped only if payment is confirmed and stock is available. Payment confirmed and stock available are guards, not just events. Test the guards, not only the events: ship with payment confirmed but stock unavailable (expect no transition), and ship with stock available but payment unconfirmed (expect no transition).

### Steps, in order

1. Model states, events, transitions, guards, and actions. Draw the diagram and build the transition table. If the diagram and the table disagree, the specification is defective. Resolve it before designing tests.
2. Design tests for coverage, choosing a level (see below) and stating it.
3. For each transition, test the guard in both directions where possible: guard true (transition happens) and guard false (transition does not happen, with a clear rejection and no state change).
4. For each state, test invalid events: events that should not move the system from that state, and check that they are rejected with no state change and no side effect.

### Coverage: switch coverage

Switch coverage counts sequences of transitions, not only single transitions:

- 0-switch coverage: every transition is exercised at least once. This is the same as valid-transitions coverage in Foundation terms.
- 1-switch coverage: every pair of consecutive transitions is exercised at least once. This catches defects where the first transition leaves the system in a subtly wrong state that only the second transition reveals.
- N-switch coverage: every sequence of N + 1 consecutive transitions is exercised at least once. Cost grows quickly with N, so choose N by risk. Safety-critical and state-heavy systems justify higher N.
- Round-trip coverage: every sequence that starts and ends in the same state is exercised, including loops that return to the start. Round trips catch defects in cycles, such as a booking that can be cancelled and rebooked, where the second booking inherits stale data from the first.

Subtlety: 1-switch coverage does not automatically subsume 0-switch coverage in every formulation, because a 1-switch set built from pairs may miss a transition that never appears in a pair in the set. State your coverage level and check it by counting transitions and pairs in your actual test set, not by assuming subsumption.

### Worked example, original

States for a clinic booking: Requested, Confirmed, CheckedIn, Completed, Cancelled. Events: confirm, check in, complete, cancel. Guards: confirm requires a free slot; check in requires the appointment time to have arrived; complete requires check-in to have happened.

- 0-switch tests: confirm from Requested, check in from Confirmed, complete from CheckedIn, cancel from Requested and from Confirmed. Each valid transition once.
- 1-switch tests: confirm then check in, check in then complete, confirm then cancel, and request then confirm then check in as a sequence, checking that the second transition works from the state the first transition actually left.
- Guard tests: confirm with no free slot (expect reject, state stays Requested); check in before appointment time (expect reject, state stays Confirmed); complete from Confirmed without check-in (expect reject, state stays Confirmed).
- Invalid event tests: complete from Requested, check in from Completed, confirm from Cancelled. Each must reject with no state change.
- Round-trip test: request, confirm, cancel, request again for the same slot, confirm again, and check that the second booking is clean, with no stale data from the cancelled booking.

### Strengths, limits, and mistakes

- Strengths: systematic for state-dependent behaviour, strong for guards and invalid events, and the diagram itself finds specification defects.
- Limits: state explosion: systems with many states and variables produce models too large to test exhaustively, so prioritise states and transitions by risk; and models can be wrong, so validate the model with stakeholders before deriving tests from it.
- Mistakes: testing valid transitions only, without invalid events or guard-false cases; and claiming 1-switch coverage without counting pairs in the actual set.

## 3.2.3 Scenario-based testing

### When to use it

Use scenario-based testing when a user journey matters as a whole, including branches, loops, and exceptions, not only single functions. Examples: checkout, booking, onboarding, and any multi-step workflow where the order of steps and the handling of interruptions matter.

Scenarios come from use cases, user stories, and activity diagrams. A scenario is a path through a workflow, from a trigger to an outcome, including alternative paths and exception paths.

### Steps, in order

1. Identify the workflow and its trigger, main path, alternative paths, and exception paths. Alternative paths are valid variations (for example pay by card or by wallet). Exception paths are failures and interruptions (for example payment declined, network lost, session expired).
2. Distinguish extensions from exceptions: an extension is a variation that still reaches a successful outcome by a different route; an exception is a failure that must be handled, recovered from, or reported, and may not reach success. Test both, and do not treat an exception as if it were an extension.
3. Design scenarios for the main path, for each alternative path, and for each exception path, at least once.
4. Cover loops simply first: a loop executed zero times, once, and more than once (simple loop coverage). A loop that is never tested with zero iterations hides an empty-list defect; a loop tested only once hides a second-iteration defect.
5. For parallel work, check completion order: when two activities run in parallel, test the orders in which they can complete, and check that the workflow handles each order correctly, not only the most common order.
6. Check state after each scenario, not only the final outcome: intermediate states, data, and messages must be correct, because a scenario that reaches the right final outcome through wrong intermediate states is still defective.

### Worked example, original

Workflow: book a clinic appointment online. Main path: search for a slot, choose a slot, enter details, confirm, receive confirmation. Alternative paths: choose a different slot after seeing no availability, edit details before confirming, pay by card or by wallet where payment applies. Exception paths: slot taken by another user during booking, payment declined, session expired during booking, network lost after confirmation sent but before confirmation received.

- Main path test: complete booking end to end, check confirmation and slot reserved.
- Alternative path tests: change slot mid-booking, edit details, pay by each method.
- Exception path tests: slot taken during booking (expect clear message and a chance to choose another slot, with no double booking); payment declined (expect booking not confirmed, slot released, and a clear retry path); session expired (expect booking not silently lost, or a clear message that it was lost and how to restart).
- Loop test: book for one patient, then for a second patient in the same session, and check that the second booking does not inherit the first patient's details.
- Parallel completion test: where payment and slot reservation happen in parallel, test payment completing first and reservation completing first, and check both orders leave a consistent booking.

### Strengths, limits, and mistakes

- Strengths: tests whole user journeys, catches workflow and interruption defects that single-function tests miss, and is understandable to stakeholders, who can validate scenarios.
- Limits: scenarios can be long and brittle, and scenario coverage is hard to state precisely unless paths are counted; use scenario counting (paths covered divided by paths identified) and state it.
- Mistakes: testing only the main path; treating exceptions as extensions; and checking only the final outcome, without checking intermediate states and data.
