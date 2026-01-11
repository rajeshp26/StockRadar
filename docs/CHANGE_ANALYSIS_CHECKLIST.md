# System Change Analysis & Impact Assessment Checklist

A practical guide for analyzing proposed changes and assessing their impact on the codebase, including end-to-end call stack analysis.

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

## Section 2: Call Stack Analysis - Complete Request Flow

**This section is critical for understanding how your change affects the entire system.**

### 2.1 Map the Complete User Journey

Start with the user action that triggers the problem:

- [ ] **What user action triggers this flow?**
  - Example: "User clicks 'View Watchlist' button"
- [ ] **What is the entry point in the code?**
  - Example: "watchlist/page.tsx component mount"
- [ ] **Trace the complete flow step by step**

**Example Format:**
```
User Action: Click "View Watchlist" button
  ↓
Entry Point: web/src/features/watchlists/pages/watchlist.tsx
  ├─ Component mounts
  ├─ useEffect hook triggers
  ├─ Calls: useWatchlist() hook
  │
  ├─ useWatchlist Hook: web/src/features/watchlists/hooks/useWatchlist.ts
  │  ├─ Retrieves user from useAuth()
  │  ├─ Calls: watchlistService.getDefaultWatchlist()
  │  │
  │  ├─ WatchlistService: web/src/features/watchlists/services/watchlist.service.ts
  │  │  ├─ Imports: api from @/lib/api
  │  │  ├─ Calls: api.post('/watchlists/default-with-items', {})
  │  │  │
  │  │  ├─ Axios Instance: web/src/lib/api.ts
  │  │  │  ├─ Has interceptor that adds Authorization header
  │  │  │  ├─ Intercepts request before sending
  │  │  │  ├─ Adds: Authorization: Bearer <token>
  │  │  │  │
  │  │  │  ├─ Proxy Route: web/src/app/api/proxy/[...path]/route.ts
  │  │  │  │  ├─ Receives request with Authorization header
  │  │  │  │  ├─ Forwards to: http://127.0.0.1:8001/api/watchlists/default-with-items
  │  │  │  │  ├─ Preserves: Authorization header
  │  │  │  │  │
  │  │  │  │  ├─ Backend Endpoint: backend/api/watchlists.py
  │  │  │  │  │  ├─ Route: POST /watchlists/default-with-items
  │  │  │  │  │  ├─ Dependency: Depends(get_current_user_dep)
  │  │  │  │  │  │
  │  │  │  │  │  ├─ Auth Dependency: backend/auth.py get_current_user()
  │  │  │  │  │  │  ├─ Extracts: Authorization header
  │  │  │  │  │  │  ├─ Verifies: Firebase token
  │  │  │  │  │  │  ├─ Returns: Decoded user object OR raises 401
  │  │  │  │  │  │  │
  │  │  │  │  │  ├─ Service Call: watchlist_service.get_default_watchlist_with_items(user.uid)
  │  │  │  │  │  │  ├─ Database Query: SELECT * FROM watchlists WHERE user_id = user.uid
  │  │  │  │  │  │  ├─ Returns: WatchlistWithItems
  │  │  │  │  │  │  │
  │  │  │  │  │  ├─ Response: 200 OK + watchlist data
  │  │  │  │  │  │
  │  │  │  │  ├─ Frontend receives response
  │  │  │  │  │
  │  │  │  ├─ Response Interceptor: web/src/lib/api.ts
  │  │  │  │  ├─ Checks: Response status
  │  │  │  │  ├─ If 401: Log "Unauthorized"
  │  │  │  │  ├─ Returns: Parsed response data
  │  │  │  │  │
  │  │  ├─ watchlistService returns: WatchlistWithItems
  │  │  │
  │  ├─ useWatchlist updates state
  │  │
  ├─ watchlist.tsx renders with data
  │
User sees: Watchlist displayed on page ✓
```

### 2.2 Document Each Layer

For each layer in the call stack, document:

