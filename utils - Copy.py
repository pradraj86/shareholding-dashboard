from pathlib import Path
import pandas as pd
import streamlit as st
import subprocess
import numpy as np

# ─── Constants ────────────────────────────────────────────────────────────────

MASTER_CSV_SH  = Path("data/shareholding_all.parquet")
MASTER_CSV_FIN = Path("data/financials_all.parquet")
SNAPSHOT_FILE   = Path("data/snapshot_all.parquet")
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

CF_DISPLAY_METRICS = [
    "CFO",
    "CFI",
    "CFF",
    "Free Cash Flow",
    "True Free Cash Flow",
    "Capex",
    "Net Cash Flow",
    "CFO/OP",
]

CF_YOY_METRICS = [
    "CFO",
    "CFI",
    "CFF",
    "Free Cash Flow",
    "True Free Cash Flow",
    "Capex",
    "Net Cash Flow",
]
@st.cache_data(ttl=60)
def load_all_data():

    df_sh   = load_master_sh()
    df_fin  = load_master_fin()
    df_cf   = load_master_cf()
    df_snap = load_snapshot()
    
    return df_sh, df_fin, df_cf, df_snap
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
    
    df["pct"]      = pd.to_numeric(df["pct"], errors="coerce")
    df.dropna(subset=["pct"], inplace=True)
    df["symbol"]   = df["symbol"].str.upper().str.strip()
    df["category"] = df["category"].str.strip()
   
    df["symbol"] = (
    df["symbol"]
    .astype(str)
    .str.upper()
    .str.strip()
)

    df["category"] = (
        df["category"]
        .astype(str)
        .str.strip()
    )

    df["quarter"] = (
        df["quarter"]
        .astype(str)
        .str.strip()
    )
    df["sort_key"] = (df["quarter"].astype(str).apply(make_period_key))
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
    
    df["symbol"] = (
    df["symbol"]
    .astype(str)
    .str.upper()
    .str.strip()
)

    df["metric"] = (
        df["metric"]
        .astype(str)
        .str.strip()
    )

    df["period"] = (
        df["period"]
        .astype(str)
        .str.strip()
    )
    df["value"]  = pd.to_numeric(df["value"], errors="coerce")
    df.dropna(subset=["value"], inplace=True)
    df["symbol"] = df["symbol"].str.upper().str.strip()
    df["metric"] = df["metric"].str.strip()
    df["sort_key"] = df["period"].apply(make_period_key)
    return df.reset_index(drop=True)


# ─── Sorting utilities ────────────────────────────────────────────────────────
QUARTER_MAP = {
    "Mar": 3,
    "Jun": 6,
    "Sep": 9,
    "Dec": 12,
}


def quarter_sort_key(q):

    try:

        qtr, year = str(q).split()

        return (
            int(year),
            QUARTER_MAP.get(qtr, 0)
        )

    except:

        return (0, 0)


def sort_quarters(df, col="quarter"):

    df = df.copy()

    series = df[col]

    if isinstance(series, pd.DataFrame):
        series = series.iloc[:, 0]

    df["_sort"] = series.astype(str).apply(quarter_sort_key)

    df = (
    df
    .sort_values("_sort")
    .reset_index(drop=True)
)

    return df.drop(columns="_sort")


def sort_quarter_columns(columns):

    return sorted(
        columns,
        key=quarter_sort_key
    )

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
    sub = (sort_quarters(sub.copy()).reset_index(drop=True))
    return round(sub.iloc[-1]["pct"] - sub.iloc[-2]["pct"], 2)


def latest_fin(df: pd.DataFrame, symbol: str, metric: str) -> float | None:
    sub = df[(df["symbol"] == symbol) & (df["metric"] == metric)]
    if sub.empty:
        return None
    return sort_periods(sub.copy()).iloc[-1]["value"]


