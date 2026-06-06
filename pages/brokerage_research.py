# 10_brokerage_research.py

import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path
from utils import load_brokerage_data

# ─────────────────────────────────────────────────────────────
# Page Config
# ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Brokerage Research Tracker",
    page_icon="📈",
    layout="wide",
)

st.title("📈 Brokerage Research Tracker")
st.caption(
    "Track brokerage recommendations, "
    "target prices, and institutional sentiment"
)

# ─────────────────────────────────────────────────────────────
# Data File
# ─────────────────────────────────────────────────────────────

BROKERAGE_FILE = Path(
    "data/brokerage_reports.parquet"
)

# ─────────────────────────────────────────────────────────────
# Load Data
# ─────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────
# Load
# ─────────────────────────────────────────────────────────────

df = load_brokerage_data()

# ─────────────────────────────────────────────
# Normalize symbols
# ─────────────────────────────────────────────

if "symbol" in df.columns:

    df["symbol"] = (
        df["symbol"]
        .astype(str)
        .str.upper()
        .str.strip()
        .str.replace("-EQ", "", regex=False)
        .str.replace(" NSE", "", regex=False)
        .str.replace(" NS", "", regex=False)
        .str.replace(".NS", "", regex=False)
    )

# ─────────────────────────────────────────────────────────────
# Empty State
# ─────────────────────────────────────────────────────────────

if df.empty:

    st.warning(
        "No brokerage data found.\n\n"
        "Run brokerage_fetcher.py first."
    )

    st.stop()

# ─────────────────────────────────────────────────────────────
# Sidebar Filters
# ─────────────────────────────────────────────────────────────

with st.sidebar:

    st.header("Filters")

    search_stock = st.text_input(
        "Search Stock"
    )

    symbols = sorted(
        df["symbol"]
        .dropna()
        .unique()
        .tolist()
    ) if "symbol" in df.columns else []

    brokers = sorted(
        df["broker"]
        .dropna()
        .unique()
        .tolist()
    ) if "broker" in df.columns else []

    ratings = sorted(
        df["rating"]
        .dropna()
        .unique()
        .tolist()
    ) if "rating" in df.columns else []

    selected_symbols = st.multiselect(
        "Stocks",
        options=symbols,
        default=[],
    )

    selected_brokers = st.multiselect(
        "Brokerages",
        options=brokers,
        default=[],
    )

    selected_ratings = st.multiselect(
        "Ratings",
        options=ratings,
        default=[],
    )

# ─────────────────────────────────────────────────────────────
# Apply Filters
# ─────────────────────────────────────────────────────────────

filtered = df.copy()

if search_stock:

    filtered = filtered[
        filtered["symbol"]
        .str.contains(
            search_stock.upper(),
            na=False
        )
    ]

if selected_symbols:

    filtered = filtered[
        filtered["symbol"]
        .isin(selected_symbols)
    ]

if selected_brokers:

    filtered = filtered[
        filtered["broker"]
        .isin(selected_brokers)
    ]

if selected_ratings:

    filtered = filtered[
        filtered["rating"]
        .isin(selected_ratings)
    ]

# ─────────────────────────────────────────────────────────────
# Metrics
# ─────────────────────────────────────────────────────────────

c1, c2, c3, c4 = st.columns(4)

with c1:

    st.metric(
        "Total Reports",
        len(filtered)
    )

with c2:

    st.metric(
        "Stocks Covered",
        filtered["symbol"].nunique()
        if "symbol" in filtered.columns else 0
    )

with c3:

    st.metric(
        "Brokerages",
        filtered["broker"].nunique()
        if "broker" in filtered.columns else 0
    )

with c4:

    avg_upside = (
        round(
            filtered["upside_pct"].mean(),
            2
        )
        if "upside_pct" in filtered.columns
        else 0
    )

    st.metric(
        "Avg Upside %",
        f"{avg_upside}%"
    )

