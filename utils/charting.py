# utils/charting.py
import plotly.graph_objects as go
import pandas as pd
import streamlit as st
import numpy as np
from scipy.stats import linregress
from typing import Optional


def create_candlestick_fig(
    df: pd.DataFrame,
    token: str,
    height: int = 600,
    show_sr: bool = True,
    show_trendlines: bool = False,
    breakout_type: str = 'None'  # Now accepts this argument
) -> go.Figure:
    """
    Create interactive candlestick chart with conditional SR or TL overlays.
    breakout_type can be 'SR ...', 'TL ...', or 'None'
    """
    if df.empty:
        fig = go.Figure()
        fig.update_layout(title=f"No data for {token}")
        return fig

    plot_df = df.reset_index()

    fig = go.Figure(data=[
        go.Candlestick(
            x=plot_df['datetime'],
            open=plot_df['open'],
            high=plot_df['high'],
            low=plot_df['low'],
            close=plot_df['close'],
            name=token,
            increasing_line_color='green',
            decreasing_line_color='red'
        )
    ])

    # Volume bars
    fig.add_trace(
        go.Bar(
            x=plot_df['datetime'],
            y=plot_df['volume'],
            name='Volume',
            yaxis='y2',
            marker_color='rgba(150,150,150,0.6)',
            opacity=0.7
        )
    )

    # Add overlays based on breakout_type
    if 'SR' in breakout_type and show_sr:
        # Recent SR levels (last 100 candles)
        recent = plot_df.tail(100)
        resistance = recent['high'].max()
        support = recent['low'].min()
        fig.add_hline(y=resistance, line_dash="dash", line_color="blue",
                      annotation_text=f"Resistance ({resistance:.4f})")
        fig.add_hline(y=support, line_dash="dash", line_color="red",
                      annotation_text=f"Support ({support:.4f})")

    elif 'TL' in breakout_type and show_trendlines:
        # Use longer lookback for better, less narrow TL fit
        tl_lookback = 120  # ~30 hours at 15-min — tunable
        recent = df.tail(tl_lookback)

        if len(recent) >= 30:  # minimum for meaningful regression
            x = np.arange(len(recent))
            upper_slope, upper_int, _, _, _ = linregress(x, recent['high'].values)
            lower_slope, lower_int, _, _, _ = linregress(x, recent['low'].values)

            # Stringent slope filter: skip if both lines are too flat
            min_slope_abs = 0.0005  # adjust: higher = stricter (only steeper lines shown)
            if abs(upper_slope) > min_slope_abs or abs(lower_slope) > min_slope_abs:
                fig.add_trace(go.Scatter(
                    x=recent['datetime'],
                    y=upper_slope * x + upper_int,
                    mode='lines',
                    name='Upper TL',
                    line=dict(dash='dash', color='blue', width=2.5)  # thicker for visibility
                ))
                fig.add_trace(go.Scatter(
                    x=recent['datetime'],
                    y=lower_slope * x + lower_int,
                    mode='lines',
                    name='Lower TL',
                    line=dict(dash='dash', color='red', width=2.5)
                ))
            else:
                # Optional: show a note if skipped
                fig.add_annotation(
                    x=0.02, y=0.98, xref="paper", yref="paper",
                    text="TL too flat — not shown",
                    showarrow=False,
                    font=dict(size=10, color="gray"),
                    align="left"
                )

    # Title with breakout type if present
    title = f"{token} 15-min Chart (Last {len(plot_df)} candles)"
    if breakout_type != 'None':
        title += f" - {breakout_type}"

    fig.update_layout(
        title=title,
        yaxis_title="Price (USDT)",
        yaxis2=dict(title="Volume", overlaying="y", side="right", showgrid=False),
        xaxis_rangeslider_visible=True,
        height=height,
        template="plotly_dark" if st.get_option("theme.base") == "dark" else "plotly",
        hovermode="x unified",
        margin=dict(l=40, r=40, t=60, b=40)
    )

    return fig
