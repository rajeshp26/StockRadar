-- Drop current_market_data table (optional — price_sources is canonical)
-- Only run this after confirming price_sources has complete coverage for all holdings.

-- DROP TABLE IF EXISTS current_market_data CASCADE;

-- ROLLBACK:
-- CREATE TABLE public.current_market_data (
--     company_id    integer                   not null,
--     current_price numeric(10,4)             not null,
--     open_price    numeric(10,4)             null,
--     high_price    numeric(10,4)             null,
--     low_price     numeric(10,4)             null,
--     close_price   numeric(10,4)             null,
--     volume        bigint                    null,
--     market_state  character varying(20)     null,
--     last_updated  timestamp with time zone  not null default CURRENT_TIMESTAMP,
--     constraint current_market_data_pkey primary key (company_id),
--     constraint current_market_data_company_id_fkey
--         foreign key (company_id) references companies (company_id) on delete CASCADE
-- ) TABLESPACE pg_default;
