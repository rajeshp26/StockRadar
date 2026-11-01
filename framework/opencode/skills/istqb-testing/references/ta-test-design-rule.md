# Test Analyst Chapter 3.3: Rule-Based Test Techniques

Use this reference for decision table testing at Test Analyst depth and for metamorphic testing. For Foundation decision table testing, use `references/test-techniques.md` first, then come here for minimisation, extended entries, cause-and-effect graphs, and checksums.

## 3.3.1 Decision table testing, at Test Analyst depth

### When to use it

Use decision table testing when behaviour depends on combinations of conditions, and the combinations matter, not only single conditions. Examples: discount rules, approval rules, eligibility rules, and pricing rules where several conditions together decide the outcome.

### Steps, in order

1. Identify conditions and actions from the specification. Conditions are inputs or states that affect the outcome. Actions are outcomes or outputs.
2. Build the full table: every combination of condition values, as columns, with actions for each column. Do not skip combinations at this stage. A skipped combination is a decision you have not made.
3. Remove infeasible columns: combinations that cannot happen in reality. Mark them as infeasible and remove them, and record why they are infeasible, so a reviewer can challenge the removal.
4. Check for missing or contradictory actions: a column with no action, or two columns with the same conditions but different actions, is a specification defect. Resolve it before minimising.
5. Minimise the table: collapse columns that have the same actions and differ in only one condition, marking that condition with a dash (does not matter) in the collapsed column. Repeat until no further collapse is possible without changing an action. The result is a minimal table.
6. Write at least one test per remaining column. State coverage as feasible columns exercised divided by feasible columns identified, after minimisation, and state that the table was minimised, so a reader knows the count refers to the minimal table, not the full table.

### Limited-entry versus extended-entry tables

- Limited-entry tables: each condition takes only true or false values. They are simple and common, and they suit yes-or-no conditions.
- Extended-entry tables: conditions take more than two values, such as a category (standard, premium, VIP) or a range (low, medium, high). Extended tables are more expressive, but they have more columns, and minimisation matters more. Do not force a multi-value condition into true/false form if that hides a value that changes the outcome.

### Cause-and-effect graphs

A cause-and-effect graph is a visual model of the same logic, used to derive a decision table or to check one. Causes are conditions, effects are actions, and the graph shows logical relations between them, including AND, OR, NOT, and constraints such as "these two causes cannot both be true" or "this effect requires that cause".

Use a cause-and-effect graph when the specification is written as prose and the decision table is hard to build directly from it. Build the graph from the prose, derive the table from the graph, and check the table against the graph. If the graph and the table disagree, one of them is wrong, and the disagreement itself is valuable: it usually points to a missing or contradictory rule in the prose.

### Checksum procedure

A checksum is a way to check that a decision table was built and minimised correctly, by counting in a structured way. In general terms: assign a weight to each action, sum the weights for each column according to its actions, and compare the sums for the full table and the minimal table. If the sums differ in a way that is not explained by the collapse, the minimisation changed an outcome and is wrong.

Important limit: a correct checksum does not prove the table is correct. It proves only that the minimisation preserved the actions as written. If the original table had a wrong action, the checksum will faithfully preserve the wrong action. Check the actions against the specification separately. Do not present a correct checksum as proof that the rules are right.

### Worked example, original

Rule for a library fine waiver: conditions are member type (standard or premium, extended to a category in a fuller version), book overdue by more than 30 days (yes or no), and first overdue offence (yes or no). Actions are waive fine, charge half fine, charge full fine.

Full limited-entry table, with member type as standard or premium, overdue over 30 days yes or no, first offence yes or no: 2 times 2 times 2, or 8 columns. Remove infeasible columns if any (for example a rule that premium members never incur fines would make some columns infeasible, but only if the specification actually says so; do not invent infeasibility).

Suppose the specification says: premium members always get a waiver on first offence, regardless of overdue length. Then columns for premium, first offence yes, overdue yes and overdue no, both have action waive fine, and differ only in overdue length. Collapse them into one column with overdue marked as dash, action waive fine. That collapse is safe only because the specification says overdue length does not matter for premium first offences. If the specification does not say that, do not collapse.