def qoq_fin(
    df: pd.DataFrame,
    symbol: str,
    metric: str
) -> float | None:

    sub = df[
        (df["symbol"] == symbol)
        & (df["metric"] == metric)
    ]

    if len(sub) < 2:
        return None

    sub = (
        sort_periods(sub.copy())
        .reset_index(drop=True)
    )

    latest = sub.iloc[-1]["value"]

    prev = sub.iloc[-2]["value"]

    # Avoid divide-by-zero
    if prev == 0:
        return None

    growth = (
        (latest - prev)
        / abs(prev)
    ) * 100

    return round(growth, 1)


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


def yoy_cf(
    df: pd.DataFrame,
    symbol: str,
    metric: str
) -> float | None:

    sub = df[
        (df["symbol"] == symbol)
        & (df["metric"] == metric)
    ]

    if len(sub) < 2:
        return None

    sub = (
        sort_periods(sub.copy())
        .reset_index(drop=True)
    )

    latest = sub.iloc[-1]["value"]

    prev = sub.iloc[-2]["value"]

    # Special handling for Capex
    if metric == "Capex":

        latest = abs(latest)

        prev = abs(prev)

    # avoid divide-by-zero
    if prev == 0:
        return None

    # avoid misleading negative-base math
    if (
        metric != "Capex"
        and (latest < 0 or prev < 0)
    ):
        return None

    growth = (
        (latest - prev)
        / abs(prev)
    ) * 100

    return round(growth, 1)

# ─────────────────────────────────────────────────────────────
# CFO / OPERATING PROFIT
# ─────────────────────────────────────────────────────────────

def calc_cfo_op(df_cf, df_fin, symbol):
    """
    CFO / Operating Profit
    Measures cash conversion quality.
    """

    cfo = latest_cf(
        df_cf,
        symbol,
        "Cash from Operating Activity"
    )

    op = latest_fin(
        df_fin,
        symbol,
        "Operating Profit"
    )

    if cfo is None:
        return None

    if op in [None, 0]:
        return None

    return round(cfo / op, 2)

# ─────────────────────────────────────────────────────────────
# CAPEX / CFO
# ─────────────────────────────────────────────────────────────

def calc_capex_ratio(df_cf, symbol):
    """
    Fixed Asset Purchased / CFO
    Measures reinvestment intensity.
    """

    capex = latest_cf(
        df_cf,
        symbol,
        "Fixed assets purchased"
    )

    cfo = latest_cf(
        df_cf,
        symbol,
        "Cash from Operating Activity"
    )

    if capex is None:
        return None

    if cfo in [None, 0]:
        return None

    return round(abs(capex) / cfo, 2)

# ─────────────────────────────────────────────────────────────
# CASH QUALITY LABEL
# ─────────────────────────────────────────────────────────────

def get_cash_quality_label(cfo_op):

    if cfo_op is None:
        return "No Data"

    if cfo_op >= 1.1:
        return "Excellent Cash Conversion"

    elif cfo_op >= 0.9:
        return "Healthy Cash Conversion"

    elif cfo_op >= 0.7:
        return "Moderate Cash Conversion"

    elif cfo_op > 0:
        return "Weak Cash Conversion"

    return "Negative CFO"

# ─────────────────────────────────────────────────────────────
# CAPEX PROFILE LABEL
# ─────────────────────────────────────────────────────────────

def get_capex_profile(capex_ratio):

    if capex_ratio is None:
        return "No Data"

    if capex_ratio <= 0.5:
        return "Asset Light"

    elif capex_ratio <= 1.0:
        return "Balanced Reinvestment"

    elif capex_ratio <= 1.5:
        return "Expansion Phase"

    return "Capex Heavy"
# ─────────────────────────────────────────────────────────────
# CASH FLOW SCORE
# ─────────────────────────────────────────────────────────────

def score_cashflow(df_cf, df_fin, symbol):
    """
    Total score = 25

    Components:
    - CFO/OP score = 15
    - Capex/CFO score = 10
    """

    score = 0

    cfo_op = calc_cfo_op(df_cf, df_fin, symbol)

    capex_ratio = calc_capex_ratio(df_cf, symbol)

