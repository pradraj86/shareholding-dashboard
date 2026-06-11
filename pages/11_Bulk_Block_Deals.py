import streamlit as st
import pandas as pd

from utils import *

st.set_page_config(
    page_title="Bulk & Block Deals",
    layout="wide"
)

# =====================================================
# LOAD DATA
# =====================================================

bulk_df = load_bulk_deals()
block_df = load_block_deals()

# =====================================================
# COMBINED DATA
# =====================================================

all_df = pd.concat([bulk_df, block_df], ignore_index=True)
all_df = prepare_bulk_block(all_df)

if "Date" in all_df.columns:
    all_df["Date"] = pd.to_datetime(all_df["Date"], errors="coerce")

if "Date" in bulk_df.columns:
    bulk_df["Date"] = pd.to_datetime(bulk_df["Date"], errors="coerce")

if "Date" in block_df.columns:
    block_df["Date"] = pd.to_datetime(block_df["Date"], errors="coerce")

analysis_cols = {"Symbol", "Client Name", "Buy/Sell", "Trade_Value"}
analysis_ready = not all_df.empty and analysis_cols.issubset(all_df.columns)

# =====================================================
# CSS STYLING
# =====================================================

st.markdown("""
<style>
/* ---- Base ---- */
[data-testid="stAppViewContainer"] {
    background: #0e1117;
}
[data-testid="stSidebar"] {
    background: #161b24;
}

/* ---- Filter card ---- */
.filter-card {
    background: #161b24;
    border: 1px solid #2a3040;
    border-radius: 10px;
    padding: 1rem 1.2rem 0.8rem;
    margin-bottom: 1rem;
}
.filter-card-title {
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #6b7a99;
    margin-bottom: 0.6rem;
}

/* ---- KPI strip ---- */
.kpi-row {
    display: flex;
    gap: 0.75rem;
    margin-bottom: 1rem;
    flex-wrap: wrap;
}
.kpi-card {
    flex: 1;
    min-width: 130px;
    background: #161b24;
    border: 1px solid #2a3040;
    border-radius: 10px;
    padding: 0.8rem 1rem;
    text-align: center;
}
.kpi-label {
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #6b7a99;
    margin-bottom: 0.3rem;
}
.kpi-value {
    font-size: 1.35rem;
    font-weight: 700;
    color: #e2e8f0;
    font-family: monospace;
}
.kpi-value.green  { color: #34d399; }
.kpi-value.red    { color: #f87171; }
.kpi-value.blue   { color: #60a5fa; }
.kpi-value.amber  { color: #fbbf24; }

/* ---- Signal badges ---- */
.badge {
    display: inline-block;
    padding: 2px 9px;
    border-radius: 9999px;
    font-size: 0.72rem;
    font-weight: 600;
    white-space: nowrap;
}
.badge-strong-accum { background: #064e3b; color: #6ee7b7; }
.badge-accum        { background: #065f46; color: #a7f3d0; }
.badge-strong-dist  { background: #7f1d1d; color: #fca5a5; }
.badge-dist         { background: #991b1b; color: #fecaca; }
.badge-transfer     { background: #1e3a5f; color: #93c5fd; }
.badge-neutral      { background: #374151; color: #9ca3af; }

/* ---- Alert box ---- */
.insight-box {
    background: #1a2035;
    border-left: 3px solid #60a5fa;
    border-radius: 0 8px 8px 0;
    padding: 0.7rem 1rem;
    font-size: 0.82rem;
    color: #cbd5e1;
    margin-bottom: 0.8rem;
}
.insight-box.bullish { border-color: #34d399; }
.insight-box.bearish { border-color: #f87171; }
.insight-box.neutral { border-color: #6b7a99; }

/* ---- Section headers ---- */
.section-header {
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #6b7a99;
    border-bottom: 1px solid #2a3040;
    padding-bottom: 0.4rem;
    margin: 0.8rem 0 0.6rem;
}
</style>
""", unsafe_allow_html=True)

# =====================================================
# PAGE HEADER + GLOBAL METRICS
# =====================================================

st.markdown("## 📦 Bulk & Block Deals")

# Build global KPIs
total_buy_val  = all_df.loc[all_df["Buy/Sell"].astype(str).str.upper() == "BUY",  "Trade_Value"].sum() if analysis_ready else 0
total_sell_val = all_df.loc[all_df["Buy/Sell"].astype(str).str.upper() == "SELL", "Trade_Value"].sum() if analysis_ready else 0
net_flow       = total_buy_val - total_sell_val
unique_stocks  = all_df["Symbol"].nunique() if not all_df.empty else 0

net_color = "green" if net_flow >= 0 else "red"
net_sign  = "+" if net_flow >= 0 else ""

