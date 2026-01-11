# System Change Analysis & Impact Assessment Checklist

A practical guide for analyzing proposed changes and assessing their impact on the codebase.

---

## Before You Start: Ask These Questions

- [ ] Am I fixing a bug, adding a feature, or refactoring?
- [ ] Will this change affect how other parts of the system work?
- [ ] Could I break something by making this change?
- [ ] How confident am I that I've found all affected code?

If you answered "yes" to any of the last three, follow this checklist.

---

## Section 1: Understanding the Current State

### 1.1 Document What Exists Today
- [ ] Write down how the system currently works
  - What does this component/module do?
  - What files depend on it?
  - How are things imported/exported?
- [ ] Gather evidence, don't rely on memory
  - Use `grep`, search tools, IDE
  - Check actual code, not assumptions
  - Example: `grep -r "import.*from.*api"` to find all places importing api.ts

### 1.2 Understand the Problem
- [ ] Can you describe the problem in one sentence?
- [ ] Have you reproduced it (seen the error yourself)?
- [ ] Do you know the root cause or just the symptom?
  - Symptom: "Page shows 401 error"
  - Root cause: "Token isn't available when component mounts"

### 1.3 Identify Everything Affected
- [ ] What files/components are directly broken?
- [ ] What files/components depend on those files?
  - Use automated tools: `grep`, dependency analyzers, IDE "find references"
  - Don't guess—verify with code search
- [ ] Create a simple map
  - "auth.ts is imported by: login-form.tsx, user-nav.tsx, settings.tsx"

---

## Section 2: Planning Your Change

### 2.1 Define What You're Going to Do
- [ ] Write out the change clearly
  - What are you modifying?
  - What are you deleting?
  - What are you adding?
- [ ] Provide before/after examples of code
- [ ] Explain why this solves the problem

### 2.2 List Every File That Needs to Change
- [ ] Which files will I modify?
- [ ] Which files will I delete?
- [ ] Which files will I create?
- [ ] Which files depend on the above and also need changes?
  - Use: `grep -r 'oldPath'` to find all references
  - Example: If changing `export default api` to `export const api`, find all files that import it

### 2.3 Check for Hidden Dependencies
- [ ] Does this module initialize anything when imported?
  - Example: Does it set up Firebase? Connect to a database?
  - If yes, will moving/changing it break initialization order?
- [ ] Does this depend on context or props that aren't always available?
  - Example: Can this component be used at the app root, or only within a specific layout?
  - If yes, where is it safe to place it?
- [ ] Are there multiple versions or definitions of the same thing?
  - Example: Two different `useAuth` hooks in different locations
  - This suggests incomplete refactoring or confusion

### 2.4 Think About Edge Cases
- [ ] Will this work on first load? On page refresh?
- [ ] What if the user is offline?
- [ ] What if something fails (network error, missing data)?
- [ ] What about old browser versions or different environments (SSR, mobile)?

---

## Section 3: Assessing the Risk

