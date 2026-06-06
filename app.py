import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from pathlib import Path
import subprocess
from datetime import date, timedelta
from utils import *
# ─── Page Config ──────────────────────────────────────────────────────────────
WATCHLIST_FILE = "watchlist.txt"
tech_path = Path("data/technicals_all.parquet")

if tech_path.exists():
    df_tech = pd.read_parquet(tech_path)
else:
    df_tech = pd.DataFrame()


def load_watchlist():

    try:
        with open(WATCHLIST_FILE, "r") as f:
            return [
                x.strip()
                .replace("NSE:", "")
                for x in f.readlines()
                if x.strip()
            ]
    except:
        return []


def save_watchlist(symbols):

    with open(WATCHLIST_FILE, "w") as f:

        for s in sorted(set(symbols)):
            f.write(f"NSE:{s}\n")

def render_leaderboard(df, metric, fmt="{:.0f}"):

    for idx, (_, row) in enumerate(df.iterrows(), start=1):

        medal = {
            1:"🥇",
            2:"🥈",
            3:"🥉"
        }.get(idx, f"{idx}.")

        with st.container(border=True):

            c1,c2,c3 = st.columns([1,4,2])

            c1.markdown(medal)

            c2.markdown(
                f"**{row['symbol']}**"
            )

            c3.markdown(
                f"**{fmt.format(row[metric])}**"
            )          
st.set_page_config(
    page_title="Stock Tracker",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Theme ────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }

