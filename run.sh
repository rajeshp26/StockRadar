#!/bin/bash

# ===================================================================
# Universal Runner for StockerPro
# -------------------------------------------------------------------
# This script provides a consistent entry point for running any 
# command within the project's Nix-based Python environment.
#
# It ensures that the correct virtual environment is activated and
# all dependencies are installed before executing the command.
#
# Usage:
#   ./run.sh "your-command-here"
#
# Example:
#   ./run.sh "pytest"
#   ./run.sh "python scripts/generate_test_token.py email@example.com psswrd"
# ===================================================================

set -e

# Navigate to the script's directory to ensure paths are correct
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if a command was provided
if [ -z "$1" ]; then
    echo "Usage: ./run.sh \"<command>\""_unstable
    exit 1
fi

COMMAND_TO_RUN=$1

# Execute the command inside the nix-shell
# This ensures we have the correct system-level dependencies (like python3)
nix-shell --run "
    # Activate the Python virtual environment
    source backend/venv/bin/activate
    
    # Ensure all dependencies are up-to-date
    pip install -r backend/requirements.txt > /dev/null
    
    # Execute the provided command
    echo 'Running command: $COMMAND_TO_RUN'
    $COMMAND_TO_RUN
"
