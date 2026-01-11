# Environment Setup Guide

This guide provides a comprehensive overview of the setup process for the StockerPro backend, including key lessons learned from troubleshooting the initial setup.

## 1. Professional Project Structure

A clean and organized project structure is crucial for long-term maintainability. The following principles should be adhered to:

*   **Centralized Scripts:** All utility, debugging, and diagnostic scripts should be placed in the `scripts/` directory at the project root. This keeps the root directory clean and easy to navigate.
*   **Comprehensive `.gitignore`:** A robust `.gitignore` file is essential for preventing clutter in the repository. It should ignore:
    *   Log files (`*.log`)
    *   Python cache directories (`__pycache__/`)
    *   Compiled Python files (`*.py[cod]`, `*$py.class`)
    *   Environment files (`.env`)
    *   IDE-specific folders (`.idea/`, `.vscode/`)
*   **Regular Cleanup:** Periodically remove old log files and redundant scripts to maintain a clean and organized codebase.

## 2. Critical Security: The `.gitignore` File

Before adding any credentials or secret files, it is **absolutely essential** to ensure that your project has a comprehensive `.gitignore` file. This file tells your version control system (Git) to ignore specific files and directories, preventing you from accidentally committing sensitive data to your repository.

**A failure to do this is a critical security vulnerability.**

Your `.gitignore` file should be at the root of the project and must be configured to ignore, at a minimum:
*   Secret files: `backend/.env`, `backend/google_credentials.json`
*   Python environment and cache files: `__pycache__/`, `venv/`, `*.pyc`
*   Node.js dependency directories: `node_modules/`
*   IDE-specific configuration folders: `.idea/`, `.vscode/`

A robust, pre-configured `.gitignore` file will be provided for this project to ensure security and a clean repository.

## 3. Prerequisites: Acquiring API Keys & Credentials

Before you can run the backend, you need to gather several secret keys and configuration details from external services. These should be stored in a `.env` file within the `backend/` directory.

### a. Supabase

1.  Navigate to your Supabase project dashboard.
2.  Go to **Project Settings** > **API**.
3.  Under **Project API keys**, you will find:
    *   **Project URL:** Copy this value and add it to your `.env` file as `SUPABASE_URL`.
    *   **`service_role` Secret:** Copy this secret key and add it to your `.env` file as `SUPABASE_SERVICE_ROLE_KEY`. **Important:** The application specifically requires the `service_role` key, not the `anon` key.

### b. Firebase

1.  Navigate to the [Firebase Console](https://console.firebase.google.com/) and select your project.
2.  Go to **Project settings** (the gear icon) > **Service accounts**.
3.  Click **"Generate new private key"**. This will download a JSON file containing your service account credentials.
4.  **Rename this file to `google_credentials.json`** and place it in the `backend/` directory.
5.  In your `.env` file, add your Firebase Project ID as `FIREBASE_PROJECT_ID`. You can find this in the **Project settings** > **General** tab.

### c. Gemini (Optional)

If you plan to use the Gemini-powered features:

1.  Go to [Google AI Studio](https://aistudio.google.com/).
2.  Click **"Get API key"**.
3.  Copy the generated key and add it to your `.env` file as `GEMINI_API_KEY`.

## 4. `.env` Configuration

Your final `backend/.env` file should look like this:

```
# Supabase
SUPABASE_URL=your_supabase_project_url
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_secret

# Firebase
FIREBASE_PROJECT_ID=your_firebase_project_id

# Gemini (Optional)
GEMINI_API_KEY=your_gemini_api_key
```

**Key Lesson:** The application's configuration (`config.py`) is strict. It specifically requires the Supabase secret key to be named `SUPABASE_SERVICE_ROLE_KEY`. Using the older name `SUPABASE_KEY` will cause a validation error.

## 5. Nix Environment & Script Logic

The backend relies on a specific development environment managed by Nix to ensure consistency. The `backend/start.sh` script is the heart of the setup process and is designed to handle the complexities of this environment.

*   **`nix-shell` is Ephemeral:** The `nix-shell` environment is temporary and only exists for the command it runs. You must prefix any command that interacts with the backend with `nix-shell --run`.
*   **Self-Contained Script Logic:** The `start.sh` script is now robust. If you run it and the Python virtual environment (`venv`) doesn't exist, the script will automatically:
    1.  Create the `venv` for you.
    2.  Activate it.
    3.  Install all the necessary dependencies from `requirements.txt`.
*   **Idempotent:** You can run the script multiple times without issues. If the environment is already set up, it will simply activate it and start the server.

## 6. Backend Quick Start: The One Command to Rule Them All

To start the backend, navigate to the project's **root directory** in your terminal and run the following single command:

```bash
nix-shell --run "bash backend/start.sh"
```

This command correctly handles the Nix environment and executes the robust startup script, which will then handle the virtual environment and dependencies.

## 7. Frontend Quick Start

The frontend is a Next.js application located in the `web/` directory.

To start the frontend development server, run the following command from the project's **root directory**:

```bash
cd web && npm install && npm audit fix && npm run dev
```

This will:
1.  Navigate into the `web` directory.
2.  Install all the required Node.js packages.
3.  Fix any security vulnerabilities.
4.  Start the Next.js development server on `http://localhost:9002`.

**Note on Port Conflicts:** If you see an error that port 9002 is already in use, you can kill the existing process by running `kill $(lsof -t -i:9002)`.

The frontend is configured to work with the backend running on `http://localhost:8000`. Ensure the backend is running before starting the frontend.

## 8. Diagnostic Scripts

The `scripts/` directory contains several helpful diagnostic tools:

*   `debug_backend_sync.py`: This script sends a test user sync request to the backend. This is useful for ensuring the backend is running and the user sync endpoint is working correctly.
*   `debug_stock.py`: This script tests the `yfinance` library by fetching data for the ticker "HRL". This is useful for debugging issues with fetching stock data.
*   `diagnostic.sh`: This script runs a comprehensive set of diagnostics on your development environment, including memory usage, disk space, and OOM killer events. This is a valuable tool for debugging performance issues.

## 9. Generating a Test Authentication Token

For development and testing purposes, you may need to generate a valid authentication token for a specific user ID (UID) without going through a full login flow. The `generate_test_token.py` script serves this purpose.

**Important:** This script uses the project's service account credentials to generate a **Firebase Custom Token**. This is a server-generated token used for testing or to sign in a client SDK; it is different from the ID token a user gets after logging in.

### Prerequisites

Before running the script, ensure you have completed the setup in this guide:
1.  The `backend/google_credentials.json` file must be present.
2.  The `backend/.env` file must exist and contain the correct `FIREBASE_PROJECT_ID`.

### Usage

To generate a token, run the following command from the project's **root directory**:

```bash
nix-shell --run "python scripts/generate_test_token.py YOUR_TEST_USER_UID"
```

Replace `YOUR_TEST_USER_UID` with the actual UID of the user you wish to impersonate (e.g., a test user's email or a unique ID from your Firebase Authentication user list).

If successful, the script will print the generated custom token to the console.
