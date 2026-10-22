-- Sizes and shape of the tables behind the compare call.
SELECT 'rowcount' AS metric, count(*)::text AS value FROM portfolio_snapshots
UNION ALL
SELECT 'date_min', min(snapshot_date)::text FROM portfolio_snapshots
UNION ALL
SELECT 'date_max', max(snapshot_date)::text FROM portfolio_snapshots
UNION ALL
SELECT 'rows_with_holdings_json', count(*)::text FROM portfolio_snapshots WHERE holdings_json IS NOT NULL
UNION ALL
SELECT 'total_bytes', pg_size_pretty(pg_total_relation_size('portfolio_snapshots')) FROM portfolio_snapshots LIMIT 1
UNION ALL
SELECT 'table_bytes', pg_size_pretty(pg_relation_size('portfolio_snapshots')) FROM portfolio_snapshots LIMIT 1
UNION ALL
SELECT 'avg_holdings_json_bytes', round(avg(length(holdings_json)))::text FROM portfolio_snapshots WHERE holdings_json IS NOT NULL
UNION ALL
SELECT 'max_holdings_json_bytes', max(length(holdings_json))::text FROM portfolio_snapshots
UNION ALL
SELECT 'accounts', string_agg(DISTINCT account_id::text, ',') FROM portfolio_snapshots;
