#!/bin/bash

# ============================================
# StockerPro Backend Startup (Development Mode)
# Handles: Nix environment, .env injection, virtualenv
# ============================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${GREEN}🚀 StockerPro Backend Startup${NC}\n"

# ============================================
# STEP 1: Verify Prerequisites (.env, config.py)
# ============================================

echo -e "${YELLOW}🔍 Step 1: Prerequisites Check${NC}"

if [ ! -f ".env" ]; then
    echo -e "${RED}❌ .env file not found at $SCRIPT_DIR/.env${NC}"
    exit 1
fi

if [ ! -f "config.py" ]; then
    echo -e "${RED}❌ config.py not found${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Core prerequisites OK${NC}\n"

# ============================================
# STEP 2: Setup Virtual Environment & Dependencies
# ============================================

echo -e "${YELLOW}🐍 Step 2: Setting up Python virtual environment${NC}"

if [ ! -d "venv" ]; then
    echo -e "${YELLOW}   Virtual environment not found. Creating...${NC}"
    # Use the python from the Nix shell
    python3 -m venv venv
    echo -e "${GREEN}   ✅ venv created.${NC}"
else
    echo -e "${GREEN}   ✅ venv found.${NC}"
fi

# Activate the virtual environment
source venv/bin/activate
echo -e "${GREEN}   ✅ venv activated: $VIRTUAL_ENV${NC}"

# Install/update dependencies
echo -e "${YELLOW}   Installing dependencies from requirements.txt...${NC}"
pip install -r requirements.txt
echo -e "${GREEN}   ✅ Dependencies installed.${NC}\n"

# ============================================
# STEP 3: Load .env Variables into Shell
# ============================================

echo -e "${YELLOW}🔑 Step 3: Loading environment variables${NC}"

# Safe method: read .env line by line, skip comments and empty lines
while IFS='=' read -r key value || [ -n "$key" ]; do
    # Skip comments and empty lines
    [[ "$key" =~ ^[[:space:]]*# ]] && continue
    [[ -z "$key" ]] && continue
    
    # Trim whitespace
    key=$(echo "$key" | xargs)
    value=$(echo "$value" | xargs)
    
    # Export the variable
    export "$key=$value"
done < .env

echo -e "${GREEN}✅ Environment variables loaded${NC}"
echo -e "   - SUPABASE_URL: ${SUPABASE_URL:0:20}..."
echo -e "   - FIREBASE_PROJECT_ID: $FIREBASE_PROJECT_ID"
[ -n "$GEMINI_API_KEY" ] && echo -e "   - GEMINI_API_KEY: configured"
echo ""


# ============================================
# STEP 4: Cleanup Old Processes
# ============================================

echo -e "${YELLOW}🧹 Step 4: Cleanup${NC}"

PID_FILE="$SCRIPT_DIR/backend.pid"
LOG_DIR="$SCRIPT_DIR/logs"

mkdir -p "$LOG_DIR"

if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo -e "${YELLOW}   Stopping old process (PID: $OLD_PID)...${NC}"
        kill -TERM "$OLD_PID" 2>/dev/null || true
        sleep 2
        kill -9 "$OLD_PID" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
fi

echo -e "${GREEN}✅ Cleanup complete${NC}\n"

# ============================================
# STEP 5: Verify Configuration
# ============================================

echo -e "${YELLOW}⚙️  Step 5: Configuration validation${NC}"

# Quick test: import config to validate it loads
if python3 -c "from config import settings; print(f'Project ID: {settings.FIREBASE_PROJECT_ID}')" 2>&1; then
    echo -e "${GREEN}✅ Configuration valid${NC}\n"
else
    echo -e "${RED}❌ Configuration validation failed${NC}"
    exit 1
fi

# ============================================
# STEP 6: Start FastAPI Server (Foreground)
# ============================================

echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}🎯 Starting FastAPI Server in foreground...${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}📍 Host: 0.0.0.0${NC}"
echo -e "${YELLOW}📍 Port: 8001${NC}"
echo -e "${YELLOW}📍 API Docs: http://localhost:8001/docs${NC}"
echo -e "${YELLOW}Press Ctrl+C to stop${NC}\n"

# Set PYTHONPATH to ensure imports work correctly
export PYTHONPATH="${SCRIPT_DIR}:${SCRIPT_DIR}/..${PYTHONPATH:+:$PYTHONPATH}"

# Launch in the foreground for development with auto-reloading.
python -m uvicorn main:app \
    --host 0.0.0.0 \
    --port 8001 \
    --reload \
    --log-level debug
