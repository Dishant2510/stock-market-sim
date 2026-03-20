"""
initializer.py
─────────────────────────────────────────────────────────────────────────────
One-time setup script. Run this ONCE before starting the server.

What it does (in order):
  1. Creates all required directories
  2. Fetches raw OHLCV CSVs for all 100 tickers via yfinance
  3. Engineers features and saves processed parquet files
  4. Fits GARCH(1,1) volatility models per ticker
  5. Computes and saves anchor prices
  6. Optionally fetches news headlines (requires NewsAPI key)
  7. Validates that all expected output files exist
  8. Writes a final summary to data_manifest.json

Usage:
  python -m data.initializer               # Normal run (skips cached data)
  python -m data.initializer --force       # Re-fetch everything from scratch
  python -m data.initializer --skip-news   # Skip NewsAPI headlines fetch

After this script succeeds, stock_data/ will be fully populated and
the simulation engine can start.
─────────────────────────────────────────────────────────────────────────────
"""

import sys
import json
import time
import logging
import argparse
from datetime import datetime
from pathlib import Path

from config import (
    ALL_TICKERS,
    TICKER_CAP_MAP,
    STOCK_DATA_DIR,
    RAW_DIRS,
    PROCESSED_DIR,
    PROCESSED_FILES,
    MODELS_DIR,
    ANCHOR_PRICES_FILE,
    VOLATILITY_PARAMS_FILE,
    DATA_MANIFEST_FILE,
    NEWS_API_KEY,
)

