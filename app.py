import streamlit as st
import pandas as pd
import subprocess
from utils import (
    load_all_data,
    build_summary_cached,
    analyze_cashflow,
    get_file_timestamp,
    load_data,
    refresh_tradingview_data,
    calculate_entry_score
)

# Set page config exactly ONCE at the top of the file
st.set_page_config(
    page_title="Investment Tracker & Scanner",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Helper Functions ─────────────────────────────────────────────────────────

def run_fetcher(script_name, label):
    with st.spinner(f"Running {label}..."):
        try:
            subprocess.run(
                ["python", script_name],
                capture_output=True,
                text=True,
                check=True
            )
            st.success(f"✅ {label} completed")
            st.cache_data.clear()
            return True
        except subprocess.CalledProcessError as e:
            st.error(f"❌ {label} failed")
            st.code(e.stderr)
            return False

def run_batch(batch_file, label):
    with st.spinner(f"{label}..."):
        try:
            result = subprocess.run(
                [batch_file],
                shell=True,
                capture_output=True,
                text=True,
                check=True
            )
            st.success(f"✅ {label} completed")
            if result.stdout:
                st.code(result.stdout)
            return True
        except subprocess.CalledProcessError as e:
            st.error(f"❌ {label} failed")
            st.code((e.stdout or "") + "\n" + (e.stderr or ""))
            return False

# ─── Custom CSS Theme ─────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght=300;400;500;600&display=swap');
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

# ─── Sidebar Controls & Configurations ────────────────────────────────────────

with st.sidebar:
    st.title("📊 Control Panel")
    st.caption("Source: Screener.in & TradingView")
    st.markdown("---")
    
    st.caption("📅 Last Data Updates")
    st.caption(f"📊 Screener : {get_file_timestamp('data/shareholding_all.parquet')}")
    st.caption(f"🕵️ Insider : {get_file_timestamp('data/insider_trades.parquet')}")
    st.caption(f"📦 Bulk/Block : {get_file_timestamp('data/bulk_deals.parquet')}")
    st.caption(f"📢 Corporate : {get_file_timestamp('data/corporate_actions_all.parquet')}")
    st.caption(f"🏦 Brokerage : {get_file_timestamp('data/brokerage_reports.parquet')}")
    
    st.markdown("---")
    st.subheader("🔄 Data Refresh")

    if st.button("📊 Screener Data", use_container_width=True):
        if run_fetcher("screener_fetcher.py", "Screener Refresh"):
            st.rerun()

    if st.button("🕵️ Insider Trades", use_container_width=True):
        if run_fetcher("insider_fetcher.py", "Insider Refresh"):
            st.rerun()

    if st.button("📦 Bulk / Block Deals", use_container_width=True):
        if run_fetcher("bulk_block_fetcher.py", "Bulk/Block Refresh"):
            st.rerun()

    if st.button("📢 Corporate Actions", use_container_width=True):
        if run_fetcher("corporate_actions_fetcher.py", "Corporate Actions Refresh"):
            st.rerun()

    if st.button("🏦 Brokerage Reports", use_container_width=True):
        if run_fetcher("brokerage_fetcher.py", "Brokerage Refresh"):
            st.rerun()
   
    if st.button("🚀 Refresh Everything", use_container_width=True):
        scripts = [
            ("screener_fetcher.py", "Screener"),
            ("insider_fetcher.py", "Insider"),
            ("bulk_block_fetcher.py", "Bulk/Block"),
            ("corporate_actions_fetcher.py", "Corporate Actions"),
            ("brokerage_fetcher.py", "Brokerage")
        ]
        for script, label in scripts:
            if not run_fetcher(script, label):
                break
        st.rerun()
    
    st.markdown("---")
    st.subheader("☁️ GitHub Control")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📥 Update GitHub", use_container_width=True):
            run_batch("update_github.bat", "GitHub Update")
    with col2:
        if st.button("📤 Push Only", use_container_width=True):
            run_batch("commit_github.bat", "GitHub Push")

    if st.button("🔄 Clear Cache Only", use_container_width=True):
        st.cache_data.clear()
        st.success("Cache Cleared!") 
        st.rerun()

# ─── Load Screener Datasets ───────────────────────────────────────────────────

with st.spinner("📊 Loading screener data..."):
    (
        df_sh,
        df_fin,
        df_cf,
        df_insider,
        df_snap,
        df_brokerage,
        df_tech,
        df_tv
    ) = load_all_data()

if df_sh.empty and df_fin.empty and df_cf.empty:
    st.error("No screener data found. Please trigger updates from the sidebar refresh options.")
    st.stop()

# ─── Populate Filters on Sidebar ──────────────────────────────────────────────

symbols = sorted(df_sh["symbol"].unique().tolist() if not df_sh.empty else df_fin["symbol"].unique().tolist())
categories = sorted(df_sh["category"].unique().tolist()) if not df_sh.empty else []

with st.sidebar:
    st.markdown("---")
    st.markdown('<div class="section-title">Global Screener Filters</div>', unsafe_allow_html=True)

    selected_symbols = st.multiselect(
        "Filter Specific Stocks (Leave blank for all)",
        options=symbols,
        default=[],
        placeholder="Select stocks...",
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
    st.markdown('<div class="section-title">Sorting & Criteria</div>', unsafe_allow_html=True)

    sort_by = st.selectbox(
        "Sort stocks by",
        ["Symbol A–Z", "FII % ↓", "FII % ↑", "FII QoQ change ↓","Promoter % ↓", "Sales ↓", "Net Profit ↓", "Market Cap ↓","Growth Score ↓", "Cashflow Score ↓","Composite Score ↓"]
    )
    filter_by = st.selectbox(
        "Predefined Criteria Filter",
        ["All", "FII increasing", "FII decreasing", "FII > 20%", "FII < 5%", "Net Profit +ve", "Sales growth YoY"],
    )

    min_growth_score = st.slider(
        "Minimum Growth Score Required",
        min_value=0,
        max_value=25,
        value=0,
    )

# ─── Process Summary Data ─────────────────────────────────────────────────────

summary = build_summary_cached(
    df_sh,
    df_fin,
    df_cf,
    df_insider,
    df_snap,
    df_brokerage,
    df_tech,
    df_tv,
    tuple(selected_symbols),
    tuple(selected_cats),
)

if not summary.empty:
    summary["symbol"] = summary["symbol"].astype(str).str.upper().str.strip()
    
    # Store key metrics on session state
    _cache_key = (tuple(sorted(selected_symbols)), tuple(sorted(selected_cats)))
    if st.session_state.get("_summary_key") != _cache_key or "summary" not in st.session_state:
        st.session_state["summary"] = summary
        st.session_state["_summary_key"] = _cache_key

    st.session_state["selected_symbols"] = selected_symbols
    st.session_state["selected_cats"]    = selected_cats
    st.session_state["symbols"]          = symbols

    # Handle filters
    if "Growth Score" not in summary.columns:
        summary["Growth Score"] = 0
    summary = summary[summary["Growth Score"] >= min_growth_score].copy()
    summary["Cash Flow Analysis"] = summary.apply(analyze_cashflow, axis=1)

    # Dynamic criteria filters
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

    # Dynamic sorting
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
        if "symbol" in summary.columns:
            summary = summary.sort_values("symbol")

# ─── Render Clean Tabbed Interface ───────────────────────────────────────────

tab1, tab2 = st.tabs(["📊 Screener Tracker Dashboard", "🚀 TradingView Growth Scanner"])

with tab1:
    st.subheader("Portfolio Financial Tracker Overview")
    st.caption(
        f"Aggregated database from Screener.in · {len(symbols)} stocks · "
        f"{df_sh['quarter'].nunique() if not df_sh.empty else 0} quarters"
    )

    home_cols = st.columns(4)
    home_cols[0].metric("Filtered Stocks", f"{len(summary):,}")
    home_cols[1].metric("A+ / A Grade Stocks", f"{summary.get('Grade', pd.Series(dtype=str)).astype(str).isin(['A+', 'A']).sum():,}")
    home_cols[2].metric("FII Accumulating", f"{summary.get('FIIs QoQ', pd.Series(dtype=float)).fillna(0).gt(0).sum():,}")
    home_cols[3].metric("Strong Cashflow Coverage", f"{summary.get('Cashflow Score', pd.Series(dtype=float)).fillna(0).ge(15).sum():,}")

    st.markdown("---")
    st.markdown("### 📈 Screener Financial Quality Matrix")
    
    if not summary.empty:
        # Determine available columns to showcase
        cols_to_show = ["symbol", "Grade", "Composite Score", "Growth Score", "Cashflow Score", "Shareholding Score", "LTP", "MCap (Cr)", "Red Flags", "Cash Flow Analysis"]
        existing_cols = [col for col in cols_to_show if col in summary.columns]
        st.dataframe(summary[existing_cols], use_container_width=True, hide_index=True)
    else:
        st.warning("No records match the active criteria filter.")

with tab2:
    st.subheader("TradingView Real-Time Technical Scanner")
    
    col_tv_actions, col_tv_space = st.columns([1, 4])
    with col_tv_actions:
        if st.button("🔄 Refresh Scanner Feed", key="refresh_tv_button"):
            try:
                fname, rows = refresh_tradingview_data()
                st.success(f"Successfully loaded {rows} rows from {fname}")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(str(e))

    try:
        df_tv_scanned = load_data()
    except Exception:
        df_tv_scanned = pd.DataFrame()

    if not df_tv_scanned.empty:
        # Technical Signal Metrics
        c1, c2, c3, c4 = st.columns(4)
        tech_col = "Technical rating 1 day" if "Technical rating 1 day" in df_tv_scanned.columns else None
        analyst_col = "Analyst rating" if "Analyst rating" in df_tv_scanned.columns else None

        strong_buy_cnt = (
            df_tv_scanned[tech_col].astype(str).str.contains("Strong Buy", case=False, na=False).sum()
            if tech_col else 0
        )
        buy_strong_buy_cnt = (
            df_tv_scanned[tech_col].astype(str).isin(["Buy", "Strong Buy"]).sum()
            if tech_col else 0
        )
        analyst_strong_buy_cnt = (
            df_tv_scanned[analyst_col].astype(str).str.contains("Strong Buy", case=False, na=False).sum()
            if analyst_col else 0
        )

        with c1:
            st.metric("Total Scanned Assets", len(df_tv_scanned))
        with c2:
            st.metric("Tech Indicator (Strong Buy)", strong_buy_cnt)
        with c3:
            st.metric("Composite Strong Buy/Buy", buy_strong_buy_cnt)
        with c4:
            st.metric("Analyst Consensus Strong Buy", analyst_strong_buy_cnt)

        st.markdown("---")
        st.markdown("### 🚀 TradingView Growth Stock Screener Table")

        # Interactive Sub-Filters for Tab 2 Table
        sub_filters = st.columns(3)
        with sub_filters[0]:
            tv_rating_filter = st.selectbox(
                "Technical Trend Strength",
                ["All", "Strong Buy", "Buy", "Neutral", "Sell"],
                key="tv_rating_filter_box"
            )
        with sub_filters[1]:
            min_rev_growth = st.number_input(
                "Minimum Quarterly Revenue YoY Growth (%)",
                value=0.0,
                key="tv_rev_growth_filter_input"
            )
        with sub_filters[2]:
            display_cols_default = [col for col in ["Symbol", "Price", "Analyst rating", "Technical rating 1 day", "Performance % 1 month", "Revenue growth %, Quarterly YoY", "Earnings per share diluted growth %, Quarterly YoY"] if col in df_tv_scanned.columns]
            tv_cols_to_show = st.multiselect(
                "Display Columns",
                options=df_tv_scanned.columns.tolist(),
                default=display_cols_default,
                key="tv_cols_to_show_select"
            )

        # Apply sub-filters dynamically
        filtered_tv = df_tv_scanned.copy()
        if tech_col and tv_rating_filter != "All":
            filtered_tv = filtered_tv[filtered_tv[tech_col].astype(str).str.contains(tv_rating_filter, case=False, na=False)]
        
        rev_yoy_col = "Revenue growth %, Quarterly YoY"
        if rev_yoy_col in filtered_tv.columns:
            filtered_tv[rev_yoy_col] = pd.to_numeric(filtered_tv[rev_yoy_col], errors="coerce").fillna(0.0)
            filtered_tv = filtered_tv[filtered_tv[rev_yoy_col] >= min_rev_growth]

        if not filtered_tv.empty:
            st.dataframe(filtered_tv[tv_cols_to_show if tv_cols_to_show else filtered_tv.columns], use_container_width=True, hide_index=True)
        else:
            st.info("No scanned stocks matches the active trend configurations.")
    else:
        st.warning("TradingView technical scan dataset not loaded. Run a data refresh cycle from Tab 2 or generate files.")