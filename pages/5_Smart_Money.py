import io
import sys
import pandas as pd
from pathlib import Path
import plotly.express as px
import streamlit as st
from datetime import date, timedelta
from utils import *

st.title("💼 Smart Money & Institutional Flow Tracker")

# Load Data
df_sh, df_fin, df_cf, df_insider, df_snap, df_brokerage, df_tech, df_tv = load_all_data()

tab_insider, tab_deals, tab_broker = st.tabs([
    "🕵️ Insider Trading Disclosures", "📦 Bulk & Block Deals", "🏦 Analyst Price Targets"
])

with tab_insider:
    st.subheader("Director & Promoter Disclosures (Trendlyne)")
    if df_insider.empty:
        st.info("No Insider disclosures logged.")
    else:
        ins_df = df_insider.copy()
        ins_stock = st.text_input("Search Insider Ticker", "").upper()
        if ins_stock:
            ins_df = ins_df[ins_df["stock"].str.contains(ins_stock, na=False)]
            
        st.dataframe(ins_df.sort_values("value", ascending=False).head(100), use_container_width=True, hide_index=True)

with tab_deals:
    st.subheader("Large Volume Trades (Bulk & Block)")
    bulk_df = load_bulk_deals()
    block_df = load_block_deals()
    all_deals = pd.concat([bulk_df, block_df], ignore_index=True)
    
    if all_deals.empty:
        st.info("No Bulk or Block deal logs present.")
    else:
        all_deals = prepare_bulk_block(all_deals)
        deals_stock = st.text_input("Filter Deals Ticker", "").upper()
        if deals_stock:
            all_deals = all_deals[all_deals["Symbol"].str.contains(deals_stock, na=False)]
            
        st.dataframe(all_deals.sort_values("Trade_Value", ascending=False).head(100), use_container_width=True, hide_index=True)

with tab_broker:
    st.subheader("Professional Broker Recommendation Consensus")
    if df_brokerage.empty:
        st.info("Brokerage target research tracking files not active.")
    else:
        st.dataframe(df_brokerage.sort_values("upside_pct", ascending=False).head(100), use_container_width=True, hide_index=True)