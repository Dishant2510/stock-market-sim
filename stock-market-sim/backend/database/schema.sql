-- =============================================================================
-- schema.sql  —  PostgreSQL
-- Stock Market Sim Database Schema
-- =============================================================================

-- USERS
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL DEFAULT '',
    cash          NUMERIC(14,4) NOT NULL DEFAULT 100000.00,
    created_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    last_active   TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

-- HOLDINGS
CREATE TABLE IF NOT EXISTS holdings (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ticker     TEXT    NOT NULL,
    qty        NUMERIC(14,4) NOT NULL DEFAULT 0,
    avg_cost   NUMERIC(14,4) NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, ticker)
);

CREATE INDEX IF NOT EXISTS idx_holdings_user   ON holdings(user_id);
CREATE INDEX IF NOT EXISTS idx_holdings_ticker ON holdings(ticker);

-- TRADES
CREATE TABLE IF NOT EXISTS trades (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ticker      TEXT    NOT NULL,
    action      TEXT    NOT NULL CHECK(action IN ('buy', 'sell')),
    qty         NUMERIC(14,4) NOT NULL CHECK(qty > 0),
    price       NUMERIC(14,4) NOT NULL CHECK(price > 0),
    total       NUMERIC(14,4) NOT NULL,
    cash_before NUMERIC(14,4) NOT NULL,
    cash_after  NUMERIC(14,4) NOT NULL,
    cap_tier    TEXT    NOT NULL CHECK(cap_tier IN ('large', 'mid', 'small')),
    executed_at TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trades_user     ON trades(user_id);
CREATE INDEX IF NOT EXISTS idx_trades_ticker   ON trades(ticker);
CREATE INDEX IF NOT EXISTS idx_trades_executed ON trades(executed_at);

-- PRICE_HISTORY
CREATE TABLE IF NOT EXISTS price_history (
    id          SERIAL PRIMARY KEY,
    ticker      TEXT    NOT NULL,
    cap_tier    TEXT    NOT NULL CHECK(cap_tier IN ('large', 'mid', 'small')),
    price       NUMERIC(14,4) NOT NULL,
    bid         NUMERIC(14,4) NOT NULL,
    ask         NUMERIC(14,4) NOT NULL,
    sentiment   NUMERIC(8,4)  NOT NULL DEFAULT 0.0,
    tick        INTEGER NOT NULL,
    recorded_at TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_price_ticker ON price_history(ticker, recorded_at);
CREATE INDEX IF NOT EXISTS idx_price_tick   ON price_history(tick);

-- NEWS_EVENTS
CREATE TABLE IF NOT EXISTS news_events (
    id              SERIAL PRIMARY KEY,
    ticker          TEXT    NOT NULL,
    headline        TEXT    NOT NULL,
    impact          TEXT    NOT NULL CHECK(impact IN ('bullish', 'bearish', 'neutral')),
    sentiment_delta NUMERIC(8,4) NOT NULL,
    generated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_news_ticker ON news_events(ticker, generated_at);

-- LEADERBOARD VIEW
CREATE OR REPLACE VIEW leaderboard AS
SELECT
    u.id                                                AS user_id,
    u.username,
    u.cash,
    COALESCE(SUM(h.qty * latest.price), 0)             AS holdings_value,
    u.cash + COALESCE(SUM(h.qty * latest.price), 0)    AS total_value,
    u.cash + COALESCE(SUM(h.qty * latest.price), 0) - 100000.0 AS pnl
FROM users u
LEFT JOIN holdings h ON h.user_id = u.id AND h.qty > 0
LEFT JOIN LATERAL (
    SELECT price FROM price_history p
    WHERE p.ticker = h.ticker
    ORDER BY recorded_at DESC
    LIMIT 1
) latest ON true
GROUP BY u.id, u.username, u.cash
ORDER BY total_value DESC;