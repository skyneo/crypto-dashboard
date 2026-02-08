# config.py
"""
Central configuration for the crypto dashboard project.
All paths, thresholds, scoring weights, etc. live here.
"""

import os
from pathlib import Path
from datetime import timedelta

# ======================
#  Directory & File Paths
# ======================
# Try to find the project root by looking for known files
def find_project_root():
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "config.py").exists() or (current / "utils" / "data_loader.py").exists():
            return current
        current = current.parent
    # Fallback: use script's parent
    return Path(__file__).resolve().parent.parent

PROJECT_ROOT = find_project_root()
#PROJECT_ROOT = Path(__file__).parent.parent.resolve()   # assumes config.py is in project root

DATA_DIR = PROJECT_ROOT / "data"
DATA_STREAM_DIR = PROJECT_ROOT / "data_stream"
IMAGES_DIR = PROJECT_ROOT / "images"

# Existing files
SYMBOLS_ALL_CSV = DATA_DIR / "binance_300_symbols.csv"
SYMBOLS_FILTERED_CSV = DATA_DIR / "filtered_symbols.csv"
ALERTS_FILE = DATA_STREAM_DIR / "alerts.txt"
DASHBOARD_STATE_PARQUET = DATA_STREAM_DIR / "dashboard_state.parquet"

# ======================
#  Dashboard & UI Settings
# ======================
APP_TITLE = "Crypto Trade Opportunity Dashboard"
APP_ICON = "chart-with-upwards-trend"  # emoji or streamlit icon name

# Number of columns in main dashboard
MAIN_COLUMNS = 3
COLUMN_HEADERS = [
    "Setup / Accumulation Phase",
    "Entry / Breakout Phase",
    "Continuation / In-Trade Phase"
]

# How many tokens to show per column before "Show more"
TOKENS_PER_PAGE_PER_COLUMN = 12

# ======================
#  Scoring & Phase Thresholds
# ======================
# Profitability score (0-10)
PROFITABILITY_WEIGHTS = {
    "rr_ratio": 0.45,           # Reward:Risk
    "volume_surge": 0.25,
    "momentum": 0.20,
    "proximity_to_target": 0.10
}
MIN_PROFIT_SCORE_FOR_HIGHLIGHT = 6.5

# Market cleanliness score (0-10)
CLEANNESS_WEIGHTS = {
    "adx_strength": 0.40,       # ADX > 25 = strong trend
    "fractal_clarity": 0.30,    # few overlapping swings
    "bb_width_low": 0.20,       # consolidation = cleaner setup
    "volume_consistency": 0.10
}
MIN_CLEAN_SCORE_FOR_GOOD = 7.0

# Phase classification thresholds
PHASE_BREAKOUT_RECENCY_MINUTES = 180     # breakouts within last 3 hours → Entry phase
PHASE_TREND_STRENGTH_ADX = 25            # ADX above this = trending (Continuation likely)

# ======================
#  Charting Defaults
# ======================
DEFAULT_PLOT_DAYS = 30
CHART_HEIGHT = 650
CHART_WIDTH = 1000
DEFAULT_INDICATORS = ["SMA20", "EMA50", "Support/Resistance"]

# ======================
#  Authentication (basic for MVP)
# ======================
# For simple login – later can be replaced with proper auth (streamlit-authenticator, OAuth, etc.)
#MOVED TO streamlit-authenticator

# ======================
#  Other Constants
# ======================
TIMEZONE = "Asia/Singapore"           # your location
UTC_OFFSET = timedelta(hours=8)

# Binance API related (if fetching live in dashboard)
BINANCE_PUBLIC_API_BASE = "https://api.binance.com/api/v3"
REQUEST_TIMEOUT_SEC = 10
RATE_LIMIT_SLEEP = 0.4                # seconds between calls when batching

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(IMAGES_DIR, exist_ok=True)
