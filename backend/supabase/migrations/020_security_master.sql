-- 020_security_master.sql
-- Migration: introduce listing-specific security identity.
--
-- WHY THIS EXISTS
--   companies is an issuer-shaped table. A company row carries one exchange, one currency
--   and one current_market_data quote, so META / NMS / COMMON and META / NEO / CDR collapse
--   into one row. The exchange shown in search is discarded before persistence, holdings
--   carry only a legacy exchange_override string, and three different CDR rules decide
--   which price gets divided by which ratio.
--
--   This migration does NOT rename or delete legacy columns. It adds the missing model and
--   backfills it from data that is already present:
--     * companies            -> issuer metadata (unchanged, legacy compatibility)
--     * securities           -> one row per tradable listing
--     * quotes               -> one quote per security_id
--     * watchlist_items.security_id -> the exact listing the user selected
--     * portfolio_holdings.security_id -> legacy read-model compatibility
--     * portfolio_holding_lots -> per-listing quantities, including mixed direct/CDR lots
--
--   Currency on trade and internal-transfer events is the lot discriminator: in this data
--   CAD trades are depositary receipts and USD trades are the underlying common share.
--   Account 9 META (company 145) therefore yields 25 CDR shares + 2 direct shares, which is
--   the mixed lot that a company-wide cdr_ratio cannot price correctly.
--
-- IDEMPOTENCY
--   CREATE TABLE IF NOT EXISTS, ADD COLUMN IF NOT EXISTS, ON CONFLICT, and guarded
--   constraints make a second execution a no-op. The apply script verifies this by running
--   the migration twice and diffing a before/after snapshot.
--
-- ROLLBACK (only after all readers are flipped back to company_id):
--   ALTER TABLE public.watchlist_items DROP CONSTRAINT IF EXISTS unique_watchlist_security;
--   ALTER TABLE public.watchlist_items DROP COLUMN IF EXISTS security_id;
--   ALTER TABLE public.portfolio_holdings DROP COLUMN IF EXISTS security_id;
--   DROP TABLE IF EXISTS public.portfolio_holding_lots;
--   DROP TABLE IF EXISTS public.quotes;
--   DROP TABLE IF EXISTS public.securities;

BEGIN;

