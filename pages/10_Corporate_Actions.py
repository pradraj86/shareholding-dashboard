import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path

from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, ColumnsAutoSizeMode



st.set_page_config(
    page_title="Corporate Actions",
    page_icon="📢",
    layout="wide"
)

st.title("📢 Corporate Announcements")
st.caption("Source: NSE PR Bhavcopy")

CORP_FILE = Path(
    "data/corporate_actions_all.parquet"
)

@st.cache_data(ttl=3600)
def load_corporate_actions():

    if not CORP_FILE.exists():
        return pd.DataFrame()

    return pd.read_parquet(CORP_FILE)


def categorize_announcement(text):

    t = str(text).upper()

    if "INVESTOR" in t or "ANALYST" in t:
        return "Investor Meet"

    elif "BOARD MEETING" in t:
        return "Board Meeting"

    elif "PRESS RELEASE" in t:
        return "Press Release"

    elif "DIVIDEND" in t:
        return "Dividend"

    elif "ACQUISITION" in t:
        return "Acquisition"

    elif "MERGER" in t or "AMALGAMATION" in t:
        return "Merger"

    elif (
        "DIRECTOR" in t
        or "MANAGEMENT" in t
        or "APPOINTMENT" in t
        or "RESIGNATION" in t
        or "KMP" in t
    ):
        return "Management Change"

    elif (
        "QIP" in t
        or "QUALIFIED INSTITUTIONAL PLACEMENT" in t
        or "FUND RAISING" in t
    ):
        return "Fund Raising"

    elif "ALLOTMENT" in t:
        return "Allotment"

    elif "ESOP" in t:
        return "ESOP"

    elif "TRADING WINDOW" in t:
        return "Trading Window"

    else:
        return "Other"


df = load_corporate_actions()
st.write("Rows in parquet:", len(df))
if df.empty:

    st.warning(
        "No corporate actions data found.\n\n"
        "Run corporate_actions_fetcher.py first."
    )

    st.stop()

# ----------------------------
# Prepare Data
# ----------------------------

df = df.copy()

df["date"] = pd.to_datetime(
    df["date"],
    errors="coerce"
)

df["announcement_category"] = (
    df["announcement_type"]
    .fillna("")
    .apply(categorize_announcement)
)

# ----------------------------
# Sidebar Filters
# ----------------------------

