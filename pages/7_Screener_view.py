import io
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))
from utils import *

tech_path = Path("data/technicals_all.parquet")

if tech_path.exists():
    df_tech = pd.read_parquet(tech_path)
else:
    df_tech = pd.DataFrame()
st.title("Quarterly Screener")

df_sh, df_fin, df_cf, df_insider, df_snap , df_brokerage, df_tech= load_all_data()
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

top_cols = st.columns([1.7, 1, 1, 1])
with top_cols[0]:
    selected = st.multiselect(
        "Stocks",
        filtered_symbols or sorted(df_fin["symbol"].unique()),
        default=(filtered_symbols or sorted(df_fin["symbol"].unique()))[:25],
    )
with top_cols[1]:
    metric = st.selectbox("Metric", [m for m in ["Sales", "EBITDA", "Net Profit", "EPS", "EBITDA Margin %"] if m in df_fin["metric"].unique()])
with top_cols[2]:
    periods_to_show = st.slider("Periods", 4, 16, 8)
with top_cols[3]:
    min_yoy = st.number_input("Min YoY %", value=-999.0, step=5.0)

if not selected:
    st.info("Select at least one stock.")
    st.stop()

data = df_fin[
    df_fin["symbol"].isin(selected)
    & df_fin["metric"].eq(metric)
    & df_fin["freq"].eq("quarterly")
].copy()
data = sort_periods(data)

if data.empty:
    st.info(f"No quarterly data for {metric}.")
    st.stop()

periods = sort_quarter_columns(data["period"].unique())[-periods_to_show:]
data = data[data["period"].astype(str).isin([str(p) for p in periods])]

pivot = data.pivot_table(index="symbol", columns="period", values="value", aggfunc="first")
pivot = pivot.reindex(columns=periods)
if len(pivot.columns) >= 5:
    last = pivot.columns[-1]
    prev = pivot.columns[-5]
    pivot["YoY %"] = ((pivot[last] - pivot[prev]) / pivot[prev].abs() * 100).round(1)
else:
    pivot["YoY %"] = pd.NA

if not df_snap.empty:
    snap_idx = df_snap.set_index("symbol")
    pivot["LTP"] = snap_idx.reindex(pivot.index)["ltp"]
    pivot["MCap (Cr)"] = snap_idx.reindex(pivot.index)["market_cap_cr"]

pivot = pivot[pivot["YoY %"].fillna(-9999) >= min_yoy].sort_values("YoY %", ascending=False)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Stocks", len(pivot))
k2.metric("Median YoY", f"{pivot['YoY %'].median():+.1f}%" if pivot["YoY %"].notna().any() else "-")
k3.metric("Positive YoY", int((pivot["YoY %"] > 0).sum()))
k4.metric("Latest period", str(periods[-1]) if periods else "-")

tab_chart, tab_table = st.tabs(["Rank Chart", "Trend Table"])

with tab_chart:
    rank_df = pivot.reset_index()[["symbol", "YoY %"]].dropna().head(30)
    fig = px.bar(rank_df, x="YoY %", y="symbol", orientation="h", title=f"Top {metric} YoY growth")
    fig.update_layout(template="plotly_white", height=520, margin=dict(l=20, r=20, t=50, b=20), yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig, width="stretch")

with tab_table:
    fmt = {c: "{:,.1f}" for c in pivot.columns if c not in {"YoY %", "LTP", "MCap (Cr)"}}
    fmt.update({"YoY %": "{:+.1f}%", "LTP": "{:,.1f}", "MCap (Cr)": "{:,.0f}"})
    st.dataframe(pivot.style.format(fmt, na_rep="-"), width="stretch", height=560)

buffer = io.BytesIO()
pivot.reset_index().to_parquet(buffer, index=False)
st.download_button(
    f"Download {metric} trend",
    data=buffer.getvalue(),
    file_name=f"{metric.lower().replace(' ', '_')}_trend.parquet",
    mime="application/octet-stream",
)
