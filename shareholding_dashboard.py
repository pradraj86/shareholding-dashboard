"""
shareholding_dashboard.py
─────────────────────────
Streamlit dashboard for visualising:
  • Quarterly shareholding patterns (Promoters / FIIs / DIIs / Public)
  • Quarterly financials (Sales, EBITDA, Net Profit, EPS)
  • Snapshot metrics (LTP, Market Cap)

Run with:
    streamlit run shareholding_dashboard.py

Requirements:
    pip install streamlit pandas plotly
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from pathlib import Path
import subprocess
from datetime import date, timedelta

# ─── Page Config ──────────────────────────────────────────────────────────────

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

# ─── Constants ────────────────────────────────────────────────────────────────

MASTER_CSV_SH  = Path("data/shareholding_all.parquet")
MASTER_CSV_FIN = Path("data/financials_all.parquet")
MASTER_CSV_CA  = Path("data/corporate_actions_all.parquet")
SNAPSHOT_FILE   = Path("data/snapshot_all.parquet")
BULK_DEALS_CSV    = Path("data/bulk_deals_all.parquet")
BLOCK_DEALS_CSV   = Path("data/block_deals_all.parquet")
INSIDER_TRADE_CSV = Path("data/insider_trading_all.parquet")
PER_STOCK_DEALS   = Path("data/deals_per_stock")

PER_STOCK_SH   = Path("data/shareholding_screener")
PER_STOCK_FIN  = Path("data/financials_screener")
PER_STOCK_CA   = Path("data/corporate_actions_screener")
TV_ALERTS_CSV = Path("data/tv_alerts.parquet")
MASTER_CSV_CF  = Path("data/cashflow_all.parquet")
PER_STOCK_CF   = Path("data/cashflow_screener")

CATEGORY_COLORS = {
    "Promoters": "#5f5e5a",
    "FIIs":      "#378ADD",
    "DIIs":      "#1D9E75",
    "Public":    "#BA7517",
    "Govt":      "#7F77DD",
    "Others":    "#D85A30",
}

METRIC_COLORS = {
    "Sales":          "#378ADD",
    "EBITDA":         "#1D9E75",
    "EBITDA Margin %":"#7F77DD",
    "Net Profit":     "#BA7517",
    "EPS":            "#D85A30",
}


CF_COLORS = {
    "CFO": "#1D9E75",
    "CFI": "#D85A30",
    "CFF": "#378ADD",
    "Free Cash Flow": "#7F77DD",
    "Net Cash Flow": "#5f5e5a",
    "Capex": "#BA7517",
}
METRIC_UNITS = {
    "Sales":           "₹ Cr",
    "EBITDA":          "₹ Cr",
    "EBITDA Margin %": "%",
    "Net Profit":      "₹ Cr",
    "EPS":             "₹",
}

# ─── Data Loading ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def load_master_sh() -> pd.DataFrame:
    if MASTER_CSV_SH.exists():
        try:
            df = pd.read_parquet(MASTER_CSV_SH)
            if not df.empty:
                return _clean_sh(df)
        except Exception:
            pass
    if PER_STOCK_SH.exists():
        frames = []
        for f in sorted(PER_STOCK_SH.glob("shareholding_*.parquet")):
            try:
                tmp = pd.read_parquet(f)
                if not tmp.empty:
                    frames.append(tmp)
            except Exception:
                pass
        if frames:
            return _clean_sh(pd.concat(frames, ignore_index=True))
    return pd.DataFrame()


@st.cache_data(ttl=3600)
def load_master_fin() -> pd.DataFrame:
    if MASTER_CSV_FIN.exists():
        try:
            df = pd.read_parquet(MASTER_CSV_FIN)
            if not df.empty:
                return _clean_fin(df)
        except Exception:
            pass
    if PER_STOCK_FIN.exists():
        frames = []
        for f in sorted(PER_STOCK_FIN.glob("financials_*.parquet")):
            try:
                tmp = pd.read_parquet(f)
                if not tmp.empty:
                    frames.append(tmp)
            except Exception:
                pass
        if frames:
            return _clean_fin(pd.concat(frames, ignore_index=True))
    return pd.DataFrame()

@st.cache_data(ttl=3600)
def load_master_cf() -> pd.DataFrame:
    if MASTER_CSV_CF.exists():
        try:
            df = pd.read_parquet(MASTER_CSV_CF)
            if not df.empty:
                return _clean_fin(df)
        except Exception:
            pass
    if PER_STOCK_CF.exists():
        frames = []
        for f in sorted(PER_STOCK_CF.glob("cashflow_*.parquet")):
            try:
                tmp = pd.read_parquet(f)
                if not tmp.empty:
                    frames.append(tmp)
            except Exception:
                pass
        if frames:
            return _clean_fin(pd.concat(frames, ignore_index=True))
    return pd.DataFrame()


@st.cache_data(ttl=3600)
def load_snapshot() -> pd.DataFrame:
    if SNAPSHOT_FILE.exists():
        try:
            df = pd.read_parquet(SNAPSHOT_FILE)
            if not df.empty:
                df["symbol"] = df["symbol"].str.upper().str.strip()
                return df
        except Exception:
            pass
    return pd.DataFrame()


@st.cache_data(ttl=3600)
def load_corporate_actions() -> pd.DataFrame:
    """Load corporate actions data from all stocks."""
    if not MASTER_CSV_CA.exists():
        return pd.DataFrame()
    try:
        frames = []
        if PER_STOCK_CA.exists():
            for ca_file in sorted(PER_STOCK_CA.glob("corporate_actions_*.parquet")):
                try:
                    df = pd.read_parquet(ca_file, parse_dates=["date"])
                    if not df.empty:
                        frames.append(df)
                except Exception:
                    pass
        if frames:
            return pd.concat(frames, ignore_index=True).drop_duplicates()
        else:
            df = pd.read_parquet(MASTER_CSV_CA, parse_dates=["date"])
            return df if not df.empty else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def load_alerts() -> pd.DataFrame:
    if not TV_ALERTS_CSV.exists():
        return pd.DataFrame()
    try:
        df = pd.read_parquet(TV_ALERTS_CSV, parse_dates=["date"])
        df["symbol"] = df["symbol"].str.upper().str.strip()
        df.sort_values("date", ascending=False, inplace=True)
        return df.reset_index(drop=True)
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=600)
def load_bulk_deals() -> pd.DataFrame:
    if not BULK_DEALS_CSV.exists():
        return pd.DataFrame()
    try:
        df = pd.read_parquet(BULK_DEALS_CSV, parse_dates=["date"])
        df["symbol"] = df["symbol"].str.upper().str.strip()
        return df.sort_values("date", ascending=False).reset_index(drop=True)
    except Exception:
        return pd.DataFrame()
 
 
@st.cache_data(ttl=600)
def load_block_deals() -> pd.DataFrame:
    if not BLOCK_DEALS_CSV.exists():
        return pd.DataFrame()
    try:
        df = pd.read_parquet(BLOCK_DEALS_CSV, parse_dates=["date"])
        df["symbol"] = df["symbol"].str.upper().str.strip()
        return df.sort_values("date", ascending=False).reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def load_insider_trading() -> pd.DataFrame:
    if not INSIDER_TRADE_CSV.exists():
        return pd.DataFrame()
    try:
        df = pd.read_parquet(INSIDER_TRADE_CSV, parse_dates=["date"])
        df["symbol"] = df["symbol"].str.upper().str.strip()
        return df.sort_values("date", ascending=False).reset_index(drop=True)
    except Exception:
        return pd.DataFrame()
def _clean_sh(df: pd.DataFrame) -> pd.DataFrame:
   
    df.columns = [c.strip().lower() for c in df.columns]
    rename = {}
    for c in df.columns:
        if "sym"  in c:                       rename[c] = "symbol"
        elif "qtr" in c or "quarter" in c:    rename[c] = "quarter"
        elif "cat" in c:                       rename[c] = "category"
        elif "pct" in c or "val" in c or "%" in c: rename[c] = "pct"
    df.rename(columns=rename, inplace=True)
    required = {"symbol", "quarter", "category", "pct"}
    if not required.issubset(df.columns):
        st.error(f"Shareholding CSV missing columns. Found: {list(df.columns)}")
        return pd.DataFrame()
    df["symbol"] = df["symbol"].astype("category")
    df["category"] = df["category"].astype("category")
    df["quarter"] = df["quarter"].astype("category")
    df["pct"]      = pd.to_numeric(df["pct"], errors="coerce")
    df.dropna(subset=["pct"], inplace=True)
    df["symbol"]   = df["symbol"].str.upper().str.strip()
    df["category"] = df["category"].str.strip()
    return df.reset_index(drop=True)


def _clean_fin(df: pd.DataFrame) -> pd.DataFrame:
    
    df.columns = [c.strip().lower() for c in df.columns]
    rename = {}
    for c in df.columns:
        if "sym"    in c: rename[c] = "symbol"
        elif "period" in c or "quarter" in c or "qtr" in c: rename[c] = "period"
        elif "freq"   in c: rename[c] = "freq"
        elif "metric" in c: rename[c] = "metric"
        elif "val"    in c or "pct" in c: rename[c] = "value"
    df.rename(columns=rename, inplace=True)
    required = {"symbol", "period", "metric", "value"}
    if not required.issubset(df.columns):
        st.error(f"Financials CSV missing columns. Found: {list(df.columns)}")
        return pd.DataFrame()
    df["symbol"] = df["symbol"].astype("category")
    df["metric"] = df["metric"].astype("category")
    df["period"] = df["period"].astype("category")
    df["value"]  = pd.to_numeric(df["value"], errors="coerce")
    df.dropna(subset=["value"], inplace=True)
    df["symbol"] = df["symbol"].str.upper().str.strip()
    df["metric"] = df["metric"].str.strip()
    return df.reset_index(drop=True)


# ─── Sorting utilities ────────────────────────────────────────────────────────

def sort_quarters(df: pd.DataFrame, col: str = "quarter") -> pd.DataFrame:
    month_order = {
        "jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
        "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
        "q1":1,"q2":4,"q3":7,"q4":10,
    }
    def key(q):
        parts = str(q).lower().split()
        for p in parts:
            if p in month_order:
                for p2 in parts:
                    try:
                        return int(p2) * 100 + month_order[p]
                    except ValueError:
                        pass
        return 0
    quarters   = df[col].unique().tolist()
    sorted_q   = sorted(quarters, key=key)
    df[col]    = pd.Categorical(df[col], categories=sorted_q, ordered=True)
    return df.sort_values(col)


def sort_periods(df: pd.DataFrame) -> pd.DataFrame:
    return sort_quarters(df, col="period")


# ─── Computed helpers ─────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_latest_metrics(df_sh: pd.DataFrame, df_fin: pd.DataFrame, df_cf: pd.DataFrame, symbols: tuple, categories: tuple):
    """Cache latest metrics for all symbols/categories to avoid repeated filtering."""
    latest_sh_cache = {}
    latest_fin_cache = {}
    latest_cf_cache = {}
    
    for symbol in symbols:
        for category in categories:
            key = (symbol, category)
            sub = df_sh[(df_sh["symbol"] == symbol) & (df_sh["category"] == category)]
            if not sub.empty:
                latest_sh_cache[key] = sort_quarters(sub.copy()).iloc[-1]["pct"]
        
        for metric in ["Sales", "EBITDA", "Net Profit", "EPS"]:
            key = (symbol, metric)
            sub = df_fin[(df_fin["symbol"] == symbol) & (df_fin["metric"] == metric)]
            if not sub.empty:
                latest_fin_cache[key] = sort_periods(sub.copy()).iloc[-1]["value"]
        
        #for metric in ["CFO", "CFI", "CFF"]:
        for metric in ["CFO","CFI","CFF","Free Cash Flow","Capex","Net Cash Flow",]:    
            key = (symbol, metric)
            sub = df_cf[(df_cf["symbol"] == symbol) & (df_cf["metric"] == metric)]
            if not sub.empty:
                latest_cf_cache[key] = sort_periods(sub.copy()).iloc[-1]["value"]
    
    return latest_sh_cache, latest_fin_cache, latest_cf_cache

def latest_sh(df: pd.DataFrame, symbol: str, category: str) -> float | None:
    sub = df[(df["symbol"] == symbol) & (df["category"] == category)]
    if sub.empty:
        return None
    return sort_quarters(sub.copy()).iloc[-1]["pct"]


def qoq_sh(df: pd.DataFrame, symbol: str, category: str) -> float | None:
    sub = df[(df["symbol"] == symbol) & (df["category"] == category)]
    if len(sub) < 2:
        return None
    sub = sort_quarters(sub.copy())
    return round(sub.iloc[-1]["pct"] - sub.iloc[-2]["pct"], 2)


def latest_fin(df: pd.DataFrame, symbol: str, metric: str) -> float | None:
    sub = df[(df["symbol"] == symbol) & (df["metric"] == metric)]
    if sub.empty:
        return None
    return sort_periods(sub.copy()).iloc[-1]["value"]


def qoq_fin(df: pd.DataFrame, symbol: str, metric: str) -> float | None:
    sub = df[(df["symbol"] == symbol) & (df["metric"] == metric)]
    if len(sub) < 2:
        return None
    sub = sort_periods(sub.copy())
    return round(sub.iloc[-1]["value"] - sub.iloc[-2]["value"], 2)


def yoy_fin(df: pd.DataFrame, symbol: str, metric: str) -> float | None:
    """YoY growth % (latest vs 4 quarters ago)."""
    sub = df[(df["symbol"] == symbol) & (df["metric"] == metric)]
    if len(sub) < 5:
        return None
    sub = sort_periods(sub.copy()).reset_index(drop=True)
    v_now  = sub.iloc[-1]["value"]
    v_prev = sub.iloc[-5]["value"]
    if v_prev == 0:
        return None
    return round((v_now - v_prev) / abs(v_prev) * 100, 1)

def latest_cf(df: pd.DataFrame, symbol: str, metric: str) -> float | None:
    sub = df[(df["symbol"] == symbol) & (df["metric"] == metric)]
    if sub.empty:
        return None
    return sort_periods(sub.copy()).iloc[-1]["value"]


def yoy_cf(df: pd.DataFrame, symbol: str, metric: str) -> float | None:
    sub = df[(df["symbol"] == symbol) & (df["metric"] == metric)]

    if len(sub) < 2:
        return None

    sub = sort_periods(sub.copy()).reset_index(drop=True)

    latest = sub.iloc[-1]["value"]
    prev   = sub.iloc[-2]["value"]

    if prev == 0:
        return None

    return round((latest - prev) / abs(prev) * 100, 1)

# ─── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("📊 Stock Tracker")
    st.caption("Source: Screener.in")

    if st.button("🔄 Reload data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    with st.spinner("📊 Loading data..."):
        df_sh   = load_master_sh()
        df_fin  = load_master_fin()
        df_cf   = load_master_cf()
        df_snap = load_snapshot()
        df_ca   = load_corporate_actions()

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
        ["Symbol A–Z", "FII % ↓", "FII % ↑", "FII QoQ change ↓",
         "Promoter % ↓", "Sales ↓", "Net Profit ↓", "Market Cap ↓"],
    )
    filter_by = st.selectbox(
        "Filter to",
        ["All", "FII increasing", "FII decreasing", "FII > 20%", "FII < 5%",
         "Net Profit +ve", "Sales growth YoY"],
    )


# ─── Filter data ──────────────────────────────────────────────────────────────

df_sh_f = df_sh[
    df_sh["symbol"].isin(selected_symbols) &
    df_sh["category"].isin(selected_cats)
].copy() if not df_sh.empty else pd.DataFrame()

df_fin_f = df_fin[df_fin["symbol"].isin(selected_symbols)].copy() if not df_fin.empty else pd.DataFrame()

def make_period_key(series):

    month_order = {
        "jan":1,"feb":2,"mar":3,"apr":4,
        "may":5,"jun":6,"jul":7,"aug":8,
        "sep":9,"oct":10,"nov":11,"dec":12,
        "q1":1,"q2":4,"q3":7,"q4":10,
    }

    def parse(q):

        parts = str(q).lower().split()

        yr = 0
        mo = 0

        for p in parts:

            if p in month_order:
                mo = month_order[p]

            elif p.isdigit() and len(p) == 4:
                yr = int(p)

        return yr * 100 + mo

    return series.map(parse)
# ─── Build summary table ──────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def build_summary(df_sh, df_fin, df_cf, df_snap, syms, cats):
    # ─── FAST LOOKUP MAPS ─────────────────────────────────────────────

      # ─── PRECOMPUTED SORT KEYS ─────────────────────────────

    if "sort_key" not in df_fin.columns:
        df_fin = df_fin.copy()
        df_fin["sort_key"] = make_period_key(df_fin["period"])

    if "sort_key" not in df_cf.columns:
        df_cf = df_cf.copy()
        df_cf["sort_key"] = make_period_key(df_cf["period"])

    if "sort_key" not in df_sh.columns:
        df_sh = df_sh.copy()
        df_sh["sort_key"] = make_period_key(df_sh["quarter"])
    
    
    fin_latest_map = (
    df_fin.sort_values("sort_key")
    .groupby(["symbol", "metric"])
    .last()["value"]
    .to_dict()
)

    sh_latest_map = (
        df_sh.sort_values("sort_key")
        .groupby(["symbol", "category"])
        .last()["pct"]
        .to_dict()
    )

    cf_latest_map = (
        df_cf.sort_values("sort_key")
        .groupby(["symbol", "metric"])
        .last()["value"]
        .to_dict()
    )
    
      
    # df_fin["sort_key"] = make_period_key(df_fin["period"])
    # df_cf["sort_key"] = make_period_key(df_cf["period"])
    # df_sh["sort_key"] = make_period_key(df_sh["quarter"])
        # ─── QoQ / YoY LOOKUP MAPS ─────────────────────────────────────

    sh_qoq_map = {}

    for (sym, cat), grp in df_sh.groupby(["symbol", "category"]):

        grp = sort_quarters(grp)

        vals = grp["pct"].tolist()

        if len(vals) >= 2:

            sh_qoq_map[(sym, cat)] = round(
                vals[-1] - vals[-2],
                2
            )

    fin_qoq_map = {}
    fin_yoy_map = {}

    for (sym, met), grp in df_fin.groupby(["symbol", "metric"]):

       # grp = sort_periods(grp)

        
        
        grp = grp.sort_values("sort_key")
        vals = grp["value"].tolist()
        # QoQ
        if len(vals) >= 2:

            fin_qoq_map[(sym, met)] = round(
                vals[-1] - vals[-2],
                2
            )

        # YoY
        if len(vals) >= 5 and vals[-5] != 0:

            fin_yoy_map[(sym, met)] = round(
                (vals[-1] - vals[-5]) / abs(vals[-5]) * 100,
                1
            )

    cf_yoy_map = {}

    for (sym, met), grp in df_cf.groupby(["symbol", "metric"]):
        # df_fin["sort_key"] = make_period_key(df_fin["period"])
        # df_cf["sort_key"] = make_period_key(df_cf["period"])
        # df_sh["sort_key"] = make_period_key(df_sh["quarter"])
        grp = grp.sort_values("sort_key")
        #grp = sort_periods(grp)

        vals = grp["value"].tolist()

        if len(vals) >= 2 and vals[-2] != 0:

            cf_yoy_map[(sym, met)] = round(
                (vals[-1] - vals[-2]) / abs(vals[-2]) * 100,
                1
            )
    
    
    snap_map = (
    df_snap.set_index("symbol").to_dict("index")
    if not df_snap.empty
    else {}
    )
    rows = []
    for sym in syms:
        row = {"symbol": sym}
        for cat in cats:
           # row[f"{cat} %"]   = latest_sh(df_sh, sym, cat)
            row[f"{cat} %"] = sh_latest_map.get((sym, cat))
            #row[f"{cat} QoQ"] = qoq_sh(df_sh, sym, cat)
            row[f"{cat} QoQ"] = sh_qoq_map.get((sym, cat))
        for met in ["Sales", "EBITDA", "Net Profit", "EPS"]:
            #row[met]             = latest_fin(df_fin, sym, met)
            row[met] = fin_latest_map.get((sym, met))
            #row[f"{met} QoQ"]    = qoq_fin(df_fin, sym, met)
            row[f"{met} QoQ"] = fin_qoq_map.get((sym, met))
            #row[f"{met} YoY %"]  = yoy_fin(df_fin, sym, met)
            #row[f"{met} YoY %"] = yoy_fin(df_fin, sym, met)
            row[f"{met} YoY %"] = fin_yoy_map.get((sym, met))
        
        # Cash Flow
        # for met in ["CFO", "CFI", "CFF"]:
        for met in ["CFO","CFI","CFF","Free Cash Flow","Capex","Net Cash Flow",]:    
            #row[f"{met}"] = latest_cf(df_cf, sym, met)
            row[f"{met}"] = cf_latest_map.get((sym, met))
            #row[f"{met} YoY %"] = yoy_cf(df_cf, sym, met)
            row[f"{met} YoY %"] = cf_yoy_map.get((sym, met))

        # Snapshot
        if not df_snap.empty:
            #snap_row = df_snap[df_snap["symbol"] == sym]
            #snap_map = df_snap.set_index("symbol").to_dict("index")
            snap = snap_map.get(sym, {})

            row["LTP"] = snap.get("ltp")
            row["MCap (Cr)"] = snap.get("market_cap_cr")
            # row["LTP"]        = snap_row["ltp"].iloc[0]        if not snap_row.empty else None
            # row["MCap (Cr)"]  = snap_row["market_cap_cr"].iloc[0] if not snap_row.empty else None
        else:
            row["LTP"] = None
            row["MCap (Cr)"] = None
        rows.append(row)
    return pd.DataFrame(rows)


def analyze_cashflow(row):

    notes = []

    cfo  = row.get("CFO")
    fcf  = row.get("Free Cash Flow")
    capx = row.get("Capex")
    netc = row.get("Net Cash Flow")

    cfo_yoy = row.get("CFO YoY %")
    fcf_yoy = row.get("Free Cash Flow YoY %")

    # CFO quality
    if cfo is not None:
        if cfo > 0:
            notes.append("Strong operating cash generation")
        else:
            notes.append("Negative operating cash flow")

    # Free cash flow
    if fcf is not None:
        if fcf > 0:
            notes.append("Positive free cash flow")
        else:
            notes.append("Free cash flow negative")

    # Growth
    if cfo_yoy is not None:
        if cfo_yoy > 20:
            notes.append("Operating cash flow growing strongly")
        elif cfo_yoy < -20:
            notes.append("Operating cash flow deteriorating")

    if fcf_yoy is not None:
        if fcf_yoy > 20:
            notes.append("Free cash flow improving")
        elif fcf_yoy < -20:
            notes.append("Free cash flow weakening")

    # Capex
    if capx is not None and cfo is not None:
        if abs(capx) > cfo:
            notes.append("Heavy capex relative to operating cash")

    # Net cash
    if netc is not None:
        if netc > 0:
            notes.append("Net cash increasing")
        else:
            notes.append("Net cash declining")

    return " | ".join(notes)

tech_map = {}

if not df_tech.empty:

    tech_map = (
        df_tech
        .set_index("symbol")
        .to_dict("index")
    )
summary = build_summary(
    df_sh,
    df_fin,
    df_cf,
    df_snap,
    df_tech,
    tuple(selected_symbols),
    tuple(selected_cats),
    
)
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
else:                          summary = summary.sort_values("symbol")

filtered_symbols = summary["symbol"].tolist()


# ─── Market-wide stats ────────────────────────────────────────────────────────

st.title("Stock Analytics Dashboard")
st.caption(f"Data from Screener.in · {len(symbols)} stocks · "
           f"{df_sh['quarter'].nunique() if not df_sh.empty else 0} quarters")

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

st.markdown("---")


# ─── Tabs ─────────────────────────────────────────────────────────────────────


tab1, tab2, tab_cf, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11, tab12 = st.tabs([
    "📈 Shareholding",
    "💰 Financials",
    "💵 Cash Flow",
    "🔢 Summary table",
    "🗺 FII heatmap",
    "📊 Cross-stock compare",
    "📋 Screener view",
    "🌐 FPI Analysis",
    "🔔 TV Alerts",
    "🎯 Corporate Actions",
    "🏦 Bulk Deals",
    "⚡ Block Deals",
    "🕵️ Insider Trading",
])
# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Individual stock shareholding trend
# ══════════════════════════════════════════════════════════════════════════════

with tab1:
    stock = st.selectbox("Select stock", filtered_symbols or symbols, key="sh_stock")
    sub   = df_sh[df_sh["symbol"] == stock].copy() if not df_sh.empty else pd.DataFrame()
    sub   = sort_quarters(sub) if not sub.empty else sub

    if sub.empty:
        st.warning(f"No shareholding data for {stock}.")
    else:
        k_cols = st.columns(4)
        for i, cat in enumerate(["Promoters","FIIs","DIIs","Public"]):
            lv  = latest_sh(df_sh, stock, cat)
            chg = qoq_sh(df_sh, stock, cat)
            if lv is None:
                continue
            chg_str = (f"+{chg:.2f}%" if chg and chg > 0 else f"{chg:.2f}%") if chg else "—"
            chg_css = "up" if chg and chg > 0 else ("down" if chg and chg < 0 else "neu")
            k_cols[i % 4].markdown(f"""
            <div class="metric-card">
                <div class="metric-label">{cat}</div>
                <div class="metric-val">{lv:.2f}%</div>
                <div class="metric-sub {chg_css}">QoQ: {chg_str}</div>
            </div>""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        fig = go.Figure()
        for cat in sub["category"].unique():
            cat_df = sub[sub["category"] == cat]
            fig.add_trace(go.Scatter(
                x=cat_df["quarter"].astype(str), y=cat_df["pct"],
                name=cat, mode="lines+markers",
                line=dict(color=CATEGORY_COLORS.get(cat,"#888"), width=2.5,
                          dash="dot" if cat in ("Promoters","Public") else "solid"),
                marker=dict(size=6),
                hovertemplate=f"<b>{cat}</b><br>%{{x}}<br>%{{y:.2f}}%<extra></extra>",
            ))
        fig.update_layout(
            title=f"{stock} — Quarterly shareholding",
            xaxis_title="Quarter", yaxis_title="Shareholding %",
            yaxis_ticksuffix="%", hovermode="x unified", template="plotly_white",
            legend=dict(orientation="h", y=-0.2), height=420,
            margin=dict(l=40,r=20,t=50,b=60),
        )
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("Raw data table"):
            pivot = sub.pivot_table(index="quarter", columns="category", values="pct").reset_index()
            display_pivot = pivot.copy()

            for c in display_pivot.columns:

                if c == "quarter" or c == "period":
                    continue

                try:
                    display_pivot[c] = display_pivot[c].apply(
                        lambda x: f"{x:,.2f}"
                        if pd.notna(x)
                        else "—"
                    )

                except Exception:
                    pass

            st.dataframe(
                display_pivot,
                use_container_width=True,
                hide_index=True,
            )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Individual stock financials
