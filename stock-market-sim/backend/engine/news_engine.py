"""
news_engine.py
─────────────────────────────────────────────────────────────────────────────
Generates AI-powered financial news headlines using Google Gemini API.
Falls back to templated headlines if Gemini API is unavailable.
Called by: main.py (background news loop)
─────────────────────────────────────────────────────────────────────────────
"""

import random
import logging
import json
import httpx
from datetime import datetime

from config import (
    ALL_TICKERS,
    TICKER_CAP_MAP,
    CAP_PROFILES,
    NEWS_WEIGHTS,
    GEMINI_API_KEY,
)
from engine.price_engine import MarketState, apply_sentiment_shock
from database.db import log_news

log = logging.getLogger(__name__)

GEMINI_MODEL   = "gemini-1.5-flash"
GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)


def pick_news_ticker() -> str:
    return random.choices(ALL_TICKERS, weights=NEWS_WEIGHTS, k=1)[0]


def _build_prompt(ticker: str, market: MarketState) -> str:
    state     = market.get(ticker)
    price_str = f"${state.price:.2f}" if state else "unknown"
    tier      = TICKER_CAP_MAP[ticker]
    tier_context = {
        "large": "blue-chip large-cap stock",
        "mid":   "mid-cap growth stock",
        "small": "speculative small-cap stock",
    }[tier]
    return (
        f"You are a financial news wire. Generate ONE short financial headline "
        f"about {ticker} ({tier_context}), currently trading at {price_str}. "
        f"The headline should be realistic, specific, and max 15 words. "
        f"Also return sentiment impact and a delta between -0.6 and +0.6. "
        f"Respond ONLY with valid JSON, no markdown:\n"
        f'{{"headline":"...","impact":"bullish"|"bearish"|"neutral","delta":0.0}}'
    )


async def _call_gemini(prompt: str) -> dict | None:
    if not GEMINI_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                GEMINI_API_URL,
                params={"key": GEMINI_API_KEY},
                headers={"content-type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"maxOutputTokens": 150, "temperature": 0.9},
                },
            )
            if not resp.is_success:
                log.warning(f"Gemini API {resp.status_code}: {resp.text[:200]}")
                return None

            data = resp.json()
            text = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
                .strip()
            )
            text = text.replace("```json", "").replace("```", "").strip()
            parsed = json.loads(text)
            if all(k in parsed for k in ("headline", "impact", "delta")):
                return parsed
    except Exception as e:
        log.warning(f"Gemini API call failed: {e}")
    return None


_BULLISH_TEMPLATES = [
    "{ticker} surges on strong earnings beat expectations",
    "Analysts upgrade {ticker} citing improving fundamentals",
    "{ticker} announces new partnership driving growth outlook",
    "Institutional investors increase {ticker} holdings significantly",
    "{ticker} reports record revenue in latest quarter",
]
_BEARISH_TEMPLATES = [
    "{ticker} misses earnings estimates amid rising costs",
    "Analysts downgrade {ticker} on weakening demand signals",
    "{ticker} faces regulatory scrutiny over business practices",
    "Short sellers increase bets against {ticker}",
    "{ticker} cuts guidance citing macroeconomic headwinds",
]
_NEUTRAL_TEMPLATES = [
    "{ticker} holds investor day, reaffirms annual targets",
    "{ticker} announces executive leadership transition",
    "{ticker} completes previously announced share buyback",
    "Market watches {ticker} ahead of upcoming product launch",
]

def _fallback_headline(ticker: str) -> dict:
    roll = random.random()
    if roll < 0.45:
        return {"headline": random.choice(_BULLISH_TEMPLATES).format(ticker=ticker),
                "impact": "bullish", "delta": round(random.uniform(0.1, 0.45), 2)}
    elif roll < 0.85:
        return {"headline": random.choice(_BEARISH_TEMPLATES).format(ticker=ticker),
                "impact": "bearish", "delta": round(random.uniform(-0.45, -0.1), 2)}
    else:
        return {"headline": random.choice(_NEUTRAL_TEMPLATES).format(ticker=ticker),
                "impact": "neutral", "delta": round(random.uniform(-0.05, 0.05), 2)}


async def generate_news_event(market: MarketState, db) -> dict | None:
    ticker = pick_news_ticker()
    prompt = _build_prompt(ticker, market)

    result = await _call_gemini(prompt)
    source = "gemini"

    if result is None:
        result = _fallback_headline(ticker)
        source = "fallback"

    headline = result.get("headline", "Market activity detected")
    impact   = result.get("impact", "neutral")
    delta    = max(-0.6, min(0.6, float(result.get("delta", 0.0))))

    apply_sentiment_shock(market, ticker, delta)
    await log_news(db, ticker, headline, impact, delta)

    event = {
        "ticker":    ticker,
        "headline":  headline,
        "impact":    impact,
        "delta":     delta,
        "cap_tier":  TICKER_CAP_MAP[ticker],
        "source":    source,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    }
    log.info(f"NEWS [{source}] {ticker} ({impact}) delta={delta:+.2f} | {headline}")
    return event
