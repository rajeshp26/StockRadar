#!/bin/bash

# StockerPro Unified Mobile Manager
# Usage: ./manage.sh [run|stop|build] [web|android|ios]

COMMAND=$1
VARIANT=$2
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

# 1. Load Environment Variables
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ ERROR: .env file missing in mobile directory."
    exit 1
fi

source "$ENV_FILE"

# 2. Command: STOP
if [ "$COMMAND" == "stop" ]; then
    echo ">>> Stopping all Mobile services..."
    # Kill common web port
    lsof -ti:9003 | xargs kill -9 2>/dev/null || true
    echo "✅ Cleaned up."
    exit 0
fi

# 3. Command: RUN
if [ "$COMMAND" == "run" ]; then
    cd "$SCRIPT_DIR"

    # Define build-time variables
    DART_DEFINES=(
        "--dart-define=FIREBASE_API_KEY=$FIREBASE_API_KEY"
        "--dart-define=FIREBASE_PROJECT_ID=$FIREBASE_PROJECT_ID"
        "--dart-define=FIREBASE_AUTH_DOMAIN=$FIREBASE_AUTH_DOMAIN"
        "--dart-define=FIREBASE_STORAGE_BUCKET=$FIREBASE_STORAGE_BUCKET"
        "--dart-define=FIREBASE_MESSAGING_SENDER_ID=$FIREBASE_MESSAGING_SENDER_ID"
        "--dart-define=FIREBASE_APP_ID=$FIREBASE_APP_ID"
    )

    if [ "$VARIANT" == "web" ]; then
        echo ">>> Running Flutter Web on Port 9003..."
        lsof -ti:9003 | xargs kill -9 2>/dev/null || true
        flutter run -d web-server --web-port 9003 --web-hostname 0.0.0.0 "${DART_DEFINES[@]}"
    
    elif [ "$VARIANT" == "android" ]; then
        if [ ! -f "android/app/google-services.json" ]; then
            echo "⚠️  WARNING: android/app/google-services.json missing."
        fi
        flutter run "${DART_DEFINES[@]}"
    
    else
        echo "Usage: ./manage.sh run [web|android]"
    fi
fi
