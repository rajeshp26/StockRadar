#!/bin/bash
cd /mnt/c/Project/StockerPro/StockerPro/backend
exec /home/rajesh/venv_stockerpro/bin/uvicorn main:app --host 0.0.0.0 --port 8001
