/* ============================================================
   Migration: Create event_sequence + projection_checkpoint tables
   
   Run this in Supabase SQL Editor (Dashboard → SQL Editor)
   ============================================================ */

-- 1. Event sequence table for projection handler polling
CREATE TABLE IF NOT EXISTS public.event_sequence (
  seq_id         BIGSERIAL PRIMARY KEY,
  event_id       UUID NOT NULL REFERENCES portfolio_events(id),
  aggregate_id   TEXT NOT NULL,
  version        INTEGER NOT NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_event_sequence_created ON event_sequence(created_at);
CREATE INDEX IF NOT EXISTS idx_event_sequence_aggregate ON event_sequence(aggregate_id, seq_id);

-- 2. Backfill from existing events
INSERT INTO event_sequence (event_id, aggregate_id, version, created_at)
SELECT id, aggregate_id, event_version, created_at
FROM portfolio_events
ORDER BY created_at
ON CONFLICT DO NOTHING;

-- 3. Trigger to auto-populate on new events
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

-- 4. Checkpoint table for resumable polling
CREATE TABLE IF NOT EXISTS public.projection_checkpoint (
  id            INTEGER PRIMARY KEY DEFAULT 1,
  last_seq_id   BIGINT NOT NULL DEFAULT 0,
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO projection_checkpoint (id, last_seq_id)
VALUES (1, (SELECT COALESCE(MAX(seq_id), 0) FROM event_sequence))
ON CONFLICT (id) DO NOTHING;

-- Verify
SELECT 'event_sequence' as tbl, COUNT(*) FROM event_sequence
UNION ALL
SELECT 'projection_checkpoint', COUNT(*) FROM projection_checkpoint;