# ══════════════════════════════════════════════════════════════════════════════

with tab2:
    col_a, col_b = st.columns([3, 1])
    with col_a:
        fin_stock = st.selectbox("Select stock", filtered_symbols or symbols, key="fin_stock")
    with col_b:
        fin_freq = st.selectbox("Frequency", ["quarterly", "annual"], key="fin_freq")

    sub_fin = df_fin[
        (df_fin["symbol"] == fin_stock) &
        (df_fin["freq"] == fin_freq)
    ] if not df_fin.empty else pd.DataFrame()

    if sub_fin.empty:
        st.info(f"No financials data for **{fin_stock}** ({fin_freq}). "
                "Run screener_fetcher.py to fetch data.")
    else:
        sub_fin = sort_periods(sub_fin)

        # ── KPI cards ────────────────────────────────────────────────────────
        kpi_cols = st.columns(5)
        snap_row  = df_snap[df_snap["symbol"] == fin_stock] if not df_snap.empty else pd.DataFrame()

        # LTP & MCap from snapshot
        ltp_val  = snap_row["ltp"].iloc[0]        if not snap_row.empty else None
        mcap_val = snap_row["market_cap_cr"].iloc[0] if not snap_row.empty else None

        kpi_items = [
            ("LTP",        f"₹{ltp_val:,.0f}"  if ltp_val  else "—", "", ""),
            ("Market Cap", f"₹{mcap_val/100:,.0f}k Cr" if mcap_val and mcap_val>1000 else
                           (f"₹{mcap_val:,.0f} Cr" if mcap_val else "—"), "", ""),
        ]
        for met in ["Sales","Net Profit","EPS"]:
            lv  = latest_fin(df_fin, fin_stock, met)
            chg = yoy_fin(df_fin, fin_stock, met)
            unit = METRIC_UNITS.get(met,"")
            val_str = f"{lv:,.1f} {unit}" if lv is not None else "—"
            chg_str = (f"+{chg:.1f}% YoY" if chg and chg > 0 else f"{chg:.1f}% YoY") if chg else "—"
            chg_css = "up" if chg and chg > 0 else ("down" if chg and chg < 0 else "neu")
            kpi_items.append((met, val_str, chg_str, chg_css))

        for col, (label, val, sub, css) in zip(kpi_cols, kpi_items):
            col.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">{label}</div>
                <div class="metric-val">{val}</div>
                <div class="metric-sub {css}">{sub}</div>
            </div>""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # ── Metric selector ──────────────────────────────────────────────────
        available_metrics = sub_fin["metric"].unique().tolist()
        selected_metrics  = st.multiselect(
            "Metrics to plot",
            options=available_metrics,
            default=[m for m in ["Sales","EBITDA","Net Profit"] if m in available_metrics],
            key="fin_metrics",
        )

        if selected_metrics:
            # Dual-axis: revenue-scale metrics on left, margin/EPS on right
            margin_metrics = {"EBITDA Margin %", "EPS"}
            left_metrics   = [m for m in selected_metrics if m not in margin_metrics]
            right_metrics  = [m for m in selected_metrics if m in margin_metrics]

            fig_fin = go.Figure()
            periods = sorted(sub_fin["period"].unique(), key=lambda q: (
                lambda parts, mo={
                    "jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
                    "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
                    "q1":1,"q2":4,"q3":7,"q4":10,
                }: next(
                    (int(p2)*100+mo[p] for p in parts if p in mo for p2 in parts
                     if p2.isdigit() and len(p2)==4), 0
                )
            )(str(q).lower().split()))

            for met in left_metrics:
                met_df = sub_fin[sub_fin["metric"] == met].copy()
                met_df = sort_periods(met_df)
                color  = METRIC_COLORS.get(met, "#555")
                fig_fin.add_trace(go.Bar(
                    x=met_df["period"].astype(str), y=met_df["value"],
                    name=met, marker_color=color, opacity=0.85,
                    hovertemplate=f"<b>{met}</b><br>%{{x}}<br>₹%{{y:,.1f}} Cr<extra></extra>",
                    yaxis="y1",
                ))

            for met in right_metrics:
                met_df = sub_fin[sub_fin["metric"] == met].copy()
                met_df = sort_periods(met_df)
                color  = METRIC_COLORS.get(met, "#888")
                unit   = METRIC_UNITS.get(met, "")
                fig_fin.add_trace(go.Scatter(
                    x=met_df["period"].astype(str), y=met_df["value"],
                    name=met, mode="lines+markers",
                    line=dict(color=color, width=2.5, dash="dot"),
                    marker=dict(size=7),
                    hovertemplate=f"<b>{met}</b><br>%{{x}}<br>%{{y:.2f}} {unit}<extra></extra>",
                    yaxis="y2",
                ))

            fig_fin.update_layout(
                title=f"{fin_stock} — {fin_freq.title()} financials",
                xaxis_title="Period",
                yaxis=dict(title="₹ Crore", tickprefix="₹"),
                yaxis2=dict(title="% / ₹", overlaying="y", side="right", showgrid=False),
                hovermode="x unified", template="plotly_white",
                legend=dict(orientation="h", y=-0.2),
                barmode="group", height=460,
                margin=dict(l=60,r=60,t=50,b=80),
            )
            st.plotly_chart(fig_fin, use_container_width=True)

        # Growth table
        with st.expander("Quarterly data table"):
            pivot_fin = sub_fin.pivot_table(
                index="period", columns="metric", values="value", aggfunc="first"
            ).reset_index()
            st.dataframe(
                pivot_fin.style.format({c: "{:,.2f}" for c in pivot_fin.columns if c != "period"}),
                use_container_width=True,
            )