st.divider()

# ─────────────────────────────────────────────────────────────
# Tabs
# ─────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "Latest Reports",
    "Consensus",
    "Institutional Conviction",
    "Broker Analysis",
    "Charts",
    "Recent Reports",
])

# ─────────────────────────────────────────────────────────────
# Latest Reports
# ─────────────────────────────────────────────────────────────

with tab1:

    st.subheader(
        "Latest Brokerage Reports"
    )

    latest_df = filtered.copy()

    if "date" in latest_df.columns:

        latest_df = latest_df.sort_values(
            "date",
            ascending=False
        )

    display_cols = [
        c for c in [
            "date",
            "symbol",
            "broker",
            "rating",
            "cmp",
            "target_price",
            "upside_pct",
            "report_title",
        ]
        if c in latest_df.columns
    ]

    st.dataframe(
        latest_df[display_cols],
        use_container_width=True,
        hide_index=True,
    )

# ─────────────────────────────────────────────────────────────
# Consensus
# ─────────────────────────────────────────────────────────────

with tab2:

    st.subheader("Consensus View")

    if "symbol" in filtered.columns:

        consensus = (
            filtered
            .groupby("symbol")
            .agg(
                Reports=("symbol", "count"),
                Avg_Target=(
                    "target_price",
                    "mean"
                ),
                Avg_Upside=(
                    "upside_pct",
                    "mean"
                ),
                Brokers=(
                    "broker",
                    "nunique"
                ),
            )
            .reset_index()
        )

        consensus["Avg_Target"] = (
            consensus["Avg_Target"]
            .round(2)
        )

        consensus["Avg_Upside"] = (
            consensus["Avg_Upside"]
            .round(2)
        )

        consensus = consensus.sort_values(
            "Avg_Upside",
            ascending=False
        )

        st.dataframe(
            consensus,
            use_container_width=True,
            hide_index=True,
        )

        # ── Consensus Matrix ─────────────────────

        st.subheader("Consensus Matrix")

        pivot = (
            filtered
            .pivot_table(
                index="symbol",
                columns="rating",
                values="broker",
                aggfunc="count",
                fill_value=0,
            )
        )

        st.dataframe(
            pivot,
            use_container_width=True,
        )

# ─────────────────────────────────────────────────────────────
# Institutional Conviction
# ─────────────────────────────────────────────────────────────

with tab3:

    st.subheader(
        "Institutional Conviction"
    )

    conviction = (
        filtered
        .groupby("symbol")
        .agg(
            Reports=("symbol", "count"),
            Avg_Upside=(
                "upside_pct",
                "mean"
            ),
            Brokers=(
                "broker",
                "nunique"
            ),
        )
        .reset_index()
    )

    conviction["Conviction"] = (
        conviction["Reports"] * 0.5
        + conviction["Avg_Upside"] * 0.3
        + conviction["Brokers"] * 0.2
    )

    conviction = conviction.sort_values(
        "Conviction",
        ascending=False
    )

    conviction["Avg_Upside"] = (
        conviction["Avg_Upside"]
        .round(2)
    )

    conviction["Conviction"] = (
        conviction["Conviction"]
        .round(2)
    )

    st.dataframe(
        conviction.head(25),
        use_container_width=True,
        hide_index=True,
    )

# ─────────────────────────────────────────────────────────────
# Broker Analysis
# ─────────────────────────────────────────────────────────────

