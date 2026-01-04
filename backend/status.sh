#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/backend.pid"
LOG_FILE="$SCRIPT_DIR/logs/backend.log"

echo "StockerPro Backend Status"
echo "════════════════════════════════════════"

if [ ! -f "$PID_FILE" ]; then
    echo "Status: ❌ NOT RUNNING (no PID file)"
    exit 1
fi

BACKEND_PID=$(cat "$PID_FILE")

if ! ps -p "$BACKEND_PID" > /dev/null 2>&1; then
    echo "Status: ❌ NOT RUNNING (stale PID)"
    rm "$PID_FILE"
    exit 1
fi

echo "Status: ✅ RUNNING"
echo "PID: $BACKEND_PID"
echo ""

# Get process info
echo "Process Info:"
echo "─────────────────────────────────────────"
ps -p "$BACKEND_PID" -o pid,ppid,user,%cpu,%mem,etime,cmd
echo ""

# Check if port is listening
echo "Network:"
echo "─────────────────────────────────────────"
if curl -s http://localhost:8001/health > /dev/null 2>&1; then
    echo "✅ Listening on port 8001"
else
    echo "⚠️  Port 8001 not responding (still starting?)"
fi
echo ""

# API Health
echo "API Health Check:"
echo "─────────────────────────────────────────"
if curl -s http://localhost:8001/health > /dev/null 2>&1; then
    curl -s http://localhost:8001/health
else
    echo "❌ API is not responding"
fi
echo ""

# Show last log lines
echo "Recent Logs (last 10 lines):"
echo "─────────────────────────────────────────"
if [ -f "$LOG_FILE" ]; then
    tail -n 10 "$LOG_FILE"
else
    echo "No log file found"
fi
