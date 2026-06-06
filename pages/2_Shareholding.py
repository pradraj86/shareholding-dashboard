import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))
from utils import *

tech_path = Path("data/technicals_all.parquet")

if tech_path.exists():
    df_tech = pd.read_parquet(tech_path)
else:
    df_tech = pd.DataFrame()
st.title("Shareholding")

df_sh, df_fin, df_cf, df_insider, df_snap,df_brokerage, df_tech = load_all_data()
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

if df_sh.empty:
    st.info("No shareholding data available.")
    st.stop()

top_cols = st.columns([1.4, 1, 1])
with top_cols[0]:
    stock = st.selectbox("Stock", filtered_symbols or sorted(df_sh["symbol"].unique()), key="sh_stock")
with top_cols[1]:
    period_count = st.slider("Quarters", 4, 20, 10)
with top_cols[2]:
    chart_mode = st.segmented_control("View", ["Grouped", "Stacked"], default="Grouped")

sub = sort_quarters(df_sh[df_sh["symbol"].eq(stock)].copy(), "quarter")
if sub.empty:
    st.warning(f"No shareholding data for {stock}.")
    st.stop()

quarters = sort_quarter_columns(sub["quarter"].unique())[-period_count:]
sub = sub[sub["quarter"].astype(str).isin([str(q) for q in quarters])]

latest_rows = (
    sort_quarters(df_sh[df_sh["symbol"].eq(stock)].copy(), "quarter")
    .groupby("category", as_index=False)
    .tail(1)
)

k_cols = st.columns(4)
for col, cat in zip(k_cols, ["Promoters", "FIIs", "DIIs", "Public"]):
    lv = latest_sh(df_sh, stock, cat)
    chg = qoq_sh(df_sh, stock, cat)
    col.metric(cat, f"{lv:.2f}%" if pd.notna(lv) else "-", f"{chg:+.2f} pp" if pd.notna(chg) else None)

chart_tab, table_tab, movers_tab = st.tabs(["Trend", "Data", "Largest QoQ Moves"])

with chart_tab:
    fig = go.Figure()
    for cat in ["Promoters", "FIIs", "DIIs", "Public"]:
        cat_df = sub[sub["category"].eq(cat)]
        if cat_df.empty:
            continue
        fig.add_trace(
            go.Bar(
                x=cat_df["quarter"].astype(str),
                y=cat_df["pct"],
                name=cat,
                marker_color=CATEGORY_COLORS.get(cat, "#64748b"),
                hovertemplate=f"<b>{cat}</b><br>%{{x}}<br>%{{y:.2f}}%<extra></extra>",
            )
        )
    fig.update_layout(
        title=f"{stock} ownership trend",
        template="plotly_white",
        barmode="stack" if chart_mode == "Stacked" else "group",
        yaxis_title="Holding %",
        yaxis_ticksuffix="%",
        height=460,
        margin=dict(l=35, r=20, t=50, b=70),
        legend=dict(orientation="h", y=-0.18),
    )
    st.plotly_chart(fig, width="stretch")

with table_tab:
    pivot = sub.pivot_table(index="quarter", columns="category", values="pct", aggfunc="first")
    pivot = pivot.reindex(quarters)
    st.dataframe(
        pivot.style.format("{:.2f}%", na_rep="-"),
        width="stretch",
        height=420,
    )

with movers_tab:
    latest_q = sort_quarter_columns(df_sh["quarter"].unique())[-1]
    prev_q = sort_quarter_columns(df_sh["quarter"].unique())[-2] if df_sh["quarter"].nunique() >= 2 else None
    if prev_q is None:
        st.info("Need at least two quarters for QoQ moves.")
    else:
        latest = df_sh[df_sh["quarter"].astype(str).eq(str(latest_q))]
        prev = df_sh[df_sh["quarter"].astype(str).eq(str(prev_q))]
        moves = latest.merge(prev, on=["symbol", "category"], suffixes=("", "_prev"))
        moves["QoQ pp"] = moves["pct"] - moves["pct_prev"]
        moves = moves[moves["category"].isin(["Promoters", "FIIs", "DIIs"])]
        moves = moves.sort_values("QoQ pp", ascending=False)
        pick = st.selectbox("Category", ["FIIs", "DIIs", "Promoters"], key="sh_move_cat")
        display = moves[moves["category"].eq(pick)][["symbol", "category", "pct", "pct_prev", "QoQ pp"]].head(40)
        st.dataframe(display.style.format({"pct": "{:.2f}%", "pct_prev": "{:.2f}%", "QoQ pp": "{:+.2f}"}), width="stretch", hide_index=True)
