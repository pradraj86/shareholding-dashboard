import streamlit as st
import pandas as pd

from utils import *
st.set_page_config(
    page_title="Bulk & Block Deals",
    layout="wide"
)

st.title("📦 Bulk & Block Deals Analysis")

# =====================================================
# LOAD DATA
# =====================================================

bulk_df = load_bulk_deals()
block_df = load_block_deals()
# =====================================================
# COMBINED DATA
# =====================================================

all_df = pd.concat(
    [bulk_df, block_df],
    ignore_index=True
)

all_df = prepare_bulk_block(
    all_df
)

if "Date" in all_df.columns:
    all_df["Date"] = pd.to_datetime(
        all_df["Date"],
        errors="coerce"
    )

analysis_cols = {
    "Symbol",
    "Client Name",
    "Buy/Sell",
    "Trade_Value"
}

analysis_ready = (
    not all_df.empty
    and analysis_cols.issubset(all_df.columns)
)
# =====================================================
# SEARCH FILTERS
# =====================================================

st.subheader("🔍 Search & Filters")

c1, c2, c3, c4 = st.columns(4)

with c1:
    symbol_search = st.text_input(
        "Symbol",
        placeholder="RELIANCE"
    )

with c2:
    client_search = st.text_input(
        "Client Name",
        placeholder="Mutual Fund"
    )

with c3:
    buy_sell_filter = st.selectbox(
        "Buy / Sell",
        ["All", "BUY", "SELL"]
    )

with c4:
    min_trade_value = st.number_input(
        "Min Trade Value (₹)",
        value=0.0,
        step=1000000.0
    )

date_range = st.date_input(
    "Deal Date Range",
    value=[]
)

def apply_filters(df):

    if df.empty:
        return df

    filtered = df.copy()

    if symbol_search:

        filtered = filtered[
            filtered["Symbol"]
            .astype(str)
            .str.contains(
                symbol_search,
                case=False,
                na=False
            )
        ]

    if client_search:

        filtered = filtered[
            filtered["Client Name"]
            .astype(str)
            .str.contains(
                client_search,
                case=False,
                na=False
            )
        ]

    if buy_sell_filter != "All":

        filtered = filtered[
            filtered["Buy/Sell"]
            .astype(str)
            .str.upper()
            == buy_sell_filter
        ]

    if (
        "Trade_Value" in filtered.columns
        and min_trade_value > 0
    ):

        filtered = filtered[
            filtered["Trade_Value"]
            >= min_trade_value
        ]
    if (
        isinstance(date_range, (list, tuple))
        and len(date_range) == 2
        and "Date" in filtered.columns
    ):

        start_date = pd.Timestamp(date_range[0])

        end_date = pd.Timestamp(date_range[1])

        filtered = filtered[
            (filtered["Date"] >= start_date)
            &
            (filtered["Date"] <= end_date)
        ]
    return filtered