# ── CFO / OP SCORE ─────────────────────

    if cfo_op is not None:

        if cfo_op >= 1.2:
            score += 15

        elif cfo_op >= 1.0:
            score += 13

        elif cfo_op >= 0.8:
            score += 10

        elif cfo_op >= 0.6:
            score += 6

        elif cfo_op > 0:
            score += 3
 # ── CAPEX SCORE ────────────────────────

    if capex_ratio is not None:

        if capex_ratio <= 0.5:
            score += 10

        elif capex_ratio <= 1.0:
            score += 8

        elif capex_ratio <= 1.5:
            score += 5

        elif capex_ratio <= 2.0:
            score += 2

    return {
        "cashflow_score": score,
        "cfo_op": cfo_op,
        "capex_ratio": capex_ratio,
        "cash_quality": get_cash_quality_label(cfo_op),
        "capex_profile": get_capex_profile(capex_ratio),
    }
def make_period_key(q):

    month_order = {
        "jan":1,"feb":2,"mar":3,"apr":4,
        "may":5,"jun":6,"jul":7,"aug":8,
        "sep":9,"oct":10,"nov":11,"dec":12,
        "q1":3,"q2":6,"q3":9,"q4":12,
    }

    parts = str(q).lower().split()
    yr = 0
    mo = 0

    for p in parts:

        if p in month_order:
            mo = month_order[p]

        elif p.isdigit() and len(p) == 4:
            yr = int(p)

    return yr * 100 + mo
# ─── Build summary table ──────────────────────────────────────────────────────



