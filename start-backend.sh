#!/bin/bash

# This script sets up and runs the Python backend server.

# Exit immediately if a command exits with a non-zero status.
set -e

echo ">>> Setting up Python virtual environment..."
# Create the virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "Virtual environment created."
fi

# Activate the virtual environment
source .venv/bin/activate

echo ">>> Installing dependencies from backend/requirements.txt..."
pip install -r backend/requirements.txt

echo ">>> Starting Python backend server on http://0.0.0.0:8000"
echo ">>> (Running in the background with --reload)"

# Change to the backend directory and start the Uvicorn server in the background
cd backend && uvicorn main:app --host 0.0.0.0 --port 8000 --reload &

echo ">>> Backend server started successfully."
echo ">>> You can now work on the frontend. The backend will run in the background."