with st.sidebar:

    st.header("Filters")

    search_symbol = st.text_input(
        "Search Symbol"
    )

    categories = sorted(
        df["announcement_category"]
        .dropna()
        .unique()
        .tolist()
    )

    selected_categories = st.multiselect(
        "Category",
        options=categories,
        default=[]
    )

    min_date = df["date"].min().date()
    max_date = df["date"].max().date()

    date_range = st.date_input(
        "Date Range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )

    st.divider()
    important_only = st.checkbox("Important Events Only")
    IMPORTANT = [
        "Investor Meet", "Management Change", "Board Meeting",
        "Dividend", "Acquisition", "Merger", "Fund Raising"
    ]

# ----------------------------
# Filters
# ----------------------------

filtered = df.copy()

if search_symbol:

    filtered = filtered[
        filtered["symbol"]
        .astype(str)
        .str.upper()
        .str.contains(
            search_symbol.upper(),
            na=False
        )
    ]

if selected_categories:

    filtered = filtered[
        filtered["announcement_category"]
        .isin(selected_categories)
    ]

if (
    isinstance(date_range, tuple)
    and len(date_range) == 2
):

    start_date, end_date = date_range

    filtered = filtered[
        filtered["date"]
        .between(
            pd.to_datetime(start_date),
            pd.to_datetime(end_date)
        )
    ]

if important_only:
    filtered = filtered[
        filtered["announcement_category"].isin(IMPORTANT)
    ]

# ----------------------------
# KPIs
# ----------------------------

c1, c2, c3, c4, c5 = st.columns(5)

c1.metric(
    "Announcements",
    len(filtered)
)

c2.metric(
    "Investor Meets",
    (
        filtered["announcement_category"]
        == "Investor Meet"
    ).sum()
)

c3.metric(
    "Management Changes",
    (
        filtered["announcement_category"]
        == "Management Change"
    ).sum()
)

c4.metric(
    "Board Meetings",
    (
        filtered["announcement_category"]
        == "Board Meeting"
    ).sum()
)

c5.metric(
    "Acquisitions",
    (
        filtered["announcement_category"]
        == "Acquisition"
    ).sum()
)

st.divider()

# ----------------------------
# Charts
# ----------------------------

col1, col2 = st.columns(2)

with col1:

    cat_counts = (
        filtered["announcement_category"]
        .value_counts()
        .reset_index()
    )

    cat_counts.columns = [
        "Category",
        "Count"
    ]

    fig = px.bar(
        cat_counts,
        x="Category",
        y="Count",
        title="Announcement Categories"
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

with col2:

    stock_counts = (
        filtered
        .groupby("symbol")
        .size()
        .reset_index(name="Count")
        .sort_values(
            "Count",
            ascending=False
        )
        .head(20)
    )

    fig = px.bar(
        stock_counts,
        x="Count",
        y="symbol",
        orientation="h",
        title="Most Active Stocks"
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

st.divider()

# ----------------------------
# Data Table
# ----------------------------

st.subheader(
    "Corporate Announcements"
)

filtered = filtered.sort_values(
    "date",
    ascending=False
)

# Show truncated text in cell; full text on tooltip/expand
filtered["announcement_short"] = (
    filtered["announcement_text"]
    .fillna("")
    .str[:150]
    + filtered["announcement_text"].fillna("").apply(
        lambda x: "…" if len(str(x)) > 150 else ""
    )
)

display_cols = [
    c for c in [
        "date",
        "symbol",
        "company",
        "announcement_category",
        "announcement_type",
        "announcement_short",
        "announcement_text",   # hidden, used as tooltip
    ]
    if c in filtered.columns
]

grid_df = filtered[display_cols].copy()
grid_df["date"] = grid_df["date"].dt.strftime("%Y-%m-%d")

gb = GridOptionsBuilder.from_dataframe(grid_df)
gb.configure_default_column(
    resizable=True,
    sortable=True,
    filter=True,
    wrapText=True,
    autoHeight=True,
)

gb.configure_column("date",          width=110, pinned="left")
gb.configure_column("symbol",        width=120, pinned="left")
gb.configure_column("company",       width=220)
gb.configure_column("announcement_category", width=160, header_name="Category")
gb.configure_column("announcement_type",     width=200, header_name="Type")
gb.configure_column(
    "announcement_short",
    header_name="Announcement",
    flex=1,                   # takes all remaining width
    minWidth=300,
    tooltipField="announcement_text",   # hover shows full text
    wrapText=True,
    autoHeight=True,
)
gb.configure_column("announcement_text", hide=True)  # hidden – only for tooltip

gb.configure_pagination(
    paginationAutoPageSize=False,
    paginationPageSize=25
)
gb.configure_grid_options(
    tooltipShowDelay=200,
    rowHeight=60,
    domLayout="normal",
)

grid_options = gb.build()

AgGrid(
    grid_df,
    gridOptions=grid_options,
    update_mode=GridUpdateMode.NO_UPDATE,
    columns_auto_size_mode=ColumnsAutoSizeMode.NO_AUTOSIZE,
    use_container_width=True,
    height=600,
    allow_unsafe_jscode=True,
    theme="streamlit",
)

# ----------------------------
# Download
# ----------------------------

csv = filtered.to_csv(
    index=False
).encode("utf-8")

st.download_button(
    "⬇ Download CSV",
    csv,
    file_name="corporate_actions.csv",
    mime="text/csv"
)