@st.cache_data(ttl=3600)
def build_summary(df_sh, df_fin, df_cf, df_snap, syms, cats):
    

    if "sort_key" not in df_fin.columns:
        df_fin = df_fin.copy()
        df_fin["sort_key"] = df_fin["period"].apply(make_period_key)

    if "sort_key" not in df_cf.columns:
        df_cf = df_cf.copy()
        df_cf["sort_key"] = df_cf["period"].apply(make_period_key)

    if "sort_key" not in df_sh.columns:
        df_sh = df_sh.copy()
        df_sh["sort_key"] = df_sh["quarter"].apply(make_period_key)
    
    fin_latest_map = (
    df_fin.loc[
        df_fin.groupby(
            ["symbol", "metric"]
        )["sort_key"].idxmax()
    ]
    .set_index(["symbol", "metric"])["value"]
    .to_dict()
)

    sh_latest_map = (
    df_sh.loc[
        df_sh.groupby(
            ["symbol", "category"]
        )["sort_key"].idxmax()
    ]
    .set_index(["symbol", "category"])["pct"]
    .to_dict()
)

    
    cf_latest_map = (
    df_cf.loc[
        df_cf.groupby(
            ["symbol", "metric"]
        )["sort_key"].idxmax()
    ]
    .set_index(["symbol", "metric"])["value"]
    .to_dict()
)
    
      
    
    
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

                    
        grp = grp.sort_values("sort_key")
        vals = grp["value"].tolist()
        # QoQ
        if len(vals) >= 2 and vals[-2] != 0:
            fin_qoq_map[(sym, met)] = round(
        (
            (vals[-1] - vals[-2])
            / abs(vals[-2])
        ) * 100,
        1
    )

        # YoY
        if len(vals) >= 5 and vals[-5] != 0:

            fin_yoy_map[(sym, met)] = round(
                (vals[-1] - vals[-5]) / abs(vals[-5]) * 100,
                1
            )

    cf_yoy_map = {}

    for (sym, met), grp in df_cf.groupby(["symbol", "metric"]):

        grp = grp.sort_values("sort_key")

        vals = grp["value"].tolist()

        # Annual cashflow → compare latest year vs previous year
        if len(vals) >= 2 and vals[-2] != 0:

            latest = vals[-1]
            prev = vals[-2]

            # Normalize Capex
            if met == "Capex":
                latest = abs(latest)
                prev = abs(prev)

            cf_yoy_map[(sym, met)] = round(
                ((latest - prev) / abs(prev)) * 100,
                1
            )

    sh_symbols = set(df_sh["symbol"].dropna().astype(str)) if "symbol" in df_sh.columns else set()
    fin_symbols = set(df_fin["symbol"].dropna().astype(str)) if "symbol" in df_fin.columns else set()
    cf_symbols = set(df_cf["symbol"].dropna().astype(str)) if "symbol" in df_cf.columns else set()

    if not df_fin.empty and "freq" in df_fin.columns:
        annual_fin = df_fin[df_fin["freq"].eq("annual")]
        quarterly_fin = df_fin[df_fin["freq"].eq("quarterly")]
    else:
        annual_fin = pd.DataFrame(columns=df_fin.columns)
        quarterly_fin = df_fin

    annual_fin_latest_map = (
        annual_fin.loc[
            annual_fin.groupby(["symbol", "metric"])["sort_key"].idxmax()
        ]
        .set_index(["symbol", "metric"])["value"]
        .to_dict()
        if not annual_fin.empty
        else {}
    )

    latest_quarter_map = (
        quarterly_fin.sort_values("sort_key")
        .groupby("symbol")["period"]
        .last()
        .to_dict()
        if not quarterly_fin.empty
        else {}
    )

    latest_cashflow_period_map = (
        df_cf.sort_values("sort_key")
        .groupby("symbol")["period"]
        .last()
        .to_dict()
        if not df_cf.empty
        else {}
    )
       
    snap_map = (
    df_snap.set_index("symbol").to_dict("index")
    if not df_snap.empty
    else {}
    )
    rows = []
    for sym in syms:
        row = {"symbol": sym}
        perf = calculate_performance_score(
        df_sh, df_fin, df_cf, sym,)

        row.update(perf)
        for cat in cats:
           
            row[f"{cat} %"] = sh_latest_map.get((sym, cat))
            
            row[f"{cat} QoQ"] = sh_qoq_map.get((sym, cat))
        for met in ["Sales", "EBITDA", "Net Profit", "EPS"]:
            
            row[met] = fin_latest_map.get((sym, met))
            
            row[f"{met} QoQ"] = fin_qoq_map.get((sym, met))
           
            row[f"{met} YoY %"] = fin_yoy_map.get((sym, met))
        
        # Cash Flow
        
        for met in CF_DISPLAY_METRICS:

            row[f"{met}"] = cf_latest_map.get((sym, met))

            if met in CF_YOY_METRICS:

                row[f"{met} YoY %"] = cf_yoy_map.get((sym, met))

        # Snapshot
        if not df_snap.empty:
            
            snap = snap_map.get(sym, {})

            row["LTP"] = snap.get("ltp")
            row["MCap (Cr)"] = snap.get("market_cap_cr")
            
        else:
            row["LTP"] = None
            row["MCap (Cr)"] = None

        row["Has Shareholding"] = sym in sh_symbols
        row["Has Financials"] = sym in fin_symbols
        row["Has Cash Flow"] = sym in cf_symbols
        row["Has Snapshot"] = bool(
            pd.notna(row.get("LTP")) and pd.notna(row.get("MCap (Cr)"))
        )
        row["Latest Quarter"] = latest_quarter_map.get(sym)
        row["Latest Cashflow Year"] = latest_cashflow_period_map.get(sym)

        missing = []
        if not row["Has Shareholding"]:
            missing.append("shareholding")
        if not row["Has Financials"]:
            missing.append("financials")
        if not row["Has Cash Flow"]:
            missing.append("cash flow")
        if not row["Has Snapshot"]:
            missing.append("snapshot")
        row["Data Quality"] = "Complete" if not missing else "Missing " + ", ".join(missing)

        mcap = row.get("MCap (Cr)")
        annual_sales = annual_fin_latest_map.get((sym, "Sales"))
        annual_profit = annual_fin_latest_map.get((sym, "Net Profit"))
        cfo = row.get("CFO")
        true_fcf = row.get("True Free Cash Flow")

        row["P/S"] = (
            round(mcap / annual_sales, 2)
            if pd.notna(mcap) and pd.notna(annual_sales) and annual_sales > 0
            else None
        )
        row["P/E"] = (
            round(mcap / annual_profit, 2)
            if pd.notna(mcap) and pd.notna(annual_profit) and annual_profit > 0
            else None
        )
        row["CFO Yield %"] = (
            round((cfo / mcap) * 100, 2)
            if pd.notna(mcap) and mcap > 0 and pd.notna(cfo)
            else None
        )
        row["FCF Yield %"] = (
            round((true_fcf / mcap) * 100, 2)
            if pd.notna(mcap) and mcap > 0 and pd.notna(true_fcf)
            else None
        )

        flags = []
        if not row["Has Financials"]:
            flags.append("No financials")
        if not row["Has Cash Flow"]:
            flags.append("No cash flow")
        if pd.notna(row.get("Sales YoY %")) and row["Sales YoY %"] > 10 and pd.notna(cfo) and cfo <= 0:
            flags.append("Sales up, CFO negative")
        if pd.notna(row.get("Net Profit")) and row["Net Profit"] > 0 and pd.notna(cfo) and cfo / row["Net Profit"] < 0.7:
            flags.append("Weak CFO/PAT")
        if pd.notna(true_fcf) and true_fcf < 0 and pd.notna(row.get("Net Profit")) and row["Net Profit"] > 0:
            flags.append("Profit with negative FCF")
        if pd.notna(row.get("Promoters QoQ")) and row["Promoters QoQ"] < 0:
            flags.append("Promoter holding down")
        if (
            pd.notna(row.get("FIIs QoQ"))
            and pd.notna(row.get("DIIs QoQ"))
            and row["FIIs QoQ"] < 0
            and row["DIIs QoQ"] < 0
        ):
            flags.append("FII and DII down")
        row["Red Flags"] = " | ".join(flags)

        rows.append(row)
    return pd.DataFrame(rows)


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