**Frontend Layer:**
- [ ] **UI Component:** What file? What triggers it?
- [ ] **Hooks:** What hooks does it use? (useAuth, useWatchlist, etc.)
- [ ] **Services:** What services does it call?
- [ ] **HTTP Client:** How is the request made? (Axios, fetch, etc.)

**Proxy/Gateway Layer:**
- [ ] **Route Handler:** Where is the proxy configured?
- [ ] **Header Forwarding:** Are headers preserved or modified?
- [ ] **URL Rewriting:** Is the endpoint path modified?
- [ ] **Environment:** What is the backend URL?

**Backend Layer:**
- [ ] **Entry Point:** What file handles the endpoint?
- [ ] **Route:** What is the exact path and HTTP method?
- [ ] **Dependencies:** What injected dependencies does it require?
- [ ] **Authentication:** How is the user verified?
- [ ] **Authorization:** What permissions are required?
- [ ] **Business Logic:** What service/function handles the work?
- [ ] **Database:** What queries are executed?
- [ ] **Response:** What data is returned?

**Data Flow:**
- [ ] **Request Path:** User Action → Frontend → Proxy → Backend
- [ ] **Response Path:** Backend → Proxy → Frontend → UI
- [ ] **Data Transformations:** How is data modified at each layer?

### 2.3 Identify Critical Dependencies in the Flow

- [ ] **What external services are required?**
  - Firebase? Database? Third-party APIs?
  - Are they available in the current environment?
- [ ] **What initialization must happen first?**
  - Must Firebase be initialized before making requests?
  - Must the user be authenticated?
  - Must environment variables be set?
- [ ] **What can fail at each step?**
  - Step 1 fails: "Authorization header missing" → Backend returns 401
  - Step 2 fails: "User not found in database" → Backend returns 404
  - Step 3 fails: "Network timeout" → Request never completes

**Create a failure matrix:**

| Layer | Failure Mode | Symptom | Impact |
|-------|--------------|---------|--------|
| Frontend | Authorization header not added | 401 response | User can't see data |
| Frontend | Request timeout | Network error | User sees spinner forever |
| Proxy | Backend unreachable | ECONNREFUSED | Request fails |
| Backend | Token invalid | 401 response | User forced to re-login |
| Backend | Database error | 500 response | Service unavailable |

### 2.4 Verify the Call Stack with Code Review

- [ ] **For each file in the call stack, read the actual code**
  - Don't assume—verify with grep and file reading
  - Check: imports, function signatures, return types
  - Example: Verify api.ts actually exports `api` instance
- [ ] **Check for missing pieces**
  - Is the Axios instance created?
  - Is the interceptor attached?
  - Is the token being set?
- [ ] **Verify data transformations**
  - What data enters this layer?
  - What data leaves this layer?
  - Are transformations correct?

---

## Section 3: Impact Analysis of Your Proposed Change

### 3.1 How Does Your Change Affect the Call Stack?

For each layer in the call stack:

- [ ] **Does this change affect this layer?**
- [ ] **If yes, how does it change the behavior?**
- [ ] **Will this break anything downstream?**

**Example:**

```
Your Change: Populate web/src/lib/api.ts with Axios instance

Impact on Call Stack:
├─ Frontend UI Component (watchlist.tsx)
│  └─ No change needed ✓
├─ useWatchlist Hook
│  └─ No change needed ✓
├─ WatchlistService
│  └─ api.post() now works (was broken before) ✓
├─ Axios Instance (api.ts)
│  └─ NOW POPULATED - interceptor now works ✓
│     └─ Authorization header NOW ADDED ✓
├─ Proxy Route
│  └─ NOW receives Authorization header ✓
│     └─ Now forwards header to backend ✓
├─ Backend Endpoint
│  └─ NOW receives Authorization header ✓
│     └─ Token verification now succeeds ✓
└─ User sees watchlist ✓ (previously got 401 error)
```

