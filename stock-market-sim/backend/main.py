"""
main.py
─────────────────────────────────────────────────────────────────────────────
FastAPI application entry point.

Endpoints:
  POST /users/register          register a new user
  GET  /users/{user_id}         get user profile + cash
  GET  /prices                  get all current prices snapshot
  GET  /prices/{ticker}         get price history for one ticker
  POST /trade                   execute a buy or sell
  GET  /portfolio/{user_id}     get holdings + P&L for a user
  GET  /trades/{user_id}        get trade history for a user
  GET  /news                    get recent news events
  GET  /leaderboard             get top users by portfolio value

Background tasks:
  tick_loop   — updates all prices every TICK_INTERVAL_SEC seconds
  news_loop   — generates AI news every NEWS_INTERVAL_SEC seconds

Run with:
  uvicorn main:app --reload --port 8000
─────────────────────────────────────────────────────────────────────────────
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import asyncpg

from config import (
    TICK_INTERVAL_SEC,
    NEWS_INTERVAL_SEC,
    ALL_TICKERS,
    TICKER_CAP_MAP,
)
from database.db import (
    init_db,
    get_db_dep,
    create_user,
    get_user,
    get_user_by_username,
    get_holdings,
    get_trade_history,
    get_recent_news,
    get_leaderboard,
    get_price_history,
)
from engine.price_engine import market_state, tick_all, persist_tick
from engine.market_maker import compute_imbalances
from engine.order_handler import execute_trade, drain_pending_orders
from engine.news_engine import generate_news_event

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger(__name__)

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


# ─── LIFESPAN ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    log.info("Starting up Stock Market Sim...")

    # 1. Init DB (creates tables if not exist)
    await init_db()

    # 2. Load market state from anchor prices + vol params
    market_state.load()
    log.info(f"Market state loaded: {len(market_state.tickers)} tickers")

    # 3. Start background loops
    tick_task = asyncio.create_task(tick_loop())
    news_task = asyncio.create_task(news_loop())

    log.info("Background loops started")
    log.info(f"Server ready. Tick interval: {TICK_INTERVAL_SEC}s | News interval: {NEWS_INTERVAL_SEC}s")

    yield  # Server is running

    # Shutdown
    tick_task.cancel()
    news_task.cancel()
    log.info("Shutdown complete")


# ─── APP ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title       = "Stock Market Sim API",
    description = "AI-driven virtual stock market simulation",
    version     = "1.0.0",
    lifespan    = lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)


# ─── BACKGROUND LOOPS ─────────────────────────────────────────────────────────

async def tick_loop():
    """
    Price tick loop — runs every TICK_INTERVAL_SEC seconds.
    1. Drain pending orders from order_handler
    2. Compute net imbalances via market_maker
    3. Tick all prices via price_engine
    4. Persist prices to DB
    """
    while True:
        await asyncio.sleep(TICK_INTERVAL_SEC)
        try:
            pending    = await drain_pending_orders()
            imbalances = compute_imbalances(pending) if pending else {}

            tick_all(market_state, imbalances)

            # Write to DB via connection pool
            from database.db import get_pool
            _pool = await get_pool()
            async with _pool.acquire() as db:
                await persist_tick(market_state, db)

        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error(f"Tick loop error: {e}", exc_info=True)


async def news_loop():
    """
    News generation loop — runs every NEWS_INTERVAL_SEC seconds.
    Generates one AI news event and applies sentiment shock to market.
    """
    await asyncio.sleep(5)  # Small delay before first news event
    while True:
        await asyncio.sleep(NEWS_INTERVAL_SEC)
        try:
            from database.db import get_pool
            pool = await get_pool()
            async with pool.acquire() as db:
                await generate_news_event(market_state, db)

        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error(f"News loop error: {e}", exc_info=True)


# ─── REQUEST MODELS ───────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=30)
    password: str = Field(..., min_length=4, max_length=100)

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=30)
    password: str = Field(..., min_length=1, max_length=100)

class TradeRequest(BaseModel):
    user_id: int
    ticker:  str
    action:  str   # "buy" or "sell"
    qty:     float = Field(..., gt=0)


# ─── ROUTES ───────────────────────────────────────────────────────────────────

@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return {
        "status":  "ok",
        "tickers": len(market_state.tickers),
        "tick":    market_state.global_tick,
    }


# ── Users ──────────────────────────────────────────────────────────────────────

@app.post("/users/register", status_code=201)
async def register_user(
    body: RegisterRequest,
    db = Depends(get_db_dep),
):
    try:
        user = await create_user(db, body.username, body.password)
        return {"ok": True, "user": user}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/users/login")
async def login(
    req: LoginRequest,
    db = Depends(get_db_dep),
):
    import hashlib
    user = await get_user_by_username(db, req.username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    expected = hashlib.sha256(req.password.encode()).hexdigest()
    if user["password_hash"] != expected:
        # Legacy accounts with no password — allow empty hash to match any password once
        if user["password_hash"] != "":
            raise HTTPException(status_code=401, detail="Incorrect password")
    return {k: v for k, v in dict(user).items() if k != "password_hash"}


@app.get("/users/{user_id}")
async def get_user_profile(
    user_id: int,
    db = Depends(get_db_dep),
):
    user = await get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# ── Prices ─────────────────────────────────────────────────────────────────────

@app.get("/prices")
async def get_all_prices():
    """Return current price snapshot for all tickers."""
    return market_state.snapshot()


@app.get("/prices/{ticker}")
async def get_ticker_price(
    ticker: str,
    limit:  int = 200,
    db = Depends(get_db_dep),
):
    """Return price history for a single ticker (for charting)."""
    ticker = ticker.upper()
    if ticker not in ALL_TICKERS:
        raise HTTPException(status_code=404, detail=f"Unknown ticker: {ticker}")

    state   = market_state.get(ticker)
    history = await get_price_history(db, ticker, limit=limit)

    return {
        "ticker":   ticker,
        "cap_tier": TICKER_CAP_MAP[ticker],
        "current":  {
            "price":     state.price,
            "bid":       state.bid,
            "ask":       state.ask,
            "sentiment": state.sentiment,
            "tick":      state.tick,
        } if state else {},
        "history": history,
    }


# ── Trading ────────────────────────────────────────────────────────────────────

@app.post("/trade")
async def trade(
    body: TradeRequest,
    db = Depends(get_db_dep),
):
    result = await execute_trade(
        db      = db,
        market  = market_state,
        user_id = body.user_id,
        ticker  = body.ticker,
        action  = body.action,
        qty     = body.qty,
    )
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.message)

    return {
        "ok":         True,
        "message":    result.message,
        "ticker":     result.ticker,
        "action":     result.action,
        "qty":        result.qty,
        "exec_price": result.exec_price,
        "total":      result.total,
        "cash_after": result.cash_after,
        "trade_id":   result.trade_id,
    }


# ── Portfolio ──────────────────────────────────────────────────────────────────

@app.get("/portfolio/{user_id}")
async def get_portfolio(
    user_id: int,
    db = Depends(get_db_dep),
):
    user = await get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    holdings      = await get_holdings(db, user_id)
    holdings_value = 0.0
    enriched       = []

    for h in holdings:
        ticker    = h["ticker"]
        state     = market_state.get(ticker)
        cur_price = state.price if state else h["avg_cost"]
        mkt_value = round(cur_price * h["qty"], 4)
        pnl       = round((cur_price - h["avg_cost"]) * h["qty"], 4)
        pnl_pct   = round((cur_price - h["avg_cost"]) / h["avg_cost"], 6) if h["avg_cost"] else 0

        holdings_value += mkt_value
        enriched.append({
            **h,
            "current_price": cur_price,
            "market_value":  mkt_value,
            "pnl":           pnl,
            "pnl_pct":       pnl_pct,
        })

    total_value = round(float(user["cash"]) + holdings_value, 4)
    total_pnl   = round(float(total_value) - 100_000.0, 4)

    return {
        "user_id":        user_id,
        "username":       user["username"],
        "cash":           float(user["cash"]),
        "holdings_value": round(float(holdings_value), 4),
        "total_value":    total_value,
        "total_pnl":      total_pnl,
        "holdings":       enriched,
    }


# ── Trade History ──────────────────────────────────────────────────────────────

@app.get("/trades/{user_id}")
async def get_trades(
    user_id: int,
    limit:   int = 50,
    db = Depends(get_db_dep),
):
    user = await get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    trades = await get_trade_history(db, user_id, limit=limit)
    return {"user_id": user_id, "trades": trades}


# ── News ───────────────────────────────────────────────────────────────────────

@app.get("/news")
async def get_news(
    limit: int = 20,
    db = Depends(get_db_dep),
):
    news = await get_recent_news(db, limit=limit)
    return {"news": news}


# ── Leaderboard ────────────────────────────────────────────────────────────────

@app.get("/leaderboard")
async def leaderboard(
    limit: int = 20,
    db = Depends(get_db_dep),
):
    rows = await get_leaderboard(db, limit=limit)
    return {"leaderboard": rows}