"""
fetcher.py
─────────────────────────────────────────────────────────────────────────────
Downloads historical OHLCV data for all 100 tickers.

Primary source:  stooq (via pandas_datareader) — no API key, no rate limits
Fallback source: yfinance — used only if stooq returns empty

stooq provides free daily OHLCV for US stocks going back years.
No crumb, no cookie, no 429 issues.

Called by: data/initializer.py
─────────────────────────────────────────────────────────────────────────────
"""

import json
import time
import math
import logging
import requests
import pandas as pd
import yfinance as yf
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    import pandas_datareader as pdr
    DATAREADER_AVAILABLE = True
except ImportError:
    DATAREADER_AVAILABLE = False

from config import (
    ALL_TICKERS,
    TICKER_CAP_MAP,
    RAW_DIRS,
    STOCK_DATA_DIR,
    DATA_MANIFEST_FILE,
    YFINANCE_PERIOD,
    YFINANCE_INTERVAL,
    NEWS_API_KEY,
    NEWSAPI_BASE_URL,
    NEWSAPI_PAGE_SIZE,
    LARGE_CAP,
    MID_CAP,
    SMALL_CAP,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# 2 years of data
END_DATE   = datetime.today()
START_DATE = END_DATE - timedelta(days=730)

DELAY_BETWEEN_TICKERS = 2   # stooq is much more lenient than Yahoo


# ─── MANIFEST HELPERS ─────────────────────────────────────────────────────────

def load_manifest() -> dict:
    if DATA_MANIFEST_FILE.exists():
        try:
            content = DATA_MANIFEST_FILE.read_text(encoding="utf-8").strip()
            if content:
                return json.loads(content)
        except (json.JSONDecodeError, ValueError):
            pass
    return {"last_fetched": None, "tickers_fetched": 0, "status": {}}


def save_manifest(manifest: dict) -> None:
    with open(DATA_MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


def already_fetched_today(manifest: dict) -> bool:
    last = manifest.get("last_fetched")
    return bool(last and last == str(date.today()))


# ─── STOOQ FETCH (primary) ────────────────────────────────────────────────────

def _fetch_via_stooq(ticker: str) -> pd.DataFrame | None:
    """
    Fetch OHLCV from stooq.com via pandas_datareader.
    Free, no API key, no rate limiting.
    stooq uses US ticker symbols directly (AAPL, MSFT, etc.)
    """
    if not DATAREADER_AVAILABLE:
        return None
    try:
        df = pdr.get_data_stooq(ticker, start=START_DATE, end=END_DATE)
        if df.empty:
            return None
        # stooq returns newest-first — reverse to chronological
        df = df.sort_index()
        df.columns = [c.lower() for c in df.columns]
        return df
    except Exception as e:
        log.debug(f"  stooq failed for {ticker}: {e}")
        return None


# ─── YFINANCE FETCH (fallback) ────────────────────────────────────────────────

def _fetch_via_yfinance(ticker: str) -> pd.DataFrame | None:
    """
    Fallback to yfinance if stooq returns nothing.
    Only used for tickers stooq doesn't cover.
    """
    try:
        df = yf.download(
            ticker,
            start=START_DATE,
            end=END_DATE,
            auto_adjust=True,
            progress=False,
        )
        if df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [c.lower() for c in df.columns]
        return df
    except Exception as e:
        log.debug(f"  yfinance fallback failed for {ticker}: {e}")
        return None


# ─── PROCESS AND SAVE ─────────────────────────────────────────────────────────

def _process_and_save(df: pd.DataFrame, ticker: str, source: str) -> dict:
    """Add derived columns and save CSV."""
    try:
        df = df.copy()
        df.index.name = "date"

        # Ensure required columns exist
        required = ["open", "high", "low", "close"]
        missing  = [c for c in required if c not in df.columns]
        if missing:
            return {"rows": 0, "ok": False, "reason": f"missing columns: {missing}"}

        df["returns"]     = df["close"].pct_change()
        df["log_returns"] = df["returns"].apply(
            lambda r: float("nan") if pd.isna(r) else math.log(1 + r)
        )
        df["range_pct"] = (df["high"] - df["low"]) / df["close"]
        df["ticker"]    = ticker
        df["cap_tier"]  = TICKER_CAP_MAP[ticker]
        df["source"]    = source

        tier     = TICKER_CAP_MAP[ticker]
        out_path = RAW_DIRS[tier] / f"{ticker}.csv"
        RAW_DIRS[tier].mkdir(parents=True, exist_ok=True)
        df.to_csv(out_path)

        return {"rows": len(df), "ok": True, "reason": None, "source": source}
    except Exception as e:
        return {"rows": 0, "ok": False, "reason": str(e)}


# ─── FETCH ONE TICKER ─────────────────────────────────────────────────────────

def _fetch_one(ticker: str) -> dict:
    """Try stooq first, then yfinance as fallback."""

    # Try stooq first
    df = _fetch_via_stooq(ticker)
    if df is not None and not df.empty:
        return _process_and_save(df, ticker, source="stooq")

    log.debug(f"  stooq empty for {ticker}, trying yfinance...")

    # Fallback to yfinance
    df = _fetch_via_yfinance(ticker)
    if df is not None and not df.empty:
        return _process_and_save(df, ticker, source="yfinance")

    return {"rows": 0, "ok": False, "reason": "empty_from_all_sources"}


# ─── MAIN FETCH ENTRY POINT ───────────────────────────────────────────────────

def fetch_all_tickers(force: bool = False) -> dict:
    """
    Fetch all 100 tickers. Skips tickers with existing CSVs unless force=True.
    Saves after every ticker so crashes lose nothing.
    """
    if not DATAREADER_AVAILABLE:
        log.error("pandas_datareader not installed. Run: pip install pandas-datareader")
        raise ImportError("pandas_datareader required. Run: pip install pandas-datareader")

    manifest = load_manifest()

    if already_fetched_today(manifest) and not force:
        log.info("Fetched today already -- checking for any missing tickers...")

    status     = manifest.get("status", {})
    need_fetch = []

    for ticker in ALL_TICKERS:
        tier     = TICKER_CAP_MAP[ticker]
        csv_path = RAW_DIRS[tier] / f"{ticker}.csv"
        if not force and csv_path.exists():
            rows = len(pd.read_csv(csv_path))
            if rows > 50:
                log.info(f"  SKIP {ticker} -- cached ({rows} rows)")
                status[ticker] = {"rows": rows, "ok": True, "reason": "cached",
                                  "fetched_at": str(datetime.now())}
                continue
        need_fetch.append(ticker)

    if not need_fetch:
        log.info("All 100 tickers already cached.")
        manifest.update({"last_fetched": str(date.today()),
                         "tickers_fetched": len(ALL_TICKERS), "status": status})
        save_manifest(manifest)
        return status

    total   = len(need_fetch)
    est_min = max(1, (total * DELAY_BETWEEN_TICKERS) // 60)
    log.info(f"Fetching {total} tickers via stooq (no rate limits)...")
    log.info(f"Date range: {START_DATE.date()} to {END_DATE.date()}")
    log.info(f"Estimated time: ~{est_min} minutes")

    ok_count   = 0
    fail_count = 0

    for i, ticker in enumerate(need_fetch, 1):
        log.info(f"[{i:03d}/{total}] {ticker}...")
        result = _fetch_one(ticker)

        if result["ok"]:
            src = result.get("source", "?")
            log.info(f"  OK   {ticker} -- {result['rows']} rows [{src}]")
            ok_count += 1
        else:
            log.warning(f"  FAIL {ticker} -- {result['reason']}")
            fail_count += 1

        status[ticker] = {**result, "fetched_at": str(datetime.now())}
        manifest.update({
            "last_fetched":    str(date.today()),
            "tickers_fetched": ok_count,
            "status":          status,
        })
        save_manifest(manifest)

        if i < total:
            time.sleep(DELAY_BETWEEN_TICKERS)

    log.info(f"\nFetch complete: {ok_count} OK, {fail_count} failed")
    failed = [t for t, v in status.items() if not v.get("ok")]
    if failed:
        log.warning(f"Failed tickers: {failed}")

    return status


# ─── LOAD A SINGLE TICKER CSV ─────────────────────────────────────────────────

def load_ticker_csv(ticker: str) -> pd.DataFrame | None:
    tier     = TICKER_CAP_MAP[ticker]
    csv_path = RAW_DIRS[tier] / f"{ticker}.csv"
    if not csv_path.exists():
        log.warning(f"No CSV for {ticker}")
        return None
    return pd.read_csv(csv_path, index_col="date", parse_dates=True)


# ─── NEWSAPI HEADLINES ────────────────────────────────────────────────────────

def fetch_news_headlines(tickers=None, max_articles=300):
    if not NEWS_API_KEY:
        log.warning("NEWS_API_KEY not set -- skipping.")
        return pd.DataFrame()

    out_path     = STOCK_DATA_DIR / "news_headlines.csv"
    tickers      = tickers or (LARGE_CAP[:5] + MID_CAP[:5] + SMALL_CAP[:5])
    all_articles = []

    for ticker in tickers:
        params = {
            "q": ticker, "language": "en", "sortBy": "publishedAt",
            "pageSize": min(NEWSAPI_PAGE_SIZE, max_articles // len(tickers)),
            "apiKey": NEWS_API_KEY,
        }
        try:
            resp = requests.get(NEWSAPI_BASE_URL, params=params, timeout=10)
            resp.raise_for_status()
            for a in resp.json().get("articles", []):
                text = ((a.get("title") or "") + " " + (a.get("description") or "")).strip()
                if text:
                    all_articles.append({
                        "headline":     text,
                        "ticker":       ticker,
                        "source":       a.get("source", {}).get("name", ""),
                        "published_at": a.get("publishedAt", ""),
                    })
            time.sleep(0.5)
        except Exception as e:
            log.error(f"  NewsAPI failed for {ticker}: {e}")

    if not all_articles:
        return pd.DataFrame()

    df = pd.DataFrame(all_articles).drop_duplicates(subset=["headline"])
    df.to_csv(out_path, index=False)
    log.info(f"Saved {len(df)} headlines -> {out_path.name}")
    return df


# ─── HEALTH CHECK ─────────────────────────────────────────────────────────────

def check_data_health() -> dict:
    summary = {}
    for ticker in ALL_TICKERS:
        tier     = TICKER_CAP_MAP[ticker]
        csv_path = RAW_DIRS[tier] / f"{ticker}.csv"
        exists   = csv_path.exists()
        rows     = len(pd.read_csv(csv_path)) if exists else 0
        summary[ticker] = {"exists": exists, "rows": rows}

    ok     = sum(1 for v in summary.values() if v["exists"] and v["rows"] > 100)
    broken = [t for t, v in summary.items() if not v["exists"] or v["rows"] <= 100]
    log.info(f"Health check: {ok}/100 tickers OK")
    if broken:
        log.warning(f"Broken/missing: {broken}")
    return summary


if __name__ == "__main__":
    fetch_all_tickers(force=False)
    check_data_health()