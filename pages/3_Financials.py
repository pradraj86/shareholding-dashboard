import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))
from utils import *

tech_path = Path("data/technicals_all.parquet")

if tech_path.exists():
    df_tech = pd.read_parquet(tech_path)
else:
    df_tech = pd.DataFrame()
st.title("Financials")

df_sh, df_fin, df_cf,df_insider, df_snap , df_brokerage, df_tech= load_all_data()
selected_symbols = st.session_state.get("selected_symbols", [])
selected_cats = st.session_state.get("selected_cats", [])
symbols = st.session_state.get("symbols", [])
if not symbols:
    symbols = sorted(set(df_sh["symbol"].unique()) | set(df_fin["symbol"].unique()))
if not selected_symbols:
    selected_symbols = symbols
if not selected_cats and not df_sh.empty:
    selected_cats = [c for c in ["Promoters", "FIIs", "DIIs", "Public"] if c in set(df_sh["category"].unique())]

# Fast: read pre-computed summary from session_state (set by app.py)
summary = st.session_state.get("summary", pd.DataFrame())
tech_map = {}

if not df_tech.empty:

    tech_map = (
        df_tech
        .set_index("symbol")
        .to_dict("index")
    )
if summary.empty:
    # Fallback: compute if navigated directly without going through app.py
    summary = build_summary_cached(
    df_sh,
    df_fin,
    df_cf,
    df_insider,
    df_snap,
    df_brokerage,
    df_tech,
    tuple(selected_symbols),
    tuple(selected_cats),
)
filtered_symbols = summary["symbol"].tolist() if not summary.empty else symbols

if df_fin.empty:
    st.info("No financial data available.")
    st.stop()

top_cols = st.columns([1.3, 0.8, 1.8])
with top_cols[0]:
    stock = st.selectbox("Stock", filtered_symbols or sorted(df_fin["symbol"].unique()), key="fin_stock")
with top_cols[1]:
    freq = st.segmented_control("Frequency", ["quarterly", "annual"], default="quarterly", key="fin_freq")
with top_cols[2]:
    available = df_fin[(df_fin["symbol"].eq(stock)) & (df_fin["freq"].eq(freq))]["metric"].dropna().unique().tolist()
    default_metrics = [m for m in ["Sales", "EBITDA", "Net Profit"] if m in available]
    selected_metrics = st.multiselect("Metrics", available, default=default_metrics or available[:3], key="fin_metrics")

sub = sort_periods(df_fin[(df_fin["symbol"].eq(stock)) & (df_fin["freq"].eq(freq))].copy())
if sub.empty:
    st.info(f"No {freq} financials data for {stock}.")
    st.stop()

snap = df_snap[df_snap["symbol"].eq(stock)] if not df_snap.empty else pd.DataFrame()
ltp = snap["ltp"].iloc[0] if not snap.empty else None
mcap = snap["market_cap_cr"].iloc[0] if not snap.empty else None

k_cols = st.columns(5)
k_cols[0].metric("LTP", f"Rs {ltp:,.1f}" if pd.notna(ltp) else "-")
k_cols[1].metric("MCap", f"Rs {mcap:,.0f} Cr" if pd.notna(mcap) else "-")
for col, met in zip(k_cols[2:], ["Sales", "Net Profit", "EPS"]):
    lv = latest_fin(df_fin, stock, met)
    chg = yoy_fin(df_fin, stock, met)
    col.metric(met, f"{lv:,.1f}" if pd.notna(lv) else "-", f"{chg:+.1f}% YoY" if pd.notna(chg) else None)

chart_tab, margin_tab, table_tab = st.tabs(["Trend", "Margins & EPS", "Data"])

with chart_tab:
    fig = go.Figure()
    for met in selected_metrics:
        met_df = sort_periods(sub[sub["metric"].eq(met)].copy())
        if met_df.empty:
            continue
        is_line = met in {"EPS", "EBITDA Margin %"}
        if is_line:
            fig.add_trace(
                go.Scatter(
                    x=met_df["period"].astype(str),
                    y=met_df["value"],
                    name=met,
                    mode="lines+markers",
                    line=dict(color=METRIC_COLORS.get(met, "#64748b"), width=2.4),
                    yaxis="y2",
                    hovertemplate=f"<b>{met}</b><br>%{{x}}<br>%{{y:,.2f}}<extra></extra>",
                )
            )
        else:
            fig.add_trace(
                go.Bar(
                    x=met_df["period"].astype(str),
                    y=met_df["value"],
                    name=met,
                    marker_color=METRIC_COLORS.get(met, "#64748b"),
                    hovertemplate=f"<b>{met}</b><br>%{{x}}<br>%{{y:,.2f}}<extra></extra>",
                )
            )
    fig.update_layout(
        title=f"{stock} {freq} financial trend",
        template="plotly_white",
        height=470,
        barmode="group",
        hovermode="x unified",
        yaxis=dict(title="Rs Cr"),
        yaxis2=dict(title="% / EPS", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", y=-0.18),
        margin=dict(l=45, r=55, t=55, b=75),
    )
    st.plotly_chart(fig, width="stretch")

with margin_tab:
    margin_metrics = [m for m in ["EBITDA Margin %", "EPS"] if m in available]
    if not margin_metrics:
        st.info("No margin or EPS metrics available.")
    else:
        fig = go.Figure()
        for met in margin_metrics:
            met_df = sort_periods(sub[sub["metric"].eq(met)].copy())
            fig.add_trace(go.Scatter(x=met_df["period"].astype(str), y=met_df["value"], name=met, mode="lines+markers"))
        fig.update_layout(template="plotly_white", height=420, hovermode="x unified", legend=dict(orientation="h", y=-0.18))
        st.plotly_chart(fig, width="stretch")

with table_tab:
    pivot = sub.pivot_table(index="period", columns="metric", values="value", aggfunc="first")
    st.dataframe(pivot.style.format("{:,.2f}", na_rep="-"), width="stretch", height=430)
