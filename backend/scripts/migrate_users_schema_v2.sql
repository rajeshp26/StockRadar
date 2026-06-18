-- Migration: v2 — Add profile fields + UNIQUE constraints to `users` table
--
-- Phase 1 of SignUp redesign adds:
--   1. first_name, last_name, avatar_url columns
--   2. UNIQUE constraint on auth_id (prevents duplicate auth-linked rows)
--   3. UNIQUE constraint on email (prevents duplicate email rows, race-condition safety)
--   4. Remove the now-unnecessary `username` default (was always '')

-- Step 1: Add new columns (nullable to not break existing rows)
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS first_name TEXT,
  ADD COLUMN IF NOT EXISTS last_name  TEXT,
  ADD COLUMN IF NOT EXISTS avatar_url TEXT;

-- Step 2: Add UNIQUE constraints.
-- These are what actually prevent duplicate users at the database level.
-- The old app-level check in POST /users/sync (check then insert) had a
-- race-condition window. The UNIQUE constraint closes it.
-- Supabase's .upsert() with on_conflict can then be used for atomic upserts.
ALTER TABLE users
  ADD CONSTRAINT uq_users_auth_id UNIQUE (auth_id);

ALTER TABLE users
  ADD CONSTRAINT uq_users_email UNIQUE (email);

-- Step 3: Verify the new schema
-- Expected columns: user_id (PK), auth_id (UNIQUE), email (UNIQUE),
--   username, first_name, last_name, avatar_url, last_signed_in, preferred_currency
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'users'
ORDER BY ordinal_position;
