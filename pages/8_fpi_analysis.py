import streamlit as st
from utils import *
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

tech_path = Path("data/technicals_all.parquet")

if tech_path.exists():
    df_tech = pd.read_parquet(tech_path)
else:
    df_tech = pd.DataFrame()
df_sh, df_fin, df_cf, df_insider, df_snap , df_brokerage, df_tech = load_all_data()
# ══════════════════════════════════════════════════════════════════════════════
# TAB 7 — FPI Analysis
# ══════════════════════════════════════════════════════════════════════════════
selected_symbols = st.session_state.get("selected_symbols", [])
selected_cats = st.session_state.get("selected_cats", [])
symbols = st.session_state.get("symbols", [])


# Fast: read pre-computed summary from session_state (set by app.py)
summary = st.session_state.get("summary", pd.DataFrame())
tech_map = {}

if not df_tech.empty:

    tech_map = (
        df_tech
        .set_index("symbol")
        .to_dict("index")
    )
if summary.empty:
    # Fallback: compute if navigated directly without going through app.py
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
filtered_symbols = summary["symbol"].tolist()
st.subheader("FPI (Foreign Portfolio Investor) Analysis")

if df_sh.empty or "FIIs" not in df_sh["category"].unique():
    st.warning("No FII/FPI shareholding data available. Run screener_fetcher.py first.")
