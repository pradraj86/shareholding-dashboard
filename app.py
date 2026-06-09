import streamlit as st
import pandas as pd
import subprocess
from utils import *

st.set_page_config(
    page_title="Stock Tracker",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
import subprocess
import streamlit as st


def run_fetcher(script_name, label):

    with st.spinner(f"Running {label}..."):

        try:

            result = subprocess.run(
                ["python", script_name],
                capture_output=True,
                text=True,
                check=True
            )

            st.success(
                f"✅ {label} completed"
            )

            st.cache_data.clear()

            return True

        except subprocess.CalledProcessError as e:

            st.error(
                f"❌ {label} failed"
            )

            st.code(e.stderr)

            return False
# ─── Theme ────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }

.metric-card {
    background: #f8f9fa;
    border: 1px solid #e9ecef;
    border-radius: 10px;
    padding: 1rem 1.25rem;
    text-align: center;
}
.metric-label { font-size: 12px; color: #6c757d; margin-bottom: 4px; letter-spacing: 0.04em; }
.metric-val   { font-size: 26px; font-weight: 600; color: #212529; }
.metric-sub   { font-size: 12px; margin-top: 2px; }

.up   { color: #1e7e34; }
.down { color: #c0392b; }
.neu  { color: #6c757d; }

.section-title {
    font-size: 13px;
    font-weight: 500;
    color: #6c757d;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 0.5rem;
}
</style>
""", unsafe_allow_html=True)

# ─── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("📊 Stock Tracker")
    st.caption("Source: Screener.in")
    st.markdown("---")
    st.subheader("🔄 Data Refresh")

    if st.button(
        "📊 Screener Data",
        use_container_width=True
    ):
        if run_fetcher(
            "screener_fetcher.py",
            "Screener Refresh"
        ):
            st.rerun()

    if st.button(
        "🕵️ Insider Trades",
        use_container_width=True
    ):
        if run_fetcher(
            "insider_fetcher.py",
            "Insider Refresh"
        ):
            st.rerun()

    if st.button(
        "📦 Bulk / Block Deals",
        use_container_width=True
    ):
        if run_fetcher(
            "bulk_block_fetcher.py",
            "Bulk/Block Refresh"
        ):
            st.rerun()

    if st.button(
        "📢 Corporate Actions",
        use_container_width=True
    ):
        if run_fetcher(
            "corporate_actions_fetcher.py",
            "Corporate Actions Refresh"
        ):
            st.rerun()

    if st.button(
        "🏦 Brokerage Reports",
        use_container_width=True
    ):
        if run_fetcher(
            "brokerage_fetcher.py",
            "Brokerage Refresh"
        ):
            st.rerun()
   
    if st.button(
    "🚀 Refresh Everything",
    use_container_width=True
):

        scripts = [
            ("screener_fetcher.py", "Screener"),
            ("insider_fetcher.py", "Insider"),
            ("bulk_block_fetcher.py", "Bulk/Block"),
            ("corporate_actions_fetcher.py", "Corporate Actions"),
            ("brokerage_fetcher.py", "Brokerage")
        ]

        for script, label in scripts:

            ok = run_fetcher(
                script,
                label
            )

            if not ok:
                break

        st.rerun()

    if st.button("🔄 Clear Cache Only", use_container_width=True):
        st.cache_data.clear() # This wipes the Streamlit RAM
        st.success("Cache Cleared!") 
        st.rerun() # This forces the app to reload everything from the files
    with st.spinner("📊 Loading data..."):

        (
            df_sh,
            df_fin,
            df_cf,
            df_insider,
            df_snap,df_brokerage, df_tech
        ) = load_all_data()
        

    if df_sh.empty and df_fin.empty and df_cf.empty:
        st.error("No data found.\n\nRun `python screener_fetcher.py` first.")
        st.stop()

    symbols    = sorted(df_sh["symbol"].unique().tolist() if not df_sh.empty else
                        df_fin["symbol"].unique().tolist())
    categories = sorted(df_sh["category"].unique().tolist()) if not df_sh.empty else []

    st.markdown("---")
    st.markdown('<div class="section-title">Filters</div>', unsafe_allow_html=True)

    selected_symbols = st.multiselect(
        "Stocks (leave blank = all)",
        options=symbols,
        default=[],
        placeholder="Select stocks…",
    )
    if not selected_symbols:
        selected_symbols = symbols

    selected_cats = st.multiselect(
        "Shareholding categories",
        options=categories,
        default=[c for c in ["Promoters","FIIs","DIIs","Public"] if c in categories],
    )
    if not selected_cats:
        selected_cats = categories

    st.markdown("---")
    st.markdown('<div class="section-title">Sort / Filter overview</div>', unsafe_allow_html=True)

    sort_by = st.selectbox(
        "Sort stocks by",
        ["Symbol A–Z", "FII % ↓", "FII % ↑", "FII QoQ change ↓","Promoter % ↓", "Sales ↓", "Net Profit ↓", "Market Cap ↓","Growth Score ↓",
        "Cashflow Score ↓","Composite Score ↓"]
    )
    filter_by = st.selectbox(
        "Filter to",
        ["All", "FII increasing", "FII decreasing", "FII > 20%", "FII < 5%",
         "Net Profit +ve", "Sales growth YoY"],
    )

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
# Normalize symbols before merges
summary["symbol"] = (
    summary["symbol"]
    .astype(str)
    .str.upper()
    .str.strip()
)
# After building summary, cache it in session_state so pages don't recompute
_cache_key = (tuple(sorted(selected_symbols)), tuple(sorted(selected_cats)))
if st.session_state.get("_summary_key") != _cache_key or "summary" not in st.session_state:
    st.session_state["summary"] = summary
    st.session_state["_summary_key"] = _cache_key

# Store filter state for pages
st.session_state["selected_symbols"] = selected_symbols
st.session_state["selected_cats"]    = selected_cats
st.session_state["symbols"]          = symbols
# ─── Filter data ──────────────────────────────────────────────────────────────
# ─── Growth Score Filter ─────────────────────────────

min_growth_score = st.sidebar.slider(
    "Minimum Growth Score",
    min_value=0,
    max_value=25,
    value=0,
)

if "Growth Score" not in summary.columns:
    summary["Growth Score"] = 0

summary = summary[
    summary["Growth Score"] >= min_growth_score
].copy()
summary["Cash Flow Analysis"] = summary.apply(analyze_cashflow, axis=1)
# Apply filter
if filter_by == "FII increasing":
    summary = summary[summary.get("FIIs QoQ", pd.Series(dtype=float)).fillna(0) > 0]
elif filter_by == "FII decreasing":
    summary = summary[summary.get("FIIs QoQ", pd.Series(dtype=float)).fillna(0) < 0]
elif filter_by == "FII > 20%":
    summary = summary[summary.get("FIIs %", pd.Series(dtype=float)).fillna(0) > 20]
elif filter_by == "FII < 5%":
    summary = summary[summary.get("FIIs %", pd.Series(dtype=float)).fillna(0) < 5]
elif filter_by == "Net Profit +ve":
    summary = summary[summary.get("Net Profit", pd.Series(dtype=float)).fillna(0) > 0]
elif filter_by == "Sales growth YoY":
    summary = summary[summary.get("Sales YoY %", pd.Series(dtype=float)).fillna(0) > 0]

# Apply sort
if   "FII % ↓"   in sort_by: summary = summary.sort_values("FIIs %",       ascending=False)
elif "FII % ↑"   in sort_by: summary = summary.sort_values("FIIs %",       ascending=True)
elif "QoQ"       in sort_by: summary = summary.sort_values("FIIs QoQ",     ascending=False)
elif "Promoter"  in sort_by: summary = summary.sort_values("Promoters %",  ascending=False)
elif "Sales ↓"   in sort_by: summary = summary.sort_values("Sales",        ascending=False)
elif "Net Profit" in sort_by: summary = summary.sort_values("Net Profit",  ascending=False)
elif "Market Cap" in sort_by: summary = summary.sort_values("MCap (Cr)",   ascending=False)
elif "Growth Score" in sort_by:summary = summary.sort_values("Growth Score",ascending=False)
elif "Cashflow Score" in sort_by:summary = summary.sort_values("Cashflow Score",ascending=False)
elif "Composite Score" in sort_by:summary = summary.sort_values("Composite Score",ascending=False)
else:                           
    if not summary.empty and "symbol" in summary.columns:
        summary = summary.sort_values("symbol")


# ─── Market-wide stats ────────────────────────────────────────────────────────

st.title("Stock Tracker")
st.caption(
    f"Data from Screener.in · {len(symbols)} stocks · "
    f"{df_sh['quarter'].nunique() if not df_sh.empty else 0} quarters"
)

home_cols = st.columns(4)

home_cols[0].metric(
    "Filtered Stocks",
    f"{len(summary):,}"
)

home_cols[1].metric(
    "A+ / A Stocks",
    f"{summary.get('Grade', pd.Series(dtype=str)).astype(str).isin(['A+', 'A']).sum():,}"
)

home_cols[2].metric(
    "FII Increasing",
    f"{summary.get('FIIs QoQ', pd.Series(dtype=float)).fillna(0).gt(0).sum():,}"
)

home_cols[3].metric(
    "Strong Cashflow",
    f"{summary.get('Cashflow Score', pd.Series(dtype=float)).fillna(0).ge(15).sum():,}"
)

st.info(
    "Detailed score cards, quality matrix, grade distribution, tables, "
    "and TradingView export now live only on the Stock Summary page."
)

st.stop()

