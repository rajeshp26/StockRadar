-- Migration: Create group_metric_stats and aggregation_state tables
-- Run:  psql -h <host> -U <user> -d <db> -f migration_group_metric_stats.sql

-- ============================================================================
-- Table: group_metric_stats
-- Stores percentile-based distribution stats for valuation metrics per group
-- (sector/industry). Used by the gauge to show sector-relative valuation.
-- ============================================================================
create table if not exists public.group_metric_stats (
  id serial not null,
  group_type text not null,          -- 'sector' or 'industry'
  group_key text not null,           -- sector name, industry name
  metric_id text not null,           -- 'pe', 'ev_ebitda', 'pfcf'
  p05 numeric(10, 2) null,
  p25 numeric(10, 2) null,
  p50 numeric(10, 2) null,
  p75 numeric(10, 2) null,
  p95 numeric(10, 2) null,
  mean numeric(10, 2) null,
  sample_size integer not null default 0,
  computed_at timestamp with time zone null default CURRENT_TIMESTAMP,
  constraint group_metric_stats_pkey primary key (id),
  constraint uq_group_metric unique (group_type, group_key, metric_id)
);

create index if not exists idx_group_metric_stats_lookup
  on public.group_metric_stats (group_type, group_key, metric_id);

-- ============================================================================
-- Table: aggregation_state
-- Distributed lock + watermark for the aggregation scheduler.
-- Prevents concurrent runs across replicas.
-- ============================================================================
create table if not exists public.aggregation_state (
  aggregation_id text not null default 'sector_metric_agg',
  is_running boolean not null default false,
  last_started_at timestamp with time zone null,
  last_completed_at timestamp with time zone null,
  lock_owner text null,
  lock_expires_at timestamp with time zone null,
  constraint aggregation_state_pkey primary key (aggregation_id)
);

-- Insert initial state row (idempotent)
insert into public.aggregation_state (aggregation_id, is_running, last_completed_at)
values ('sector_metric_agg', false, null)
on conflict (aggregation_id) do nothing;
