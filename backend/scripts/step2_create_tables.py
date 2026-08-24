"""Step 2: Create event_sequence and projection_checkpoint tables via Supabase management API."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging

import httpx

from config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stderr)
log = logging.getLogger("step2")

SUPABASE_URL = settings.SUPABASE_URL
SERVICE_KEY = settings.SUPABASE_SERVICE_ROLE_KEY

from urllib.parse import urlparse

parsed = urlparse(SUPABASE_URL)
project_ref = parsed.netloc.split(".")[0]
log.info(f"Project ref: {project_ref}")

MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS public.event_sequence (
  seq_id         BIGSERIAL PRIMARY KEY,
  event_id       UUID NOT NULL REFERENCES portfolio_events(id),
  aggregate_id   TEXT NOT NULL,
  version        INTEGER NOT NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_event_sequence_created ON event_sequence(created_at);
CREATE INDEX IF NOT EXISTS idx_event_sequence_aggregate ON event_sequence(aggregate_id, seq_id);

INSERT INTO event_sequence (event_id, aggregate_id, version, created_at)
SELECT id, aggregate_id, event_version, created_at
FROM portfolio_events
ORDER BY created_at
ON CONFLICT DO NOTHING;

CREATE OR REPLACE FUNCTION event_insert_sequence_trigger()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO event_sequence (event_id, aggregate_id, version, created_at)
  VALUES (NEW.id, NEW.aggregate_id, NEW.event_version, NEW.created_at);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_portfolio_events_after_insert ON portfolio_events;
CREATE TRIGGER trg_portfolio_events_after_insert
AFTER INSERT ON portfolio_events
FOR EACH ROW EXECUTE FUNCTION event_insert_sequence_trigger();

CREATE TABLE IF NOT EXISTS public.projection_checkpoint (
  id            INTEGER PRIMARY KEY DEFAULT 1,
  last_seq_id   BIGINT NOT NULL DEFAULT 0,
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO projection_checkpoint (id, last_seq_id)
VALUES (1, (SELECT COALESCE(MAX(seq_id), 0) FROM event_sequence))
ON CONFLICT (id) DO NOTHING;
"""

# Try Supabase management API (requires service_role key)
headers = {
    "apikey": SERVICE_KEY,
    "Authorization": "Bearer " + SERVICE_KEY,
    "Content-Type": "application/json",
}

# Method 1: Direct Postgres connection via Supabase SQL endpoint
sql_url = f"https://{project_ref}.supabase.co/sql"
log.info(f"SQL endpoint: {sql_url}")

try:
    r = httpx.post(
        sql_url,
        headers=headers,
        json={"query": MIGRATION_SQL},
        timeout=30,
    )
    log.info(f"SQL API status: {r.status_code}")
    log.info(f"Response: {r.text[:300]}")
except Exception as e:
    log.warning(f"SQL API failed: {e}")

# Method 2: Try the management API with different endpoint
management_url = f"https://api.supabase.com/v1/projects/{project_ref}/sql/query"
log.info(f"Management API URL: {management_url}")

try:
    r = httpx.post(
        management_url,
        headers=headers,
        json={"query": MIGRATION_SQL},
        timeout=30,
    )
    log.info(f"Management API status: {r.status_code}")
    log.info(f"Response: {r.text[:500]}")
except Exception as e:
    log.warning(f"Management API failed: {e}")

# Method 3: Directly via supabase REST API (if we can use the pg-dump endpoint)
direct_url = f"{SUPABASE_URL}/rest/v1/"
try:
    # Some Supabase instances accept raw SQL via the pg API
    r = httpx.post(
        f"https://{project_ref}.supabase.co/auth/v1/admin/execute",
        headers=headers,
        json={"query": MIGRATION_SQL},
        timeout=30,
    )
    log.info(f"Admin execute status: {r.status_code}")
    log.info(f"Response: {r.text[:300]}")
except Exception as e:
    log.warning(f"Admin execute failed: {e}")

# Verify
log.info("Verifying tables...")
from database import supabase

for tbl in ["event_sequence", "projection_checkpoint"]:
    try:
        q = supabase.table(tbl).select("*", count="exact").limit(1).execute()
        log.info(f"  {tbl}: {q.count} rows - SUCCESS")
    except Exception as e:
        log.error(f"  {tbl}: FAILED - {e}")
