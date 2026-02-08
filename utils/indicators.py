# utils/indicators.py
"""
Pure pandas/numpy implementations of common technical indicators.
Avoids TA-Lib dependency for easier setup.
"""

import pandas as pd
import numpy as np
from typing import Tuple, Optional


def calculate_sma(series: pd.Series, period: int = 20) -> pd.Series:
    """Simple Moving Average"""
    return series.rolling(window=period).mean()


def calculate_ema(series: pd.Series, period: int = 20) -> pd.Series:
    """Exponential Moving Average"""
    return series.ewm(span=period, adjust=False).mean()


def calculate_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14
) -> pd.Series:
    """
    Average True Range (ATR) - pure pandas version
    """
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr


def calculate_adx(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14
) -> pd.Series:
    """
    Average Directional Index (ADX) - approximate pandas version
    (simplified; not identical to TA-Lib but close enough for scoring)
    """
    up = high - high.shift(1)
    down = low.shift(1) - low
    plus_dm = np.where((up > down) & (up > 0), up, 0)
    minus_dm = np.where((down > up) & (down > 0), down, 0)

    tr = calculate_atr(high, low, close, period)  # reuse ATR func
    atr = tr  # already smoothed

    plus_di = 100 * (pd.Series(plus_dm).rolling(window=period).mean() / atr)
    minus_di = 100 * (pd.Series(minus_dm).rolling(window=period).mean() / atr)

    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
    adx = dx.rolling(window=period).mean()
    return adx


def calculate_bollinger_width(
    close: pd.Series,
    period: int = 20,
    std_dev: float = 2.0
) -> pd.Series:
    """Bollinger Band width as % of middle band (measures consolidation)"""
    sma = calculate_sma(close, period)
    std = close.rolling(window=period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    width = (upper - lower) / sma * 100  # percentage width
    return width


def find_fractal_peaks_valleys(
    high: pd.Series,
    low: pd.Series,
    window: int = 5
) -> Tuple[pd.Series, pd.Series]:
    """
    Simple fractal detection: local max in high / local min in low
    Returns two series (boolean masks) for peaks and valleys
    """
    # Rolling max/min over window
    rolling_max = high.rolling(window=window, center=True).max()
    rolling_min = low.rolling(window=window, center=True).min()

    peaks = high == rolling_max
    valleys = low == rolling_min

    # Filter to only significant ones (optional: can add min change threshold)
    return peaks, valleys


def count_recent_swings(
    df: pd.DataFrame,
    lookback_candles: int = 50,
    min_distance: int = 5
) -> int:
    """
    Rough count of significant highs/lows in recent data
    Fewer swings → cleaner structure
    """
    peaks, valleys = find_fractal_peaks_valleys(
        df['high'].iloc[-lookback_candles:],
        df['low'].iloc[-lookback_candles:],
        window=5
    )
    swing_points = pd.concat([peaks, valleys], axis=1).any(axis=1)
    # Count changes (up/down swings)
    changes = swing_points.diff().abs().sum()
    return int(changes)


def get_latest_indicators(df: pd.DataFrame) -> dict:
    """
    Compute a dict of latest indicator values for scoring / visualization
    """
    if len(df) < 50:
        return {}

    close = df['close']
    high = df['high']
    low = df['low']

    return {
        'sma20': calculate_sma(close, 20).iloc[-1],
        'ema50': calculate_ema(close, 50).iloc[-1],
        'atr14': calculate_atr(high, low, close, 14).iloc[-1],
        'adx14': calculate_adx(high, low, close, 14).iloc[-1],
        'bb_width': calculate_bollinger_width(close, 20).iloc[-1],
        'latest_close': close.iloc[-1],
        'latest_high': high.iloc[-1],
        'latest_low': low.iloc[-1],
        'latest_volume': df['volume'].iloc[-1],
    }
