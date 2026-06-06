import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))
from utils import *


st.title("Cash Flow")

df_sh, df_fin, df_cf, df_snap = load_all_data()
selected_symbols = st.session_state.get("selected_symbols", [])
selected_cats = st.session_state.get("selected_cats", [])
symbols = st.session_state.get("symbols", [])
if not symbols:
    symbols = sorted(set(df_sh["symbol"].unique()) | set(df_fin["symbol"].unique()) | set(df_cf["symbol"].unique()))
if not selected_symbols:
    selected_symbols = symbols
if not selected_cats and not df_sh.empty:
    selected_cats = [c for c in ["Promoters", "FIIs", "DIIs", "Public"] if c in set(df_sh["category"].unique())]

summary = build_summary(df_sh, df_fin, df_cf, df_snap, tuple(selected_symbols), tuple(selected_cats))
filtered_symbols = summary["symbol"].tolist() if not summary.empty else symbols

if df_cf.empty:
    st.info("No cash-flow data available.")
    st.stop()

top_cols = st.columns([1.2, 1.8])
with top_cols[0]:
    stock = st.selectbox("Stock", filtered_symbols or sorted(df_cf["symbol"].unique()), key="cf_stock")
with top_cols[1]:
    available = df_cf[df_cf["symbol"].eq(stock)]["metric"].dropna().unique().tolist()
    ordered = [m for m in CF_DISPLAY_METRICS if m in available] + [m for m in available if m not in CF_DISPLAY_METRICS]
    default = [m for m in ["CFO", "True Free Cash Flow", "Capex", "Net Cash Flow"] if m in ordered]
    metrics = st.multiselect("Metrics", ordered, default=default or ordered[:4], key="cf_metrics")

sub = sort_periods(df_cf[df_cf["symbol"].eq(stock)].copy())
if sub.empty:
    st.warning(f"No cash-flow data available for {stock}.")
    st.stop()

k_cols = st.columns(5)
for col, met in zip(k_cols, ["CFO", "True Free Cash Flow", "Capex", "Net Cash Flow", "CFO/OP"]):
    val = latest_cf(df_cf, stock, met)
    yoy = yoy_cf(df_cf, stock, met) if met != "CFO/OP" else None
    suffix = "%" if met == "CFO/OP" else " Cr"
    col.metric(met, f"{val:,.1f}{suffix}" if pd.notna(val) else "-", f"{yoy:+.1f}% YoY" if pd.notna(yoy) else None)

chart_tab, quality_tab, table_tab = st.tabs(["Trend", "Quality Notes", "Data"])

with chart_tab:
    fig = go.Figure()
    for met in metrics:
        met_df = sort_periods(sub[sub["metric"].eq(met)].copy())
        if met_df.empty:
            continue
        fig.add_trace(
            go.Bar(
                x=met_df["period"].astype(str),
                y=met_df["value"],
                name=met,
                marker_color=CF_COLORS.get(met, "#64748b"),
                hovertemplate=f"<b>{met}</b><br>%{{x}}<br>%{{y:,.1f}}<extra></extra>",
            )
        )
    fig.add_hline(y=0, line_width=1, line_dash="dot", line_color="#94a3b8")
    fig.update_layout(
        title=f"{stock} annual cash-flow trend",
        template="plotly_white",
        height=470,
        barmode="group",
        hovermode="x unified",
        yaxis_title="Rs Cr",
        legend=dict(orientation="h", y=-0.2),
        margin=dict(l=45, r=20, t=55, b=80),
    )
    st.plotly_chart(fig, width="stretch")

with quality_tab:
    row = summary[summary["symbol"].eq(stock)].iloc[0] if not summary[summary["symbol"].eq(stock)].empty else {}
    st.metric("Cashflow Score", row.get("Cashflow Score", "-") if isinstance(row, pd.Series) else "-")
    st.write(row.get("Cash Flow Analysis", analyze_cashflow(row)) if isinstance(row, pd.Series) else "-")
    cols = [c for c in ["CFO", "True Free Cash Flow", "Capex", "CFO/OP", "CFO Yield %", "FCF Yield %", "Red Flags"] if c in summary.columns]
    if isinstance(row, pd.Series) and cols:
        st.dataframe(pd.DataFrame([row[cols]]), width="stretch", hide_index=True)

with table_tab:
    pivot = sub.pivot_table(index="period", columns="metric", values="value", aggfunc="first")
    st.dataframe(pivot.style.format("{:,.2f}", na_rep="-"), width="stretch", height=430)
