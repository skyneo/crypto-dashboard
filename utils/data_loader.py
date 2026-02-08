# utils/data_loader.py
"""
Centralized functions to load project data safely and consistently.
"""

import pandas as pd
from pathlib import Path
from typing import Optional, Dict, List
import datetime
import pytz
from config import (
    SYMBOLS_FILTERED_CSV,
    ALERTS_FILE,
    DASHBOARD_STATE_PARQUET,
    TIMEZONE,
)


def load_filtered_symbols() -> pd.DataFrame:
    """Load the filtered symbols list (main source of truth for which tokens we track)."""
    if not SYMBOLS_FILTERED_CSV.exists():
        raise FileNotFoundError(f"Filtered symbols file not found: {SYMBOLS_FILTERED_CSV}")
    
    df = pd.read_csv(SYMBOLS_FILTERED_CSV)
    expected_cols = {"symbol", "full_symbol", "volume", "price", "price_change"}
    if not expected_cols.issubset(df.columns):
        raise ValueError(f"Missing expected columns in {SYMBOLS_FILTERED_CSV}. Found: {df.columns}")
    
    # Basic cleaning
    df["full_symbol"] = df["full_symbol"].str.upper()
    df["symbol"] = df["symbol"].str.upper()
    return df.sort_values("volume", ascending=False).reset_index(drop=True)


def load_token_parquet(
    token: str,
    data_dir: Path = None,
    required_columns: Optional[List[str]] = None
) -> pd.DataFrame:
    """Load the 15-min kline Parquet for a specific token."""
    if data_dir is None:
        from config import DATA_DIR
        data_dir = DATA_DIR
    
    parquet_path = data_dir / f"{token.upper()}.parquet"
    if not parquet_path.exists():
        raise FileNotFoundError(f"No data found for {token}: {parquet_path}")
    
    df = pd.read_parquet(parquet_path, engine="pyarrow")
    
    # Ensure minimal required structure
    required = {"open_time", "open", "high", "low", "close", "volume"}
    if required_columns:
        required.update(required_columns)
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns in {token} data: {missing}")
    
    # Convert timestamp to datetime (UTC)
    df["datetime"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.set_index("datetime").sort_index()
    
    return df


def load_alerts() -> pd.DataFrame:
    """Parse alerts.txt into a usable DataFrame."""
    if not ALERTS_FILE.exists():
        return pd.DataFrame(columns=["timestamp_local", "timestamp_utc", "token", "message"])
    
    lines = []
    with open(ALERTS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                # Format: 2026-02-04 18:29:23 (2026-02-04 10:15:00 UTC) TOKEN - message
                parts = line.split(" (", 1)
                local_ts_str = parts[0].strip()
                rest = parts[1].rstrip(")")
                utc_ts_str, token_msg = rest.split(") ", 1)
                token, message = token_msg.split(" - ", 1)
                
                local_dt = datetime.datetime.strptime(local_ts_str, "%Y-%m-%d %H:%M:%S")
                utc_dt = datetime.datetime.strptime(utc_ts_str, "%Y-%m-%d %H:%M:%S UTC")
                
                lines.append({
                    "timestamp_local": local_dt,
                    "timestamp_utc": utc_dt,
                    "token": token.strip(),
                    "message": message.strip(),
                    "raw_line": line
                })
            except Exception:
                # Skip malformed lines
                continue
    
    df = pd.DataFrame(lines)
    if not df.empty:
        df = df.sort_values("timestamp_local", ascending=False).reset_index(drop=True)
    return df


def load_dashboard_state() -> Optional[pd.DataFrame]:
    """Load pre-computed dashboard state if it exists."""
    if DASHBOARD_STATE_PARQUET.exists():
        return pd.read_parquet(DASHBOARD_STATE_PARQUET)
    return None


def get_local_now() -> datetime.datetime:
    """Current time in project timezone."""
    return datetime.datetime.now(pytz.timezone(TIMEZONE))


def get_utc_now() -> datetime.datetime:
    return datetime.datetime.now(pytz.UTC)
