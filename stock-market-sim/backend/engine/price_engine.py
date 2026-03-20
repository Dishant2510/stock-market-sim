"""
price_engine.py
─────────────────────────────────────────────────────────────────────────────
Core simulation engine. Maintains live market state for all 100 tickers
and updates prices on every tick using the formula:

  P_new = P + α·imbalance + β·sentiment + σ·noise + γ·(anchor - P)

  α = order imbalance impact  (how much net buy/sell moves the price)
  β = sentiment sensitivity   (how much news moves the price)
  σ = volatility              (GARCH-fitted per ticker, scaled by cap tier)
  γ = mean reversion strength (pulls price back toward real-world anchor)

Loaded once at startup. All state lives in MarketState (in-memory).
Price history is written to DB asynchronously after each tick.

Called by: main.py (background tick loop)
Reads:     stock_data/anchor_prices.json
           stock_data/volatility_params.json
           config.py CAP_PROFILES, PRICE_ENGINE
─────────────────────────────────────────────────────────────────────────────
"""

import math
import random
import logging
import asyncio
from dataclasses import dataclass, field
from typing import Optional

from config import (
    ALL_TICKERS,
    TICKER_CAP_MAP,
    CAP_PROFILES,
    PRICE_ENGINE,
    SENTIMENT_DECAY,
    MAX_HISTORY_POINTS,
)
from data.price_model import load_anchor_prices, load_volatility_params

log = logging.getLogger(__name__)


# ─── TICKER STATE ─────────────────────────────────────────────────────────────

@dataclass
class TickerState:
    """Live state for a single ticker in the simulation."""
    ticker:     str
    cap_tier:   str
    price:      float
    anchor:     float           # Mean-reversion target (real-world close price)
    bid:        float
    ask:        float
    sentiment:  float = 0.0     # Range [-1, +1], decays each tick
    sigma:      float = 0.015   # Adjusted daily volatility from GARCH
    history:    list  = field(default_factory=list)  # List of recent prices
    tick:       int   = 0


# ─── MARKET STATE ─────────────────────────────────────────────────────────────

class MarketState:
    """
    Holds live TickerState for all 100 tickers.
    Initialised once at startup from anchor prices + volatility params.
    """

    def __init__(self):
        self.tickers: dict[str, TickerState] = {}
        self.global_tick: int = 0
        self._loaded = False

    def load(self) -> None:
        """Load anchor prices and volatility params, initialise all tickers."""
        anchors    = load_anchor_prices()
        vol_params = load_volatility_params()

        for ticker in ALL_TICKERS:
            anchor   = anchors.get(ticker, 100.0)
            tier     = TICKER_CAP_MAP[ticker]
            profile  = CAP_PROFILES[tier]

            # Start price slightly randomised around anchor (+/- 2%)
            start_price = anchor * (0.98 + random.uniform(0, 0.04))

            # Get adjusted sigma from GARCH params
            vp    = vol_params.get(ticker, {})
            sigma = vp.get("sigma_daily_adjusted") or vp.get("sigma_daily") or 0.02

            spread  = profile["spread_pct"]
            bid     = round(start_price * (1 - spread), 4)
            ask     = round(start_price * (1 + spread), 4)

            self.tickers[ticker] = TickerState(
                ticker   = ticker,
                cap_tier = tier,
                price    = round(start_price, 4),
                anchor   = anchor,
                bid      = bid,
                ask      = ask,
                sigma    = sigma,
                history  = [round(start_price, 4)],
            )

        self._loaded = True
        log.info(f"MarketState loaded: {len(self.tickers)} tickers")

    def get(self, ticker: str) -> Optional[TickerState]:
        return self.tickers.get(ticker)

    def all_tickers(self) -> list[str]:
        return list(self.tickers.keys())

    def snapshot(self) -> dict:
        """Return a JSON-serialisable snapshot of all current prices."""
        return {
            ticker: {
                "price":     s.price,
                "bid":       s.bid,
                "ask":       s.ask,
                "sentiment": round(s.sentiment, 4),
                "cap_tier":  s.cap_tier,
                "tick":      s.tick,
                "history":   s.history[-100:],  # last 100 points for frontend
            }
            for ticker, s in self.tickers.items()
        }


# ─── PRICE UPDATE FORMULA ─────────────────────────────────────────────────────

