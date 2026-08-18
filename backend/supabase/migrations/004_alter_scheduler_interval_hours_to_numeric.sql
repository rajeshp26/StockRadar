-- Alter scheduler_state.interval_hours from INT to NUMERIC to support
-- fractional hour intervals (e.g. 0.5 = 30 min, 0.0167 = 1 min).
-- The planner.register() API already accepts float values for interval_hours
-- and interval_minutes; this migration aligns the DB schema with the code.

ALTER TABLE scheduler_state
    ALTER COLUMN interval_hours TYPE NUMERIC USING interval_hours::NUMERIC;