-- ── 1. Security master ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.securities (
    security_id             bigserial PRIMARY KEY,
    company_id              integer NOT NULL REFERENCES public.companies(company_id) ON DELETE CASCADE,
    symbol                  text NOT NULL,
    exchange                text NOT NULL,
    kind                    text NOT NULL CHECK (kind IN ('COMMON','CDR','ETF','FUND','INDEX')),
    currency                character varying(3) NOT NULL,
    provider_symbol         text NOT NULL,
    underlying_security_id  bigint NULL REFERENCES public.securities(security_id) ON DELETE SET NULL,
    cdr_ratio               numeric(10,2) NULL,
    provenance              text NOT NULL DEFAULT 'migration_020',
    created_at              timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_securities_listing UNIQUE (symbol, exchange, kind, currency, provider_symbol),
    CONSTRAINT ck_securities_cdr_ratio CHECK (
        (kind = 'CDR' AND cdr_ratio IS NOT NULL AND underlying_security_id IS NOT NULL)
        OR (kind <> 'CDR' AND cdr_ratio IS NULL AND underlying_security_id IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_securities_company_id ON public.securities(company_id);
CREATE INDEX IF NOT EXISTS idx_securities_underlying ON public.securities(underlying_security_id);

-- ── 2. Quote store: one quote per listing, not per issuer ───────────────────
CREATE TABLE IF NOT EXISTS public.quotes (
    security_id     bigint PRIMARY KEY REFERENCES public.securities(security_id) ON DELETE CASCADE,
    current_price   numeric(14,6) NULL,
    open_price      numeric(14,6) NULL,
    high_price      numeric(14,6) NULL,
    low_price       numeric(14,6) NULL,
    close_price     numeric(14,6) NULL,
    volume          bigint NULL,
    market_state    character varying(20) NULL,
    source          text NOT NULL,
    is_stale        boolean NOT NULL DEFAULT true,
    last_updated    timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_quotes_last_updated ON public.quotes(last_updated);

-- ── 3. Add security identity to existing readers ───────────────────────────
ALTER TABLE public.watchlist_items ADD COLUMN IF NOT EXISTS security_id bigint NULL;
ALTER TABLE public.portfolio_holdings ADD COLUMN IF NOT EXISTS security_id bigint NULL;

-- ── 4. Backfill direct securities for every issuer ─────────────────────────
-- Exchange aliases are canonicalised here to match domain/listing_identity.py.
WITH company_base AS (
    SELECT
        c.company_id,
        upper(btrim(c.ticker_symbol)) AS symbol,
        CASE upper(btrim(coalesce(c.exchange, '')))
            WHEN 'TOR' THEN 'TSX' WHEN 'TSX' THEN 'TSX' WHEN 'TO' THEN 'TSX'
            WHEN 'XTSE' THEN 'TSX' WHEN 'T' THEN 'TSX'
            WHEN 'NE' THEN 'NEO' WHEN 'NEO' THEN 'NEO'
            WHEN 'NAS' THEN 'NMS' WHEN 'NCM' THEN 'NMS' WHEN 'NGM' THEN 'NMS'
            WHEN 'NYQ' THEN 'NYQ' WHEN 'NYS' THEN 'NYQ' WHEN 'NYSE' THEN 'NYQ'
            ELSE upper(btrim(coalesce(c.exchange, 'UNKNOWN')))
        END AS exchange,
        CASE lower(btrim(coalesce(c.security_type, '')))
            WHEN 'etf' THEN 'ETF' WHEN 'fund' THEN 'FUND' WHEN 'index' THEN 'INDEX'
            ELSE 'COMMON'
        END AS kind,
        upper(btrim(coalesce(c.currency, 'USD'))) AS currency,
        c.ticker_symbol
    FROM public.companies c
)
INSERT INTO public.securities (
    company_id, symbol, exchange, kind, currency, provider_symbol, provenance
)
SELECT
    company_id,
    symbol,
    exchange,
    kind,
    currency,
    symbol || CASE exchange
        WHEN 'TSX' THEN '.TO' WHEN 'NEO' THEN '.NE' WHEN 'TSXV' THEN '.V' ELSE ''
    END,
    'migration_020_direct'
FROM company_base
ON CONFLICT (symbol, exchange, kind, currency, provider_symbol) DO NOTHING;

-- ── 5. Backfill CDR securities linked to their underlying listing ──────────
WITH cdr_company AS (
    SELECT
        c.company_id,
        upper(btrim(c.ticker_symbol)) AS symbol,
        c.cdr_ratio,
        upper(btrim(coalesce(c.currency, 'USD'))) AS underlying_currency,
        CASE upper(btrim(coalesce(c.exchange, '')))
            WHEN 'TOR' THEN 'TSX' WHEN 'TSX' THEN 'TSX' WHEN 'TO' THEN 'TSX'
            WHEN 'XTSE' THEN 'TSX' WHEN 'T' THEN 'TSX'
            WHEN 'NE' THEN 'NEO' WHEN 'NEO' THEN 'NEO'
            WHEN 'NAS' THEN 'NMS' WHEN 'NCM' THEN 'NMS' WHEN 'NGM' THEN 'NMS'
            WHEN 'NYQ' THEN 'NYQ' WHEN 'NYS' THEN 'NYQ' WHEN 'NYSE' THEN 'NYQ'
            ELSE upper(btrim(coalesce(c.exchange, 'UNKNOWN')))
        END AS exchange
    FROM public.companies c
    WHERE c.cdr_ratio IS NOT NULL
)
INSERT INTO public.securities (
    company_id, symbol, exchange, kind, currency, provider_symbol,
    underlying_security_id, cdr_ratio, provenance
)
SELECT
    cc.company_id,
    cc.symbol,
    'NEO',
    'CDR',
    'CAD',
    cc.symbol || '.NE',
    underlying.security_id,
    cc.cdr_ratio,
    'migration_020_cdr'
FROM cdr_company cc
JOIN public.securities underlying
  ON underlying.company_id = cc.company_id
 AND underlying.symbol = cc.symbol
 AND underlying.exchange = cc.exchange
 AND underlying.kind = 'COMMON'
 AND underlying.currency = cc.underlying_currency
ON CONFLICT (symbol, exchange, kind, currency, provider_symbol) DO UPDATE
SET underlying_security_id = EXCLUDED.underlying_security_id,
    cdr_ratio = EXCLUDED.cdr_ratio,
    provenance = EXCLUDED.provenance,
    updated_at = CURRENT_TIMESTAMP
WHERE public.securities.underlying_security_id IS DISTINCT FROM EXCLUDED.underlying_security_id
   OR public.securities.cdr_ratio IS DISTINCT FROM EXCLUDED.cdr_ratio;

-- ── 6. Watchlist identity → exact listing ───────────────────────────────────
UPDATE public.watchlist_items wi
SET security_id = direct.security_id
FROM (
    SELECT company_id, min(security_id) AS security_id
    FROM public.securities
    WHERE kind <> 'CDR'
    GROUP BY company_id
) direct
WHERE wi.security_id IS NULL
  AND wi.company_id = direct.company_id;

ALTER TABLE public.watchlist_items ALTER COLUMN security_id SET NOT NULL;

ALTER TABLE public.watchlist_items DROP CONSTRAINT IF EXISTS unique_watchlist_company;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'unique_watchlist_security' AND conrelid = 'public.watchlist_items'::regclass
    ) THEN
        ALTER TABLE public.watchlist_items
            ADD CONSTRAINT unique_watchlist_security UNIQUE (watchlist_id, security_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_watchlist_items_security_id
    ON public.watchlist_items(security_id);
ALTER TABLE public.watchlist_items
    DROP CONSTRAINT IF EXISTS watchlist_items_security_id_fkey;
ALTER TABLE public.watchlist_items
    ADD CONSTRAINT watchlist_items_security_id_fkey
    FOREIGN KEY (security_id) REFERENCES public.securities(security_id) ON DELETE CASCADE;

-- ── 7. Per-lot holdings from event currency ─────────────────────────────────
-- Trade and internal-transfer events carry the listing currency. CAD means CDR, USD means
-- the underlying common share. Dividends are excluded: their quantity column is corrupted
-- upstream (see BLK-028) and must never become a share count.
CREATE TABLE IF NOT EXISTS public.portfolio_holding_lots (
    lot_id          bigserial PRIMARY KEY,
    account_id      integer NOT NULL,
    security_id     bigint NOT NULL REFERENCES public.securities(security_id) ON DELETE CASCADE,
    quantity        numeric(18,8) NOT NULL CHECK (quantity > 0),
    cost_basis      numeric(18,6) NOT NULL DEFAULT 0,
    currency        character varying(3) NOT NULL,
    source          text NOT NULL,
    created_at      timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_portfolio_holding_lot UNIQUE (account_id, security_id)
);

CREATE INDEX IF NOT EXISTS idx_holding_lots_security_id
    ON public.portfolio_holding_lots(security_id);

WITH event_lots AS (
    SELECT
        account_id,
        company_id,
        -- CAD purchases are depositary receipts. A positive USD internal transfer marks
        -- the portion subsequently held as the underlying common share, so remove it from
        -- the CDR count. The offsetting negative transfer nets to zero and is ignored.
        cad_trade_qty - coalesce(usd_transfer_in, 0) AS cdr_qty,
        coalesce(usd_transfer_in, 0) AS direct_qty
    FROM (
        SELECT
            (data->>'account_id')::integer AS account_id,
            (data->>'company_id')::integer AS company_id,
            sum((data->>'quantity')::numeric)
                FILTER (WHERE data->>'activity_type' = 'Trade'
                          AND upper(btrim(coalesce(data->>'currency','USD'))) = 'CAD') AS cad_trade_qty,
            max((data->>'quantity')::numeric)
                FILTER (WHERE data->>'activity_type' = 'InternalSecurityTransfer'
                          AND upper(btrim(coalesce(data->>'currency','USD'))) = 'USD'
                          AND (data->>'quantity')::numeric > 0) AS usd_transfer_in
        FROM public.portfolio_events
        WHERE data->>'activity_type' IN ('Trade', 'InternalSecurityTransfer')
          AND data->>'quantity' IS NOT NULL
          AND data->>'account_id' IS NOT NULL
          AND data->>'company_id' IS NOT NULL
        GROUP BY 1, 2
    ) aggregated
),
holding_cost AS (
    SELECT
        h.account_id,
        h.company_id,
        h.quantity,
        coalesce(
            h.average_cost,
            CASE WHEN h.quantity <> 0 THEN h.total_cost / h.quantity ELSE 0 END,
            0
        ) AS unit_cost,
        coalesce(h.exchange_override, '') AS exchange_override,
        c.cdr_ratio
    FROM public.portfolio_holdings h
    JOIN public.companies c ON c.company_id = h.company_id
    WHERE h.quantity > 0
),
lot_candidates AS (
    -- Non-CDR issuers: one direct lot carrying the full legacy quantity.
    SELECT
        hc.account_id,
        direct.security_id,
        hc.quantity AS quantity,
        hc.quantity * hc.unit_cost AS cost_basis,
        direct.currency,
        'migration_020_direct' AS source
    FROM holding_cost hc
    JOIN public.securities direct
      ON direct.company_id = hc.company_id
     AND direct.kind <> 'CDR'
    WHERE hc.cdr_ratio IS NULL

    UNION ALL

    -- CDR issuers: CAD trade quantity, falling back to the legacy TOR override only when
    -- there is no event evidence. Mixed accounts keep their USD direct lot below.
    SELECT
        hc.account_id,
        cdr.security_id,
        CASE
            WHEN el.cdr_qty IS NOT NULL AND el.cdr_qty > 0 THEN el.cdr_qty
            WHEN hc.exchange_override IN ('TOR','TSX','NEO','NE') THEN hc.quantity
            ELSE 0
        END AS quantity,
        CASE
            WHEN el.cdr_qty IS NOT NULL AND el.cdr_qty > 0 THEN el.cdr_qty
            WHEN hc.exchange_override IN ('TOR','TSX','NEO','NE') THEN hc.quantity
            ELSE 0
        END * hc.unit_cost AS cost_basis,
        cdr.currency,
        'migration_020_cdr_event_currency' AS source
    FROM holding_cost hc
    JOIN public.securities cdr
      ON cdr.company_id = hc.company_id AND cdr.kind = 'CDR'
    LEFT JOIN event_lots el
      ON el.account_id = hc.account_id AND el.company_id = hc.company_id
    WHERE hc.cdr_ratio IS NOT NULL

    UNION ALL

    -- Direct leg inside a mixed CDR issuer account.
    SELECT
        hc.account_id,
        direct.security_id,
        coalesce(el.direct_qty, 0) AS quantity,
        coalesce(el.direct_qty, 0) * hc.unit_cost AS cost_basis,
        direct.currency,
        'migration_020_direct_event_currency' AS source
    FROM holding_cost hc
    JOIN public.securities direct
      ON direct.company_id = hc.company_id AND direct.kind <> 'CDR'
    LEFT JOIN event_lots el
      ON el.account_id = hc.account_id AND el.company_id = hc.company_id
    WHERE hc.cdr_ratio IS NOT NULL
      AND coalesce(el.direct_qty, 0) > 0
)
INSERT INTO public.portfolio_holding_lots (
    account_id, security_id, quantity, cost_basis, currency, source
)
SELECT account_id, security_id, quantity, cost_basis, currency, source
FROM lot_candidates
WHERE quantity > 0
ON CONFLICT (account_id, security_id) DO UPDATE
SET quantity = EXCLUDED.quantity,
    cost_basis = EXCLUDED.cost_basis,
    currency = EXCLUDED.currency,
    source = EXCLUDED.source,
    updated_at = CURRENT_TIMESTAMP;

-- Legacy read-model compatibility: point each holding at its dominant listing. Lot-aware
-- valuation must read portfolio_holding_lots, never this compatibility column alone.
UPDATE public.portfolio_holdings h
SET security_id = COALESCE(cdr.security_id, direct.security_id)
FROM (
    SELECT company_id, min(security_id) AS security_id
    FROM public.securities WHERE kind = 'COMMON' GROUP BY company_id
) direct
LEFT JOIN (
    SELECT company_id, min(security_id) AS security_id
    FROM public.securities WHERE kind = 'CDR' GROUP BY company_id
) cdr ON cdr.company_id = direct.company_id
WHERE h.company_id = direct.company_id
  AND h.security_id IS NULL
  AND (
      cdr.security_id IS NULL
      OR h.exchange_override IN ('TOR','TSX','NEO','NE')
      OR EXISTS (
          SELECT 1 FROM public.portfolio_holding_lots l
          WHERE l.account_id = h.account_id AND l.security_id = cdr.security_id
      )
  );

CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_security_id
    ON public.portfolio_holdings(security_id);

-- ── 8. Seed direct quotes, mark them stale ─────────────────────────────────
-- current_market_data is issuer-keyed and may contain a CDR-contaminated price. Seed only
-- the direct listing and mark migration quotes stale; CDR quotes must come from META.NE
-- through the exact-symbol ingestion path.
INSERT INTO public.quotes (
    security_id, current_price, open_price, high_price, low_price, close_price,
    volume, market_state, source, is_stale, last_updated
)
SELECT
    s.security_id,
    md.current_price,
    md.open_price,
    md.high_price,
    md.low_price,
    md.close_price,
    md.volume,
    md.market_state,
    'migration_020_current_market_data',
    true,
    md.last_updated
FROM public.securities s
JOIN public.current_market_data md ON md.company_id = s.company_id
WHERE s.kind = 'COMMON'
ON CONFLICT (security_id) DO NOTHING;

-- ── 9. Privileges ───────────────────────────────────────────────────────────
GRANT SELECT, INSERT, UPDATE, DELETE ON public.securities TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.quotes TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.portfolio_holding_lots TO service_role;
GRANT USAGE ON SEQUENCE public.securities_security_id_seq TO service_role;
GRANT USAGE ON SEQUENCE public.portfolio_holding_lots_lot_id_seq TO service_role;
GRANT SELECT ON public.securities TO authenticated;
GRANT SELECT ON public.quotes TO authenticated;
GRANT SELECT ON public.portfolio_holding_lots TO authenticated;

COMMENT ON TABLE public.securities IS
    'One row per tradable listing. companies remains the issuer/legacy compatibility table; exchange and currency here are the selected listing identity.';
COMMENT ON TABLE public.quotes IS
    'Quote keyed by security_id. Replaces company_id-keyed current_market_data as the pricing source.';
COMMENT ON TABLE public.portfolio_holding_lots IS
    'Security-level quantity split derived from event currency. Required to value mixed direct/CDR positions such as account 9 META.';

COMMIT;
