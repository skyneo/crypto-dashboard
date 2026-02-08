# app.py
"""
Crypto Trade Opportunity Dashboard
3-column phased view + token cards + charts
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path
from datetime import datetime
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth
import requests

from config import (
    APP_TITLE, APP_ICON, MAIN_COLUMNS, COLUMN_HEADERS,
    TOKENS_PER_PAGE_PER_COLUMN, 
    DASHBOARD_STATE_PARQUET, DATA_DIR, TIMEZONE,
    ALERTS_FILE
)

from utils.data_loader import load_token_parquet, load_alerts
from utils.charting import create_candlestick_fig   # ← we'll create this next

#@st.cache_data(ttl=900)  # 15 min
#def load_from_cloud(file_name, gdrive_link):
#    url = f"https://drive.google.com/file/d/{gdrive_link}"  # make shareable link
#    path = DATA_DIR / file_name
#    with open(path, "wb") as f:
#        f.write(requests.get(url).content)
#    return path
#
# Call in load functions
#load_from_cloud("dashboard_state.parquet", "1hFWBcj9tn6uIhiw23YZ8hVit2qJ6ljId/view?usp=sharing")
#load_from_cloud("alerts.txt", "1NjhH5pUq1xwsf6P7LCi0iUb_pzojfr34/view?usp=drive_link")

# Add this near the top of app.py (after imports)
@st.cache_data(ttl=60)  # refresh every minute
def load_alerts():
    if not Path(ALERTS_FILE).exists():
        return pd.DataFrame()
    
    lines = []
    with open(ALERTS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                parts = line.split(" (", 1)
                local_ts_str = parts[0].strip()
                rest = parts[1].rstrip(")")
                utc_ts_str, token_msg = rest.split(") ", 1)
                token, message = token_msg.split(" - ", 1)

                local_dt = datetime.strptime(local_ts_str, "%Y-%m-%d %H:%M:%S")
                utc_dt_str = utc_ts_str.replace(" UTC", "")
                utc_dt = datetime.strptime(utc_dt_str, "%Y-%m-%d %H:%M:%S")

                status = "Unknown"
                direction = "Unknown"
                if "Breakout" in message:
                    status_part, direction_part = message.split(" on ")
                    status = status_part.replace("Breakout ", "").strip()
                    direction = direction_part.strip()

                lines.append({
                    "timestamp_local": local_dt,
                    "token": token.strip(),
                    "status": status,
                    "direction": direction,
                    "full_message": message.strip(),
                })
            except:
                continue

    df = pd.DataFrame(lines)
    if not df.empty:
        df = df.sort_values("timestamp_local", ascending=False).reset_index(drop=True)
    return df

# ────────────────────────────────────────────────
#  Simple login (MVP - replace with streamlit-authenticator later)
# ────────────────────────────────────────────────
# Load credentials
credentials_path = Path(".streamlit/credentials.yaml")  # or ".streamlit/credentials.yaml"
with credentials_path.open() as file:
    config = yaml.load(file, Loader=SafeLoader)

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

# Login widget
authenticator.login(location="main")

authentication_status = st.session_state["authentication_status"]
name = st.session_state["name"]
username = st.session_state["username"]

if authentication_status:
    authenticator.logout("Logout", "sidebar")
    st.sidebar.success(f"Welcome {name}")
    # ← Your full dashboard code goes here (columns, state loading, etc.)
elif authentication_status is False:
    st.error("Username/password is incorrect")
elif authentication_status is None:
    st.warning("Please enter your username and password")

if authentication_status:
    # ────────────────────────────────────────────────
    #  Main Dashboard
    # ────────────────────────────────────────────────
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon=APP_ICON,
        layout="wide"
    )
    
    st.title(APP_TITLE)
    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | User: {st.session_state.get('username', 'Guest')}")
    
    # Load state
    @st.cache_data(ttl=300)  # cache 5 min
    def load_state():
        path = Path(DASHBOARD_STATE_PARQUET)
        #print(f"DASHBOARD_STATE_PARQUET: {DASHBOARD_STATE_PARQUET}")
        if not path.exists():
            st.error(f"Dashboard state not found: {path}")
            return pd.DataFrame()
        return pd.read_parquet(path)
    
    state_df = load_state()
    alerts_df = load_alerts()
    
    if state_df.empty:
        st.warning("No dashboard state available. Run dashboard_state_builder.py first.")
        st.stop()
    
    # ────────────────────────────────────────────────
    #  Sidebar filters
    # ────────────────────────────────────────────────
    with st.sidebar:
        st.header("Filters")
        min_profit = st.slider("Min Profitability Score", 0.0, 10.0, 0.0, 0.5)
        min_clean = st.slider("Min Cleanliness Score", 0.0, 10.0, 0.0, 0.5)
        phase_filter = st.multiselect(
            "Show Phases",
            options=state_df['phase'].unique(),
            default=state_df['phase'].unique()
        )
    
        if st.button("Refresh Data"):
            st.cache_data.clear()
            st.rerun()
    
    # Apply filters
    filtered_df = state_df[
        (state_df['profitability'] >= min_profit) &
        (state_df['cleanliness'] >= min_clean) &
        (state_df['phase'].isin(phase_filter))
    ].copy()
    
    # ────────────────────────────────────────────────
    #  3-Column Layout
    # ────────────────────────────────────────────────
    col1, col2, col3 = st.columns(MAIN_COLUMNS)
    
    columns = [col1, col2, col3]
    phases_groups = [
        filtered_df[filtered_df['phase'].str.contains("Setup|Accumulation|Neutral", case=False, na=False)],
        filtered_df[filtered_df['phase'].str.contains("Entry|Breakout", case=False, na=False)],
        filtered_df[filtered_df['phase'].str.contains("Continuation|In-Trade", case=False, na=False)]
    ]
    
    for idx, (col, header, group_df) in enumerate(zip(columns, COLUMN_HEADERS, phases_groups)):
        with col:
            st.subheader(header)
            if group_df.empty:
                st.info("No tokens in this phase match current filters.")
                continue
    
            group_df = group_df.sort_values('combined_score', ascending=False)
    
            for _, row in group_df.head(TOKENS_PER_PAGE_PER_COLUMN).iterrows():
                token = row['token']
                score = row['combined_score']
                profit = row['profitability']
                clean = row['cleanliness']
                phase = row['phase']
                price = row['last_price']
    
                # Color based on score
                #color = "green" if score >= 7 else "orange" if score >= 4 else "red"
    
                with st.expander(f"{token}  |  Score: {score:.1f}  |  ${price:,.2f}", expanded=False):
                    #st.markdown(f"**Phase**: {phase}")
                    phase_color = {
                        "Entry / Breakout Phase": "orange",
                        "Continuation / In-Trade Phase": "green",
                        "Setup / Accumulation Phase": "blue"
                    }.get(phase, "gray")
                    st.markdown(f"**Phase**: :{phase_color}[{phase}]")
                    st.markdown(f"**Profitability**: {profit:.1f}/10")
                    st.markdown(f"**Cleanliness**: {clean:.1f}/10")
                    color = "green" if score >= 4 else "orange" if score >= 2.5 else "gray"
                    st.markdown(f"**Score**: :{color}[{score:.1f}]")
    
                    # Show latest alert for this token
                    recent_alert = alerts_df[alerts_df['token'] == token].head(1)
                    if not recent_alert.empty:
                        alert_msg = recent_alert['full_message'].iloc[0]
                        alert_time = recent_alert['timestamp_local'].iloc[0].strftime("%Y-%m-%d %H:%M")
                        st.caption(f"Latest Alert ({alert_time}): {alert_msg}")
                    else:
                        st.caption("No recent alerts")
    
                    # Quick chart preview
                    try:
                        df_token = load_token_parquet(token)
                        fig = create_candlestick_fig(
                            df_token.tail(200),
                            token,
                            show_sr='SR' in row['breakout_type'],     # conditional
                            show_trendlines='TL' in row['breakout_type'],  # conditional
                            breakout_type=row['breakout_type'],
                            height=400
                        )
    
                        #fig = create_candlestick_fig(
                        #    df_token.tail(200),  # last ~50 hours
                        #    token,
                        #    show_sr=True,
                        #    height=400
                        #)
    
                        #st.plotly_chart(fig, use_container_width=True)
                        st.plotly_chart(fig, width='stretch')
                    except Exception as e:
                        st.warning(f"Chart not available: {e}")
    
                    if st.button("View Full Chart", key=f"full_{token}"):
                        st.session_state.selected_token = token
                        st.session_state.selected_row = row.to_dict()  # store row as dict
                        st.rerun()
    
    # ────────────────────────────────────────────────
    #  Full Chart Modal / Section (when selected)
    # ────────────────────────────────────────────────
    # Full chart block (outside loop)
    if "selected_token" in st.session_state:
        token = st.session_state.selected_token
        selected_row = st.session_state.get('selected_row', {})
        breakout_type = selected_row.get('breakout_type', 'None')
    
        st.markdown("---")
        st.header(f"Full Chart: {token}")
    
        try:
            df_full = load_token_parquet(token)
            fig_full = create_candlestick_fig(
                df_full.tail(1000),
                token,
                show_sr='SR' in breakout_type,
                show_trendlines='TL' in breakout_type,
                breakout_type=breakout_type,
                height=700
            )
            st.plotly_chart(fig_full, width='stretch')
        except Exception as e:
            st.error(f"Cannot load chart for {token}: {e}")
    
        if st.button("Close Full Chart"):
            for key in ['selected_token', 'selected_row']:
                st.session_state.pop(key, None)
            st.rerun()
