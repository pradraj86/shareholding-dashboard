from pathlib import Path
import pandas as pd
import streamlit as st
import subprocess
import numpy as np


# ─── Constants ────────────────────────────────────────────────────────────────
MASTER_CSV_SH  = Path("data/shareholding_all.parquet")
MASTER_CSV_FIN = Path("data/financials_all.parquet")
SNAPSHOT_FILE  = Path("data/snapshot_all.parquet")
PER_STOCK_SH   = Path("data/shareholding_screener")
PER_STOCK_FIN  = Path("data/financials_screener")
PER_STOCK_CA   = Path("data/corporate_actions_screener")
TV_ALERTS_CSV  = Path("data/tv_alerts.parquet")
MASTER_CSV_CF  = Path("data/cashflow_all.parquet")
INSIDER_FILE   = Path("data/insider_trades.parquet")
PER_STOCK_CF   = Path("data/cashflow_screener")
BROKERAGE_FILE = Path("data/brokerage_reports.parquet")
TECHNICAL_FILE = Path("data/technicals_all.parquet")
CORP_ACTIONS_FILE = Path("data/corporate_actions_all.parquet")


CATEGORY_COLORS = {
    "Promoters": "#5f5e5a", "FIIs": "#378ADD", "DIIs": "#1D9E75",
    "Public": "#BA7517",    "Govt": "#7F77DD",  "Others": "#D85A30",
}
METRIC_COLORS = {
    "Sales": "#378ADD", "EBITDA": "#1D9E75", "EBITDA Margin %": "#7F77DD",
    "Net Profit": "#BA7517", "EPS": "#D85A30",
}
CF_COLORS = {
    "CFO": "#1D9E75", "CFI": "#D85A30", "CFF": "#378ADD",
    "Free Cash Flow": "#7F77DD", "Net Cash Flow": "#5f5e5a", "Capex": "#BA7517",
}
METRIC_UNITS = {
    "Sales": "₹ Cr", "EBITDA": "₹ Cr", "EBITDA Margin %": "%",
    "Net Profit": "₹ Cr", "EPS": "₹",
}
CF_DISPLAY_METRICS = [
    "CFO", "CFI", "CFF", "Free Cash Flow", "True Free Cash Flow",
    "Fixed Asset Purchased", "Net Cash Flow", "CFO/OP",
]
CF_YOY_METRICS = [
    "CFO", "CFI", "CFF", "Free Cash Flow", "True Free Cash Flow",
    "Fixed Asset Purchased", "Net Cash Flow",
]

@st.cache_data(ttl=3600)
def load_technical_data():

    if not TECHNICAL_FILE.exists():
        return pd.DataFrame()

    try:

        df = pd.read_parquet(
            TECHNICAL_FILE
        )

        if "symbol" in df.columns:

            df["symbol"] = (
                df["symbol"]
                .astype(str)
                .str.upper()
                .str.strip()
            )

        return df

    except Exception as e:

        st.warning(
            f"Could not load technical data: {e}"
        )

        return pd.DataFrame()
# ─── Data Loading ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_all_data():
    return load_master_sh(), load_master_fin(), load_master_cf(), load_insider_data(), load_snapshot(),load_brokerage_data(), load_technical_data()

@st.cache_data(ttl=3600)
def load_master_sh() -> pd.DataFrame:
    if MASTER_CSV_SH.exists():
        try:
            df = pd.read_parquet(MASTER_CSV_SH)
            if not df.empty: return _clean_sh(df)
        except Exception: pass
    if PER_STOCK_SH.exists():
        frames = []
        for f in sorted(PER_STOCK_SH.glob("shareholding_*.parquet")):
            try:
                tmp = pd.read_parquet(f)
                if not tmp.empty: frames.append(tmp)
            except Exception: pass
        if frames: return _clean_sh(pd.concat(frames, ignore_index=True))
    return pd.DataFrame()

@st.cache_data(ttl=3600)
def load_master_fin() -> pd.DataFrame:
    if MASTER_CSV_FIN.exists():
        try:
            df = pd.read_parquet(MASTER_CSV_FIN)
            if not df.empty: return _clean_fin(df)
        except Exception: pass
    if PER_STOCK_FIN.exists():
        frames = []
        for f in sorted(PER_STOCK_FIN.glob("financials_*.parquet")):
            try:
                tmp = pd.read_parquet(f)
                if not tmp.empty: frames.append(tmp)
            except Exception: pass
        if frames: return _clean_fin(pd.concat(frames, ignore_index=True))
    return pd.DataFrame()

@st.cache_data(ttl=3600)
def load_master_cf() -> pd.DataFrame:
    if MASTER_CSV_CF.exists():
        try:
            df = pd.read_parquet(MASTER_CSV_CF)
            if not df.empty: return _clean_fin(df)
        except Exception: pass
    if PER_STOCK_CF.exists():
        frames = []
        for f in sorted(PER_STOCK_CF.glob("cashflow_*.parquet")):
            try:
                tmp = pd.read_parquet(f)
                if not tmp.empty: frames.append(tmp)
            except Exception: pass
        if frames: return _clean_fin(pd.concat(frames, ignore_index=True))
    return pd.DataFrame()