### 3.2 Trace Each Affected File

- [ ] **List every file touched by this change**
  - Files modified: Which ones?
  - Files deleted: Which ones?
  - Files created: Which ones?
  - Files affected: Which files depend on the above?
- [ ] **For each affected file:**
  - [ ] Read the current code
  - [ ] Understand what it does
  - [ ] Understand how your change affects it
  - [ ] Will it still work after your change?

**Use grep to verify:**
```bash
# Find all files that import the changed file
grep -r "import.*from.*@/lib/api" web/src

# Verify all imports still work after your change
grep -r "from.*@/lib/api" web/src | wc -l

# Confirm no broken imports remain
grep -r "api\." web/src | head -20
```

### 3.3 Environment-Specific Impact

- [ ] **Does this change work in development?**
  - Is the environment variable `NEXT_PUBLIC_API_URL` set?
  - Is the backend running at expected URL?
- [ ] **Does this change work in staging?**
  - Are environment variables different?
  - Is the backend URL different?
- [ ] **Does this change work in production?**
  - Are there production-specific settings?
  - Is the backend URL different?
- [ ] **Does this change affect SSR (Server-Side Rendering)?**
  - Can Axios run on the server?
  - Are headers available on the server?

---

## Section 4: Planning Your Change

### 4.1 Define What You're Going to Do

- [ ] Write out the change clearly
  - What are you modifying?
  - What are you deleting?
  - What are you adding?
- [ ] Provide before/after examples of code
- [ ] Explain why this solves the problem

### 4.2 List Every File That Needs to Change

- [ ] Which files will I modify?
- [ ] Which files will I delete?
- [ ] Which files will I create?
- [ ] Which files depend on the above and also need changes?
  - Use: `grep -r 'oldPath'` to find all references
  - Example: If changing `export default api` to `export const api`, find all files that import it

### 4.3 Check for Hidden Dependencies

- [ ] Does this module initialize anything when imported?
  - Example: Does it set up Firebase? Connect to a database?
  - If yes, will moving/changing it break initialization order?
- [ ] Does this depend on context or props that aren't always available?
  - Example: Can this component be used at the app root, or only within a specific layout?
  - If yes, where is it safe to place it?
- [ ] Are there multiple versions or definitions of the same thing?
  - Example: Two different `useAuth` hooks in different locations
  - This suggests incomplete refactoring or confusion
- [ ] **In the call stack, does this change affect initialization order?**
  - Example: AuthProvider must initialize before API client uses the token

### 4.4 Think About Edge Cases

- [ ] Will this work on first load? On page refresh?
- [ ] What if the user is offline?
- [ ] What if something fails (network error, missing data)?
- [ ] What about old browser versions or different environments (SSR, mobile)?

---

## Section 5: Assessing the Risk

### 5.1 What Could Go Wrong?

