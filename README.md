# Firebase Studio

This is a NextJS starter in Firebase Studio.

To get started, take a look at src/app/page.tsx.

## Running the Backend (Python Server)

The application's backend is a separate Python server that the Next.js frontend communicates with. You must run this server manually for the application to be fully functional.

### First-Time Setup

If you haven't set up the backend before, run this command in your terminal once:

```bash
python -m venv .venv && source .venv/bin/activate && pip install -r backend/requirements.txt
```

### Running the Server

To start the backend server, run the following command in your terminal. This will keep the server running and automatically reload it when you make changes to the backend code.

```bash
source .venv/bin/activate && cd backend && uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

You will need to keep this terminal window open. You should see output indicating the server has started, like: `INFO: Uvicorn running on http://0.0.0.0:8000`.