st.markdown(f"""
<div class="kpi-row">
  <div class="kpi-card">
    <div class="kpi-label">Bulk Deals</div>
    <div class="kpi-value blue">{len(bulk_df):,}</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">Block Deals</div>
    <div class="kpi-value blue">{len(block_df):,}</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">Unique Stocks</div>
    <div class="kpi-value amber">{unique_stocks:,}</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">Total Buy Flow</div>
    <div class="kpi-value green">₹{total_buy_val/1e7:,.0f} Cr</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">Total Sell Flow</div>
    <div class="kpi-value red">₹{total_sell_val/1e7:,.0f} Cr</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">Net Flow</div>
    <div class="kpi-value {net_color}">{net_sign}₹{net_flow/1e7:,.0f} Cr</div>
  </div>
</div>
""", unsafe_allow_html=True)

# =====================================================
# SHARED FILTER PANEL
# =====================================================

st.markdown('<div class="filter-card"><div class="filter-card-title">🔍 Filters — apply across all tabs</div>', unsafe_allow_html=True)

fc1, fc2, fc3, fc4, fc5 = st.columns([2, 2, 1.5, 1.5, 2])

with fc1:
    symbol_search = st.text_input("Symbol", placeholder="e.g. RELIANCE", label_visibility="visible")

with fc2:
    client_search = st.text_input("Client Name", placeholder="e.g. SBI MF", label_visibility="visible")

with fc3:
    buy_sell_filter = st.selectbox("Buy / Sell", ["All", "BUY", "SELL"])

with fc4:
    min_trade_value = st.number_input("Min Value (₹ Cr)", value=0.0, step=10.0)
    min_trade_value_raw = min_trade_value * 1e7

with fc5:
    date_range = st.date_input("Date Range", value=[])

st.markdown("</div>", unsafe_allow_html=True)


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    filtered = df.copy()

    if symbol_search:
        filtered = filtered[
            filtered["Symbol"].astype(str).str.contains(symbol_search, case=False, na=False)
        ]
    if client_search:
        filtered = filtered[
            filtered["Client Name"].astype(str).str.contains(client_search, case=False, na=False)
        ]
    if buy_sell_filter != "All":
        filtered = filtered[filtered["Buy/Sell"].astype(str).str.upper() == buy_sell_filter]
    if min_trade_value_raw > 0 and "Trade_Value" in filtered.columns:
        filtered = filtered[filtered["Trade_Value"] >= min_trade_value_raw]
    if (
        isinstance(date_range, (list, tuple))
        and len(date_range) == 2
        and "Date" in filtered.columns
    ):
        filtered = filtered[
            (filtered["Date"] >= pd.Timestamp(date_range[0]))
            & (filtered["Date"] <= pd.Timestamp(date_range[1]))
        ]
    return filtered


# =====================================================
# INSIGHT GENERATOR
# =====================================================

def generate_insights(df: pd.DataFrame) -> list[dict]:
    """Return list of {level, text} insight dicts."""
    if df.empty:
        return []

    insights = []

    buy_df  = df[df["Buy/Sell"].astype(str).str.upper() == "BUY"]
    sell_df = df[df["Buy/Sell"].astype(str).str.upper() == "SELL"]
    buy_val  = buy_df["Trade_Value"].sum()
    sell_val = sell_df["Trade_Value"].sum()
    net_val  = buy_val - sell_val

    # Net flow sentiment
    if buy_val + sell_val > 0:
        bias_pct = net_val / max(buy_val, sell_val) * 100
        if bias_pct >= 25:
            insights.append({"level": "bullish", "text": f"Strong institutional accumulation — net buying bias of {bias_pct:.0f}% (₹{net_val/1e7:,.0f} Cr net inflow)."})
        elif bias_pct >= 5:
            insights.append({"level": "bullish", "text": f"Moderate accumulation detected — buying exceeds selling by {bias_pct:.0f}% (₹{net_val/1e7:,.0f} Cr net)."})
        elif bias_pct <= -25:
            insights.append({"level": "bearish", "text": f"Strong institutional distribution — net selling bias of {abs(bias_pct):.0f}% (₹{abs(net_val)/1e7:,.0f} Cr net outflow)."})
        elif bias_pct <= -5:
            insights.append({"level": "bearish", "text": f"Moderate distribution — selling exceeds buying by {abs(bias_pct):.0f}%."})
        else:
            insights.append({"level": "neutral", "text": f"Flow is broadly balanced — buy/sell ratio near parity. Could indicate matched transfers."})

    # Top accumulation stock
    if not buy_df.empty and "Symbol" in buy_df.columns:
        top_buy_sym = buy_df.groupby("Symbol")["Trade_Value"].sum().idxmax()
        top_buy_val = buy_df.groupby("Symbol")["Trade_Value"].sum().max()
        insights.append({"level": "bullish", "text": f"Highest single-stock buying: <b>{top_buy_sym}</b> attracted ₹{top_buy_val/1e7:,.0f} Cr in buy-side flow."})

    # Top distribution stock
    if not sell_df.empty and "Symbol" in sell_df.columns:
        top_sell_sym = sell_df.groupby("Symbol")["Trade_Value"].sum().idxmax()
        top_sell_val = sell_df.groupby("Symbol")["Trade_Value"].sum().max()
        insights.append({"level": "bearish", "text": f"Highest single-stock selling: <b>{top_sell_sym}</b> saw ₹{top_sell_val/1e7:,.0f} Cr in sell-side flow."})

    # Block deal concentration check
    if "Source" in df.columns:
        block_only = df[df["Source"].astype(str).str.upper() == "BLOCK"]
        if not block_only.empty:
            block_pct = block_only["Trade_Value"].sum() / df["Trade_Value"].sum() * 100
            if block_pct >= 60:
                insights.append({"level": "neutral", "text": f"Block deals dominate — {block_pct:.0f}% of total value. These are pre-negotiated; interpret direction with caution."})

    # Concentrated client
    if "Client Name" in buy_df.columns and not buy_df.empty:
        top_client_buy = buy_df.groupby("Client Name")["Trade_Value"].sum()
        top_client_name = top_client_buy.idxmax()
        top_client_val  = top_client_buy.max()
        if top_client_val / max(buy_val, 1) >= 0.3:
            insights.append({"level": "neutral", "text": f"Concentrated buyer: <b>{top_client_name}</b> accounts for {top_client_val/buy_val*100:.0f}% of total buy value — watch for follow-through."})

    return insights


