# MarketSim

A full-stack virtual stock market simulator running 100 tickers in real time. Prices are driven by GARCH volatility models fitted on real historical data, sentiment shocks from an AI news engine, and order flow imbalance from user trades. The result is a market that behaves like a real exchange — not a random walk.

Live at: https://stock-market-sim-mu.vercel.app

---

## What It Is

MarketSim is a self-contained trading simulation platform. Users register an account, receive $100,000 in virtual cash, and trade across 100 US equities — large, mid, and small cap — in a market that never stops ticking. Every 2 seconds, all 100 prices update simultaneously. Every 2 minutes, an AI-generated news headline hits one ticker and moves the market.

The simulation is not a toy. Prices are anchored to real historical closes pulled from Stooq. Per-ticker volatility is estimated using GARCH(1,1) models fitted on actual return series. The price engine applies mean reversion, sentiment drift, and order imbalance impact in each tick — the same mechanics used in academic market microstructure models.

---

## Use Cases

**Learning to trade.** The simulator is a risk-free environment for understanding how markets work. Users can experiment with position sizing, timing, and portfolio construction without any financial exposure. The bid-ask spread, market impact of large orders, and sentiment-driven volatility are all modeled explicitly — so the lessons transfer.

**Understanding market microstructure.** The spread between bid and ask widens during volatility spikes. Small-cap stocks are thinner, more volatile, and more sensitive to news than large caps. Order flow from user trades moves prices through the imbalance mechanism. These are the real dynamics of equity markets, rendered visible.

**Portfolio management practice.** The portfolio tab tracks holdings, average cost, unrealised P&L, and return percentage per position in real time. The leaderboard ranks all users by total portfolio value. Users can observe how diversification, sector concentration, and trade timing affect outcomes over simulated time.

**Demonstrating AI in finance.** The news engine calls the Gemini API to generate contextually appropriate financial headlines — bullish, bearish, or neutral — for a randomly selected ticker every 2 minutes. Each headline carries a sentiment delta that propagates through the price engine as a decay-weighted shock. The source (AI or fallback template) is tracked per event.

**Quantitative finance education.** The backend is built on real quantitative foundations: GARCH volatility, mean reversion toward fundamental anchors, sentiment as a drift term, and liquidity-adjusted price impact. The Jupyter notebooks walk through EDA, volatility calibration, and strategy backtesting against the simulation.

---

## Features

**Market engine**
- 100 US equity tickers across large, mid, and small cap tiers
- Prices update every 2 seconds using per-ticker GARCH(1,1) volatility
- Mean reversion toward real historical anchor prices
- Order imbalance impact: user buy/sell flow moves prices
- Sentiment decay: news shocks fade over subsequent ticks
- Bid-ask spread that widens with volatility and narrows on liquid stocks

**Trading**
- Market orders executed at ask (buy) or bid (sell)
- Portfolio tracking with average cost basis and unrealised P&L
- Full trade history per user
- Leaderboard ranked by total portfolio value across all users

**AI news engine**
- Gemini-powered headlines targeted at individual tickers
- Sentiment classification (bullish / bearish / neutral) with magnitude
- Automatic fallback to templated headlines when API is unavailable
- News feed visible in real time with cap tier and sentiment delta

**Charts**
- Candlestick chart per ticker built from live tick stream
- OHLC candles with wick rendering, colour-coded by direction
- Live price line with current price label
- Hover tooltip showing exact open, high, low, close values

**Accounts**
- Username and password authentication
- SHA-256 password hashing
- Persistent accounts across sessions via PostgreSQL
- New username creates account; existing username requires correct password

---

## Architecture

```
Frontend          Backend           Data
---------         -------           ----
React + Vite      FastAPI           Supabase (PostgreSQL)
Vercel            Render            Real OHLCV from Stooq
                  Python 3.11       GARCH params (fitted offline)
```

