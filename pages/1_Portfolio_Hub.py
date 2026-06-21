import io
import sys
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))
from utils import *

st.markdown("""
<style>
.block-container { padding-top: 1rem !important; }
div[data-testid="stMetric"] { background: #ffffff; border: 1px solid #e8eaed; border-radius: 8px; padding: 10px 12px; }
div[data-testid="stMetricLabel"] { font-size: 12px; color: #64748b; }
div[data-testid="stMetricValue"]  { font-size: 22px; font-weight: 650; }
.section-note { color: #64748b; font-size: 13px; margin-top: -8px; margin-bottom: 8px; }
.metric-card { background: #0f172a; border: 1px solid #1e293b; border-radius: 12px; padding: 18px; margin-bottom: 10px; }
.metric-title { color: #94a3b8; font-size: 14px; }
.metric-value { color: white; font-size: 36px; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

# --- Format Helpers ---
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
    skip = {"Grade", "symbol", "Latest Financial Quarter", "Latest Shareholding Quarter", "Latest Cashflow Quarter", "Data Quality", "Red Flags", "Cash Flow Analysis"}
    fmt = {}
    for col in cols:
        if col in skip: continue
        if col in {"CFO/OP", "FA/CFO"}: fmt[col] = "{:,.2f}x"
        elif "YoY" in col: fmt[col] = "{:+.1f}%"
        elif "QoQ" in col: fmt[col] = "{:+.2f} pp"
        elif col.endswith(" %"): fmt[col] = "{:.2f}%"
        elif col in {"Performance Score", "Growth Score", "Cashflow Score", "Shareholding Score"}: fmt[col] = "{:,.1f}"
        elif pd.api.types.is_numeric_dtype(df[col]): fmt[col] = "{:,.1f}"
    styled = df[cols].style.format(fmt, na_rep="-")
    if "Grade" in cols: styled = styled.map(color_grade, subset=["Grade"])
    change_cols = [c for c in cols if "QoQ" in c or "YoY" in c or c in {"CFO Yield %", "FCF Yield %"}]
    if change_cols: styled = styled.map(color_change, subset=change_cols)
    return styled

# --- Load Data ---
df_sh, df_fin, df_cf, df_insider, df_snap, df_brokerage, df_tech, df_tv = load_all_data()

selected_symbols = st.session_state.get("selected_symbols", [])
selected_cats    = st.session_state.get("selected_cats", [])
symbols          = st.session_state.get("symbols", [])

if not symbols:
    symbols = sorted(set(df_sh["symbol"].unique() if not df_sh.empty else []) | set(df_fin["symbol"].unique() if not df_fin.empty else []))
if not selected_symbols: selected_symbols = symbols
if not selected_cats and not df_sh.empty:
    selected_cats = [c for c in ["Promoters", "FIIs", "DIIs", "Public"] if c in set(df_sh["category"].unique())]

summary = st.session_state.get("summary", pd.DataFrame())
if summary.empty:
    summary = build_summary_cached(df_sh, df_fin, df_cf, df_insider, df_snap, df_brokerage, df_tech, df_tv, tuple(selected_symbols), tuple(selected_cats))

if summary.empty:
    st.info("No summary data available. Please load the main dataset first.")
    st.stop()

summary["symbol"]             = summary["symbol"].astype(str).str.strip()
summary["Cash Flow Analysis"] = summary.apply(analyze_cashflow, axis=1)
summary["_grade_rank"]        = grade_rank(summary["Grade"]) if "Grade" in summary.columns else 99

st.title("🏆 Core Portfolio Hub")
st.markdown(f"<div class='section-note'>{len(summary):,} active tracked stocks.</div>", unsafe_allow_html=True)

# Filters
c1, c2, c3, c4, c5 = st.columns([1.1, 1.1, 1.1, 1.4, 1.2])
with c1: min_score = st.slider("Min score", 0, 100, 0, 5)
with c2: grade_filter = st.multiselect("Grade", ["A+", "A", "B", "C", "F"], default=["A+", "A", "B", "C", "F"])
with c3: quality_filter = st.selectbox("Data quality", ["All", "Complete only", "Has red flags"])
with c4: search = st.text_input("Search stock", placeholder="Symbol...")
with c5: sort_by = st.selectbox("Sort by", ["Grade", "Performance Score", "Sales YoY %", "Net Profit YoY %", "FII QoQ", "Promoters QoQ", "MCap (Cr)"])

# Filter Logic
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

# KPI Summary
complete_count  = int(filtered.get("Data Quality", pd.Series(dtype=str)).eq("Complete").sum())
red_flag_count  = int(filtered.get("Red Flags", pd.Series(dtype=str)).fillna("").ne("").sum())
avg_score       = filtered.get("Performance Score", pd.Series(dtype=float)).mean()
a_count         = filtered.get("Grade", pd.Series(dtype=str)).astype(str).isin(["A+", "A"]).sum()

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Filtered", f"{len(filtered):,}")
k2.metric("A/A+ Grade", f"{a_count:,}")
k3.metric("Avg Score", num_fmt(avg_score, 1))
k4.metric("Complete Data", f"{complete_count:,}")
k5.metric("With Flags", f"{red_flag_count:,}")

tab_perf, tab_matrix, tab_tables, tab_sectors, tab_watchlist = st.tabs([
    "📈 Rankings & Scores", "🎯 Quality Matrix", "📋 Financial Tables", "🏭 Sector Analysis", "📺 TradingView Watchlist"
])

with tab_perf:
    chart_cols = st.columns(2)
    with chart_cols[0]:
        grade_counts = filtered["Grade"].astype(str).value_counts().reindex(["A+", "A", "B", "C", "F"]).dropna().reset_index()
        grade_counts.columns = ["Grade", "Stocks"]
        fig = px.bar(grade_counts, x="Grade", y="Stocks", color="Grade", title="Grade Distribution", color_discrete_map={"A+": "#166534", "A": "#16a34a", "B": "#facc15", "C": "#fb923c", "F": "#dc2626"})
        fig.update_layout(height=260, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    with chart_cols[1]:
        score_cols = [c for c in ["Growth Score", "Cashflow Score", "Shareholding Score"] if c in filtered.columns]
        if score_cols:
            top_scores = filtered.head(25).melt(id_vars="symbol", value_vars=score_cols, var_name="Score", value_name="Value")
            fig = px.bar(top_scores, x="symbol", y="Value", color="Score", title="Top 25 Stock Score Composition")
            fig.update_layout(height=260, xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)

    rank_cols = [c for c in ["symbol", "Grade", "Performance Score", "Growth Score", "Cashflow Score", "Shareholding Score", "Data Quality", "Red Flags"] if c in filtered.columns]
    st.dataframe(format_table(filtered, rank_cols), use_container_width=True, height=450, hide_index=True)

with tab_matrix:
    if all(c in filtered.columns for c in ["Growth Score", "Cashflow Score", "Performance Score"]):
        matrix_df = filtered.dropna(subset=["Growth Score", "Cashflow Score"])
        fig = px.scatter(matrix_df, x="Growth Score", y="Cashflow Score", size="Performance Score", color="Grade", hover_name="symbol", size_max=30, color_discrete_map={"A+": "#16a34a", "A": "#22c55e", "B": "#facc15", "C": "#fb923c", "F": "#dc2626"})
        fig.add_vline(x=matrix_df["Growth Score"].median(), line_dash="dash")
        fig.add_hline(y=matrix_df["Cashflow Score"].median(), line_dash="dash")
        fig.update_layout(height=480, title="Scatter Matrix (Growth vs Cashflow)")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### ⭐ Leaders List")
    leaders = filtered.sort_values("Performance Score", ascending=False).head(8)
    l_cols = st.columns(4)
    for idx, (_, row) in enumerate(leaders.iterrows()):
        with l_cols[idx % 4]:
            with st.container(border=True):
                st.markdown(f"**{row['symbol']}** ({row['Grade']})")
                st.write(f"Composite Score: `{row['Performance Score']:.1f}`")
                st.caption(f"G: {row['Growth Score']:.1f} | C: {row['Cashflow Score']:.1f}")

with tab_tables:
    base_fin = ["symbol", "Grade", "Performance Score", "Latest Financial Quarter", "Data Quality"]
    overview_cols = base_fin + [c for c in ["Sales", "Sales YoY %", "Net Profit", "Net Profit YoY %", "EPS", "EPS YoY %", "Promoters %", "FIIs %", "DIIs %", "Red Flags"] if c in filtered.columns]
    quality_cols = base_fin + [c for c in ["CFO", "True Free Cash Flow", "Fixed Asset Purchased", "CFO/OP", "FA/CFO", "Cash Quality"] if c in filtered.columns]
    
    table_opt = st.segmented_control("Table Type", ["Overview", "Cash Flow Quality"])
    if table_opt == "Cash Flow Quality":
        st.dataframe(format_table(filtered, quality_cols), use_container_width=True, height=450, hide_index=True)
    else:
        st.dataframe(format_table(filtered, overview_cols), use_container_width=True, height=450, hide_index=True)

with tab_sectors:
    if "Sector" in df_tv.columns:
        # TradingView CSV exports vary in which columns are included/how they're
        # punctuated, so build the agg dict only from columns that actually exist
        # instead of assuming the full set is present (avoids KeyError crashes).
        wanted = {
            "Symbol": ("count", "Stocks"),
            "Performance % 1 month": ("mean", "Avg 1M Return"),
            "Revenue growth %, Quarterly YoY": ("mean", "Avg Revenue Growth"),
            "Earnings per share diluted growth %, Quarterly YoY": ("mean", "Avg EPS Growth"),
        }
        agg_map = {col: how for col, (how, _) in wanted.items() if col in df_tv.columns}
        missing = [col for col in wanted if col not in df_tv.columns]

        if missing:
            st.caption(f"⚠️ Missing from TradingView data, skipped: {', '.join(missing)}")

        if "Symbol" not in agg_map:
            st.info("TradingView data has no 'Symbol' column — cannot build sector summary.")
        else:
            sector_summary = df_tv.groupby("Sector").agg(agg_map).reset_index()
            sector_summary.columns = ["Sector"] + [wanted[col][1] for col in agg_map]
            sort_col = "Avg EPS Growth" if "Avg EPS Growth" in sector_summary.columns else sector_summary.columns[-1]
            st.dataframe(sector_summary.sort_values(sort_col, ascending=False), use_container_width=True, hide_index=True)
    else:
        st.info("No Sector classification data available in tradingview database.")

with tab_watchlist:
    tv_c1, tv_c2 = st.columns(2)
    with tv_c1: tv_grade_filter = st.multiselect("Watchlist Grade", ["A+", "A", "B", "C", "F"], default=["A+", "A"], key="tv_hub_grade")
    with tv_c2:
        quarter_opts = sorted(filtered["Latest Financial Quarter"].dropna().astype(str).unique(), reverse=True) if "Latest Financial Quarter" in filtered.columns else []
        tv_quarter_filter = st.multiselect("Watchlist Quarter", quarter_opts, default=[], key="tv_hub_quarter")

    tv_stocks = filtered.copy()
    if tv_grade_filter: tv_stocks = tv_stocks[tv_stocks["Grade"].astype(str).isin(tv_grade_filter)]
    if tv_quarter_filter: tv_stocks = tv_stocks[tv_stocks["Latest Financial Quarter"].astype(str).str.strip().isin([x.strip() for x in tv_quarter_filter])]

    tv_stocks["TV Symbol"] = "NSE:" + tv_stocks["symbol"].astype(str).str.upper()
    tv_string = ",".join(tv_stocks["TV Symbol"].dropna().unique().tolist())
    
    st.text_area("TradingView Import Watchlist", value=tv_string, height=120)
    st.caption(f"Total Watchlist Symbols: {len(tv_stocks)}")
    st.download_button("⬇ Download Watchlist CSV", tv_stocks.to_csv(index=False), file_name="hub_watchlist.csv")