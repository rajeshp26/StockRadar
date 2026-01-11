
# Detailed Flow: User Login and Watchlist Retrieval

This document provides a granular, step-by-step breakdown of the user authentication process and the subsequent retrieval of the watchlist data. It is intended to be a definitive guide for understanding this critical application flow.

## 1. User Authentication Flow

The authentication process is a coordinated effort between the Next.js frontend, the Next.js API proxy, the FastAPI backend, and Firebase Authentication.

**Step 1: User Initiates Login (Frontend)**

- **Action**: The user enters their credentials and clicks the "Login" button.
- **Component**: `web/src/components/auth/login-form.tsx`
- **Expectation**: The `onSubmit` function is triggered, which uses the Firebase SDK to authenticate the user.

**Step 2: Firebase Authentication (Client-Side)**

- **Action**: The Firebase SDK communicates with the Firebase Authentication service to verify the user's credentials.
- **Expectation**: Upon successful authentication, Firebase returns a JSON Web Token (JWT) to the client.

**Step 3: Token Storage and Backend Sync (Frontend)**

- **Action**: The JWT is stored in the browser's local storage. The `syncWithBackend` function is then called to synchronize the user's profile with the backend.
- **Component**: `web/src/components/auth/auth-provider.tsx`
- **Expectation**: An API request is made to `/api/proxy/users/sync`, with the JWT included in the `Authorization` header.

**Step 4: Proxy Forwarding (Next.js API Proxy)**

- **Action**: The Next.js API proxy at `web/src/app/api/proxy/[...path]/route.ts` receives the request and forwards it to the FastAPI backend.
- **Expectation**: The proxy must preserve the `Authorization` header and forward it to the backend. This was the point of failure, but the fix ensures the header is always present.

**Step 5: Token Verification and User Sync (Backend)**

- **Action**: The FastAPI backend receives the request, and the `get_current_user` dependency verifies the JWT using the Firebase Admin SDK. The `/users/sync` endpoint then creates or updates the user's profile in the Supabase database.
- **Component**: `backend/api/users.py`, `backend/auth.py`
- **Expectation**: A `200 OK` response is returned, and the user's profile is successfully synchronized.

## 2. Watchlist Data Flow

Once the user is authenticated, the application fetches the user's watchlist data.

**Step 1: Dashboard Page Load (Frontend)**

- **Action**: The user is redirected to the dashboard, and the `DashboardPage` component is rendered.
- **Component**: `web/src/app/(authenticated)/dashboard/page.tsx`
- **Expectation**: The `useWatchlist` hook is called, which initiates the process of fetching the watchlist data.

**Step 2: Fetch Watchlist Data (Frontend)**

- **Action**: The `fetchWatchlist` function in the `useWatchlist` hook makes a POST request to `/api/proxy/watchlists/default-with-items`.
- **Component**: `web/src/features/watchlists/hooks/useWatchlist.ts`, `web/src/features/watchlists/services/watchlist.service.ts`
- **Expectation**: The request is sent with the user's JWT in the `Authorization` header.

**Step 3: Proxy and Backend Processing**

- **Action**: The request is forwarded through the proxy to the backend, which authenticates the user and fetches the watchlist data from the Supabase database.
- **Expectation**: The backend returns a `200 OK` response with the watchlist data in JSON format.

**Step 4: Render Watchlist (Frontend)**

- **Action**: The `useWatchlist` hook receives the data and updates the component's state.
- **Expectation**: The watchlist and its items are displayed on the dashboard.

## 3. Placeholder Code and Refactoring Plan

The following placeholders and areas for improvement have been identified:

- **`get_current_user_dep` in `backend/dependencies.py`**: This placeholder is overridden at runtime, which can be confusing. The action plan is to create a dedicated `auth` module with a `JWTAuthenticator` class that can be imported directly.

- **Hardcoded URLs in Frontend Services**: API endpoints are hardcoded in the frontend services. The action plan is to centralize these endpoints in a single configuration file.

- **Lack of Centralized Error Handling**: The codebase lacks a global error handler, making it difficult to manage and debug errors. The action plan is to implement a global error handler and a generic `api` service to encapsulate API requests.
