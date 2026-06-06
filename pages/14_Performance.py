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
st.title("Performance")

df_sh, df_fin, df_cf, df_insider, df_snap , df_brokerage, df_tech= load_all_data()
symbols = sorted(set(df_fin["symbol"].unique()) | set(df_sh["symbol"].unique()))
cats = tuple([c for c in ["Promoters", "FIIs", "DIIs", "Public"] if c in set(df_sh["category"].unique())])
tech_map = {}

if not df_tech.empty:

    tech_map = (
        df_tech
        .set_index("symbol")
        .to_dict("index")
    )
tech_map = {}

if not df_tech.empty:

    tech_map = (
        df_tech
        .set_index("symbol")
        .to_dict("index")
    )    
summary = build_summary_cached(
    df_sh,
    df_fin,
    df_cf,
    df_insider,
    df_snap,
    df_brokerage,
    df_tech,
    symbols,
    cats,
)
if summary.empty:
    st.info("No performance data available.")
    st.stop()

summary["_grade_rank"] = summary["Grade"].astype(str).map({"A+": 0, "A": 1, "B": 2, "C": 3, "F": 4}).fillna(99)

controls = st.columns([1, 1.2, 1.2, 1.5])
with controls[0]:
    min_score = st.slider("Min score", 0, 100, 50, 5)
with controls[1]:
    grades = st.multiselect("Grade", ["A+", "A", "B", "C", "F"], default=["A+", "A", "B", "C", "F"])
with controls[2]:
    dimension = st.selectbox("Dimension", ["Performance Score", "Growth Score", "Cashflow Score", "Shareholding Score"])
with controls[3]:
    search = st.text_input("Search", placeholder="Symbol")

filtered = summary[
    summary["Performance Score"].fillna(0).ge(min_score)
    & summary["Grade"].astype(str).isin(grades)
].copy()
if search:
    filtered = filtered[filtered["symbol"].astype(str).str.contains(search.strip(), case=False, na=False)]
filtered = filtered.sort_values(dimension, ascending=False, na_position="last")

k1, k2, k3, k4 = st.columns(4)
k1.metric("Stocks", len(filtered))
k2.metric("A grade", int(filtered["Grade"].astype(str).isin(["A+", "A"]).sum()))
k3.metric("Avg score", f"{filtered['Performance Score'].mean():.1f}" if not filtered.empty else "-")
k4.metric("Strong cashflow", int(filtered["Cashflow Score"].fillna(0).ge(15).sum()))

chart_cols = st.columns([1, 1])
with chart_cols[0]:
    grade_counts = filtered["Grade"].astype(str).value_counts().reindex(["A+", "A", "B", "C", "F"]).dropna().reset_index()
    grade_counts.columns = ["Grade", "Stocks"]
    fig = px.bar(grade_counts, x="Grade", y="Stocks", color="Grade", title="Grade distribution")
    fig.update_layout(template="plotly_white", height=300, showlegend=False)
    st.plotly_chart(fig, width="stretch")
with chart_cols[1]:
    top = filtered.head(25)
    fig = px.bar(top, x=dimension, y="symbol", orientation="h", color="Grade", title=f"Top stocks by {dimension}")
    fig.update_layout(template="plotly_white", height=300, yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig, width="stretch")

tab_rank, tab_score_mix, tab_export = st.tabs(["Rankings", "Score Mix", "Export"])

rank_cols = [
    "symbol",
    "Grade",
    "Performance Score",
    "Growth Score",
    "Cashflow Score",
    "Shareholding Score",
    "Data Quality",
    "Red Flags",
]
rank_cols = [c for c in rank_cols if c in filtered.columns]

with tab_rank:
    st.dataframe(
        filtered[rank_cols].style.format(
            {
                "Performance Score": "{:.1f}",
                "Growth Score": "{:.1f}",
                "Cashflow Score": "{:.1f}",
                "Shareholding Score": "{:.1f}",
            },
            na_rep="-",
        ),
        width="stretch",
        height=560,
        hide_index=True,
    )

with tab_score_mix:
    mix_cols = [c for c in ["Growth Score", "Cashflow Score", "Shareholding Score"] if c in filtered.columns]
    mix = filtered.head(40).melt(id_vars="symbol", value_vars=mix_cols, var_name="Score", value_name="Value")
    fig = px.bar(mix, x="symbol", y="Value", color="Score", title="Score composition")
    fig.update_layout(template="plotly_white", height=520, xaxis_tickangle=-45)
    st.plotly_chart(fig, width="stretch")

with tab_export:
    export = filtered.drop(columns=["_grade_rank"], errors="ignore")
    st.dataframe(export, width="stretch", height=520, hide_index=True)

buffer = io.BytesIO()
filtered.drop(columns=["_grade_rank"], errors="ignore").to_parquet(buffer, index=False)
st.download_button("Download performance table", buffer.getvalue(), "performance_summary.parquet", "application/octet-stream")