The frontend polls the backend every 2.5 seconds for prices and portfolio data. News events are fetched on page load and after each news interval. All state is server-side — refreshing the page or opening a second tab shows the same live market.

The backend runs two background loops: a tick loop that fires every 2 seconds and a news loop that fires every 2 minutes. Both write to PostgreSQL. The price engine runs entirely in memory for speed; price history is persisted to the database asynchronously after each tick.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React, Vite, Recharts |
| Backend | FastAPI, Python 3.11, asyncpg |
| Database | PostgreSQL via Supabase |
| Hosting | Vercel (frontend), Render (backend) |
| Volatility | GARCH(1,1) via arch library |
| Sentiment | VADER + Gemini API |
| Data | Stooq historical OHLCV |

---

## Running Locally

**Backend**
```bash
cd stock-market-sim/backend
pip install -r requirements.txt
# Create a .env file with DATABASE_URL and GEMINI_API_KEY
python -m uvicorn main:app --reload --port 8000
```

**Frontend**
```bash
cd stock-market-sim/frontend
npm install
# Create a .env file with VITE_API_URL=http://localhost:8000
npm run dev
```

The backend expects `stock_data/anchor_prices.json` and `stock_data/volatility_params.json` to exist. These are generated by running the data pipeline notebooks or the fetcher and price model scripts directly.

---

## Notebooks

Four Jupyter notebooks are included in `backend/notebooks/`:

`01_market_analysis.ipynb` — Exploratory analysis of the 100-ticker universe. Return distributions, volatility profiles, correlation heatmap, GARCH alpha/beta scatter.

`02_sentiment_training.ipynb` — VADER scoring on news templates, label distribution, FinBERT fine-tuning block (disabled by default).

`03_simulation_backtest.ipynb` — Simulation vs real price overlay, volatility calibration, three strategy backtests (momentum, mean reversion, news-driven), sentiment shock response analysis.

`04_rl_market_maker.ipynb` — PPO reinforcement learning agent for market making. Full training pipeline with evaluation against passive baseline. Model saved to `models/rl_mm_policy.pt` for live deployment (not yet active).

---

## Project Structure

```
stock-market-sim/
├── backend/
│   ├── main.py                  API server and background loops
│   ├── config.py                Ticker universe, cap tiers, engine params
│   ├── requirements.txt
│   ├── data/
│   │   ├── fetcher.py           Stooq data download
│   │   └── price_model.py       GARCH fitting, anchor price computation
│   ├── database/
│   │   ├── db.py                asyncpg connection pool and all DB helpers
│   │   └── schema.sql           PostgreSQL schema
│   ├── engine/
│   │   ├── price_engine.py      Core tick engine, GARCH price formula
│   │   ├── market_maker.py      Passive liquidity provider
│   │   ├── order_handler.py     Trade execution and pending order queue
│   │   ├── news_engine.py       Gemini API news generation
│   │   ├── rl_environment.py    PPO training environment
│   │   └── rl_agent.py          PPO trainer and inference wrapper
│   ├── stock_data/              Parquet files, GARCH params, anchor prices
│   └── notebooks/               Analysis and training notebooks
└── frontend/
    └── src/
        ├── App.jsx              Main layout and polling logic
        ├── api/client.js        All backend API calls
        └── components/
            ├── StockGrid.jsx    Ticker list with sparklines
            ├── TradePanel.jsx   Candlestick chart and order form
            ├── Portfolio.jsx    Holdings and P&L view
            ├── NewsFeed.jsx     Live AI news feed
            ├── Leaderboard.jsx  User rankings
            ├── TickerTape.jsx   Scrolling price tape
            └── Login.jsx        Auth screen
```

---

## Deployment

The application is deployed across three free-tier services:

- **Vercel** serves the React frontend with `VITE_API_URL` pointing to the backend
- **Render** runs the FastAPI backend with `DATABASE_URL` and `GEMINI_API_KEY` set as environment variables
- **Supabase** hosts the PostgreSQL database with SSL required
