import sys
import io
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))
from utils import *

st.title("📊 Fundamental Stock Analyzer")

# Load Data
df_sh, df_fin, df_cf, df_insider, df_snap, df_brokerage, df_tech, df_tv = load_all_data()
summary = st.session_state.get("summary", pd.DataFrame())

if summary.empty:
    st.info("Summary not loaded. Building placeholder mapping...")
    symbols_list = sorted(set(df_sh["symbol"].unique()) | set(df_fin["symbol"].unique())) if not df_sh.empty else []
else:
    symbols_list = summary["symbol"].unique().tolist()

# Global Stock Selector
stock = st.selectbox("🎯 Select Stock to Analyze", symbols_list or ["No Data Loaded"])
st.divider()

if df_fin.empty:
    st.error("Financial database is currently empty.")
    st.stop()

tab_fin, tab_sh, tab_cf, tab_hm, tab_screener = st.tabs([
    "📈 Financial Trends & Margins", "👥 Shareholding & FPI Trends", "💸 Cash Flow & Quality", "🔥 Heatmaps", "🔎 YoY Quarter Screener"
])

with tab_fin:
    top_cols = st.columns([1, 2])
    with top_cols[0]:
        freq = st.segmented_control("Reporting Frequency", ["quarterly", "annual"], default="quarterly", key="sa_freq")
    with top_cols[1]:
        available = df_fin[(df_fin["symbol"] == stock) & (df_fin["freq"] == freq)]["metric"].dropna().unique().tolist()
        default_metrics = [m for m in ["Sales", "EBITDA", "Net Profit"] if m in available]
        selected_metrics = st.multiselect("Compare Metrics", available, default=default_metrics or available[:3])

    sub_fin = sort_periods(df_fin[(df_fin["symbol"] == stock) & (df_fin["freq"] == freq)].copy())
    if sub_fin.empty:
        st.warning(f"No {freq} financial records found for {stock}")
    else:
        snap = df_snap[df_snap["symbol"] == stock] if not df_snap.empty else pd.DataFrame()
        ltp = snap["ltp"].iloc[0] if not snap.empty else None
        mcap = snap["market_cap_cr"].iloc[0] if not snap.empty else None

        k_cols = st.columns(5)
        k_cols[0].metric("Last Traded Price", f"Rs {ltp:,.1f}" if pd.notna(ltp) else "-")
        k_cols[1].metric("Market Cap (Cr)", f"Rs {mcap:,.0f} Cr" if pd.notna(mcap) else "-")
        for idx, met in enumerate(["Sales", "Net Profit", "EPS"]):
            lv = latest_fin(df_fin, stock, met)
            chg = yoy_fin(df_fin, stock, met)
            k_cols[2 + idx].metric(met, f"{lv:,.1f}" if pd.notna(lv) else "-", f"{chg:+.1f}% YoY" if pd.notna(chg) else None)

        fig = go.Figure()
        for met in selected_metrics:
            met_df = sort_periods(sub_fin[sub_fin["metric"] == met].copy())
            if met_df.empty: continue
            is_line = met in {"EPS", "EBITDA Margin %"}
            if is_line:
                fig.add_trace(go.Scatter(x=met_df["period"].astype(str), y=met_df["value"], name=met, mode="lines+markers", line=dict(color=METRIC_COLORS.get(met, "#64748b"), width=2.4), yaxis="y2"))
            else:
                fig.add_trace(go.Bar(x=met_df["period"].astype(str), y=met_df["value"], name=met, marker_color=METRIC_COLORS.get(met, "#64748b")))

        fig.update_layout(title=f"{stock} {freq} financial trend", template="plotly_white", barmode="group", hovermode="x unified", yaxis=dict(title="Rs Cr"), yaxis2=dict(title="% / EPS", overlaying="y", side="right", showgrid=False), legend=dict(orientation="h", y=-0.18))
        st.plotly_chart(fig, use_container_width=True)

with tab_sh:
    if df_sh.empty:
        st.info("Shareholding database is currently empty.")
    else:
        sub_sh = sort_quarters(df_sh[df_sh["symbol"] == stock].copy(), "quarter")
        if sub_sh.empty:
            st.warning(f"No ownership details found for {stock}.")
        else:
            q_cols = st.columns(4)
            for idx, cat in enumerate(["Promoters", "FIIs", "DIIs", "Public"]):
                lv = latest_sh(df_sh, stock, cat)
                chg = qoq_sh(df_sh, stock, cat)
                q_cols[idx].metric(cat, f"{lv:.2f}%" if pd.notna(lv) else "-", f"{chg:+.2f} pp" if pd.notna(chg) else None)

            # Bar plot
            fig = go.Figure()
            for cat in ["Promoters", "FIIs", "DIIs", "Public"]:
                cat_df = sub_sh[sub_sh["category"] == cat]
                if cat_df.empty: continue
                fig.add_trace(go.Bar(x=cat_df["quarter"].astype(str), y=cat_df["pct"], name=cat, marker_color=CATEGORY_COLORS.get(cat, "#64748b")))
            fig.update_layout(title="Ownership structure quarterly trend", barmode="stack", yaxis_title="Holding %", template="plotly_white")
            st.plotly_chart(fig, use_container_width=True)

            # FFP / FPI Activity classification
            st.markdown("#### FPI Trend Analysis")
            fii_sub = sub_sh[sub_sh["category"] == "FIIs"]
            if len(fii_sub) >= 2:
                latest_fii = fii_sub.iloc[-1]["pct"]
                prev_fii = fii_sub.iloc[-2]["pct"]
                qoq_fii = round(latest_fii - prev_fii, 2)
                yoy_fii = round(latest_fii - fii_sub.iloc[-5]["pct"], 2) if len(fii_sub) >= 5 else None
                
                status = "Neutral / Holding"
                if qoq_fii > 1.0: status = "Aggressive Buying 🟢"
                elif qoq_fii > 0: status = "Buying 🟢"
                elif qoq_fii < -1.0: status = "Aggressive Selling 🔴"
                elif qoq_fii < 0: status = "Selling 🔴"
                
                st.info(f"**Latest Shareholding Status:** FII holding at **{latest_fii:.2f}%** ({status}) | QoQ: **{qoq_fii:+.2f} pp** | YoY: **{f'{yoy_fii:+.2f} pp' if yoy_fii else '—'}**")

