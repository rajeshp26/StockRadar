#!/bin/bash

# This script sets up and runs the Python backend server using the new architecture.

# Exit immediately if a command exits with a non-zero status.
set -e

# Use the virtual environment in the backend folder
VENV_DIR="backend/.venv"

echo ">>> Setting up Python virtual environment in $VENV_DIR..."
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    echo "Virtual environment created."
fi

# Activate the virtual environment
source "$VENV_DIR/bin/activate"

echo ">>> Installing dependencies..."
pip install -r backend/requirements.txt
pip install pytest httpx # Testing dependencies

# Set PYTHONPATH so absolute imports work
export PYTHONPATH=$PYTHONPATH:$(pwd)/backend

echo ">>> Starting Python backend server on http://0.0.0.0:8001"
# Match the port used in src/app/api/proxy/[...path]/route.ts
uvicorn main:app --app-dir backend --host 0.0.0.0 --port 8001 --reload
