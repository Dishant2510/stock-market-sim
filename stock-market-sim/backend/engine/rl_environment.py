"""
rl_environment.py
─────────────────────────────────────────────────────────────────────────────
Gym-style environment for training a market-making RL agent.

The agent plays the role of the market maker for a single ticker.
Each step it observes the current market state and decides:
  1. How wide to set the spread (tight = more flow, wide = more profit per fill)
  2. Whether to lean the quotes (skew bid/ask to reduce inventory risk)

State (8 dimensions, all normalised to [-1, 1] or [0, 1]):
  [0] mid_price_norm       normalised deviation from anchor (anchor=0)
  [1] inventory_norm       shares held / MAX_INVENTORY  ∈ [-1, 1]
  [2] cash_norm            cash / STARTING_CASH         ∈ [0, 2]
  [3] order_imbalance      net buy/sell flow last N ticks ∈ [-1, 1]
  [4] sentiment            current ticker sentiment      ∈ [-1, 1]
  [5] volatility_regime    realised vol last 20 ticks / sigma_daily ∈ [0, 3]
  [6] recent_return_5      5-tick return                ∈ [-1, 1]
  [7] recent_return_20     20-tick return               ∈ [-1, 1]

Action (2 dimensions, continuous, clipped to [-1, 1]):
  [0] spread_action   → actual_spread = base_spread * (1 + spread_action)
                        -1 = tightest (0.5x base), +1 = widest (2x base)
  [1] lean_action     → shifts mid toward bid (negative) or ask (positive)
                        -1 = lean hard ask (holding too much, want to sell)
                        +1 = lean hard bid (short, want to buy)

Reward (per step):
  + realized_spread   captured half-spread on each filled order
  - inventory_penalty |inventory| / MAX_INVENTORY * INVENTORY_PENALTY
  - adverse_selection price moved against MM after fill
  - terminal_penalty  large penalty if inventory limit breached

Episode: N_STEPS ticks of simulated price data for one ticker.
─────────────────────────────────────────────────────────────────────────────
"""

import numpy as np
import random
from dataclasses import dataclass, field
from typing import Optional

# ─── ENVIRONMENT CONSTANTS ────────────────────────────────────────────────────

MAX_INVENTORY     = 500      # Max shares the MM holds (long or short)
STARTING_CASH     = 100_000
INVENTORY_PENALTY = 0.002    # Per-step penalty coefficient
ADVERSE_HORIZON   = 5        # Ticks ahead to measure adverse selection
N_STEPS           = 500      # Episode length
ORDER_ARRIVAL_P   = 0.3      # Probability of an order arriving each tick
BASE_SPREAD_LARGE = 0.001
BASE_SPREAD_MID   = 0.003
BASE_SPREAD_SMALL = 0.010
BASE_SPREADS      = {"large": BASE_SPREAD_LARGE, "mid": BASE_SPREAD_MID, "small": BASE_SPREAD_SMALL}

STATE_DIM  = 8
ACTION_DIM = 2


# ─── PRICE SIMULATOR ──────────────────────────────────────────────────────────

def simulate_price_path(anchor: float, sigma: float, n: int, seed: int = None) -> np.ndarray:
    """
    Simulate a price path using the same formula as price_engine.py.
    Used to generate training episodes offline.
    """
    rng = np.random.default_rng(seed)
    prices = np.empty(n + ADVERSE_HORIZON + 1)
    prices[0] = anchor * (0.97 + rng.random() * 0.06)
    sentiment = 0.0

    for i in range(1, len(prices)):
        noise     = rng.normal(0, sigma)
        reversion = 0.015 * (anchor - prices[i-1]) / anchor
        sent_drift = 0.002 * sentiment
        shock     = rng.normal(0, sigma * 1.5) if rng.random() < 0.01 else 0.0
        prices[i] = max(0.01, prices[i-1] * (1 + noise + reversion + sent_drift + shock))
        sentiment = sentiment * 0.92 + (rng.random() - 0.5) * 0.1

    return prices


# ─── ENVIRONMENT ──────────────────────────────────────────────────────────────