- [ ] Could this break the app on startup?
- [ ] Could this break a specific feature silently (user doesn't see an error)?
- [ ] Could this break only certain users (mobile, offline, slow networks)?
- [ ] Could this create a maintenance burden (future developers won't know why something is ordered this way)?
- [ ] **Could this break any step in the call stack?**
  - Example: Missing interceptor → requests sent without auth → 401 errors

### 5.2 Is This a Breaking Change?

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

### 5.3 Create a Quick Rollback Plan

- [ ] If this goes wrong in 5 minutes, what do I do?
  - Revert the commit?
  - Which files need to be restored?
- [ ] How will I know if it's broken?
  - What error will I see?
  - What should I test?

---

## Section 6: Breaking Work Into Steps

### 6.1 What Order Should Changes Happen?

- [ ] Do foundational changes first
  - Example: Install global provider before updating imports
- [ ] Do dependent changes after
  - Example: Update imports after provider exists
- [ ] Can you test after each step?
  - If no, you might be doing too much at once
- [ ] **For the call stack, do changes from top to bottom or bottom to top?**
  - Frontend first? Backend first? Middle first?
  - Which order minimizes risk?

### 6.2 Define Success Criteria for Each Step

For each step, write down:

- [ ] What should happen if this step succeeds?
- [ ] What should I test/verify?
- [ ] What error is acceptable? (e.g., import errors are OK after step 1, but not after step 5)
- [ ] What error means I should stop and fix it?

**Example:**

- Step 1: Populate api.ts with Axios instance
  - Success: File contains `export const api = axios.create(...)`
  - Test: `grep "export const api" web/src/lib/api.ts`
  - Expected errors: None at this step
  - Stop if: File still empty or has syntax errors

- Step 2: Start dev server
  - Success: Server starts, no import errors
  - Test: Run `npm run dev`, check console
  - Expected errors: None
  - Stop if: Server fails to start

- Step 3: Make authenticated request
  - Success: Authorization header present in Network tab
  - Test: Open DevTools, check request headers
  - Expected errors: None
  - Stop if: Authorization header missing or malformed

### 6.3 Plan Your Testing

- [ ] After each step, what specific thing will you test?
  - "Run app and check console for errors"
  - "Navigate to /login and verify form renders"
  - "Check that grep shows correct import paths"
  - "Verify Authorization header is present in Network tab"
- [ ] How will you verify success?
  - Manual inspection of code
  - Running app in browser
  - Running automated tests
  - Using `grep` or search tools
  - Checking Network tab for headers
  - Checking backend logs for successful authentication

---

## Section 7: Executing the Change

### 7.1 Before You Start

- [ ] Commit your current work (clean git status)
- [ ] Create a feature branch (if using version control)
- [ ] Write down the current state
  - What's broken right now?
  - What should work after?
- [ ] Document the call stack for reference
  - Keep the call stack diagram visible while you work

### 7.2 Execute Step by Step

For each step:

- [ ] Make the change
- [ ] Verify it worked (run tests/checks)
- [ ] Write down what happened
  - Did you see expected errors?
  - Any surprises?
- [ ] **Check the call stack at this step**
  - Did the change affect what you expected?
  - Are downstream effects as predicted?
- [ ] **Stop immediately if something unexpected happens**
  - Don't assume you can fix it by continuing
  - Stop and diagnose

**Example from your work:**

- Step 1: Populated api.ts with Axios instance
- Check: `grep "export const api"` shows instance exists ✓
- Check: Import errors gone from watchlistService ✓
- Check: Call stack now has working Axios instance ✓
- Proceed to Step 2

### 7.3 Document as You Go

- [ ] Which files did you actually change?
- [ ] What did the console show (errors, warnings)?
- [ ] How does this compare to what you expected?
- [ ] **How did each step affect the call stack?**

---

## Section 8: Verifying Everything Works

### 8.1 Automated Checks

- [ ] Run build: `npm run build` (or equivalent)
  - Should compile without errors
- [ ] Run tests: `npm run test` (if you have tests)
  - Should pass
- [ ] Run type checker: `tsc --noEmit` (if using TypeScript)
  - Should have no errors
- [ ] Search for old patterns: `grep -r "oldImportPath"` (or equivalent)
  - Should find nothing (or only expected results)

### 8.2 Call Stack Verification

Verify that each step in the call stack works:

- [ ] **Frontend component renders**
  - No errors in console
  - Component mounts successfully
- [ ] **Hook calls service**
  - useWatchlist hook executes without errors
  - Service is called
- [ ] **Service makes HTTP request**
  - API client exists and is not null/undefined
  - Request is made to correct endpoint
- [ ] **Interceptor adds auth header**
  - Authorization header present in Network tab
  - Header format is correct: `Bearer <token>`
- [ ] **Proxy forwards request**
  - Proxy receives request with auth header
  - Proxy forwards request to backend
  - Backend receives request with auth header
- [ ] **Backend authenticates user**
  - Token is valid
  - User object is extracted
  - No 401 errors
- [ ] **Backend returns data**
  - Response status is 200
  - Response body contains expected data
- [ ] **Frontend receives data**
  - Response parsed correctly
  - Component state updated with data
  - UI displays data

### 8.3 Manual Testing

- [ ] Test the main flow affected by your change
  - Example: Login flow if you changed auth
  - Example: Watchlist page if you changed data fetching
- [ ] Test related features
  - Example: Logout, password reset if you changed login
- [ ] Test on different scenarios
  - First-time user vs returning user
  - Different browser if possible
  - Different network speed if possible (DevTools throttling)
- [ ] **Test each step in the call stack manually**
  - Open DevTools Network tab
  - Trigger the action
  - Verify request is sent with Authorization header
  - Verify response is 200 OK
  - Verify UI displays data

### 8.4 Verify No Regressions

- [ ] Did you break anything unrelated?
  - Click around the app, try different pages
  - Look for console errors
  - Check that features still work
- [ ] **Did you break anything upstream or downstream in the call stack?**
  - Check all pages that use the api client
  - Check all services that use the api instance
  - Verify authentication still works elsewhere

### 8.5 Final Verification Checklist

- [ ] All files that needed to change have been changed
  - Use: `grep -r "pattern"` to verify nothing was missed
- [ ] All imports are correct
  - Example: `grep -r 'from.*@/lib/api'` shows all point to correct location
- [ ] No old/incorrect code remains
  - Example: Old api files deleted or unused
- [ ] Build passes
- [ ] Tests pass
- [ ] Manual testing passed
- [ ] **Call stack verification passed**
  - All layers working correctly
  - Request flows from frontend to backend
  - Response flows from backend to frontend
  - Authorization header present at each step
- [ ] **Network inspection passed**
  - Authorization header present in requests
  - Response status is 200 (not 401)
  - Response body contains expected data

---

## Section 9: Documenting Your Work

### 9.1 Write a Summary

- [ ] What was the problem?
- [ ] What did you change?
- [ ] Why did you change it this way?
- [ ] What files were affected?
- [ ] **How does this fix the call stack?**

**Example:**

```
Problem: API requests not authenticated. Authorization header missing
from all requests, causing 401 errors from backend.

Root Cause: api.ts file was empty. Axios instance and interceptor
that adds Authorization header were missing.

Solution: Populated api.ts with:
1. Axios instance creation (axios.create)
2. setAuthToken function to set Authorization header
3. Request interceptor to log headers (debugging)
4. Response interceptor to handle 401 errors

Files Changed:
- web/src/lib/api.ts: Added Axios configuration

Affected Files (no changes needed):
- web/src/features/auth/services/token-manager.ts: Now works correctly
- web/src/providers/auth-provider.tsx: Already calls setAuthToken correctly
- web/src/shared/contexts/ServiceContext.tsx: api now available
- web/src/features/watchlists/services/watchlist.service.ts: api.post now works
- backend/api/watchlists.py: Now receives Authorization header

Why This Works:
Call Stack Before:
  Frontend → Axios (broken) → Proxy → Backend (401)

Call Stack After:
  Frontend → Axios (working) → Proxy → Backend (200) ✓

The Axios instance now exists and has interceptor to add auth header.
This unblocks the entire authentication chain.
```

### 9.2 Create a Call Stack Diagram

- [ ] Document the before/after call stack
  - Show which parts were broken
  - Show which parts are now fixed
  - Show data flow at each step
- [ ] Include this in your commit message or PR description

### 9.3 Update Code Comments (if needed)

- [ ] Add comments explaining non-obvious decisions
  - Example: "Axios instance must be populated here for interceptor to work"
  - Example: "setAuthToken is called by token-manager on auth state changes"
- [ ] Link to related issues or documentation

### 9.4 Share Knowledge

- [ ] Tell your team what you changed and why
- [ ] Explain the call stack and how the fix enables it
- [ ] If this reveals a process improvement, document it
  - Example: "Add call stack verification step to change checklist"

---

## Section 10: Call Stack Analysis Template

**Use this template for your next change:**

```
USE CASE: [Description of user action]

ENTRY POINT: [File and function where it starts]

COMPLETE CALL STACK:
┌─ Frontend Layer
│  ├─ File: [path]
│  ├─ Function: [name]
│  └─ Action: [what it does]
├─ Service Layer
│  ├─ File: [path]
│  ├─ Function: [name]
│  └─ Action: [what it does]
├─ HTTP Client Layer
│  ├─ File: [path]
│  ├─ Interceptors: [list]
│  └─ Headers: [what's added]
├─ Proxy/Gateway Layer
│  ├─ File: [path]
│  ├─ Route: [endpoint]
│  └─ Forwarding: [what's preserved/modified]
└─ Backend Layer
   ├─ File: [path]
   ├─ Endpoint: [method + path]
   ├─ Dependencies: [injected dependencies]
   ├─ Logic: [what it does]
   └─ Response: [what it returns]

FAILURE POINTS:
- [Layer] could fail if [condition] → [symptom]
- [Layer] could fail if [condition] → [symptom]

IMPACT OF PROPOSED CHANGE:
- [Layer] affected? [yes/no] → [how?]
- [Layer] affected? [yes/no] → [how?]

VERIFICATION:
- [ ] Each layer works independently
- [ ] Data flows correctly between layers
- [ ] Headers preserved through proxy
- [ ] Backend receives request with auth
- [ ] Frontend receives response with data
```

---

## Quick Decision Tree

**Use this to decide how much of the checklist to follow:**

```
Is this a one-line typo fix?
├─ Yes → Just fix it, minimal checklist needed
└─ No → Continue...

Will anyone else's code be affected?
├─ No → Follow sections 1-5
└─ Yes → Follow all sections

Does this change affect authentication or HTTP requests?
├─ Yes → Do Section 2 (call stack) thoroughly
└─ No → Standard sections

Am I changing imports/exports or file locations?
├─ Yes → Do section 3.2 (trace each affected file) carefully
└─ No → Standard sections

Is this initialization/setup code (like providers)?
├─ Yes → Do section 4.3 (dependencies) and 5.1 (order matters)
└─ No → Standard sections

Could this affect timing/async behavior?
├─ Yes → Do section 2.4 (race conditions) and test thoroughly
└─ No → Standard sections
```

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
| Not tracing the complete call stack | Miss dependencies and side effects | Map out every step from UI to backend |
| Not verifying headers in Network tab | Silent auth failures | Check DevTools for Authorization header |
| Assuming interceptor was attached | Requests sent without auth | Verify interceptor in api.ts |

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
- [ ] You can't map out the complete call stack
- [ ] You don't know where headers are added/removed in the proxy
- [ ] Backend authentication logic is unclear

---

## Checklist Summary (Print This)

**Before making changes:**

- [ ] I understand the current state
- [ ] I have mapped the complete call stack from UI to backend
- [ ] I have a list of all affected files (verified with search tools)
- [ ] I understand each layer's role in the call stack
- [ ] I have a plan with clear steps
- [ ] I know what success looks like for each step
- [ ] I have a rollback plan
- [ ] I know what to test and when

**While making changes:**

- [ ] I'm doing one logical change at a time
- [ ] I'm testing after each change
- [ ] I'm checking the call stack at each step
- [ ] I'm stopping if something unexpected happens
- [ ] I'm documenting what I did and why

**After making changes:**

- [ ] Build passes
- [ ] Tests pass
- [ ] Manual testing passed
- [ ] Verification grep commands show clean state
- [ ] Call stack verification passed (all layers working)
- [ ] Network tab shows Authorization header present
- [ ] Backend receives requests with auth header
- [ ] Frontend receives 200 responses with data
- [ ] Team is aware of the change
- [ ] Decision and process are documented
- [ ] Call stack diagram is documented