After minimisation, write one test per remaining column, and state the coverage as minimal-table columns exercised divided by minimal-table columns identified.

### Strengths, limits, and mistakes

- Strengths: systematic for combination rules, exposes missing and contradictory rules, and minimisation reduces test count without reducing rule coverage, when done correctly.
- Limits: tables grow quickly with many conditions, and extended tables are harder to build and review; and a table is only as good as the conditions and actions identified from the specification.
- Mistakes: skipping combinations at the full-table stage; collapsing columns that differ in more than one condition, or that have different actions; inventing infeasibility; and treating a correct checksum as proof that the rules are right.

## 3.3.2 Metamorphic testing

### When to use it

Use metamorphic testing when there is no simple oracle: you cannot easily say what the exact correct output should be for a given input, but you do know a relation that must hold between related inputs and outputs. Examples: search, sorting, optimisation, machine learning, and complex calculations where the exact answer is hard to compute by hand, but a relation is easy to state.

A metamorphic relation (MR) is that relation. It connects a source test case and a follow-up test case: run the source case, build a follow-up case by changing the source input in a known way, run the follow-up case, and check that the outputs satisfy the relation. If the relation is violated, a defect is present, even though you never knew the exact expected output for either case alone.

### Steps, in order

1. Identify a metamorphic relation for the system. The relation must be true for correct behaviour, not just usually true. A relation that is only usually true will produce false failures.
2. Design a source test case: a normal, valid input.
3. Build a follow-up test case from the source case by applying the relation's input change.
4. Run both cases and check the relation between their outputs. If the relation holds, the pair passes. If it is violated, report a defect with both cases, both outputs, and the relation violated.
5. Repeat with different source cases and different relations. One relation checks one property. A system needs several relations to be tested well.

### Metamorphic relation types, with original examples

- Subset relation: a result for a subset of inputs must be consistent with the result for the full set. Example: searching a catalogue for "red shoes" and then for "red shoes" with a filter for size 8 must return only items that were in the first result, not new items.
- Partition relation: splitting inputs into parts and combining results must give the same result as processing the whole input. Example: counting items in two halves of a list and adding the counts must equal counting the whole list.
- Ordering relation: changing the order of irrelevant inputs must not change the result, or must change it only in a stated way. Example: sorting a list, then shuffling the input and sorting again, must give the same sorted output.
- Addition relation: adding an irrelevant input must not change the result for other inputs. Example: adding an item to a cart that is out of stock and not purchasable must not change the total for the purchasable items, except for a stated shipping or tax effect that the relation must name.
- Scaling relation: scaling an input by a known factor must scale the output by a known factor. Example: doubling all quantities in a cart, with no discount thresholds crossed, must double the subtotal.

State the relation precisely before running the pair. A vague relation ("results should be similar") cannot pass or fail, and is not a test.

### Relation to property-based testing

Metamorphic testing and property-based testing are related but different. Property-based testing checks a property of a single output (for example "output is sorted", "total never negative"). Metamorphic testing checks a relation between two outputs (source and follow-up). A property can be a metamorphic relation with a trivial follow-up, but metamorphic testing is needed when no single-output property is strong enough to judge correctness alone. Use property-based checks where a single-output property exists, and metamorphic relations where only a between-output relation exists.

### Coverage

There is no generally accepted coverage measure for metamorphic testing comparable to branch coverage or pairwise coverage. Do not invent one. Report metamorphic testing by relations tested, source cases per relation, and violations found, not by a percentage that has no defined denominator. A report that says "metamorphic coverage 80 percent" without defining what 100 percent would mean is not evidence.

### Strengths, limits, and mistakes

- Strengths: works where no oracle exists, which is common for complex, search, and learning systems; relations are often easy for stakeholders to validate; and violations point directly to a defect, even without an exact expected output.
- Limits: finding good relations is hard, and weak relations find few defects; a violated relation may mean the relation was wrong, not the system, so validate relations with stakeholders before reporting; and metamorphic testing does not replace exact-output testing where an exact oracle exists.
- Mistakes: using a vague relation that cannot fail; reporting a violation without checking whether the relation itself was correct; and claiming a coverage percentage for metamorphic testing.