def build_deal_interpretation(df, days=30):

    if df.empty:
        return pd.DataFrame()

    required_cols = {
        "Date",
        "Symbol",
        "Client Name",
        "Buy/Sell",
        "Trade_Value"
    }

    if not required_cols.issubset(df.columns):
        return pd.DataFrame()

    working = df.copy()

    cutoff = (
        pd.Timestamp.today()
        - pd.Timedelta(days=days)
    )

    working = working[
        working["Date"] >= cutoff
    ]

    if working.empty:
        return pd.DataFrame()

    buy_df = working[
        working["Buy/Sell"]
        .astype(str)
        .str.upper()
        == "BUY"
    ]

    sell_df = working[
        working["Buy/Sell"]
        .astype(str)
        .str.upper()
        == "SELL"
    ]

    buy_value = (
        buy_df
        .groupby("Symbol")["Trade_Value"]
        .sum()
    )

    sell_value = (
        sell_df
        .groupby("Symbol")["Trade_Value"]
        .sum()
    )

    buy_deals = (
        buy_df
        .groupby("Symbol")["Trade_Value"]
        .count()
    )

    sell_deals = (
        sell_df
        .groupby("Symbol")["Trade_Value"]
        .count()
    )

    latest_date = (
        working
        .groupby("Symbol")["Date"]
        .max()
    )

    sources = (
        working
        .groupby("Symbol")["Source"]
        .apply(
            lambda values: ", ".join(
                sorted(
                    values
                    .dropna()
                    .astype(str)
                    .unique()
                )
            )
        )
        if "Source" in working.columns
        else pd.Series(dtype=str)
    )

    top_buyers = (
        buy_df
        .groupby(["Symbol", "Client Name"])["Trade_Value"]
        .sum()
        .reset_index()
        .sort_values(
            ["Symbol", "Trade_Value"],
            ascending=[True, False]
        )
        .groupby("Symbol")["Client Name"]
        .first()
    )

    top_sellers = (
        sell_df
        .groupby(["Symbol", "Client Name"])["Trade_Value"]
        .sum()
        .reset_index()
        .sort_values(
            ["Symbol", "Trade_Value"],
            ascending=[True, False]
        )
        .groupby("Symbol")["Client Name"]
        .first()
    )

    result = pd.DataFrame({
        "Buy_Value": buy_value,
        "Sell_Value": sell_value,
        "Buy_Deals": buy_deals,
        "Sell_Deals": sell_deals,
        "Last_Date": latest_date,
        "Source": sources,
        "Top_Buyer": top_buyers,
        "Top_Seller": top_sellers
    }).fillna({
        "Buy_Value": 0,
        "Sell_Value": 0,
        "Buy_Deals": 0,
        "Sell_Deals": 0,
        "Source": "",
        "Top_Buyer": "",
        "Top_Seller": ""
    })

    result["Net_Value"] = (
        result["Buy_Value"]
        - result["Sell_Value"]
    )

    result["Gross_Value"] = (
        result["Buy_Value"]
        + result["Sell_Value"]
    )

    result["Net_Bias_Pct"] = (
        result["Net_Value"]
        .div(
            result[["Buy_Value", "Sell_Value"]]
            .max(axis=1)
            .replace(0, pd.NA)
        )
        .fillna(0)
        * 100
    )

    def classify(row):

        buy_value = row["Buy_Value"]
        sell_value = row["Sell_Value"]
        net_bias = row["Net_Bias_Pct"]

        has_buy = buy_value > 0
        has_sell = sell_value > 0

        if has_buy and has_sell and abs(net_bias) <= 1:
            return (
                "Matched Transfer",
                "Neutral: large buy and sell values are almost equal."
            )

        if net_bias >= 25:
            return (
                "Strong Accumulation",
                "Bullish: buying value is much higher than selling value."
            )

        if net_bias >= 5:
            return (
                "Accumulation",
                "Positive: buying value is higher than selling value."
            )

        if net_bias <= -25:
            return (
                "Strong Distribution",
                "Bearish: selling value is much higher than buying value."
            )

        if net_bias <= -5:
            return (
                "Distribution",
                "Negative: selling value is higher than buying value."
            )

        return (
            "Mixed / Neutral",
            "Neutral: flow is balanced or too small to read directionally."
        )

    labels = result.apply(
        classify,
        axis=1,
        result_type="expand"
    )

    result["Deal_Type"] = labels[0]
    result["Interpretation"] = labels[1]

    result["Buy_Cr"] = (
        result["Buy_Value"] / 1e7
    ).round(2)

    result["Sell_Cr"] = (
        result["Sell_Value"] / 1e7
    ).round(2)

    result["Net_Cr"] = (
        result["Net_Value"] / 1e7
    ).round(2)

    result["Gross_Cr"] = (
        result["Gross_Value"] / 1e7
    ).round(2)

    result["Net_Bias_%"] = (
        result["Net_Bias_Pct"]
    ).round(2)

    result["Buy_Deals"] = (
        result["Buy_Deals"]
        .astype(int)
    )

    result["Sell_Deals"] = (
        result["Sell_Deals"]
        .astype(int)
    )

    result = result.reset_index()

    return result.sort_values(
        "Gross_Value",
        ascending=False
    )

# =====================================================
# METRICS
# =====================================================

c1, c2, c3, c4 = st.columns(4)

with c1:
    st.metric(
        "Bulk Deals",
        len(bulk_df)
    )

with c2:
    st.metric(
        "Block Deals",
        len(block_df)
    )

with c3:
    st.metric(
        "Total Deals",
        len(all_df)
    )

with c4:
    st.metric(
        "Unique Stocks",
        all_df["Symbol"].nunique()
        if not all_df.empty else 0
    )
# =====================================================
# TABS
# =====================================================

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(
    [
        "🔥 Top Accumulation",
        "📉 Top Distribution",
        "🏢 Top Buyers",
        "💰 Top Sellers",
        "📋 Bulk Deals",
        "🏦 Block Deals",
        "⭐ Smart Money",
        "Deal Interpretation"
    ]
)

# =====================================================
# TOP ACCUMULATION
# =====================================================

with tab1:

    st.subheader(
        "Top Accumulation Stocks (30 Days)"
    )

    flow = get_stock_net_flow(
        days=30
    )

    if not flow.empty:

        accum = (
            flow
            .sort_values(
                "Net_Value",
                ascending=False
            )
            .head(50)
        )

        st.dataframe(
            accum,
            width="stretch",
            hide_index=True
        )

    else:

        st.info(
            "No data available."
        )

# =====================================================
# TOP DISTRIBUTION
# =====================================================

