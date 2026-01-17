#!/bin/bash

set -e  # Exit on error

# Get the project root directory
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "🧹 Cleaning up ports..."
lsof -ti :3000 | xargs kill -9 2>/dev/null || true
lsof -ti :8001 | xargs kill -9 2>/dev/null || true
lsof -ti :9000 | xargs kill -9 2>/dev/null || true

echo "⏳ Waiting for ports to be released..."
sleep 2

echo "🚀 Starting backend on port 8001..."
# Run backend inside nix-shell from the project root
# The shellHook in shell.nix will set up the environment correctly
(cd "$PROJECT_ROOT" && nix-shell --run "cd backend && bash start.sh") &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

# Give backend time to start and initialize
echo "⏳ Waiting for backend to initialize..."
sleep 4

echo "🚀 Starting frontend on port 3000..."
# Run frontend from the web directory
cd "$PROJECT_ROOT/web"
PORT=3000 npm run dev

# Cleanup on exit
trap "echo '🛑 Shutting down...'; kill $BACKEND_PID 2>/dev/null || true" EXIT