def _next_price(state: TickerState, imbalance: float = 0.0) -> float:
    """
    Compute the next price for a ticker using the core formula:

      P_new = P * (1 + α·imbalance + β·sentiment·sens + σ·noise + γ·reversion)

    Parameters:
      imbalance  — net order flow this tick (positive = net buying pressure)
      state      — current TickerState
    """
    profile = CAP_PROFILES[state.cap_tier]

    # ── Components ────────────────────────────────────────────────────────────
    alpha     = PRICE_ENGINE["alpha"]
    beta      = PRICE_ENGINE["beta"]
    gamma     = profile["mean_reversion_strength"]
    sens      = profile["sentiment_sensitivity"]

    # Noise: normally distributed, scaled by ticker's GARCH sigma
    noise     = random.gauss(0, state.sigma)

    # Sentiment drift: scaled by tier sensitivity
    sent_drift = beta * state.sentiment * sens

    # Mean reversion: pulls toward anchor proportionally to deviation
    reversion = gamma * (state.anchor - state.price) / state.anchor

    # Order imbalance impact
    impact    = alpha * imbalance

    # Occasional liquidity shock (fat tails — 3% chance per tick)
    shock = 0.0
    if random.random() < 0.03:
        shock = random.gauss(0, state.sigma * 2)

    total_return = noise + sent_drift + reversion + impact + shock

    new_price = state.price * (1 + total_return)

    # Price floor — never go below $0.01
    return max(0.01, round(new_price, 4))


def _update_spread(state: TickerState, new_price: float) -> tuple[float, float]:
    """
    Compute bid/ask spread. Widens during high volatility.
    Base spread from CAP_PROFILES, multiplied by recent price move magnitude.
    """
    profile    = CAP_PROFILES[state.cap_tier]
    base_spread = profile["spread_pct"]

    # Widen spread if price moved more than 2x normal sigma this tick
    move = abs(new_price - state.price) / state.price if state.price > 0 else 0
    vol_multiplier = 1.0 + max(0, (move - state.sigma) / state.sigma)
    spread = min(base_spread * vol_multiplier, base_spread * 3)  # cap at 3x

    bid = round(new_price * (1 - spread), 4)
    ask = round(new_price * (1 + spread), 4)
    return bid, ask


# ─── TICK ─────────────────────────────────────────────────────────────────────

def tick_all(
    market: MarketState,
    imbalances: dict[str, float] | None = None,
) -> dict[str, dict]:
    """
    Advance all tickers by one simulation tick.

    Args:
      market:     MarketState instance
      imbalances: dict of {ticker: net_imbalance} from order_handler

    Returns:
      dict of per-ticker changes: {ticker: {old_price, new_price, change_pct}}
    """
    imbalances = imbalances or {}
    changes    = {}
    market.global_tick += 1

    for ticker, state in market.tickers.items():
        old_price  = state.price
        imbalance  = imbalances.get(ticker, 0.0)

        # Compute new price
        new_price  = _next_price(state, imbalance)
        bid, ask   = _update_spread(state, new_price)

        # Decay sentiment toward neutral each tick
        state.sentiment = round(state.sentiment * SENTIMENT_DECAY, 4)

        # Update state
        state.price = new_price
        state.bid   = bid
        state.ask   = ask
        state.tick  = market.global_tick

        # Append to history, cap length
        state.history.append(new_price)
        if len(state.history) > MAX_HISTORY_POINTS:
            state.history = state.history[-MAX_HISTORY_POINTS:]

        change_pct = (new_price - old_price) / old_price if old_price > 0 else 0
        changes[ticker] = {
            "old_price":  old_price,
            "new_price":  new_price,
            "change_pct": round(change_pct, 6),
            "bid":        bid,
            "ask":        ask,
            "sentiment":  state.sentiment,
        }

    return changes


def apply_sentiment_shock(
    market: MarketState,
    ticker: str,
    delta: float,
) -> None:
    """
    Apply a sentiment shock to a ticker (e.g. from a news event).
    Clamps sentiment to [-1, +1].
    """
    state = market.get(ticker)
    if state:
        state.sentiment = max(-1.0, min(1.0, state.sentiment + delta))
        log.debug(f"Sentiment shock {ticker}: delta={delta:+.3f} -> {state.sentiment:.3f}")


# ─── ASYNC DB WRITE ───────────────────────────────────────────────────────────

async def persist_tick(market: MarketState, db) -> None:
    """
    Write all current prices to price_history table.
    Called after each tick by the background loop in main.py.
    Runs prune every 100 ticks to keep DB size bounded.
    """
    from database.db import record_price, prune_price_history

    for ticker, state in market.tickers.items():
        await record_price(
            db       = db,
            ticker   = ticker,
            cap_tier = state.cap_tier,
            price    = state.price,
            bid      = state.bid,
            ask      = state.ask,
            sentiment = state.sentiment,
            tick     = state.tick,
        )


    # Prune old history every 100 ticks
    if market.global_tick % 100 == 0:
        await prune_price_history(db, keep_ticks=500)
        log.debug(f"Price history pruned at tick {market.global_tick}")


# ─── SINGLETON ────────────────────────────────────────────────────────────────
# Shared instance imported by main.py and order_handler.py

market_state = MarketState()