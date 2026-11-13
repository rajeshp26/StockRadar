
# Authentication Refactor: A Robust and Scalable Design

This document details the architecture of the StockerPro authentication system, including the end-to-end flow from user sign-up to data synchronization.

## 1. Core Principles

-   **Single Source of Truth for Identity**: Firebase Authentication is the sole authority for user identity and the issuance of authentication tokens (JWTs).
-   **Decoupled Application Database**: Supabase stores application-specific user data (profiles, watchlists), but it does **not** handle authentication. It trusts the `auth_id` (the UID from the auth provider) provided by the backend.
-   **Backend-Driven Synchronization**: The FastAPI backend is responsible for keeping the user profile in Supabase synchronized with the user's identity from the authentication provider.

---

## 2. User Identity and `auth_id` Lifecycle

This section explicitly answers the critical questions of how a user's identity is created, stored, and verified.

### Phase 1: New User Sign-Up & Initial Sync

1.  **Who generates the `auth_id`?**
    **The Auth Provider (currently Firebase).** When a user signs up on the frontend, the provider's SDK is called. The provider creates a new user and generates a permanent, unique User ID (UID). This UID is the `auth_id`.

2.  **Who saves the `auth_id` to Supabase?**
    **Our Backend.** Immediately after sign-up, the frontend calls our backend's `POST /api/proxy/users/sync` endpoint. The backend extracts the `auth_id` from the user's JWT and **inserts** a new record into the Supabase `users` table, linking the provider's identity to a new application profile.

### Phase 2: Subsequent Logins & Data Consistency

1.  **Are we using the same `auth_id`?**
    **Yes.** When a returning user logs in, the auth provider issues a token containing the **exact same `auth_id`**.

2.  **How is it used?**
    The frontend again calls `POST /api/proxy/users/sync`. This time, the backend finds an existing user record matching the `auth_id` and simply **updates** it (e.g., updating the `last_signed_in` timestamp).

This two-phase lifecycle ensures a robust and consistent identity management system.

---

## 3. The Authentication Flow (State Machine)

The frontend uses a formal state machine to manage authentication status, ensuring a predictable and resilient user experience.

1.  **Initialization:** `AuthProvider` status is `'initializing'`.
2.  **Listen for Token Changes:** `AuthProvider` subscribes to the provider's SDK for token changes (e.g., `onIdTokenChanged`).
3.  **Token Exchange:** The provider orchestrates the exchange of the auth token for an application user profile from our backend via the `/users/sync` endpoint.
4.  **Rendering:** The `AuthenticatedLayout` observes the auth status and renders the appropriate UI.

---

## 4. Backend to Supabase Communication

The backend requires privileged access to the Supabase database. This is handled securely via environment variables (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`) used to initialize an admin-level Supabase client.

---

## 5. Architectural Refinements (Post-Incident Addendums)

The following sections detail specific architectural improvements made after identifying flaws in the initial design.

### 5.1. Decoupling API and Authentication

-   **Problem**: The frontend's API module was tightly coupled with authentication logic.
-   **Solution**: A dedicated `token-manager.ts` was created to isolate token handling. The API client is now only responsible for HTTP configuration.

### 5.2. User Sync Data Contract

-   **Problem**: The frontend was not sending the required `email` and `username` in the `/users/sync` request.
-   **Solution**: The `AuthService` on the frontend was corrected to always send the required data, fulfilling the backend's API contract.

---

## 6. Replacing the Authentication Provider

This system is designed to be **pluggable**, allowing the authentication provider to be swapped without a full rewrite. The decoupling of the application database (Supabase) from the identity provider is the key to this flexibility.

If we were to replace Firebase with another provider (e.g., Auth0, Okta), the following changes would be required:

### 1. Frontend Changes (`web/`)

-   **SDK Replacement**: All calls to the Firebase SDK would be replaced with the new provider's SDK for handling login, sign-up, and token management.
-   **Configuration**: The Firebase-specific configuration would be swapped with the new provider's credentials (e.g., Client ID, Domain).

### 2. Backend Changes (`backend/`)

-   **Token Verification Logic**: The `get_current_user` dependency must be updated. The logic would be switched from using the Firebase Admin SDK to using the new provider's recommended library for JWT validation.
-   **Credentials**: The `google_credentials.json` file would be replaced with the new provider's secrets or environment variables.

### 3. Data and Migration

-   **`auth_id` Source**: The `auth_id` in the Supabase `users` table would now come from the new provider.
-   **User Migration Strategy**: A migration plan for existing users would be critical. This would likely involve a one-time process to link their existing Supabase user profiles to the new `auth_id` from the new provider upon their first login post-migration.
