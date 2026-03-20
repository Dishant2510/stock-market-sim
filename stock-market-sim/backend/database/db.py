"""
db.py
─────────────────────────────────────────────────────────────────────────────
Async PostgreSQL connection and all database helper functions.

Uses asyncpg for non-blocking DB access inside FastAPI's async event loop.
Connection URL read from DATABASE_URL environment variable (set by Railway).

Tables: users, holdings, trades, price_history, news_events
View:   leaderboard
─────────────────────────────────────────────────────────────────────────────
"""

import asyncpg
import logging
import os
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")   # Set by Railway automatically
SCHEMA_PATH  = Path(__file__).parent / "schema.sql"

# ─── CONNECTION POOL ──────────────────────────────────────────────────────────

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Return (or create) the shared connection pool."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
        log.info("PostgreSQL connection pool created")
    return _pool


async def init_db() -> None:
    """
    Create all tables if they don't exist.
    Called once at FastAPI startup via lifespan.
    """
    pool = await get_pool()
    sql  = SCHEMA_PATH.read_text(encoding="utf-8")
    async with pool.acquire() as conn:
        await conn.execute(sql)
    log.info("Database initialised")


async def get_db_dep():
    """
    FastAPI dependency — yields a connection from the pool.
    Auto-returned to pool after request completes.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


# asyncpg returns Record objects — convert to plain dicts
# Also cast Decimal to float so arithmetic works in Python
from decimal import Decimal

def _cast(v):
    if isinstance(v, Decimal):
        return float(v)
    return v

def _row(r) -> dict:
    return {k: _cast(v) for k, v in dict(r).items()} if r else None

def _rows(rs) -> list[dict]:
    return [{k: _cast(v) for k, v in dict(r).items()} for r in rs]


# ─── USER HELPERS ─────────────────────────────────────────────────────────────

async def create_user(db, username: str, password: str) -> dict:
    """
    Create a new user with starting cash and hashed password.
    Raises ValueError if username already taken.
    """
    import hashlib
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    try:
        row = await db.fetchrow(
            """
            INSERT INTO users (username, password_hash)
            VALUES ($1, $2)
            RETURNING *
            """,
            username, password_hash
        )
        return _row(row)
    except asyncpg.UniqueViolationError:
        raise ValueError(f"Username '{username}' is already taken.")


async def get_user(db, user_id: int) -> Optional[dict]:
    """Fetch one user by ID."""
    row = await db.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
    return _row(row)


async def get_user_by_username(db, username: str) -> Optional[dict]:
    """Fetch one user by username."""
    row = await db.fetchrow("SELECT * FROM users WHERE username = $1", username)
    return _row(row)


async def update_user_cash(db, user_id: int, new_cash: float) -> None:
    """Update a user's cash balance."""
    await db.execute(
        "UPDATE users SET cash = $1, last_active = NOW() WHERE id = $2",
        round(new_cash, 4), user_id
    )


# ─── HOLDINGS HELPERS ─────────────────────────────────────────────────────────

async def get_holdings(db, user_id: int) -> list[dict]:
    """Return all non-zero holdings for a user."""
    rows = await db.fetch(
        "SELECT * FROM holdings WHERE user_id = $1 AND qty > 0 ORDER BY ticker",
        user_id
    )
    return _rows(rows)


async def get_holding(db, user_id: int, ticker: str) -> Optional[dict]:
    """Return a single holding row or None."""
    row = await db.fetchrow(
        "SELECT * FROM holdings WHERE user_id = $1 AND ticker = $2",
        user_id, ticker
    )
    return _row(row)


async def upsert_holding(db, user_id: int, ticker: str, qty: float, avg_cost: float) -> None:
    """Insert or update a holding. Deletes row if qty reaches 0."""
    if qty <= 0:
        await db.execute(
            "DELETE FROM holdings WHERE user_id = $1 AND ticker = $2",
            user_id, ticker
        )
    else:
        await db.execute(
            """
            INSERT INTO holdings (user_id, ticker, qty, avg_cost, updated_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (user_id, ticker)
            DO UPDATE SET
                qty        = EXCLUDED.qty,
                avg_cost   = EXCLUDED.avg_cost,
                updated_at = EXCLUDED.updated_at
            """,
            user_id, ticker, round(qty, 4), round(avg_cost, 4)
        )


