-- Migration: Add health score columns to financial_ratios
--
-- Adds columns required by the Fundamentals tab Health section:
--   piotroski_score  — Piotroski F-Score (0-9), 9-point scale
--   altman_z_score   — Altman Z-Score, 5-factor bankruptcy prediction
--
-- Both will be populated by derived_financial_metrics_job.py
-- in its new quarterly computation path.
--

ALTER TABLE financial_ratios
  ADD COLUMN IF NOT EXISTS piotroski_score DOUBLE PRECISION;

ALTER TABLE financial_ratios
  ADD COLUMN IF NOT EXISTS altman_z_score DOUBLE PRECISION;

COMMENT ON COLUMN financial_ratios.piotroski_score IS 'Piotroski F-Score (0-9): profitability 4pts, leverage/liquidity 3pts, efficiency 2pts';
COMMENT ON COLUMN financial_ratios.altman_z_score IS 'Altman Z-Score: 1.2A+1.4B+3.3C+0.6D+1.0E (≥3 safe, <1.8 distress)';