def render_insights(insights: list[dict]) -> None:
    if not insights:
        return
    st.markdown('<div class="section-header">💡 Key Insights</div>', unsafe_allow_html=True)
    for ins in insights:
        st.markdown(f'<div class="insight-box {ins["level"]}">{ins["text"]}</div>', unsafe_allow_html=True)


# =====================================================
# DEAL INTERPRETATION
# =====================================================

def build_deal_interpretation(df: pd.DataFrame, days: int = 30) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    required = {"Date", "Symbol", "Client Name", "Buy/Sell", "Trade_Value"}
    if not required.issubset(df.columns):
        return pd.DataFrame()

    working = df.copy()
    cutoff  = pd.Timestamp.today() - pd.Timedelta(days=days)
    working = working[working["Date"] >= cutoff]
    if working.empty:
        return pd.DataFrame()

    buy_df  = working[working["Buy/Sell"].astype(str).str.upper() == "BUY"]
    sell_df = working[working["Buy/Sell"].astype(str).str.upper() == "SELL"]

    buy_value  = buy_df.groupby("Symbol")["Trade_Value"].sum()
    sell_value = sell_df.groupby("Symbol")["Trade_Value"].sum()
    buy_deals  = buy_df.groupby("Symbol")["Trade_Value"].count()
    sell_deals = sell_df.groupby("Symbol")["Trade_Value"].count()
    latest_date = working.groupby("Symbol")["Date"].max()

    sources = (
        working.groupby("Symbol")["Source"].apply(
            lambda v: ", ".join(sorted(v.dropna().astype(str).unique()))
        )
        if "Source" in working.columns
        else pd.Series(dtype=str)
    )

    def top_client(gdf, sym_col="Symbol", client_col="Client Name"):
        return (
            gdf.groupby([sym_col, client_col])["Trade_Value"]
            .sum().reset_index()
            .sort_values([sym_col, "Trade_Value"], ascending=[True, False])
            .groupby(sym_col)[client_col].first()
        )

    top_buyers  = top_client(buy_df)  if not buy_df.empty  else pd.Series(dtype=str)
    top_sellers = top_client(sell_df) if not sell_df.empty else pd.Series(dtype=str)

    result = pd.DataFrame({
        "Buy_Value":  buy_value,
        "Sell_Value": sell_value,
        "Buy_Deals":  buy_deals,
        "Sell_Deals": sell_deals,
        "Last_Date":  latest_date,
        "Source":     sources,
        "Top_Buyer":  top_buyers,
        "Top_Seller": top_sellers,
    }).fillna({"Buy_Value": 0, "Sell_Value": 0, "Buy_Deals": 0, "Sell_Deals": 0, "Source": "", "Top_Buyer": "", "Top_Seller": ""})

    result["Net_Value"]    = result["Buy_Value"]  - result["Sell_Value"]
    result["Gross_Value"]  = result["Buy_Value"]  + result["Sell_Value"]
    result["Net_Bias_Pct"] = (
        result["Net_Value"]
        .div(result[["Buy_Value", "Sell_Value"]].max(axis=1).replace(0, pd.NA))
        .fillna(0) * 100
    )

    def classify(row):
        bv, sv, nb = row["Buy_Value"], row["Sell_Value"], row["Net_Bias_Pct"]
        if bv > 0 and sv > 0 and abs(nb) <= 1:
            return ("Matched Transfer",     "Neutral: large buy and sell values are almost equal.")
        if nb >= 25:  return ("Strong Accumulation", "Bullish: buying value is much higher than selling value.")
        if nb >= 5:   return ("Accumulation",         "Positive: buying value is higher than selling value.")
        if nb <= -25: return ("Strong Distribution",  "Bearish: selling value is much higher than buying value.")
        if nb <= -5:  return ("Distribution",          "Negative: selling value is higher than buying value.")
        return ("Mixed / Neutral", "Neutral: flow is balanced or too small to read directionally.")

    labels = result.apply(classify, axis=1, result_type="expand")
    result["Deal_Type"]     = labels[0]
    result["Interpretation"] = labels[1]

    result["Buy_Cr"]    = (result["Buy_Value"]  / 1e7).round(2)
    result["Sell_Cr"]   = (result["Sell_Value"] / 1e7).round(2)
    result["Net_Cr"]    = (result["Net_Value"]  / 1e7).round(2)
    result["Gross_Cr"]  = (result["Gross_Value"]/ 1e7).round(2)
    result["Net_Bias_%"] = result["Net_Bias_Pct"].round(2)
    result["Buy_Deals"]  = result["Buy_Deals"].astype(int)
    result["Sell_Deals"] = result["Sell_Deals"].astype(int)

    return result.reset_index().sort_values("Gross_Value", ascending=False)


