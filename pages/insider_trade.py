from datetime import date, timedelta
from pathlib import Path
import io

import pandas as pd
import plotly.express as px
import streamlit as st

from insider_fetcher import build_insider_summary, fetch_insider_data, insider_score

# ─── Constants ────────────────────────────────────────────────────────────────
INSIDER_FILE  = Path("data/insider_trades.parquet")
BUY_COLOR     = "#1e7e34"
SELL_COLOR    = "#c0392b"
NEUTRAL_COLOR = "#f8f9fa"

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="Insider Trading", page_icon="🔍", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }

div[data-testid="stMetric"] {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 10px 14px;
}
div[data-testid="stMetricLabel"] { font-size: 12px; color: #64748b; }
div[data-testid="stMetricValue"] { font-size: 20px; font-weight: 650; }

.buy-pill  { background:#dcfce7; color:#166534; padding:2px 8px;
             border-radius:6px; font-weight:600; font-size:12px; }
.sell-pill { background:#fee2e2; color:#991b1b; padding:2px 8px;
             border-radius:6px; font-weight:600; font-size:12px; }
.section-note { color:#64748b; font-size:13px; margin-bottom:6px; }
</style>
""", unsafe_allow_html=True)

# ─── Helpers ──────────────────────────────────────────────────────────────────
@st.cache_data(ttl=60 * 30, show_spinner=False)
def load_insider_data(start_date, end_date, hide_small_qty):
    return fetch_insider_data(start_date, end_date, hide_small_qty)

def format_inr(value):
    if pd.isna(value):
        return "-"
    v = float(value)
    if abs(v) >= 1e7: return f"₹{v / 1e7:,.2f} Cr"
    if abs(v) >= 1e5: return f"₹{v / 1e5:,.2f} L"
    return f"₹{v:,.0f}"

def color_signed(value):
    if pd.isna(value): return ""
    if value > 0: return f"color:{BUY_COLOR}; font-weight:600"
    if value < 0: return f"color:{SELL_COLOR}; font-weight:600"
    return ""

def df_style(df, fmt, signed_cols=None):
    """Apply format + green/red coloring in one call."""
    s = df.style.format(fmt, na_rep="-")
    for col in (signed_cols or []):
        if col in df.columns:
            s = s.map(color_signed, subset=[col])
    return s

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🔍 Insider Filters")
    default_end   = date.today()
    default_start = default_end - timedelta(days=7)

    start_date     = st.date_input("Start date", value=default_start)
    end_date       = st.date_input("End date",   value=default_end)
    hide_small_qty = st.checkbox("Hide small quantity deals", value=True)

    if start_date > end_date:
        st.error("Start date must be before end date.")
        st.stop()

    st.markdown("---")
    # Quick date presets
    preset = st.radio("Quick range", ["7 days", "30 days", "90 days"], horizontal=True)
    if st.button("Apply preset", use_container_width=True):
        days_map = {"7 days": 7, "30 days": 30, "90 days": 90}
        end_date   = date.today()
        start_date = end_date - timedelta(days=days_map[preset])

    if st.button("🔄 Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ─── Load data ────────────────────────────────────────────────────────────────
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

# Persist to parquet (silent)
INSIDER_FILE.parent.mkdir(parents=True, exist_ok=True)
df.to_parquet(INSIDER_FILE, index=False)

# ─── Title ────────────────────────────────────────────────────────────────────
st.title("🔍 Insider Trading Analysis")
st.markdown(
    f"<div class='section-note'>Source: Trendlyne Insider/SAST disclosures &nbsp;·&nbsp; "
    f"{len(df):,} records · {start_date} → {end_date}</div>",
    unsafe_allow_html=True,
)

# ─── Inline filters ───────────────────────────────────────────────────────────
def unique_sorted(col):
    return sorted(df[col].dropna().unique().tolist()) if col in df.columns else []

fc1, fc2, fc3, fc4 = st.columns([1.2, 1.2, 1.2, 1.4])
with fc1: selected_actions    = st.multiselect("Action",          unique_sorted("action"),          default=unique_sorted("action"))
with fc2: selected_categories = st.multiselect("Client category", unique_sorted("client_category"), default=unique_sorted("client_category"))
with fc3: selected_modes      = st.multiselect("Mode",            unique_sorted("mode"),             default=[])
with fc4: stock_search        = st.text_input("Search stock / client", placeholder="Symbol or name…")

# ─── Apply filters ────────────────────────────────────────────────────────────
filtered = df.copy()
if selected_actions:    filtered = filtered[filtered["action"].isin(selected_actions)]
if selected_categories: filtered = filtered[filtered["client_category"].isin(selected_categories)]
if selected_modes:      filtered = filtered[filtered["mode"].isin(selected_modes)]
if stock_search:
    needle   = stock_search.strip().lower()
    filtered = filtered[
        filtered["stock"].astype(str).str.lower().str.contains(needle, na=False)
        | filtered["client_name"].astype(str).str.lower().str.contains(needle, na=False)
    ]

# ─── KPI strip ────────────────────────────────────────────────────────────────
buy_value    = filtered.loc[filtered["action"].eq("Acquisition"), "value"].sum()
sell_value   = filtered.loc[filtered["action"].eq("Disposal"),    "value"].sum()
pledge_value = filtered.loc[filtered["action"].eq("Pledge"),      "value"].sum()
net_value    = filtered["signed_value"].sum() if "signed_value" in filtered.columns else 0
net_delta    = "▲ Net Buy" if net_value >= 0 else "▼ Net Sell"

m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("Records",       f"{len(filtered):,}")
m2.metric("Stocks",        f"{filtered['stock'].nunique():,}" if "stock" in filtered.columns else "-")
m3.metric("Acquisition",   format_inr(buy_value))
m4.metric("Disposal",      format_inr(sell_value))
m5.metric("Net Buy/Sell",  format_inr(net_value),  delta=net_delta)
m6.metric("Pledge",        format_inr(pledge_value))

st.markdown("---")

# ─── Charts ───────────────────────────────────────────────────────────────────
ch1, ch2 = st.columns(2)

with ch1:
    val_by_action = (
        filtered.groupby("action", dropna=False)["value"]
        .sum().reset_index().sort_values("value", ascending=False)
    )
    fig = px.bar(
        val_by_action, x="action", y="value",
        title="Disclosed value by action",
        color="action",
        color_discrete_map={"Acquisition": BUY_COLOR, "Disposal": SELL_COLOR, "Pledge": "#f59e0b"},
        text_auto=".2s",
    )
    fig.update_layout(height=340, margin=dict(l=10,r=10,t=46,b=10), showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

with ch2:
    if "signed_value" in filtered.columns:
        net_by_stock = (
            filtered[filtered["action"].isin(["Acquisition", "Disposal"])]
            .groupby("stock", dropna=False)["signed_value"]
            .sum().sort_values(ascending=False).head(15).reset_index()
        )
        fig = px.bar(
            net_by_stock, x="signed_value", y="stock", orientation="h",
            title="Top 15 net buy/sell by stock",
            color="signed_value",
            color_continuous_scale=[SELL_COLOR, NEUTRAL_COLOR, BUY_COLOR],
        )
        fig.update_layout(
            height=340, margin=dict(l=10,r=10,t=46,b=10),
            yaxis={"categoryorder": "total ascending"},
            coloraxis_showscale=False,
        )
        st.plotly_chart(fig, use_container_width=True)

# ─── Second chart row: timeline + category split ──────────────────────────────
if "period" in filtered.columns or "date" in filtered.columns:
    date_col = "date" if "date" in filtered.columns else "period"
    ch3, ch4 = st.columns(2)

    with ch3:
        timeline = (
            filtered.groupby([date_col, "action"], dropna=False)["value"]
            .sum().reset_index()
        )
        fig = px.line(
            timeline, x=date_col, y="value", color="action",
            title="Value over time by action",
            color_discrete_map={"Acquisition": BUY_COLOR, "Disposal": SELL_COLOR, "Pledge": "#f59e0b"},
        )
        fig.update_layout(height=300, margin=dict(l=10,r=10,t=46,b=10))
        st.plotly_chart(fig, use_container_width=True)

    with ch4:
        cat_pie = (
            filtered.groupby("client_category", dropna=False)["value"]
            .sum().reset_index()
        )
        fig = px.pie(
            cat_pie, values="value", names="client_category",
            title="Value split by client category", hole=0.55,
        )
        fig.update_layout(height=300, margin=dict(l=10,r=10,t=46,b=10))
        st.plotly_chart(fig, use_container_width=True)

# ─── Tabbed tables ────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(
    ["📋 Transactions", "🏢 Top Stocks", "👥 Client Categories", "📊 High Traded %"]
)

TABLE_H   = 580
NUM_FMT   = {"quantity": "{:,.0f}", "avg_price": "{:,.1f}",
             "value": "{:,.0f}", "signed_value": "{:,.0f}", "traded_pct": "{:.2f}%"}
SIGN_COLS = ["signed_value"]

TX_COLS = ["stock","client_name","client_category","action",
           "quantity","avg_price","value","signed_value",
           "traded_pct","period","mode","regulation_insider_sast","insider_score"]

with tab1:
    tx_cols = [c for c in TX_COLS if c in filtered.columns]
    table   = filtered.sort_values(["insider_score","value"], ascending=False)[tx_cols]
    st.dataframe(df_style(table, NUM_FMT, SIGN_COLS), use_container_width=True, height=TABLE_H)

with tab2:
    top_stock = pd.DataFrame({
        "disclosed_value":   summary["value_by_stock"],
        "quantity":          summary["quantity_by_stock"],
        "net_buy_sell_value":summary["net_by_stock"],
    }).reset_index(names="stock").sort_values("disclosed_value", ascending=False).head(50)
    st.dataframe(
        df_style(top_stock,
                 {"disclosed_value":"{:,.0f}","quantity":"{:,.0f}","net_buy_sell_value":"{:,.0f}"},
                 ["net_buy_sell_value"]),
        use_container_width=True, height=TABLE_H,
    )

with tab3:
    cat_df = (
        filtered.groupby(["client_category","action"], dropna=False)
        .agg(rows=("stock","size"), value=("value","sum"), quantity=("quantity","sum"))
        .reset_index().sort_values("value", ascending=False)
    )
    st.dataframe(
        df_style(cat_df, {"value":"{:,.0f}","quantity":"{:,.0f}"}),
        use_container_width=True, height=TABLE_H,
    )

with tab4:
    PCT_COLS = ["stock","client_name","client_category","action","quantity","traded_pct","mode","period"]
    pct_cols = [c for c in PCT_COLS if c in filtered.columns]
    top_pct  = filtered.sort_values("traded_pct", ascending=False)[pct_cols].head(50)
    st.dataframe(
        df_style(top_pct, {"quantity":"{:,.0f}","traded_pct":"{:.2f}%"}),
        use_container_width=True, height=TABLE_H,
    )

# ─── Downloads ────────────────────────────────────────────────────────────────
st.markdown("---")
dl1, dl2, _ = st.columns([1, 1, 4])

with dl1:
    buf = io.BytesIO()
    filtered.to_parquet(buf, index=False)
    st.download_button(
        "⬇ Download Parquet",
        data=buf.getvalue(),
        file_name="insider_trading_filtered.parquet",
        mime="application/octet-stream",
        use_container_width=True,
    )

with dl2:
    st.download_button(
        "⬇ Download CSV",
        data=filtered.to_csv(index=False).encode("utf-8"),
        file_name="insider_trading_filtered.csv",
        mime="text/csv",
        use_container_width=True,
    )