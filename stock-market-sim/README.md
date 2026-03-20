# Stock Market Sim

An AI-driven virtual stock market simulation where users trade 100 real-world companies using virtual money. Built for educational and portfolio demonstration purposes.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | Python, FastAPI |
| Simulation Engine | NumPy, Pandas, arch (GARCH) |
| Sentiment Model | VADER, FinBERT (HuggingFace) |
| Database | SQLite |
| Frontend | React.js, Recharts, Axios |
| Data Source | yfinance (free), NewsAPI (free tier) |

---

## Project Structure

```
stock-market-sim/
├── backend/
│   ├── main.py                        # FastAPI entry point + routes
│   ├── config.py                      # Tickers, cap profiles, constants
│   ├── engine/
│   │   ├── price_engine.py            # Core price simulation
│   │   ├── market_maker.py            # Bid/ask spread logic
│   │   ├── news_engine.py             # AI news generation
│   │   └── order_handler.py           # Trade execution
│   ├── data/
│   │   ├── fetcher.py                 # yfinance data download
│   │   ├── price_model.py             # GARCH volatility fitting
│   │   ├── sentiment_model.py         # VADER + FinBERT sentiment
│   │   └── initializer.py             # One-time data setup script
│   ├── stock_data/
│   │   ├── raw/
│   │   │   ├── large_cap/             # One CSV per large cap ticker
│   │   │   ├── mid_cap/               # One CSV per mid cap ticker
│   │   │   └── small_cap/             # One CSV per small cap ticker
│   │   ├── processed/                 # Feature-engineered parquet files
│   │   ├── anchor_prices.json         # Simulation starting prices
│   │   ├── volatility_params.json     # GARCH sigma per ticker
│   │   └── data_manifest.json         # Fetch log and status
│   ├── models/
│   │   └── finbert_finetuned/         # Saved FinBERT weights
│   └── database/
│       ├── db.py                      # SQLite connection + helpers
│       └── schema.sql                 # Table definitions
└── frontend/
    └── src/
        └── components/
            ├── Dashboard.jsx
            ├── StockChart.jsx
            ├── TradePanel.jsx
            ├── Portfolio.jsx
            ├── NewsFeed.jsx
            └── Leaderboard.jsx
```

---

## Quickstart

### 1. Install backend dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 2. Add your NewsAPI key
```bash
cp .env.example .env
# Edit .env and add your free NewsAPI key from https://newsapi.org
```

### 3. Run the data initializer (run once)
```bash
cd backend
python -m data.initializer
```
This fetches all 100 tickers from yfinance, fits GARCH volatility models,
and saves anchor prices. Takes ~2-3 minutes on first run.

### 4. Start the backend server
```bash
uvicorn main:app --reload --port 8000
```

### 5. Start the frontend
```bash
cd frontend
npm install
npm start
```

Frontend runs at `http://localhost:3000`, backend at `http://localhost:8000`.

---

## Stock Universe (100 Tickers)

| Tier | Count | Volatility | Bid-Ask Spread |
|---|---|---|---|
| Large Cap | 40 | Low | 0.1% |
| Mid Cap | 35 | Medium | 0.3% |
| Small Cap | 25 | High | 1.0% |

---

## Simulation Model

Price update formula applied every tick:

```
P_new = P + α·imbalance + β·sentiment + σ·noise + γ·(anchor − P)

Where:
  α  = liquidity sensitivity (how much user trades move price)
  β  = sentiment sensitivity (how much news moves price)
  σ  = volatility (GARCH-fitted per ticker, scaled by cap tier)
  γ  = mean reversion strength (pulls price back toward anchor)
```

---

## AI Components

| Component | Model | Source |
|---|---|---|
| Sentiment scoring | VADER | Local, rule-based, free |
| News headline generation | Claude API | Anthropic |
| Volatility estimation | GARCH(1,1) | Fitted on yfinance data |
| Optional fine-tune | FinBERT | HuggingFace, free |

---

## Free Tier API Usage

| API | Used For | Limit |
|---|---|---|
| yfinance | Historical OHLCV data | Unlimited |
| NewsAPI | Headlines for sentiment training | 100 req/day |
| HuggingFace | FinBERT model weights | Free download |

---

## Future Enhancements

- Reinforcement learning market maker
- Multi-user real-time trading via WebSockets
- Advanced order book depth simulation
- Analytics dashboard and leaderboards
- LLM-powered realistic financial news generation