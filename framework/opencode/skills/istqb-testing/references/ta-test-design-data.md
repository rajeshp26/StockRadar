# Test Analyst Chapter 3.1: Data-Based Test Techniques

Use this reference for domain testing, combinatorial testing, and random testing. For Foundation equivalence partitioning and boundary value analysis, use `references/test-techniques.md` first: domain testing extends boundary thinking into multiple dimensions, and combinatorial testing extends equivalence thinking into combinations.

## 3.1.1 Domain testing

### When to use it

Use domain testing when a rule has boundaries in one or more dimensions, and defects are likely at or near those boundaries. Examples: age and income rules, price and quantity rules, date ranges, and any rule where two or more numeric inputs interact, such as a loan approved only if income is above a threshold and debt ratio is below a threshold.

Domain testing is the Test Analyst extension of boundary value analysis. Foundation BVA tests one dimension at a time. Domain testing tests boundaries in multiple dimensions, and tests the boundary itself, just inside it, and just outside it, in each dimension.

### Steps, in order

1. Identify the domain: the set of inputs the rule accepts, described as ranges, categories, or a combination.
2. Identify each boundary: each edge of the domain, in each dimension.
3. For each boundary, identify test points:
   - ON points: values exactly on the boundary.
   - OFF points: values just outside the boundary, at the smallest meaningful distance.
   - IN points: values just inside the domain, near the boundary.
   - OUT points: values outside the domain, away from the boundary, to check rejection.
4. For multi-dimensional domains, combine points across dimensions deliberately, not randomly. A point that is ON in one dimension and OFF in another tests a corner, and corners are where multi-dimensional rules fail.
5. Count coverage before choosing a set: simplified coverage, reliable coverage, and the number of points each requires (see below). Choose a set that meets the coverage you claimed, and state which coverage you achieved.

### Coverage: simplified versus reliable

Point counts grow with borders, not dimensions, so the technique stays practical for high-dimensional domains. For an ON point, note the border type: on a closed border, ON sits exactly on the border; on an open border, ON sits as close as accuracy allows inside it. OFF is the mirror image: just outside a closed border, or exactly on an open border. IN is inside but not an ON point for that border; OUT is outside but not an OFF point.

- Simplified domain coverage, per border: for an inequality border, one ON and one OFF point; for an equality border, one ON and two OFF points, one each side; for a not-equal border, one OFF point on the border and two ON points, one each side. For N inequality borders, unoptimised simplified coverage needs 2N points. It is cheap, but it can miss defects that only appear at a corner where two boundaries interact.
- Reliable domain coverage, per border: for an inequality border, one ON, OFF, IN, and OUT point; for an equality border, one ON and two OUT points; for a not-equal border, one OFF and two IN points, one each side. For N inequality borders, unoptimised reliable coverage needs usually 3N + 1 points, the plus one being a shared IN point. Sharing an ON point where two closed borders meet, or using ON and OFF points for one partition as OFF and ON points for its neighbour, can reduce the count, but sharing is harder for non-convex or disjoint partitions.
- Equality-only fault warning: in the book's analysis of seven typical faulty versions of a rule, reliable coverage catches all seven, while simplified coverage misses the equality-only fault, since both its points still give the expected answer for that fault. Example: a rule that should be "income greater than or equal to $50,000" but is implemented as "income greater than $50,000" will pass a simplified set that never tests exactly $50,000. Reliable coverage, with ON points, catches it. If a boundary uses equality, test the exact boundary value. That sentence alone prevents a common domain-testing failure.

### Worked example, original

Rule for a library loan: a member may borrow a book if age is at least 18 and outstanding fines are at most $10. Two dimensions: age (boundary 18) and fines (boundary $10).

- ON points: age 18, fines $10 (both exactly on their boundaries; expect allow).
- OFF points: age 17, fines $10 (just outside age; expect reject); age 18, fines $11 (just outside fines; expect reject).
- IN points: age 19, fines $9 (just inside both; expect allow).
- OUT points: age 10, fines $50 (well outside; expect reject).
- Corner test: age 17, fines $11 (outside both; expect reject, and check the rejection reason names the correct rule, not just any rejection).