# ─── TRADE HELPERS ────────────────────────────────────────────────────────────

async def log_trade(
    db,
    user_id:     int,
    ticker:      str,
    action:      str,
    qty:         float,
    price:       float,
    cap_tier:    str,
    cash_before: float,
    cash_after:  float,
) -> int:
    """Insert a trade record. Returns the new trade ID."""
    total = round(price * qty, 4)
    row = await db.fetchrow(
        """
        INSERT INTO trades
            (user_id, ticker, action, qty, price, total, cash_before, cash_after, cap_tier)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
        RETURNING id
        """,
        user_id, ticker, action,
        round(qty, 4), round(price, 4), total,
        round(cash_before, 4), round(cash_after, 4), cap_tier
    )
    return row["id"]


async def get_trade_history(db, user_id: int, limit: int = 50) -> list[dict]:
    """Return the last N trades for a user, newest first."""
    rows = await db.fetch(
        """
        SELECT * FROM trades
        WHERE user_id = $1
        ORDER BY executed_at DESC
        LIMIT $2
        """,
        user_id, limit
    )
    return _rows(rows)


# ─── PRICE HISTORY HELPERS ────────────────────────────────────────────────────

async def record_price(
    db,
    ticker:    str,
    cap_tier:  str,
    price:     float,
    bid:       float,
    ask:       float,
    sentiment: float,
    tick:      int,
) -> None:
    """Insert one price snapshot for a ticker."""
    await db.execute(
        """
        INSERT INTO price_history (ticker, cap_tier, price, bid, ask, sentiment, tick)
        VALUES ($1,$2,$3,$4,$5,$6,$7)
        """,
        ticker, cap_tier,
        round(price, 4), round(bid, 4), round(ask, 4),
        round(sentiment, 4), tick
    )


async def get_price_history(db, ticker: str, limit: int = 200) -> list[dict]:
    """Return the last N price records for a ticker, oldest first."""
    rows = await db.fetch(
        """
        SELECT price, bid, ask, sentiment, tick, recorded_at
        FROM price_history
        WHERE ticker = $1
        ORDER BY tick DESC
        LIMIT $2
        """,
        ticker, limit
    )
    return list(reversed(_rows(rows)))


async def prune_price_history(db, keep_ticks: int = 500) -> None:
    """Delete old price history keeping only the last N ticks per ticker."""
    await db.execute(
        """
        DELETE FROM price_history
        WHERE id NOT IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY ticker ORDER BY tick DESC
                ) AS rn
                FROM price_history
            ) ranked
            WHERE rn <= $1
        )
        """,
        keep_ticks
    )


# ─── NEWS HELPERS ─────────────────────────────────────────────────────────────

async def log_news(db, ticker: str, headline: str, impact: str, sentiment_delta: float) -> None:
    """Insert a generated news event."""
    await db.execute(
        """
        INSERT INTO news_events (ticker, headline, impact, sentiment_delta)
        VALUES ($1,$2,$3,$4)
        """,
        ticker, headline, impact, round(sentiment_delta, 4)
    )


async def get_recent_news(db, limit: int = 20) -> list[dict]:
    """Return the last N news events, newest first."""
    rows = await db.fetch(
        "SELECT * FROM news_events ORDER BY generated_at DESC LIMIT $1",
        limit
    )
    return _rows(rows)


# ─── LEADERBOARD ──────────────────────────────────────────────────────────────

async def get_leaderboard(db, limit: int = 20) -> list[dict]:
    """Return top N users by total portfolio value."""
    rows = await db.fetch(
        "SELECT * FROM leaderboard LIMIT $1",
        limit
    )
    return _rows(rows)