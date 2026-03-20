"""
order_handler.py
─────────────────────────────────────────────────────────────────────────────
Validates and executes user trade requests (buy/sell).

Flow for each trade:
  1. Validate inputs (qty > 0, ticker exists, user has enough cash/shares)
  2. Execute at current bid (sell) or ask (buy) price
  3. Update user cash and holdings in DB
  4. Log trade to trades table
  5. Register order in pending_orders so imbalance hits price next tick

Called by: main.py POST /trade
─────────────────────────────────────────────────────────────────────────────
"""

import logging
import asyncio
from typing import Optional
from dataclasses import dataclass

import aiosqlite

from config import TICKER_CAP_MAP, ALL_TICKERS
from engine.price_engine import MarketState
from database.db import (
    get_user,
    update_user_cash,
    get_holding,
    upsert_holding,
    log_trade,
)

log = logging.getLogger(__name__)


# ─── PENDING ORDERS BUFFER ────────────────────────────────────────────────────
# Orders accumulate here between ticks.
# price_engine.tick_all() drains this buffer each tick via market_maker.

_pending_orders: list[dict] = []
_orders_lock = asyncio.Lock()


async def register_pending(ticker: str, action: str, qty: float) -> None:
    """Add an executed order to the pending buffer for next price tick."""
    async with _orders_lock:
        _pending_orders.append({"ticker": ticker, "action": action, "qty": qty})


async def drain_pending_orders() -> list[dict]:
    """
    Remove and return all pending orders.
    Called by the tick loop in main.py before each price update.
    """
    async with _orders_lock:
        orders = list(_pending_orders)
        _pending_orders.clear()
        return orders


# ─── TRADE RESULT ─────────────────────────────────────────────────────────────

@dataclass
class TradeResult:
    ok:          bool
    message:     str
    ticker:      str        = ""
    action:      str        = ""
    qty:         float      = 0.0
    exec_price:  float      = 0.0
    total:       float      = 0.0
    cash_after:  float      = 0.0
    trade_id:    Optional[int] = None


# ─── CORE TRADE EXECUTION ─────────────────────────────────────────────────────

async def execute_trade(
    db:       aiosqlite.Connection,
    market:   MarketState,
    user_id:  int,
    ticker:   str,
    action:   str,
    qty:      float,
) -> TradeResult:
    """
    Validate and execute a buy or sell order.

    Buy  → executes at ASK price (user pays more)
    Sell → executes at BID price (user receives less)

    Returns a TradeResult with ok=True on success, ok=False with message on failure.
    """
    # ── Input validation ──────────────────────────────────────────────────────
    ticker = ticker.upper().strip()
    action = action.lower().strip()

    if ticker not in ALL_TICKERS:
        return TradeResult(ok=False, message=f"Unknown ticker: {ticker}")

    if action not in ("buy", "sell"):
        return TradeResult(ok=False, message=f"Invalid action '{action}'. Must be 'buy' or 'sell'.")

    if not isinstance(qty, (int, float)) or qty <= 0:
        return TradeResult(ok=False, message="Quantity must be a positive number.")

    qty = float(qty)

    # ── Fetch user ────────────────────────────────────────────────────────────
    user = await get_user(db, user_id)
    if not user:
        return TradeResult(ok=False, message=f"User {user_id} not found.")

    # ── Get current market price ───────────────────────────────────────────────
    state = market.get(ticker)
    if not state:
        return TradeResult(ok=False, message=f"No market data for {ticker}.")

    cap_tier   = TICKER_CAP_MAP[ticker]
    exec_price = state.ask if action == "buy" else state.bid
    total      = round(exec_price * qty, 4)

    # ── Buy validation ────────────────────────────────────────────────────────
    if action == "buy":
        if user["cash"] < total:
            return TradeResult(
                ok=False,
                message=(
                    f"Insufficient cash. Need ${total:,.2f}, "
                    f"have ${user['cash']:,.2f}."
                )
            )

        cash_before = user["cash"]
        cash_after  = round(cash_before - total, 4)

        # Update holdings: compute new avg cost
        holding     = await get_holding(db, user_id, ticker)
        old_qty     = holding["qty"]    if holding else 0.0
        old_cost    = holding["avg_cost"] if holding else 0.0
        new_qty     = round(old_qty + qty, 4)
        new_avg     = round(
            (old_qty * old_cost + qty * exec_price) / new_qty, 4
        ) if new_qty > 0 else exec_price

        await update_user_cash(db, user_id, cash_after)
        await upsert_holding(db, user_id, ticker, new_qty, new_avg)

    # ── Sell validation ───────────────────────────────────────────────────────
    else:
        holding = await get_holding(db, user_id, ticker)
        held    = holding["qty"] if holding else 0.0

        if held < qty:
            return TradeResult(
                ok=False,
                message=(
                    f"Insufficient shares. Trying to sell {qty:.2f}, "
                    f"holding {held:.2f} {ticker}."
                )
            )

        cash_before = user["cash"]
        cash_after  = round(cash_before + total, 4)
        new_qty     = round(held - qty, 4)
        avg_cost    = holding["avg_cost"]

        await update_user_cash(db, user_id, cash_after)
        await upsert_holding(db, user_id, ticker, new_qty, avg_cost)

    # ── Log trade ─────────────────────────────────────────────────────────────
    trade_id = await log_trade(
        db          = db,
        user_id     = user_id,
        ticker      = ticker,
        action      = action,
        qty         = qty,
        price       = exec_price,
        cap_tier    = cap_tier,
        cash_before = cash_before,
        cash_after  = cash_after,
    )
    await db.commit()

    # ── Register for next tick imbalance ──────────────────────────────────────
    await register_pending(ticker, action, qty)

    log.info(
        f"TRADE [{trade_id}] user={user_id} {action.upper()} "
        f"{qty:.2f}x {ticker} @ ${exec_price:.2f} | "
        f"cash: ${cash_before:.2f} -> ${cash_after:.2f}"
    )

    return TradeResult(
        ok         = True,
        message    = f"{action.upper()} {qty:.2f} {ticker} @ ${exec_price:.2f}",
        ticker     = ticker,
        action     = action,
        qty        = qty,
        exec_price = exec_price,
        total      = total,
        cash_after = cash_after,
        trade_id   = trade_id,
    )