Simplified coverage for this rule uses ON and OFF points per boundary. Reliable coverage adds IN points and corner combinations, and states that the exact boundary values 18 and $10 were both tested.

### Strengths, limits, and mistakes

- Strengths: systematic boundary coverage in multiple dimensions, strong for numeric and date rules, and good at finding off-by-one and operator errors.
- Limits: does not handle unordered categories well (use equivalence partitioning or combinatorial testing instead), and becomes expensive as dimensions grow, because corners multiply.
- Mistakes: testing only IN points (never testing the boundary itself); testing only one dimension at a time (missing corner defects); and claiming reliable coverage from a simplified set.

## 3.1.2 Combinatorial testing

### When to use it

Use combinatorial testing when many parameters interact, full combinations are too many to test, and defects are likely caused by interactions between a small number of parameters, not by every parameter at once. Examples: configuration testing (browser, operating system, language, screen size), form validation with several fields, and feature combinations in a product.

### Steps, in order

1. Identify parameters and their values. If a parameter has very many values, first split it into equivalence partitions and use one representative per partition, with a reason recorded. Do not silently drop a value dimension that matters. Use a classification tree or a feature model to organise them, and to record which combinations are possible and which are impossible. A classification tree is only a representation; the coverage criterion does the work.
2. Remove impossible combinations before generating cases. A combination that cannot happen in reality should not be tested, and should not be counted in coverage. Where values constrain each other, use a feature model recording mandatory, optional, exclusive, and requires relations, since constraints change which combinations are feasible.
3. Choose a coverage strength:
   - Each-choice coverage: every value of every parameter appears at least once. This is the weakest combinatorial coverage, and it is not pairwise coverage.
   - Pairwise coverage (2-wise): every pair of values from every pair of parameters appears at least once. This is the most common combinatorial strength, because most interaction defects involve two parameters.
   - N-wise coverage: every combination of N parameters appears at least once. Full combination coverage is N-wise where N equals the number of parameters, and it is usually too large to run.
4. Build a test set that meets the chosen strength, using a base-choice or pairwise construction (see below). Count the coverage items before you claim coverage.
5. Check the set against the classification tree or feature model: does every required pair appear, and does no test contain an impossible combination?

### Construction methods

- Base choice: pick a base case (usually the most common or most important combination), then vary one parameter at a time from the base, keeping all other parameters at their base values. For parameters with values counts v(1), v(2), and so on, base-choice size is 1 plus the sum of (v(i) minus 1) over all parameters. Example: three parameters with 3, 2, and 2 values give 1 + 2 + 1 + 1, or 5 tests. Base choice is cheap and good for finding defects in single-parameter variations, but it does not guarantee pairwise coverage.
- Pairwise construction: build a set where every pair appears at least once, using a tool or a systematic method. Pairwise sets are larger than base-choice sets, but smaller than full combinations, and they catch two-parameter interaction defects. Its lower bound is the product of the two largest value counts. Finding a truly minimal set is computationally hard, so tools use heuristics that may return a near-minimal set: verify all pairs against the rows, and do not assume a tool's set is minimal. Add the base or most common configuration explicitly if the criterion does not already include it, since a pairwise suite can miss the most common all-valid configuration entirely.
- Multiple-choice and higher N-wise: use only when risk justifies it, such as safety-critical interactions, because test counts grow quickly.

### Worked example, original

A shop checkout form has three parameters: payment method (card, wallet, bank transfer: 3 values), shipping (standard, express: 2 values), and discount (none, code: 2 values). Full combinations: 3 times 2 times 2, or 12 tests.

- Each-choice coverage: at least 3 tests, covering all 3 payment methods, both shipping options, and both discount options across the set.
- Base choice: base case card, standard, none. Vary payment to wallet and bank transfer (2 tests), shipping to express (1 test), discount to code (1 test), plus the base case itself: 5 tests total.
- Pairwise coverage: a set where every payment-shipping pair, every payment-discount pair, and every shipping-discount pair appears at least once. That set is larger than 5 tests and smaller than 12, and it is the right choice if payment-shipping interactions are a known risk (for example express shipping with bank transfer has a different cutoff time).

State which strength you achieved. "Combinatorial testing" without a strength is not a coverage claim.

### Strengths, limits, and mistakes

