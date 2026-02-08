# pages/01_Alerts_History.py
"""
Alerts History Page
Shows full log from alerts.txt with filtering, search and token chart links
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

from config import (
    ALERTS_FILE,
    TIMEZONE,
    APP_TITLE
)
from utils.data_loader import get_local_now

# Page config (Streamlit auto-detects this as a page)
st.set_page_config(
    page_title=f"Alerts History – {APP_TITLE}",
    layout="wide"
)

st.title("Alerts History")
st.caption("All detected breakouts and setup signals from the system")

# ────────────────────────────────────────────────
# Load and parse alerts
# ────────────────────────────────────────────────
@st.cache_data(ttl=60)  # refresh every minute
def load_and_parse_alerts():
    if not Path(ALERTS_FILE).exists():
        st.warning(f"Alerts file not found: {ALERTS_FILE}")
        return pd.DataFrame()

    lines = []
    with open(ALERTS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                # Format: 2026-02-04 18:29:23 (2026-02-04 10:15:00 UTC) TOKEN - Breakout {status} on {direction}
                parts = line.split(" (", 1)
                local_ts_str = parts[0].strip()
                rest = parts[1].rstrip(")")
                utc_ts_str, token_msg = rest.split(") ", 1)
                token, message = token_msg.split(" - ", 1)

                local_dt = datetime.strptime(local_ts_str, "%Y-%m-%d %H:%M:%S")
                utc_dt_str = utc_ts_str.replace(" UTC", "")
                utc_dt = datetime.strptime(utc_dt_str, "%Y-%m-%d %H:%M:%S")

                # Parse message
                if "Breakout" in message:
                    status_part, direction_part = message.split(" on ")
                    status = status_part.replace("Breakout ", "").strip()
                    direction = direction_part.strip()
                else:
                    status = "Unknown"
                    direction = "Unknown"

                lines.append({
                    "timestamp_local": local_dt,
                    "timestamp_utc": utc_dt,
                    "token": token.strip(),
                    "status": status,
                    "direction": direction,
                    "full_message": message.strip(),
                    "raw_line": line
                })
            except Exception as e:
                # Skip malformed lines
                continue

    if not lines:
        st.info("No alerts found in the log yet.")
        return pd.DataFrame()

    df = pd.DataFrame(lines)
    df = df.sort_values("timestamp_local", ascending=False).reset_index(drop=True)
    return df


alerts_df = load_and_parse_alerts()

if alerts_df.empty:
    st.stop()

# ────────────────────────────────────────────────
# Sidebar filters & stats
# ────────────────────────────────────────────────
with st.sidebar:
    st.header("Filter Alerts")
    # Date range
    min_date = alerts_df["timestamp_local"].min().date()
    max_date = alerts_df["timestamp_local"].max().date()
    date_range = st.date_input(
        "Date Range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )

    # Token search
    all_tokens = sorted(alerts_df["token"].unique())
    selected_tokens = st.multiselect(
        "Tokens",
        options=all_tokens,
        default=all_tokens[:10]  # default to first 10 to avoid overload
    )

    # Status & Direction
    status_options = ["happened", "about to happen", "Unknown"]
    selected_status = st.multiselect("Status", options=status_options, default=status_options)

    direction_options = ["upside", "downside", "Unknown"]
    selected_direction = st.multiselect("Direction", options=direction_options, default=direction_options)

    # Free text search in message
    search_text = st.text_input("Search in message", "")

    # Show only recent?
    recent_only = st.checkbox("Show only last 7 days", value=True)

# ────────────────────────────────────────────────
# Apply filters
# ────────────────────────────────────────────────
filtered = alerts_df.copy()

# Date range
if len(date_range) == 2:
    start_date, end_date = date_range
    filtered = filtered[
        (filtered["timestamp_local"].dt.date >= start_date) &
        (filtered["timestamp_local"].dt.date <= end_date)
    ]

# Tokens
if selected_tokens:
    filtered = filtered[filtered["token"].isin(selected_tokens)]

# Status
if selected_status:
    filtered = filtered[filtered["status"].isin(selected_status)]

# Direction
if selected_direction:
    filtered = filtered[filtered["direction"].isin(selected_direction)]

# Text search
if search_text:
    filtered = filtered[filtered["full_message"].str.contains(search_text, case=False, na=False)]

# Recent only
if recent_only:
    week_ago = (get_local_now() - timedelta(days=7)).date()
    filtered = filtered[filtered["timestamp_local"].dt.date >= week_ago]

# ────────────────────────────────────────────────
# Stats & summary
# ────────────────────────────────────────────────
total_alerts = len(filtered)
unique_tokens = filtered["token"].nunique()
latest_alert = filtered["timestamp_local"].max() if not filtered.empty else None

col1, col2, col3 = st.columns(3)
col1.metric("Total Alerts (filtered)", total_alerts)
col2.metric("Unique Tokens", unique_tokens)
if latest_alert:
    col3.metric("Most Recent", latest_alert.strftime("%Y-%m-%d %H:%M"))

# ────────────────────────────────────────────────
# Main table
# ────────────────────────────────────────────────
if filtered.empty:
    st.info("No alerts match the current filters.")
else:
    # Prepare display columns
    display_df = filtered[[
        "timestamp_local", "token", "status", "direction", "full_message"
    ]].copy()

    display_df["timestamp_local"] = display_df["timestamp_local"].dt.strftime("%Y-%m-%d %H:%M:%S")

    # Add clickable token column
    def make_token_link(token):
        return f"[{token}](#token-{token})"

    display_df["token_link"] = display_df["token"].apply(make_token_link)

    # Show table
    st.dataframe(
        display_df[["timestamp_local", "token_link", "status", "direction", "full_message"]],
        column_config={
            "token_link": st.column_config.TextColumn("Token", width="medium"),
            "timestamp_local": "Time (local)",
            "status": st.column_config.TextColumn("Status"),
            "direction": st.column_config.TextColumn("Direction"),
            "full_message": st.column_config.TextColumn("Message", width="large")
        },
        hide_index=True,
        #use_container_width=True
        width='stretch'
    )

# ────────────────────────────────────────────────
# Jump to token chart (when clicking token link)
# ────────────────────────────────────────────────
st.markdown("---")
if "selected_token_from_alerts" in st.session_state:
    token = st.session_state.selected_token_from_alerts
    st.subheader(f"Recent Chart: {token}")
    try:
        from utils.data_loader import load_token_parquet
        from utils.charting import create_candlestick_fig

        df_token = load_token_parquet(token)
        fig = create_candlestick_fig(df_token.tail(400), token, height=600)
        st.plotly_chart(fig, width='stretch')

        if st.button("Clear Chart"):
            del st.session_state.selected_token_from_alerts
            st.rerun()
    except Exception as e:
        st.error(f"Cannot load chart for {token}: {e}")
