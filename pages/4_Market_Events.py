import io
import sys
import pandas as pd
from pathlib import Path
import plotly.express as px
import streamlit as st
from datetime import date, timedelta
from utils import *

st.title("📅 Market Events, Alerts & Announcements")

# Load Data
df_sh, df_fin, df_cf, df_insider, df_snap, df_brokerage, df_tech, df_tv = load_all_data()

tab_cal, tab_ann, tab_alerts = st.tabs([
    "Earnings Calendar", "Exchange Announcements", "📡 Technical Alerts"
])

with tab_cal:
    st.subheader("Trendlyne Earnings Results Calendar")
    
    # ── Quick Date Range preset ──
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    
    col_c1, col_c2 = st.columns(2)
    with col_c1: start_date = st.date_input("Calendar Start", value=monday, key="cal_start")
    with col_c2: end_date = st.date_input("Calendar End", value=sunday, key="cal_end")
    
    # In case data isn't directly scraped locally, refer to parquet
    cal_file = Path("data/corporate_actions_all.parquet")
    if cal_file.exists():
        cal_df = pd.read_parquet(cal_file)
        cal_df["date"] = pd.to_datetime(cal_df["date"]).dt.date
        filtered_cal = cal_df[cal_df["date"].between(start_date, end_date)]
        st.dataframe(filtered_cal[["date", "symbol", "company", "announcement_type", "announcement_text"]].sort_values("date"), use_container_width=True, hide_index=True)
    else:
        st.warning("Announcements file not found in directory.")

with tab_ann:
    st.subheader("Exchange Filings & announcements")
    CORP_FILE = Path("data/corporate_actions_all.parquet")
    if CORP_FILE.exists():
        df_corp = pd.read_parquet(CORP_FILE)
        df_corp["date"] = pd.to_datetime(df_corp["date"])
        
        search_sym = st.text_input("Filter Ticker Symbol", "").upper()
        if search_sym:
            df_corp = df_corp[df_corp["symbol"].str.contains(search_sym, na=False)]
        
        st.dataframe(df_corp[["date", "symbol", "company", "announcement_type", "announcement_text"]].sort_values("date", ascending=False).head(100), use_container_width=True, hide_index=True)
    else:
        st.info("No announcement files present.")

with tab_alerts:
    st.subheader("📡 Google Sheet Connected Alerts")
    ALERT_FILE = Path("data/tv_alerts.parquet")
    if ALERT_FILE.exists():
        alerts_df = pd.read_parquet(ALERT_FILE)
        st.dataframe(alerts_df.sort_values("date", ascending=False).head(100), use_container_width=True, hide_index=True)
    else:
        st.info("No active TradingView alerts logged in system.")