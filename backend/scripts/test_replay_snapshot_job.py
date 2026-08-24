"""Quick test: run the daily snapshot job in event-replay mode to verify it works with real data."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings

print(f"ENABLE_EVENT_REPLAY_SNAPSHOTS={settings.ENABLE_EVENT_REPLAY_SNAPSHOTS}")
print(f"EVENT_REPLAY_COMPARISON_MODE={settings.EVENT_REPLAY_COMPARISON_MODE}")

from application.jobs.portfolio_snapshot_job import compute_daily_snapshots

asyncio.run(compute_daily_snapshots())
print("Done.")