@st.cache_data(ttl=3600)
def load_insider_data() -> pd.DataFrame:
    if not INSIDER_FILE.exists(): return pd.DataFrame()
    try:
        df = pd.read_parquet(INSIDER_FILE)
        if df.empty: return pd.DataFrame()
        if "stock" in df.columns:
            df["stock"] = df["stock"].astype(str).str.upper().str.strip()
        for col in ["value", "quantity"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.reset_index(drop=True)
    except Exception as e:
        st.warning(f"Could not load insider data: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def load_snapshot() -> pd.DataFrame:
    if SNAPSHOT_FILE.exists():
        try:
            df = pd.read_parquet(SNAPSHOT_FILE)
            if not df.empty:
                df["symbol"] = df["symbol"].str.upper().str.strip()
                return df
        except Exception: pass
    return pd.DataFrame()

@st.cache_data(ttl=600)
def load_alerts() -> pd.DataFrame:
    if not TV_ALERTS_CSV.exists(): return pd.DataFrame()
    try:
        df = pd.read_parquet(TV_ALERTS_CSV, parse_dates=["date"])
        df["symbol"] = df["symbol"].str.upper().str.strip()
        df.sort_values("date", ascending=False, inplace=True)
        return df.reset_index(drop=True)
    except Exception: return pd.DataFrame()


def _clean_sh(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.strip().lower() for c in df.columns]
    rename = {}
    for c in df.columns:
        if "sym" in c:                              rename[c] = "symbol"
        elif "qtr" in c or "quarter" in c:          rename[c] = "quarter"
        elif "cat" in c:                            rename[c] = "category"
        elif "pct" in c or "val" in c or "%" in c:  rename[c] = "pct"
    df.rename(columns=rename, inplace=True)
    if not {"symbol","quarter","category","pct"}.issubset(df.columns):
        st.error(f"Shareholding missing columns. Found: {list(df.columns)}")
        return pd.DataFrame()
    df["pct"]      = pd.to_numeric(df["pct"], errors="coerce")
    df.dropna(subset=["pct"], inplace=True)
    df["symbol"]   = df["symbol"].astype(str).str.upper().str.strip()
    df["category"] = df["category"].astype(str).str.strip()
    df["quarter"]  = df["quarter"].astype(str).str.strip()
    df["sort_key"] = df["quarter"].apply(make_period_key)
    return df.reset_index(drop=True)

def _clean_fin(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.strip().lower() for c in df.columns]
    rename = {}
    for c in df.columns:
        if "sym" in c:                              rename[c] = "symbol"
        elif "period" in c or "quarter" in c or "qtr" in c: rename[c] = "period"
        elif "freq" in c:                           rename[c] = "freq"
        elif "metric" in c:                         rename[c] = "metric"
        elif "val" in c or "pct" in c:             rename[c] = "value"
    df.rename(columns=rename, inplace=True)
    if not {"symbol","period","metric","value"}.issubset(df.columns):
        st.error(f"Financials missing columns. Found: {list(df.columns)}")
        return pd.DataFrame()
    df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
    df["metric"] = df["metric"].astype(str).str.strip()
    df["period"] = df["period"].astype(str).str.strip()
    df["value"]  = pd.to_numeric(df["value"], errors="coerce")
    df.dropna(subset=["value"], inplace=True)
    df["sort_key"] = df["period"].apply(make_period_key)
    return df.reset_index(drop=True)

# ─── Sorting ──────────────────────────────────────────────────────────────────
QUARTER_MAP = {"Mar": 3, "Jun": 6, "Sep": 9, "Dec": 12}

def quarter_sort_key(q):
    try:
        qtr, year = str(q).split()
        return (int(year), QUARTER_MAP.get(qtr, 0))
    except: return (0, 0)

def sort_quarters(df, col="quarter"):
    df = df.copy()
    series = df[col]
    if isinstance(series, pd.DataFrame): series = series.iloc[:, 0]
    df["_sort"] = series.astype(str).apply(quarter_sort_key)
    return df.sort_values("_sort").reset_index(drop=True).drop(columns="_sort")

def sort_quarter_columns(columns):
    return sorted(columns, key=quarter_sort_key)

def sort_periods(df: pd.DataFrame) -> pd.DataFrame:
    return sort_quarters(df, col="period")

def make_period_key(q):
    month_order = {
        "jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
        "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
        "q1":3,"q2":6,"q3":9,"q4":12,
    }
    parts = str(q).lower().split()
    yr = mo = 0
    for p in parts:
        if p in month_order: mo = month_order[p]
        elif p.isdigit() and len(p) == 4: yr = int(p)
    return yr * 100 + mo

# ─── Per-symbol helpers (used by single-stock detail pages only) ──────────────
def latest_sh(df, symbol, category):
    sub = df[(df["symbol"] == symbol) & (df["category"] == category)]
    return None if sub.empty else sort_quarters(sub.copy()).iloc[-1]["pct"]

def qoq_sh(df, symbol, category):
    sub = df[(df["symbol"] == symbol) & (df["category"] == category)]
    if len(sub) < 2: return None
    sub = sort_quarters(sub.copy()).reset_index(drop=True)
    return round(sub.iloc[-1]["pct"] - sub.iloc[-2]["pct"], 2)

def latest_fin(df, symbol, metric):
    sub = df[(df["symbol"] == symbol) & (df["metric"] == metric)]
    return None if sub.empty else sort_periods(sub.copy()).iloc[-1]["value"]

def qoq_fin(df, symbol, metric):
    sub = df[(df["symbol"] == symbol) & (df["metric"] == metric)]
    if len(sub) < 2: return None
    sub = sort_periods(sub.copy()).reset_index(drop=True)
    latest, prev = sub.iloc[-1]["value"], sub.iloc[-2]["value"]
    if prev == 0: return None
    return round((latest - prev) / abs(prev) * 100, 1)

def yoy_fin(df, symbol, metric):
    sub = df[(df["symbol"] == symbol) & (df["metric"] == metric)]
    if len(sub) < 5: return None
    sub = sort_periods(sub.copy()).reset_index(drop=True)
    v_now, v_prev = sub.iloc[-1]["value"], sub.iloc[-5]["value"]
    if v_prev == 0: return None
    return round((v_now - v_prev) / abs(v_prev) * 100, 1)

def latest_cf(df, symbol, metric):
    sub = df[(df["symbol"] == symbol) & (df["metric"] == metric)]
    return None if sub.empty else sort_periods(sub.copy()).iloc[-1]["value"]

def yoy_cf(df, symbol, metric):
    sub = df[(df["symbol"] == symbol) & (df["metric"] == metric)]
    if len(sub) < 2: return None
    sub = sort_periods(sub.copy()).reset_index(drop=True)
    latest, prev = sub.iloc[-1]["value"], sub.iloc[-2]["value"]
    if metric == "Capex": latest, prev = abs(latest), abs(prev)
    if prev == 0: return None
    if metric != "Capex" and (latest < 0 or prev < 0): return None
    return round((latest - prev) / abs(prev) * 100, 1)

# ─── CFO/OP & Capex helpers ───────────────────────────────────────────────────
def calc_cfo_op(df_cf, df_fin, symbol):

    cfo = latest_cf(df_cf, symbol, "CFO")

    op = latest_cf(
        df_cf,
        symbol,
        "Profit from Operations"
    )

    

    if cfo is None or op in (None, 0):
        return None

    return round((cfo / op) * 100, 1)

def calc_capex_analysis(df_cf, symbol):
    sub = df_cf[(df_cf["symbol"] == symbol) & (df_cf["metric"] == "Fixed Asset Purchased")].copy()
    if sub.empty:
        return {"capex": None, "prev_capex": None, "capex_yoy": None, "cfo": None, "capex_ratio": None}
    sub = sub.sort_values("period")
    lc = float(sub.iloc[-1]["value"]) if len(sub) >= 1 else None
    pc = float(sub.iloc[-2]["value"]) if len(sub) >= 2 else None
    cyoy = round(((lc - pc) / abs(pc)) * 100, 2) if lc and pc else None
    cfo = latest_cf(df_cf, symbol, "CFO")
    cr  = round(abs(lc) / cfo, 2) if lc and cfo else None
    return {"capex": lc, "prev_capex": pc, "capex_yoy": cyoy, "cfo": cfo, "capex_ratio": cr}

def get_cash_quality_label(v):
    if v is None:   return "No Data"
    if v >= 1.1:    return "Excellent Cash Conversion"
    elif v >= 0.9:  return "Healthy Cash Conversion"
    elif v >= 0.7:  return "Moderate Cash Conversion"
    elif v > 0:     return "Weak Cash Conversion"
    return "Negative CFO"

def get_capex_profile(v):
    if v is None:   return "No Data"
    if v <= 0.5:    return "Asset Light"
    elif v <= 1.0:  return "Balanced Reinvestment"
    elif v <= 1.5:  return "Expansion Phase"
    return "Capex Heavy"

# ─── PURE scoring functions (no DataFrames — accept scalars) ──────────────────
def _compute_growth_score(sales_yoy, ebitda_yoy, np_yoy, eps_yoy,
                           lat_ebitda, lat_np, lat_eps):
    s = 0.0
    def _yoy_points(v, tiers_pos, tiers_neg):
        if not pd.notna(v): return 0
        for threshold, pts in tiers_pos:
            if v >= threshold: return pts
        for threshold, pts in tiers_neg:
            if v <= threshold: return pts
        return 0
    s += _yoy_points(sales_yoy,  [(25,7),(15,5),(5,3),(0,1)],  [(-30,-5),(-15,-3),(-1e9,-1)])
    s += _yoy_points(ebitda_yoy, [(25,6),(15,4),(5,2),(0,1)],  [(-30,-5),(-15,-3),(-1e9,-1)])
    s += _yoy_points(np_yoy,     [(30,7),(20,5),(10,3),(0,1)],  [(-50,-6),(-25,-4),(-1e9,-2)])
    s += _yoy_points(eps_yoy,    [(25,5),(15,3),(5,1),(0,.5)],  [(-50,-5),(-25,-3),(-1e9,-1)])
    if pd.notna(lat_ebitda) and lat_ebitda < 0: s -= 4
    if pd.notna(lat_np)     and lat_np < 0:     s -= 5
    if pd.notna(lat_eps)    and lat_eps < 0:    s -= 3
    s = round(max(-10, min(25, s)), 2)
    grade = "Excellent" if s>=16 else "Strong" if s>=10 else "Average" if s>=4 else "Weak" if s>=0 else "Poor"
    return s, grade

def _compute_cf_score(cfo, fcf, net_profit, cfo_yoy, fcf_yoy, cfo_op):
    s = 0.0

    # ── CFO/OP ratio (cash conversion quality) ── max +6 ──────────────────
    if cfo_op is not None:
        if   cfo_op >= 1.2: s += 6   # converting more cash than profit → excellent
        elif cfo_op >= 1.0: s += 4   # fully converting operating profit → good
        elif cfo_op >= 0.8: s += 2   # decent conversion
        elif cfo_op >= 0.6: s += 1   # weak but positive
        elif cfo_op <= 0:   s -= 3   # negative CFO vs operating profit

    # ── CFO absolute level ────────────────────────────────────────────────
    if pd.notna(cfo):
        s += (8 if pd.notna(cfo_yoy) and cfo_yoy > 20 else 6) if cfo > 0 else -4

    # ── Free Cash Flow ────────────────────────────────────────────────────
    if pd.notna(fcf):
        s += (5 if pd.notna(fcf_yoy) and fcf_yoy > 20 else 4) if fcf > 0 else -2

    # ── Earnings quality: CFO vs Net Profit ───────────────────────────────
    if pd.notna(cfo) and pd.notna(net_profit) and net_profit != 0:
        r = cfo / net_profit
        s += 4 if r >= 1.2 else 3 if r >= 1.0 else 1 if r >= 0.7 else -1 if r >= 0.5 else -3

    # ── CFO growth ────────────────────────────────────────────────────────
    if pd.notna(cfo_yoy):
        s += 2 if cfo_yoy > 30 else 1 if cfo_yoy > 10 else -3 if cfo_yoy < -30 else -2 if cfo_yoy < -15 else 0

    # ── FCF improvement ───────────────────────────────────────────────────
    if pd.notna(fcf_yoy):
        s += 1 if fcf_yoy > 30 else -2 if fcf_yoy < -30 else -1 if fcf_yoy < -15 else 0

    # ── Persistent cash burn penalty ──────────────────────────────────────
    if pd.notna(cfo) and pd.notna(fcf) and cfo < 0 and fcf < 0:
        s -= 1

    s = round(max(-8, min(26, s)), 2)   # new max is 26 (6+8+5+4+2+1)
    grade = "Excellent" if s >= 18 else "Strong" if s >= 12 else "Average" if s >= 5 else "Weak" if s >= 0 else "Poor"
    return s, grade

# REPLACE this function in utils.py:
def _compute_ownership_score(fii_qoq, dii_qoq, promoter_qoq, insider_net):
    s = 0.0

    if pd.notna(fii_qoq):
        if   fii_qoq >= 3:  s += 4
        elif fii_qoq > 1:   s += 2
        elif fii_qoq > 0:   s += 1
        elif fii_qoq <= -3: s -= 5
        elif fii_qoq <= -1: s -= 3
        elif fii_qoq < 0:   s -= 1
        # fii_qoq == 0 → no change

    if pd.notna(dii_qoq):
        if   dii_qoq >= 2:  s += 3
        elif dii_qoq > 0:   s += 1
        elif dii_qoq <= -2: s -= 3
        elif dii_qoq < 0:   s -= 1

    if pd.notna(promoter_qoq):
        if   promoter_qoq >= 2:  s += 5
        elif promoter_qoq >= 1:  s += 3
        elif promoter_qoq > 0:   s += 1
        elif promoter_qoq <= -3: s -= 6
        elif promoter_qoq <= -1: s -= 4
        elif promoter_qoq < 0:   s -= 2

    sig = "Neutral"
    if pd.notna(insider_net):
        if   insider_net > 100_000_000:  s += 4; sig = "Strong Insider Buying"
        elif insider_net > 20_000_000:   s += 2; sig = "Positive Insider Buying"
        elif insider_net < -100_000_000: s -= 5; sig = "Heavy Insider Selling"
        elif insider_net < -20_000_000:  s -= 3; sig = "Moderate Insider Selling"

    if pd.notna(fii_qoq) and pd.notna(dii_qoq) and fii_qoq < 0 and dii_qoq < 0:
        s -= 2

    return round(max(-10, min(10, s)), 2), sig

# REPLACE this function in utils.py:
def _composite_to_perf_grade(composite):
    # Growth(-10→25)*0.5 + CF(-10→26)*0.35 + Ownership(-10→10)*0.15
    # max = 12.5 + 9.1 + 1.5 = 23.1   min = -10
    COMP_MIN = -10
    COMP_MAX = 23
    perf = round(max(0, min(100, ((composite - COMP_MIN) / (COMP_MAX - COMP_MIN)) * 100)), 2)
    grade = "A+" if perf >= 85 else "A" if perf >= 72 else "B" if perf >= 58 else "C" if perf >= 42 else "D" if perf >= 28 else "F"
    return perf, grade

# ─── Legacy per-symbol scorer (used ONLY by single-stock detail pages) ────────
def score_growth(df_fin, symbol):
    vals = [yoy_fin(df_fin,symbol,m) for m in ["Sales","EBITDA","Net Profit","EPS"]]
    lats = [latest_fin(df_fin,symbol,m) for m in ["EBITDA","Net Profit","EPS"]]
    s, g = _compute_growth_score(*vals, *lats)
    return {"score": s, "grade": g, "details": {}}

def score_cashflow(df_cf, df_fin, symbol):
    cfo=latest_cf(df_cf,symbol,"CFO"); fcf=latest_cf(df_cf,symbol,"True Free Cash Flow")
    np_=latest_fin(df_fin,symbol,"Net Profit")
    cfo_yoy=yoy_cf(df_cf,symbol,"CFO"); fcf_yoy=yoy_cf(df_cf,symbol,"True Free Cash Flow")
    
    # You MUST calculate cfo_op here first so the function knows what it is
    cfo_op = calc_cfo_op(df_cf, df_fin, symbol) 
    
    s,g = _compute_cf_score(cfo,fcf,np_,cfo_yoy,fcf_yoy,cfo_op)
    return {"score":s,"grade":g,"details":{}}

def calculate_performance_score(df_sh, df_fin, df_cf, df_insider, symbol):
    gs, gg = _compute_growth_score(
        yoy_fin(df_fin, symbol, "Sales"), yoy_fin(df_fin, symbol, "EBITDA"),
        yoy_fin(df_fin, symbol, "Net Profit"), yoy_fin(df_fin, symbol, "EPS"),
        latest_fin(df_fin, symbol, "EBITDA"), latest_fin(df_fin, symbol, "Net Profit"),
        latest_fin(df_fin, symbol, "EPS"),
    )
    cfo     = latest_cf(df_cf, symbol, "CFO")
    fcf     = latest_cf(df_cf, symbol, "True Free Cash Flow")
    np_val  = latest_fin(df_fin, symbol, "Net Profit")
    cfo_yoy = yoy_cf(df_cf, symbol, "CFO")
    fcf_yoy = yoy_cf(df_cf, symbol, "True Free Cash Flow")
    cfo_op  = calc_cfo_op(df_cf, df_fin, symbol)   # ← add this line

    cs, cg = _compute_cf_score(cfo, fcf, np_val, cfo_yoy, fcf_yoy, cfo_op)  # ← pass cfo_op

    fq = qoq_sh(df_sh, symbol, "FIIs")
    dq = qoq_sh(df_sh, symbol, "DIIs")
    pq = qoq_sh(df_sh, symbol, "Promoters")
    inet = None
    if not df_insider.empty:
        sub  = df_insider[df_insider["stock"].astype(str).str.upper() == str(symbol).upper()]
        if not sub.empty:
            inet = (sub.loc[sub["action"] == "Acquisition", "value"].sum()
                    - sub.loc[sub["action"] == "Disposal",   "value"].sum())

    os_, sig = _compute_ownership_score(fq, dq, pq, inet)
    comp     = round(gs * .60 + cs * .35 + os_ * .5, 2)
    perf, grade = _composite_to_perf_grade(comp)

    return {
        "Growth Score": gs, "Cashflow Score": cs, "Shareholding Score": os_,
        "Ownership Score": os_, "Composite Score": comp, "Performance Score": perf,
        "Grade": grade, "FII QoQ": fq, "DII QoQ": dq, "DIIs QoQ": dq,
        "Promoters QoQ": pq, "Promoter QoQ": pq, "Insider Signal": sig,
        "Growth Grade": gg, "Cashflow Grade": cg,

    }
def extract_year(period):
    try:
        return str(period).split()[-1]
    except:
        return None

def _compute_valuation_score(pe, pb):
    """
    Score from 0 to 10 (later scaled to 0-100).
    Lower PE/PB is better, but we also penalize extremely negative.
    """
    score = 0.0
    if pd.notna(pe) and pe > 0:
        if pe <= 10:    score += 5
        elif pe <= 15:  score += 4
        elif pe <= 20:  score += 3
        elif pe <= 30:  score += 2
        elif pe <= 40:  score += 1
        else:           score += 0
    if pd.notna(pb) and pb > 0:
        if pb <= 1:     score += 5
        elif pb <= 2:   score += 4
        elif pb <= 3:   score += 3
        elif pb <= 4:   score += 2
        elif pb <= 5:   score += 1
        else:           score += 0
    return round(min(10, score), 2)        
# ─── FAST VECTORIZED build_summary ────────────────────────────────────────────
@st.cache_data(ttl=3600)
def build_summary(df_sh, df_fin, df_cf, df_insider, df_snap, df_brokerage,df_tech, syms, cats):
    """
    HIGH-PERFORMANCE ENGINE (FIXED VERSION)
    Synchronizes column names exactly with the Dashboard requirements.
    """
    if df_fin.empty and df_sh.empty:
        return pd.DataFrame()

    # Ensure sort_key columns exist
    def _ensure_sort_key(df, col):
        if df.empty or "sort_key" in df.columns: return df
        df = df.copy(); df["sort_key"] = df[col].apply(make_period_key); return df

    df_fin = _ensure_sort_key(df_fin, "period")
    df_cf  = _ensure_sort_key(df_cf,  "period")
    df_sh  = _ensure_sort_key(df_sh,  "quarter")

    # ── ONE-PASS map builders ─────────────────────────────────────────────────
    def _latest_map(df, g1, g2, val, sort="sort_key"):
        if df.empty: return {}
        idx = df.groupby([g1, g2])[sort].idxmax()
        return df.loc[idx].set_index([g1, g2])[val].to_dict()

    fin_latest = _latest_map(df_fin, "symbol", "metric", "value")
    cf_latest  = _latest_map(df_cf,  "symbol", "metric", "value")
    sh_latest  = _latest_map(df_sh,  "symbol", "category", "pct")

    # QoQ / YoY maps
    sh_qoq = {}
    for (sym, cat), grp in df_sh.groupby(["symbol","category"]):
        v = grp.sort_values("sort_key")["pct"].tolist()
        if len(v) >= 2: sh_qoq[(sym,cat)] = round(v[-1]-v[-2], 2)

    fin_qoq, fin_yoy = {}, {}
    for (sym, met), grp in df_fin.groupby(["symbol","metric"]):
        v = grp.sort_values("sort_key")["value"].tolist()
        if len(v)>=2 and v[-2]!=0:
            fin_qoq[(sym,met)] = round((v[-1]-v[-2])/abs(v[-2])*100, 1)
        if len(v)>=5 and v[-5]!=0:
            fin_yoy[(sym,met)] = round((v[-1]-v[-5])/abs(v[-5])*100, 1)

    cf_yoy = {}
    for (sym, met), grp in df_cf.groupby(["symbol","metric"]):
        v = grp.sort_values("sort_key")["value"].tolist()
        if len(v)>=2 and v[-2]!=0:
            l, p = (abs(v[-1]),abs(v[-2])) if met=="Capex" else (v[-1],v[-2])
            cf_yoy[(sym,met)] = round((l-p)/abs(p)*100, 1)

    # Insider/Brokerage/Snapshot maps
    insider_map = {}
    if not df_insider.empty and "stock" in df_insider.columns:
        buys = df_insider[df_insider["action"]=="Acquisition"].groupby("stock")["value"].sum()
        sells = df_insider[df_insider["action"]=="Disposal"].groupby("stock")["value"].sum()
        for sym in buys.index.union(sells.index):
            insider_map[sym.upper()] = float(buys.get(sym,0)) - float(sells.get(sym,0))
    
    snap_map = df_snap.set_index("symbol").to_dict("index") if not df_snap.empty else {}

    broker_map = {}
    if not df_brokerage.empty:
        broker_summary = df_brokerage.groupby("symbol").agg(
            Broker_Reports=("symbol", "count"),
            Avg_Target=("target_price", "mean"),
            Avg_Upside=("upside_pct", "mean"),
            Brokerages=("broker", "nunique"),
        ).reset_index()
        broker_summary["Avg_Target"] = broker_summary["Avg_Target"].round(2)
        broker_summary["Avg_Upside"] = broker_summary["Avg_Upside"].round(2)
        print("\nBROKER SYMBOLS")
        print(df_brokerage["symbol"].unique()[:20])

        print("\nSUMMARY SYMBOLS")
        print(list(syms)[:20])
        broker_map = broker_summary.set_index("symbol").to_dict("index")
        print("Brokerage rows:", len(df_brokerage))
        print("Brokerage symbols sample:")
        print(df_brokerage["symbol"].dropna().unique()[:20])

        print("Broker map sample:")
        for k in list(broker_map.keys())[:5]:
            print(k, broker_map[k])
    tech_map = {}

    if not df_tech.empty:

        tech_map = (
            df_tech
            .set_index("symbol")
            .to_dict("index")
        )
    # Latest period maps
    qf = df_fin[df_fin["freq"].eq("quarterly")] if "freq" in df_fin.columns else df_fin
    lq_fin_map = qf.sort_values("sort_key").groupby("symbol")["period"].last().to_dict() if not qf.empty else {}
    lq_cf_map = df_cf.sort_values("sort_key").groupby("symbol")["period"].last().to_dict() if not df_cf.empty else {}
    lq_sh_map = df_sh.sort_values("sort_key").groupby("symbol")["quarter"].last().to_dict() if not df_sh.empty else {}

    sh_syms  = set(df_sh["symbol"].dropna()) if not df_sh.empty  else set()
    fin_syms = set(df_fin["symbol"].dropna()) if not df_fin.empty else set()
    cf_syms  = set(df_cf["symbol"].dropna())  if not df_cf.empty  else set()


    corp_df = load_corporate_actions()
    corp_map = {}

    if not corp_df.empty:

        latest = (
            corp_df
            .sort_values("date")
            .groupby("symbol")
            .last()
            .reset_index()
        )

        corp_map = (
            latest
            .set_index("symbol")
            .to_dict("index")
        )
    # ── Inner loop: O(1) dict lookups ──────────────────────────────────────────
    rows = []
    for sym in syms:
        row = {"symbol": sym}
        tech = tech_map.get(sym, {})
        corp = corp_map.get(sym, {})

        row["Latest Announcement"] = (corp.get("announcement"))
        row["Last Announcement Date"] = (corp.get("date"))
        # 1. THE FIX: Key names MUST match Dashboard expectations exactly
        l_fin_q = lq_fin_map.get(sym)
        l_sh_q  = lq_sh_map.get(sym)
        l_cf_q  = lq_cf_map.get(sym)

        row["Latest Financial Quarter"]    = l_fin_q
        row["Latest Shareholding Quarter"] = l_sh_q
        row["Latest Cashflow Quarter"]     = l_cf_q

        # 2. Freshness
        row["Financial Freshness"] = "Updated" if l_fin_q == l_sh_q else ("Lagging" if l_fin_q else "No Data")
        row["Shareholding Freshness"] = "Updated" if l_sh_q == l_fin_q else ("Lagging" if l_sh_q else "No Data")
        row["Cashflow Freshness"] = "Updated" if l_cf_q == l_fin_q else ("Lagging" if l_cf_q else "No Data")

        # 3. Shareholding (with Fuzzy Match)
        for cat in cats:
            val = sh_latest.get((sym, cat))
            if val is None: val = sh_latest.get((sym, f"{cat} %"))
            row[f"{cat} %"] = val
            
            q_val = sh_qoq.get((sym, cat))
            if q_val is None: q_val = sh_qoq.get((sym, f"{cat} %"))
            row[f"{cat} QoQ"] = q_val

        # 4. Financials
        for met in ["Sales","EBITDA","Net Profit","EPS"]:
            row[met]            = fin_latest.get((sym,met))
            row[f"{met} QoQ"]   = fin_qoq.get((sym,met))
            row[f"{met} YoY %"] = fin_yoy.get((sym,met))

        # 5. Cash flow
        for met in CF_DISPLAY_METRICS:
            row[met] = cf_latest.get((sym,met))
            if met in CF_YOY_METRICS:
                row[f"{met} YoY %"] = cf_yoy.get((sym,met))

        # 6. Snapshot
        snap = snap_map.get(sym, {})
        row["LTP"]       = snap.get("ltp")
        row["MCap (Cr)"] = snap.get("market_cap_cr")
        row["Technical Score"] = tech.get(
    "technical_score"
)

        row["RSI"] = tech.get(
            "rsi14"
        )

        row["Entry Status"] = tech.get(
            "entry_status"
        )

        row["Close"] = tech.get(
            "close"
        )

        row["EMA50"] = tech.get(
            "ema50"
        )

        row["EMA200"] = tech.get(
            "ema200"
        )
        # Inside build_summary(), after `snap = snap_map.get(sym, {})`:
        pe = snap.get("pe")
        pb = snap.get("pb")
        val_score = _compute_valuation_score(pe, pb)
        row["Valuation Score"] = val_score
        # 7. Brokerage
        broker = broker_map.get(sym, {})
        row["Broker Reports"] = broker.get("Broker_Reports")
        row["Avg Target"]     = broker.get("Avg_Target")
        row["Avg Upside %"]   = broker.get("Avg_Upside")
        row["Brokerages"]     = broker.get("Brokerages")

        # 8. Flags
        row["Has Shareholding"] = sym in sh_syms
        row["Has Financials"]   = sym in fin_syms
        row["Has Cash Flow"]    = sym in cf_syms
        row["Has Snapshot"]     = bool(pd.notna(row["LTP"]) and pd.notna(row["MCap (Cr)"]))

        # 9. Validation & Red Flags
        sh_vs_fin = compare_quarters(l_sh_q, l_fin_q)
        cf_vs_fin = compare_quarters(l_cf_q, l_fin_q)
        f_flags = []
        if sh_vs_fin == 1: f_flags.append("Shareholding Ahead")
        elif sh_vs_fin == -1: f_flags.append("Shareholding Lagging")
        if cf_vs_fin == 1: f_flags.append("Cashflow Ahead")
        elif cf_vs_fin == -1: f_flags.append("Cashflow Lagging")
        row["Data Freshness"] = " | ".join(f_flags) if f_flags else "Fully Synced"

        missing = [k for k,v in [("shareholding",row["Has Shareholding"]),
                                    ("financials",row["Has Financials"]),
                                    ("cash flow",row["Has Cash Flow"]),
                                    ("snapshot",row["Has Snapshot"])] if not v]
        row["Data Quality"] = "Complete" if not missing else "Missing "+", ".join(missing)

        # 10. CFO/OP Calculation
        # 10. CFO/OP Calculation

        cfo_op = calc_cfo_op(
            df_cf,
            df_fin,
            sym
        )

        fa = cf_latest.get(
            (sym, "Fixed Asset Purchased")
        )

        cfo_v = cf_latest.get(
            (sym, "CFO")
        )

        fa_cfo = (
            round(abs(fa) / cfo_v, 2)
            if fa and cfo_v
            else None
        )

        row["CFO/OP"] = cfo_op
        row["Cash Quality"] = get_cash_quality_label(
            cfo_op / 100 if cfo_op is not None else None
        )
        # 11. Scoring
        gs, gg = _compute_growth_score(
            fin_yoy.get((sym,"Sales")),    fin_yoy.get((sym,"EBITDA")),
            fin_yoy.get((sym,"Net Profit")),fin_yoy.get((sym,"EPS")),
            fin_latest.get((sym,"EBITDA")), fin_latest.get((sym,"Net Profit")),
            fin_latest.get((sym,"EPS")),
        )
        cfo_     = cf_latest.get((sym,"CFO"))
        fcf_     = cf_latest.get((sym,"True Free Cash Flow"))
        lat_np   = fin_latest.get((sym,"Net Profit"))
        cs, cg   = _compute_cf_score(cfo_, fcf_, lat_np,
                                    cf_yoy.get((sym,"CFO")),
                                    cf_yoy.get((sym,"True Free Cash Flow")),cfo_op)
        fq = sh_qoq.get((sym,"FIIs"))
        dq = sh_qoq.get((sym,"DIIs"))
        pq = sh_qoq.get((sym,"Promoters"))
        os_, sig = _compute_ownership_score(fq, dq, pq, insider_map.get(sym))

        comp = round(gs*.50 + cs*.35 + os_*0.15, 2)
        perf, grade = _composite_to_perf_grade(comp)

        row.update({
            "Growth Score":gs,"Cashflow Score":cs,"Shareholding Score":os_,"Ownership Score":os_,
            "Composite Score":comp,"Performance Score":perf,"Grade":grade,
            "FII QoQ":fq,"DIIs QoQ":dq,"DIIs QoQ":dq,"Promoters QoQ":pq,"Promoter QoQ":pq,
            "Insider Signal":sig,"Growth Grade":gg,"Cashflow Grade":cg,
        })

        # 12. Final Red Flags
        flags = []
        if not row["Has Financials"]: flags.append("No financials")
        if not row["Has Cash Flow"]:  flags.append("No cash flow")
        sfcf = fin_yoy.get((sym,"Sales"))
        tfcf = cf_latest.get((sym,"True Free Cash Flow"))
        if pd.notna(sfcf) and sfcf>10 and pd.notna(cfo_) and cfo_<=0:      flags.append("Sales up, CFO negative")
        if pd.notna(lat_np) and lat_np>0 and pd.notna(cfo_) and cfo_/lat_np<0.7: flags.append("Weak CFO/PAT")
        if pd.notna(tfcf) and tfcf<0 and pd.notna(lat_np) and lat_np>0:    flags.append("Profit with negative FCF")
        if pd.notna(pq) and pq<0:                                            flags.append("Promoter holding down")
        if pd.notna(fq) and pd.notna(dq) and fq<0 and dq<0:                flags.append("FII and DII down")
        if lq_cf_map.get(sym) != lq_fin_map.get(sym):                     flags.append("Outdated cashflow data")
        row["Red Flags"] = " | ".join(flags)
        rows.append(row)

    return pd.DataFrame(rows)
@st.cache_data(ttl=3600)
def build_summary_cached(
    df_sh,
    df_fin,
    df_cf,
    df_insider,
    df_snap,
    df_brokerage,
    df_tech,
    selected_symbols,
    selected_cats
):
    return build_summary(
        df_sh,
        df_fin,
        df_cf,
        df_insider,
        df_snap,
        df_brokerage,
        df_tech,
        selected_symbols,
        selected_cats
    )    
# ─── Cashflow narrative ───────────────────────────────────────────────────────
def analyze_cashflow(row):
    notes = []
    cfo=row.get("CFO"); fcf=row.get("Free Cash Flow"); fa=row.get("Fixed Asset Purchased")
    netc=row.get("Net Cash Flow"); cop=row.get("CFO/OP")
    cyoy=row.get("CFO YoY %"); fyoy=row.get("Fixed Asset Purchased YoY %")
    if cop is not None:
        if   cop>=1.2: notes.append(f"Excellent cash conversion (CFO/OP={cop:.2f})")
        elif cop>=0.9: notes.append(f"Healthy cash conversion (CFO/OP={cop:.2f})")
        elif cop>=0.7: notes.append(f"Moderate cash conversion (CFO/OP={cop:.2f})")
        elif cop>0:    notes.append(f"Weak cash conversion (CFO/OP={cop:.2f})")
        else:          notes.append(f"Negative CFO vs operating profit (CFO/OP={cop:.2f})")
    elif cfo is not None:
        notes.append("Strong operating cash" if cfo>0 else "Negative operating cash flow")
    if fa and cfo and cfo>0:
        r=abs(fa)/cfo
        if   r<=0.5: notes.append(f"Asset-light model (FA/CFO={r:.2f})")
        elif r<=1.0: notes.append(f"Balanced reinvestment (FA/CFO={r:.2f})")
        elif r<=1.5: notes.append(f"Expansion phase capex (FA/CFO={r:.2f})")
        else:        notes.append(f"Capex-heavy reinvestment (FA/CFO={r:.2f})")
    if cyoy is not None:
        if cyoy>20: notes.append("CFO growing strongly YoY")
        elif cyoy<-20: notes.append("CFO deteriorating YoY")
    if fyoy is not None:
        if fyoy>30: notes.append("Fixed asset investment accelerating")
        elif fyoy<-30: notes.append("Fixed asset investment declining")
    if fcf is not None: notes.append("Positive FCF" if fcf>0 else "Negative FCF")
    if netc is not None: notes.append("Net cash increasing" if netc>0 else "Net cash declining")
    return " | ".join(notes) if notes else "No cash flow data"

# ─── Misc helpers ─────────────────────────────────────────────────────────────
BUY_COLOR="#1D9E75"; SELL_COLOR="#c0392b"; NEUT_COLOR="#6c757d"

def _buy_sell_color(val):
    if not val: return NEUT_COLOR
    v=str(val).lower()
    if "buy" in v or "purchas" in v or "acqui" in v: return BUY_COLOR
    if "sell" in v or "dis" in v: return SELL_COLOR
    return NEUT_COLOR

def _deals_fetch_button(label="🔄 Fetch latest deals"):
    if st.button(label, use_container_width=True):
        with st.spinner("Fetching…"):
            try:
                r=subprocess.run(["python","deals_fetcher.py"],capture_output=True,text=True,timeout=300)
                if r.returncode==0: st.success("Updated!"); st.cache_data.clear(); st.rerun()
                else: st.error(f"Error:\n{r.stderr[-600:]}")
            except FileNotFoundError: st.error("deals_fetcher.py not found.")
            except subprocess.TimeoutExpired: st.error("Timed out.")

def latest_shareholding_change(df_sh, symbol, category):
    df_sh["category"] = (
    df_sh["category"]
    .astype(str)
    .str.strip()
    .str.replace("+", "", regex=False)
    .str.strip()
    .replace({
        "Fiis": "FIIs",
        "Diis": "DIIs",
        "Promoters": "Promoters",
        "Public": "Public",
        "Others": "Others",
    })
)
    sub=df_sh[(df_sh["symbol"]==symbol)&(df_sh["category"]==category)].copy()
    if len(sub)<2: return np.nan
    sub=sort_quarters(sub)
    return round(sub.iloc[-1]["pct"]-sub.iloc[-2]["pct"],2)

def color_growth_score(val):
    if pd.isna(val): return ""
    if val>=20: return "background-color:#1e7e34;color:white;"
    elif val>=15: return "background-color:#28a745;color:white;"
    elif val>=10: return "background-color:#ffc107;color:black;"
    return "background-color:#dc3545;color:white;"

@st.cache_data(ttl=3600)
def calculate_trend(df, symbol, metric, periods):
    try:
        if "sort_key" not in df.columns:
            df=df.copy(); col="period" if "period" in df.columns else "quarter"
            df["sort_key"]=df[col].apply(make_period_key)
        sub=df[(df["symbol"]==symbol)&(df["metric"]==metric)].copy()
        if sub.empty: return None
        sub["value"]=pd.to_numeric(sub["value"],errors="coerce")
        sub=sub.dropna(subset=["value"]).sort_values("sort_key")
        vals=sub["value"].tail(periods).tolist()
        if len(vals)<2: return None
        first,last=float(vals[0]),float(vals[-1])
        if abs(first)<1e-9: return None
        g=((last-first)/abs(first))*100
        t="Strong Uptrend" if g>=20 else "Uptrend" if g>=5 else "Strong Downtrend" if g<=-20 else "Downtrend" if g<=-5 else "Sideways"
        return {"growth_pct":round(g,2),"trend":t,"latest":round(last,2),
                "momentum":round(max(0,min(100,50+g)),1),"periods_used":len(vals)}
    except Exception as e:
        return {"growth_pct":None,"trend":"Error","latest":None,"momentum":None,"periods_used":0,"error":str(e)}

@st.cache_data(ttl=3600)
def calculate_peer_rank(df, symbols, metric):
    ranks=[{"symbol":s,"value":float(latest_fin(df,s,metric))}
           for s in symbols if pd.notna(latest_fin(df,s,metric))]
    if not ranks: return pd.DataFrame(columns=["symbol","value","rank","percentile"])
    rdf=pd.DataFrame(ranks).sort_values("value",ascending=False).reset_index(drop=True)
    rdf["rank"]=range(1,len(rdf)+1)
    rdf["percentile"]=((1-(rdf["rank"]-1)/len(rdf))*100).round(0).astype(int)
    return rdf

@st.cache_data(ttl=3600)
def get_latest_metrics(df_sh, df_fin, df_cf, symbols, categories):
    """Kept for backward compatibility — not used by build_summary anymore."""
    return {}, {}, {}

# ─── Latest Available Period Helpers ─────────────────────────────────────────

def latest_fin_period(df_fin, symbol):
    sub = df_fin[df_fin["symbol"] == symbol]
    if sub.empty:
        return None
    sub = sort_periods(sub)
    return str(sub.iloc[-1]["period"])


def latest_cf_period(df_cf, symbol):
    sub = df_cf[df_cf["symbol"] == symbol]
    if sub.empty:
        return None
    sub = sort_periods(sub)
    return str(sub.iloc[-1]["period"])


def latest_sh_period(df_sh, symbol):
    sub = df_sh[df_sh["symbol"] == symbol]
    if sub.empty:
        return None
    sub = sort_quarters(sub)
    return str(sub.iloc[-1]["quarter"])

def compare_quarters(q1, q2):

    if pd.isna(q1) or pd.isna(q2):
        return None

    try:

        m1, y1 = str(q1).split()
        m2, y2 = str(q2).split()

        t1 = (int(y1), QUARTER_MAP.get(m1, 0))
        t2 = (int(y2), QUARTER_MAP.get(m2, 0))

        if t1 > t2:
            return 1

        elif t1 < t2:
            return -1

        return 0

    except:
        return None
    
@st.cache_data(ttl=3600)
def load_brokerage_data():

    if not BROKERAGE_FILE.exists():
        return pd.DataFrame()

    try:

        df = pd.read_parquet(BROKERAGE_FILE)

        if df.empty:
            return pd.DataFrame()

        # ── Normalize columns ─────────────────────────────

        df.columns = (
            df.columns.astype(str)
            .str.strip()
            .str.lower()
            .str.replace(
                r"[^a-z0-9]+",
                "_",
                regex=True
            )
            .str.strip("_")
        )


        # ── Flexible column mapping ─────────────────────────

        rename_map = {}

        for c in df.columns:

            lc = c.lower()

            if "stock" in lc or "symbol" in lc:
                rename_map[c] = "symbol"

            elif (
                "broker" in lc
                or "brokerage" in lc
                or "research" in lc
                or "house" in lc
                or "firm" in lc
                or "author" in lc
            ):
                rename_map[c] = "broker"

            elif (
                "rating" in lc
                or "call" in lc
                or "type" in lc
            ):
                rename_map[c] = "rating"

            elif "target" in lc:
                rename_map[c] = "target_price"

            elif (
                "ltp" in lc
                or "cmp" in lc
                or "price" in lc
            ):
                rename_map[c] = "cmp"

            elif "upside" in lc:
                rename_map[c] = "upside_pct"

            elif "date" in lc:
                rename_map[c] = "date"

# IMPORTANT → OUTSIDE LOOP
        df.rename(columns=rename_map, inplace=True)
                # ── Cleanup ──────────────────────────────────────
        # Remove duplicate columns
        df = df.loc[:, ~df.columns.duplicated()]
        if "symbol" in df.columns:
            df["symbol"] = (
                df["symbol"]
                .astype(str)
                .str.upper()
                .str.strip()
            )

        if "broker" in df.columns:
            df["broker"] = (
                df["broker"]
                .astype(str)
                .str.strip()
            )

        if "rating" in df.columns:
            df["rating"] = (
                df["rating"]
                .astype(str)
                .str.upper()
                .str.strip()
            )

        if "date" in df.columns:
            df["date"] = pd.to_datetime(
                df["date"],
                errors="coerce"
            )

        numeric_cols = [
            "target_price",
            "cmp",
            "upside_pct",
        ]

        for col in numeric_cols:

            if col in df.columns:

                df[col] = (
                    df[col]
                    .astype(str)
                    .str.replace(",", "", regex=False)
                    .str.replace("%", "", regex=False)
                )

                df[col] = pd.to_numeric(
                    df[col],
                    errors="coerce"
                )

        return df.reset_index(drop=True)

    except Exception as e:

        st.error(
            f"Error loading brokerage data: {e}"
        )

        return pd.DataFrame()


@st.cache_data(ttl=3600)
def load_corporate_actions():

    if not CORP_ACTIONS_FILE.exists():
        return pd.DataFrame()

    try:

        df = pd.read_parquet(
            CORP_ACTIONS_FILE
        )

        df["symbol"] = (
            df["symbol"]
            .astype(str)
            .str.upper()
            .str.strip()
        )

        return df

    except Exception:
        return pd.DataFrame()