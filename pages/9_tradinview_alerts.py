# Integrated TradingView Alerts Page
import streamlit as st
import pandas as pd
from pathlib import Path
import plotly.express as px
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import logging
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from utils import *

# ══════════════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════════════

SERVICE_ACCOUNT_JSON = "service_account.json"
SHEET_ID = "1eCgxl3xVJQXdhPDultBo5i7PbCu57KXsahc1YwBYBmw"
WORKSHEET_NAME = "Sheet1"

LOCAL_CACHE = Path("data/tv_alerts.csv")

COLUMN_MAP = {
    "Date": "date",
    "Ticker": "symbol",
    "Price": "price",
    "Column 1": "bar_time",
    "Alert Type": "alert_type",
}
# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
import logging
from pathlib import Path

# ─────────────────────────────────────────────
# LOG DIRECTORY
# ─────────────────────────────────────────────

LOG_DIR = Path("logs")

LOG_DIR.mkdir(exist_ok=True)

LOG_FILE = LOG_DIR / "tv_alerts.log"

# ─────────────────────────────────────────────
# LOGGER CONFIG
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),                # Console
        logging.FileHandler(LOG_FILE, encoding="utf-8"),  # File
    ]
)

log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════
# GOOGLE SHEETS FETCHER
# ══════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=300)
def fetch_tv_alerts():
    log.info("📡 Fetching fresh TradingView alerts data...")

    import google.auth.transport.requests

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly"
    ]

    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_JSON,
        scopes=scopes,
    )

    # Force fresh token
    request = google.auth.transport.requests.Request()

    creds.refresh(request)

    service = build(
        "sheets",
        "v4",
        credentials=creds,
        cache_discovery=False,
    )

    sheet = service.spreadsheets()

    result = (
        sheet.values()
        .get(
            spreadsheetId=SHEET_ID,
            range=f"{WORKSHEET_NAME}!A:Z"
        )
        .execute()
    )

    values = result.get("values", [])

    if not values:
        return pd.DataFrame()

    headers = values[0]

    rows = values[1:]

    rows = [
        r + [""] * (len(headers) - len(r))
        for r in rows
    ]

    df = pd.DataFrame(rows, columns=headers)

    # Rename columns
    df.rename(columns=COLUMN_MAP, inplace=True)

    # Clean dates
    if "date" in df.columns:

        df["date"] = pd.to_datetime(
            df["date"],
            dayfirst=True,
            errors="coerce",
        )

    if "bar_time" in df.columns:

        df["bar_time"] = pd.to_datetime(
            df["bar_time"],
            utc=True,
            errors="coerce",
        )

    # Price
    if "price" in df.columns:

        df["price"] = pd.to_numeric(
            df["price"],
            errors="coerce",
        )

    # Symbol cleanup
    if "symbol" in df.columns:

        df["symbol"] = (
            df["symbol"]
            .astype(str)
            .str.upper()
            .str.strip()
        )

    df.dropna(subset=["symbol"], inplace=True)

    # Save local backup
    LOCAL_CACHE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    df.to_csv(
        LOCAL_CACHE,
        index=False
    )

    return df.reset_index(drop=True)

# ══════════════════════════════════════════════════════════════════════
# PAGE
# ══════════════════════════════════════════════════════════════════════

st.title("📡 TradingView Alerts")
# Auto refresh every 5 minutes
st_autorefresh(
    interval=5 * 60 * 1000,
    key="tv_alert_refresh"
)
log.info("🔄 Streamlit page auto-refresh triggered")
df_sh, df_fin, df_cf, df_insider, df_snap , df_brokerage, df_tech= load_all_data()
selected_symbols = st.session_state.get("selected_symbols", [])
selected_cats = st.session_state.get("selected_cats", [])
tech_map = {}

