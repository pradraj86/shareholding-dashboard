import streamlit as st
import pandas as pd
from utils import *

st.title("🚀 Watchlist Scanner & Signal Generator")

# Load TradingView scanner data safely
# (load_data() -> load_tradingview_data() now normalizes column names against
# TV_CANONICAL_COLUMNS in utils.py, so minor TradingView export drift like
# extra spaces/commas no longer breaks this page. Genuinely absent columns
# are still possible if your CSV export excludes them — those are guarded
# below with safe_col() instead of crashing the whole page.)
df = load_data()

# Handle uninitialized or missing dataset cases gracefully
if df.empty:
    st.warning("⚠️ TradingView Growth Scanner dataset (`tradingview_growth.parquet`) is missing.")
    st.info(
        "Please ensure you have placed your raw TradingView CSV export "
        "(matching the pattern `EPS YOY AND QOQ_*.csv`) inside the `data/` directory."
    )
    
    # Inline generation trigger
    if st.button("🔄 Compile Parquet from CSV Source", use_container_width=True):
        try:
            fname, rows = refresh_tradingview_data()
            st.success(f"Successfully processed {rows} rows from {fname} into parquet!")
            st.cache_data.clear()
            st.rerun()
        except FileNotFoundError:
            st.error(
                "Could not find any source CSV matching `EPS YOY AND QOQ_*.csv` "
                "in your 'data/' folder. Please place the raw file there first."
            )
        except Exception as e:
            st.error(f"Failed to generate dataset: {e}")
            
    st.stop()

# Continue processing if data is present
df = apply_global_filters(df)

if "Symbol" not in df.columns:
    st.error(
        "The TradingView dataset has no 'Symbol' column even after normalization — "
        "this scanner can't function without it. Check your CSV export."
    )
    st.stop()

# Precalculate Entry score & Grades
# calculate_entry_score() already looks up each field defensively (get_val
# helper in utils.py), so it tolerates missing columns on its own.
df["Entry Score"] = df.apply(calculate_entry_score, axis=1)
df["Grade"] = df["Entry Score"].apply(get_grade)


def safe_col(frame, col):
    """True if col exists in frame; otherwise shows a small inline warning
    naming the missing column so it's obvious what to fix in the CSV export,
    rather than crashing the whole tab."""
    if col in frame.columns:
        return True
    st.caption(f"⚠️ Column not found in TradingView data, skipped: `{col}`")
    return False


def safe_cols(frame, cols):
    """Filter a wanted column list down to ones that actually exist, warning
    once per missing column."""
    present = [c for c in cols if safe_col(frame, c)]
    return present


tab_high, tab_momentum, tab_growth, tab_smart, tab_details = st.tabs([
    "⭐ High Conviction & Elite Setups", "⚡ Momentum & Timeframe Alignment", "📈 Growth Screeners", "💡 Smart Entry Breakouts", "🔍 Stock Technical Sheet"
])

with tab_high:
    st.subheader("High Conviction Setups (Score >= 80)")
    df_high = df.sort_values("Entry Score", ascending=False).copy()

    df_high["Category"] = "Ignore"
    df_high.loc[df_high["Entry Score"] >= 100, "Category"] = "🏆 Elite"
    df_high.loc[(df_high["Entry Score"] >= 80) & (df_high["Entry Score"] < 100), "Category"] = "🚀 High Conviction"
    df_high.loc[(df_high["Entry Score"] >= 60) & (df_high["Entry Score"] < 80), "Category"] = "✅ Watchlist"

    high_df = df_high[df_high["Entry Score"] >= 80]
    st.metric("Top Setup Stocks Found", len(high_df))

    wanted_cols = ["Symbol", "Entry Score", "Category", "Technical rating 1 day", "Technical rating 1 week", "Analyst rating", "Relative volume 1 day"]
    show_cols = safe_cols(high_df, wanted_cols)
    st.dataframe(high_df[show_cols], use_container_width=True, hide_index=True)

    watchlist_str = " , ".join("NSE:" + s for s in high_df["Symbol"])
    st.text_area("TradingView Watchlist Import String (High Conviction)", value=watchlist_str, height=100)

