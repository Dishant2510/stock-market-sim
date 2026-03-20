"""
price_model.py
─────────────────────────────────────────────────────────────────────────────
Fits a GARCH(1,1) model on historical returns for each ticker to estimate
realistic per-ticker volatility (sigma). Also engineers features from raw
OHLCV data and saves processed parquet files.

Outputs:
  stock_data/volatility_params.json         ← GARCH omega, alpha, beta, sigma per ticker
  stock_data/processed/*_features.parquet   ← Feature-engineered DataFrames

Called by: data/initializer.py
Reads from: stock_data/raw/{cap_tier}/TICKER.csv  (written by fetcher.py)
─────────────────────────────────────────────────────────────────────────────
"""

import json
import logging
import warnings
from pathlib import Path

# Heavy imports done lazily so price_engine can import load_anchor_prices
# and load_volatility_params without triggering pandas/arch at startup
def _lazy_imports():
    import numpy as np
    import pandas as pd
    from arch import arch_model
    return np, pd, arch_model

from config import (
    ALL_TICKERS,
    TICKER_CAP_MAP,
    CAP_PROFILES,
    RAW_DIRS,
    PROCESSED_DIR,
    PROCESSED_FILES,
    VOLATILITY_PARAMS_FILE,
    ANCHOR_PRICES_FILE,
    STOCK_DATA_DIR,
)

warnings.filterwarnings("ignore")  # Suppress GARCH convergence warnings
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


# ─── FEATURE ENGINEERING ─────────────────────────────────────────────────────

def engineer_features(df, ticker: str) :
    np, pd, arch_model = _lazy_imports()
    """
    Takes raw OHLCV DataFrame and adds features needed by the simulation
    engine and sentiment model.

    Features added:
      returns, log_returns, volatility_20d, sma_20, sma_50,
      rsi_14, volume_ratio, range_pct, gap_pct
    """
    df = df.copy()

    # ── Returns ──────────────────────────────────────────────────────────────
    df["returns"]     = df["close"].pct_change()
    df["log_returns"] = np.log(df["close"] / df["close"].shift(1))

    # ── Rolling Volatility (20-day annualised) ────────────────────────────────
    df["volatility_20d"] = df["returns"].rolling(20).std() * np.sqrt(252)

    # ── Moving Averages ───────────────────────────────────────────────────────
    df["sma_20"] = df["close"].rolling(20).mean()
    df["sma_50"] = df["close"].rolling(50).mean()

    # ── RSI (14-period) ───────────────────────────────────────────────────────
    delta = df["close"].diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / loss.replace(0, np.nan)
    df["rsi_14"] = 100 - (100 / (1 + rs))

    # ── Volume Ratio (vs 20-day avg) ──────────────────────────────────────────
    if "volume" in df.columns:
        df["volume_ratio"] = df["volume"] / df["volume"].rolling(20).mean()
    else:
        df["volume_ratio"] = 1.0

    # ── Price Range as % (intraday volatility proxy) ──────────────────────────
    df["range_pct"] = (df["high"] - df["low"]) / df["close"]

    # ── Overnight Gap ─────────────────────────────────────────────────────────
    df["gap_pct"] = (df["open"] - df["close"].shift(1)) / df["close"].shift(1)

    # ── Metadata ─────────────────────────────────────────────────────────────
    df["ticker"]   = ticker
    df["cap_tier"] = TICKER_CAP_MAP[ticker]

    return df.dropna(subset=["returns"])


# ─── GARCH FITTING ────────────────────────────────────────────────────────────

