# utils/patterns.py
"""
Core pattern detection, phase classification, and scoring logic.
Used by both alert scripts and dashboard.
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional
from scipy.stats import linregress

from utils.indicators import (
    calculate_sma, calculate_ema, calculate_atr,
    calculate_adx, calculate_bollinger_width,
    count_recent_swings, get_latest_indicators
)
from config import (
    PROFITABILITY_WEIGHTS, CLEANNESS_WEIGHTS,
)


def detect_support_resistance(
    df: pd.DataFrame,
    lookback: int = 100
) -> Tuple[float, float]:
    """Simple recent support (min low) and resistance (max high)"""
    recent = df.iloc[-lookback:]
    resistance = recent['high'].max()
    support = recent['low'].min()
    return support, resistance


def classify_trade_phase(
    df: pd.DataFrame,
    indicators: Dict[str, float]
) -> Tuple[str, str]:
    """
    Classifies current trade phase with breakout type.
    Prioritizes: TL flag breakout > SR breakout > trend continuation > setup.
    Returns (phase, breakout_type) where breakout_type is e.g. 'TL happened upside',
    'SR about to downside', or 'None'.
    """
    if len(df) < 100:
        return "Unknown", "None"

    # ────────────────────────────────────────────────
    # 1H Trend Filter
    # ────────────────────────────────────────────────
    df_1h = df.resample('1h').agg({
        'open': 'first', 'high': 'max', 'low': 'min',
        'close': 'last', 'volume': 'sum'
    }).dropna()

    sma_period_1h = 20
    if len(df_1h) >= sma_period_1h:
        sma_1h = df_1h['close'].rolling(window=sma_period_1h).mean().iloc[-1]
        current_1h_close = df_1h['close'].iloc[-1]
        trend = 'up' if current_1h_close > sma_1h else 'down' if current_1h_close < sma_1h else 'sideways'
    else:
        trend = 'sideways'

    # Current candle
    current = df.iloc[-1]
    current_close = current['close']
    current_high = current['high']
    current_low = current['low']
    current_volume = current['volume']

    # Initialize flags
    tl_breakout_detected = False
    tl_breakout_type = None
    sr_breakout_detected = False
    sr_breakout_type = None

    # ────────────────────────────────────────────────
    # 1. TL Flag Pattern Breakout (priority)
    # ────────────────────────────────────────────────
    max_lookback_for_pole = 2500
    flag_channel_lookback = 80          # longer for better slope
    min_flagpole_candles = 8
    max_flagpole_candles = 50
    min_flagpole_move_pct = 4.0         # stricter
    min_volume_surge_flagpole = 1.35    # stricter
    min_flag_candles = 10               # stricter

    def detect_flagpole(start_idx: int, direction: str) -> Tuple[bool, Optional[pd.Timestamp], float]:
        end_idx = start_idx + max_flagpole_candles
        if end_idx > len(df):
            return False, None, 0.0

        segment = df.iloc[start_idx:end_idx]
        if direction == 'up':
            move_pct = (segment['close'].max() - segment['close'].min()) / segment['close'].min() * 100
            recent_avg_vol = df['volume'].iloc[max(0, start_idx-100):start_idx].mean() or 1.0
            vol_surge = segment['volume'].mean() / recent_avg_vol
            is_pole = move_pct >= min_flagpole_move_pct and vol_surge >= min_volume_surge_flagpole
        else:
            move_pct = (segment['close'].min() - segment['close'].max()) / segment['close'].max() * 100
            recent_avg_vol = df['volume'].iloc[max(0, start_idx-100):start_idx].mean() or 1.0
            vol_surge = segment['volume'].mean() / recent_avg_vol
            is_pole = move_pct <= -min_flagpole_move_pct and vol_surge >= min_volume_surge_flagpole

        return is_pole, segment.index[0] if is_pole else None, move_pct

    start_search_idx = max(0, len(df) - max_lookback_for_pole - flag_channel_lookback)
    end_search_idx = len(df) - min_flagpole_candles

    found_pole = False
    pole_start = None
    pole_direction = None

    for i in range(end_search_idx, start_search_idx - 1, -1):
        is_up, start_time, _ = detect_flagpole(i, 'up')
        if is_up:
            found_pole = True
            pole_start = start_time
            pole_direction = 'up'
            break
        is_down, start_time, _ = detect_flagpole(i, 'down')
        if is_down:
            found_pole = True
            pole_start = start_time
            pole_direction = 'down'
            break

    if found_pole:
        flag_start_idx = df.index.get_loc(pole_start) + 1
        flag_df = df.iloc[flag_start_idx:]

        if len(flag_df) >= min_flag_candles:
            x_flag = np.arange(len(flag_df))
            upper_slope, upper_intercept, _, _, _ = linregress(x_flag, flag_df['high'].values)
            lower_slope, lower_intercept, _, _, _ = linregress(x_flag, flag_df['low'].values)

            # Stricter slope filter
            min_slope_abs = 0.0008
            if abs(upper_slope) > min_slope_abs or abs(lower_slope) > min_slope_abs:
                flag_sloping_down = upper_slope < -1e-6 or lower_slope < -1e-6
                flag_sloping_up   = upper_slope > 1e-6 or lower_slope > 1e-6

                is_bullish_flag = (pole_direction == 'up') and flag_sloping_down
                is_bearish_flag = (pole_direction == 'down') and flag_sloping_up

                if is_bullish_flag or is_bearish_flag:
                    offset_from_flag_end = len(df) - flag_start_idx - 1
                    current_x_rel = (len(flag_df) - 1) + offset_from_flag_end

                    upper_proj = upper_slope * current_x_rel + upper_intercept
                    lower_proj = lower_slope * current_x_rel + lower_intercept

                    if upper_proj > 0 and lower_proj > 0:
                        avg_volume_flag = flag_df['volume'].mean() or 1.0

                        if is_bullish_flag and trend in ['up', 'sideways']:
                            if current_close > upper_proj:
                                tl_breakout_detected = True
                                tl_breakout_type = 'TL happened upside'
                            elif (current_high >= upper_proj * (1 - 0.008)) and \
                                 (current_volume > avg_volume_flag * 1.3):
                                tl_breakout_detected = True
                                tl_breakout_type = 'TL about to upside'

                        elif is_bearish_flag and trend in ['down', 'sideways']:
                            if current_close < lower_proj:
                                tl_breakout_detected = True
                                tl_breakout_type = 'TL happened downside'
                            elif (current_low <= lower_proj * (1 + 0.008)) and \
                                 (current_volume > avg_volume_flag * 1.3):
                                tl_breakout_detected = True
                                tl_breakout_type = 'TL about to downside'

    if tl_breakout_detected:
        return "Entry / Breakout Phase", tl_breakout_type

    # ────────────────────────────────────────────────
    # 2. SR Breakout Fallback
    # ────────────────────────────────────────────────
    sr_lookback = 100
    lookback_df = df.iloc[-sr_lookback-1:-1]
    if len(lookback_df) >= sr_lookback:
        resistance = lookback_df['high'].max()
        support = lookback_df['low'].min()
        avg_volume = lookback_df['volume'].mean() or 1.0

        if trend in ['up', 'sideways']:
            if current_close > resistance:
                sr_breakout_detected = True
                sr_breakout_type = 'SR happened upside'
            elif current_high >= resistance * (1 - 0.008) and current_volume > avg_volume * 1.3:
                sr_breakout_detected = True
                sr_breakout_type = 'SR about to upside'

        if trend in ['down', 'sideways']:
            if current_close < support:
                sr_breakout_detected = True
                sr_breakout_type = 'SR happened downside'
            elif current_low <= support * (1 + 0.008) and current_volume > avg_volume * 1.3:
                sr_breakout_detected = True
                sr_breakout_type = 'SR about to downside'

    if sr_breakout_detected:
        return "Entry / Breakout Phase", sr_breakout_type

    # ────────────────────────────────────────────────
    # 3. Trend continuation
    # ────────────────────────────────────────────────
    adx = indicators.get('adx14', np.nan)
    ema50 = indicators.get('ema50', current_close)
    close = indicators['latest_close']

    is_trending = (not np.isnan(adx) and adx > 18) or \
                  abs(close - ema50) > (ema50 * 0.008) if ema50 != 0 else False

    if is_trending:
        if close > ema50:
            return "Continuation / In-Trade Phase (Up)", "None"
        elif close < ema50:
            return "Continuation / In-Trade Phase (Down)", "None"

    return "Setup / Accumulation Phase", "None"



def calculate_profitability(
    df: pd.DataFrame,
    indicators: Dict[str, float]
) -> float:
    """
    Profitability score 0-10
    """
    if len(df) < 30:
        return 0.0

    atr = indicators['atr14']
    close = indicators['latest_close']
    volume = indicators['latest_volume']
    avg_vol = df['volume'].iloc[-50:-1].mean() if len(df) > 50 else 1.0

    rr_ratio = 3.0 if atr > 0 else 1.0
    vol_surge = min(5.0, volume / avg_vol if avg_vol > 0 else 1.0)
    momentum = 1.0 + (close - indicators['ema50']) / indicators['ema50'] * 20
    recent_high = df['high'].iloc[-50:].max()
    recent_low = df['low'].iloc[-50:].min()
    proximity_up = (recent_high - close) / atr if atr > 0 else 0
    proximity_score = min(2.0, max(0.0, proximity_up))

    score = (
        rr_ratio * PROFITABILITY_WEIGHTS["rr_ratio"] +
        vol_surge * PROFITABILITY_WEIGHTS["volume_surge"] +
        momentum * PROFITABILITY_WEIGHTS["momentum"] +
        proximity_score * PROFITABILITY_WEIGHTS["proximity_to_target"]
    )

    return min(10.0, max(0.0, round(score, 1)))


def calculate_market_cleanliness(
    df: pd.DataFrame,
    indicators: Dict[str, float]
) -> float:
    """
    Cleanliness score 0-10
    """
    adx = indicators.get('adx14', 0)
    bb_width = indicators.get('bb_width', 10.0)

    trend_score = min(10.0, adx / 2.5) if not np.isnan(adx) else 3.0
    swings = count_recent_swings(df, lookback_candles=80)
    swing_penalty = max(0, 10 - swings * 0.5)
    consol_bonus = max(0, 8 - bb_width) if bb_width < 10 else 0

    score = (
        trend_score * CLEANNESS_WEIGHTS["adx_strength"] +
        swing_penalty * CLEANNESS_WEIGHTS["fractal_clarity"] +
        consol_bonus * CLEANNESS_WEIGHTS["bb_width_low"]
    )

    return min(10.0, max(0.0, round(score, 1)))


def compute_all_metrics(token: str) -> Optional[Dict]:
    """
    Main entry point: load data → compute indicators → phase + scores
    """
    from utils.data_loader import load_token_parquet

    try:
        df = load_token_parquet(token)
        if len(df) < 100:
            return None

        indicators = get_latest_indicators(df)
        phase, breakout_type = classify_trade_phase(df, indicators)

        profitability = calculate_profitability(df, indicators)
        cleanliness = calculate_market_cleanliness(df, indicators)

        combined_score = round(
            profitability * 0.55 + cleanliness * 0.45, 1
        )

        return {
            'token': token,
            'phase': phase,
            'breakout_type': breakout_type or 'None',
            'profitability': profitability,
            'cleanliness': cleanliness,
            'combined_score': combined_score,
            'last_price': indicators['latest_close'],
            'last_volume': indicators['latest_volume'],
            'adx': indicators.get('adx14', np.nan),
            'timestamp': df.index[-1].isoformat()
        }

    except Exception as e:
        print(f"Error computing metrics for {token}: {e}")
        return None
