# Environment Setup Guide

This guide provides a comprehensive overview of the setup process for the StockerPro project. By following these steps, you will have a secure, fully functional development environment for both the frontend and backend.

## Core Principle: Environment Variables

We do not commit secrets or environment-specific configurations directly to the git repository. Instead, we use a system of environment files:

*   **.env.example:** A template file that lists all the necessary environment variables for a service (e.g., `web/` or `backend/`).
*   **.env / .env.local:** Your personal, secret environment file. You create this by copying the `.env.example` file and filling in your actual credentials. These files are **never** committed to git, thanks to the project's `.gitignore` file.

---

## Backend Quick Start (`backend/`)

### Step 1: Create Your Environment File

In your terminal, at the project root, run:

```bash
cp backend/.env.example backend/.env
```

### Step 2: Edit `backend/.env`

Open the `backend/.env` file you just created and fill in the following values:

*   `SUPABASE_URL` & `SUPABASE_SERVICE_ROLE_KEY`:
    1.  Navigate to your Supabase project dashboard.
    2.  Go to **Project Settings** > **API**.
    3.  Copy the **Project URL** and the **`service_role` Secret** into your `.env` file.

*   `FIREBASE_PROJECT_ID`:
    1.  Navigate to the [Firebase Console](https://console.firebase.google.com/).
    2.  Go to **Project settings** (the gear icon) > **General** tab.
    3.  Copy the **Project ID** into your `.env` file.

*   `GEMINI_API_KEY` (Optional):
    1.  Go to [Google AI Studio](https://aistudio.google.com/).
    2.  Click **"Get API key"** and copy it into your `.env` file.

### Step 3: Start the Backend

To start the backend, navigate to the project's **root directory** in your terminal and run the following single command:

```bash
nix-shell --run "bash backend/start.sh"
```

This command handles the Nix environment and executes the startup script, which manages the virtual environment and dependencies.

#### Dependency preflight (`requirements.txt`)

Both long-running processes — the API (`backend/main.py`) and the background
worker (`backend/scheduler_worker.py`) — run a dependency preflight at startup.
It compares the **installed** `defeatbeta-api` and `duckdb` (and every other
pinned package) against `backend/requirements.txt` and logs a loud `DEPENDENCY
DRIFT DETECTED` banner when they disagree.

This exists because a silent drift once emptied the price pipeline for roughly
six weeks. `requirements.txt` declared `defeatbeta-api==0.0.61` and
`duckdb==1.5.3`, while the installed environment held `0.0.50` and `1.4.3`.
`defeatbeta-api` 0.0.50 pins `duckdb==1.4.3`, and the `cache_httpfs` extension it
loads at connection time does not exist for DuckDB 1.4.3 (the community-extension
repository returns HTTP 404 for 1.4.3 and 206 for 1.5.3). Every price fetch
therefore died at `DuckDBClient` initialisation and degraded to a per-symbol
warning, so `price_history` drained out with nothing erroring.

Run the check on demand:

```bash
python backend/scripts/preflight_dependencies.py          # exit 1 on drift
python backend/scripts/preflight_dependencies.py --quiet  # silent when clean
```

Set `PRICE_PREFLIGHT_FATAL=1` to make a **pipeline-critical** drift fatal at
startup instead of a warning (recommended for price-only deployments and CI).
Drift in a non-pricing package is reported but never fatal.

To fix drift:

```bash
python -m pip install -r backend/requirements.txt
```

---

## Frontend Quick Start (`web/`)

### Step 1: Create Your Environment File

In your terminal, at the project root, run:

```bash
cp web/.env.example web/.env.local
```

### Step 2: Edit `web/.env.local`

Open the `web/.env.local` file. You will need to populate it with your Firebase project's web app configuration.

1.  Navigate to the [Firebase Console](https://console.firebase.google.com/).
2.  Go to **Project settings** > **General** tab.
3.  Scroll down to the "Your apps" section and select your web app.
4.  Under **Firebase SDK snippet**, select **Config**.
5.  Copy the values for `apiKey`, `authDomain`, `projectId`, etc., into the corresponding `NEXT_PUBLIC_FIREBASE_*` variables in your `web/.env.local` file.

### Step 3: Install Dependencies & Start the Server

From the project's **root directory**, run:

```bash
cd web && npm install && npm audit fix && npm run dev
```

This will install all packages, fix any known vulnerabilities, and start the Next.js development server, typically on `http://localhost:3000`.

---

## Security, Diagnostics, and Testing

The previous version of this guide contained detailed information on diagnostic scripts and generating test tokens. These sections are still relevant and have been preserved below.

### Diagnostic Scripts

The `scripts/` directory contains several helpful diagnostic tools:

*   `debug_backend_sync.py`: Sends a test user sync request to the backend.
*   `debug_stock.py`: Tests the `yfinance` library by fetching stock data.
*   `diagnostic.sh`: Runs a comprehensive set of diagnostics on your development environment.

### Generating a Test Authentication Token

To generate a Firebase Custom Token for testing, run the following command from the project's **root directory**, ensuring your `backend/.env` file is correctly configured:

```bash
nix-shell --run "python scripts/generate_test_token.py YOUR_TEST_USER_UID"
```
