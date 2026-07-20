-- Migration 003: Add processed column to splits table
-- Splits already handled by price-only logic are marked processed=TRUE.
-- New splits get processed=FALSE until the event producer processes them.

ALTER TABLE splits ADD COLUMN IF NOT EXISTS processed BOOLEAN DEFAULT FALSE;
UPDATE splits SET processed = TRUE WHERE processed = FALSE;