with tab2:

    st.subheader(
        "Top Distribution Stocks (30 Days)"
    )

    flow = get_stock_net_flow(
        days=30
    )

    if not flow.empty:

        dist = (
            flow
            .sort_values(
                "Net_Value",
                ascending=True
            )
            .head(50)
        )

        st.dataframe(
            dist,
            width="stretch",
            hide_index=True
        )

    else:

        st.info(
            "No data available."
        )

# =====================================================
# TOP BUYERS
# =====================================================

with tab3:

    st.subheader(
        "Top Buyers (Bulk + Block)"
    )

    if analysis_ready:

        buyers = (
            all_df[
                all_df["Buy/Sell"]
                .astype(str)
                .str.upper()
                == "BUY"
            ]
            .dropna(subset=["Client Name"])
            .groupby("Client Name")
            .agg(
                Trade_Value=("Trade_Value", "sum"),
                Deals=("Symbol", "count")
            )
            .reset_index()
            .sort_values(
                "Trade_Value",
                ascending=False
            )
        )

        buyers["Trade_Value_Cr"] = (
            buyers["Trade_Value"] / 1e7
        ).round(2)

        st.dataframe(
            buyers[
                [
                    "Client Name",
                    "Trade_Value_Cr",
                    "Deals"
                ]
            ].head(100),
            width="stretch",
            hide_index=True
        )

    else:

        st.info(
            "No analysis data available."
        )

with tab8:

    # =====================================================
    # DEAL INTERPRETATION
    # =====================================================

    st.subheader(
        "Deal Interpretation"
    )

    if analysis_ready:

        i1, i2, i3 = st.columns(3)

        with i1:

            interpretation_days = st.selectbox(
                "Analysis Window",
                [7, 15, 30, 60, 90],
                index=2
            )

        with i2:

            interpretation_type = st.selectbox(
                "Deal Signal",
                [
                    "All",
                    "Matched Transfer",
                    "Strong Accumulation",
                    "Accumulation",
                    "Strong Distribution",
                    "Distribution",
                    "Mixed / Neutral"
                ]
            )

        with i3:

            interpretation_min_value = st.number_input(
                "Min Gross Value Cr",
                value=0.0,
                step=100.0
            )

        interpretation = build_deal_interpretation(
            all_df,
            days=interpretation_days
        )

        if symbol_search and not interpretation.empty:

            interpretation = interpretation[
                interpretation["Symbol"]
                .astype(str)
                .str.contains(
                    symbol_search,
                    case=False,
                    na=False
                )
            ]

        if interpretation_type != "All" and not interpretation.empty:

            interpretation = interpretation[
                interpretation["Deal_Type"]
                == interpretation_type
            ]

        if interpretation_min_value > 0 and not interpretation.empty:

            interpretation = interpretation[
                interpretation["Gross_Cr"]
                >= interpretation_min_value
            ]

        if not interpretation.empty:

            matched_count = (
                interpretation["Deal_Type"]
                .eq("Matched Transfer")
                .sum()
            )

            accumulation_count = (
                interpretation["Deal_Type"]
                .isin(
                    [
                        "Strong Accumulation",
                        "Accumulation"
                    ]
                )
                .sum()
            )

            distribution_count = (
                interpretation["Deal_Type"]
                .isin(
                    [
                        "Strong Distribution",
                        "Distribution"
                    ]
                )
                .sum()
            )

            m1, m2, m3, m4 = st.columns(4)

            m1.metric(
                "Stocks Analysed",
                f"{len(interpretation):,}"
            )

            m2.metric(
                "Matched Transfers",
                f"{matched_count:,}"
            )

            m3.metric(
                "Accumulation Signals",
                f"{accumulation_count:,}"
            )

            m4.metric(
                "Distribution Signals",
                f"{distribution_count:,}"
            )

            display_interpretation = interpretation[
                [
                    "Symbol",
                    "Deal_Type",
                    "Interpretation",
                    "Buy_Cr",
                    "Sell_Cr",
                    "Net_Cr",
                    "Gross_Cr",
                    "Net_Bias_%",
                    "Buy_Deals",
                    "Sell_Deals",
                    "Top_Buyer",
                    "Top_Seller",
                    "Last_Date",
                    "Source"
                ]
            ].head(200)

            st.dataframe(
                display_interpretation,
                width="stretch",
                hide_index=True
            )

        else:

            st.info(
                "No interpreted deals match the selected filters."
            )

    else:

        st.info(
            "No analysis data available."
        )

# =====================================================
# TOP SELLERS
# =====================================================