.metric-card {
    background: #f8f9fa;
    border: 1px solid #e9ecef;
    border-radius: 10px;
    padding: 1rem 1.25rem;
    text-align: center;
}
.metric-label { font-size: 12px; color: #6c757d; margin-bottom: 4px; letter-spacing: 0.04em; }
.metric-val   { font-size: 26px; font-weight: 600; color: #212529; }
.metric-sub   { font-size: 12px; margin-top: 2px; }

.up   { color: #1e7e34; }
.down { color: #c0392b; }
.neu  { color: #6c757d; }

.section-title {
    font-size: 13px;
    font-weight: 500;
    color: #6c757d;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 0.5rem;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<style>

.stock-card{
    background:#ffffff;
    border:1px solid #e5e7eb;
    border-radius:12px;
    padding:12px;
    margin-bottom:8px;
}

.stock-name{
    font-size:18px;
    font-weight:700;
}

.stock-grade{
    float:right;
    padding:4px 10px;
    border-radius:8px;
    font-weight:700;
}

.grade-aplus{
    background:#16a34a;
    color:white;
}

.grade-a{
    background:#22c55e;
    color:white;
}

.grade-b{
    background:#facc15;
    color:black;
}

</style>
""", unsafe_allow_html=True)

st.markdown("""
<style>

.leader-card{
    border:1px solid #e5e7eb;
    border-radius:12px;
    padding:10px;
    margin-bottom:8px;
    background:#fafafa;
}

.rank1{
    color:#d97706;
    font-weight:700;
}

.rank2{
    color:#6b7280;
    font-weight:700;
}

.rank3{
    color:#92400e;
    font-weight:700;
}

.rankn{
    color:#374151;
}

</style>
""", unsafe_allow_html=True)

# ─── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("📊 Stock Tracker")
    st.caption("Source: Screener.in")
    if st.button("🔄 Download From Screener", use_container_width=True):
        # 1. Show a spinner so the user knows something is happening
        with st.spinner("📥 Fetching fresh data from Screener..."):
            try:
                # 2. Run your actual python script that downloads the data
                # Replace 'screener_fetcher.py' with your actual filename
                result = subprocess.run(
                    ["python", "screener_fetcher.py"], 
                    capture_output=True, 
                    text=True, 
                    check=True
                )
                
                # 3. If the script finished without error, clear the cache
                st.cache_data.clear()
                
                # 4. Success message and restart the app
                st.success("✅ Data Updated!")
                st.rerun()
                
            except subprocess.CalledProcessError as e:
                # If the fetcher script fails, show the error from that script
                st.error(f"Error during fetch: {e.stderr}")

   

    if st.button("🔄 Clear Cache Only", use_container_width=True):
        st.cache_data.clear() # This wipes the Streamlit RAM
        st.success("Cache Cleared!") 
        st.rerun() # This forces the app to reload everything from the files
    with st.spinner("📊 Loading data..."):

        (
            df_sh,
            df_fin,
            df_cf,
            df_insider,
            df_snap,df_brokerage, df_tech
        ) = load_all_data()
        

    if df_sh.empty and df_fin.empty and df_cf.empty:
        st.error("No data found.\n\nRun `python screener_fetcher.py` first.")
        st.stop()

    symbols    = sorted(df_sh["symbol"].unique().tolist() if not df_sh.empty else
                        df_fin["symbol"].unique().tolist())
    categories = sorted(df_sh["category"].unique().tolist()) if not df_sh.empty else []

    st.markdown("---")
    st.markdown('<div class="section-title">Filters</div>', unsafe_allow_html=True)

    selected_symbols = st.multiselect(
        "Stocks (leave blank = all)",
        options=symbols,
        default=[],
        placeholder="Select stocks…",
    )
    if not selected_symbols:
        selected_symbols = symbols

    selected_cats = st.multiselect(
        "Shareholding categories",
        options=categories,
        default=[c for c in ["Promoters","FIIs","DIIs","Public"] if c in categories],
    )
    if not selected_cats:
        selected_cats = categories

    st.markdown("---")
    st.markdown('<div class="section-title">Sort / Filter overview</div>', unsafe_allow_html=True)

    sort_by = st.selectbox(
        "Sort stocks by",
        ["Symbol A–Z", "FII % ↓", "FII % ↑", "FII QoQ change ↓","Promoter % ↓", "Sales ↓", "Net Profit ↓", "Market Cap ↓","Growth Score ↓",
        "Cashflow Score ↓","Composite Score ↓"]
    )
    filter_by = st.selectbox(
        "Filter to",
        ["All", "FII increasing", "FII decreasing", "FII > 20%", "FII < 5%",
         "Net Profit +ve", "Sales growth YoY"],
    )

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
# Normalize symbols before merges
summary["symbol"] = (
    summary["symbol"]
    .astype(str)
    .str.upper()
    .str.strip()
)
# After building summary, cache it in session_state so pages don't recompute
_cache_key = (tuple(sorted(selected_symbols)), tuple(sorted(selected_cats)))
if st.session_state.get("_summary_key") != _cache_key or "summary" not in st.session_state:
    st.session_state["summary"] = summary
    st.session_state["_summary_key"] = _cache_key

# Store filter state for pages
st.session_state["selected_symbols"] = selected_symbols
st.session_state["selected_cats"]    = selected_cats
st.session_state["symbols"]          = symbols
# ─── Filter data ──────────────────────────────────────────────────────────────
# ─── Growth Score Filter ─────────────────────────────

min_growth_score = st.sidebar.slider(
    "Minimum Growth Score",
    min_value=0,
    max_value=25,
    value=0,
)

if "Growth Score" not in summary.columns:
    summary["Growth Score"] = 0

summary = summary[
    summary["Growth Score"] >= min_growth_score
]
# st.write(
#     summary[summary["symbol"] == "LTF"]
# )
df_sh_f = df_sh[
    df_sh["symbol"].isin(selected_symbols) &
    df_sh["category"].isin(selected_cats)
].copy() if not df_sh.empty else pd.DataFrame()

df_fin_f = df_fin[df_fin["symbol"].isin(selected_symbols)].copy() if not df_fin.empty else pd.DataFrame()


summary["Cash Flow Analysis"] = summary.apply(analyze_cashflow, axis=1)
# Apply filter
if filter_by == "FII increasing":
    summary = summary[summary.get("FIIs QoQ", pd.Series(dtype=float)).fillna(0) > 0]
elif filter_by == "FII decreasing":
    summary = summary[summary.get("FIIs QoQ", pd.Series(dtype=float)).fillna(0) < 0]
elif filter_by == "FII > 20%":
    summary = summary[summary.get("FIIs %", pd.Series(dtype=float)).fillna(0) > 20]
elif filter_by == "FII < 5%":
    summary = summary[summary.get("FIIs %", pd.Series(dtype=float)).fillna(0) < 5]
elif filter_by == "Net Profit +ve":
    summary = summary[summary.get("Net Profit", pd.Series(dtype=float)).fillna(0) > 0]
elif filter_by == "Sales growth YoY":
    summary = summary[summary.get("Sales YoY %", pd.Series(dtype=float)).fillna(0) > 0]

# Apply sort
if   "FII % ↓"   in sort_by: summary = summary.sort_values("FIIs %",       ascending=False)
elif "FII % ↑"   in sort_by: summary = summary.sort_values("FIIs %",       ascending=True)
elif "QoQ"       in sort_by: summary = summary.sort_values("FIIs QoQ",     ascending=False)
elif "Promoter"  in sort_by: summary = summary.sort_values("Promoters %",  ascending=False)
elif "Sales ↓"   in sort_by: summary = summary.sort_values("Sales",        ascending=False)
elif "Net Profit" in sort_by: summary = summary.sort_values("Net Profit",  ascending=False)
elif "Market Cap" in sort_by: summary = summary.sort_values("MCap (Cr)",   ascending=False)
elif "Growth Score" in sort_by:summary = summary.sort_values("Growth Score",ascending=False)
elif "Cashflow Score" in sort_by:summary = summary.sort_values("Cashflow Score",ascending=False)
elif "Composite Score" in sort_by:summary = summary.sort_values("Composite Score",ascending=False)
else:                           
    if not summary.empty and "symbol" in summary.columns:
        summary = summary.sort_values("symbol")

filtered_symbols = summary["symbol"].tolist()


# ─── Market-wide stats ────────────────────────────────────────────────────────

st.title("Stock Analytics Dashboard")
st.caption(f"Data from Screener.in · {len(symbols)} stocks · "
           f"{df_sh['quarter'].nunique() if not df_sh.empty else 0} quarters")
# =====================================================
# STOCK SPOTLIGHT
# =====================================================

if not summary.empty:

    spotlight = (
        summary
        .sort_values(
            "Performance Score",
            ascending=False
        )
        .iloc[0]
    )

    st.markdown("## 🔥 Stock Spotlight")

    c1, c2, c3, c4, c5 = st.columns([3,1,1,1,1])

    with c1:
        st.markdown(
            f"""
            ### {spotlight['symbol']}
            Grade **{spotlight['Grade']}**
            """
        )

    with c2:
        st.metric(
            "Score",
            round(
                spotlight["Performance Score"],
                1
            )
        )

    with c3:
        st.metric(
            "Growth",
            round(
                spotlight["Growth Score"],
                1
            )
        )

    with c4:
        st.metric(
            "Cashflow",
            round(
                spotlight["Cashflow Score"],
                1
            )
        )

    with c5:
        if "FIIs %" in spotlight.index:
            st.metric(
                "FII %",
                round(
                    spotlight["FIIs %"],
                    1
                )
            )

    st.info(
        "Highest ranked stock based on current scoring model."
    )


# =====================================================
# MARKET PULSE
# =====================================================

a_plus_count = (summary["Grade"] == "A+").sum()
a_count      = (summary["Grade"] == "A").sum()

fii_up_count = (
    summary.get("FIIs QoQ", pd.Series(dtype=float))
    .fillna(0)
    .gt(0)
    .sum()
)

cash_good = (
    summary.get("Cashflow Score", pd.Series(dtype=float))
    .fillna(0)
    .ge(15)
    .sum()
)

cash_weak = (
    summary.get("Cashflow Score", pd.Series(dtype=float))
    .fillna(0)
    .lt(8)
    .sum()
)

st.markdown(
    f"""
    <div style="
        padding:12px;
        border-radius:10px;
        background:#111827;
        border:1px solid #374151;
        margin-bottom:15px;
        font-size:16px;
    ">

    🟢 <b>A+ Stocks:</b> {a_plus_count}
    &nbsp;&nbsp;&nbsp;

    🟩 <b>A Stocks:</b> {a_count}
    &nbsp;&nbsp;&nbsp;

    📈 <b>FII Increasing:</b> {fii_up_count}
    &nbsp;&nbsp;&nbsp;

    💰 <b>Strong Cashflow:</b> {cash_good}
    &nbsp;&nbsp;&nbsp;

    🔴 <b>Weak Cashflow:</b> {cash_weak}

    </div>
    """,
    unsafe_allow_html=True
)    
# Extract metrics from already-built summary to avoid recalculating
fii_vals = summary.get("FIIs %", pd.Series(dtype=float)).dropna().tolist() if not summary.empty else []
fii_avg  = round(sum(fii_vals)/len(fii_vals), 2) if fii_vals else 0
fii_chgs = summary.get("FIIs QoQ", pd.Series(dtype=float)).dropna().tolist() if not summary.empty else []
fii_up   = sum(1 for c in fii_chgs if c > 0)
fii_dn   = sum(1 for c in fii_chgs if c < 0)

sal_vals = summary.get("Sales", pd.Series(dtype=float)).dropna().tolist() if not summary.empty else []
np_vals  = summary.get("Net Profit", pd.Series(dtype=float)).dropna().tolist() if not summary.empty else []
np_pos   = sum(1 for v in np_vals if v > 0)

c1,c2,c3,c4,c5,c6 = st.columns(6)
for col, label, val, sub, css in [
    (c1, "Total stocks",    len(symbols),                    "",                   ""),
    (c2, "Avg FII %",       f"{fii_avg}%",                   "across all stocks",  ""),
    (c3, "FII increasing",  fii_up,                           "stocks QoQ",         "up"),
    (c4, "FII decreasing",  fii_dn,                           "stocks QoQ",         "down"),
    (c5, "Profitable",      np_pos,                           "positive net profit","up"),
    (c6, "Filtered",        len(filtered_symbols),            f"'{filter_by}'",     ""),
]:
    col.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="metric-val {css}">{val}</div>
        <div class="metric-sub" style="color:#adb5bd">{sub}</div>
    </div>""", unsafe_allow_html=True)
# =====================================================
# MARKET OVERVIEW
# =====================================================

st.markdown("---")
st.markdown("## 🏆 Market Overview")

left, right = st.columns([1,1])

with left:

    grade_counts = (
        summary["Grade"]
        .value_counts()
        .reindex(["A+","A","B","C","F"])
        .fillna(0)
    )

    fig = px.pie(
    values=grade_counts.values,
    names=grade_counts.index,
    hole=0.65,
    color=grade_counts.index,
    color_discrete_map={
        "A+": "#16a34a",
        "A": "#22c55e",
        "B": "#facc15",
        "C": "#fb923c",
        "F": "#dc2626",
    },
    title="Grade Distribution"
)

    fig.update_layout(
        height=350,
        margin=dict(
            l=10,
            r=10,
            t=50,
            b=10
        )
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

with right:

    st.markdown("### ⭐ Top Quality Stocks")

    top_quality = (
        summary
        .sort_values(
            "Performance Score",
            ascending=False
        )
        .head(10)
    )

    for _, row in top_quality.iterrows():

        with st.container(border=True):

            c1, c2 = st.columns([4,1])

            with c1:
                st.write(
                    f"**{row['symbol']}** | "
                    f"Score: {row['Performance Score']:.0f} | "
                    f"Growth: {row['Growth Score']:.0f} | "
                    f"Cashflow: {row['Cashflow Score']:.0f}"
                )

            with c2:
                st.metric(
                    "Grade",
                    row["Grade"]
                )
# =====================================================
# QUALITY COMPOUNDER MATRIX
# =====================================================

st.markdown("## 🎯 Quality Compounder Matrix")

matrix_df = summary.copy()

required_cols = [
    "Growth Score",
    "Cashflow Score",
    "Performance Score",
    "Grade"
]

if all(col in matrix_df.columns for col in required_cols):

    matrix_df = matrix_df.dropna(
        subset=[
            "Growth Score",
            "Cashflow Score"
        ]
    )

    fig = px.scatter(
        matrix_df,
        x="Growth Score",
        y="Cashflow Score",
        size="Performance Score",
        color="Grade",
        hover_name="symbol",
        size_max=35,
        color_discrete_map={
            "A+": "#16a34a",
            "A": "#22c55e",
            "B": "#facc15",
            "C": "#fb923c",
            "F": "#dc2626",
        }
    )

    fig.add_vline(
    x=matrix_df["Growth Score"].median(),
    line_dash="dash"
)

    fig.add_hline(
    y=matrix_df["Cashflow Score"].median(),
    line_dash="dash"
)
    

    fig.update_layout(
        height=600,
        title="Growth vs Cashflow Quality",
        xaxis_title="Growth Score",
        yaxis_title="Cashflow Score"
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )
st.markdown("---")
st.session_state["selected_symbols"] = selected_symbols
st.session_state["selected_cats"] = selected_cats
st.session_state["sort_by"] = sort_by
st.session_state["filter_by"] = filter_by
st.session_state["symbols"] = symbols


st.markdown("## ⭐ Watchlist Manager")

watchlist = load_watchlist()

c1, c2 = st.columns(2)

with c1:

    add_symbols = st.multiselect(
        "Add Stocks",
        options=symbols
    )

    if st.button("➕ Add"):

        watchlist.extend(add_symbols)

        save_watchlist(watchlist)

        st.success("Watchlist Updated")

        st.rerun()

with c2:

    remove_symbols = st.multiselect(
        "Remove Stocks",
        options=watchlist
    )

    if st.button("❌ Remove"):

        watchlist = [
            x
            for x in watchlist
            if x not in remove_symbols
        ]

        save_watchlist(watchlist)

        st.success("Watchlist Updated")

        st.rerun()

st.markdown("## ⭐ Watchlist Dashboard")

watchlist_syms = set(load_watchlist())

watchlist_df = summary[
    summary["symbol"].isin(watchlist_syms)
].copy()

if not watchlist_df.empty:

    watchlist_df = watchlist_df.sort_values(
        "Performance Score",
        ascending=False
    )

    for _, row in watchlist_df.iterrows():

        with st.container(border=True):

            c1, c2, c3, c4, c5 = st.columns(
                [3,1,1,1,1]
            )

            with c1:
                st.markdown(
                    f"### {row['symbol']}"
                )

            with c2:
                st.metric(
                    "Grade",
                    row["Grade"]
                )

            with c3:
                st.metric(
                    "Score",
                    round(
                        row["Performance Score"],
                        1
                    )
                )

            with c4:
                st.metric(
                    "Growth",
                    round(
                        row["Growth Score"],
                        1
                    )
                )

            with c5:
                st.metric(
                    "Cashflow",
                    round(
                        row["Cashflow Score"],
                        1
                    )
                )      

st.markdown("---")
st.markdown("## 🚀 Market Leaders")
c1, c2, c3 = st.columns(3)
with c1:

    st.markdown("### 📈 Fastest Growth")

    growth_df = (
        summary
        .sort_values(
            "Growth Score",
            ascending=False
        )
        .head(10)
    )

    render_leaderboard(
    growth_df,
    "Growth Score"
)
with c2:

    st.markdown("### 💰 Strongest Cashflow")

    cf_df = (
        summary
        .sort_values(
            "Cashflow Score",
            ascending=False
        )
        .head(10)
    )

    render_leaderboard(
    cf_df,
    "Cashflow Score"
)

with c3:

    st.markdown("### 🏦 Highest FII Holding")

    fii_df = (
        summary
        .sort_values(
            "FIIs %",
            ascending=False
        )
        .head(10)
    )

    render_leaderboard(
    fii_df,
    "FIIs %",
    "{:.1f}%"
)      

st.markdown("---")
st.markdown("## 🎯 Today's Best Opportunities")
best = (
    summary[
        (summary["Grade"].isin(["A+","A"]))
        &
        (summary["Growth Score"] >= 15)
        &
        (summary["Cashflow Score"] >= 15)
    ]
    .sort_values(
        "Performance Score",
        ascending=False
    )
    .head(12)
)   
cols = st.columns(4)

for idx, (_, row) in enumerate(best.iterrows()):

    with cols[idx % 4]:

        with st.container(border=True):

            st.markdown(
                f"### {row['symbol']}"
            )

            st.metric(
                "Score",
                round(
                    row["Performance Score"],
                    1
                )
            )

            st.write(
                f"Grade: **{row['Grade']}**"
            )

            st.write(
                f"Growth: **{row['Growth Score']}**"
            )

            st.write(
                f"Cashflow: **{row['Cashflow Score']}**"
            )           
# ── paste inside the `with st.sidebar:` block in app.py ──────────────────────
from pages import Results_calendar
# Note: rename import if Streamlit complains about numeric prefix, use importlib

st.sidebar.markdown("---")
st.sidebar.markdown("### 📅 Results this week")

_today   = date.today()
_monday  = _today - timedelta(days=_today.weekday())
_sunday  = _monday + timedelta(days=6)

try:
    _cal = Results_calendar.fetch_results_calendar(_monday.strftime("%Y-%m-%d"), _sunday.strftime("%Y-%m-%d"))
    _wl  = Results_calendar.load_watchlist()
    if not _cal.empty:
        _wl_cal = _cal[_cal["symbol"].isin(_wl)].sort_values("result_date")
        for _, _r in _wl_cal.iterrows():
            _d  = (_r["result_date"] - _today).days
            _lbl = "TODAY 🔴" if _d==0 else "TOMORROW 🟠" if _d==1 else _r["result_date"].strftime("%d %b")
            st.sidebar.markdown(
                f"**{_r['symbol']}** &nbsp; `{_lbl}`  \n"
                f"<span style='font-size:11px;color:#64748b'>{_r['event']}</span>",
                unsafe_allow_html=True,
            )
    else:
        st.sidebar.caption("No results found for this week.")
except Exception:
    st.sidebar.caption("Calendar unavailable.")


