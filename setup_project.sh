#!/bin/bash

# ─── STOCK MARKET SIM — PROJECT SCAFFOLD ──────────────────────────────────────
PROJECT="stock-market-sim"

echo "Creating project structure for $PROJECT..."

# ─── ROOT ─────────────────────────────────────────────────────────────────────
mkdir -p $PROJECT
touch $PROJECT/README.md

# ─── BACKEND ──────────────────────────────────────────────────────────────────
mkdir -p $PROJECT/backend

touch $PROJECT/backend/main.py
touch $PROJECT/backend/config.py
touch $PROJECT/backend/requirements.txt

# ─── ENGINE ───────────────────────────────────────────────────────────────────
mkdir -p $PROJECT/backend/engine

touch $PROJECT/backend/engine/__init__.py
touch $PROJECT/backend/engine/price_engine.py
touch $PROJECT/backend/engine/market_maker.py
touch $PROJECT/backend/engine/news_engine.py
touch $PROJECT/backend/engine/order_handler.py

# ─── DATA ─────────────────────────────────────────────────────────────────────
mkdir -p $PROJECT/backend/data

touch $PROJECT/backend/data/__init__.py
touch $PROJECT/backend/data/fetcher.py
touch $PROJECT/backend/data/sentiment_model.py
touch $PROJECT/backend/data/price_model.py
touch $PROJECT/backend/data/initializer.py

# ─── STOCK DATA ───────────────────────────────────────────────────────────────
mkdir -p $PROJECT/backend/stock_data/raw/large_cap
mkdir -p $PROJECT/backend/stock_data/raw/mid_cap
mkdir -p $PROJECT/backend/stock_data/raw/small_cap
mkdir -p $PROJECT/backend/stock_data/processed

touch $PROJECT/backend/stock_data/anchor_prices.json
touch $PROJECT/backend/stock_data/volatility_params.json
touch $PROJECT/backend/stock_data/data_manifest.json

# ─── MODELS ───────────────────────────────────────────────────────────────────
mkdir -p $PROJECT/backend/models/finbert_finetuned

touch $PROJECT/backend/models/.gitkeep
touch $PROJECT/backend/models/finbert_finetuned/.gitkeep

# ─── DATABASE ─────────────────────────────────────────────────────────────────
mkdir -p $PROJECT/backend/database

touch $PROJECT/backend/database/__init__.py
touch $PROJECT/backend/database/db.py
touch $PROJECT/backend/database/schema.sql

# ─── FRONTEND ─────────────────────────────────────────────────────────────────
mkdir -p $PROJECT/frontend/public
mkdir -p $PROJECT/frontend/src/components
mkdir -p $PROJECT/frontend/src/api

touch $PROJECT/frontend/public/index.html
touch $PROJECT/frontend/package.json

touch $PROJECT/frontend/src/App.jsx
touch $PROJECT/frontend/src/api/client.js

touch $PROJECT/frontend/src/components/Dashboard.jsx
touch $PROJECT/frontend/src/components/StockChart.jsx
touch $PROJECT/frontend/src/components/TradePanel.jsx
touch $PROJECT/frontend/src/components/Portfolio.jsx
touch $PROJECT/frontend/src/components/NewsFeed.jsx
touch $PROJECT/frontend/src/components/Leaderboard.jsx

# ─── NOTEBOOKS ────────────────────────────────────────────────────────────────
mkdir -p $PROJECT/notebooks

touch $PROJECT/notebooks/01_data_exploration.ipynb
touch $PROJECT/notebooks/02_sentiment_training.ipynb
touch $PROJECT/notebooks/03_price_model_tuning.ipynb

# ─── DONE ─────────────────────────────────────────────────────────────────────
echo ""
echo "✅ Done! Project structure created:"
echo ""
find $PROJECT -not -path "*/\.*" | sort | awk '
{
  n = split($0, parts, "/")
  indent = ""
  for (i = 2; i < n; i++) indent = indent "│   "
  if (n > 1) {
    prefix = (n == 2) ? "├── " : "├── "
    print indent prefix parts[n]
  } else {
    print parts[1] "/"
  }
}
'
echo ""
echo "Next step: cd $PROJECT && open backend/requirements.txt"