def score_growth(
    df_fin: pd.DataFrame,
    df_sh: pd.DataFrame,
    symbol: str
) -> dict:
    """
    Growth scoring model (0–25).

    Factors:
    - Sales YoY
    - EBITDA YoY
    - Net Profit YoY
    - EPS YoY
    """

    score = 0.0

    details = {}

    # ─────────────────────────────────────────────
    # Sales Growth
    # ─────────────────────────────────────────────

    sales_yoy = yoy_fin(df_fin, symbol, "Sales")

    details["Sales YoY"] = sales_yoy

    if pd.notna(sales_yoy):

        if sales_yoy >= 25:
            score += 7

        elif sales_yoy >= 15:
            score += 5

        elif sales_yoy >= 5:
            score += 3

    # ─────────────────────────────────────────────
    # EBITDA Growth
    # ─────────────────────────────────────────────

    ebitda_yoy = yoy_fin(df_fin, symbol, "EBITDA")

    details["EBITDA YoY"] = ebitda_yoy

    if pd.notna(ebitda_yoy):

        if ebitda_yoy >= 25:
            score += 6

        elif ebitda_yoy >= 15:
            score += 4

        elif ebitda_yoy >= 5:
            score += 2

    # ─────────────────────────────────────────────
    # Net Profit Growth
    # ─────────────────────────────────────────────

    np_yoy = yoy_fin(df_fin, symbol, "Net Profit")

    details["Net Profit YoY"] = np_yoy

    if pd.notna(np_yoy):

        if np_yoy >= 30:
            score += 7

        elif np_yoy >= 20:
            score += 5

        elif np_yoy >= 10:
            score += 3

    # ─────────────────────────────────────────────
    # EPS Growth
    # ─────────────────────────────────────────────

    eps_yoy = yoy_fin(df_fin, symbol, "EPS")

    details["EPS YoY"] = eps_yoy

    if pd.notna(eps_yoy):

        if eps_yoy >= 25:
            score += 5

        elif eps_yoy >= 15:
            score += 3

        elif eps_yoy >= 5:
            score += 1

        # ─────────────────────────────────────────────
    # FII / DII Accumulation
    # ─────────────────────────────────────────────

    fii_change = latest_shareholding_change(df_sh, symbol, "FIIs")
    dii_change = latest_shareholding_change(df_sh, symbol, "DIIs")

    details["FII Change"] = fii_change
    details["DII Change"] = dii_change

    # FII scoring
    if pd.notna(fii_change):

        if fii_change >= 2:
            score += 4

        elif fii_change >= 1:
            score += 3

        elif fii_change > 0:
            score += 2

    # DII scoring
    if pd.notna(dii_change):

        if dii_change >= 2:
            score += 3

        elif dii_change >= 1:
            score += 2

        elif dii_change > 0:
            score += 1
    # ─────────────────────────────────────────────
    # Final normalization
    # ─────────────────────────────────────────────

    score = round(min(25, score), 2)

    # Grade
    if score >= 22:
        grade = "Excellent"

    elif score >= 18:
        grade = "Strong"

    elif score >= 12:
        grade = "Average"

    else:
        grade = "Weak"

    return {
        "score": score,
        "grade": grade,
        "details": details,
    }