- Strengths: strong for interaction defects, far cheaper than full combinations, and systematic where ad hoc combination testing is not.
- Limits: pairwise coverage does not guarantee three-parameter interaction defects are found; impossible combinations must be removed or the set will contain untestable cases; and parameter values must be chosen well, or the set will test irrelevant values.
- Mistakes: claiming pairwise coverage from a base-choice set; counting each-choice coverage as pairwise; and testing impossible combinations and then reporting them as failures.

## 3.1.3 Random testing

### When to use it

Use random testing when inputs are many, varied, or distributed like real usage, and you have a way to judge each random case. Examples: fuzzing a parser with varied inputs, load testing with varied user journeys, and testing a calculation with varied numeric inputs where a property must always hold.

### Steps, in order

1. Define the input distribution: uniform (every value equally likely, usage-agnostic, suits verification) or operational profile (values distributed like real usage, suits validation and reliability estimation; probabilities leaving each step must sum to 100 percent). The distribution decides what random testing actually tests. Uniform random testing finds edge cases. Operational-profile random testing finds defects users are most likely to hit.
2. Choose unguided testing (distribution stays fixed) or guided testing (distribution changes as points are drawn).
3. Define the oracle or property before running at scale: how will you judge each random case? Without an oracle, random testing can run but cannot pass or fail. Use a property-based oracle (for example "total never negative", "output is sorted"), an inverse check (for example squaring a square-root result and comparing with the input), a metamorphic relation (see `references/ta-test-design-rule.md`), or a reference implementation or previous version.
4. Choose a seed for the random generator, and record it. A random test run that cannot be reproduced cannot be debugged. The seed is what makes random testing repeatable.
5. Run a large number of cases, log failures with their inputs and seed, and reproduce each failure from its seed before reporting it.
6. Decide the stopping rule in advance, since there is no coverage criterion: a fixed run count, a time budget, or a defect-based rule such as stopping after a long run with no new defects.
7. Report coverage in terms of inputs exercised and properties checked, not only in terms of cases run. "10,000 random cases passed" without a property or a distribution is not evidence.

### Variants, and when each fits

- Uniform random testing: every input equally likely. Good for finding edge cases and for testing parsers and calculations.
- Operational-profile random testing: inputs distributed like real usage. Good for estimating reliability and for finding defects users will actually hit.
- Guided random testing: the distribution changes as points are drawn, guiding inputs toward interesting areas, such as boundaries or past defect areas, instead of staying fixed. Good when pure random testing wastes cases on uninteresting inputs.
- Unguided random testing: the distribution stays fixed. Good for unbiased exploration, but wasteful if most random inputs are invalid or uninteresting.
- Adaptive random testing: motivated by failure-causing inputs clustering in contiguous regions, so spreading points evenly raises the chance of hitting a faulty region. Three strategies: fixed-size candidate set (draw several candidates, keep the one farthest from already-drawn points); restricted random testing (an exclusion zone around each chosen point, so later points must fall outside it); and random partitioning (each drawn point splits the domain, and the next point comes from the largest remaining region).
- Monkey testing, fuzz testing, and chaos testing are related forms: monkey testing sends random actions to an interface; fuzz testing sends random or malformed data to find crashes and security defects; chaos testing injects failures into a running system to check resilience. All three need an oracle (crash, hang, or incorrect result) and a reproducible seed or log, or their findings cannot be fixed.

### Worked example, original

A shop total calculation must satisfy the property "total equals sum of item prices, minus discount, plus tax, and total is never negative". Random testing generates 1,000 random carts (random item counts, prices, discount codes, and tax regions), computes the total by the system under test, and checks the property for each cart, using an independent calculation as a pseudo-oracle. A failure is logged with its cart, its seed, and the property violated. Without the property, the 1,000 carts would be observations, not tests.

### Strengths, limits, and mistakes

- Strengths: finds defects that systematic techniques miss, because it does not assume which inputs matter; scales to large input spaces; and, with an operational profile, estimates real-world reliability.
- Limits: the oracle problem is central (random inputs without a judgement method are not tests); coverage is hard to state precisely; and failures can be hard to reproduce without a seed.
- Mistakes: running random cases without an oracle and reporting passes; not recording the seed; and using a uniform distribution when the question is about real user reliability, or vice versa.
