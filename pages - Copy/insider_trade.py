from datetime import date, timedelta
import io

import pandas as pd
import plotly.express as px
import streamlit as st

from insider_fetcher import build_insider_summary, fetch_insider_data, insider_score


st.title("Insider Trading Analysis")
st.caption("Source: Trendlyne Insider/SAST disclosures")


@st.cache_data(ttl=60 * 30, show_spinner=False)
def load_insider_data(start_date, end_date, hide_small_qty):
    return fetch_insider_data(start_date, end_date, hide_small_qty)


def format_inr(value):
    if pd.isna(value):
        return "-"
    value = float(value)
    if abs(value) >= 1e7:
        return f"Rs {value / 1e7:,.2f} Cr"
    if abs(value) >= 1e5:
        return f"Rs {value / 1e5:,.2f} L"
    return f"Rs {value:,.0f}"


def color_signed_value(value):
    if pd.isna(value):
        return ""
    if value > 0:
        return "color: #1e7e34; font-weight: 600"
    if value < 0:
        return "color: #c0392b; font-weight: 600"
    return ""


with st.sidebar:
    st.markdown("### Insider filters")
    default_end = date.today()
    default_start = default_end - timedelta(days=7)

    start_date = st.date_input("Start date", value=default_start)
    end_date = st.date_input("End date", value=default_end)
    hide_small_qty = st.checkbox("Hide small quantity deals", value=True)

    if start_date > end_date:
        st.error("Start date must be before end date.")
        st.stop()

    if st.button("Refresh insider data", width="stretch"):
        st.cache_data.clear()
        st.rerun()


with st.spinner("Fetching insider disclosures..."):
    try:
        df = load_insider_data(start_date, end_date, hide_small_qty)
    except Exception as exc:
        st.error(f"Could not fetch insider trading data: {exc}")
        st.stop()

if df.empty:
    st.info("No insider trading disclosures found for the selected period.")
    st.stop()

df = df.copy()
df["insider_score"] = df.apply(insider_score, axis=1)
summary = build_insider_summary(df)

actions = sorted(df["action"].dropna().unique().tolist()) if "action" in df.columns else []
categories = sorted(df["client_category"].dropna().unique().tolist()) if "client_category" in df.columns else []
modes = sorted(df["mode"].dropna().unique().tolist()) if "mode" in df.columns else []

filter_col1, filter_col2, filter_col3, filter_col4 = st.columns([1.2, 1.2, 1.2, 1.4])
with filter_col1:
    selected_actions = st.multiselect("Action", actions, default=actions)
with filter_col2:
    selected_categories = st.multiselect("Client category", categories, default=categories)
with filter_col3:
    selected_modes = st.multiselect("Mode", modes, default=[])
with filter_col4:
    stock_search = st.text_input("Stock/client search", placeholder="Type stock or client name")

filtered = df.copy()
if selected_actions:
    filtered = filtered[filtered["action"].isin(selected_actions)]
if selected_categories:
    filtered = filtered[filtered["client_category"].isin(selected_categories)]
if selected_modes:
    filtered = filtered[filtered["mode"].isin(selected_modes)]
if stock_search:
    needle = stock_search.strip().lower()
    filtered = filtered[
        filtered["stock"].astype(str).str.lower().str.contains(needle, na=False)
        | filtered["client_name"].astype(str).str.lower().str.contains(needle, na=False)
    ]

buy_value = filtered.loc[filtered["action"].eq("Acquisition"), "value"].sum()
sell_value = filtered.loc[filtered["action"].eq("Disposal"), "value"].sum()
pledge_value = filtered.loc[filtered["action"].eq("Pledge"), "value"].sum()
net_value = filtered["signed_value"].sum() if "signed_value" in filtered.columns else 0

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Rows", f"{len(filtered):,}")
m2.metric("Acquisition", format_inr(buy_value))
m3.metric("Disposal", format_inr(sell_value))
m4.metric("Net buy/sell", format_inr(net_value))
m5.metric("Pledge", format_inr(pledge_value))

