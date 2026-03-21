-- Analyst feedback loop: persist opinions and track outcomes

CREATE TABLE IF NOT EXISTS analyst_opinions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP NOT NULL,
    symbol TEXT NOT NULL,
    current_price REAL NOT NULL,
    bias TEXT NOT NULL,
    confidence REAL NOT NULL,
    alignment TEXT DEFAULT '',
    trade_ideas_json TEXT DEFAULT '[]',
    key_levels_above_json TEXT DEFAULT '[]',
    key_levels_below_json TEXT DEFAULT '[]',
    timeframe_analysis_json TEXT DEFAULT '{}',
    changes_from_last TEXT DEFAULT '',
    computation_ms INTEGER DEFAULT 0,
    ai_model TEXT DEFAULT '',
    urgency TEXT DEFAULT 'coast',
    -- Outcome tracking (filled in later by the scorer)
    outcome_scored BOOLEAN DEFAULT 0,
    outcome_scored_at TIMESTAMP,
    bias_correct BOOLEAN,
    price_after_5m REAL,
    price_after_15m REAL,
    price_after_1h REAL,
    price_after_4h REAL,
    max_favorable REAL,
    max_adverse REAL,
    tp1_hit BOOLEAN,
    tp2_hit BOOLEAN,
    sl_hit BOOLEAN,
    overall_score REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_analyst_opinions_symbol ON analyst_opinions(symbol);
CREATE INDEX IF NOT EXISTS idx_analyst_opinions_timestamp ON analyst_opinions(timestamp);
CREATE INDEX IF NOT EXISTS idx_analyst_opinions_bias ON analyst_opinions(bias);
CREATE INDEX IF NOT EXISTS idx_analyst_opinions_scored ON analyst_opinions(outcome_scored);

-- Per-level accuracy tracking: did price react at predicted levels?
CREATE TABLE IF NOT EXISTS analyst_level_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opinion_id INTEGER NOT NULL,
    level_price REAL NOT NULL,
    level_type TEXT NOT NULL,          -- unfilled_fvg, bullish_ob, bearish_ob, support, resistance, etc.
    level_timeframe TEXT,
    level_confluence INTEGER DEFAULT 1,
    direction TEXT NOT NULL,           -- above or below current price
    -- Outcome
    price_reached BOOLEAN DEFAULT 0,
    price_reacted BOOLEAN DEFAULT 0,   -- bounced/rejected at level
    price_broke BOOLEAN DEFAULT 0,     -- broke through level
    bars_to_reach INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (opinion_id) REFERENCES analyst_opinions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_level_outcomes_opinion ON analyst_level_outcomes(opinion_id);
CREATE INDEX IF NOT EXISTS idx_level_outcomes_type ON analyst_level_outcomes(level_type);

-- Aggregate accuracy stats (updated periodically)
CREATE TABLE IF NOT EXISTS analyst_accuracy_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    stat_period TEXT NOT NULL,          -- last_24h, last_7d, last_30d, all_time
    total_opinions INTEGER DEFAULT 0,
    bias_accuracy REAL DEFAULT 0.0,
    avg_confidence REAL DEFAULT 0.0,
    tp1_hit_rate REAL DEFAULT 0.0,
    tp2_hit_rate REAL DEFAULT 0.0,
    sl_hit_rate REAL DEFAULT 0.0,
    avg_max_favorable REAL DEFAULT 0.0,
    avg_max_adverse REAL DEFAULT 0.0,
    level_reach_rate REAL DEFAULT 0.0,
    level_react_rate REAL DEFAULT 0.0,
    best_timeframe TEXT,               -- which TF alignment predicts best
    worst_bias TEXT,                    -- which bias direction is least accurate
    avg_score REAL DEFAULT 0.0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, stat_period)
);
