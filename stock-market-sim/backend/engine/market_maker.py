"""
market_maker.py
─────────────────────────────────────────────────────────────────────────────
Lightweight AI market maker that:
  1. Continuously quotes bid/ask spreads (handled in price_engine.py)
  2. Absorbs excess sell pressure when there are no natural buyers
  3. Prevents prices from becoming illiquid or crashing to zero

The market maker is passive — it doesn't actively trade, it just absorbs
imbalance beyond the liquidity_depth threshold defined in CAP_PROFILES.

Called by: engine/order_handler.py
─────────────────────────────────────────────────────────────────────────────
"""

import logging
from config import CAP_PROFILES, TICKER_CAP_MAP

log = logging.getLogger(__name__)


def get_liquidity_depth(ticker: str) -> float:
    """
    Returns max shares the market maker will absorb per tick.
    Larger for large-cap (deep market), smaller for small-cap (thin market).
    """
    tier = TICKER_CAP_MAP[ticker]
    return CAP_PROFILES[tier]["liquidity_depth"]


def absorb_imbalance(ticker: str, raw_imbalance: float) -> tuple[float, float]:
    """
    Clip the order imbalance to the market maker's liquidity depth.

    If a user tries to sell 10,000 shares of a small-cap with depth=500,
    the market maker absorbs 500 and the remaining 9,500 hits the price hard.

    Returns:
      absorbed_imbalance  — clipped imbalance passed to price engine
      mm_absorption       — how much the market maker absorbed (for logging)
    """
    depth = get_liquidity_depth(ticker)

    # Clip to [-depth, +depth]
    absorbed  = max(-depth, min(depth, raw_imbalance))
    remainder = raw_imbalance - absorbed   # excess beyond what MM absorbs

    # If there's excess sell pressure beyond depth, apply extra downward push
    # by letting the full imbalance through (MM steps back)
    if abs(raw_imbalance) > depth:
        log.debug(
            f"MM {ticker}: imbalance {raw_imbalance:.0f} exceeds depth {depth:.0f} "
            f"— remainder {remainder:.0f} hits price"
        )
        return raw_imbalance, abs(remainder)  # pass full imbalance, note excess

    return absorbed, 0.0


def get_bid_ask(ticker: str, price: float, volatility: float) -> tuple[float, float]:
    """
    Compute market maker bid/ask quotes.

    Spread widens when:
      - Volatility is high (market maker charges more for risk)
      - Price is very low (penny stocks get wide spreads)

    Returns (bid, ask).
    """
    tier        = TICKER_CAP_MAP[ticker]
    base_spread = CAP_PROFILES[tier]["spread_pct"]

    # Widen spread based on volatility: each 1% of extra vol widens spread 20%
    vol_factor  = 1.0 + max(0.0, (volatility - 0.01) * 20)

    # Penny stock surcharge: spread widens below $5
    penny_factor = 1.5 if price < 5.0 else 1.0

    spread = base_spread * vol_factor * penny_factor
    spread = min(spread, 0.05)  # cap at 5% max spread

    bid = round(price * (1 - spread), 4)
    ask = round(price * (1 + spread), 4)
    return bid, ask


def compute_imbalances(pending_orders: list[dict]) -> dict[str, float]:
    """
    Aggregate all pending orders into net imbalance per ticker.

    imbalance > 0 = net buying pressure  → price goes up
    imbalance < 0 = net selling pressure → price goes down

    Args:
      pending_orders: list of {ticker, action, qty} dicts collected since last tick

    Returns:
      {ticker: net_imbalance_shares}
    """
    imbalances: dict[str, float] = {}

    for order in pending_orders:
        ticker = order["ticker"]
        qty    = order["qty"]
        sign   = 1.0 if order["action"] == "buy" else -1.0

        imbalances[ticker] = imbalances.get(ticker, 0.0) + sign * qty

    # Apply market maker absorption per ticker
    result = {}
    for ticker, raw in imbalances.items():
        absorbed, excess = absorb_imbalance(ticker, raw)
        result[ticker]   = absorbed

    return result