### 3.1 What Could Go Wrong?
- [ ] Could this break the app on startup?
- [ ] Could this break a specific feature silently (user doesn't see an error)?
- [ ] Could this break only certain users (mobile, offline, slow networks)?
- [ ] Could this create a maintenance burden (future developers won't know why something is ordered this way)?

### 3.2 Is This a Breaking Change?
- [ ] Are you changing how something is exported?
  - From: `export default api`
  - To: `export const api`
  - Consumers must change: `import api` → `import { api }`
- [ ] Are you changing a function signature?
  - This might break callers
- [ ] Are you moving a file to a new location?
  - All imports must be updated
- [ ] Are you changing behavior (not just structure)?
  - Users might expect the old behavior

### 3.3 Create a Quick Rollback Plan
- [ ] If this goes wrong in 5 minutes, what do I do?
  - Revert the commit?
  - Which files need to be restored?
- [ ] How will I know if it's broken?
  - What error will I see?
  - What should I test?

---

## Section 4: Breaking Work Into Steps

### 4.1 What Order Should Changes Happen?
- [ ] Do foundational changes first
  - Example: Install global provider before updating imports
- [ ] Do dependent changes after
  - Example: Update imports after provider exists
- [ ] Can you test after each step?
  - If no, you might be doing too much at once

### 4.2 Define Success Criteria for Each Step
For each step, write down:
- [ ] What should happen if this step succeeds?
- [ ] What should I test/verify?
- [ ] What error is acceptable? (e.g., import errors are OK after step 1, but not after step 5)
- [ ] What error means I should stop and fix it?

**Example:**
- Step 1: Install AuthProvider in root layout
  - Success: App starts, no errors about provider missing
  - Test: Run `npm run dev`, check console
  - Expected errors: Import errors from files using old paths (this is OK)
  - Stop if: App doesn't start, Firebase errors

- Step 2: Fix user-nav.tsx imports
  - Success: user-nav.tsx imports correct provider
  - Test: Check that import line is correct
  - Expected errors: None (this file should work now)
  - Stop if: Syntax errors or type errors

### 4.3 Plan Your Testing
- [ ] After each step, what specific thing will you test?
  - "Run app and check console for errors"
  - "Navigate to /login and verify form renders"
  - "Check that grep shows correct import paths"
- [ ] How will you verify success?
  - Manual inspection of code
  - Running app in browser
  - Running automated tests
  - Using `grep` or search tools

---

## Section 5: Executing the Change

### 5.1 Before You Start
- [ ] Commit your current work (clean git status)
- [ ] Create a feature branch (if using version control)
- [ ] Write down the current state
  - What's broken right now?
  - What should work after?

### 5.2 Execute Step by Step
For each step:
- [ ] Make the change
- [ ] Verify it worked (run tests/checks)
- [ ] Write down what happened
  - Did you see expected errors?
  - Any surprises?
- [ ] **Stop immediately if something unexpected happens**
  - Don't assume you can fix it by continuing
  - Stop and diagnose

**Example from your work:**
- Step 1: Added AuthProvider to root layout
- Check: Run app → no "useAuth must be in provider" error ✓
- Check: See import errors from 4 files → this is expected ✓
- Proceed to Step 2

### 5.3 Document as You Go
- [ ] Which files did you actually change?
- [ ] What did the console show (errors, warnings)?
- [ ] How does this compare to what you expected?

---

## Section 6: Verifying Everything Works

### 6.1 Automated Checks
- [ ] Run build: `npm run build` (or equivalent)
  - Should compile without errors
- [ ] Run tests: `npm run test` (if you have tests)
  - Should pass
- [ ] Run type checker: `tsc --noEmit` (if using TypeScript)
  - Should have no errors
- [ ] Search for old patterns: `grep -r "oldImportPath"` (or equivalent)
  - Should find nothing (or only expected results)

### 6.2 Manual Testing
- [ ] Test the main flow affected by your change
  - Example: Login flow if you changed auth
  - Example: Watchlist page if you changed data fetching
- [ ] Test related features
  - Example: Logout, password reset if you changed login
- [ ] Test on different scenarios
  - First-time user vs returning user
  - Different browser if possible
  - Different network speed if possible (DevTools throttling)

### 6.3 Verify No Regressions
- [ ] Did you break anything unrelated?
  - Click around the app, try different pages
  - Look for console errors
  - Check that features still work

### 6.4 Final Verification Checklist
- [ ] All files that needed to change have been changed
  - Use: `grep -r "pattern"` to verify nothing was missed
- [ ] All imports are correct
  - Example: `grep -r 'useAuth'` shows all point to correct location
- [ ] No old/incorrect code remains
  - Example: Old provider files deleted or unused
- [ ] Build passes
- [ ] Tests pass
- [ ] Manual testing passed

---

## Section 7: Documenting Your Work

### 7.1 Write a Summary
- [ ] What was the problem?
- [ ] What did you change?
- [ ] Why did you change it this way?
- [ ] What files were affected?

**Example:**
'''
Problem: Auth tokens weren't available when components tried to use them,
causing "useAuth must be within AuthProvider" errors.

Solution: Moved AuthProvider from page-level to root layout to provide
context globally. Updated all imports to use canonical provider location.

Files changed:
- app/layout.tsx: Added AuthProvider wrapper
- components/user-nav.tsx: Fixed import path
- components/auth/signup-form.tsx: Fixed import path
- components/dashboard/watchlist.tsx: Fixed import path
- features/watchlists/hooks/useWatchlist.ts: Fixed import path

Why: Root provider ensures all components have access to auth context,
eliminating race conditions. Canonical import path prevents confusion
about which provider to use.
'''

### 7.2 Update Code Comments (if needed)
- [ ] Add comments explaining non-obvious decisions
  - Example: "Provider must be above ServiceProvider because auth is needed"
  - Example: "Must subscribe to onIdTokenChanged to handle token refresh"
- [ ] Link to related issues or documentation

### 7.3 Share Knowledge
- [ ] Tell your team what you changed and why
- [ ] If this reveals a process improvement, document it
  - Example: "Add grep verification step to refactoring checklist"

---

## Quick Decision Tree

**Use this to decide how much of the checklist to follow:**

'''
Is this a one-line typo fix?
├─ Yes → Just fix it, minimal checklist needed
└─ No → Continue...

Will anyone else's code be affected?
├─ No → Follow sections 1-5
└─ Yes → Follow all sections

Am I changing imports/exports or file locations?
├─ Yes → Do section 2.2 (audit dependencies) carefully
└─ No → Standard sections

Is this initialization/setup code (like providers)?
├─ Yes → Do section 2.3 (dependencies) and 3.1 (order matters)
└─ No → Standard sections

Could this affect timing/async behavior?
├─ Yes → Do section 2.4 (race conditions) and test thoroughly
└─ No → Standard sections
'''

---

## Common Mistakes (Avoid These!)

| Mistake | Why It's Bad | Prevention |
|---------|-------------|-----------|
| "I'll just change this one thing" then realize 5 other files break | Incomplete analysis | Use grep/search before starting |
| Assuming you found all affected code | Silent failures in untested code | Document list of affected files first |
| Not testing after each step | Can't tell which step broke something | Test after every atomic change |
| Changing multiple things at once | Can't isolate the cause of failures | Do one logical change, then test |
| Forgetting to update imports in one place | App works in some places, breaks in others | Use final grep verification |
| Not understanding why old code existed | Repeat the same mistake later | Document decisions in comments |
| Only testing the happy path | Edge cases are fragile | Test offline, slow network, errors |
| Not planning rollback | If it breaks, you're stuck | Document what needs to be undone |

---

## When to Ask for Help

Stop and ask for help if:
- [ ] You can't reproduce the problem
- [ ] You don't understand why the current design exists
- [ ] Your change will affect more than 10 files
- [ ] You're not sure if this is a breaking change
- [ ] You found conflicting requirements
- [ ] You can't think of a way to test this safely
- [ ] Multiple people own the code you're changing

---

## Checklist Summary (Print This)

Before making changes:
- [ ] I understand the current state
- [ ] I have a list of all affected files (verified with search tools)
- [ ] I have a plan with clear steps
- [ ] I know what success looks like for each step
- [ ] I have a rollback plan
- [ ] I know what to test and when

While making changes:
- [ ] I'm doing one logical change at a time
- [ ] I'm testing after each change
- [ ] I'm stopping if something unexpected happens
- [ ] I'm documenting what I did and why

After making changes:
- [ ] Build passes
- [ ] Tests pass
- [ ] Manual testing passed
- [ ] Verification grep commands show clean state
- [ ] Team is aware of the change
- [ ] Decision and process are documented