with tab4:

    st.subheader(
        "Top Sellers (Bulk + Block)"
    )

    if analysis_ready:

        sellers = (
            all_df[
                all_df["Buy/Sell"]
                .astype(str)
                .str.upper()
                == "SELL"
            ]
            .dropna(subset=["Client Name"])
            .groupby("Client Name")
            .agg(
                Trade_Value=("Trade_Value", "sum"),
                Deals=("Symbol", "count")
            )
            .reset_index()
            .sort_values(
                "Trade_Value",
                ascending=False
            )
        )

        sellers["Trade_Value_Cr"] = (
            sellers["Trade_Value"] / 1e7
        ).round(2)

        st.dataframe(
            sellers[
                [
                    "Client Name",
                    "Trade_Value_Cr",
                    "Deals"
                ]
            ].head(100),
            width="stretch",
            hide_index=True
        )

    else:

        st.info(
            "No analysis data available."
        )
# =====================================================
# RECENT DEALS
# =====================================================

# =====================================================
# BULK DEALS
# =====================================================

with tab5:

    st.subheader("Bulk Deals")

    bulk_filtered = apply_filters(
        bulk_df
    )

    st.caption(
        f"{len(bulk_filtered):,} records found"
    )

    # -------------------------------------
    # Symbol Summary
    # -------------------------------------

    if (
        symbol_search
        and not bulk_filtered.empty
        and "Trade_Value" in bulk_filtered.columns
    ):

        buy_value = (
            bulk_filtered[
                bulk_filtered["Buy/Sell"]
                .astype(str)
                .str.upper()
                == "BUY"
            ]["Trade_Value"]
            .sum()
        )

        sell_value = (
            bulk_filtered[
                bulk_filtered["Buy/Sell"]
                .astype(str)
                .str.upper()
                == "SELL"
            ]["Trade_Value"]
            .sum()
        )

        c1, c2, c3 = st.columns(3)

        c1.metric(
            "Buy Value",
            f"₹{buy_value/1e7:,.2f} Cr"
        )

        c2.metric(
            "Sell Value",
            f"₹{sell_value/1e7:,.2f} Cr"
        )

        c3.metric(
            "Net Value",
            f"₹{(buy_value-sell_value)/1e7:,.2f} Cr"
        )

    display_df = bulk_filtered.copy()

    if "Trade_Value" in display_df.columns:

        display_df["Trade_Value"] = (
            display_df["Trade_Value"]
            .fillna(0)
            .map(lambda x: f"{x:,.0f}")
        )

    st.download_button(
        "⬇ Download Filtered Bulk Deals",
        bulk_filtered.to_csv(index=False),
        file_name="bulk_filtered.csv",
        mime="text/csv"
    )

    st.dataframe(
        display_df,
        width="stretch",
        hide_index=True
    )
# =====================================================
# BLOCK DEALS
# =====================================================

with tab6:

    st.subheader("Block Deals")

    block_filtered = apply_filters(
        block_df
    )

    st.caption(
        f"{len(block_filtered):,} records found"
    )

    display_df = block_filtered.copy()

    if "Trade_Value" in display_df.columns:

        display_df["Trade_Value"] = (
            display_df["Trade_Value"]
            .fillna(0)
            .map(lambda x: f"{x:,.0f}")
        )

    st.download_button(
        "⬇ Download Filtered Block Deals",
        block_filtered.to_csv(index=False),
        file_name="block_filtered.csv",
        mime="text/csv"
    )

    st.dataframe(
        display_df,
        width="stretch",
        hide_index=True
    )

#=============SMART MONEY========================
with tab7:

    st.subheader(
        "Smart Money Stocks (Bulk + Block)"
    )

    if analysis_ready:

        buys = (
            all_df[
                all_df["Buy/Sell"]
                .astype(str)
                .str.upper()
                == "BUY"
            ]
            .groupby("Symbol")["Trade_Value"]
            .sum()
        )

        sells = (
            all_df[
                all_df["Buy/Sell"]
                .astype(str)
                .str.upper()
                == "SELL"
            ]
            .groupby("Symbol")["Trade_Value"]
            .sum()
        )

        smart = pd.DataFrame({
            "Buy_Value": buys,
            "Sell_Value": sells
        }).fillna(0)

        smart["Net_Value"] = (
            smart["Buy_Value"]
            - smart["Sell_Value"]
        )

        smart = smart.reset_index()

        smart["Buy_Cr"] = (
            smart["Buy_Value"] / 1e7
        ).round(2)

        smart["Sell_Cr"] = (
            smart["Sell_Value"] / 1e7
        ).round(2)

        smart["Net_Cr"] = (
            smart["Net_Value"] / 1e7
        ).round(2)

        smart = smart.sort_values(
            "Net_Value",
            ascending=False
        )

        st.dataframe(
            smart[
                [
                    "Symbol",
                    "Buy_Cr",
                    "Sell_Cr",
                    "Net_Cr"
                ]
            ].head(100),
            width="stretch",
            hide_index=True
        )

    else:

        st.info(
            "No analysis data available."
        )
