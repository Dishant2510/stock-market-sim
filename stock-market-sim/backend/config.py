"""
config.py
─────────────────────────────────────────────────────────────────────────────
Central configuration for the stock market simulation.
Every other file imports from here — never hardcode constants elsewhere.
─────────────────────────────────────────────────────────────────────────────
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─── API KEYS ─────────────────────────────────────────────────────────────────
NEWS_API_KEY      = os.getenv("NEWS_API_KEY", "")       # https://newsapi.org (free tier)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")  # Legacy, unused
GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY", "")         # For AI news generation

# ─── SIMULATION CONSTANTS ─────────────────────────────────────────────────────
STARTING_CASH        = 100_000.00   # Virtual USD each user starts with
TICK_INTERVAL_SEC    = 2            # Seconds between price engine ticks
NEWS_INTERVAL_SEC    = 120           # Seconds between AI news events
SENTIMENT_DECAY      = 0.92         # Sentiment multiplied by this each tick (fades toward 0)
MAX_HISTORY_POINTS   = 500          # Max price history points kept per ticker in memory
TICKS_PER_SIM_DAY    = 1200         # Sigma scaling: daily sigma / sqrt(this) = per-tick sigma

# ─── PRICE ENGINE PARAMS ──────────────────────────────────────────────────────
# These are the α, β, γ weights in:
# P_new = P + α·imbalance + β·sentiment + σ·noise + γ·(anchor − P)
PRICE_ENGINE = {
    "alpha": 0.00005,   # Order imbalance impact (how much net buy/sell moves price)
    "beta":  0.0005,     # Sentiment drift weight
    "gamma": 0.015,     # Mean reversion strength toward anchor price
}

# ─── CAP TIER PROFILES ────────────────────────────────────────────────────────
# Each tier overrides the base engine params for realistic per-tier behavior.
CAP_PROFILES = {
    "large": {
        "volatility_multiplier":   0.08,    # Dampens GARCH sigma
        "sentiment_sensitivity":   0.04,    # Scales beta for this tier
        "liquidity_depth":         5000,   # Max shares market maker absorbs per tick
        "mean_reversion_strength": 0.85,    # Overrides gamma
        "spread_pct":              0.001,  # 0.1% bid-ask spread
        "news_weight":             0.20,   # 20% chance of being picked for news event
    },
    "mid": {
        "volatility_multiplier":   0.12,
        "sentiment_sensitivity":   0.07,
        "liquidity_depth":         2000,
        "mean_reversion_strength": 0.70,
        "spread_pct":              0.003,  # 0.3%
        "news_weight":             0.30,
    },
    "small": {
        "volatility_multiplier":   0.18,    # Moderately noisy
        "sentiment_sensitivity":   0.10,    # News moves price noticeably
        "liquidity_depth":         500,    # Thin market, easy to move
        "mean_reversion_strength": 0.55,    # Some reversion
        "spread_pct":              0.01,   # 1%
        "news_weight":             0.50,   # 50% chance — most news-sensitive
    },
}

# ─── STOCK UNIVERSE ───────────────────────────────────────────────────────────

LARGE_CAP = [
    # Tech
    "AAPL", "MSFT", "NVDA", "GOOGL", "META",
    "AMZN", "TSLA", "AMD",  "INTC",  "ORCL",
    # Finance
    "JPM",  "BAC",  "GS",   "MS",    "WFC",
    "BLK",  "AXP",  "C",    "USB",   "PNC",
    # Healthcare
    "JNJ",  "UNH",  "PFE",  "ABBV",  "MRK",
    "LLY",  "TMO",  "ABT",  "BMY",   "AMGN",
    # Energy / Industrial / Consumer
    "XOM",  "CVX",  "CAT",  "BA",    "HON",
    "GE",   "WMT",  "KO",   "PG",    "MCD",
]

MID_CAP = [
    # Tech / SaaS
    "DDOG", "ZS",   "OKTA", "TWLO",  "BILL",
    "DOCU", "HUBS", "NET",  "MDB",   "ESTC",
    # Finance
    "HOOD", "SOFI", "ALLY", "OMF",   "CURO",
    "PFSI", "RKT",  "UWMC", "ENVA",  "LDI",
    # Healthcare / Biotech
    "EXAS", "INVA", "ACAD", "JAZZ",  "IONS",
    "ONTO", "NVST", "OMCL", "NVCR",  "PRGO",
    # Consumer / Retail
    "FIVE", "RH",   "BOOT", "DXPE",  "SFM",
]

SMALL_CAP = [
    # Crypto miners / high-beta tech
    "MARA", "RIOT", "CIFR", "HUT",   "CLSK",
    "BITF", "WULF", "BTBT", "MGNI",  "KOPN",
    # Biotech / Pharma (volatile, news-driven)
    "SAVA", "AGEN", "OCGN", "NVAX",  "ADMA",
    "ATHA", "MNKD", "ARDX", "TELA",  "APRE",
    # Misc small plays
    "CLOV", "SPCE", "KOSS", "EXPR",  "OPEN",
]

ALL_TICKERS = LARGE_CAP + MID_CAP + SMALL_CAP  # 100 total

# ─── TICKER → CAP TIER MAP ────────────────────────────────────────────────────
TICKER_CAP_MAP: dict[str, str] = {
    **{t: "large" for t in LARGE_CAP},
    **{t: "mid"   for t in MID_CAP},
    **{t: "small" for t in SMALL_CAP},
}

# ─── NEWS WEIGHTS ─────────────────────────────────────────────────────────────
# Probability of each ticker being chosen for a news event.
# Small caps are weighted more heavily — they're more sentiment-sensitive.
def get_news_weights() -> list[float]:
    weights = []
    for ticker in ALL_TICKERS:
        tier   = TICKER_CAP_MAP[ticker]
        count  = len([t for t in ALL_TICKERS if TICKER_CAP_MAP[t] == tier])
        weight = CAP_PROFILES[tier]["news_weight"] / count
        weights.append(weight)
    return weights

NEWS_WEIGHTS = get_news_weights()

# ─── DATA PATHS ───────────────────────────────────────────────────────────────
import pathlib

BASE_DIR        = pathlib.Path(__file__).parent
STOCK_DATA_DIR  = BASE_DIR / "stock_data"
RAW_DIR         = STOCK_DATA_DIR / "raw"
PROCESSED_DIR   = STOCK_DATA_DIR / "processed"
MODELS_DIR      = BASE_DIR / "models"

RAW_DIRS = {
    "large": RAW_DIR / "large_cap",
    "mid":   RAW_DIR / "mid_cap",
    "small": RAW_DIR / "small_cap",
}

PROCESSED_FILES = {
    "large": PROCESSED_DIR / "large_cap_features.parquet",
    "mid":   PROCESSED_DIR / "mid_cap_features.parquet",
    "small": PROCESSED_DIR / "small_cap_features.parquet",
}

ANCHOR_PRICES_FILE     = STOCK_DATA_DIR / "anchor_prices.json"
VOLATILITY_PARAMS_FILE = STOCK_DATA_DIR / "volatility_params.json"
DATA_MANIFEST_FILE     = STOCK_DATA_DIR / "data_manifest.json"

# ─── YFINANCE FETCH CONFIG ────────────────────────────────────────────────────
YFINANCE_PERIOD   = "2y"    # 2 years of daily OHLCV data
YFINANCE_INTERVAL = "1d"    # Daily bars

# ─── NEWSAPI CONFIG ───────────────────────────────────────────────────────────
NEWSAPI_PAGE_SIZE  = 100    # Max per request on free tier
NEWSAPI_BASE_URL   = "https://newsapi.org/v2/everything"

# ─── VALIDATION ───────────────────────────────────────────────────────────────
assert len(ALL_TICKERS) == 100,       f"Expected 100 tickers, got {len(ALL_TICKERS)}"
assert len(LARGE_CAP)   == 40,        f"Expected 40 large cap, got {len(LARGE_CAP)}"
assert len(MID_CAP)     == 35,        f"Expected 35 mid cap, got {len(MID_CAP)}"
assert len(SMALL_CAP)   == 25,        f"Expected 25 small cap, got {len(SMALL_CAP)}"
assert len(set(ALL_TICKERS)) == 100,  "Duplicate tickers found in config"

weights_sum = sum(NEWS_WEIGHTS)
assert abs(weights_sum - 1.0) < 1e-9, f"News weights must sum to 1.0, got {weights_sum}"