BADGE_MAP = {
    "Strong Accumulation": '<span class="badge badge-strong-accum">⬆ Strong Accum</span>',
    "Accumulation":        '<span class="badge badge-accum">↑ Accumulation</span>',
    "Strong Distribution": '<span class="badge badge-strong-dist">⬇ Strong Dist</span>',
    "Distribution":        '<span class="badge badge-dist">↓ Distribution</span>',
    "Matched Transfer":    '<span class="badge badge-transfer">⇄ Matched</span>',
    "Mixed / Neutral":     '<span class="badge badge-neutral">~ Neutral</span>',
}

# =====================================================
# NET FLOW helper  (used in tab1/tab2)
# =====================================================

def get_stock_net_flow(days: int = 30) -> pd.DataFrame:
    if not analysis_ready:
        return pd.DataFrame()

    df = apply_filters(all_df)
    if df.empty:
        return pd.DataFrame()

    cutoff = pd.Timestamp.today() - pd.Timedelta(days=days)
    if "Date" in df.columns:
        df = df[df["Date"] >= cutoff]

    buy_df  = df[df["Buy/Sell"].astype(str).str.upper() == "BUY"]
    sell_df = df[df["Buy/Sell"].astype(str).str.upper() == "SELL"]

    buys  = buy_df.groupby("Symbol")["Trade_Value"].sum()
    sells = sell_df.groupby("Symbol")["Trade_Value"].sum()

    flow = pd.DataFrame({"Buy_Value": buys, "Sell_Value": sells}).fillna(0)
    flow["Net_Value"] = flow["Buy_Value"] - flow["Sell_Value"]
    flow = flow.reset_index()
    flow["Buy_Cr"]  = (flow["Buy_Value"]  / 1e7).round(2)
    flow["Sell_Cr"] = (flow["Sell_Value"] / 1e7).round(2)
    flow["Net_Cr"]  = (flow["Net_Value"]  / 1e7).round(2)
    return flow


# =====================================================
# TABS
# =====================================================

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "🔥 Accumulation",
    "📉 Distribution",
    "🏢 Top Buyers",
    "💰 Top Sellers",
    "📋 Bulk Deals",
    "🏦 Block Deals",
    "⭐ Smart Money",
    "🔬 Deal Interpretation",
])

