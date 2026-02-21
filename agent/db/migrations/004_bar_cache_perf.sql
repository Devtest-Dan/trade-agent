-- Performance: backfill bar_time_unix and add index
-- (column is added via _add_column_if_missing in database.py before migrations run)

UPDATE bar_cache SET bar_time_unix = CAST(strftime('%s', bar_time) AS INTEGER)
WHERE bar_time_unix IS NULL;

CREATE INDEX IF NOT EXISTS idx_bar_cache_unix ON bar_cache(symbol, timeframe, bar_time_unix);