with tab_momentum:
    st.subheader("Momentum Ratings & Timeframe Alignment")
    min_perf = st.slider("Minimum 1-Month Return %", 0, 100, 10, key="ms_perf")

    if safe_col(df, "Performance % 1 month"):
        mom_df = df[df["Performance % 1 month"] >= min_perf].copy()
        mom_df = mom_df.sort_values("Performance % 1 month", ascending=False)

        st.markdown("#### Strong 1-Month Trend Stocks")
        mom_cols = safe_cols(mom_df, ["Symbol", "Performance % 1 month", "Performance % 1 week", "Relative volume 1 day", "Technical rating 1 day"])
        st.dataframe(mom_df[mom_cols], use_container_width=True, hide_index=True)
    else:
        st.info("1-month performance data unavailable — skipping trend table.")

    st.markdown("#### Aligned Multi-Timeframe Strong Buys (4H + 1D + 1W)")
    tf_cols = ["Technical rating 4 hours", "Technical rating 1 day", "Technical rating 1 week"]
    if all(safe_col(df, c) for c in tf_cols):
        aligned = df[
            df["Technical rating 4 hours"].isin(["Buy", "Strong Buy"]) &
            df["Technical rating 1 day"].isin(["Buy", "Strong Buy"]) &
            df["Technical rating 1 week"].isin(["Buy", "Strong Buy"])
        ]
        aligned_cols = safe_cols(aligned, ["Symbol", "Technical rating 4 hours", "Technical rating 1 day", "Technical rating 1 week", "Moving averages rating 1 day"])
        st.dataframe(aligned[aligned_cols], use_container_width=True, hide_index=True)
    else:
        st.info("Multi-timeframe technical ratings unavailable — skipping alignment table.")

with tab_growth:
    st.subheader("YoY & QoQ Growth Leader Screening")
    g_c1, g_c2 = st.columns(2)
    with g_c1: min_qoq_eps = st.slider("Min EPS Growth QoQ %", -20, 200, 10, key="g_eps_qoq")
    with g_c2: min_qoq_rev = st.slider("Min Revenue Growth QoQ %", -20, 200, 10, key="g_rev_qoq")

    eps_qoq_col = "Earnings per share diluted growth %, Quarterly QoQ"
    rev_qoq_col = "Revenue growth %, Quarterly QoQ"
    if safe_col(df, eps_qoq_col) and safe_col(df, rev_qoq_col):
        filtered_growth = df[
            (df[eps_qoq_col] >= min_qoq_eps) &
            (df[rev_qoq_col] >= min_qoq_rev)
        ]
        growth_cols = safe_cols(filtered_growth, ["Symbol", "Price", eps_qoq_col, rev_qoq_col, "Technical rating 1 day"])
        st.dataframe(filtered_growth[growth_cols], use_container_width=True, hide_index=True)
    else:
        st.info("QoQ growth data unavailable — skipping growth screener.")

with tab_smart:
    st.subheader("Breakout Candidates")
    st.caption("Strong Fundamental growth + Breakout technical patterns + Volume expansion")

    required = ["Relative volume 1 day", "Technical rating 1 day", "Technical rating 1 week", "Earnings per share diluted growth %, Quarterly YoY"]
    if all(safe_col(df, c) for c in required):
        signals = df[
            (df["Entry Score"] >= 80) &
            (df["Relative volume 1 day"] >= 1.2) &
            df["Technical rating 1 day"].isin(["Buy", "Strong Buy"]) &
            df["Technical rating 1 week"].isin(["Buy", "Strong Buy"]) &
            (df["Earnings per share diluted growth %, Quarterly YoY"] > 15)
        ]
        signal_cols = safe_cols(signals, ["Symbol", "Entry Score", "Price", "Relative volume 1 day", "Performance % 1 week", "Performance % 1 month", "Technical rating 1 day"])
        st.dataframe(signals[signal_cols], use_container_width=True, hide_index=True)
    else:
        st.info("Required breakout signal columns unavailable — skipping this screener.")

with tab_details:
    st.subheader("Detailed Assets Technical Sheet")
    sel_stock = st.selectbox("Select Ticker for Detailed Metrics", sorted(df["Symbol"]), key="sel_ms_stock")
    stock_row = df[df["Symbol"] == sel_stock].iloc[0]

    c1, c2, c3 = st.columns(3)
    c1.metric("Breakout Score", f"{stock_row['Entry Score']:.1f}")
    c2.metric("Breakout Grade", stock_row["Grade"])
    c3.metric("Price", f"Rs {stock_row['Price']:.1f}" if "Price" in df.columns and pd.notna(stock_row.get("Price")) else "-")

    st.markdown("##### Fundamental Check")
    eps_yoy_col = "Earnings per share diluted growth %, Quarterly YoY"
    rev_yoy_col = "Revenue growth %, Quarterly YoY"
    eps_txt = f"{stock_row[eps_yoy_col]:.2f}%" if eps_yoy_col in df.columns and pd.notna(stock_row.get(eps_yoy_col)) else "—"
    rev_txt = f"{stock_row[rev_yoy_col]:.2f}%" if rev_yoy_col in df.columns and pd.notna(stock_row.get(rev_yoy_col)) else "—"
    st.write(f"EPS YoY: **{eps_txt}** | Rev YoY: **{rev_txt}**")

    st.markdown("##### Multi-Timeframe Check")
    def tf_val(col):
        return stock_row[col] if col in df.columns and pd.notna(stock_row.get(col)) else "—"
    st.write(
        f"4H: **{tf_val('Technical rating 4 hours')}** | "
        f"1D: **{tf_val('Technical rating 1 day')}** | "
        f"1W: **{tf_val('Technical rating 1 week')}** | "
        f"1M: **{tf_val('Technical rating 1 month')}**"
    )