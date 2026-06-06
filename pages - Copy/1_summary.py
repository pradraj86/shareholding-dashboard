import io
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))

from utils import *


st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1rem !important;
    }
    div[data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #e8eaed;
        border-radius: 8px;
        padding: 10px 12px;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 12px;
        color: #64748b;
    }
    div[data-testid="stMetricValue"] {
        font-size: 22px;
        font-weight: 650;
    }
    .section-note {
        color: #64748b;
        font-size: 13px;
        margin-top: -8px;
        margin-bottom: 8px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def pct_fmt(value, digits=1):
    if pd.isna(value):
        return "-"
    return f"{value:+.{digits}f}%"


def num_fmt(value, digits=1):
    if pd.isna(value):
        return "-"
    return f"{value:,.{digits}f}"


def grade_rank(series):
    order = {"A+": 0, "A": 1, "B": 2, "C": 3, "F": 4}
    return series.astype(str).map(order).fillna(99)


def color_change(value):
    if pd.isna(value):
        return ""
    if value > 0:
        return "color: #15803d; font-weight: 600"
    if value < 0:
        return "color: #b91c1c; font-weight: 600"
    return ""


def color_grade(value):
    colors = {
        "A+": "background-color: #166534; color: white; font-weight: 700",
        "A": "background-color: #16a34a; color: white; font-weight: 700",
        "B": "background-color: #facc15; color: #1f2937; font-weight: 700",
        "C": "background-color: #fb923c; color: #1f2937; font-weight: 700",
        "F": "background-color: #dc2626; color: white; font-weight: 700",
    }
    return colors.get(str(value), "")


def format_table(df, cols):
    fmt = {}
    for col in cols:
        if col in {"Grade", "symbol", "Latest Quarter", "Latest Cashflow Year", "Data Quality", "Red Flags", "Cash Flow Analysis"}:
            continue
        if col in {"P/E", "P/S"}:
            fmt[col] = "{:,.2f}"
        elif col in {"CFO Yield %", "FCF Yield %"} or "YoY" in col or "QoQ" in col or col.endswith(" %"):
            fmt[col] = "{:+.2f}%" if "Yield" in col else "{:+.1f}%" if "YoY" in col else "{:+.2f} pp" if "QoQ" in col else "{:.2f}%"
        elif col in {"Performance Score", "Growth Score", "Cashflow Score", "Shareholding Score"}:
            fmt[col] = "{:,.1f}"
        elif pd.api.types.is_numeric_dtype(df[col]):
            fmt[col] = "{:,.1f}"

    styled = df[cols].style.format(fmt, na_rep="-")
    if "Grade" in cols:
        styled = styled.map(color_grade, subset=["Grade"])
    change_cols = [c for c in cols if "QoQ" in c or "YoY" in c or c in {"CFO Yield %", "FCF Yield %"}]
    if change_cols:
        styled = styled.map(color_change, subset=change_cols)
    return styled


df_sh, df_fin, df_cf, df_snap = load_all_data()

selected_symbols = st.session_state.get("selected_symbols", [])
selected_cats = st.session_state.get("selected_cats", [])
symbols = st.session_state.get("symbols", [])

if not symbols:
    symbols = sorted(
        set(df_sh["symbol"].unique().tolist() if not df_sh.empty else [])
        | set(df_fin["symbol"].unique().tolist() if not df_fin.empty else [])
    )
if not selected_symbols:
    selected_symbols = symbols
if not selected_cats:
    selected_cats = [c for c in ["Promoters", "FIIs", "DIIs", "Public"] if c in set(df_sh.get("category", pd.Series(dtype=str)).unique())]

summary = build_summary(
    df_sh,
    df_fin,
    df_cf,
    df_snap,
    tuple(selected_symbols),
    tuple(selected_cats),
)

if summary.empty:
    st.info("No summary data available for the current filters.")
    st.stop()

summary["symbol"] = summary["symbol"].astype(str).str.strip()
summary["Cash Flow Analysis"] = summary.apply(analyze_cashflow, axis=1)
summary["_grade_rank"] = grade_rank(summary["Grade"]) if "Grade" in summary.columns else 99

st.title("Stock Summary")
st.markdown(
    f"<div class='section-note'>{len(summary):,} stocks from Screener financials, shareholding, cash-flow, and snapshot data.</div>",
    unsafe_allow_html=True,
)

control_cols = st.columns([1.1, 1.1, 1.1, 1.4, 1.2])
with control_cols[0]:
    min_score = st.slider("Min score", 0, 100, 0, 5)
with control_cols[1]:
    grade_filter = st.multiselect("Grade", ["A+", "A", "B", "C", "F"], default=["A+", "A", "B", "C", "F"])
with control_cols[2]:
    quality_filter = st.selectbox("Data quality", ["All", "Complete only", "Has red flags"])
with control_cols[3]:
    search = st.text_input("Search stock", placeholder="Symbol")
with control_cols[4]:
    sort_by = st.selectbox(
        "Sort by",
        ["Grade", "Performance Score", "Sales YoY %", "Net Profit YoY %", "CFO Yield %", "FII QoQ", "Promoters QoQ", "P/E"],
    )

filtered = summary.copy()
if "Performance Score" in filtered.columns:
    filtered = filtered[filtered["Performance Score"].fillna(0) >= min_score]
if grade_filter and "Grade" in filtered.columns:
    filtered = filtered[filtered["Grade"].astype(str).isin(grade_filter)]
if quality_filter == "Complete only" and "Data Quality" in filtered.columns:
    filtered = filtered[filtered["Data Quality"].eq("Complete")]
elif quality_filter == "Has red flags" and "Red Flags" in filtered.columns:
    filtered = filtered[filtered["Red Flags"].fillna("").ne("")]
if search:
    filtered = filtered[filtered["symbol"].str.contains(search.strip(), case=False, na=False)]

if sort_by == "Grade" and "_grade_rank" in filtered.columns:
    filtered = filtered.sort_values(["_grade_rank", "Performance Score"], ascending=[True, False])
elif sort_by in filtered.columns:
    filtered = filtered.sort_values(sort_by, ascending=False, na_position="last")
else:
    filtered = filtered.sort_values("symbol")

complete_count = int(filtered.get("Data Quality", pd.Series(dtype=str)).eq("Complete").sum())
red_flag_count = int(filtered.get("Red Flags", pd.Series(dtype=str)).fillna("").ne("").sum())
avg_score = filtered.get("Performance Score", pd.Series(dtype=float)).mean()
a_count = filtered.get("Grade", pd.Series(dtype=str)).astype(str).isin(["A+", "A"]).sum()

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Filtered", f"{len(filtered):,}")
k2.metric("A grade", f"{a_count:,}")
k3.metric("Avg score", num_fmt(avg_score, 1))
k4.metric("Complete data", f"{complete_count:,}")
k5.metric("With flags", f"{red_flag_count:,}")

if filtered.empty:
    st.info("No stocks match the selected filters.")
    st.stop()

chart_cols = st.columns([1, 1])
with chart_cols[0]:
    grade_counts = (
        filtered["Grade"].astype(str).value_counts().reindex(["A+", "A", "B", "C", "F"]).dropna().reset_index()
    )
    grade_counts.columns = ["Grade", "Stocks"]
    fig = px.bar(
        grade_counts,
        x="Grade",
        y="Stocks",
        color="Grade",
        color_discrete_map={"A+": "#166534", "A": "#16a34a", "B": "#facc15", "C": "#fb923c", "F": "#dc2626"},
        title="Grade distribution",
    )
    fig.update_layout(height=260, margin=dict(l=8, r=8, t=42, b=8), showlegend=False)
    st.plotly_chart(fig, width="stretch")

with chart_cols[1]:
    score_cols = [c for c in ["Growth Score", "Cashflow Score", "Shareholding Score"] if c in filtered.columns]
    if score_cols:
        top_scores = filtered.head(25).melt(id_vars="symbol", value_vars=score_cols, var_name="Score", value_name="Value")
        fig = px.bar(top_scores, x="symbol", y="Value", color="Score", title="Top filtered stocks by score mix")
        fig.update_layout(height=260, margin=dict(l=8, r=8, t=42, b=8), xaxis_tickangle=-45)
        st.plotly_chart(fig, width="stretch")

base_cols = [
    "symbol",
    "Grade",
    "Performance Score",
    "Latest Quarter",
    "Data Quality",
]

overview_cols = base_cols + [
    "Sales",
    "Sales YoY %",
    "Net Profit",
    "Net Profit YoY %",
    "EPS",
    "EPS YoY %",
    "Promoters %",
    "FIIs %",
    "DIIs %",
    "Red Flags",
]

quality_cols = base_cols + [
    "CFO",
    "True Free Cash Flow",
    "CFO/OP",
    "CFO Yield %",
    "FCF Yield %",
    "CFO YoY %",
    "True Free Cash Flow YoY %",
    "Cash Flow Analysis",
]

ownership_cols = base_cols + [
    "Promoters %",
    "Promoters QoQ",
    "FIIs %",
    "FIIs QoQ",
    "DIIs %",
    "DIIs QoQ",
    "Public %",
    "Public QoQ",
]

valuation_cols = base_cols + [
    "MCap (Cr)",
    "LTP",
    "P/E",
    "P/S",
    "CFO Yield %",
    "FCF Yield %",
]

def existing(cols):
    return [c for c in cols if c in filtered.columns]


tab_overview, tab_quality, tab_ownership, tab_value, tab_flags = st.tabs(
    ["Overview", "Cash Quality", "Ownership", "Valuation", "Flags"]
)

with tab_overview:
    cols = existing(overview_cols)
    st.dataframe(
        format_table(filtered, cols),
        width="stretch",
        height=470,
        hide_index=True,
    )

with tab_quality:
    cols = existing(quality_cols)
    st.dataframe(
        format_table(filtered, cols),
        width="stretch",
        height=470,
        hide_index=True,
    )

with tab_ownership:
    cols = existing(ownership_cols)
    st.dataframe(
        format_table(filtered, cols),
        width="stretch",
        height=470,
        hide_index=True,
    )

with tab_value:
    cols = existing(valuation_cols)
    st.dataframe(
        format_table(filtered, cols),
        width="stretch",
        height=470,
        hide_index=True,
    )

with tab_flags:
    flag_df = filtered[filtered.get("Red Flags", pd.Series(dtype=str)).fillna("").ne("")]
    cols = existing(["symbol", "Grade", "Performance Score", "Data Quality", "Red Flags", "Cash Flow Analysis"])
    st.dataframe(
        format_table(flag_df, cols) if not flag_df.empty else flag_df,
        width="stretch",
        height=470,
        hide_index=True,
    )

st.divider()

with st.expander("All columns export view", expanded=False):
    export_df = filtered.drop(columns=["_grade_rank"], errors="ignore")
    st.dataframe(export_df, width="stretch", height=420, hide_index=True)

buffer = io.BytesIO()
filtered.drop(columns=["_grade_rank"], errors="ignore").to_parquet(buffer, index=False)

st.download_button(
    "Download filtered summary",
    data=buffer.getvalue(),
    file_name="stock_summary.parquet",
    mime="application/octet-stream",
)
