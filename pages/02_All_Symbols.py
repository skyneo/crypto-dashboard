# pages/02_All_Symbols.py
"""
All Symbols Page - List view only, chart loads on demand
"""

import streamlit as st
import pandas as pd
from pathlib import Path

from config import (
    APP_TITLE,
    SYMBOLS_FILTERED_CSV,
    DATA_DIR
)
from utils.data_loader import load_token_parquet
from utils.charting import create_candlestick_fig

# Page config
st.set_page_config(
    page_title=f"All Symbols – {APP_TITLE}",
    layout="wide"
)

st.title("All Tracked Symbols")
st.caption("Click any symbol to view its 15-min candlestick chart")

# ────────────────────────────────────────────────
# Load symbols list
# ────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_symbols_list():
    path = Path(SYMBOLS_FILTERED_CSV)
    if not path.exists():
        st.error(f"Filtered symbols file not found: {path}")
        return pd.DataFrame()
    
    df = pd.read_csv(path)
    useful_cols = ['symbol', 'full_symbol', 'volume', 'price', 'price_change']
    existing_cols = [c for c in useful_cols if c in df.columns]
    df = df[existing_cols].copy()
    
    if 'volume' in df.columns:
        df = df.sort_values('volume', ascending=False).reset_index(drop=True)
    else:
        df = df.sort_values('full_symbol').reset_index(drop=True)
    
    return df


symbols_df = load_symbols_list()

if symbols_df.empty:
    st.stop()

# ────────────────────────────────────────────────
# Sidebar controls
# ────────────────────────────────────────────────
with st.sidebar:
    st.header("Display Options")
    
    search_term = st.text_input("Search symbol or full symbol", "")
    
    chart_lookback_days = st.slider(
        "Chart lookback days",
        min_value=7,
        max_value=90,
        value=30,
        step=7,
        help="Number of days to show in the chart when viewing"
    )

# Apply search filter
if search_term:
    mask = (
        symbols_df['symbol'].str.contains(search_term, case=False, na=False) |
        symbols_df.get('full_symbol', '').str.contains(search_term, case=False, na=False)
    )
    display_df = symbols_df[mask]
else:
    display_df = symbols_df

st.markdown(f"**Showing {len(display_df)} of {len(symbols_df)} symbols**")

# ────────────────────────────────────────────────
# Grid of symbols (no charts here)
# ────────────────────────────────────────────────
cols = st.columns(4)

for idx, row in display_df.iterrows():
    symbol = row['symbol']
    full_symbol = row.get('full_symbol', symbol)
    price = row.get('price', '—')
    change = row.get('price_change', '—')
    
    col_idx = idx % 4
    with cols[col_idx]:
        with st.container(border=True):
            st.markdown(f"**{full_symbol}**")
            if price != '—':
                st.caption(f"Price: ${price:,.4f}")
            if change != '—':
                st.caption(f"24h Change: {change:+.2f}%")
            
            if st.button("View Chart", key=f"view_{full_symbol}"):
                st.session_state.selected_symbol_chart = full_symbol
                st.rerun()

# ────────────────────────────────────────────────
# Full chart section (loads only when selected)
# ────────────────────────────────────────────────
if "selected_symbol_chart" in st.session_state:
    selected = st.session_state.selected_symbol_chart
    
    st.markdown("---")
    st.subheader(f"Chart: {selected}")
    
    try:
        df_full = load_token_parquet(selected)
        
        # Calculate approximate number of candles
        candles_per_day = 24 * 4  # 15-min candles
        target_candles = min(len(df_full), chart_lookback_days * candles_per_day)
        
        fig = create_candlestick_fig(
            df_full.tail(target_candles),
            selected,
            height=700,
            show_sr=True,
            show_trendlines=True
        )
        
        st.plotly_chart(fig, width='stretch')
        
    except Exception as e:
        st.error(f"Failed to load chart for {selected}: {str(e)}")
    
    if st.button("Close Chart"):
        del st.session_state.selected_symbol_chart
        st.rerun()
