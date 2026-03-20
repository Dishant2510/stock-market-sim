"""
market_maker.py  (RL-upgraded version)
─────────────────────────────────────────────────────────────────────────────
Replaces the passive market maker with one that:
  1. Tries to load the RL policy from models/rl_mm_policy.pt at startup
  2. If loaded: uses RL agent to set spreads + lean quotes per ticker
  3. If not loaded: falls back to the original passive logic (unchanged)

Drop-in replacement — all function signatures stay the same.
─────────────────────────────────────────────────────────────────────────────
"""

import logging
from pathlib import Path
from config import CAP_PROFILES, TICKER_CAP_MAP
from engine.rl_agent import rl_mm

log = logging.getLogger(__name__)

# Load RL model at import time (non-blocking — falls back if missing)
_MODEL_PATH = Path(__file__).parent.parent / "models" / "rl_mm_policy.pt"
_rl_active  = rl_mm.load(_MODEL_PATH)

if _rl_active:
    log.info("Market maker mode: RL AGENT")
else:
    log.info("Market maker mode: PASSIVE (train RL agent to upgrade)")


# ─── UNCHANGED HELPERS ────────────────────────────────────────────────────────

def get_liquidity_depth(ticker: str) -> float:
    tier = TICKER_CAP_MAP[ticker]
    return CAP_PROFILES[tier]["liquidity_depth"]


def absorb_imbalance(ticker: str, raw_imbalance: float) -> tuple[float, float]:
    depth     = get_liquidity_depth(ticker)
    absorbed  = max(-depth, min(depth, raw_imbalance))
    remainder = raw_imbalance - absorbed
    if abs(raw_imbalance) > depth:
        log.debug(f"MM {ticker}: imbalance {raw_imbalance:.0f} exceeds depth {depth:.0f}")
        return raw_imbalance, abs(remainder)
    return absorbed, 0.0


def compute_imbalances(pending_orders: list[dict]) -> dict[str, float]:
    imbalances: dict[str, float] = {}
    for order in pending_orders:
        ticker = order["ticker"]
        qty    = order["qty"]
        sign   = 1.0 if order["action"] == "buy" else -1.0
        imbalances[ticker] = imbalances.get(ticker, 0.0) + sign * qty
    result = {}
    for ticker, raw in imbalances.items():
        absorbed, _ = absorb_imbalance(ticker, raw)
        result[ticker] = absorbed
    return result


# ─── RL-UPGRADED BID/ASK ──────────────────────────────────────────────────────

def get_bid_ask(
    ticker:       str,
    price:        float,
    volatility:   float,
    inventory:    float = 0.0,
    cash:         float = 100_000,
    imbalance:    float = 0.0,
    sentiment:    float = 0.0,
    price_history: list = None,
) -> tuple[float, float]:
    """
    Compute bid/ask.

    If RL model loaded: delegate to rl_mm.get_quotes() for dynamic spreads.
    Otherwise: passive formula (same as original market_maker.py).

    Extra kwargs (inventory, cash, imbalance, sentiment, price_history)
    are used by RL agent and silently ignored by passive fallback.
    """
    tier        = TICKER_CAP_MAP[ticker]
    base_spread = CAP_PROFILES[tier]["spread_pct"]

    if _rl_active:
        return rl_mm.get_quotes(
            ticker        = ticker,
            mid_price     = price,
            inventory     = inventory,
            cash          = cash,
            imbalance     = imbalance,
            sentiment     = sentiment,
            price_history = price_history or [],
            sigma         = volatility,
            cap_tier      = tier,
        )

    # ── Passive fallback (original logic) ─────────────────────────────────────
    vol_factor   = 1.0 + max(0.0, (volatility - 0.01) * 20)
    penny_factor = 1.5 if price < 5.0 else 1.0
    spread       = min(base_spread * vol_factor * penny_factor, 0.05)
    bid          = round(price * (1 - spread), 4)
    ask          = round(price * (1 + spread), 4)
    return bid, ask
