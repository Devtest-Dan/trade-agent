-- Execution slippage tracking
ALTER TABLE trades ADD COLUMN signal_price REAL;
ALTER TABLE trades ADD COLUMN fill_price REAL;
ALTER TABLE trades ADD COLUMN slippage_pips REAL;

-- Also add to journal
ALTER TABLE trade_journal ADD COLUMN signal_price REAL;
ALTER TABLE trade_journal ADD COLUMN fill_price REAL;
ALTER TABLE trade_journal ADD COLUMN slippage_pips REAL;