if not df_tech.empty:

    tech_map = (
        df_tech
        .set_index("symbol")
        .to_dict("index")
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
# summary = build_summary(
#     df_sh,
#     df_fin,
#     df_cf,df_insider,
#     df_snap,
#     tuple(df_fin["symbol"].unique()),
#     tuple(df_sh["category"].unique()),
# )




score_lookup = (
    summary[
        [
            "symbol",
            "Growth Score",
            "Cashflow Score",
            "Composite Score",
            "Grade",
        ]
    ]
    .drop_duplicates(subset=["symbol"])
    .set_index("symbol")
)


# Manual refresh button
if st.button("🔄 Refresh Alerts"):
    log.info("👆 Manual refresh button clicked")
    fetch_tv_alerts.clear()

    st.rerun()

# Load alerts
try:
    alerts = fetch_tv_alerts()

except Exception as e:

    st.error(f"Could not fetch alerts:\n\n{e}")

    if LOCAL_CACHE.exists():

        st.warning("Using locally cached alerts instead.")

        alerts = pd.read_csv(
            LOCAL_CACHE,
            parse_dates=["date", "bar_time"],
        )

    else:
        st.stop()

if alerts.empty:
    st.info("No TradingView alerts available.")
    st.stop()

alerts = alerts.sort_values(
    "date",
    ascending=False,
)



# Normalize alert symbols
alerts["symbol"] = (
    alerts["symbol"]
    .astype(str)
    .str.upper()
    .str.strip()
    .str.replace("NSE:", "", regex=False)
    .str.replace(".NS", "", regex=False)
)
# ═════════════════════════════════════════════
# PERFORMANCE SCORES
# ═════════════════════════════════════════════


alerts = alerts.merge(
    summary[
        [
            "symbol",
            "Growth Score",
            "Cashflow Score",
            "Composite Score",
            "Grade",
        ]
    ],
    on="symbol",
    how="left"
)

# ══════════════════════════════════════════════════════════════════════
# FILTERS
# ══════════════════════════════════════════════════════════════════════

st.sidebar.header("Filters")

symbols = (
    alerts.sort_values("date", ascending=False)
    ["symbol"]
    .dropna()
    .drop_duplicates()
    .tolist()
)

selected_symbols = st.sidebar.multiselect(
    "Symbols",
    symbols,
    default=symbols,
)

alert_types = sorted(alerts["alert_type"].dropna().unique())

selected_alerts = st.sidebar.multiselect(
    "Alert Types",
    alert_types,
    default=alert_types,
)

filtered = alerts[
    alerts["symbol"].isin(selected_symbols)
    &
    alerts["alert_type"].isin(selected_alerts)
]

# ══════════════════════════════════════════════════════════════════════
# KPI STRIP
# ══════════════════════════════════════════════════════════════════════

k1, k2, k3, k4 = st.columns(4)

k1.metric("Total Alerts", len(filtered))

k2.metric(
    "Unique Stocks",
    filtered["symbol"].nunique(),
)

k3.metric(
    "Alert Types",
    filtered["alert_type"].nunique(),
)

latest_alert = (
    filtered["date"].max()
    if not filtered.empty
    else None
)

k4.metric(
    "Latest Alert",
    latest_alert.strftime("%d-%b %H:%M")
    if pd.notna(latest_alert)
    else "—",
)

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════
# ALERT DISTRIBUTION
# ══════════════════════════════════════════════════════════════════════

st.subheader("Alert Distribution")

alert_dist = (
    filtered["alert_type"]
    .value_counts()
    .reset_index()
)

alert_dist.columns = ["alert_type", "count"]

fig = px.bar(
    alert_dist,
    x="alert_type",
    y="count",
    text="count",
)

fig.update_layout(
    height=400,
    template="plotly_white",
    xaxis_title="Alert Type",
    yaxis_title="Count",
)

st.plotly_chart(fig, width="stretch")

# ══════════════════════════════════════════════════════════════════════
# TOP ALERTED STOCKS
# ══════════════════════════════════════════════════════════════════════

st.subheader("Most Alerted Stocks")

stock_dist = (
    filtered["symbol"]
    .value_counts()
    .head(15)
    .reset_index()
)

stock_dist.columns = ["symbol", "count"]

fig2 = px.bar(
    stock_dist,
    x="symbol",
    y="count",
    text="count",
)

fig2.update_layout(
    height=400,
    template="plotly_white",
    xaxis_title="Stock",
    yaxis_title="Alerts",
)

st.plotly_chart(fig2, width="stretch")

# ══════════════════════════════════════════════════════════════════════
# RECENT ALERTS TABLE
# ══════════════════════════════════════════════════════════════════════

st.subheader("Recent Alerts")

show_cols = [
    "date",
    "symbol",
    "price",
    "alert_type",
    "Growth Score",
    "Cashflow Score",
    "Composite Score",
    "Grade",
]

recent_df = filtered[show_cols].copy()

recent_df.rename(columns={
    "date": "Alert Time",
    "symbol": "Symbol",
    "price": "Price",
    "alert_type": "Alert Type",
}, inplace=True)

st.dataframe(
    recent_df,
    width="stretch",
    height=600,
)

# ══════════════════════════════════════════════════════════════════════
# DOWNLOAD
# ══════════════════════════════════════════════════════════════════════

st.download_button(
    "⬇ Download Alerts CSV",
    filtered.to_csv(index=False).encode(),
    "tv_alerts.csv",
    "text/csv",
)

st.caption(
    f"Last page refresh: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
)