import streamlit as st
from utils import *
import pandas as pd
import plotly.express as px

# Load data

df_sh, df_fin, df_cf, df_snap= load_all_data()

# ============================================================================
# Session selections
# ============================================================================

selected_symbols = st.session_state.get("selected_symbols", [])
selected_cats = st.session_state.get("selected_cats", [])

# ============================================================================
# Build summary
# ============================================================================

summary = build_summary(
    df_sh,
    df_fin,
    df_cf,
    df_snap,
    tuple(selected_symbols),
    tuple(selected_cats),
)

filtered_symbols = summary["symbol"].tolist()

# ============================================================================
# Title
# ============================================================================

st.subheader(
    "Combined Shareholding & Cash Flow Heatmap"
)

# ============================================================================
# Heatmap type selector
# ============================================================================

heatmap_type = st.selectbox(

    "Heatmap Type",

    [
        "Shareholding",
        "Cash Flow",
        "Financials",
    ],

    key="heatmap_type",
)

# ============================================================================
# Dynamic metric selector
# ============================================================================
if heatmap_type == "Shareholding":

    metric_choice = st.selectbox(

        "Category",

        [
            c for c in [
                "FIIs",
                "DIIs",
                "Promoters",
                "Public",
            ]
            if c in df_sh["category"].unique()
        ],

        key="hm_sh_metric",
    )

elif heatmap_type == "Cash Flow":

    metric_choice = st.selectbox(

        "Cash Flow Metric",

        [
            m for m in [
                "CFO",
                "True Free Cash Flow",
                "Capex",
                "Net Cash Flow",
                "CFO/OP",
            ]
            if m in df_cf["metric"].unique()
        ],

        key="hm_cf_metric",
    )

else:

    metric_choice = st.selectbox(

        "Financial Metric",

        [
            m for m in [
                "Sales",
                "EBITDA",
                "Net Profit",
                "EPS",
                "EBITDA Margin %",
            ]
            if m in df_fin["metric"].unique()
        ],

        key="hm_fin_metric",
    )

# ============================================================================
# Prepare data dynamically
# ============================================================================

if heatmap_type == "Shareholding":

    hm_data = df_sh[
        (df_sh["symbol"].isin(filtered_symbols)) &
        (df_sh["category"] == metric_choice)
    ]

    hm_data = sort_quarters(hm_data)

    value_col = "pct"

    period_col = "quarter"

    title = f"{metric_choice} % Heatmap"

    colorscale = {
        "FIIs": "Blues",
        "DIIs": "Greens",
        "Promoters": "Greys",
        "Public": "Oranges",
    }.get(metric_choice, "Blues")

    xaxis_title = "Quarter"

    hover_label = "Quarter"

    value_suffix = "%"
elif heatmap_type == "Financials":

    hm_data = df_fin[
        (df_fin["symbol"].isin(filtered_symbols)) &
        (df_fin["metric"] == metric_choice)
    ]

    hm_data = sort_periods(hm_data)

    # Keep only quarterly data
    hm_data = hm_data[
        hm_data["freq"] == "quarterly"
    ]

    # From 2015 onward
    hm_data = hm_data[
        hm_data["period"]
        .astype(str)
        .str.extract(r'(\d{4})')[0]
        .astype(float) >= 2015
    ]

    value_col = "value"

    period_col = "period"

    title = f"{metric_choice} Quarterly Heatmap"

    colorscale = {
        "Sales": "Blues",
        "EBITDA": "Greens",
        "Net Profit": "Purples",
        "EPS": "Oranges",
        "EBITDA Margin %": "Greys",
    }.get(metric_choice, "Blues")

    xaxis_title = "Quarter"

    hover_label = "Quarter"

    value_suffix = (
        "%"
        if "Margin" in metric_choice
        else ""
    )
else:

    hm_data = df_cf[
        (df_cf["symbol"].isin(filtered_symbols)) &
        (df_cf["metric"] == metric_choice)
    ]

    hm_data = sort_periods(hm_data)
    hm_data = hm_data[
    hm_data["period"]
    .astype(str)
    .str.extract(r'(\d{4})')[0]
    .astype(float) >= 2020
]

    # Convert annual labels to pure year
    hm_data["period"] = (
        hm_data["period"]
        .astype(str)
        .str.extract(r'(\d{4})')[0]
    )

    value_col = "value"

    period_col = "period"

    title = f"{metric_choice} Heatmap"

    colorscale = {
    "CFO": "Greens",
    "True Free Cash Flow": "Blues",
    "Capex": "Oranges",
    "Net Cash Flow": "Purples",
    "CFO/OP": "Greys",
}.get(metric_choice, "Blues")

    xaxis_title = "Year"

    hover_label = "Year"

    value_suffix = ""

# ============================================================================
# Empty check
# ============================================================================

if hm_data.empty:

    st.info(
        "No data available for selected combination."
    )

# ============================================================================
# Heatmap
# ============================================================================

else:

    # ============================================================================
# Pagination
# ============================================================================

    symbols_per_page = 20

    all_symbols = sorted(
        hm_data["symbol"].unique()
    )

    total_pages = max(
        1,
        (len(all_symbols) - 1) // symbols_per_page + 1
    )

    page = st.number_input(

        "Page",

        min_value=1,

        max_value=total_pages,

        value=1,

        step=1,
    )

    start_idx = (page - 1) * symbols_per_page

    end_idx = start_idx + symbols_per_page

    page_symbols = all_symbols[start_idx:end_idx]

    hm_data = hm_data[
        hm_data["symbol"].isin(page_symbols)
    ]

    # Pivot

    pivot = hm_data.pivot_table(

        index="symbol",

        columns=period_col,

        values=value_col,

        aggfunc="first",
    )

    # Chronological sorting

    sorted_cols = sorted(

        pivot.columns.astype(str),

        key=make_period_key
    )

    pivot = pivot.reindex(
        columns=sorted_cols
    )

    # Sort stocks by latest period

    pivot = pivot.sort_values(

        sorted_cols[-1],

        ascending=False
    )

    # Create heatmap

    fig_hm = px.imshow(

        pivot,

        aspect="auto",

        color_continuous_scale=colorscale,

        labels=dict(
            color=metric_choice
        ),

        title=title,
    )

    # Text + hover

    fig_hm.update_traces(

        hovertemplate=(
            "<b>%{y}</b><br>"
            f"{hover_label}: "
            "%{x}<br>"
            "Value: %{z:.2f}"
            f"{value_suffix}"
            "<extra></extra>"
        ),

        texttemplate=(
            "%{z:.1f}" + value_suffix
        ),

        textfont_size=14,
    )

    # Layout

    fig_hm.update_layout(

        height=max(
            400,
            len(pivot) * 20 + 100
        ),

        xaxis_title=xaxis_title,

        margin=dict(
            l=100,
            r=20,
            t=60,
            b=60,
        ),
    )

    # Preserve order

    fig_hm.update_xaxes(

        categoryorder="array",

        categoryarray=sorted_cols
    )

    # Plot

    st.plotly_chart(

        fig_hm,

        width="stretch"
    )