def latest_shareholding_change(df_sh, symbol, category):

    sub = df_sh[
        (df_sh["symbol"] == symbol) &
        (df_sh["category"] == category)
    ].copy()

    if len(sub) < 2:
        return np.nan

    sub = sort_quarters(sub)

    latest = sub.iloc[-1]["pct"]
    prev = sub.iloc[-2]["pct"]

    return round(latest - prev, 2)

def color_growth_score(val):

    if pd.isna(val):
        return ""

    if val >= 20:
        return "background-color: #1e7e34; color: white;"

    elif val >= 15:
        return "background-color: #28a745; color: white;"

    elif val >= 10:
        return "background-color: #ffc107; color: black;"

    return "background-color: #dc3545; color: white;"

def score_cashflow(
    df_cf: pd.DataFrame,
    df_fin: pd.DataFrame,
    symbol: str
) -> dict:
    """
    Cashflow quality scoring model (0–20).

    Factors:
    - CFO positive
    - Free Cash Flow positive
    - CFO > Net Profit
    - CFO YoY growth
    - FCF improving
    - Negative CFO/FCF penalties
    """

    score = 0.0

    details = {}

    # ─────────────────────────────────────────────
    # Latest values
    # ─────────────────────────────────────────────

    cfo = latest_cf(df_cf, symbol, "CFO")
    fcf = latest_cf(df_cf, symbol, "True Free Cash Flow")
    np  = latest_fin(df_fin, symbol, "Net Profit")

    cfo_yoy = yoy_cf(df_cf, symbol, "CFO")
    fcf_yoy = yoy_cf(df_cf, symbol, "True Free Cash Flow")

    details["CFO"] = cfo
    details["FCF"] = fcf
    details["Net Profit"] = np
    details["CFO YoY"] = cfo_yoy
    details["FCF YoY"] = fcf_yoy

    # ─────────────────────────────────────────────
    # CFO Positive
    # ─────────────────────────────────────────────

    if pd.notna(cfo):

        if cfo > 0:
            score += 8

        else:
            score -= 5

    # ─────────────────────────────────────────────
    # Free Cash Flow Positive
    # ─────────────────────────────────────────────

    if pd.notna(fcf):

        if fcf > 0:
            score += 5

        else:
            score -= 3

    # ─────────────────────────────────────────────
    # CFO > Net Profit
    # Earnings quality check
    # ─────────────────────────────────────────────

    if (
        pd.notna(cfo)
        and pd.notna(np)
        and np > 0
    ):

        ratio = cfo / np

        details["CFO/PAT Ratio"] = round(ratio, 2)

        if ratio >= 1.2:
            score += 4

        elif ratio >= 1:
            score += 3

        elif ratio >= 0.7:
            score += 1

        else:
            score -= 2

    # ─────────────────────────────────────────────
    # CFO Growth
    # ─────────────────────────────────────────────

    if pd.notna(cfo_yoy):

        if cfo_yoy > 30:
            score += 2

        elif cfo_yoy > 10:
            score += 1

        elif cfo_yoy < -20:
            score -= 2

    # ─────────────────────────────────────────────
    # FCF Improvement
    # ─────────────────────────────────────────────

    if pd.notna(fcf_yoy):

        if fcf_yoy > 30:
            score += 1

        elif fcf_yoy < -20:
            score -= 1

    # ─────────────────────────────────────────────
    # Final normalization
    # ─────────────────────────────────────────────

    score = round(max(0, min(20, score)), 2)

    # ─────────────────────────────────────────────
    # Grade
    # ─────────────────────────────────────────────

    if score >= 16:
        grade = "Excellent"

    elif score >= 12:
        grade = "Strong"

    elif score >= 8:
        grade = "Average"

    else:
        grade = "Weak"

    return {
        "score": score,
        "grade": grade,
        "details": details,
    }



