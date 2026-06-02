#!/bin/bash
# Run the e2e seed data script from within WSL
cd "$(dirname "$0")/.."
source .venv/bin/activate
python scripts/seed_e2e_data.py