st.markdown("---")

chart_col1, chart_col2 = st.columns(2)
with chart_col1:
    value_by_action = (
        filtered.groupby("action", dropna=False)["value"]
        .sum()
        .reset_index()
        .sort_values("value", ascending=False)
    )
    fig = px.bar(
        value_by_action,
        x="action",
        y="value",
        title="Disclosed value by action",
        text_auto=".2s",
    )
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig, width="stretch")

with chart_col2:
    net_by_stock = (
        filtered[filtered["action"].isin(["Acquisition", "Disposal"])]
        .groupby("stock", dropna=False)["signed_value"]
        .sum()
        .sort_values(ascending=False)
        .head(15)
        .reset_index()
    )
    fig = px.bar(
        net_by_stock,
        x="signed_value",
        y="stock",
        orientation="h",
        title="Top net buy/sell value by stock",
        color="signed_value",
        color_continuous_scale=["#c0392b", "#f8f9fa", "#1e7e34"],
    )
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=50, b=10), yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig, width="stretch")

tab1, tab2, tab3, tab4 = st.tabs(
    ["Transactions", "Top stocks", "Client categories", "High traded percent"]
)

display_cols = [
    "stock",
    "client_name",
    "client_category",
    "action",
    "quantity",
    "avg_price",
    "value",
    "signed_value",
    "traded_pct",
    "period",
    "mode",
    "regulation_insider_sast",
    "insider_score",
]
display_cols = [col for col in display_cols if col in filtered.columns]

with tab1:
    table = filtered.sort_values(["insider_score", "value"], ascending=False)[display_cols]
    styled = (
        table.style.format(
            {
                "quantity": "{:,.0f}",
                "avg_price": "{:,.1f}",
                "value": "{:,.0f}",
                "signed_value": "{:,.0f}",
                "traded_pct": "{:.2f}%",
            },
            na_rep="-",
        )
        .map(color_signed_value, subset=["signed_value"] if "signed_value" in table.columns else [])
    )
    st.dataframe(styled, width="stretch", height=620)

with tab2:
    top_stock = pd.DataFrame(
        {
            "disclosed_value": summary["value_by_stock"],
            "quantity": summary["quantity_by_stock"],
            "net_buy_sell_value": summary["net_by_stock"],
        }
    ).reset_index(names="stock")
    top_stock = top_stock.sort_values("disclosed_value", ascending=False).head(50)
    st.dataframe(
        top_stock.style.format(
            {
                "disclosed_value": "{:,.0f}",
                "quantity": "{:,.0f}",
                "net_buy_sell_value": "{:,.0f}",
            },
            na_rep="-",
        ).map(color_signed_value, subset=["net_buy_sell_value"]),
        width="stretch",
        height=520,
    )

with tab3:
    category_df = (
        filtered.groupby(["client_category", "action"], dropna=False)
        .agg(rows=("stock", "size"), value=("value", "sum"), quantity=("quantity", "sum"))
        .reset_index()
        .sort_values("value", ascending=False)
    )
    st.dataframe(
        category_df.style.format({"value": "{:,.0f}", "quantity": "{:,.0f}"}, na_rep="-"),
        width="stretch",
        height=520,
    )

with tab4:
    top_pct_cols = [
        "stock",
        "client_name",
        "client_category",
        "action",
        "quantity",
        "traded_pct",
        "mode",
        "period",
    ]
    top_pct_cols = [col for col in top_pct_cols if col in filtered.columns]
    top_pct = filtered.sort_values("traded_pct", ascending=False)[top_pct_cols].head(50)
    st.dataframe(
        top_pct.style.format({"quantity": "{:,.0f}", "traded_pct": "{:.2f}%"}, na_rep="-"),
        width="stretch",
        height=520,
    )

buffer = io.BytesIO()
filtered.to_parquet(buffer, index=False)

st.download_button(
    "Download filtered insider data",
    data=buffer.getvalue(),
    file_name="insider_trading_analysis.parquet",
    mime="application/octet-stream",
)