import io
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")),
        logging.FileHandler(STOCK_DATA_DIR.parent / "initializer.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


# ─── STEP 0: DIRECTORIES ──────────────────────────────────────────────────────

def create_directories() -> None:
    log.info("-" * 60)
    log.info("STEP 0 — Creating directories")
    log.info("-" * 60)

    dirs = [
        STOCK_DATA_DIR,
        PROCESSED_DIR,
        MODELS_DIR,
        MODELS_DIR / "finbert_finetuned",
        *RAW_DIRS.values(),
    ]

    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        log.info(f"  OK  {d.relative_to(Path.cwd()) if d.is_relative_to(Path.cwd()) else d}")

    # Create empty JSON files if they don't exist yet
    for path in [ANCHOR_PRICES_FILE, VOLATILITY_PARAMS_FILE, DATA_MANIFEST_FILE]:
        if not path.exists():
            path.write_text("{}")
            log.info(f"  Created empty {path.name}")


# ─── STEP 1: FETCH RAW DATA ───────────────────────────────────────────────────

def step_fetch(force: bool) -> dict:
    log.info("-" * 60)
    log.info("STEP 1 — Fetching raw OHLCV data from yfinance")
    log.info("-" * 60)

    from data.fetcher import fetch_all_tickers, check_data_health
    status = fetch_all_tickers(force=force)
    health = check_data_health()

    ok_count   = sum(1 for v in health.values() if v["exists"] and v["rows"] > 100)
    fail_count = len(ALL_TICKERS) - ok_count

    log.info(f"Fetch result: {ok_count} OK, {fail_count} failed/empty")
    return health


# ─── STEP 2: FEATURE ENGINEERING ─────────────────────────────────────────────

def step_process() -> None:
    log.info("-" * 60)
    log.info("STEP 2 — Engineering features + saving parquet files")
    log.info("-" * 60)

    from data.price_model import process_all_tickers
    process_all_tickers()


# ─── STEP 3: FIT GARCH ───────────────────────────────────────────────────────

def step_garch() -> dict:
    log.info("-" * 60)
    log.info("STEP 3 — Fitting GARCH(1,1) volatility models")
    log.info("-" * 60)

    from data.price_model import fit_all_volatility_models
    params = fit_all_volatility_models()

    garch_count = sum(1 for v in params.values() if v.get("method") == "garch")
    log.info(f"GARCH converged: {garch_count}/{len(ALL_TICKERS)} tickers")
    return params


# ─── STEP 4: ANCHOR PRICES ───────────────────────────────────────────────────

def step_anchors() -> dict:
    log.info("-" * 60)
    log.info("STEP 4 — Computing anchor prices")
    log.info("-" * 60)

    from data.price_model import compute_anchor_prices
    anchors = compute_anchor_prices()

    valid = sum(1 for v in anchors.values() if v > 0)
    log.info(f"Anchor prices set: {valid}/{len(ALL_TICKERS)}")
    return anchors


# ─── STEP 5: NEWS HEADLINES (optional) ───────────────────────────────────────

def step_news() -> int:
    log.info("-" * 60)
    log.info("STEP 5 — Fetching news headlines (NewsAPI)")
    log.info("-" * 60)

    if not NEWS_API_KEY:
        log.warning("NEWS_API_KEY not set in .env — skipping. Sentiment model will use VADER only.")
        return 0

    from data.fetcher import fetch_news_headlines
    df = fetch_news_headlines()

    count = len(df) if not df.empty else 0
    log.info(f"Headlines fetched: {count}")
    return count


# ─── STEP 6: VALIDATION ───────────────────────────────────────────────────────

def step_validate() -> bool:
    log.info("-" * 60)
    log.info("STEP 6 — Validating all output files")
    log.info("-" * 60)

    errors = []

    # Check required JSON files
    for path in [ANCHOR_PRICES_FILE, VOLATILITY_PARAMS_FILE]:
        if not path.exists():
            errors.append(f"MISSING: {path.name}")
        else:
            with open(path) as f:
                data = json.load(f)
            if len(data) < 50:
                log.warning(f"  WARN {path.name} has only {len(data)} entries")
            else:
                log.info(f"  OK  {path.name} ({len(data)} entries)")

    # Check processed parquet files
    for tier, path in PROCESSED_FILES.items():
        if not path.exists():
            errors.append(f"MISSING: {path.name}")
        else:
            import pandas as pd
            df = pd.read_parquet(path)
            log.info(f"  OK  {path.name} ({len(df)} rows)")

    # Check at least 90/100 raw CSVs exist
    csv_count = sum(
        1 for tier_dir in RAW_DIRS.values()
        for f in tier_dir.glob("*.csv")
    )
    if csv_count < 60:
        errors.append(f"Only {csv_count}/100 raw CSVs — too few to continue")
    elif csv_count < 90:
        log.warning(f"  WARN Raw CSVs: {csv_count}/100 (some tickers unavailable on stooq)")
    else:
        log.info(f"  OK  Raw CSVs: {csv_count}/100")

    if errors:
        log.error("Validation FAILED:")
        for e in errors:
            log.error(f"  ✗ {e}")
        return False

    log.info("All validations passed ✓")
    return True


# ─── STEP 7: WRITE FINAL MANIFEST ─────────────────────────────────────────────

def write_final_manifest(health: dict, vol_params: dict, anchors: dict, news_count: int) -> None:
    log.info("-" * 60)
    log.info("STEP 7 — Writing final manifest")
    log.info("-" * 60)

    manifest = {
        "initialized_at": str(datetime.now()),
        "tickers_total":  len(ALL_TICKERS),
        "tickers_ok":     sum(1 for v in health.values() if v.get("ok")),
        "garch_fitted":   sum(1 for v in vol_params.values() if v.get("method") == "garch"),
        "anchors_set":    sum(1 for v in anchors.values() if v > 0),
        "news_headlines": news_count,
        "status": {
            ticker: {
                "rows":     health.get(ticker, {}).get("rows", 0),
                "ok":       health.get(ticker, {}).get("ok", False),
                "reason":   health.get(ticker, {}).get("reason"),
                "cap_tier": TICKER_CAP_MAP[ticker],
                "anchor":   anchors.get(ticker),
                "sigma_daily": vol_params.get(ticker, {}).get("sigma_daily_adjusted"),
            }
            for ticker in ALL_TICKERS
        },
    }

    with open(DATA_MANIFEST_FILE, "w") as f:
        json.dump(manifest, f, indent=2)
    log.info(f"Manifest written → {DATA_MANIFEST_FILE}")


# ─── PRINT SUMMARY ────────────────────────────────────────────────────────────

def print_summary(health: dict, vol_params: dict, anchors: dict) -> None:
    log.info("\n" + "=" * 60)
    log.info("INITIALIZATION COMPLETE")
    log.info("=" * 60)

    for tier in ["large", "mid", "small"]:
        tickers = [t for t in ALL_TICKERS if TICKER_CAP_MAP[t] == tier]
        ok      = sum(1 for t in tickers if health.get(t, {}).get("ok"))
        log.info(f"  {tier.upper():6s} cap: {ok}/{len(tickers)} tickers OK")

    log.info("")
    log.info("Files written:")
    log.info(f"  {ANCHOR_PRICES_FILE.name}")
    log.info(f"  {VOLATILITY_PARAMS_FILE.name}")
    log.info(f"  {DATA_MANIFEST_FILE.name}")
    for path in PROCESSED_FILES.values():
        log.info(f"  {path.name}")

    log.info("")
    log.info("Sample anchor prices:")
    sample = ["AAPL", "NVDA", "TSLA", "DDOG", "MARA", "RIOT"]
    for t in sample:
        price = anchors.get(t, "N/A")
        sigma = vol_params.get(t, {}).get("sigma_daily_adjusted", "N/A")
        sigma_str = f"{sigma:.4f}" if isinstance(sigma, float) else sigma
        log.info(f"  {t:6s}  anchor=${price:<10}  σ_daily={sigma_str}")

    log.info("")
    log.info("Next step: python -m uvicorn main:app --reload --port 8000")
    log.info("=" * 60)


# ─── MAIN ENTRYPOINT ──────────────────────────────────────────────────────────

def run(force: bool = False, skip_news: bool = False) -> None:
    start = time.time()

    log.info("=" * 60)
    log.info("STOCK MARKET SIM - DATA INITIALIZER")
    log.info(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"Force re-fetch: {force}")
    log.info("=" * 60)

    create_directories()

    health     = step_fetch(force=force)
    step_process()
    vol_params = step_garch()
    anchors    = step_anchors()
    news_count = 0 if skip_news else step_news()
    valid      = step_validate()

    if not valid:
        log.error("Initialization FAILED — see errors above.")
        sys.exit(1)

    write_final_manifest(health, vol_params, anchors, news_count)
    print_summary(health, vol_params, anchors)

    elapsed = time.time() - start
    log.info(f"Total time: {elapsed:.1f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stock Market Sim — Data Initializer")
    parser.add_argument("--force",      action="store_true", help="Re-fetch all data even if cached")
    parser.add_argument("--skip-news",  action="store_true", help="Skip NewsAPI headlines fetch")
    args = parser.parse_args()

    run(force=args.force, skip_news=args.skip_news)