import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))
from utils import *

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="Stock Summary", layout="wide")

# ─── Single consolidated CSS block ────────────────────────────────────────────
st.markdown("""
<style>
.block-container { padding-top: 1rem !important; }

/* Native st.metric cards */
div[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #e8eaed;
    border-radius: 8px;
    padding: 10px 12px;
}
div[data-testid="stMetricLabel"] { font-size: 12px; color: #64748b; }
div[data-testid="stMetricValue"]  { font-size: 22px; font-weight: 650; }

.section-note { color: #64748b; font-size: 13px; margin-top: -8px; margin-bottom: 8px; }

/* Custom dark metric cards (TV export section) */
.metric-card {
    background: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 12px;
    padding: 18px;
    margin-bottom: 10px;
}
.metric-title { color: #94a3b8; font-size: 14px; }
.metric-value { color: white; font-size: 36px; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

# ─── Helpers ──────────────────────────────────────────────────────────────────
def pct_fmt(value, digits=1):
    return "-" if pd.isna(value) else f"{value:+.{digits}f}%"

def num_fmt(value, digits=1):
    return "-" if pd.isna(value) else f"{value:,.{digits}f}"

def grade_rank(series):
    order = {"A+": 0, "A": 1, "B": 2, "C": 3, "F": 4}
    return series.astype(str).map(order).fillna(99)

def color_change(value):
    if pd.isna(value): return ""
    if value > 0: return "color: #15803d; font-weight: 600"
    if value < 0: return "color: #b91c1c; font-weight: 600"
    return ""

def color_grade(value):
    colors = {
        "A+": "background-color: #166534; color: white; font-weight: 700",
        "A":  "background-color: #16a34a; color: white; font-weight: 700",
        "B":  "background-color: #facc15; color: #1f2937; font-weight: 700",
        "C":  "background-color: #fb923c; color: #1f2937; font-weight: 700",
        "F":  "background-color: #dc2626; color: white; font-weight: 700",
    }
    return colors.get(str(value), "")

def format_table(df, cols):
    skip = {
        "Grade", "symbol", "Latest Financial Quarter",
        "Latest Shareholding Quarter", "Latest Cashflow Quarter",
        "Data Quality", "Red Flags", "Cash Flow Analysis",
    }
    fmt = {}
    for col in cols:
        if col in skip:
            continue
        if col in {"CFO/OP", "FA/CFO"}:
            fmt[col] = "{:,.2f}x"
        elif "YoY" in col:
            fmt[col] = "{:+.1f}%"
        elif "QoQ" in col:
            fmt[col] = "{:+.2f} pp"
        elif col.endswith(" %"):
            fmt[col] = "{:.2f}%"
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

def existing(cols):
    return [c for c in cols if c in filtered.columns]

# ─── Load data ────────────────────────────────────────────────────────────────
df_sh, df_fin, df_cf, df_insider, df_snap, df_brokerage, df_tech = load_all_data()

selected_symbols = st.session_state.get("selected_symbols", [])
selected_cats    = st.session_state.get("selected_cats", [])
symbols          = st.session_state.get("symbols", [])

if not symbols:
    symbols = sorted(
        set(df_sh["symbol"].unique().tolist() if not df_sh.empty else [])
        | set(df_fin["symbol"].unique().tolist() if not df_fin.empty else [])
    )
if not selected_symbols:
    selected_symbols = symbols
if not selected_cats:
    selected_cats = [
        c for c in ["Promoters", "FIIs", "DIIs", "Public"]
        if c in set(df_sh.get("category", pd.Series(dtype=str)).unique())
    ]

# ─── Build summary ────────────────────────────────────────────────────────────
summary = st.session_state.get("summary", pd.DataFrame())

if not df_tech.empty:
    tech_map = df_tech.set_index("symbol").to_dict("index")
else:
    tech_map = {}

if summary.empty:
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

if summary.empty:
    st.info("No summary data available for the current filters.")
    st.stop()

summary["symbol"]             = summary["symbol"].astype(str).str.strip()
summary["Cash Flow Analysis"] = summary.apply(analyze_cashflow, axis=1)
summary["_grade_rank"]        = grade_rank(summary["Grade"]) if "Grade" in summary.columns else 99

# ─── Title ────────────────────────────────────────────────────────────────────
st.title("Stock Summary")
st.markdown(
    f"<div class='section-note'>{len(summary):,} stocks from Screener financials, "
    f"shareholding, cash-flow, and snapshot data.</div>",
    unsafe_allow_html=True,
)

# ─── Filter controls ──────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns([1.1, 1.1, 1.1, 1.4, 1.2])
with c1: min_score     = st.slider("Min score", 0, 100, 0, 5)
with c2: grade_filter  = st.multiselect("Grade", ["A+", "A", "B", "C", "F"], default=["A+", "A", "B", "C", "F"])
with c3: quality_filter= st.selectbox("Data quality", ["All", "Complete only", "Has red flags"])
with c4: search        = st.text_input("Search stock", placeholder="Symbol")
with c5: sort_by       = st.selectbox(
    "Sort by",
    ["Grade", "Performance Score", "Sales YoY %", "Net Profit YoY %",
     "CFO Yield %", "FII QoQ", "Promoters QoQ", "P/E"],
)

# ─── Apply filters ────────────────────────────────────────────────────────────
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

# ─── KPI strip ────────────────────────────────────────────────────────────────
complete_count  = int(filtered.get("Data Quality",    pd.Series(dtype=str)).eq("Complete").sum())
red_flag_count  = int(filtered.get("Red Flags",       pd.Series(dtype=str)).fillna("").ne("").sum())
avg_score       = filtered.get("Performance Score",   pd.Series(dtype=float)).mean()
a_count         = filtered.get("Grade",               pd.Series(dtype=str)).astype(str).isin(["A+", "A"]).sum()

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Filtered",      f"{len(filtered):,}")
k2.metric("A grade",       f"{a_count:,}")
k3.metric("Avg score",     num_fmt(avg_score, 1))
k4.metric("Complete data", f"{complete_count:,}")
k5.metric("With flags",    f"{red_flag_count:,}")

if filtered.empty:
    st.info("No stocks match the selected filters.")
    st.stop()

# ─── Quality Matrix ───────────────────────────────────────────────────────────
st.markdown("## 🎯 Quality Matrix")

if all(c in filtered.columns for c in ["Growth Score", "Cashflow Score", "Performance Score"]):
    matrix_df = filtered.dropna(subset=["Growth Score", "Cashflow Score"])
    fig = px.scatter(
        matrix_df,
        x="Growth Score", y="Cashflow Score",
        size="Performance Score", color="Grade",
        hover_name="symbol", size_max=35,
        color_discrete_map={"A+": "#16a34a", "A": "#22c55e", "B": "#facc15", "C": "#fb923c", "F": "#dc2626"},
    )
    fig.add_vline(x=matrix_df["Growth Score"].median(),   line_dash="dash")
    fig.add_hline(y=matrix_df["Cashflow Score"].median(), line_dash="dash")
    fig.update_layout(height=650)
    st.plotly_chart(fig, use_container_width=True)

# ─── Top Quality Stocks cards ─────────────────────────────────────────────────
st.markdown("## ⭐ Top Quality Stocks")
leaders = filtered.sort_values("Performance Score", ascending=False).head(12)
cols = st.columns(4)

for idx, (_, row) in enumerate(leaders.iterrows()):
    with cols[idx % 4]:
        with st.container(border=True):
            st.markdown(f"### {row['symbol']}")
            st.metric("Score", round(row["Performance Score"], 1))
            st.write(f"Grade: **{row['Grade']}**")
            st.write(f"Growth: **{row['Growth Score']}**")
            st.write(f"Cashflow: **{row['Cashflow Score']}**")

# ─── Grade distribution + Score mix charts ────────────────────────────────────
chart_cols = st.columns(2)

with chart_cols[0]:
    grade_counts = (
        filtered["Grade"].astype(str)
        .value_counts()
        .reindex(["A+", "A", "B", "C", "F"])
        .dropna()
        .reset_index()
    )
    grade_counts.columns = ["Grade", "Stocks"]
    fig = px.bar(
        grade_counts, x="Grade", y="Stocks", color="Grade",
        color_discrete_map={"A+": "#166534", "A": "#16a34a", "B": "#facc15", "C": "#fb923c", "F": "#dc2626"},
        title="Grade distribution",
    )
    fig.update_layout(height=260, margin=dict(l=8, r=8, t=42, b=8), showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

with chart_cols[1]:
    score_cols = [c for c in ["Growth Score", "Cashflow Score", "Shareholding Score"] if c in filtered.columns]
    if score_cols:
        top_scores = (
            filtered.head(25)
            .melt(id_vars="symbol", value_vars=score_cols, var_name="Score", value_name="Value")
        )
        fig = px.bar(top_scores, x="symbol", y="Value", color="Score", title="Top filtered stocks by score mix")
        fig.update_layout(height=260, margin=dict(l=8, r=8, t=42, b=8), xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

# ─── Column definitions ───────────────────────────────────────────────────────
base_fin = ["symbol", "Grade", "Performance Score", "Latest Financial Quarter",  "Data Freshness", "Data Quality"]
base_ca  = ["symbol", "Grade", "Performance Score", "Latest Cashflow Quarter",   "Data Freshness", "Data Quality"]
base_sh  = ["symbol", "Grade", "Performance Score", "Latest Shareholding Quarter","Data Freshness", "Data Quality"]

overview_cols = base_fin + [
    "Sales", "Sales YoY %", "Net Profit", "Net Profit YoY %", "EPS", "EPS YoY %",
    "Promoters %", "FIIs %", "DIIs %",
    "Red Flags", "Broker Reports", "Avg Target", "Avg Upside %", "Street View",
]

quality_cols = base_ca + [
    "CFO", "True Free Cash Flow", "Fixed Asset Purchased",
    "CFO/OP", "FA/CFO", "Cash Quality", "Capex Profile",
    "CFO YoY %", "Fixed Asset Purchased YoY %", "Cash Flow Analysis",
]

ownership_cols = base_sh + [
    "Promoters %", "Promoters QoQ",
    "FIIs %",      "FIIs QoQ",
    "DIIs %",      "DIIs QoQ",
    "Public %",    "Public QoQ",
]

valuation_cols = ["MCap (Cr)", "LTP", "CFO/OP", "FA/CFO", "Cash Quality", "Capex Profile"]

# ─── Tabbed data tables ───────────────────────────────────────────────────────
tab_overview, tab_quality, tab_ownership, tab_value, tab_flags = st.tabs(
    ["Financials", "Cash Quality", "Ownership", "Valuation", "Flags"]
)

TABLE_H = 470

with tab_overview:
    st.dataframe(format_table(filtered, existing(overview_cols)),
                 use_container_width=True, height=TABLE_H, hide_index=True)

with tab_quality:
    st.dataframe(format_table(filtered, existing(quality_cols)),
                 use_container_width=True, height=TABLE_H, hide_index=True)

with tab_ownership:
    st.dataframe(format_table(filtered, existing(ownership_cols)),
                 use_container_width=True, height=TABLE_H, hide_index=True)

with tab_value:
    st.dataframe(format_table(filtered, existing(valuation_cols)),
                 use_container_width=True, height=TABLE_H, hide_index=True)

with tab_flags:
    flag_df  = filtered[filtered.get("Red Flags", pd.Series(dtype=str)).fillna("").ne("")]
    flag_cols = existing(["symbol", "Grade", "Performance Score", "Data Quality", "Red Flags", "Cash Flow Analysis"])
    st.dataframe(
        format_table(flag_df, flag_cols) if not flag_df.empty else flag_df,
        use_container_width=True, height=TABLE_H, hide_index=True,
    )

st.divider()

with st.expander("All columns export view", expanded=False):
    st.dataframe(
        filtered.drop(columns=["_grade_rank"], errors="ignore"),
        use_container_width=True, height=420, hide_index=True,
    )

# ─── TradingView Watchlist Export ─────────────────────────────────────────────
st.divider()
st.subheader("📺 TradingView Watchlist Export")

tv_c1, tv_c2 = st.columns(2)

with tv_c1:
    tv_grade_filter = st.multiselect(
        "Grade", ["A+", "A", "B", "C", "F"], default=["A+", "A"], key="tv_grade"
    )

with tv_c2:
    quarter_opts = (
        sorted(filtered["Latest Financial Quarter"].dropna().astype(str).unique(), reverse=True)
        if "Latest Financial Quarter" in filtered.columns else []
    )
    tv_quarter_filter = st.multiselect(
        "Latest Financial Quarter", quarter_opts, default=[], key="tv_quarter"
    )

# Apply TV filters
tv_stocks = filtered.copy()
if tv_grade_filter:
    tv_stocks = tv_stocks[tv_stocks["Grade"].astype(str).isin(tv_grade_filter)]
if tv_quarter_filter:
    tv_stocks = tv_stocks[
        tv_stocks["Latest Financial Quarter"].astype(str).str.strip()
        .isin([x.strip() for x in tv_quarter_filter])
    ]

tv_stocks["TV Symbol"] = "NSE:" + tv_stocks["symbol"].astype(str).str.upper()

# Summary cards
m1, m2, m3, m4 = st.columns(4)
quarter_label = tv_quarter_filter[0] if tv_quarter_filter else "All"

for col, title, value in zip(
    [m1, m2, m3, m4],
    ["Filtered Stocks", "A+ Stocks", "A Stocks", "Quarter"],
    [
        len(tv_stocks),
        (tv_stocks["Grade"] == "A+").sum(),
        (tv_stocks["Grade"] == "A").sum(),
        quarter_label,
    ],
):
    col.markdown(f"""
    <div class='metric-card'>
        <div class='metric-title'>{title}</div>
        <div class='metric-value'>{value}</div>
    </div>
    """, unsafe_allow_html=True)

# Download
b1, b2, _ = st.columns([1, 1, 4])
with b1:
    st.download_button(
        "⬇ Download CSV",
        tv_stocks.to_csv(index=False),
        file_name="watchlist.csv",
        mime="text/csv",
    )

# Preview table + TradingView string
st.markdown("## Filtered Watchlist")

search_tv = st.text_input("", placeholder="Search stock", key="tv_search")
preview_df = tv_stocks.copy()
if search_tv:
    preview_df = preview_df[
        preview_df["symbol"].str.contains(search_tv, case=False, na=False)
    ]

tv_preview_cols = existing(["TV Symbol", "Grade", "Latest Financial Quarter"])
st.dataframe(preview_df[tv_preview_cols], hide_index=True, use_container_width=True, height=450)

tv_string = ",".join(tv_stocks["TV Symbol"].dropna().unique().tolist())
st.text_area("TradingView Symbols", value=tv_string, height=150)
st.caption(f"Total Symbols: {len(tv_stocks):,}")