# ══════════════════════════════════════════════════════════════════════════════
# CASH FLOW TAB
# ══════════════════════════════════════════════════════════════════════════════

with tab_cf:

    st.subheader("Cash Flow Analysis")

    cf_stock = st.selectbox(
        "Select stock",
        filtered_symbols or symbols,
        key="cf_stock",
    )

    sub_cf = df_cf[df_cf["symbol"] == cf_stock] if not df_cf.empty else pd.DataFrame()

    if sub_cf.empty:
        st.warning(f"No cash flow data available for {cf_stock}")

    else:
        sub_cf = sort_periods(sub_cf)

        # ─── KPI CARDS ─────────────────────────────────────────────────────

        cf_kpis = st.columns(4)

        for idx, met in enumerate([
            "CFO",
            "CFI",
            "CFF",
            "Net Cash Flow",
        ]):

            met_df = sub_cf[sub_cf["metric"] == met]

            if met_df.empty:
                continue

            latest_val = met_df.iloc[-1]["value"]

            prev_val = None
            if len(met_df) >= 2:
                prev_val = met_df.iloc[-2]["value"]

            delta = None
            if prev_val not in (None, 0):
                delta = round((latest_val - prev_val) / abs(prev_val) * 100, 1)

            delta_str = (
                f"{delta:+.1f}%"
                if delta is not None
                else "—"
            )

            css = (
                "up" if delta and delta > 0
                else "down" if delta and delta < 0
                else "neu"
            )

            cf_kpis[idx].markdown(f"""
            <div class="metric-card">
                <div class="metric-label">{met}</div>
                <div class="metric-val">₹{latest_val:,.0f} Cr</div>
                <div class="metric-sub {css}">
                    YoY: {delta_str}
                </div>
            </div>
            """, unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

        # ─── Metric Selector ─────────────────────────────────────────────

        available_cf_metrics = sub_cf["metric"].unique().tolist()

        selected_cf_metrics = st.multiselect(
            "Cash flow metrics",
            options=available_cf_metrics,
            default=[
                m for m in [
                    "CFO",
                    "CFI",
                    "CFF",
                    "Free Cash Flow",
                    "Net Cash Flow",
                ] if m in available_cf_metrics
            ],
            key="cf_metrics",
        )
        # ─── CHART ───────────────────────────────────────────────────────

        if selected_cf_metrics:

            fig_cf = go.Figure()

            for met in selected_cf_metrics:

                met_df = sub_cf[sub_cf["metric"] == met]

                met_df = sort_periods(met_df)

                color = CF_COLORS.get(met, "#888")

                if met in ["Capex", "CFI"]:

                    fig_cf.add_trace(go.Bar(
                        x=met_df["period"].astype(str),
                        y=met_df["value"],
                        name=met,
                        marker_color=color,
                        opacity=0.85,
                        hovertemplate=f"<b>{met}</b><br>%{{x}}<br>₹%{{y:,.1f}} Cr<extra></extra>",
                    ))
                else:

                    fig_cf.add_trace(go.Scatter(
                        x=met_df["period"].astype(str),
                        y=met_df["value"],
                        name=met,
                        mode="lines+markers",
                        line=dict(color=color, width=3),
                        marker=dict(size=7),
                        hovertemplate=f"<b>{met}</b><br>%{{x}}<br>₹%{{y:,.1f}} Cr<extra></extra>",
                    ))

            fig_cf.update_layout(
                title=f"{cf_stock} — Cash Flow Trend",
                xaxis_title="Year",
                yaxis_title="₹ Crore",
                hovermode="x unified",
                template="plotly_white",
                height=500,
                legend=dict(
                    orientation="h",
                    y=-0.25
                ),
                margin=dict(
                    l=50,
                    r=20,
                    t=50,
                    b=90,
                ),
            )

            fig_cf.add_hline(
                y=0,
                line_width=1,
                line_dash="dot",
                line_color="#999"
            )

            st.plotly_chart(fig_cf, use_container_width=True)

            # ─── RAW TABLE ──────────────────────────────────────────────────

        with st.expander("Cash flow table"):

            pivot_cf = sub_cf.pivot_table(
                index="period",
                columns="metric",
                values="value",
                aggfunc="first",
            ).reset_index()

            st.dataframe(
                pivot_cf.style.format({
                    c: "₹{:,.2f} Cr"
                    for c in pivot_cf.columns
                    if c != "period"
                }),
                use_container_width=True,
            )




# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Summary table
# ══════════════════════════════════════════════════════════════════════════════

with tab3:
    st.subheader(f"Shareholding + financials snapshot — {len(filtered_symbols)} stocks")

    def color_chg(val):
        if pd.isna(val): return ""
        if val > 0: return "color: #1e7e34; font-weight: 500"
        if val < 0: return "color: #c0392b; font-weight: 500"
        return ""

    sh_pct_cols  = [c for c in summary.columns if c.endswith(" %") and not "YoY" in c and not "Margin" in c]
    sh_qoq_cols  = [c for c in summary.columns if "QoQ" in c and any(x in c for x in ["FII","DII","Promoter","Public"])]
    #fin_val_cols = ["Sales","EBITDA","Net Profit","EPS","LTP","MCap (Cr)"]
    fin_val_cols = ["Sales","EBITDA","Net Profit","EPS","CFO","Free Cash Flow","Capex","Net Cash Flow","LTP","MCap (Cr)",]
    fin_yoy_cols = [c for c in summary.columns if "YoY" in c]
    fin_qoq_cols = [c for c in summary.columns if "QoQ" in c and c not in sh_qoq_cols]

    # Show columns in logical order
    show_cols = (["symbol"] +
                 [c for c in sh_pct_cols if c in summary.columns] +
                 [c for c in sh_qoq_cols if c in summary.columns] +
                 [c for c in fin_val_cols if c in summary.columns] +
                 [c for c in fin_yoy_cols if c in summary.columns])
    show_cols.append("Cash Flow Analysis")
    show_cols = [c for c in show_cols if c in summary.columns]

    fmt = {}
    for c in show_cols:
        if c == "symbol":       continue
        if c == "Cash Flow Analysis": continue
        if "LTP" in c:          fmt[c] = "₹{:,.1f}"
        elif "MCap" in c:       fmt[c] = "₹{:,.0f}"
        elif "YoY" in c:        fmt[c] = "{:+.1f}%"
        elif "QoQ" in c:        fmt[c] = "{:+.2f}%"
        elif c.endswith(" %"):  fmt[c] = "{:.2f}%"
        else:                   fmt[c] = "{:,.1f}"

    # styled = (
    #     summary[show_cols].style
    #     .format(fmt, na_rep="—")
    #     .map(color_chg, subset=[c for c in sh_qoq_cols + fin_yoy_cols + fin_qoq_cols if c in show_cols])
    #     .set_properties(**{"font-size": "13px"})
    # )
    # st.dataframe(styled, use_container_width=True, height=500)
    # st.download_button("⬇ Download as CSV",
    #                    summary.to_parquet(index=False),
    #                    "stock_summary.parquet", "text/csv")
    
    


    display_df = summary[show_cols].copy()

# Apply formatting without Styler
    for c in display_df.columns:

        if c == "symbol" or c == "Cash Flow Analysis":
            continue

        if c in fmt:

            try:
                display_df[c] = display_df[c].apply(
                    lambda x: fmt[c].format(x)
                    if pd.notna(x)
                    else "—"
                )

            except Exception:
                pass

    st.dataframe(
        display_df,
        use_container_width=True,
        height=500,
    )

    import io

    buffer = io.BytesIO()

    summary.to_parquet(buffer, index=False)

    st.download_button(
        "⬇ Download Parquet",
        data=buffer.getvalue(),
        file_name="stock_summary.parquet",
        mime="application/octet-stream",
)



# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — FII heatmap
# ══════════════════════════════════════════════════════════════════════════════

with tab4:
    st.subheader("Shareholding heatmap across stocks and quarters")
    cat_choice = st.selectbox(
        "Category", options=[c for c in ["FIIs","DIIs","Promoters","Public"]
                             if not df_sh.empty and c in df_sh["category"].unique()],
        key="hm_cat",
    )
    hm_data = df_sh[
        (df_sh["symbol"].isin(filtered_symbols)) &
        (df_sh["category"] == cat_choice)
    ] if not df_sh.empty else pd.DataFrame()

    if hm_data.empty:
        st.info("No data for selected combination.")
    else:
        hm_data = sort_quarters(hm_data)
        pivot   = hm_data.pivot_table(index="symbol", columns="quarter", values="pct", aggfunc="first")
        pivot.columns = pivot.columns.astype(str)
        pivot   = pivot.sort_values(pivot.columns[-1], ascending=False)

        cs = {"FIIs":"Blues","DIIs":"Greens","Promoters":"Greys"}.get(cat_choice, "Oranges")
        fig_hm = px.imshow(pivot, aspect="auto", color_continuous_scale=cs,
                           labels=dict(color=f"{cat_choice} %"),
                           title=f"{cat_choice} % heatmap")
        fig_hm.update_traces(
            hovertemplate="<b>%{y}</b><br>Quarter: %{x}<br>%{z:.2f}%<extra></extra>",
            texttemplate="%{z:.1f}", textfont_size=9,
        )
        fig_hm.update_layout(
            height=max(400, len(pivot)*20+100),
            xaxis_title="Quarter", margin=dict(l=100,r=20,t=50,b=60),
            coloraxis_colorbar=dict(ticksuffix="%"),
        )
        st.plotly_chart(fig_hm, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — Cross-stock compare (shareholding)
# ══════════════════════════════════════════════════════════════════════════════

with tab5:
    st.subheader("Compare metrics across multiple stocks")

    col_a, col_b, col_c = st.columns([3, 1, 1])
    with col_a:
        compare_syms = st.multiselect(
            "Pick stocks",
            options=filtered_symbols or symbols,
            default=(filtered_symbols or symbols)[:min(8, len(filtered_symbols or symbols))],
            key="cmp_syms",
        )
    with col_b:
        cmp_mode = st.selectbox("Mode", ["Shareholding","Financials"], key="cmp_mode")
    with col_c:
        if cmp_mode == "Shareholding":
            cmp_cat = st.selectbox(
                "Category",
                [c for c in ["FIIs","DIIs","Promoters","Public"]
                 if not df_sh.empty and c in df_sh["category"].unique()],
                key="cmp_cat",
            )
        else:
            cmp_metric = st.selectbox(
                "Metric",
                [m for m in ["Sales","EBITDA","Net Profit","EPS","EBITDA Margin %"]
                 if not df_fin.empty and m in df_fin["metric"].unique()],
                key="cmp_metric",
            )

    if not compare_syms:
        st.info("Select at least one stock.")
    else:
        palette = px.colors.qualitative.D3
        fig_cmp = go.Figure()

        if cmp_mode == "Shareholding":
            cmp_data = df_sh[
                df_sh["symbol"].isin(compare_syms) & (df_sh["category"] == cmp_cat)
            ] if not df_sh.empty else pd.DataFrame()
            cmp_data = sort_quarters(cmp_data) if not cmp_data.empty else cmp_data

            for idx, sym in enumerate(compare_syms):
                sym_df = cmp_data[cmp_data["symbol"] == sym]
                if sym_df.empty: continue
                fig_cmp.add_trace(go.Scatter(
                    x=sym_df["quarter"].astype(str), y=sym_df["pct"],
                    name=sym, mode="lines+markers",
                    line=dict(width=2, color=palette[idx%len(palette)]),
                    hovertemplate=f"<b>{sym}</b><br>%{{x}}<br>%{{y:.2f}}%<extra></extra>",
                ))
            fig_cmp.update_layout(
                title=f"{cmp_cat} % — multi-stock",
                yaxis_ticksuffix="%", yaxis_title=f"{cmp_cat} %",
            )

        else:  # Financials
            cmp_data = df_fin[
                df_fin["symbol"].isin(compare_syms) &
                (df_fin["metric"] == cmp_metric) &
                (df_fin["freq"] == "quarterly")
            ] if not df_fin.empty else pd.DataFrame()
            cmp_data = sort_periods(cmp_data) if not cmp_data.empty else cmp_data

            for idx, sym in enumerate(compare_syms):
                sym_df = cmp_data[cmp_data["symbol"] == sym]
                if sym_df.empty: continue
                fig_cmp.add_trace(go.Scatter(
                    x=sym_df["period"].astype(str), y=sym_df["value"],
                    name=sym, mode="lines+markers",
                    line=dict(width=2, color=palette[idx%len(palette)]),
                    hovertemplate=f"<b>{sym}</b><br>%{{x}}<br>%{{y:,.1f}}<extra></extra>",
                ))
            unit = METRIC_UNITS.get(cmp_metric, "")
            fig_cmp.update_layout(
                title=f"{cmp_metric} — multi-stock",
                yaxis_title=f"{cmp_metric} ({unit})",
            )

        fig_cmp.update_layout(
            xaxis_title="Period", hovermode="x unified", template="plotly_white",
            legend=dict(orientation="h", y=-0.25, font_size=11),
            height=440, margin=dict(l=40,r=20,t=50,b=80),
        )
        st.plotly_chart(fig_cmp, use_container_width=True)

        # Latest snapshot bar
        st.markdown("#### Latest snapshot")
        if cmp_mode == "Shareholding":
            bar_data = (cmp_data.sort_values("quarter").groupby("symbol").last()
                        .reset_index()[["symbol","pct","quarter"]]
                        .sort_values("pct", ascending=False))
            y_col, y_lbl = "pct", f"{cmp_cat} %"
            text_fmt = lambda v: f"{v:.1f}%"
        else:
            bar_data = (cmp_data.sort_values("period").groupby("symbol").last()
                        .reset_index()[["symbol","value","period"]]
                        .sort_values("value", ascending=False))
            y_col, y_lbl = "value", cmp_metric
            text_fmt = lambda v: f"{v:,.0f}"

        if not bar_data.empty:
            fig_bar = px.bar(
                bar_data, x="symbol", y=y_col,
                color=y_col, color_continuous_scale="Blues",
                labels={y_col: y_lbl, "symbol": "Stock"},
                text=bar_data[y_col].apply(text_fmt),
            )
            fig_bar.update_traces(textposition="outside")
            fig_bar.update_layout(
                template="plotly_white", coloraxis_showscale=False,
                height=360, margin=dict(l=40,r=20,t=30,b=40),
            )
            st.plotly_chart(fig_bar, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 — Screener-style multi-metric table
# ══════════════════════════════════════════════════════════════════════════════

with tab6:
    st.subheader("Screener-style table — Sales, EBITDA, Net Profit, EPS trend")

    col_l, col_r = st.columns([2,1])
    with col_l:
        scr_syms = st.multiselect(
            "Stocks", options=filtered_symbols or symbols,
            default=(filtered_symbols or symbols)[:min(20, len(filtered_symbols or symbols))],
            key="scr_syms",
        )
    with col_r:
        scr_metric = st.selectbox(
            "Metric",
            [m for m in ["Sales","EBITDA","Net Profit","EPS","EBITDA Margin %"]
             if not df_fin.empty and m in df_fin["metric"].unique()],
            key="scr_metric",
        )

    if not scr_syms or df_fin.empty:
        st.info("Select stocks and make sure financials data is available.")
    else:
        scr_data = df_fin[
            df_fin["symbol"].isin(scr_syms) &
            (df_fin["metric"] == scr_metric) &
            (df_fin["freq"] == "quarterly")
        ]
        scr_data = sort_periods(scr_data)

        if scr_data.empty:
            st.info(f"No quarterly data for metric '{scr_metric}'.")
        else:
            pivot_scr = scr_data.pivot_table(
                index="symbol", columns="period", values="value", aggfunc="first"
            )
            pivot_scr.columns = pivot_scr.columns.astype(str)

            # Add YoY growth column
            if len(pivot_scr.columns) >= 5:
                last  = pivot_scr.columns[-1]
                prev  = pivot_scr.columns[-5]
                pivot_scr["YoY %"] = ((pivot_scr[last] - pivot_scr[prev]) /
                                       pivot_scr[prev].abs() * 100).round(1)
                pivot_scr = pivot_scr.sort_values("YoY %", ascending=False)

            # Add snapshot columns
            if not df_snap.empty:
                snap_idx = df_snap.set_index("symbol")
                pivot_scr["LTP"]       = snap_idx.reindex(pivot_scr.index)["ltp"]
                pivot_scr["MCap (Cr)"] = snap_idx.reindex(pivot_scr.index)["market_cap_cr"]

            unit = METRIC_UNITS.get(scr_metric, "")
            fmt_cols = {}
            for c in pivot_scr.columns:
                if c == "YoY %":     fmt_cols[c] = "{:+.1f}%"
                elif c == "LTP":     fmt_cols[c] = "₹{:,.1f}"
                elif c == "MCap (Cr)": fmt_cols[c] = "₹{:,.0f}"
                else:                fmt_cols[c] = "{:,.1f}"

            def color_yoy(val):
                if pd.isna(val): return ""
                return "color: #1e7e34; font-weight:600" if val > 0 else "color: #c0392b; font-weight:600"

            # styled_scr = (
            #     pivot_scr.style
            #     .format(fmt_cols, na_rep="—")
            #     .applymap(color_yoy, subset=["YoY %"] if "YoY %" in pivot_scr.columns else [])
            #     .background_gradient(
            #         subset=[pivot_scr.columns[-1]] if "YoY %" not in pivot_scr.columns
            #                else [pivot_scr.columns[-3]] if len(pivot_scr.columns) > 2 else [],
            #         cmap="RdYlGn", axis=0,
            #     )
            #     .set_properties(**{"font-size":"13px"})
            # )

            display_scr = pivot_scr.reset_index().copy()

            for c in display_scr.columns:

                if c == "symbol":
                    continue

                try:

                    if c == "YoY %":
                        display_scr[c] = display_scr[c].apply(
                            lambda x: f"{x:+.1f}%"
                            if pd.notna(x)
                            else "—"
                        )

                    elif c == "LTP":
                        display_scr[c] = display_scr[c].apply(
                            lambda x: f"₹{x:,.1f}"
                            if pd.notna(x)
                            else "—"
                        )

                    elif c == "MCap (Cr)":
                        display_scr[c] = display_scr[c].apply(
                            lambda x: f"₹{x:,.0f}"
                            if pd.notna(x)
                            else "—"
                        )

                    else:
                        display_scr[c] = display_scr[c].apply(
                            lambda x: f"{x:,.1f}"
                            if pd.notna(x)
                            else "—"
                        )

                except Exception:
                    pass

            st.dataframe(
                display_scr,
                use_container_width=True,
                height=600,
            )






            #st.dataframe(styled_scr, use_container_width=True, height=600)
            # st.download_button(
            #     f"⬇ Download {scr_metric} table",
            #     pivot_scr.reset_index().to_parquet(index=False),
            #     f"{scr_metric.lower().replace(' ','_')}_trend.parquet",
            #     "text/csv",
            # )


            import io

            buffer = io.BytesIO()

            pivot_scr.reset_index().to_parquet(buffer, index=False)

            st.download_button(
                label=f"⬇ Download {scr_metric} table",
                data=buffer.getvalue(),
                file_name=f"{scr_metric.lower().replace(' ','_')}_trend.parquet",
                mime="application/octet-stream",
            )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 7 — FPI Analysis
# ══════════════════════════════════════════════════════════════════════════════

with tab7:
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
                all_quarters = fpi_trend_data["quarter"].cat.categories.tolist()
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
                st.plotly_chart(fig_fpi, use_container_width=True)
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
            st.plotly_chart(fig_bar, use_container_width=True)

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

with tab8:
    st.subheader("🔔 TradingView Alerts — from Google Sheets")
 
    # ── Refresh button (re-runs the fetcher script) ───────────────────────────
    col_refresh, col_info = st.columns([1, 4])
    with col_refresh:
        if st.button("🔄 Fetch latest alerts", use_container_width=True):
            with st.spinner("Fetching from Google Sheets…"):
                try:
                    result = subprocess.run(
                        ["python", "google_sheets_fetcher.py"],
                        capture_output=True, text=True, timeout=30
                    )
                    if result.returncode == 0:
                        st.success("Alerts updated!")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error(f"Fetcher error:\n{result.stderr[-500:]}")
                except FileNotFoundError:
                    st.error("google_sheets_fetcher.py not found in working directory.")
                except subprocess.TimeoutExpired:
                    st.error("Fetch timed out (30 s).")
 
    df_alerts = load_alerts()
 
    if df_alerts.empty:
        st.info(
            "No alerts found. \n\n"
            "1. Run `python google_sheets_fetcher.py` once from the terminal to pull data.\n"
            "2. Or click **Fetch latest alerts** above after setting up your service account."
        )
        st.stop()
 
    with col_info:
        latest_ts  = df_alerts["date"].max()
        oldest_ts  = df_alerts["date"].min()
        n_alerts   = len(df_alerts)
        n_syms     = df_alerts["symbol"].nunique()
        n_types    = df_alerts["alert_type"].nunique() if "alert_type" in df_alerts.columns else 0
        st.caption(
            f"**{n_alerts}** alerts · **{n_syms}** symbols · **{n_types}** alert types · "
            f"Latest: **{latest_ts.strftime('%d %b %Y %H:%M') if pd.notna(latest_ts) else '—'}** · "
            f"Since: **{oldest_ts.strftime('%d %b %Y') if pd.notna(oldest_ts) else '—'}**"
        )
 
    st.markdown("---")
 
    # ── Sidebar-style filters (inline) ────────────────────────────────────────
    f1, f2, f3, f4 = st.columns([2, 2, 2, 2])
 
    all_syms_al   = sorted(df_alerts["symbol"].unique())
    all_types_al  = sorted(df_alerts["alert_type"].unique()) if "alert_type" in df_alerts.columns else []
 
    with f1:
        sel_syms_al = st.multiselect(
            "Filter by symbol",
            options=all_syms_al,
            default=[],
            placeholder="All symbols",
            key="al_syms",
        )
    with f2:
        sel_types_al = st.multiselect(
            "Filter by alert type",
            options=all_types_al,
            default=[],
            placeholder="All types",
            key="al_types",
        )
    with f3:
        date_range = st.date_input(
            "Date range",
            value=(df_alerts["date"].min().date(), df_alerts["date"].max().date()),
            key="al_dates",
        )
    with f4:
        sort_al = st.selectbox(
            "Sort by",
            ["Newest first", "Oldest first", "Symbol A–Z", "Price ↓", "Price ↑"],
            key="al_sort",
        )
 
    # Apply filters
    al_f = df_alerts
    if sel_syms_al:
        al_f = al_f[al_f["symbol"].isin(sel_syms_al)]
    if sel_types_al:
        al_f = al_f[al_f["alert_type"].isin(sel_types_al)]
    if len(date_range) == 2:
        d0 = pd.Timestamp(date_range[0])
        d1 = pd.Timestamp(date_range[1]) + pd.Timedelta(days=1)
        al_f = al_f[(al_f["date"] >= d0) & (al_f["date"] < d1)]
 
    # Apply sort
    if sort_al == "Newest first":
        al_f = al_f.sort_values("date", ascending=False)
    elif sort_al == "Oldest first":
        al_f = al_f.sort_values("date", ascending=True)
    elif sort_al == "Symbol A–Z":
        al_f = al_f.sort_values("symbol")
    elif sort_al == "Price ↓":
        al_f = al_f.sort_values("price", ascending=False)
    elif sort_al == "Price ↑":
        al_f = al_f.sort_values("price", ascending=True)
 
    # ── KPI strip ─────────────────────────────────────────────────────────────
    kA, kB, kC, kD = st.columns(4)
    for col_k, label_k, val_k in [
        (kA, "Filtered alerts", len(al_f)),
        (kB, "Unique symbols",  al_f["symbol"].nunique()),
        (kC, "Alert types",     al_f["alert_type"].nunique() if "alert_type" in al_f.columns else "—"),
        (kD, "Latest alert",    al_f["date"].max().strftime("%d %b %H:%M") if not al_f.empty and pd.notna(al_f["date"].max()) else "—"),
    ]:
        col_k.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">{label_k}</div>
            <div class="metric-val">{val_k}</div>
        </div>""", unsafe_allow_html=True)
 
    st.markdown("<br>", unsafe_allow_html=True)
 
    # ── Layout: alert feed (left) | charts (right) ────────────────────────────
    col_feed, col_charts = st.columns([2, 3])
 
    # ── Left: Alert feed cards ────────────────────────────────────────────────
    with col_feed:
        st.markdown("#### Alert Feed")
 
        # Colour map for alert types (cycles through a palette)
        ALERT_PALETTE = [
            "#378ADD", "#1D9E75", "#BA7517", "#7F77DD",
            "#D85A30", "#1a7a3e", "#c0392b", "#5f5e5a",
        ]
        type_colors: dict[str, str] = {}
        for idx, t in enumerate(all_types_al):
            type_colors[t] = ALERT_PALETTE[idx % len(ALERT_PALETTE)]
 
        # Show up to 100 most recent
        feed_df = al_f.head(100)
        if feed_df.empty:
            st.info("No alerts match the current filters.")
        else:
            cards = ""
            for _, row in feed_df.iterrows():
                sym       = row.get("symbol", "—")
                price     = row.get("price")
                atype     = row.get("alert_type", "Alert")
                ts        = row.get("date")
                bar_t     = row.get("bar_time", "")
 
                color     = type_colors.get(atype, "#378ADD")
                bg        = color + "15"
                price_str = f"₹{price:,.2f}" if pd.notna(price) else "—"
                ts_str    = ts.strftime("%d %b %Y  %H:%M:%S") if pd.notna(ts) else "—"
                bar_str   = (pd.Timestamp(bar_t).strftime("%d %b %Y") if bar_t and pd.notna(pd.Timestamp(bar_t)) else "")
 
                cards += f"""
                <div style="
                    background:{bg};
                    border-left:3px solid {color};
                    border-radius:6px;
                    padding:8px 12px;
                    margin-bottom:6px;
                ">
                  <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                    <div>
                      <span style="font-weight:700;font-size:14px;">{sym}</span>
                      <span style="
                        background:{color};color:#fff;
                        font-size:10px;font-weight:600;
                        border-radius:4px;padding:1px 6px;
                        margin-left:8px;
                      ">{atype}</span>
                    </div>
                    <div style="font-size:14px;font-weight:700;color:{color};">{price_str}</div>
                  </div>
                  <div style="font-size:11px;color:#6c757d;margin-top:3px;">
                    {ts_str}
                    {"  ·  Bar: " + bar_str if bar_str else ""}
                  </div>
                </div>"""
            st.markdown(cards, unsafe_allow_html=True)
 
    # ── Right: Charts ─────────────────────────────────────────────────────────
    with col_charts:
 
        # ── Chart 1: Alert count by symbol (bar) ──────────────────────────────
        st.markdown("#### Alerts by Symbol")
        if not al_f.empty:
            sym_counts = (
                al_f.groupby(["symbol", "alert_type"]).size()
                .reset_index(name="count")
                .sort_values("count", ascending=False)
            )
            top_syms = sym_counts.groupby("symbol")["count"].sum().nlargest(25).index
            sym_counts = sym_counts[sym_counts["symbol"].isin(top_syms)]
 
            fig_bar_al = go.Figure()
            for atype in sym_counts["alert_type"].unique():
                sub = sym_counts[sym_counts["alert_type"] == atype]
                fig_bar_al.add_trace(go.Bar(
                    x=sub["symbol"], y=sub["count"],
                    name=atype,
                    marker_color=type_colors.get(atype, "#888"),
                    hovertemplate="<b>%{x}</b><br>%{y} alerts<extra></extra>",
                ))
            fig_bar_al.update_layout(
                barmode="stack",
                xaxis_title="Symbol",
                yaxis_title="Alert count",
                template="plotly_white",
                height=280,
                margin=dict(l=40, r=20, t=10, b=60),
                legend=dict(orientation="h", y=-0.35, font_size=10),
                xaxis_tickangle=-45,
            )
            st.plotly_chart(fig_bar_al, use_container_width=True)
        else:
            st.info("No data for chart.")
 
        # ── Chart 2: Alerts over time (timeline) ──────────────────────────────
        st.markdown("#### Alert Timeline")
        if not al_f.empty and pd.notna(al_f["date"]).any():
            al_time = al_f
            al_time["day"] = al_time["date"].dt.normalize()
            day_counts = (
                al_time.groupby(["day", "alert_type"]).size()
                .reset_index(name="count")
            )
 
            fig_time = go.Figure()
            for atype in day_counts["alert_type"].unique():
                sub = day_counts[day_counts["alert_type"] == atype]
                fig_time.add_trace(go.Scatter(
                    x=sub["day"], y=sub["count"],
                    name=atype,
                    mode="lines+markers",
                    stackgroup="one",
                    line=dict(width=1.5, color=type_colors.get(atype, "#888")),
                    hovertemplate=f"<b>{atype}</b><br>%{{x|%d %b}}: %{{y}} alerts<extra></extra>",
                ))
            fig_time.update_layout(
                xaxis_title="Date",
                yaxis_title="Alerts / day",
                template="plotly_white",
                height=250,
                margin=dict(l=40, r=20, t=10, b=40),
                legend=dict(orientation="h", y=-0.35, font_size=10),
                hovermode="x unified",
            )
            st.plotly_chart(fig_time, use_container_width=True)
 
    st.markdown("---")
 
    # ── Per-stock alert detail + FPI overlay ──────────────────────────────────
    st.markdown("#### Per-Stock Alert Detail")
 
    al_stock = st.selectbox(
        "Select stock",
        options=sorted(al_f["symbol"].unique()) if not al_f.empty else [],
        key="al_detail_stock",
    )
 
    if al_stock:
        stock_alerts = al_f[al_f["symbol"] == al_stock]
        stock_alerts = stock_alerts.sort_values("date", ascending=False)
 
        c_detail, c_fpi_overlay = st.columns([1, 2])
 
        with c_detail:
            st.markdown(f"**{al_stock}** — {len(stock_alerts)} alert(s)")
            detail_cards = ""
            for _, row in stock_alerts.iterrows():
                atype     = row.get("alert_type", "Alert")
                price     = row.get("price")
                ts        = row.get("date")
                color     = type_colors.get(atype, "#378ADD")
                price_str = f"₹{price:,.2f}" if pd.notna(price) else "—"
                ts_str    = ts.strftime("%d %b %Y  %H:%M") if pd.notna(ts) else "—"
                detail_cards += f"""
                <div style="background:{color}15;border-left:3px solid {color};
                            border-radius:5px;padding:7px 10px;margin-bottom:5px;">
                  <span style="font-size:11px;background:{color};color:#fff;
                               border-radius:3px;padding:1px 5px;">{atype}</span>
                  <span style="font-size:14px;font-weight:700;float:right;">{price_str}</span>
                  <br><span style="font-size:11px;color:#6c757d;">{ts_str}</span>
                </div>"""
            st.markdown(detail_cards, unsafe_allow_html=True)
 
        with c_fpi_overlay:
            # FPI shareholding trend with alert markers
            fpi_sub = df_sh[
                (df_sh["symbol"] == al_stock) & (df_sh["category"] == "FIIs")
            ] if not df_sh.empty else pd.DataFrame()
 
            if not fpi_sub.empty:
                fpi_sub = sort_quarters(fpi_sub)
                fig_overlay = go.Figure()
 
                # FPI line
                fig_overlay.add_trace(go.Scatter(
                    x=fpi_sub["quarter"].astype(str),
                    y=fpi_sub["pct"],
                    name="FPI %",
                    mode="lines+markers",
                    line=dict(color="#378ADD", width=2.5),
                    marker=dict(size=6),
                    hovertemplate="<b>FPI</b><br>%{x}<br>%{y:.2f}%<extra></extra>",
                ))
 
                # Alert markers (price as annotation on secondary y)
                alert_prices = stock_alerts.dropna(subset=["price", "date"])
                if not alert_prices.empty:
                    fig_overlay.add_trace(go.Scatter(
                        x=alert_prices["date"].dt.strftime("%d %b %Y"),
                        y=alert_prices["price"],
                        name="Alert price",
                        mode="markers",
                        marker=dict(
                            symbol="triangle-up",
                            size=12,
                            color=[type_colors.get(t, "#D85A30") for t in alert_prices["alert_type"]],
                            line=dict(width=1, color="#fff"),
                        ),
                        yaxis="y2",
                        hovertemplate=(
                            "<b>%{customdata}</b><br>"
                            "Date: %{x}<br>"
                            "Price: ₹%{y:,.2f}<extra></extra>"
                        ),
                        customdata=alert_prices["alert_type"],
                    ))
 
                fig_overlay.update_layout(
                    title=f"{al_stock} — FPI trend + alert prices",
                    xaxis_title="Period",
                    yaxis=dict(title="FPI %", ticksuffix="%"),
                    yaxis2=dict(title="Price (₹)", overlaying="y", side="right",
                                showgrid=False, tickprefix="₹"),
                    template="plotly_white",
                    height=360,
                    hovermode="x unified",
                    legend=dict(orientation="h", y=-0.25, font_size=11),
                    margin=dict(l=50, r=60, t=50, b=80),
                )
                st.plotly_chart(fig_overlay, use_container_width=True)
            else:
                # Just show price history of alerts
                # Just show price history of alerts
                alert_prices_valid = stock_alerts.dropna(subset=["price", "date"])
                if not alert_prices_valid.empty:
                    fig_price = go.Figure(go.Scatter(
                        x=alert_prices_valid["date"],
                        y=alert_prices_valid["price"],
                #if not alert_prices_check := stock_alerts.dropna(subset=["price", "date"]).empty:
                 #   fig_price = go.Figure(go.Scatter(
                  #      x=stock_alerts["date"],
                       # y=stock_alerts["price"],
                        mode="markers+lines",
                        marker=dict(size=8, color="#D85A30"),
                        hovertemplate="<b>%{customdata}</b><br>%{x}<br>₹%{y:,.2f}<extra></extra>",
                        customdata=stock_alerts["alert_type"],
                    ))
                    fig_price.update_layout(
                        title=f"{al_stock} — Alert price history",
                        xaxis_title="Date", yaxis_title="Price (₹)",
                        yaxis_tickprefix="₹", template="plotly_white",
                        height=340, margin=dict(l=50, r=20, t=50, b=40),
                    )
                    st.plotly_chart(fig_price, use_container_width=True)
                else:
                    st.info("No FPI data and no price data available for overlay.")
 
    st.markdown("---")
 
    # ── Full alert history table ───────────────────────────────────────────────
    with st.expander("📋 Full alert history table"):
        display_df = al_f
        if "date" in display_df.columns:
            display_df["date"] = display_df["date"].dt.strftime("%d %b %Y  %H:%M:%S")
        if "bar_time" in display_df.columns:
            display_df["bar_time"] = display_df["bar_time"].astype(str)
 
        st.dataframe(
            display_df.style.format({"price": "₹{:,.2f}"}, na_rep="—"),
            use_container_width=True,
            height=400,
        )
        st.download_button(
            "⬇ Download filtered alerts CSV",
            al_f.to_parquet(index=False).encode(),
            "tv_alerts_filtered.parquet",
            "text/csv",
        )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 9 — CORPORATE ACTIONS
# ══════════════════════════════════════════════════════════════════════════════

with tab9:
    st.subheader("Corporate Actions")
    st.caption("Dividends, stock splits, bonus shares, rights issues, etc. from Screener.in")
    
    if df_ca.empty:
        st.info(
            "No corporate actions data available.\n\n"
            "Run `python screener_fetcher.py` to fetch corporate actions from Screener.in."
        )
    else:
        # ── Filter by symbol ────────────────────────────────────────────────────
        ca_symbols = sorted(df_ca["symbol"].unique())
        
        ca_cols = st.columns([2, 2, 1])
        with ca_cols[0]:
            ca_stock = st.selectbox(
                "Select stock",
                options=ca_symbols,
                key="ca_stock"
            )
        
        with ca_cols[1]:
            ca_action_filter = st.multiselect(
                "Filter by action type",
                options=sorted(df_ca["action_type"].unique()),
                default=[],
                placeholder="All types",
                key="ca_action_type"
            )
        
        with ca_cols[2]:
            ca_sort = st.radio("Sort", ["Newest", "Oldest"], horizontal=True, key="ca_sort")
        
        # Filter data
        ca_filtered = df_ca[df_ca["symbol"] == ca_stock]
        
        if ca_action_filter:
            ca_filtered = ca_filtered[ca_filtered["action_type"].isin(ca_action_filter)]
        
        # Sort
        if "date" in ca_filtered.columns:
            ca_filtered = ca_filtered.sort_values(
                "date", 
                ascending=(ca_sort == "Oldest")
            )
        
        if ca_filtered.empty:
            st.warning(f"No corporate actions for {ca_stock}.")
        else:
            # Display summary
            st.markdown(f"#### {ca_stock} — {len(ca_filtered)} action(s)")
            
            # Timeline view with cards
            ca_cards = ""
            action_colors = {
                "dividend": "#1D9E75",
                "split": "#378ADD",
                "bonus": "#BA7517",
                "rights": "#7F77DD",
                "merger": "#D85A30",
                "ipo": "#5f5e5a",
            }
            
            for _, row in ca_filtered.iterrows():
                action = row.get("action_type", "Action")
                date_val = row.get("date")
                value_val = row.get("value", "—")
                description = row.get("description", "")
                
                # Match color to action type
                color = "#378ADD"
                for key, col in action_colors.items():
                    if key.lower() in action.lower():
                        color = col
                        break
                
                date_str = (
                    date_val.strftime("%d %b %Y") 
                    if pd.notna(date_val) 
                    else "Date N/A"
                )
                
                ca_cards += f"""
                <div style="
                    background:{color}10;
                    border-left:4px solid {color};
                    border-radius:8px;
                    padding:12px 16px;
                    margin-bottom:8px;
                ">
                  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:4px;">
                    <div>
                      <span style="
                        font-weight:700;
                        font-size:14px;
                        background:{color};
                        color:#fff;
                        border-radius:4px;
                        padding:2px 8px;
                      ">{action}</span>
                    </div>
                    <span style="font-size:12px;color:#6c757d;">{date_str}</span>
                  </div>
                  <div style="font-size:13px;color:#212529;">
                    <b>Value:</b> {value_val}
                  </div>
                  {f'<div style="font-size:12px;color:#495057;margin-top:4px;"><i>{description}</i></div>' if description else ''}
                </div>"""
            
            st.markdown(ca_cards, unsafe_allow_html=True)
            
            st.markdown("---")
            
            # Download
            ca_display = ca_filtered
            if "date" in ca_display.columns:
                ca_display["date"] = ca_display["date"].dt.strftime("%d %b %Y")
            
            st.download_button(
                f"⬇ Download {ca_stock} corporate actions",
                ca_display.to_parquet(index=False).encode(),
                f"corporate_actions_{ca_stock}.parquet",
                "text/csv",
                key="ca_download"
            )
        
        st.markdown("---")
        
        # ── All stocks corporate actions summary ────────────────────────────────
        st.markdown("#### Market-wide Corporate Actions Summary")
        
        ca_summary = df_ca.groupby("action_type").size().reset_index(name="count")
        ca_summary = ca_summary.sort_values("count", ascending=False)
        
        if not ca_summary.empty:
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Total actions", len(df_ca))
            with col2:
                st.metric("Unique stocks", df_ca["symbol"].nunique())
            with col3:
                st.metric("Action types", df_ca["action_type"].nunique())
            
            st.markdown("**Action breakdown:**")
            
            fig_ca = go.Figure(data=[
                go.Bar(
                    x=ca_summary["action_type"],
                    y=ca_summary["count"],
                    marker_color=[action_colors.get(t.lower(), "#888") for t in ca_summary["action_type"]],
                    text=ca_summary["count"],
                    textposition="outside",
                    hovertemplate="<b>%{x}</b><br>%{y} actions<extra></extra>",
                )
            ])
            fig_ca.update_layout(
                xaxis_title="Action Type",
                yaxis_title="Count",
                template="plotly_white",
                height=300,
                showlegend=False,
                margin=dict(l=40, r=20, t=20, b=60),
            )
            st.plotly_chart(fig_ca, use_container_width=True)
            
            # Table of all corporate actions
            st.markdown("**All corporate actions:**")
            ca_table = df_ca
            if "date" in ca_table.columns:
                ca_table["date"] = ca_table["date"].dt.strftime("%d %b %Y")
            
            st.dataframe(ca_table, use_container_width=True, height=400)

def _deals_fetch_button(label="🔄 Fetch latest deals"):
    if st.button(label, use_container_width=True):
        with st.spinner("Fetching from NSE India…"):
            try:
                result = subprocess.run(
                    ["python", "deals_fetcher.py"],
                    capture_output=True, text=True, timeout=300
                )
                if result.returncode == 0:
                    st.success("Deals data updated!")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(f"Fetcher error:\n{result.stderr[-600:]}")
            except FileNotFoundError:
                st.error("deals_fetcher.py not found in working directory.")
            except subprocess.TimeoutExpired:
                st.error("Fetch timed out (5 min).")
 
 
# ─── Deal type color palette ─────────────────────────────────────────────────
BUY_COLOR  = "#1D9E75"
SELL_COLOR = "#c0392b"
NEUT_COLOR = "#6c757d"
 
 
def _buy_sell_color(val: str) -> str:
    if not val:
        return NEUT_COLOR
    v = str(val).lower()
    if "buy" in v or "purchas" in v or "acqui" in v:
        return BUY_COLOR
    if "sell" in v or "dis" in v:
        return SELL_COLOR
    return NEUT_COLOR
 
 
# ══════════════════════════════════════════════════════════════════════════════
# TAB 10 — BULK DEALS
# ══════════════════════════════════════════════════════════════════════════════
 
with tab10:
    st.subheader("🏦 Bulk Deals")
    st.caption(
        "A **bulk deal** occurs when total quantity traded > 0.5% of a company's total shares. "
        "These are disclosed by brokers to NSE on the same day."
    )
 
    col_r, _ = st.columns([1, 5])
    with col_r:
        _deals_fetch_button("🔄 Fetch Bulk Deals")
 
    df_bulk = load_bulk_deals()
 
    if df_bulk.empty:
        st.info(
            "No bulk deals data found.\n\n"
            "Run `python deals_fetcher.py` from the terminal, or click the button above."
        )
        st.stop()
 
    # ── Filters ──────────────────────────────────────────────────────────────
    f1, f2, f3, f4 = st.columns([2, 2, 2, 2])
    with f1:
        bulk_syms = st.multiselect(
            "Filter by symbol",
            sorted(df_bulk["symbol"].dropna().unique()),
            default=[s for s in selected_symbols if s in df_bulk["symbol"].values],
            placeholder="All symbols",
            key="bulk_sym_filter",
        )
    with f2:
        if "buy_sell" in df_bulk.columns:
            bulk_action = st.multiselect(
                "Buy / Sell",
                sorted(df_bulk["buy_sell"].dropna().unique()),
                key="bulk_action_filter",
            )
        else:
            bulk_action = []
    with f3:
        bulk_date_range = st.date_input(
            "Date range",
            value=(
                max(df_bulk["date"].min().date(), date.today() - timedelta(days=90)),
                date.today()
            ),
            key="bulk_date",
        )
    with f4:
        bulk_sort = st.selectbox(
            "Sort by",
            ["Newest first", "Largest qty", "Largest value"],
            key="bulk_sort",
        )
 
    # Apply filters
    bf = df_bulk
    if bulk_syms:
        bf = bf[bf["symbol"].isin(bulk_syms)]
    if bulk_action:
        bf = bf[bf["buy_sell"].isin(bulk_action)]
    if len(bulk_date_range) == 2:
        bf = bf[(bf["date"] >= pd.Timestamp(bulk_date_range[0])) &
                (bf["date"] <= pd.Timestamp(bulk_date_range[1]) + pd.Timedelta(days=1))]
    if bulk_sort == "Largest qty":
        bf = bf.sort_values("qty", ascending=False)
    elif bulk_sort == "Largest value":
        bf = bf.sort_values("price", ascending=False)
    else:
        bf = bf.sort_values("date", ascending=False)
 
    # ── KPIs ─────────────────────────────────────────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    buys  = bf[bf["buy_sell"].astype(str).str.lower().str.contains("buy|acqui|purchas", na=False)] if "buy_sell" in bf.columns else pd.DataFrame()
    sells = bf[bf["buy_sell"].astype(str).str.lower().str.contains("sell|disp", na=False)]         if "buy_sell" in bf.columns else pd.DataFrame()
    for col_k, lbl, val, css in [
        (k1, "Total deals",     len(bf),                 ""),
        (k2, "Buy deals",       len(buys),               "up"),
        (k3, "Sell deals",      len(sells),              "down"),
        (k4, "Unique stocks",   bf["symbol"].nunique(),  ""),
    ]:
        col_k.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">{lbl}</div>
            <div class="metric-val {css}">{val}</div>
        </div>""", unsafe_allow_html=True)
 
    st.markdown("<br>", unsafe_allow_html=True)
 
    # ── Charts ────────────────────────────────────────────────────────────────
    col_chart1, col_chart2 = st.columns(2)
 
    with col_chart1:
        st.markdown("#### Deal volume by symbol")
        if not bf.empty and "buy_sell" in bf.columns:
            sym_grp = (
                bf.groupby(["symbol", "buy_sell"]).size()
                .reset_index(name="count")
                .sort_values("count", ascending=False)
            )
            top_sym = sym_grp.groupby("symbol")["count"].sum().nlargest(20).index
            sym_grp = sym_grp[sym_grp["symbol"].isin(top_sym)]
 
            fig_bv = go.Figure()
            for action in sym_grp["buy_sell"].unique():
                sub = sym_grp[sym_grp["buy_sell"] == action]
                color = BUY_COLOR if "buy" in str(action).lower() else SELL_COLOR
                fig_bv.add_trace(go.Bar(
                    x=sub["symbol"], y=sub["count"],
                    name=action, marker_color=color,
                    hovertemplate="<b>%{x}</b><br>%{y} deals<extra></extra>",
                ))
            fig_bv.update_layout(
                barmode="stack", template="plotly_white", height=300,
                margin=dict(l=40,r=20,t=10,b=60), xaxis_tickangle=-45,
                legend=dict(orientation="h", y=-0.4),
            )
            st.plotly_chart(fig_bv, use_container_width=True)
        else:
            st.info("No data to chart.")
 
    with col_chart2:
        st.markdown("#### Deal timeline")
        if not bf.empty:
            bf_time = bf
            bf_time["day"] = bf_time["date"].dt.normalize()
            day_grp = bf_time.groupby(["day","buy_sell"]).size().reset_index(name="count") if "buy_sell" in bf_time.columns else bf_time.groupby("day").size().reset_index(name="count")
 
            fig_t = go.Figure()
            if "buy_sell" in day_grp.columns:
                for action in day_grp["buy_sell"].unique():
                    sub = day_grp[day_grp["buy_sell"] == action]
                    color = BUY_COLOR if "buy" in str(action).lower() else SELL_COLOR
                    fig_t.add_trace(go.Scatter(
                        x=sub["day"], y=sub["count"], name=action,
                        mode="lines+markers", line=dict(color=color, width=2),
                        stackgroup="one",
                    ))
            else:
                fig_t.add_trace(go.Scatter(
                    x=day_grp["day"], y=day_grp["count"],
                    mode="lines+markers", line=dict(color="#378ADD", width=2),
                ))
            fig_t.update_layout(
                template="plotly_white", height=300,
                margin=dict(l=40,r=20,t=10,b=40),
                legend=dict(orientation="h", y=-0.3),
                hovermode="x unified",
            )
            st.plotly_chart(fig_t, use_container_width=True)
 
    # ── Data table ────────────────────────────────────────────────────────────
    st.markdown("#### Deal records")
 
    display_cols = [c for c in ["date","symbol","client","buy_sell","qty","price","exchange"] if c in bf.columns]
    bf_disp = bf[display_cols]
    if "date" in bf_disp.columns:
        bf_disp["date"] = bf_disp["date"].dt.strftime("%d %b %Y")
 
    def _color_action(val):
        c = _buy_sell_color(str(val))
        return f"color: {c}; font-weight: 600"
 
    style_bulk = bf_disp.style
    if "buy_sell" in bf_disp.columns:
        style_bulk = style_bulk.applymap(_color_action, subset=["buy_sell"])
    if "qty" in bf_disp.columns:
        style_bulk = style_bulk.format({"qty": "{:,.0f}", "price": "{:,.2f}"}, na_rep="—")
 
    st.dataframe(style_bulk, use_container_width=True, height=450)
    st.download_button(
        "⬇ Download bulk deals CSV",
        bf.to_parquet(index=False).encode(),
        "bulk_deals_filtered.parquet", "text/csv",
        key="bulk_dl",
    )
 
 
# ══════════════════════════════════════════════════════════════════════════════
# TAB 11 — BLOCK DEALS
# ══════════════════════════════════════════════════════════════════════════════
 
with tab11:
    st.subheader("⚡ Block Deals")
    st.caption(
        "A **block deal** is ≥ 5 lakh shares or ₹5 Cr traded as a single transaction "
        "through a special 35-minute morning window (9:15–9:50 AM)."
    )
 
    col_r, _ = st.columns([1, 5])
    with col_r:
        _deals_fetch_button("🔄 Fetch Block Deals")
 
    df_block = load_block_deals()
 
    if df_block.empty:
        st.info(
            "No block deals data found.\n\n"
            "Run `python deals_fetcher.py` from the terminal, or click the button above."
        )
        st.stop()
 
    # ── Filters ──────────────────────────────────────────────────────────────
    f1, f2, f3, f4 = st.columns([2, 2, 2, 2])
    with f1:
        blk_syms = st.multiselect(
            "Filter by symbol",
            sorted(df_block["symbol"].dropna().unique()),
            default=[s for s in selected_symbols if s in df_block["symbol"].values],
            placeholder="All symbols",
            key="blk_sym_filter",
        )
    with f2:
        if "buy_sell" in df_block.columns:
            blk_action = st.multiselect(
                "Buy / Sell",
                sorted(df_block["buy_sell"].dropna().unique()),
                key="blk_action_filter",
            )
        else:
            blk_action = []
    with f3:
        blk_date_range = st.date_input(
            "Date range",
            value=(
                max(df_block["date"].min().date(), date.today() - timedelta(days=90)),
                date.today()
            ),
            key="blk_date",
        )
    with f4:
        blk_sort = st.selectbox(
            "Sort by",
            ["Newest first", "Largest qty", "Largest price"],
            key="blk_sort",
        )
 
    # Apply filters
    blkf = df_block
    if blk_syms:
        blkf = blkf[blkf["symbol"].isin(blk_syms)]
    if blk_action:
        blkf = blkf[blkf["buy_sell"].isin(blk_action)]
    if len(blk_date_range) == 2:
        blkf = blkf[(blkf["date"] >= pd.Timestamp(blk_date_range[0])) &
                    (blkf["date"] <= pd.Timestamp(blk_date_range[1]) + pd.Timedelta(days=1))]
    if blk_sort == "Largest qty":
        blkf = blkf.sort_values("qty", ascending=False)
    elif blk_sort == "Largest price":
        blkf = blkf.sort_values("price", ascending=False)
    else:
        blkf = blkf.sort_values("date", ascending=False)
 
    # ── KPIs ─────────────────────────────────────────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    blk_buys  = blkf[blkf["buy_sell"].astype(str).str.lower().str.contains("buy|acqui|purchas", na=False)] if "buy_sell" in blkf.columns else pd.DataFrame()
    blk_sells = blkf[blkf["buy_sell"].astype(str).str.lower().str.contains("sell|disp", na=False)]         if "buy_sell" in blkf.columns else pd.DataFrame()
    for col_k, lbl, val, css in [
        (k1, "Total block deals", len(blkf),                ""),
        (k2, "Buy deals",         len(blk_buys),            "up"),
        (k3, "Sell deals",        len(blk_sells),           "down"),
        (k4, "Unique stocks",     blkf["symbol"].nunique(), ""),
    ]:
        col_k.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">{lbl}</div>
            <div class="metric-val {css}">{val}</div>
        </div>""", unsafe_allow_html=True)
 
    st.markdown("<br>", unsafe_allow_html=True)
 
    # ── Significant deals highlight ───────────────────────────────────────────
    st.markdown("#### Notable block deals")
    if not blkf.empty and "qty" in blkf.columns:
        # Top 10 by qty
        top_deals = blkf.nlargest(min(10, len(blkf)), "qty")
        cards_html = ""
        for _, row in top_deals.iterrows():
            sym     = row.get("symbol","—")
            client  = row.get("client","Unknown")
            action  = row.get("buy_sell","—")
            qty     = row.get("qty")
            price   = row.get("price")
            dt      = row.get("date")
            color   = _buy_sell_color(str(action))
            qty_str = f"{qty:,.0f}" if pd.notna(qty) else "—"
            price_str = f"₹{price:,.2f}" if pd.notna(price) else "—"
            value_cr = (qty * price / 1e7) if (pd.notna(qty) and pd.notna(price)) else None
            val_str  = f"₹{value_cr:,.1f} Cr" if value_cr else ""
            dt_str  = dt.strftime("%d %b %Y") if pd.notna(dt) else "—"
            cards_html += f"""
            <div style="background:{color}12;border-left:3px solid {color};
                        border-radius:6px;padding:8px 12px;margin-bottom:6px;
                        display:flex;justify-content:space-between;align-items:center;">
              <div>
                <span style="font-weight:700;font-size:14px;">{sym}</span>
                <span style="font-size:12px;color:#6c757d;margin-left:6px;">{client}</span><br>
                <span style="font-size:12px;color:{color};font-weight:600;">{action}</span>
                <span style="font-size:11px;color:#adb5bd;margin-left:8px;">{dt_str}</span>
              </div>
              <div style="text-align:right;">
                <div style="font-size:14px;font-weight:700;">{qty_str} shares</div>
                <div style="font-size:12px;color:#6c757d;">{price_str} {" · " + val_str if val_str else ""}</div>
              </div>
            </div>"""
        st.markdown(cards_html, unsafe_allow_html=True)
    else:
        st.info("No data for notable deals.")
 
    # ── Full data table ───────────────────────────────────────────────────────
    with st.expander("📋 Full block deals table"):
        display_cols = [c for c in ["date","symbol","client","buy_sell","qty","price","exchange"] if c in blkf.columns]
        blkf_disp = blkf[display_cols]
        if "date" in blkf_disp.columns:
            blkf_disp["date"] = blkf_disp["date"].dt.strftime("%d %b %Y")
        st.dataframe(
            blkf_disp.style.format({"qty": "{:,.0f}", "price": "{:,.2f}"}, na_rep="—"),
            use_container_width=True, height=400,
        )
        st.download_button(
            "⬇ Download block deals CSV",
            blkf.to_parquet(index=False).encode(),
            "block_deals_filtered.parquet", "text/csv",
            key="blk_dl",
        )
 
 
# ══════════════════════════════════════════════════════════════════════════════
# TAB 12 — INSIDER TRADING
# ══════════════════════════════════════════════════════════════════════════════
 
with tab12:
    st.subheader("🕵️ Insider Trading (PIT Disclosures)")
    st.caption(
        "SEBI's **Prohibition of Insider Trading** (PIT) regulations mandate disclosure "
        "of all trades by promoters, directors, KMPs, and other designated persons. "
        "Data sourced from NSE PIT filings."
    )
 
    col_r, _ = st.columns([1, 5])
    with col_r:
        _deals_fetch_button("🔄 Fetch Insider Trades")
 
    df_ins = load_insider_trading()
 
    if df_ins.empty:
        st.info(
            "No insider trading data found.\n\n"
            "Run `python deals_fetcher.py` from the terminal, or click the button above."
        )
        st.stop()
 
    # ── Filters ──────────────────────────────────────────────────────────────
    f1, f2, f3, f4 = st.columns([2, 2, 2, 2])
    with f1:
        ins_syms = st.multiselect(
            "Filter by symbol",
            sorted(df_ins["symbol"].dropna().unique()),
            default=[s for s in selected_symbols if s in df_ins["symbol"].values],
            placeholder="All symbols",
            key="ins_sym_filter",
        )
    with f2:
        txn_types = []
        if "transaction_type" in df_ins.columns:
            txn_types = sorted(df_ins["transaction_type"].dropna().unique())
        ins_txn = st.multiselect(
            "Transaction type",
            options=txn_types,
            key="ins_txn_filter",
        )
    with f3:
        ins_date_range = st.date_input(
            "Date range",
            value=(
                max(df_ins["date"].min().date(), date.today() - timedelta(days=365)),
                date.today()
            ),
            key="ins_date",
        )
    with f4:
        ins_sort = st.selectbox(
            "Sort by",
            ["Newest first", "Largest qty", "Largest value"],
            key="ins_sort",
        )
 
    # Apply filters
    insf = df_ins
    if ins_syms:
        insf = insf[insf["symbol"].isin(ins_syms)]
    if ins_txn:
        insf = insf[insf["transaction_type"].isin(ins_txn)]
    if len(ins_date_range) == 2:
        insf = insf[(insf["date"] >= pd.Timestamp(ins_date_range[0])) &
                    (insf["date"] <= pd.Timestamp(ins_date_range[1]) + pd.Timedelta(days=1))]
    if ins_sort == "Largest qty":
        insf = insf.sort_values("qty", ascending=False)
    elif ins_sort == "Largest value":
        insf = insf.sort_values("value", ascending=False)
    else:
        insf = insf.sort_values("date", ascending=False)
 
    # ── KPI strip ─────────────────────────────────────────────────────────────
    k1, k2, k3, k4, k5 = st.columns(5)
    ins_buys  = insf[insf["transaction_type"].astype(str).str.lower().str.contains("buy|acqui|purchas", na=False)] if "transaction_type" in insf.columns else pd.DataFrame()
    ins_sells = insf[insf["transaction_type"].astype(str).str.lower().str.contains("sell|disp", na=False)]         if "transaction_type" in insf.columns else pd.DataFrame()
    net_qty = (insf["qty"].fillna(0) * insf["transaction_type"].astype(str).str.lower().apply(
        lambda x: 1 if "buy" in x or "acqui" in x else (-1 if "sell" in x else 0)
    )).sum() if "qty" in insf.columns else 0
 
    for col_k, lbl, val, css in [
        (k1, "Total disclosures", len(insf),               ""),
        (k2, "Buy / Acquire",     len(ins_buys),           "up"),
        (k3, "Sell / Dispose",    len(ins_sells),          "down"),
        (k4, "Unique insiders",   insf["person"].nunique() if "person" in insf.columns else "—", ""),
        (k5, "Unique stocks",     insf["symbol"].nunique(), ""),
    ]:
        col_k.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">{lbl}</div>
            <div class="metric-val {css}">{val}</div>
        </div>""", unsafe_allow_html=True)
 
    st.markdown("<br>", unsafe_allow_html=True)
 
    # ── Layout ────────────────────────────────────────────────────────────────
    col_feed2, col_chart3 = st.columns([2, 3])
 
    # ── Left: Insider trade cards ──────────────────────────────────────────────
    with col_feed2:
        st.markdown("#### Recent disclosures")
        if insf.empty:
            st.info("No records match the current filters.")
        else:
            cards_html = ""
            for _, row in insf.head(60).iterrows():
                sym     = row.get("symbol","—")
                person  = row.get("person") or row.get("acqName","Unknown")
                txn     = row.get("transaction_type","—")
                qty     = row.get("qty")
                value   = row.get("value")
                pct_b   = row.get("pct_before")
                pct_a   = row.get("pct_after")
                dt      = row.get("date")
                sec_type = row.get("type_of_security","Equity")
                mode    = row.get("mode","")
 
                color     = _buy_sell_color(str(txn))
                qty_str   = f"{qty:,.0f}" if pd.notna(qty) else "—"
                val_str   = f"₹{value:,.2f}" if pd.notna(value) else "—"
                dt_str    = dt.strftime("%d %b %Y") if pd.notna(dt) else "—"
                pct_str   = ""
                if pd.notna(pct_b) and pd.notna(pct_a):
                    arrow = "↑" if float(pct_a) > float(pct_b) else "↓"
                    pct_str = f"{pct_b:.2f}% → {pct_a:.2f}% {arrow}"
 
                cards_html += f"""
                <div style="background:{color}12;border-left:3px solid {color};
                            border-radius:6px;padding:8px 12px;margin-bottom:6px;">
                  <div style="display:flex;justify-content:space-between;">
                    <div>
                      <span style="font-weight:700;font-size:14px;">{sym}</span>
                      <span style="font-size:11px;background:{color};color:#fff;
                                   border-radius:3px;padding:1px 6px;margin-left:6px;">{txn}</span>
                    </div>
                    <span style="font-size:12px;color:#6c757d;">{dt_str}</span>
                  </div>
                  <div style="font-size:12px;margin-top:3px;">
                    <b>{person}</b>
                    {f' · <span style="color:#6c757d">{sec_type}</span>' if sec_type else ""}
                    {f' · {mode}' if mode else ""}
                  </div>
                  <div style="font-size:12px;color:#495057;margin-top:2px;">
                    Qty: <b>{qty_str}</b> &nbsp;|&nbsp; Value: <b>{val_str}</b>
                    {f' &nbsp;|&nbsp; Stake: {pct_str}' if pct_str else ""}
                  </div>
                </div>"""
            st.markdown(cards_html, unsafe_allow_html=True)
 
    # ── Right: Charts ──────────────────────────────────────────────────────────
    with col_chart3:
        # Chart 1: Buy vs Sell by symbol
        st.markdown("#### Buy vs Sell by symbol")
        if not insf.empty and "transaction_type" in insf.columns:
            ins_grp = (
                insf.groupby(["symbol","transaction_type"]).size()
                .reset_index(name="count")
            )
            top_sym_ins = ins_grp.groupby("symbol")["count"].sum().nlargest(20).index
            ins_grp = ins_grp[ins_grp["symbol"].isin(top_sym_ins)]
 
            fig_ins = go.Figure()
            for txn_type in ins_grp["transaction_type"].unique():
                sub   = ins_grp[ins_grp["transaction_type"] == txn_type]
                color = _buy_sell_color(str(txn_type))
                fig_ins.add_trace(go.Bar(
                    x=sub["symbol"], y=sub["count"],
                    name=txn_type, marker_color=color,
                    hovertemplate="<b>%{x}</b><br>%{y} disclosures<extra></extra>",
                ))
            fig_ins.update_layout(
                barmode="stack", template="plotly_white", height=300,
                margin=dict(l=40,r=20,t=10,b=60), xaxis_tickangle=-45,
                legend=dict(orientation="h", y=-0.4),
            )
            st.plotly_chart(fig_ins, use_container_width=True)
        else:
            st.info("No data for chart.")
 
        # Chart 2: Cumulative qty over time for selected stock
        st.markdown("#### Cumulative insider qty — single stock")
        ins_stock_sel = st.selectbox(
            "Select stock",
            sorted(insf["symbol"].dropna().unique()) if not insf.empty else [],
            key="ins_stock_chart",
        )
        if ins_stock_sel and "qty" in insf.columns and "transaction_type" in insf.columns:
            ins_sub = insf[insf["symbol"] == ins_stock_sel]
            ins_sub = ins_sub.sort_values("date")
            ins_sub["signed_qty"] = ins_sub.apply(
                lambda r: float(r["qty"] or 0) * (
                    1 if any(k in str(r["transaction_type"]).lower()
                             for k in ["buy","acqui","purchas"])
                    else -1
                ), axis=1
            )
            ins_sub["cumulative"] = ins_sub["signed_qty"].cumsum()
 
            fig_cum = go.Figure()
            fig_cum.add_trace(go.Bar(
                x=ins_sub["date"], y=ins_sub["signed_qty"],
                name="Per-transaction qty",
                marker_color=[_buy_sell_color(str(t)) for t in ins_sub["transaction_type"]],
                hovertemplate="<b>%{customdata}</b><br>%{x|%d %b %Y}<br>%{y:,.0f} shares<extra></extra>",
                customdata=ins_sub["person"],
            ))
            fig_cum.add_trace(go.Scatter(
                x=ins_sub["date"], y=ins_sub["cumulative"],
                name="Cumulative", mode="lines",
                line=dict(color="#378ADD", width=2.5),
                yaxis="y2",
                hovertemplate="Cumulative: %{y:,.0f}<extra></extra>",
            ))
            fig_cum.update_layout(
                title=f"{ins_stock_sel} — Insider activity",
                xaxis_title="Date",
                yaxis=dict(title="Qty per trade"),
                yaxis2=dict(title="Cumulative", overlaying="y", side="right", showgrid=False),
                template="plotly_white", height=320,
                margin=dict(l=50,r=60,t=50,b=40),
                legend=dict(orientation="h", y=-0.3),
                hovermode="x unified",
            )
            st.plotly_chart(fig_cum, use_container_width=True)
 
    # ── Stake change table ─────────────────────────────────────────────────────
    if "pct_before" in insf.columns and "pct_after" in insf.columns:
        st.markdown("#### Significant stake changes")
        stake_df = insf.dropna(subset=["pct_before","pct_after"])
        if not stake_df.empty:
            stake_df["stake_change"] = stake_df["pct_after"] - stake_df["pct_before"]
            stake_df = stake_df[stake_df["stake_change"].abs() > 0.01].nlargest(20, "stake_change")
            display_stake = stake_df[
                [c for c in ["date","symbol","person","transaction_type",
                              "pct_before","pct_after","stake_change","qty"] if c in stake_df.columns]
            ]
            if "date" in display_stake.columns:
                display_stake["date"] = display_stake["date"].dt.strftime("%d %b %Y")
 
            def color_stake(val):
                try:
                    return "color: #1e7e34; font-weight:600" if float(val) > 0 else "color: #c0392b; font-weight:600"
                except Exception:
                    return ""
 
            st.dataframe(
                display_stake.style
                    .applymap(color_stake, subset=["stake_change"])
                    .format({
                        "pct_before":   "{:.3f}%",
                        "pct_after":    "{:.3f}%",
                        "stake_change": "{:+.3f}%",
                        "qty":          "{:,.0f}",
                    }, na_rep="—"),
                use_container_width=True, height=350,
            )
 
    # ── Full table ─────────────────────────────────────────────────────────────
    with st.expander("📋 Full insider trading table"):
        ins_disp = insf
        if "date" in ins_disp.columns:
            ins_disp["date"] = ins_disp["date"].dt.strftime("%d %b %Y")
        st.dataframe(ins_disp, use_container_width=True, height=400)
        st.download_button(
            "⬇ Download insider trading CSV",
            insf.to_parquet(index=False).encode(),
            "insider_trading_filtered.parquet", "text/csv",
            key="ins_dl",
        )




# ──────────────────────────────────────────────────────────────────────────────
# UTILITY FUNCTIONS FOR NEW FEATURES
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def calculate_trend(df: pd.DataFrame, symbol: str, metric: str, periods: int = 2) -> dict:
    """Calculate trend momentum for a metric over last N periods."""
    sub = df[(df["symbol"] == symbol) & (df["metric"] == metric)]
    if sub.empty or len(sub) < periods:
        return {"trend": "N/A", "momentum": 0, "direction": "neutral"}
    sub = sub.sort_values("sort_key")
    recent = sub.tail(periods)["value"].tolist()
    momentum = ((recent[-1] - recent[0]) / recent[0] * 100) if recent[0] != 0 else 0
    direction = "up" if momentum > 1 else ("down" if momentum < -1 else "neutral")
    trend = "↗ Uptrend" if direction == "up" else ("↘ Downtrend" if direction == "down" else "→ Stable")
    return {"trend": trend, "momentum": momentum, "direction": direction}

@st.cache_data(ttl=3600)
def calculate_peer_rank(df: pd.DataFrame, symbols: list, metric: str) -> pd.DataFrame:
    """Rank stocks by latest metric value."""
    ranks = []
    for sym in symbols:
        val = latest_fin(df, sym, metric)
        if val is not None:
            ranks.append({"symbol": sym, "value": val})
    if not ranks:
        return pd.DataFrame()
    rank_df = pd.DataFrame(ranks).sort_values("value", ascending=False).reset_index(drop=True)
    rank_df["rank"] = range(1, len(rank_df) + 1)
    rank_df["percentile"] = (rank_df["rank"] / len(rank_df) * 100).round(0).astype(int)
    return rank_df

@st.cache_data(ttl=3600)
def calculate_performance_score(df_sh: pd.DataFrame, df_fin: pd.DataFrame, symbol: str) -> float:
    """Calculate a composite performance score (0-100) based on key metrics."""
    score = 50  # baseline
    
    # Shareholding momentum
    fii_qoq = qoq_sh(df_sh, symbol, "FIIs")
    if fii_qoq and fii_qoq > 0:
        score += min(15, fii_qoq * 2)
    
    # Profitability
    np_latest = latest_fin(df_fin, symbol, "Net Profit")
    if np_latest and np_latest > 0:
        score += 10
    
    # Sales growth
    sales_qoq = qoq_fin(df_fin, symbol, "Sales")
    if sales_qoq and sales_qoq > 0:
        score += min(10, sales_qoq * 2)
    
    # YoY momentum
    sales_yoy = yoy_fin(df_fin, symbol, "Sales")
    if sales_yoy and sales_yoy > 5:
        score += 15
    
    return min(100, score)

def export_data_to_excel(data_dict: dict, filename: str) -> bytes:
    """Export multiple dataframes to Excel file."""
    try:
        from io import BytesIO
        import openpyxl
    except ImportError:
        return None
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for sheet_name, df in data_dict.items():
            if not df.empty:
                df.to_excel(writer, sheet_name=sheet_name, index=False)
    output.seek(0)
    return output.getvalue()


# ──────────────────────────────────────────────────────────────────────────────
# ENHANCED TAB 9 — DATA EXPORT & MANAGEMENT
# ──────────────────────────────────────────────────────────────────────────────

with st.expander("💾 Data Export & Management", expanded=False):
    st.subheader("Export filtered data")
    
    export_cols = st.columns(3)
    with export_cols[0]:
        export_sh = st.checkbox("Include shareholding", value=True)
    with export_cols[1]:
        export_fin = st.checkbox("Include financials", value=True)
    with export_cols[2]:
        export_fmt = st.selectbox("Format", ["CSV", "Excel"])
    
    if st.button("📥 Prepare Export"):
        export_data = {}
        if export_sh and not df_sh.empty:
            export_data["Shareholding"] = df_sh[df_sh["symbol"].isin(filtered_symbols)]
        if export_fin and not df_fin.empty:
            export_data["Financials"] = df_fin[df_fin["symbol"].isin(filtered_symbols)]
        
        if export_data:
            if export_fmt == "CSV":
                for name, data in export_data.items():
                    csv_data = data.to_parquet(index=False).encode()
                    st.download_button(
                        f"⬇ {name} (CSV)",
                        csv_data,
                        f"stock_{name.lower()}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.parquet",
                        "text/csv"
                    )
            else:
                excel_data = export_data_to_excel(export_data, "stock_data")
                if excel_data:
                    st.download_button(
                        "⬇ All data (Excel)",
                        excel_data,
                        f"stock_data_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
    
    st.markdown("---")
    st.subheader("Refresh data from sources")
    
    refresh_cols = st.columns([2, 1, 1])
    with refresh_cols[0]:
        st.caption("Pull latest data from Screener.in and Google Sheets fetchers")
    with refresh_cols[1]:
        if st.button("🔄 Refresh all", use_container_width=True):
            with st.spinner("Fetching latest data..."):
                try:
                    subprocess.run(["python", "screener_fetcher.py"], timeout=120, check=False)
                    subprocess.run(["python", "google_sheets_fetcher.py"], timeout=60, check=False)
                    st.success("✅ Data refresh complete! Reload the dashboard.")
                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"❌ Refresh failed: {e}")
    with refresh_cols[2]:
        if st.button("⚡ Rerun", use_container_width=True):
            st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# TAB 9 — TREND ANALYSIS
# ──────────────────────────────────────────────────────────────────────────────

with st.expander("📊 Trend Analysis", expanded=False):
    st.subheader("Multi-metric trend overview")
    
    trend_cols = st.columns([1, 1, 1])
    
    with trend_cols[0]:
        st.caption("Select metric")
        trend_metric = st.selectbox("Metric", ["Sales", "EBITDA", "Net Profit", "EPS"], key="trend_metric")
    
    with trend_cols[1]:
        st.caption("Lookback periods")
        trend_periods = st.slider("Periods", 2, 8, 4, key="trend_periods")
    
    with trend_cols[2]:
        st.caption("Filter by trend")
        trend_filter = st.selectbox("Show", ["All", "↗ Uptrend", "↘ Downtrend", "→ Stable"], key="trend_filter")
    
    # Calculate trends for all stocks
    trends_list = []
    for sym in filtered_symbols or symbols:
        trend_info = calculate_trend(df_fin, sym, trend_metric, trend_periods)
        trends_list.append({
            "Symbol": sym,
            "Trend": trend_info["trend"],
            "Momentum %": round(trend_info["momentum"], 2),
            "Direction": trend_info["direction"]
        })
    
    trend_df = pd.DataFrame(trends_list)
    if trend_filter != "All":
        trend_df = trend_df[trend_df["Trend"].str.contains(trend_filter.split()[0])]
    
    if not trend_df.empty:
        def color_trend(val):
            if "↗" in str(val):
                return "color: #1e7e34; font-weight: bold;"
            elif "↘" in str(val):
                return "color: #c0392b; font-weight: bold;"
            return ""
        
        styled_trend = trend_df.style.applymap(color_trend, subset=["Trend"])
        st.dataframe(styled_trend, use_container_width=True, height=400)
    else:
        st.info(f"No stocks with '{trend_filter}' pattern.")


# ──────────────────────────────────────────────────────────────────────────────
# TAB 10 — PEER BENCHMARKING
# ──────────────────────────────────────────────────────────────────────────────

with st.expander("🏆 Peer Benchmarking", expanded=False):
    st.subheader("Relative performance ranking")
    
    bench_cols = st.columns([2, 1])
    with bench_cols[0]:
        bench_metric = st.selectbox("Rank by metric", ["Sales", "EBITDA", "Net Profit", "EPS"], key="bench_metric")
    with bench_cols[1]:
        bench_period = st.radio("Period", ["Latest", "YoY Change"], horizontal=True, key="bench_period")
    
    if bench_period == "Latest":
        rank_df = calculate_peer_rank(df_fin, filtered_symbols or symbols, bench_metric)
    else:
        # For YoY, we need to calculate changes
        rank_df = pd.DataFrame([
            {"symbol": sym, "value": yoy_fin(df_fin, sym, bench_metric) or 0}
            for sym in filtered_symbols or symbols
        ]).sort_values("value", ascending=False).reset_index(drop=True)
        rank_df.columns = ["symbol", "value"]
        rank_df["rank"] = range(1, len(rank_df) + 1)
        rank_df["percentile"] = (rank_df["rank"] / len(rank_df) * 100).round(0).astype(int)
        rank_df.rename(columns={"symbol": "Symbol", "value": f"{bench_metric} YoY %"}, inplace=True)
    
    if not rank_df.empty:
        rank_df.columns = ["Symbol", "Value", "Rank", "Percentile"]
        st.dataframe(rank_df, use_container_width=True, height=400)
        
        # Show top and bottom performers
        top_3 = rank_df.head(3)
        bottom_3 = rank_df.tail(3)
        
        col1, col2 = st.columns(2)
        with col1:
            st.success(f"🥇 Top performer: {top_3.iloc[0]['Symbol']} (Rank 1)")
        with col2:
            st.warning(f"📉 Needs attention: {bottom_3.iloc[-1]['Symbol']} (Rank {bottom_3.iloc[-1]['Rank']:.0f})")


# ──────────────────────────────────────────────────────────────────────────────
# TAB 11 — PERFORMANCE SCORECARD
# ──────────────────────────────────────────────────────────────────────────────

with st.expander("⭐ Performance Scorecard", expanded=False):
    st.subheader("Composite performance scores")
    
    scores = []
    for sym in filtered_symbols or symbols:
        score = calculate_performance_score(df_sh, df_fin, sym)
        scores.append({"Symbol": sym, "Score": score, "Grade": 
            "A+" if score >= 85 else ("A" if score >= 75 else ("B" if score >= 65 else ("C" if score >= 55 else "F")))})
    
    score_df = pd.DataFrame(scores).sort_values("Score", ascending=False).reset_index(drop=True)
    
    def color_score(val):
        if val >= 85:
            return "color: #1e7e34; font-weight: bold;"
        elif val >= 75:
            return "color: #378ADD; font-weight: bold;"
        elif val >= 55:
            return "color: #BA7517;"
        return "color: #c0392b;"
    
    def color_grade(val):
        if "A" in val:
            return "color: #1e7e34; font-weight: bold;"
        elif "B" in val:
            return "color: #378ADD;"
        elif "C" in val:
            return "color: #BA7517;"
        return "color: #c0392b;"
    
    styled_score = score_df.style.applymap(color_score, subset=["Score"]).applymap(color_grade, subset=["Grade"])
    st.dataframe(styled_score, use_container_width=True, height=400)
    
    st.caption("Scores based on: FII momentum (15%), Profitability (10%), Sales growth (10%), YoY performance (15%), Baseline (50%)")


# ──────────────────────────────────────────────────────────────────────────────
# TAB 12 — WATCHLIST MANAGEMENT
# ──────────────────────────────────────────────────────────────────────────────

with st.expander("📌 Watchlist Management", expanded=False):
    st.subheader("Create and manage custom watchlists")
    
    watchlist_mode = st.radio("Mode", ["View", "Add", "Remove"], horizontal=True, key="watchlist_mode")
    
    if watchlist_mode == "View":
        st.caption("Current filtered stocks")
        if filtered_symbols:
            cols = st.columns(5)
            for i, sym in enumerate(filtered_symbols):
                with cols[i % 5]:
                    st.metric(sym, "📌")
        else:
            st.info("No stocks in current filter.")
    
    elif watchlist_mode == "Add":
        new_symbols = st.multiselect(
            "Add stocks to watch",
            symbols,
            key="add_watchlist"
        )
        if st.button("➕ Add to filter", use_container_width=True):
            st.session_state.watchlist_add = new_symbols
            st.success(f"✅ Added {len(new_symbols)} stocks to watch")
    
    elif watchlist_mode == "Remove":
        if filtered_symbols:
            remove_syms = st.multiselect(
                "Remove from watch",
                filtered_symbols,
                key="remove_watchlist"
            )
            if st.button("❌ Remove from filter", use_container_width=True):
                st.session_state.watchlist_remove = remove_syms
                st.success(f"✅ Removed {len(remove_syms)} stocks from watch")
        else:
            st.info("No stocks to remove.")