@dataclass
class MarketMakerEnv:
    """
    Single-ticker market making environment.

    Usage:
        env = MarketMakerEnv(anchor=150.0, sigma=0.0015, cap_tier="large")
        state = env.reset()
        for _ in range(N_STEPS):
            action = agent.act(state)
            state, reward, done, info = env.step(action)
    """
    anchor:   float
    sigma:    float          # Per-tick sigma (already scaled from daily)
    cap_tier: str = "large"

    # Internal state (populated on reset)
    prices:       np.ndarray = field(default_factory=lambda: np.array([]))
    tick:         int        = 0
    inventory:    float      = 0.0
    cash:         float      = STARTING_CASH
    total_pnl:    float      = 0.0
    fills:        list       = field(default_factory=list)
    price_history: list      = field(default_factory=list)
    imbalance_buf: list      = field(default_factory=list)

    def reset(self, seed: int = None) -> np.ndarray:
        self.prices        = simulate_price_path(self.anchor, self.sigma, N_STEPS, seed)
        self.tick          = 0
        self.inventory     = 0.0
        self.cash          = STARTING_CASH
        self.total_pnl     = 0.0
        self.fills         = []
        self.price_history = [self.prices[0]]
        self.imbalance_buf = []
        return self._get_state()

    def step(self, action: np.ndarray):
        """
        Advance one tick.

        Args:
            action: [spread_action, lean_action] both in [-1, 1]

        Returns:
            (state, reward, done, info)
        """
        assert self.tick < N_STEPS, "Episode finished — call reset()"

        mid   = self.prices[self.tick]
        base_spread = BASE_SPREADS.get(self.cap_tier, 0.003)

        # ── Decode action ─────────────────────────────────────────────────────
        spread_mult = 1.0 + float(np.clip(action[0], -1, 1))  # [0, 2]
        lean        = float(np.clip(action[1], -1, 1)) * base_spread * 0.5
        spread      = base_spread * spread_mult

        bid = mid * (1 - spread / 2) + lean
        ask = mid * (1 + spread / 2) + lean

        # ── Simulate order arrival ────────────────────────────────────────────
        reward = 0.0
        if random.random() < ORDER_ARRIVAL_P:
            # 50/50 buy/sell order
            if random.random() < 0.5:
                # Buyer hits the ask → MM sells
                if self.inventory > -MAX_INVENTORY:
                    self.inventory -= 1
                    self.cash      += ask
                    reward         += (ask - mid)     # half spread captured
                    self.fills.append(("sell", self.tick, ask))
                    self.imbalance_buf.append(-1)
            else:
                # Seller hits the bid → MM buys
                if self.inventory < MAX_INVENTORY:
                    self.inventory += 1
                    self.cash      -= bid
                    reward         -= (mid - bid)     # half spread captured (negative cost)
                    reward         += (mid - bid)     # actually positive: we BUY below mid
                    self.fills.append(("buy", self.tick, bid))
                    self.imbalance_buf.append(1)

        if len(self.imbalance_buf) > 20:
            self.imbalance_buf = self.imbalance_buf[-20:]

        # ── Inventory penalty ─────────────────────────────────────────────────
        inv_norm    = self.inventory / MAX_INVENTORY
        inv_penalty = abs(inv_norm) * INVENTORY_PENALTY * mid
        reward     -= inv_penalty

        # ── Adverse selection penalty ──────────────────────────────────────────
        # If we just filled and price moved against us in next ADVERSE_HORIZON ticks
        if self.fills and self.tick + ADVERSE_HORIZON < len(self.prices):
            last_action, last_tick, last_price = self.fills[-1]
            if last_tick == self.tick:
                future_mid  = self.prices[self.tick + ADVERSE_HORIZON]
                adv_sel = 0.0
                if last_action == "buy"  and future_mid < last_price:
                    adv_sel = (last_price - future_mid) * 0.5
                elif last_action == "sell" and future_mid > last_price:
                    adv_sel = (future_mid - last_price) * 0.5
                reward -= adv_sel

        # ── Breached inventory limit ───────────────────────────────────────────
        if abs(self.inventory) >= MAX_INVENTORY:
            reward -= mid * 0.01   # Hard penalty

        # ── Mark-to-market P&L ────────────────────────────────────────────────
        next_mid      = self.prices[self.tick + 1]
        mtm_value     = self.cash + self.inventory * next_mid
        self.total_pnl = mtm_value - STARTING_CASH

        self.tick += 1
        self.price_history.append(next_mid)

        done  = self.tick >= N_STEPS
        state = self._get_state() if not done else np.zeros(STATE_DIM)

        info = {
            "inventory": self.inventory,
            "cash":      self.cash,
            "total_pnl": self.total_pnl,
            "spread":    spread,
            "bid":       bid,
            "ask":       ask,
        }
        return state, reward, done, info

    def _get_state(self) -> np.ndarray:
        mid = self.prices[self.tick]

        # [0] Price deviation from anchor
        price_dev = (mid - self.anchor) / self.anchor

        # [1] Inventory normalised
        inv_norm = self.inventory / MAX_INVENTORY

        # [2] Cash normalised
        cash_norm = self.cash / STARTING_CASH

        # [3] Order imbalance (last 20 ticks)
        imbalance = np.mean(self.imbalance_buf) if self.imbalance_buf else 0.0

        # [4] Sentiment proxy: recent price drift
        if len(self.price_history) >= 5:
            sentiment_proxy = (self.price_history[-1] - self.price_history[-5]) / self.price_history[-5]
            sentiment_proxy = np.clip(sentiment_proxy * 20, -1, 1)
        else:
            sentiment_proxy = 0.0

        # [5] Volatility regime: recent realised vol / expected sigma
        if len(self.price_history) >= 20:
            returns = np.diff(self.price_history[-20:]) / self.price_history[-20:-1]
            realised_vol = returns.std()
            vol_regime   = np.clip(realised_vol / (self.sigma + 1e-8), 0, 3) / 3
        else:
            vol_regime = 0.5

        # [6] 5-tick return
        if len(self.price_history) >= 5:
            ret5 = (self.price_history[-1] - self.price_history[-5]) / self.price_history[-5]
            ret5 = np.clip(ret5 * 50, -1, 1)
        else:
            ret5 = 0.0

        # [7] 20-tick return
        if len(self.price_history) >= 20:
            ret20 = (self.price_history[-1] - self.price_history[-20]) / self.price_history[-20]
            ret20 = np.clip(ret20 * 20, -1, 1)
        else:
            ret20 = 0.0

        return np.array([
            np.clip(price_dev * 5, -1, 1),
            inv_norm,
            np.clip(cash_norm - 1, -1, 1),
            imbalance,
            sentiment_proxy,
            vol_regime,
            ret5,
            ret20,
        ], dtype=np.float32)
