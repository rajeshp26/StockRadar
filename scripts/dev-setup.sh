#!/bin/bash

set -e  # Exit on error

# Get the project root directory
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "Cleaning up ports..."
lsof -ti :3000 | xargs kill -9 2>/dev/null || true
lsof -ti :8001 | xargs kill -9 2>/dev/null || true

echo "Waiting for ports to be released..."
sleep 2

# Start Supabase if not running
if ! supabase status 2>/dev/null | grep -q "supabase.*running"; then
    echo "Starting Supabase..."
    supabase start
else
    echo "Supabase already running"
fi

echo "Starting backend on port 8001..."
(cd "$PROJECT_ROOT/backend" && python -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload) &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

# Give backend time to start and initialize
echo "Waiting for backend to initialize..."
sleep 4

echo "Starting frontend on port 3000..."
cd "$PROJECT_ROOT/web"
PORT=3000 npm run dev

# Cleanup on exit
trap "echo 'Shutting down...'; kill $BACKEND_PID 2>/dev/null || true" EXIT