# ──────────────────────────────────────────────────────────────────────────────
# UTILITY FUNCTIONS FOR NEW FEATURES
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def calculate_trend(
    df: pd.DataFrame,
    symbol: str,
    metric: str,
    periods: int,
):

    try:

        # ─── Ensure sort_key exists ─────────────────────────

        if "sort_key" not in df.columns:

            df = df.copy()

            if "period" in df.columns:
                df["sort_key"] = df["period"].apply(make_period_key)

            elif "quarter" in df.columns:
                df["sort_key"] = df["quarter"].apply(make_period_key)

            else:
                return None

        # ─── Filter symbol + metric ────────────────────────

        sub = df[
            (df["symbol"] == symbol)
            & (df["metric"] == metric)
        ].copy()

        if sub.empty:
            return None

        # ─── Clean values ──────────────────────────────────

        sub["value"] = pd.to_numeric(
            sub["value"],
            errors="coerce"
        )

        sub = sub.dropna(subset=["value"])

        if sub.empty:
            return None

        # ─── Sort chronologically ──────────────────────────

        sub = sub.sort_values("sort_key")

        # ─── Take latest periods ───────────────────────────

        vals = (
            sub["value"]
            .tail(periods)
            .tolist()
        )

        if len(vals) < 2:
            return None

        first = float(vals[0])
        last = float(vals[-1])

        # Avoid divide-by-zero
        if abs(first) < 1e-9:
            return None

        # ─── Calculate growth ──────────────────────────────

        growth = ((last - first) / abs(first)) * 100

        # ─── Determine trend category ──────────────────────

        if growth >= 20:
            trend = "Strong Uptrend"

        elif growth >= 5:
            trend = "Uptrend"

        elif growth <= -20:
            trend = "Strong Downtrend"

        elif growth <= -5:
            trend = "Downtrend"

        else:
            trend = "Sideways"

        # ─── Momentum score (0–100) ────────────────────────

        momentum_score = max(
            0,
            min(100, 50 + growth)
        )

        return {
            "growth_pct": round(growth, 2),
            "trend": trend,
            "latest": round(last, 2),
            "momentum": round(momentum_score, 1),
            "periods_used": len(vals),
        }

    except Exception as e:

        return {
            "growth_pct": None,
            "trend": "Error",
            "latest": None,
            "momentum": None,
            "periods_used": 0,
            "error": str(e),
        }