# ────────────────────────────────────────────────────
# TAB 1 — TOP ACCUMULATION
# ────────────────────────────────────────────────────
with tab1:
    st.markdown('<div class="section-header">Top Accumulation Stocks (filtered · 30 days)</div>', unsafe_allow_html=True)

    flow = get_stock_net_flow(days=30)

    if not flow.empty:
        accum = flow.sort_values("Net_Value", ascending=False).head(50)

        # KPIs
        k1, k2, k3 = st.columns(3)
        k1.metric("Stocks with Net Buy", (accum["Net_Value"] > 0).sum())
        k2.metric("Total Buy Flow (Cr)", f"₹{accum['Buy_Cr'].sum():,.0f}")
        k3.metric("Top Net Inflow (Cr)", f"₹{accum['Net_Cr'].iloc[0]:,.0f}" if len(accum) else "—")

        render_insights(generate_insights(apply_filters(all_df)[
            apply_filters(all_df)["Buy/Sell"].astype(str).str.upper() == "BUY"
        ] if analysis_ready else pd.DataFrame()))

        # Chart: top 15 symbols by net buy
        import json
        chart_data = accum[accum["Net_Value"] > 0].head(15)
        if not chart_data.empty:
            bars_html = ""
            max_val = chart_data["Net_Cr"].max()
            for _, row in chart_data.iterrows():
                pct = row["Net_Cr"] / max_val * 100
                bars_html += f"""
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:5px;">
                  <div style="width:90px;font-size:0.75rem;color:#e2e8f0;text-align:right;font-family:monospace;">{row['Symbol']}</div>
                  <div style="flex:1;background:#1e2535;border-radius:4px;overflow:hidden;">
                    <div style="width:{pct:.1f}%;background:linear-gradient(90deg,#059669,#34d399);height:18px;border-radius:4px;"></div>
                  </div>
                  <div style="width:70px;font-size:0.74rem;color:#34d399;font-family:monospace;">₹{row['Net_Cr']:,.0f} Cr</div>
                </div>"""
            st.markdown(f'<div style="background:#0e1117;padding:0.8rem;border-radius:8px;border:1px solid #2a3040;">{bars_html}</div>', unsafe_allow_html=True)

        st.dataframe(
            accum[["Symbol", "Buy_Cr", "Sell_Cr", "Net_Cr"]].rename(
                columns={"Buy_Cr": "Buy (Cr)", "Sell_Cr": "Sell (Cr)", "Net_Cr": "Net (Cr)"}
            ),
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("No accumulation data with current filters.")

# ────────────────────────────────────────────────────
# TAB 2 — TOP DISTRIBUTION
# ────────────────────────────────────────────────────
with tab2:
    st.markdown('<div class="section-header">Top Distribution Stocks (filtered · 30 days)</div>', unsafe_allow_html=True)

    flow = get_stock_net_flow(days=30)

    if not flow.empty:
        dist = flow.sort_values("Net_Value", ascending=True).head(50)

        k1, k2, k3 = st.columns(3)
        k1.metric("Stocks with Net Sell", (dist["Net_Value"] < 0).sum())
        k2.metric("Total Sell Flow (Cr)", f"₹{dist['Sell_Cr'].sum():,.0f}")
        k3.metric("Top Net Outflow (Cr)", f"₹{abs(dist['Net_Cr'].iloc[0]):,.0f}" if len(dist) else "—")

        chart_data = dist[dist["Net_Value"] < 0].head(15)
        if not chart_data.empty:
            bars_html = ""
            max_val = chart_data["Net_Cr"].abs().max()
            for _, row in chart_data.iterrows():
                pct = abs(row["Net_Cr"]) / max_val * 100
                bars_html += f"""
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:5px;">
                  <div style="width:90px;font-size:0.75rem;color:#e2e8f0;text-align:right;font-family:monospace;">{row['Symbol']}</div>
                  <div style="flex:1;background:#1e2535;border-radius:4px;overflow:hidden;">
                    <div style="width:{pct:.1f}%;background:linear-gradient(90deg,#b91c1c,#f87171);height:18px;border-radius:4px;"></div>
                  </div>
                  <div style="width:80px;font-size:0.74rem;color:#f87171;font-family:monospace;">₹{abs(row['Net_Cr']):,.0f} Cr</div>
                </div>"""
            st.markdown(f'<div style="background:#0e1117;padding:0.8rem;border-radius:8px;border:1px solid #2a3040;">{bars_html}</div>', unsafe_allow_html=True)

        st.dataframe(
            dist[["Symbol", "Buy_Cr", "Sell_Cr", "Net_Cr"]].rename(
                columns={"Buy_Cr": "Buy (Cr)", "Sell_Cr": "Sell (Cr)", "Net_Cr": "Net (Cr)"}
            ),
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("No distribution data with current filters.")

# ────────────────────────────────────────────────────
# TAB 3 — TOP BUYERS
# ────────────────────────────────────────────────────
with tab3:
    st.markdown('<div class="section-header">Top Institutional Buyers (filtered)</div>', unsafe_allow_html=True)

    if analysis_ready:
        filtered_all = apply_filters(all_df)
        buyers = (
            filtered_all[filtered_all["Buy/Sell"].astype(str).str.upper() == "BUY"]
            .dropna(subset=["Client Name"])
            .groupby("Client Name")
            .agg(Trade_Value=("Trade_Value", "sum"), Deals=("Symbol", "count"), Stocks=("Symbol", "nunique"))
            .reset_index()
            .sort_values("Trade_Value", ascending=False)
        )
        buyers["Value_Cr"] = (buyers["Trade_Value"] / 1e7).round(2)
        buyers["Avg_Deal_Cr"] = (buyers["Value_Cr"] / buyers["Deals"]).round(2)

        if not buyers.empty:
            k1, k2, k3 = st.columns(3)
            k1.metric("Unique Buyers", len(buyers))
            k2.metric("Total Buy Value (Cr)", f"₹{buyers['Value_Cr'].sum():,.0f}")
            k3.metric("Top Buyer", buyers.iloc[0]["Client Name"][:25])

            # Mini bar chart for top 10
            top10 = buyers.head(10)
            max_v = top10["Value_Cr"].max()
            bars = ""
            for _, r in top10.iterrows():
                pct = r["Value_Cr"] / max_v * 100
                bars += f"""
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:5px;">
                  <div style="width:170px;font-size:0.72rem;color:#e2e8f0;text-align:right;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{r['Client Name']}</div>
                  <div style="flex:1;background:#1e2535;border-radius:4px;">
                    <div style="width:{pct:.1f}%;background:linear-gradient(90deg,#1d4ed8,#60a5fa);height:16px;border-radius:4px;"></div>
                  </div>
                  <div style="width:70px;font-size:0.72rem;color:#60a5fa;font-family:monospace;">₹{r['Value_Cr']:,.0f} Cr</div>
                </div>"""
            st.markdown(f'<div style="background:#0e1117;padding:0.8rem;border-radius:8px;border:1px solid #2a3040;margin-bottom:0.8rem;">{bars}</div>', unsafe_allow_html=True)

            st.dataframe(
                buyers[["Client Name", "Value_Cr", "Deals", "Stocks", "Avg_Deal_Cr"]].head(100).rename(
                    columns={"Value_Cr": "Value (Cr)", "Avg_Deal_Cr": "Avg Deal (Cr)"}
                ),
                use_container_width=True, hide_index=True,
            )
            st.download_button("⬇ Download", buyers.to_csv(index=False), "top_buyers.csv", mime="text/csv")
    else:
        st.info("No analysis data available.")

# ────────────────────────────────────────────────────
# TAB 4 — TOP SELLERS
# ────────────────────────────────────────────────────
with tab4:
    st.markdown('<div class="section-header">Top Institutional Sellers (filtered)</div>', unsafe_allow_html=True)

    if analysis_ready:
        filtered_all = apply_filters(all_df)
        sellers = (
            filtered_all[filtered_all["Buy/Sell"].astype(str).str.upper() == "SELL"]
            .dropna(subset=["Client Name"])
            .groupby("Client Name")
            .agg(Trade_Value=("Trade_Value", "sum"), Deals=("Symbol", "count"), Stocks=("Symbol", "nunique"))
            .reset_index()
            .sort_values("Trade_Value", ascending=False)
        )
        sellers["Value_Cr"] = (sellers["Trade_Value"] / 1e7).round(2)
        sellers["Avg_Deal_Cr"] = (sellers["Value_Cr"] / sellers["Deals"]).round(2)

        if not sellers.empty:
            k1, k2, k3 = st.columns(3)
            k1.metric("Unique Sellers", len(sellers))
            k2.metric("Total Sell Value (Cr)", f"₹{sellers['Value_Cr'].sum():,.0f}")
            k3.metric("Top Seller", sellers.iloc[0]["Client Name"][:25])

            top10 = sellers.head(10)
            max_v = top10["Value_Cr"].max()
            bars = ""
            for _, r in top10.iterrows():
                pct = r["Value_Cr"] / max_v * 100
                bars += f"""
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:5px;">
                  <div style="width:170px;font-size:0.72rem;color:#e2e8f0;text-align:right;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{r['Client Name']}</div>
                  <div style="flex:1;background:#1e2535;border-radius:4px;">
                    <div style="width:{pct:.1f}%;background:linear-gradient(90deg,#991b1b,#f87171);height:16px;border-radius:4px;"></div>
                  </div>
                  <div style="width:70px;font-size:0.72rem;color:#f87171;font-family:monospace;">₹{r['Value_Cr']:,.0f} Cr</div>
                </div>"""
            st.markdown(f'<div style="background:#0e1117;padding:0.8rem;border-radius:8px;border:1px solid #2a3040;margin-bottom:0.8rem;">{bars}</div>', unsafe_allow_html=True)

            st.dataframe(
                sellers[["Client Name", "Value_Cr", "Deals", "Stocks", "Avg_Deal_Cr"]].head(100).rename(
                    columns={"Value_Cr": "Value (Cr)", "Avg_Deal_Cr": "Avg Deal (Cr)"}
                ),
                use_container_width=True, hide_index=True,
            )
            st.download_button("⬇ Download", sellers.to_csv(index=False), "top_sellers.csv", mime="text/csv")
    else:
        st.info("No analysis data available.")

# ────────────────────────────────────────────────────
# TAB 5 — BULK DEALS RAW
# ────────────────────────────────────────────────────
with tab5:
    st.markdown('<div class="section-header">Bulk Deals — Raw (filtered)</div>', unsafe_allow_html=True)

    bulk_filtered = apply_filters(bulk_df)
    st.caption(f"{len(bulk_filtered):,} records")

    if not bulk_filtered.empty:
        # Per-symbol mini-summary when a symbol is searched
        if symbol_search:
            bv = bulk_filtered[bulk_filtered["Buy/Sell"].astype(str).str.upper() == "BUY"]["Trade_Value"].sum()
            sv = bulk_filtered[bulk_filtered["Buy/Sell"].astype(str).str.upper() == "SELL"]["Trade_Value"].sum()
            nv = bv - sv
            nc = "green" if nv >= 0 else "red"
            ns = "+" if nv >= 0 else ""
            st.markdown(f"""
            <div class="kpi-row">
              <div class="kpi-card"><div class="kpi-label">Buy Value</div><div class="kpi-value green">₹{bv/1e7:,.2f} Cr</div></div>
              <div class="kpi-card"><div class="kpi-label">Sell Value</div><div class="kpi-value red">₹{sv/1e7:,.2f} Cr</div></div>
              <div class="kpi-card"><div class="kpi-label">Net Value</div><div class="kpi-value {nc}">{ns}₹{nv/1e7:,.2f} Cr</div></div>
            </div>""", unsafe_allow_html=True)

        disp = bulk_filtered.copy()
        if "Trade_Value" in disp.columns:
            disp["Trade_Value (Cr)"] = (disp["Trade_Value"].fillna(0) / 1e7).round(2)
            disp = disp.drop(columns=["Trade_Value"], errors="ignore")

        st.download_button("⬇ Download Filtered", bulk_filtered.to_csv(index=False), "bulk_filtered.csv", mime="text/csv")
        st.dataframe(disp, use_container_width=True, hide_index=True)
    else:
        st.info("No records match the current filters.")

# ────────────────────────────────────────────────────
# TAB 6 — BLOCK DEALS RAW
# ────────────────────────────────────────────────────
with tab6:
    st.markdown('<div class="section-header">Block Deals — Raw (filtered)</div>', unsafe_allow_html=True)

    block_filtered = apply_filters(block_df)
    st.caption(f"{len(block_filtered):,} records")

    if not block_filtered.empty:
        if symbol_search:
            bv = block_filtered[block_filtered["Buy/Sell"].astype(str).str.upper() == "BUY"]["Trade_Value"].sum()
            sv = block_filtered[block_filtered["Buy/Sell"].astype(str).str.upper() == "SELL"]["Trade_Value"].sum()
            nv = bv - sv
            nc = "green" if nv >= 0 else "red"
            ns = "+" if nv >= 0 else ""
            st.markdown(f"""
            <div class="kpi-row">
              <div class="kpi-card"><div class="kpi-label">Buy Value</div><div class="kpi-value green">₹{bv/1e7:,.2f} Cr</div></div>
              <div class="kpi-card"><div class="kpi-label">Sell Value</div><div class="kpi-value red">₹{sv/1e7:,.2f} Cr</div></div>
              <div class="kpi-card"><div class="kpi-label">Net Value</div><div class="kpi-value {nc}">{ns}₹{nv/1e7:,.2f} Cr</div></div>
            </div>""", unsafe_allow_html=True)

        disp = block_filtered.copy()
        if "Trade_Value" in disp.columns:
            disp["Trade_Value (Cr)"] = (disp["Trade_Value"].fillna(0) / 1e7).round(2)
            disp = disp.drop(columns=["Trade_Value"], errors="ignore")

        st.download_button("⬇ Download Filtered", block_filtered.to_csv(index=False), "block_filtered.csv", mime="text/csv")
        st.dataframe(disp, use_container_width=True, hide_index=True)
    else:
        st.info("No records match the current filters.")

# ────────────────────────────────────────────────────
# TAB 7 — SMART MONEY
# ────────────────────────────────────────────────────
with tab7:
    st.markdown('<div class="section-header">Smart Money — Net Flow Ranking (filtered)</div>', unsafe_allow_html=True)

    if analysis_ready:
        filtered_all = apply_filters(all_df)

        buys  = filtered_all[filtered_all["Buy/Sell"].astype(str).str.upper() == "BUY"].groupby("Symbol")["Trade_Value"].sum()
        sells = filtered_all[filtered_all["Buy/Sell"].astype(str).str.upper() == "SELL"].groupby("Symbol")["Trade_Value"].sum()

        smart = pd.DataFrame({"Buy_Value": buys, "Sell_Value": sells}).fillna(0)
        smart["Net_Value"] = smart["Buy_Value"] - smart["Sell_Value"]
        smart = smart.reset_index()
        smart["Buy_Cr"]  = (smart["Buy_Value"]  / 1e7).round(2)
        smart["Sell_Cr"] = (smart["Sell_Value"] / 1e7).round(2)
        smart["Net_Cr"]  = (smart["Net_Value"]  / 1e7).round(2)
        smart["Bias_%"]  = (
            smart["Net_Value"].div(smart[["Buy_Value","Sell_Value"]].max(axis=1).replace(0, pd.NA)).fillna(0) * 100
        ).round(1)

        smart = smart.sort_values("Net_Value", ascending=False)

        # Colour-code Net column
        pos_count = (smart["Net_Value"] > 0).sum()
        neg_count = (smart["Net_Value"] < 0).sum()

        k1, k2, k3 = st.columns(3)
        k1.metric("Net Buyers", pos_count)
        k2.metric("Net Sellers", neg_count)
        k3.metric("Total Stocks", len(smart))

        render_insights(generate_insights(filtered_all))

        st.dataframe(
            smart[["Symbol", "Buy_Cr", "Sell_Cr", "Net_Cr", "Bias_%"]].head(100).rename(
                columns={"Buy_Cr": "Buy (Cr)", "Sell_Cr": "Sell (Cr)", "Net_Cr": "Net (Cr)"}
            ),
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("No analysis data available.")

# ────────────────────────────────────────────────────
# TAB 8 — DEAL INTERPRETATION
# ────────────────────────────────────────────────────
with tab8:
    st.markdown('<div class="section-header">Deal Interpretation — Signal Classification (filtered)</div>', unsafe_allow_html=True)

    if analysis_ready:
        i1, i2, i3 = st.columns(3)

        with i1:
            interpretation_days = st.selectbox("Analysis Window", [7, 15, 30, 60, 90], index=2)
        with i2:
            interpretation_type = st.selectbox("Signal Filter", [
                "All", "Matched Transfer", "Strong Accumulation", "Accumulation",
                "Strong Distribution", "Distribution", "Mixed / Neutral"
            ])
        with i3:
            interpretation_min_value = st.number_input("Min Gross Value (Cr)", value=0.0, step=100.0)

        # Build from FILTERED all_df so global filters apply
        filtered_all = apply_filters(all_df)
        interpretation = build_deal_interpretation(filtered_all, days=interpretation_days)

        if interpretation_type != "All" and not interpretation.empty:
            interpretation = interpretation[interpretation["Deal_Type"] == interpretation_type]

        if interpretation_min_value > 0 and not interpretation.empty:
            interpretation = interpretation[interpretation["Gross_Cr"] >= interpretation_min_value]

        if not interpretation.empty:
            matched_count = interpretation["Deal_Type"].eq("Matched Transfer").sum()
            accum_count   = interpretation["Deal_Type"].isin(["Strong Accumulation", "Accumulation"]).sum()
            dist_count    = interpretation["Deal_Type"].isin(["Strong Distribution", "Distribution"]).sum()
            mixed_count   = interpretation["Deal_Type"].eq("Mixed / Neutral").sum()

            st.markdown(f"""
            <div class="kpi-row">
              <div class="kpi-card"><div class="kpi-label">Stocks Analysed</div><div class="kpi-value blue">{len(interpretation):,}</div></div>
              <div class="kpi-card"><div class="kpi-label">Accumulation</div><div class="kpi-value green">{accum_count}</div></div>
              <div class="kpi-card"><div class="kpi-label">Distribution</div><div class="kpi-value red">{dist_count}</div></div>
              <div class="kpi-card"><div class="kpi-label">Matched Transfers</div><div class="kpi-value blue">{matched_count}</div></div>
              <div class="kpi-card"><div class="kpi-label">Mixed / Neutral</div><div class="kpi-value amber">{mixed_count}</div></div>
            </div>""", unsafe_allow_html=True)

            render_insights(generate_insights(filtered_all))

            # Add badge column
            interpretation["Signal"] = interpretation["Deal_Type"].map(
                lambda x: BADGE_MAP.get(x, x)
            )

            display_cols = [
                "Symbol", "Signal", "Interpretation",
                "Buy_Cr", "Sell_Cr", "Net_Cr", "Gross_Cr", "Net_Bias_%",
                "Buy_Deals", "Sell_Deals",
                "Top_Buyer", "Top_Seller", "Last_Date", "Source"
            ]
            avail_cols = [c for c in display_cols if c in interpretation.columns]

            st.dataframe(
                interpretation[avail_cols]
                .drop(columns=["Signal"], errors="ignore")  # plain table; badges render in HTML
                .head(200),
                use_container_width=True, hide_index=True,
            )

            # Optional: styled HTML table for signal column with badges
            with st.expander("🔖 View with Signal Badges"):
                html_rows = ""
                for _, row in interpretation[avail_cols].head(50).iterrows():
                    badge = BADGE_MAP.get(row.get("Deal_Type", ""), row.get("Deal_Type", ""))
                    html_rows += f"""<tr>
                      <td style="font-family:monospace;font-size:0.78rem;padding:4px 8px;">{row['Symbol']}</td>
                      <td style="padding:4px 8px;">{badge}</td>
                      <td style="font-size:0.72rem;color:#94a3b8;padding:4px 8px;">{row.get('Interpretation','')}</td>
                      <td style="font-family:monospace;color:#34d399;padding:4px 8px;">{row.get('Buy_Cr',0):,.1f}</td>
                      <td style="font-family:monospace;color:#f87171;padding:4px 8px;">{row.get('Sell_Cr',0):,.1f}</td>
                      <td style="font-family:monospace;color:#60a5fa;padding:4px 8px;">{row.get('Net_Cr',0):+,.1f}</td>
                    </tr>"""
                st.markdown(f"""
                <div style="overflow-x:auto;">
                <table style="width:100%;border-collapse:collapse;font-size:0.8rem;color:#e2e8f0;">
                  <thead><tr style="background:#1e2535;color:#6b7a99;font-size:0.7rem;letter-spacing:0.08em;text-transform:uppercase;">
                    <th style="padding:6px 8px;text-align:left;">Symbol</th>
                    <th style="padding:6px 8px;text-align:left;">Signal</th>
                    <th style="padding:6px 8px;text-align:left;">Interpretation</th>
                    <th style="padding:6px 8px;text-align:right;">Buy Cr</th>
                    <th style="padding:6px 8px;text-align:right;">Sell Cr</th>
                    <th style="padding:6px 8px;text-align:right;">Net Cr</th>
                  </tr></thead>
                  <tbody>{html_rows}</tbody>
                </table></div>""", unsafe_allow_html=True)

        else:
            st.info("No interpreted deals match the selected filters.")
    else:
        st.info("No analysis data available.")