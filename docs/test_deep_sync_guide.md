# Functional Testing Guide: Deep Sync

This guide provides the correct steps to run the `test_deep_sync.py` functional test independently of the frontend.

## Prerequisites
1.  **Environment:** Ensure the Python virtual environment is created and all dependencies are installed.
2.  **Dependencies:** Ensure `httpx` is installed in your venv (`pip install httpx`).
3.  **Database:** Ensure your Supabase project is active and accessible.
4.  **Port Availability:** Ensure port 8000 is not being used by another process.
    *   *Check:* `lsof -i :8000`
    *   *Kill if necessary:* `fuser -k 8000/tcp`
5.  **Server Health:** The backend FastAPI server must be running and responding to health checks.

## Correct Steps to Run the Test

### 1. Start the Backend Server (Terminal 1)
```bash
source .venv/bin/activate
cd backend
export PYTHONPATH=$PYTHONPATH:$(pwd)
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### 2. Verify Server is Up (Optional but Recommended)
```bash
curl -I http://127.0.0.1:8000/docs
```

### 3. Run the Test Script (Terminal 2)
```bash
source .venv/bin/activate
# IMPORTANT: PYTHONPATH must point to the 'backend' folder
export PYTHONPATH=/home/user/studio/backend
# Execute the script using the absolute path to the venv python
/home/user/studio/.venv/bin/python /home/user/studio/backend/tests/test_deep_sync.py
```

## "Don'ts" & Failure Log (Lessons Learned)

### 1. Don't run the test without setting `PYTHONPATH`
*   **Failure:** `ModuleNotFoundError: No module named 'database'`
*   **Fix:** Export the `backend` directory to your `PYTHONPATH`.

### 2. Don't run the server and test in the same background command string
*   **Failure:** Race conditions.
*   **Fix:** Use two separate terminal sessions.

### 3. Don't assume all dependencies are in `requirements.txt`
*   **Failure:** `ModuleNotFoundError: No module named 'httpx'`
*   **Fix:** Manually install `httpx`.

### 4. Don't use relative paths in background tasks
*   **Failure:** `Errno 2: No such file or directory`
*   **Fix:** Use absolute paths like `/home/user/studio/backend/...`.

### 5. Don't ignore "Address already in use" errors
*   **Failure:** `[Errno 98] error while attempting to bind on address`
*   **Fix:** Clear the port using `fuser -k 8000/tcp`.

### 6. Don't run scripts from within subdirectories if they have root-level imports
*   **Failure:** `ModuleNotFoundError: No module named 'database'`
*   **Fix:** Execute from the project root and point `PYTHONPATH` to the `backend` folder.

### 7. Don't use the system Python for testing
*   **Failure:** Imports working in one shell but failing in another.
*   **Fix:** Always use the absolute path to the virtual environment's python: `/home/user/studio/.venv/bin/python`.

### 8. Don't use `.single()` on queries that might return zero rows
*   **Failure:** `PGRST116: The result contains 0 rows`
*   **Why:** PostgREST throws an error if `.single()` is called on an empty result set.
*   **Fix:** Use `.execute()` and check if `data` exists.

### 9. Don't chain `.select()` after `.upsert()` in the Python Supabase SDK
*   **Failure:** `AttributeError: 'SyncQueryRequestBuilder' object has no attribute 'select'`
*   **Why:** The Python SDK handles upserts differently than the JS SDK; data is returned by default in the `.data` attribute.
*   **Fix:** Use `.execute()` immediately after `.upsert()`.

### 10. (Pro-Tip) Use internal Path Injection in Test Scripts
*   **Tip:** Adding `sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))` to the top of your test script makes it more resilient to different execution environments by programmatically adding the backend root to the search path.