@st.cache_data(ttl=3600)
def calculate_peer_rank(
    df: pd.DataFrame,
    symbols: list,
    metric: str
) -> pd.DataFrame:
    """Rank stocks by latest metric value."""

    ranks = []

    for sym in symbols:

        val = latest_fin(df, sym, metric)

        # Skip invalid values
        if pd.notna(val):

            try:
                val = float(val)

            except Exception:
                continue

            ranks.append({
                "symbol": sym,
                "value": val
            })

    # Empty safeguard
    if not ranks:
        return pd.DataFrame(
            columns=["symbol", "value", "rank", "percentile"]
        )

    # Build dataframe
    rank_df = pd.DataFrame(ranks)

    # Sort descending
    rank_df = (
        rank_df
        .sort_values("value", ascending=False)
        .reset_index(drop=True)
    )

    # Rank
    rank_df["rank"] = range(1, len(rank_df) + 1)

    # Percentile (higher value = better percentile)
    total = len(rank_df)

    rank_df["percentile"] = (
        (1 - (rank_df["rank"] - 1) / total) * 100
    ).round(0).astype(int)

    return rank_df


    
def calculate_performance_score(
    df_sh,
    df_fin,
    df_cf,
    symbol,
):
    """
    Institutional-style composite scoring model.
    """

    # ─────────────────────────────────────────────
    # Growth Score
    # ─────────────────────────────────────────────

    growth_info = score_growth(
    df_fin,
    df_sh,
    symbol
)

    growth_score = growth_info["score"]
	# ─────────────────────────────────────────────
    # Cashflow Score
    # ─────────────────────────────────────────────

    cf_info = score_cashflow(
        df_cf,
        df_fin,
        symbol
    )

    cf_score = cf_info["score"]
	# ─────────────────────────────────────────────
    # Shareholding Score
    # ─────────────────────────────────────────────

    fii_qoq = qoq_sh(df_sh, symbol, "FIIs")
    dii_qoq = qoq_sh(df_sh, symbol, "DIIs")
    promoter_qoq = qoq_sh(df_sh, symbol, "Promoters")

    sh_score = 0.0

    if pd.notna(fii_qoq):

        if fii_qoq > 2:
            sh_score += 5

        elif fii_qoq > 0:
            sh_score += 3
        
        elif fii_qoq < -2:
            sh_score -= 5

        elif fii_qoq < 0:
            sh_score -= 2

    if pd.notna(dii_qoq):

        if dii_qoq > 2:
            sh_score += 4

        elif dii_qoq > 0:
            sh_score += 2

        elif dii_qoq < -2:
            sh_score -= 4

        elif dii_qoq < 0:
            sh_score -= 2

    if pd.notna(promoter_qoq):

        if promoter_qoq > 1:
            sh_score += 5

        elif promoter_qoq > 0:
            sh_score += 2

        elif promoter_qoq < -2:
            sh_score -= 5   

        elif promoter_qoq < 0:
            sh_score -= 2    
    sh_score = max(0,min(10, sh_score))

    # ─────────────────────────────────────────────
    # Composite Score
    # ─────────────────────────────────────────────

    composite = round(
        (
            growth_score * 0.50
            + cf_score * 0.35
            + sh_score * 0.15
        ),
        2
    )

    # Normalize to 100
    # Max weighted composite: 25*0.50 + 20*0.35 + 10*0.15 = 21.0
    performance_score = round(
        (composite / 21) * 100,
        2
    )
	
    # ─────────────────────────────────────────────
    # Grade
    # ─────────────────────────────────────────────

    if performance_score >= 85:
        grade = "A+"

    elif performance_score >= 75:
        grade = "A"

    elif performance_score >= 65:
        grade = "B"

    elif performance_score >= 50:
        grade = "C"

    else:
        grade = "F"

    return {
        "Growth Score": growth_score,
        "Cashflow Score": cf_score,
        "Shareholding Score": sh_score,
        "Composite Score": composite,
        "Performance Score": performance_score,
        "Grade": grade,
    }
