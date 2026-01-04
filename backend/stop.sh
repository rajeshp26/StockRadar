#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/backend.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "❌ Backend is not running (no PID file)"
    exit 1
fi

BACKEND_PID=$(cat "$PID_FILE")

if ! ps -p "$BACKEND_PID" > /dev/null 2>&1; then
    echo "❌ Backend is not running (stale PID file)"
    rm "$PID_FILE"
    exit 1
fi

echo "🛑 Stopping StockerPro Backend (PID: $BACKEND_PID)..."
kill "$BACKEND_PID"

# Wait for graceful shutdown
for i in {1..10}; do
    if ! ps -p "$BACKEND_PID" > /dev/null 2>&1; then
        echo "✅ Backend stopped successfully"
        rm "$PID_FILE"
        exit 0
    fi
    sleep 1
done

# Force kill if still running
echo "⚠️  Backend didn't stop gracefully, forcing..."
kill -9 "$BACKEND_PID" 2>/dev/null || true
rm "$PID_FILE"
echo "✅ Backend stopped (forced)"
