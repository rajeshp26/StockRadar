-- 001_create_exchange_rates_table.sql
-- Migration: Create exchange_rates table for FX currency conversion.
-- Part of the FX Currency Conversion feature (design doc: docs/FX_CURRENCY_CONVERSION_DESIGN.md)

CREATE TABLE IF NOT EXISTS exchange_rates (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    base_currency   CHAR(3) NOT NULL,
    target_currency CHAR(3) NOT NULL,
    rate            NUMERIC(18, 8) NOT NULL,
    rate_date       DATE NOT NULL,
    source          TEXT NOT NULL DEFAULT 'yfinance',
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT unique_rate_per_day UNIQUE (base_currency, target_currency, rate_date),
    CONSTRAINT rate_positive CHECK (rate > 0),
    CONSTRAINT currencies_len CHECK (
        length(base_currency) = 3 AND length(target_currency) = 3
    ),
    CONSTRAINT no_same_currency CHECK (base_currency <> target_currency),
    CONSTRAINT currencies_uppercase CHECK (
        base_currency = upper(base_currency)
        AND target_currency = upper(target_currency)
    )
);

CREATE INDEX IF NOT EXISTS idx_exchange_rates_lookup
    ON exchange_rates (base_currency, target_currency, rate_date DESC);

COMMENT ON TABLE exchange_rates IS
    'Daily exchange rates for portfolio currency conversion.';
COMMENT ON COLUMN exchange_rates.base_currency IS
    'Source currency (ISO 4217), e.g. USD';
COMMENT ON COLUMN exchange_rates.target_currency IS
    'Target currency (ISO 4217), e.g. CAD';
COMMENT ON COLUMN exchange_rates.rate IS
    'Conversion rate: 1 base_currency = rate target_currency';

-- RLS: service_role writes, authenticated reads
ALTER TABLE exchange_rates ENABLE ROW LEVEL SECURITY;

CREATE POLICY "authenticated can read exchange_rates"
    ON exchange_rates
    FOR SELECT
    USING (auth.role() IN ('authenticated', 'service_role'));

CREATE POLICY "service_role can insert exchange_rates"
    ON exchange_rates
    FOR INSERT
    WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "service_role can update exchange_rates"
    ON exchange_rates
    FOR UPDATE
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "service_role can delete exchange_rates"
    ON exchange_rates
    FOR DELETE
    USING (auth.role() = 'service_role');
