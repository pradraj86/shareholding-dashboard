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
st.title("Cash Flow")

df_sh, df_fin, df_cf, df_insider, df_snap , df_brokerage, df_tech= load_all_data()
selected_symbols = st.session_state.get("selected_symbols", [])
selected_cats = st.session_state.get("selected_cats", [])
symbols = st.session_state.get("symbols", [])
if not symbols:
    symbols = sorted(set(df_sh["symbol"].unique()) | set(df_fin["symbol"].unique()) | set(df_cf["symbol"].unique()))
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

if df_cf.empty:
    st.info("No cash-flow data available.")
    st.stop()

top_cols = st.columns([1.2, 1.8])
with top_cols[0]:
    stock = st.selectbox("Stock", filtered_symbols or sorted(df_cf["symbol"].unique()), key="cf_stock")
with top_cols[1]:
    available = df_cf[df_cf["symbol"].eq(stock)]["metric"].dropna().unique().tolist()
    ordered = [m for m in CF_DISPLAY_METRICS if m in available] + [m for m in available if m not in CF_DISPLAY_METRICS]
    default = [m for m in ["CFO", "True Free Cash Flow", "Fixed Asset Purchased", "Net Cash Flow"] if m in ordered]
    metrics = st.multiselect("Metrics", ordered, default=default or ordered[:4], key="cf_metrics")

sub = sort_periods(df_cf[df_cf["symbol"].eq(stock)].copy())
if sub.empty:
    st.warning(f"No cash-flow data available for {stock}.")
    st.stop()

k_cols = st.columns(5)
# KPI strip: CFO | FCF | Fixed Asset Purchased | CFO/OP | FA/CFO ratio
kpi_defs = [
    ("CFO",                  "Cr"),
    ("True Free Cash Flow",  "Cr"),
    ("Fixed Asset Purchased","Cr"),
    ("CFO/OP",               "x"),
    ("Net Cash Flow",        "Cr"),
]
for col, (met, unit) in zip(k_cols, kpi_defs):
    if met == "CFO/OP":
        val = latest_cf(df_cf, stock, "CFO/OP")
        col.metric("CFO/OP", f"{val:.2f}x" if pd.notna(val) else "-")
    else:
        val = latest_cf(df_cf, stock, met)
        yoy = yoy_cf(df_cf, stock, met)
        col.metric(met, f"{val:,.1f} Cr" if pd.notna(val) else "-",
                   f"{yoy:+.1f}% YoY" if pd.notna(yoy) else None)

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
    _row = summary[summary["symbol"].eq(stock)]
    row = _row.iloc[0] if not _row.empty else pd.Series(dtype=object)
    st.metric("Cashflow Score", f"{row.get('Cashflow Score', '-'):.1f}" if isinstance(row.get("Cashflow Score"), float) else "-")
    st.write(row.get("Cash Flow Analysis", analyze_cashflow(row)) if isinstance(row, pd.Series) else "-")

    # CFO/OP and FA/CFO analysis cards
    if isinstance(row, pd.Series):
        cfo_op_v   = row.get("CFO/OP")
        fa_cfo_v   = row.get("FA/CFO")
        cash_qual  = row.get("Cash Quality", "-")
        capex_prof = row.get("Capex Profile", "-")

        q1, q2 = st.columns(2)
        with q1:
            st.markdown("**CFO / Operating Profit (Cash Conversion)**")
            st.metric("CFO/OP", f"{cfo_op_v:.2f}x" if pd.notna(cfo_op_v) else "-")
            st.caption(cash_qual)
        with q2:
            st.markdown("**Fixed Asset Purchased / CFO (Reinvestment Intensity)**")
            st.metric("FA/CFO", f"{fa_cfo_v:.2f}x" if pd.notna(fa_cfo_v) else "-")
            st.caption(capex_prof)

    quality_cols = [c for c in ["CFO", "True Free Cash Flow", "Fixed Asset Purchased",
                                "CFO/OP", "FA/CFO", "Cash Quality", "Capex Profile", "Red Flags"]
                    if c in summary.columns]
    if isinstance(row, pd.Series) and quality_cols:
        st.dataframe(pd.DataFrame([row[quality_cols]]), width="stretch", hide_index=True)

with table_tab:
    pivot = sub.pivot_table(index="period", columns="metric", values="value", aggfunc="first")
    st.dataframe(pivot.style.format("{:,.2f}", na_rep="-"), width="stretch", height=430)