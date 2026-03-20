"""
sentiment_model.py
─────────────────────────────────────────────────────────────────────────────
Sentiment scoring for financial text using VADER (baseline, always available)
and optionally FinBERT (HuggingFace, loaded if model exists).

Outputs a score in [-1, +1]:
  +1 = strongly bullish
   0 = neutral
  -1 = strongly bearish

Used by:
  - news_engine.py to score external headlines
  - notebooks/02_sentiment_training.ipynb for FinBERT fine-tuning

Loads lazily — models are only imported when first needed.
─────────────────────────────────────────────────────────────────────────────
"""

import logging
from pathlib import Path
from functools import lru_cache

from config import MODELS_DIR

log = logging.getLogger(__name__)

FINBERT_DIR = MODELS_DIR / "finbert_finetuned"


# ─── VADER (baseline, always available) ──────────────────────────────────────

@lru_cache(maxsize=1)
def _load_vader():
    """Load VADER SentimentIntensityAnalyzer. Cached after first call."""
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        analyzer = SentimentIntensityAnalyzer()
        log.info("VADER loaded")
        return analyzer
    except ImportError:
        log.warning("vaderSentiment not installed — pip install vaderSentiment")
        return None


def score_vader(text: str) -> float:
    """
    Score text using VADER. Returns compound score in [-1, +1].
    Falls back to 0.0 if VADER is unavailable.
    """
    analyzer = _load_vader()
    if analyzer is None:
        return 0.0
    scores = analyzer.polarity_scores(text)
    return round(scores["compound"], 4)


# ─── FINBERT (optional, higher accuracy) ──────────────────────────────────────

@lru_cache(maxsize=1)
def _load_finbert():
    """
    Load FinBERT from HuggingFace (ProsusAI/finbert).
    Uses fine-tuned local weights if available in models/finbert_finetuned/.
    Returns (tokenizer, model) or (None, None) if unavailable.
    """
    try:
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        import torch

        # Use local fine-tuned weights if they exist, else download from HF
        model_path = str(FINBERT_DIR) if (FINBERT_DIR / "config.json").exists() \
                     else "ProsusAI/finbert"

        log.info(f"Loading FinBERT from: {model_path}")
        tokenizer = AutoTokenizer.from_pretrained(model_path)
        model     = AutoModelForSequenceClassification.from_pretrained(model_path)
        model.eval()
        log.info("FinBERT loaded")
        return tokenizer, model

    except Exception as e:
        log.warning(f"FinBERT not available: {e}")
        return None, None


def score_finbert(text: str) -> float:
    """
    Score text using FinBERT.
    Returns score in [-1, +1]:
      positive label ->  score
      negative label -> -score
      neutral label  ->  0

    Falls back to VADER score if FinBERT unavailable.
    """
    tokenizer, model = _load_finbert()
    if tokenizer is None or model is None:
        return score_vader(text)

    try:
        import torch

        inputs  = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        with torch.no_grad():
            logits = model(**inputs).logits
        probs   = torch.softmax(logits, dim=-1).squeeze().tolist()

        # FinBERT label order: positive=0, negative=1, neutral=2
        # (verify with model.config.id2label if different)
        label_map = {0: 1.0, 1: -1.0, 2: 0.0}
        pred_idx  = int(torch.argmax(logits).item())
        direction = label_map.get(pred_idx, 0.0)

        # Scale by confidence (max prob)
        confidence = max(probs)
        score      = round(direction * confidence, 4)
        return score

    except Exception as e:
        log.warning(f"FinBERT scoring failed: {e} — using VADER")
        return score_vader(text)


# ─── UNIFIED SCORER ───────────────────────────────────────────────────────────

def score_text(text: str, prefer_finbert: bool = False) -> float:
    """
    Score financial text sentiment.

    Args:
      text:           The headline or text to score
      prefer_finbert: Use FinBERT if available (slower, more accurate)
                      Default: False (use VADER for speed)

    Returns float in [-1, +1].
    """
    if not text or not text.strip():
        return 0.0

    if prefer_finbert:
        return score_finbert(text)
    return score_vader(text)


def label_sentiment(score: float) -> str:
    """Convert numeric score to human-readable label."""
    if score >= 0.15:
        return "bullish"
    elif score <= -0.15:
        return "bearish"
    return "neutral"


# ─── BULK SCORING (for training data) ────────────────────────────────────────

def score_dataframe(df, text_col: str = "headline", prefer_finbert: bool = False):
    """
    Add sentiment_score and sentiment_label columns to a DataFrame.
    Used in notebooks/02_sentiment_training.ipynb.
    """
    import pandas as pd
    df = df.copy()
    df["sentiment_score"] = df[text_col].apply(
        lambda t: score_text(str(t), prefer_finbert=prefer_finbert)
    )
    df["sentiment_label"] = df["sentiment_score"].apply(label_sentiment)
    return df


# ─── STANDALONE TEST ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    samples = [
        "Apple reports record quarterly earnings, beats all estimates",
        "Tesla faces recall of 200,000 vehicles over safety concerns",
        "Fed holds interest rates steady at next meeting",
        "NVDA surges on AI chip demand surge from data centers",
        "Biotech startup SAVA halts trial after adverse patient events",
    ]
    print("\n=== Sentiment Scores ===")
    for text in samples:
        score = score_text(text)
        label = label_sentiment(score)
        print(f"  [{label:8s} {score:+.3f}] {text}")