with tab4:

    st.subheader(
        "Broker-wise Activity"
    )

    
    if "broker" in filtered.columns:

        broker_summary = (
        filtered
        .groupby("broker")
        .agg(
            Reports=("symbol", "count"),
            Avg_Upside=("upside_pct", "mean"),
            Avg_Target=("target_price", "mean"),
        )
        .reset_index()
    )

    broker_summary["Avg_Upside"] = (
        broker_summary["Avg_Upside"]
        .round(2)
    )

    broker_summary["Avg_Target"] = (
        broker_summary["Avg_Target"]
        .round(2)
    )

    st.dataframe(
        broker_summary,
        use_container_width=True,
        hide_index=True,
    )

    # ── Sentiment ─────────────────────────────

    sentiment_map = {
        "BUY": 2,
        "ACCUMULATE": 1,
        "HOLD": 0,
        "REDUCE": -1,
        "SELL": -2,
    }

    tmp = filtered.copy()

    tmp["sentiment"] = (
        tmp["rating"]
        .map(sentiment_map)
    )

    broker_sentiment = (
        tmp
        .groupby("broker")
        .agg(
            Avg_Sentiment=(
                "sentiment",
                "mean"
            ),
            Reports=("broker", "count"),
        )
        .reset_index()
    )

    broker_sentiment = broker_sentiment.sort_values(
        "Avg_Sentiment",
        ascending=False
    )

    st.subheader(
        "Broker Sentiment"
    )

    st.dataframe(
        broker_sentiment,
        use_container_width=True,
        hide_index=True,
    )

# ─────────────────────────────────────────────────────────────
# Charts
# ─────────────────────────────────────────────────────────────

with tab5:

    st.subheader(
        "Rating Distribution"
    )

    if "rating" in filtered.columns:

        rating_counts = (
            filtered["rating"]
            .value_counts()
            .reset_index()
        )

        rating_counts.columns = [
            "Rating",
            "Count"
        ]

        fig = px.pie(
            rating_counts,
            names="Rating",
            values="Count",
            hole=0.45,
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

    # ── Most Covered ─────────────────────────

    st.subheader(
        "Most Covered Stocks"
    )

    coverage = (
        filtered
        .groupby("symbol")
        .size()
        .reset_index(name="Reports")
        .sort_values(
            "Reports",
            ascending=False
        )
        .head(20)
    )

    fig = px.bar(
        coverage,
        x="symbol",
        y="Reports",
        title=(
            "Stocks With Highest "
            "Brokerage Coverage"
        ),
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

    # ── Highest Upside ──────────────────────

    st.subheader(
        "Highest Upside Stocks"
    )

    upside_df = (
        filtered
        .groupby("symbol")
        .agg(
            Avg_Upside=(
                "upside_pct",
                "mean"
            ),
            Reports=("symbol", "count"),
        )
        .reset_index()
    )

    upside_df = upside_df[
        upside_df["Reports"] >= 2
    ]

    upside_df = upside_df.sort_values(
        "Avg_Upside",
        ascending=False
    ).head(20)

    st.dataframe(
        upside_df,
        use_container_width=True,
        hide_index=True,
    )

# ─────────────────────────────────────────────────────────────
# Recent Reports
# ─────────────────────────────────────────────────────────────

with tab6:

    st.subheader(
        "Recent Reports"
    )

    if "date" in filtered.columns:

        recent = filtered[
            filtered["date"] >= (
                pd.Timestamp.now()
                - pd.Timedelta(days=7)
            )
        ]

        st.metric(
            "Reports in Last 7 Days",
            len(recent)
        )

        st.dataframe(
            recent.sort_values(
                "date",
                ascending=False
            ),
            use_container_width=True,
            hide_index=True,
        )

        st.subheader(
            "Future Features"
        )

        st.info(
            "Upgrade/Downgrade detection "
            "will appear here once "
            "historical brokerage "
            "snapshots are stored."
        )

# ─────────────────────────────────────────────────────────────
# Download
# ─────────────────────────────────────────────────────────────

csv = filtered.to_csv(index=False)

st.download_button(
    "Download Brokerage Data",
    csv,
    file_name="brokerage_reports.csv",
    mime="text/csv",
)

# ─────────────────────────────────────────────────────────────
# Footer
# ─────────────────────────────────────────────────────────────

st.divider()

st.caption(
    "Source: Brokerage research reports"
)