def fit_garch(returns, ticker: str) -> dict:
    np, pd, arch_model = _lazy_imports()
    """
    Fit a GARCH(1,1) model on daily log returns.
    Returns a dict with omega, alpha[1], beta[1], and long-run sigma.

    Falls back to rolling std if GARCH fails to converge.
    """
    # Scale returns to % for numerical stability (arch library convention)
    scaled = returns.dropna() * 100

    if len(scaled) < 60:
        log.warning(f"  {ticker}: not enough data for GARCH ({len(scaled)} rows), using rolling std")
        sigma = float(returns.std() * np.sqrt(252))
        return {"omega": None, "alpha": None, "beta": None, "sigma_daily": sigma / np.sqrt(252), "sigma_annual": sigma, "method": "rolling_std"}

    try:
        model  = arch_model(scaled, vol="Garch", p=1, q=1, dist="normal", rescale=False)
        result = model.fit(disp="off", show_warning=False)

        params = result.params
        omega  = float(params.get("omega", 0))
        alpha  = float(params.get("alpha[1]", 0))
        beta   = float(params.get("beta[1]", 0))

        # Long-run (unconditional) variance: omega / (1 - alpha - beta)
        denom         = max(1 - alpha - beta, 1e-6)
        lr_var_scaled = omega / denom
        # Convert back from scaled % to decimal daily sigma
        sigma_daily   = float(np.sqrt(lr_var_scaled) / 100)
        sigma_annual  = sigma_daily * np.sqrt(252)

        log.info(f"  {ticker}: GARCH OK | ω={omega:.4f} α={alpha:.4f} β={beta:.4f} σ_daily={sigma_daily:.4f}")
        return {
            "omega":        omega,
            "alpha":        alpha,
            "beta":         beta,
            "sigma_daily":  sigma_daily,
            "sigma_annual": sigma_annual,
            "method":       "garch",
        }

    except Exception as e:
        log.warning(f"  {ticker}: GARCH failed ({e}), using rolling std")
        sigma = float(returns.dropna().std() * np.sqrt(252))
        return {
            "omega": None, "alpha": None, "beta": None,
            "sigma_daily":  sigma / np.sqrt(252),
            "sigma_annual": sigma,
            "method":       "rolling_std",
        }


# ─── FIT ALL TICKERS ─────────────────────────────────────────────────────────

def fit_all_volatility_models() -> dict:
    np, pd, arch_model = _lazy_imports()
    """
    Fit GARCH for all 100 tickers. Saves results to volatility_params.json.
    Returns the full params dict.
    """
    log.info(f"Fitting GARCH models for {len(ALL_TICKERS)} tickers...")
    params = {}

    for i, ticker in enumerate(ALL_TICKERS, 1):
        log.info(f"[{i:03d}/{len(ALL_TICKERS)}] {ticker}")
        df = load_ticker_csv(ticker)

        if df is None or "close" not in df.columns:
            log.warning(f"  {ticker}: no data — skipping")
            params[ticker] = {"sigma_daily": 0.02, "sigma_annual": 0.317, "method": "default_fallback"}
            continue

        returns = df["close"].pct_change().dropna()
        result  = fit_garch(returns, ticker)

        # Apply cap tier volatility multiplier on top of fitted sigma
        tier       = TICKER_CAP_MAP[ticker]
        multiplier = CAP_PROFILES[tier]["volatility_multiplier"]
        # Clamp unrealistic sigma values caused by GARCH numerical failures
        # Real daily sigma range: 0.005 (very stable) to 0.15 (very volatile)
        raw_sigma = result["sigma_daily"]
        if raw_sigma > 0.15 or raw_sigma <= 0:
            log.warning(f"  {ticker}: sigma_daily={raw_sigma:.4f} out of bounds — clamping to tier default")
            tier_defaults = {"large": 0.015, "mid": 0.025, "small": 0.05}
            raw_sigma = tier_defaults[tier]
            result["sigma_daily"]  = raw_sigma
            result["sigma_annual"] = raw_sigma * (252 ** 0.5)
            result["method"]       = "clamped"

        result["sigma_daily_adjusted"]  = raw_sigma * multiplier
        result["sigma_annual_adjusted"] = result["sigma_annual"] * multiplier
        result["cap_tier"]              = tier

        params[ticker] = result

    with open(VOLATILITY_PARAMS_FILE, "w") as f:
        json.dump(params, f, indent=2)
    log.info(f"Volatility params saved → {VOLATILITY_PARAMS_FILE}")

    return params