with tab_cf:
    if df_cf.empty:
        st.info("Cash Flow database is empty.")
    else:
        sub_cf = sort_periods(df_cf[df_cf["symbol"] == stock].copy())
        if sub_cf.empty:
            st.warning(f"No cash flow disclosures found for {stock}.")
        else:
            k_cols = st.columns(5)
            kpi_cf = [("CFO", "Cr"), ("True Free Cash Flow", "Cr"), ("Fixed Asset Purchased", "Cr"), ("CFO/OP", "x"), ("Net Cash Flow", "Cr")]
            for idx, (met, unit) in enumerate(kpi_cf):
                if met == "CFO/OP":
                    val = latest_cf(df_cf, stock, "CFO/OP")
                    k_cols[idx].metric("CFO/OP Ratio", f"{val:.2f}x" if pd.notna(val) else "-")
                else:
                    val = latest_cf(df_cf, stock, met)
                    yoy = yoy_cf(df_cf, stock, met)
                    k_cols[idx].metric(met, f"{val:,.1f} Cr" if pd.notna(val) else "-", f"{yoy:+.1f}% YoY" if pd.notna(yoy) else None)

            # Reinvestment Card
            row = summary[summary["symbol"] == stock].iloc[0] if not summary.empty and stock in summary["symbol"].values else pd.Series(dtype=object)
            st.markdown("#### Quality Diagnostics")
            st.write(row.get("Cash Flow Analysis", "No summary cash diagnostics available.") if isinstance(row, pd.Series) else "No diagnostic loaded.")

with tab_hm:
    st.markdown("#### Dynamic Fundamental Heatmap Matrix")
    hm_type = st.selectbox("Dataset Focus", ["Shareholding", "Cash Flow", "Financials"], key="sa_hm_focus")
    
    # Render Heatmap logic
    if hm_type == "Shareholding":
        metric_choice = st.selectbox("Category", [c for c in ["FIIs", "DIIs", "Promoters", "Public"] if c in df_sh["category"].unique()])
        hm_data = df_sh[(df_sh["symbol"] == stock) & (df_sh["category"] == metric_choice)]
        val_col, period_col = "pct", "quarter"
    elif hm_type == "Financials":
        metric_choice = st.selectbox("Financial Metric", [m for m in ["Sales", "EBITDA", "Net Profit", "EPS"] if m in df_fin["metric"].unique()])
        hm_data = df_fin[(df_fin["symbol"] == stock) & (df_fin["metric"] == metric_choice) & (df_fin["freq"] == "quarterly")]
        val_col, period_col = "value", "period"
    else:
        metric_choice = st.selectbox("Cash Flow Metric", [m for m in ["CFO", "True Free Cash Flow", "Capex", "Net Cash Flow"] if m in df_cf["metric"].unique()])
        hm_data = df_cf[(df_cf["symbol"] == stock) & (df_cf["metric"] == metric_choice)]
        val_col, period_col = "value", "period"

    if hm_data.empty:
        st.info("Insufficient timeline records to generate visual heatmap.")
    else:
        pivot_hm = hm_data.pivot_table(index="symbol", columns=period_col, values=val_col, aggfunc="first")
        sorted_cols = sorted(pivot_hm.columns.astype(str), key=make_period_key)
        pivot_hm = pivot_hm.reindex(columns=sorted_cols)
        fig_hm = px.imshow(pivot_hm, aspect="auto", color_continuous_scale="Blues", title=f"{metric_choice} Heatmap for {stock}")
        st.plotly_chart(fig_hm, use_container_width=True)

with tab_screener:
    st.markdown("#### YoY Trend Table")
    selected_metric = st.selectbox("Select metric to screen", df_fin["metric"].unique().tolist(), key="sa_sc_metric")
    sc_periods = st.slider("Historic Quarter count", 4, 16, 8, key="sa_sc_periods")

    sc_data = df_fin[(df_fin["symbol"] == stock) & (df_fin["metric"] == selected_metric) & (df_fin["freq"] == "quarterly")].copy()
    sc_data = sort_periods(sc_data)
    
    if sc_data.empty:
        st.info("No timeline metrics matching criteria.")
    else:
        periods = sort_quarter_columns(sc_data["period"].unique())[-sc_periods:]
        sc_data = sc_data[sc_data["period"].astype(str).isin([str(p) for p in periods])]
        sc_pivot = sc_data.pivot_table(index="symbol", columns="period", values="value", aggfunc="first")
        sc_pivot = sc_pivot.reindex(columns=periods)
        
        if len(sc_pivot.columns) >= 5:
            last = sc_pivot.columns[-1]
            prev = sc_pivot.columns[-5]
            sc_pivot["YoY Growth %"] = (((sc_pivot[last] - sc_pivot[prev]) / sc_pivot[prev].abs()) * 100).round(1)
        st.dataframe(sc_pivot, use_container_width=True)