else:
    # ── Helper: classify FPI activity per stock ───────────────────────────
    def classify_fpi(df: pd.DataFrame, symbol: str) -> dict:
        """
        Returns a dict with trend classification and key stats for one stock.
        Classification logic:
            Aggressive Buying  : QoQ change > +1%
            Buying             : QoQ change  0 to +1%
            Neutral / Holding  : QoQ change  0 (exactly)
            Selling            : QoQ change -1 to 0%
            Aggressive Selling : QoQ change < -1%
            No Data            : fewer than 2 quarters
        """
        sub = df[(df["symbol"] == symbol) & (df["category"] == "FIIs")]
        sub = sort_quarters(sub)
        if len(sub) < 2:
            return {"symbol": symbol, "latest_pct": None, "qoq": None,
                    "yoy": None, "label": "No Data", "color": "#adb5bd",
                    "quarters": 0, "trend_3q": None}

        latest  = sub.iloc[-1]["pct"]
        prev    = sub.iloc[-2]["pct"]
        qoq     = round(latest - prev, 2)

        # YoY: compare vs 4 quarters ago if available
        yoy = None
        if len(sub) >= 5:
            yoy = round(latest - sub.iloc[-5]["pct"], 2)

        # 3-quarter trend slope (positive = rising, negative = falling)
        trend_3q = None
        if len(sub) >= 3:
            last3 = sub.iloc[-3:]["pct"].values
            trend_3q = round(float(last3[-1] - last3[0]), 2)

        if qoq > 1.0:
            label, color = "Aggressive Buying",  "#1a7a3e"
        elif qoq > 0:
            label, color = "Buying",              "#1D9E75"
        elif qoq == 0:
            label, color = "Neutral / Holding",   "#6c757d"
        elif qoq > -1.0:
            label, color = "Selling",             "#e07b39"
        else:
            label, color = "Aggressive Selling",  "#c0392b"

        return {
            "symbol":     symbol,
            "latest_pct": latest,
            "qoq":        qoq,
            "yoy":        yoy,
            "label":      label,
            "color":      color,
            "quarters":   len(sub),
            "trend_3q":   trend_3q,
        }

    # Build classification table for all filtered symbols
    fpi_rows = [classify_fpi(df_sh, s) for s in filtered_symbols]
    fpi_df   = pd.DataFrame(fpi_rows)

    # ── Top KPI strip ─────────────────────────────────────────────────────
    label_counts = fpi_df["label"].value_counts()
    agg_buy  = label_counts.get("Aggressive Buying",  0)
    buy      = label_counts.get("Buying",              0)
    hold     = label_counts.get("Neutral / Holding",  0)
    sell     = label_counts.get("Selling",            0)
    agg_sell = label_counts.get("Aggressive Selling", 0)
    avg_fpi  = fpi_df["latest_pct"].mean()
    avg_qoq  = fpi_df["qoq"].mean()

    k1,k2,k3,k4,k5,k6,k7 = st.columns(7)
    for col, lbl, val, css in [
        (k1, "Avg FPI %",         f"{avg_fpi:.2f}%" if pd.notna(avg_fpi) else "—", ""),
        (k2, "Avg QoQ Δ",         f"{avg_qoq:+.2f}%" if pd.notna(avg_qoq) else "—",
            "up" if pd.notna(avg_qoq) and avg_qoq > 0 else "down"),
        (k3, "Aggressive Buying",  agg_buy,  "up"),
        (k4, "Buying",             buy,       "up"),
        (k5, "Neutral / Holding",  hold,      "neu"),
        (k6, "Selling",            sell,      "down"),
        (k7, "Aggressive Selling", agg_sell,  "down"),
    ]:
        col.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">{lbl}</div>
            <div class="metric-val {css}">{val}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Layout: trend chart (left) | classification table (right) ─────────
    col_chart, col_table = st.columns([3, 2])

    # ── Left: FPI % trend chart ───────────────────────────────────────────
    with col_chart:
        fpi_stocks = st.multiselect(
            "Stocks to plot",
            options=filtered_symbols,
            default=filtered_symbols[:min(8, len(filtered_symbols))],
            key="fpi_trend_stocks",
        )
        n_quarters = st.slider(
            "Last N quarters", min_value=4, max_value=20, value=8, step=1,
            key="fpi_n_quarters",
        )

        if fpi_stocks:
            fpi_trend_data = df_sh[
                df_sh["symbol"].isin(fpi_stocks) &
                (df_sh["category"] == "FIIs")
            ]
            fpi_trend_data = sort_quarters(fpi_trend_data)

            # Limit to last N quarters globally
            # all_quarters = fpi_trend_data["quarter"].cat.categories.tolist()
            all_quarters = sort_quarter_columns(
                fpi_trend_data["quarter"].astype(str).unique().tolist()
)
            last_n_qtrs  = all_quarters[-n_quarters:]
            fpi_trend_data = fpi_trend_data[fpi_trend_data["quarter"].isin(last_n_qtrs)]

            palette  = px.colors.qualitative.D3
            fig_fpi  = go.Figure()

            for idx, sym in enumerate(fpi_stocks):
                sym_df = fpi_trend_data[fpi_trend_data["symbol"] == sym]
                if sym_df.empty:
                    continue
                row   = fpi_df[fpi_df["symbol"] == sym].iloc[0] if sym in fpi_df["symbol"].values else {}
                label = row.get("label", "")
                color = palette[idx % len(palette)]

                fig_fpi.add_trace(go.Scatter(
                    x=sym_df["quarter"].astype(str),
                    y=sym_df["pct"],
                    name=f"{sym} ({label})",
                    mode="lines+markers",
                    line=dict(width=2.5, color=color),
                    marker=dict(size=7),
                    hovertemplate=(
                        f"<b>{sym}</b><br>"
                        "Quarter: %{x}<br>"
                        "FPI: %{y:.2f}%<extra></extra>"
                    ),
                ))

            fig_fpi.update_layout(
                title="FPI % — Quarterly Trend",
                xaxis_title="Quarter",
                yaxis_title="FPI Shareholding %",
                yaxis_ticksuffix="%",
                hovermode="x unified",
                template="plotly_white",
                legend=dict(orientation="h", y=-0.28, font_size=11),
                height=440,
                margin=dict(l=50, r=20, t=50, b=100),
            )
            st.plotly_chart(fig_fpi, width="stretch")
        else:
            st.info("Select at least one stock to plot.")

    # ── Right: Classification table ───────────────────────────────────────
    with col_table:
        st.markdown("#### FPI Activity Classification")
        st.caption("Based on latest quarter-on-quarter change")

        # Sort: aggressive buyers first, aggressive sellers last
        order = {
            "Aggressive Buying":  0,
            "Buying":             1,
            "Neutral / Holding":  2,
            "Selling":            3,
            "Aggressive Selling": 4,
            "No Data":            5,
        }
        fpi_display = fpi_df
        fpi_display["_sort"] = fpi_display["label"].map(order)
        fpi_display = fpi_display.sort_values(["_sort", "qoq"], ascending=[True, False])

        # Render as styled HTML cards (one row per stock)
        cards_html = ""
        for _, row in fpi_display.iterrows():
            sym      = row["symbol"]
            pct      = f"{row['latest_pct']:.2f}%" if pd.notna(row["latest_pct"]) else "—"
            qoq_val  = row["qoq"]
            qoq_str  = (f"+{qoq_val:.2f}%" if qoq_val > 0 else f"{qoq_val:.2f}%") if pd.notna(qoq_val) else "—"
            yoy_val  = row["yoy"]
            yoy_str  = (f"+{yoy_val:.2f}%" if yoy_val and yoy_val > 0 else f"{yoy_val:.2f}%") if pd.notna(yoy_val) and yoy_val is not None else "—"
            bg       = row["color"] + "18"   # 10% opacity background
            border   = row["color"]
            lbl      = row["label"]

            # 3Q trend arrow
            t3 = row.get("trend_3q")
            if t3 is None:
                arrow = ""
            elif t3 > 0.5:
                arrow = "↑↑"
            elif t3 > 0:
                arrow = "↑"
            elif t3 == 0:
                arrow = "→"
            elif t3 > -0.5:
                arrow = "↓"
            else:
                arrow = "↓↓"

            cards_html += f"""
            <div style="
                background:{bg};
                border-left:3px solid {border};
                border-radius:6px;
                padding:7px 10px;
                margin-bottom:6px;
                display:flex;
                justify-content:space-between;
                align-items:center;
            ">
                <div>
                <span style="font-weight:600;font-size:13px;">{sym}</span>
                <span style="font-size:11px;color:#6c757d;margin-left:6px;">{arrow} 3Q</span><br>
                <span style="font-size:11px;color:{border};font-weight:500;">{lbl}</span>
                </div>
                <div style="text-align:right;">
                <div style="font-size:14px;font-weight:600;">{pct}</div>
                <div style="font-size:11px;color:#6c757d;">QoQ {qoq_str} &nbsp;|&nbsp; YoY {yoy_str}</div>
                </div>
            </div>"""

        st.markdown(cards_html, unsafe_allow_html=True)

    st.markdown("---")

    # ── Bottom: QoQ waterfall bar chart across all stocks ─────────────────
    st.markdown("#### FPI Quarter-on-Quarter Change — All Stocks")

    fpi_sorted = fpi_df.dropna(subset=["qoq"]).sort_values("qoq", ascending=False)
    if not fpi_sorted.empty:
        bar_colors = [
            "#1a7a3e" if v > 1
            else "#1D9E75" if v > 0
            else "#6c757d" if v == 0
            else "#e07b39" if v > -1
            else "#c0392b"
            for v in fpi_sorted["qoq"]
        ]

        fig_bar = go.Figure(go.Bar(
            x=fpi_sorted["symbol"],
            y=fpi_sorted["qoq"],
            marker_color=bar_colors,
            text=fpi_sorted["qoq"].apply(lambda v: f"{v:+.2f}%"),
            textposition="outside",
            hovertemplate=(
                "<b>%{x}</b><br>"
                "QoQ Δ: %{y:+.2f}%<br>"
                "<extra></extra>"
            ),
        ))
        fig_bar.add_hline(y=0, line_width=1, line_color="#adb5bd")
        fig_bar.update_layout(
            xaxis_title="Stock",
            yaxis_title="FPI QoQ Change (%)",
            yaxis_ticksuffix="%",
            template="plotly_white",
            height=340,
            margin=dict(l=40, r=20, t=20, b=60),
            showlegend=False,
        )
        st.plotly_chart(fig_bar, width="stretch")

    # ── Download ──────────────────────────────────────────────────────────
    dl_cols = ["symbol", "latest_pct", "qoq", "yoy", "trend_3q", "label", "quarters"]
    dl_df   = fpi_df[dl_cols].rename(columns={
        "latest_pct": "FPI %",
        "qoq":        "QoQ Δ%",
        "yoy":        "YoY Δ%",
        "trend_3q":   "3Q Trend Δ%",
        "label":      "Classification",
        "quarters":   "Data Quarters",
    })
    st.download_button(
        "⬇ Download FPI analysis CSV",
        dl_df.to_parquet(index=False),
        "fpi_analysis.parquet",
        "text/csv",
    )
