-- Moat Analysis Schema
-- Separates moat data from valuation_runs (different cache lifecycle).
-- moat_analysis: composite scores per company (24h quant cache)
-- moat_keyword_evidence: keyword match snippets from EDGAR 10-K (indefinite cache)
-- moat_ai_narratives: cached AI output (regenerated on user demand)

CREATE TABLE IF NOT EXISTS moat_analysis (
    id            BIGSERIAL PRIMARY KEY,
    company_id    BIGINT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    symbol        TEXT NOT NULL,

    -- Stage 1: Quant Scores
    roic                    DOUBLE PRECISION,
    wacc                    DOUBLE PRECISION,
    roic_minus_wacc         DOUBLE PRECISION,
    gross_margin_pct        DOUBLE PRECISION,
    operating_margin_pct    DOUBLE PRECISION,
    net_margin_pct          DOUBLE PRECISION,
    roic_5y_avg             DOUBLE PRECISION,
    roic_5y_std             DOUBLE PRECISION,
    roic_stability_score    DOUBLE PRECISION,
    asset_turnover          DOUBLE PRECISION,
    capital_efficiency_score DOUBLE PRECISION,
    moat_score              DOUBLE PRECISION,
    moat_category           TEXT CHECK (moat_category IN ('Wide', 'Narrow', 'None', 'Unknown')),

    -- Stage 2 flags
    text_analysis_available BOOLEAN NOT NULL DEFAULT FALSE,
    keyword_matches_count   INTEGER NOT NULL DEFAULT 0,

    -- Stage 3: Sector-adjusted
    sector                  TEXT,
    sector_adjustment       DOUBLE PRECISION DEFAULT 0.0,

    -- Stage 4: AI narrative flag
    ai_narrative_available  BOOLEAN NOT NULL DEFAULT FALSE,

    -- Metadata
    fiscal_years_used       INTEGER NOT NULL DEFAULT 0,
    data_sources            TEXT NOT NULL DEFAULT 'database',
    quarters_used           INTEGER NOT NULL DEFAULT 0,
    fallbacks_used          BOOLEAN NOT NULL DEFAULT FALSE,
    computed_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Unique constraint: one active row per company
    CONSTRAINT uq_moat_analysis_company UNIQUE (company_id)
);

CREATE INDEX IF NOT EXISTS idx_moat_analysis_symbol ON moat_analysis (symbol);
CREATE INDEX IF NOT EXISTS idx_moat_analysis_computed_at ON moat_analysis (computed_at DESC);

COMMENT ON TABLE moat_analysis IS 'Economic moat durability composite scores cached per company';
COMMENT ON COLUMN moat_analysis.roic_stability_score IS '0-100 score based on ROIC volatility over 5 years';
COMMENT ON COLUMN moat_analysis.capital_efficiency_score IS '0-100 score based on asset turnover and reinvestment quality';
COMMENT ON COLUMN moat_analysis.moat_score IS '0-100 composite score across all 4 stages';
COMMENT ON COLUMN moat_analysis.moat_category IS 'Wide (>=70), Narrow (40-69), None (<40), Unknown (insufficient data)';

-- Keyword evidence from EDGAR 10-K text analysis
CREATE TABLE IF NOT EXISTS moat_keyword_evidence (
    id              BIGSERIAL PRIMARY KEY,
    company_id      BIGINT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    symbol          TEXT NOT NULL,

    -- Filing metadata
    filing_type     TEXT NOT NULL DEFAULT '10-K',
    filing_date     DATE,
    accession_number TEXT,
    section         TEXT,   -- 'item_1_business', 'item_1a_risk_factors', 'item_7_mda', 'proxy_statement'

    -- Keyword match details
    keyword         TEXT NOT NULL,      -- e.g. 'patent', 'switching_cost'
    keyword_group   TEXT NOT NULL,      -- e.g. 'intangible_assets', 'switching_costs'
    snippet         TEXT,               -- surrounding text (~200 chars)
    relevance_score DOUBLE PRECISION DEFAULT 1.0,

    -- Metadata
    matched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_moat_keyword_evidence UNIQUE (company_id, filing_date, section, keyword, snippet)
);

CREATE INDEX IF NOT EXISTS idx_moat_evidence_company ON moat_keyword_evidence (company_id);
CREATE INDEX IF NOT EXISTS idx_moat_evidence_keyword_group ON moat_keyword_evidence (keyword_group);

COMMENT ON TABLE moat_keyword_evidence IS 'Keyword match evidence extracted from EDGAR filings for moat analysis';

-- Cached AI narratives for moat analysis
CREATE TABLE IF NOT EXISTS moat_ai_narratives (
    id              BIGSERIAL PRIMARY KEY,
    company_id      BIGINT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    symbol          TEXT NOT NULL,

    -- AI output
    model           TEXT NOT NULL DEFAULT 'openrouter/default',
    narrative       TEXT NOT NULL,
    summary         TEXT,

    -- What was used to generate
    quant_snapshot  JSONB,   -- scores used as context
    evidence_count  INTEGER NOT NULL DEFAULT 0,

    -- Metadata
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    generation_time_ms INTEGER,   -- how long the API call took

    CONSTRAINT uq_moat_ai_company UNIQUE (company_id)
);

CREATE INDEX IF NOT EXISTS idx_moat_ai_symbol ON moat_ai_narratives (symbol);

COMMENT ON TABLE moat_ai_narratives IS 'Cached AI-generated moat narratives, regenerated on user demand';