# ─── ANCHOR PRICES ────────────────────────────────────────────────────────────

def compute_anchor_prices() -> dict:
    np, pd, arch_model = _lazy_imports()
    """
    Anchor price = most recent closing price from historical data.
    This is what the simulation uses as its starting price and mean-reversion target.

    Saves to: stock_data/anchor_prices.json
    """
    log.info("Computing anchor prices (most recent close per ticker)...")
    anchors = {}

    for ticker in ALL_TICKERS:
        df = load_ticker_csv(ticker)

        if df is None or "close" not in df.columns or df.empty:
            log.warning(f"  {ticker}: no data for anchor — using 100.0 as fallback")
            anchors[ticker] = 100.0
            continue

        last_close      = float(df["close"].iloc[-1])
        anchors[ticker] = round(last_close, 4)
        log.info(f"  {ticker}: anchor = ${last_close:.2f}")

    with open(ANCHOR_PRICES_FILE, "w") as f:
        json.dump(anchors, f, indent=2)
    log.info(f"Anchor prices saved → {ANCHOR_PRICES_FILE}")

    return anchors


# ─── PROCESS & SAVE PARQUET FILES ─────────────────────────────────────────────

def process_all_tickers() -> None:
    np, pd, arch_model = _lazy_imports()
    """
    Runs feature engineering on all tickers and saves one parquet per cap tier.

    Outputs:
      stock_data/processed/large_cap_features.parquet
      stock_data/processed/mid_cap_features.parquet
      stock_data/processed/small_cap_features.parquet
    """
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    tier_frames: dict[str, list[pd.DataFrame]] = {"large": [], "mid": [], "small": []}

    for i, ticker in enumerate(ALL_TICKERS, 1):
        log.info(f"[{i:03d}/{len(ALL_TICKERS)}] Engineering features for {ticker}...")
        df = load_ticker_csv(ticker)

        if df is None or df.empty:
            log.warning(f"  {ticker}: skipping — no CSV")
            continue

        featured = engineer_features(df, ticker)
        tier      = TICKER_CAP_MAP[ticker]
        tier_frames[tier].append(featured)

    for tier, frames in tier_frames.items():
        if not frames:
            log.warning(f"No frames for {tier} cap — skipping parquet")
            continue

        combined    = pd.concat(frames, axis=0).sort_index()
        out_path    = PROCESSED_FILES[tier]
        combined.to_parquet(out_path)
        log.info(f"Saved {len(combined)} rows ({len(frames)} tickers) → {out_path.name}")


# ─── LOAD HELPERS (used by engine at runtime) ─────────────────────────────────

def load_volatility_params() -> dict:
    """Load saved GARCH params. Called by price_engine.py at startup."""
    if not VOLATILITY_PARAMS_FILE.exists():
        raise FileNotFoundError(
            f"volatility_params.json not found. Run data/initializer.py first."
        )
    with open(VOLATILITY_PARAMS_FILE) as f:
        return json.load(f)


def load_anchor_prices() -> dict:
    """Load saved anchor prices. Called by price_engine.py at startup."""
    if not ANCHOR_PRICES_FILE.exists():
        raise FileNotFoundError(
            f"anchor_prices.json not found. Run data/initializer.py first."
        )
    with open(ANCHOR_PRICES_FILE) as f:
        return json.load(f)


def load_processed(tier: str) :
    np, pd, arch_model = _lazy_imports()
    """Load processed parquet for a given cap tier."""
    path = PROCESSED_FILES.get(tier)
    if not path or not path.exists():
        raise FileNotFoundError(f"Processed parquet for '{tier}' not found at {path}")
    return pd.read_parquet(path)


# ─── STANDALONE RUN ───────────────────────────────────────────────────────────
# python -m data.price_model

if __name__ == "__main__":
    process_all_tickers()
    fit_all_volatility_models()
    compute_anchor_prices()