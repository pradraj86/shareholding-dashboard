"""
screener_fetcher.py
───────────────────
Fetches quarterly shareholding pattern AND quarterly financials
(Sales, EBITDA, Net Profit, EPS) plus snapshot metrics (Market Cap, LTP)
from Screener.in for every stock in your TradingView watchlist.

TWO-PASS STRATEGY
─────────────────
Pass 1 — Shareholding + Snapshot:
    Scrapes HTML from /company/<SYMBOL>/ (same as before).

Pass 2 — Financials (Sales / EBITDA / Net Profit / EPS):
    Uses Screener's official export API:
        GET /api/company/<id>/export/?type=standalone   (or consolidated)
    This returns the EXACT same CSV the website's "Export to Excel" button
    downloads — guaranteed to match what you see on screen.

    To get the numeric company ID we call the search API once:
        GET /api/company/search/?q=<SYMBOL>&v=3&fts=1

Usage
-----
1. Set SESSION_ID below (copy sessionid cookie from browser after logging in).
2. Run:  python screener_fetcher.py
3. Data saved to:
       data/shareholding_screener/  (one CSV per stock)
       data/shareholding_all.parquet    (combined master)
       data/financials_screener/    (one CSV per stock)
       data/financials_all.parquet      (combined master)
       data/snapshot_all.parquet        (Market Cap + LTP per stock, latest)

Requirements
------------
    pip install requests pandas beautifulsoup4 lxml
"""

import html
import io
import time
import logging
import re
import os
from pathlib import Path

import requests
import pandas as pd
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import random
from datetime import datetime
import json





# ─── CONFIGURATION ────────────────────────────────────────────────────────────

SESSION_ID      = os.getenv("SCREENER_SESSION_ID", "")   # Set this in your environment
WATCHLIST_FILE  = Path("watchlist.txt")

OUT_DIR_SH      = Path("data/shareholding_screener")
MASTER_CSV_SH   = Path("data/shareholding_all.parquet")

OUT_DIR_FIN     = Path("data/financials_screener")
MASTER_CSV_FIN  = Path("data/financials_all.parquet")

OUT_DIR_CA      = Path("data/corporate_actions_screener")
MASTER_CSV_CA   = Path("data/corporate_actions_all.parquet")

OUT_DIR_CF      = Path("data/cashflow_screener")
MASTER_CSV_CF   = Path("data/cashflow_all.parquet")

SNAPSHOT_FILE    = Path("data/snapshot_all.parquet")

# "standalone" | "consolidated" | "auto"
# "auto" = try consolidated first, fall back to standalone if no data
REPORT_TYPE = "standalone"

DELAY_BETWEEN_REQUESTS = 1.5
MAX_RETRIES            = 2
FULL_REFRESH_DAY = "Sunday"
# Replace the hard Sunday gate with a staleness check
REFRESH_AFTER_DAYS = 2   # check for new quarters if file is older than this

def _needs_staleness_check(path: Path) -> bool:
    if not path.exists():
        return True
    age_days = (time.time() - os.path.getmtime(path)) / 86400
    return age_days >= REFRESH_AFTER_DAYS
# ─── LOGGING ──────────────────────────────────────────────────────────────────
today = datetime.now().strftime("%A")

force_refresh = today == FULL_REFRESH_DAY

COMPANY_ID_CACHE_FILE = Path(
    "data/company_ids.json"
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/screener_fetch.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ─── HELPERS ──────────────────────────────────────────────────────────────────

KNOWN_EXCHANGES = {"NSE", "BSE", "NIFTY"}

def parse_watchlist(filepath: Path = WATCHLIST_FILE) -> list[str]:
    """Parse TradingView watchlist TXT → clean NSE symbols."""
    if not filepath.exists():
        log.warning(f"Watchlist not found at {filepath}. Using defaults.")
        return ["RELIANCE", "INFY", "HDFCBANK", "TCS", "ICICIBANK"]

    symbols, seen = [], set()
    for line in filepath.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("###"):
            continue
        for part in line.split(","):
            part = part.strip()
            if not part or part.startswith("###"):
                continue
            if ":" in part:
                exchange, sym = part.split(":", 1)
                if exchange.upper() in KNOWN_EXCHANGES:
                    sym = sym.strip().upper()
                    if sym not in seen:
                        seen.add(sym)
                        symbols.append(sym)
            else:
                sym = re.sub(r"[^A-Z0-9&]", "", part.upper())
                if sym and sym not in seen:
                    seen.add(sym)
                    symbols.append(sym)
    log.info(f"Loaded {len(symbols)} symbols from watchlist.")
    return symbols




def make_session(session_id: str) -> requests.Session:

    s = requests.Session()

    retry_strategy = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )

    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=1,
        pool_maxsize=1,
    )

    s.mount("https://", adapter)
    s.mount("http://", adapter)

    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-IN,en;q=0.9",
        "Referer": "https://www.screener.in/",
        "Connection": "keep-alive",
    })

    s.cookies.set(
        "sessionid",
        session_id,
        domain="www.screener.in"
    )

    return s


def fetch_html(session, symbol):

    url = f"https://www.screener.in/company/{symbol}/consolidated/"

    try:

        r = session.get(url, timeout=20)

        if r.status_code == 429:

            retry_after = int(
                r.headers.get("Retry-After", 60)
            )

            log.warning(
                f"{symbol}: RATE LIMITED. Sleeping {retry_after}s"
            )

            time.sleep(retry_after)

            return None

        if r.status_code != 200:

            log.warning(
                f"{symbol}: HTTP {r.status_code}"
            )

            return None

        text = r.text

        if (
            "Request Rate Threshold Exceeded" in text
            or "Too many requests" in text
            or "Cloudflare" in text
        ):

            log.warning(
                f"{symbol}: blocked page detected"
            )

            time.sleep(60)

            return None

        return text

    except Exception as e:

        log.warning(
            f"{symbol}: HTML fetch failed → {e}"
        )

        return None

	


# ─── SHAREHOLDING PARSER (HTML scrape — unchanged, works correctly) ───────────

def parse_shareholding_page(html: str, symbol: str) -> pd.DataFrame | None:
    """
    Extract the shareholding table from a Screener.in company page.
    Returns tidy DataFrame: symbol | quarter | category | pct
    """
    soup = BeautifulSoup(html, "lxml")

    section = soup.find("section", {"id": "shareholding"})
    if not section:
        for tbl in soup.find_all("table"):
            if "Promoters" in tbl.get_text() and "FIIs" in tbl.get_text():
                section = tbl.parent
                break

    if not section:
        return None

    table = section.find("table")
    if not table:
        return None

    header_row = table.find("thead")
    if not header_row:
        rows         = table.find_all("tr")
        header_cells = [td.get_text(strip=True) for td in rows[0].find_all(["th", "td"])]
    else:
        header_cells = [td.get_text(strip=True) for td in header_row.find_all(["th", "td"])]

    quarters = header_cells[1:]
    if not quarters:
        return None

    tbody   = table.find("tbody") or table
    records = []
    for row in tbody.find_all("tr"):
        cells    = row.find_all(["td", "th"])
        if not cells:
            continue
        category = cells[0].get_text(strip=True).replace("%", "").replace("+", "").strip()
        if not category:
            continue
        values = []
        for cell in cells[1:]:
            raw = cell.get_text(strip=True).replace(",", "").replace("%", "")
            try:
                values.append(float(raw))
            except ValueError:
                values.append(None)
        for q, v in zip(quarters, values):
            records.append({"symbol": symbol, "quarter": q, "category": category, "pct": v})

    if not records:
        return None

    df   = pd.DataFrame(records)
    df   = df[df["pct"].notna()]
    keep = {"Promoters", "FIIs", "DIIs", "Public", "Govt", "Others"}
    df   = df[df["category"].apply(lambda c: any(k.lower() in c.lower() for k in keep))]
    return df if not df.empty else None


# ─── SNAPSHOT PARSER (HTML scrape — LTP + Market Cap) ────────────────────────

def parse_snapshot(html: str, symbol: str) -> dict:
    """Extract LTP and Market Cap from the #top-ratios block."""
    soup     = BeautifulSoup(html, "lxml")
    snapshot = {"symbol": symbol, "market_cap_cr": None, "ltp": None}

    LTP_LABELS  = {"current price", "price", "cmp", "last price"}
    MCAP_LABELS = {"market cap", "market capitalization"}

    for li in soup.select("#top-ratios li"):
        name_tag = li.find("span", class_="name")
        val_tag  = li.find("span", class_="number")
        if not (name_tag and val_tag):
            continue
        label = name_tag.get_text(strip=True).lower()
        raw   = val_tag.get_text(strip=True).replace(",", "").replace("₹", "").strip()
        try:
            val = float(raw)
        except ValueError:
            continue
        if any(lbl in label for lbl in LTP_LABELS)  and snapshot["ltp"]           is None:
            snapshot["ltp"]           = val
        elif any(lbl in label for lbl in MCAP_LABELS) and snapshot["market_cap_cr"] is None:
            snapshot["market_cap_cr"] = val

    # Sanity check
    if (snapshot["ltp"] is not None and snapshot["market_cap_cr"] is not None
            and snapshot["ltp"] >= snapshot["market_cap_cr"]):
        log.warning(f"{symbol}: LTP/MCap collision detected — clearing LTP")
        snapshot["ltp"] = None

    return snapshot


# ─── CORPORATE ACTIONS PARSER (HTML scrape — Dividends, Splits, Bonus, etc.) ──

def fetch_corporate_actions_api(session: requests.Session,
                                symbol: str,
                                company_id: int) -> pd.DataFrame | None:
    """
    Fetch corporate actions from Screener's JSON API.

    Screener exposes two useful endpoints:
      1. /api/company/<id>/dividends/      → dividend history
      2. /api/company/<id>/events/         → bonus, split, rights, mergers, etc.

    Both return JSON arrays. We merge them into a single tidy DataFrame:
        symbol | date | action_type | value | description
    """
    records = []

    # ── Endpoint 1: dividends ─────────────────────────────────────────────────
    div_url = f"https://www.screener.in/api/company/{company_id}/dividends/"
    try:
        r = session.get(div_url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            # Response is typically a list of dicts or {"dividends": [...]}
            items = data if isinstance(data, list) else data.get("dividends", [])
            for item in items:
                # Fields vary: date/ex_date, dividend/amount, dividend_type
                date_raw    = item.get("date") or item.get("ex_date") or item.get("exDate", "")
                amount      = item.get("dividend") or item.get("amount") or item.get("value", "")
                dtype       = item.get("dividend_type") or item.get("type", "Dividend")
                label       = f"Dividend ({dtype})" if dtype and dtype.lower() != "dividend" else "Dividend"
                records.append({
                    "symbol":      symbol,
                    "date":        date_raw,
                    "action_type": label,
                    "value":       str(amount),
                    "description": f"₹{amount} per share" if amount else "",
                })
        else:
            log.debug(f"{symbol}: dividends API returned {r.status_code}")
    except Exception as e:
        log.debug(f"{symbol}: dividends API error: {e}")

    # ── Endpoint 2: corporate events (splits, bonus, rights, mergers …) ───────
    events_url = f"https://www.screener.in/api/company/{company_id}/events/"
    try:
        r = session.get(events_url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            items = data if isinstance(data, list) else data.get("events", [])
            for item in items:
                date_raw    = item.get("date") or item.get("ex_date") or item.get("exDate", "")
                action_type = item.get("type") or item.get("action") or item.get("event", "Corporate Action")
                value       = item.get("ratio") or item.get("value") or item.get("amount", "")
                desc        = item.get("description") or item.get("remarks") or item.get("notes", "")
                records.append({
                    "symbol":      symbol,
                    "date":        date_raw,
                    "action_type": str(action_type).strip(),
                    "value":       str(value).strip() if value else "",
                    "description": str(desc).strip(),
                })
        else:
            log.debug(f"{symbol}: events API returned {r.status_code}")
    except Exception as e:
        log.debug(f"{symbol}: events API error: {e}")

    # ── Fallback: parse HTML page for corporate actions tables ────────────────
    # Screener embeds the same data in the page HTML under a <section id="dividends">
    # and similar blocks — useful when the JSON APIs require extra auth.
    return _records_to_df(records, symbol)


def _parse_corporate_actions_html(html: str, symbol: str) -> pd.DataFrame | None:
    """
    Fallback HTML parser for corporate actions.

    Screener's page has sections like:
      <section id="dividends"> ... <table> ... </table> </section>

    The section IDs actually used on Screener are:
      #dividends   → dividend history table
      (splits/bonus are usually inside the main #profit-loss or a notes block)

    Columns in the dividends table:
      Announcement Date | Ex-Dividend Date | Dividend Type | Dividend (Rs)
    """
    soup    = BeautifulSoup(html, "lxml")
    records = []

    # Known section IDs on Screener.in
    for section_id in ("dividends", "corporate-actions", "bonus", "splits"):
        section = soup.find("section", {"id": section_id})
        if not section:
            continue
        table = section.find("table")
        if not table:
            continue

        # Header
        thead = table.find("thead")
        if thead:
            headers = [th.get_text(strip=True) for th in thead.find_all(["th", "td"])]
        else:
            rows = table.find_all("tr")
            if not rows:
                continue
            headers = [td.get_text(strip=True) for td in rows[0].find_all(["th", "td"])]

        headers_lc = [h.lower() for h in headers]

        # Identify column positions
        def col_idx(*keywords):
            for kw in keywords:
                for i, h in enumerate(headers_lc):
                    if kw in h:
                        return i
            return None

        date_col   = col_idx("ex-div", "ex date", "ex_date", "announcement", "date")
        type_col   = col_idx("type", "dividend type", "action")
        value_col  = col_idx("dividend (rs)", "dividend", "amount", "value", "ratio")
        desc_col   = col_idx("remark", "description", "notes")

        tbody = table.find("tbody") or table
        for row in tbody.find_all("tr"):
            cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
            if not cells or len(cells) < 2:
                continue

            def _get(idx):
                return cells[idx] if idx is not None and idx < len(cells) else ""

            date_raw    = _get(date_col)
            action_type = _get(type_col) or section_id.title()
            value       = _get(value_col)
            desc        = _get(desc_col)

            if not date_raw and not value:
                continue

            records.append({
                "symbol":      symbol,
                "date":        date_raw,
                "action_type": action_type.strip() or section_id.title(),
                "value":       value.strip(),
                "description": desc.strip(),
            })

    return _records_to_df(records, symbol)


def _records_to_df(records: list[dict], symbol: str) -> pd.DataFrame | None:
    """Convert a list of corporate-action record dicts into a clean DataFrame."""
    if not records:
        return None
    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[df["action_type"].notna() & (df["action_type"] != "")]
    df = df.drop_duplicates(subset=["symbol", "date", "action_type", "value"])
    df = df.sort_values("date", ascending=False).reset_index(drop=True)
    return df if not df.empty else None


# ─── COMPANY ID LOOKUP (for export API) ──────────────────────────────────────
# ─── COMPANY ID CACHE ─────────────────────────────────────────────

COMPANY_ID_CACHE_FILE = Path(
    "data/company_ids.json"
)

try:

    if COMPANY_ID_CACHE_FILE.exists():

        with open(COMPANY_ID_CACHE_FILE, "r") as f:

            _id_cache = json.load(f)

    else:

        _id_cache = {}

except Exception:

    _id_cache = {}
def get_company_id(session: requests.Session, symbol: str) -> int | None:
    """
    Look up Screener's internal numeric company ID via search API.
    Result is cached in-process so we only call it once per symbol.
    """
    if symbol in _id_cache:
        return _id_cache[symbol]

    url = f"https://www.screener.in/api/company/search/?q={symbol}&v=3&fts=1"
    try:
        r = session.get(url, timeout=10)
        if r.status_code != 200:
            log.warning(f"{symbol}: search API returned HTTP {r.status_code} — SESSION_ID may be invalid or expired")
            _id_cache[symbol] = None
            return None

        results = r.json()
        if not results:
            log.warning(f"{symbol}: search API returned empty results — check SESSION_ID cookie")
            _id_cache[symbol] = None
            return None

        # Prefer exact symbol match, fall back to first result
        company_id = None
        for res in results:
            # Screener's URL slug often contains the symbol, e.g. /company/Angelone/
            slug = res.get("url", "").strip("/").split("/")[-1].upper()
            if slug == symbol or res.get("name", "").upper() == symbol:
                company_id = res["id"]
                break
        if company_id is None:
            company_id = results[0]["id"]
            log.debug(f"{symbol}: using first search result id={company_id} "
                      f"({results[0].get('name','')})")

        _id_cache[symbol] = company_id
        try:

            COMPANY_ID_CACHE_FILE.parent.mkdir(
                parents=True,
                exist_ok=True
            )

            with open(COMPANY_ID_CACHE_FILE, "w") as f:

                json.dump(_id_cache, f)

        except Exception as e:

            log.warning(
                f"Could not save company id cache: {e}"
            )
        log.debug(f"{symbol}: company_id={company_id}")
        return company_id

    except Exception as e:
        log.warning(f"{symbol}: company ID lookup failed: {e}")
        _id_cache[symbol] = None
        return None


# ─── FINANCIALS VIA EXPORT API ────────────────────────────────────────────────

# ─── FINANCIALS — HTML SCRAPER ───────────────────────────────────────────────
# Screener discontinued the /api/company/<id>/export/ endpoint.
# We now scrape financials directly from the embedded HTML tables on the
# company page (same page we already fetch for shareholding).
#
# Screener page structure (confirmed live):
#   <section id="quarters">          ← Quarterly Results table
#   <section id="profit-loss">       ← Annual Profit & Loss table
#
# Each section contains a <table> with:
#   thead: row of period headers  (Mar 2023, Jun 2023 … TTM)
#   tbody: one row per metric     (Sales, Expenses, Operating Profit, OPM %, …)

WANTED_METRICS = {
    "sales":            "Sales",
    "revenue":          "Sales",
    "operating profit": "EBITDA",
    "opm %":            "EBITDA Margin %",
    "net profit":       "Net Profit",
    "eps in rs":        "EPS",
    "eps":              "EPS",
}

# Cash-flow line labels on Screener → canonical metric name
# Screener's cash-flow section id: "cash-flow"
# Rows (annual only — Screener does not publish quarterly CF):
#   Cash from Operating Activity
#   Cash from Investing Activity
#   Cash from Financing Activity
#   Net Cash Flow

WANTED_CF_METRICS = {

    # ─────────────────────────────────────────
    # Operating Cash Flow
    # ─────────────────────────────────────────
    "cash from operating":  "CFO",
    "operating activity":   "CFO",

    # ─────────────────────────────────────────
    # Investing Cash Flow
    # ─────────────────────────────────────────
    "cash from investing":  "CFI",
    "investing activity":   "CFI",

    # ─────────────────────────────────────────
    # Financing Cash Flow
    # ─────────────────────────────────────────
    "cash from financing":  "CFF",
    "financing activity":   "CFF",

    # ─────────────────────────────────────────
    # Net Cash
    # ─────────────────────────────────────────
    "net cash":             "Net Cash Flow",

    # ─────────────────────────────────────────
    # Free Cash Flow
    # (raw Screener value)
    # ─────────────────────────────────────────
    "free cash":            "Free Cash Flow",
    "cfo/op": "CFO/OP",

    # asset sale proceeds
    "fixed assets sold":      "Fixed Assets Sold",
}
def _to_float(raw: str) -> float | None:
    raw = raw.strip().replace(",", "").replace("%", "").replace("₹", "")
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_fin_table(table, symbol: str, freq: str) -> list[dict]:
    """Parse one Screener financials <table> into records."""
    records = []

    # Period headers are in the first row of thead (or first tr)
    thead = table.find("thead")
    if thead:
        header_row = thead.find("tr")
    else:
        header_row = table.find("tr")
    if not header_row:
        return records

    periods = [th.get_text(" ", strip=True) for th in header_row.find_all(["th", "td"])]
    # First cell is blank label column; rest are period strings
    periods = periods[1:]
    if not periods:
        return records

    # Data rows are in tbody
    tbody = table.find("tbody") or table
    for row in tbody.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if not cells:
            continue
        label_lc = cells[0].get_text(" ", strip=True).lower()
        matched   = None
        for key, canonical in WANTED_METRICS.items():
            if key in label_lc:
                matched = canonical
                break
        if not matched:
            continue

        values = [td.get_text(" ", strip=True) for td in cells[1:]]
        for period, raw in zip(periods, values):
            if period.upper() in ("TTM", ""):
                continue
            val = _to_float(raw)
            if val is not None:
                records.append({
                    "symbol": symbol,
                    "period": period,
                    "freq":   freq,
                    "metric": matched,
                    "value":  val,
                })
    return records


def parse_financials_from_html(html: str, symbol: str) -> pd.DataFrame | None:
    """
    Extract quarterly + annual financials from a Screener company page.

    Section IDs used by Screener:
        quarters      -> quarterly results
        profit-loss   -> annual profit & loss
    """
    soup    = BeautifulSoup(html, "lxml")
    records = []

    section_map = {
        "quarters":    "quarterly",
        "profit-loss": "annual",
    }

    for section_id, freq in section_map.items():
        section = soup.find("section", {"id": section_id})
        if not section:
            log.debug("%s: section #%s not found in HTML", symbol, section_id)
            continue
        table = section.find("table")
        if not table:
            log.debug("%s: no table inside #%s", symbol, section_id)
            continue
        rows = _parse_fin_table(table, symbol, freq)
        log.debug("%s: #%s -> %d rows", symbol, section_id, len(rows))
        records.extend(rows)

    if not records:
        return None

    df = pd.DataFrame(records)
    # Prefer quarterly over annual for the same period+metric
    df = (df.sort_values("freq", ascending=True)
            .drop_duplicates(subset=["symbol", "period", "metric"], keep="last"))
    return df.reset_index(drop=True)


def fetch_financials_via_api(session: requests.Session,
                              symbol: str,
                              company_id: int,
                              report_type: str = REPORT_TYPE) -> pd.DataFrame | None:
    """
    Stub kept for API compatibility.
    The export endpoint (/api/company/<id>/export/) was discontinued by Screener.
    Financials are now parsed directly from the HTML page in fetch_symbol().
    This function is no longer called; parse_financials_from_html() is used instead.
    """
    return None


# ─── CASH FLOW PARSER ────────────────────────────────────────────────────────
# Screener publishes annual cash-flow data under <section id="cash-flow">.
# The table structure is identical to the P&L table so we reuse _parse_fin_table
# but feed it WANTED_CF_METRICS instead of WANTED_METRICS.

def _parse_cf_table(table, symbol: str) -> list[dict]:
    """
    Parse Screener's cash-flow <table>.  Reuses the same cell-extraction logic
    as _parse_fin_table but matches against WANTED_CF_METRICS and always tags
    freq='annual' (Screener only shows annual CF).
    """
    records = []

    thead = table.find("thead")
    header_row = thead.find("tr") if thead else table.find("tr")
    if not header_row:
        return records

    periods = [th.get_text(" ", strip=True) for th in header_row.find_all(["th", "td"])]
    periods = periods[1:]          # first cell is the blank row-label column
    if not periods:
        return records

    tbody = table.find("tbody") or table
    for row in table.select("tr"):
        cells = row.find_all(["td", "th"])
        if not cells:
            continue
        label_lc = cells[0].get_text(" ", strip=True).lower()
        #print(label_lc)
        # if "investing" in label_lc:
        #     print(row.prettify())
        #     print("=" * 100)
        matched = None
        for key, canonical in WANTED_CF_METRICS.items():
            if key in label_lc:
                matched = canonical
                break
        if not matched:
            continue

        values = [td.get_text(" ", strip=True) for td in cells[1:]]
        for period, raw in zip(periods, values):
            if period.upper() in ("TTM", ""):
                continue
            val = _to_float(raw)
            if val is not None:
                # Normalize Capex as positive
                if matched == "Capex":
                    val = abs(val)

                records.append({
                    "symbol": symbol,
                    "period": period,
                    "freq":   "annual",
                    "metric": matched,
                    "value":  val,
                })
    return records


def fetch_cf_schedule(
    session,
    company_id,
    parent,
):

    url = (
        f"https://www.screener.in/api/company/"
        f"{company_id}/schedules/"
    )

    params = {
        "parent": parent,
        "section": "cash-flow",
        "consolidated": "",
    }

    resp = session.get(
        url,
        params=params,
        timeout=20,
    )

    if resp.status_code != 200:

        print(
            "Schedule fetch failed:",
            resp.status_code
        )

        return None

    return resp.text
def parse_cash_flow_from_html(html: str, symbol: str,session ) -> pd.DataFrame | None:

    soup = BeautifulSoup(html, "lxml")

    section = soup.find("section", {"id": "cash-flow"})

    if not section:
        log.debug("%s: section #cash-flow not found in HTML", symbol)
        return None

    table = section.find("table")

    if not table:
        log.debug("%s: no table inside #cash-flow", symbol)
        return None

    records = _parse_cf_table(table, symbol)

    log.debug("%s: #cash-flow -> %d rows", symbol, len(records))

    if not records:
        return None

    df = pd.DataFrame(records)
       

    # Extract Screener company ID
    m = re.search(
        r'data-company-id="(\d+)"',
        html
    )

    company_id = m.group(1) if m else None

    #print("COMPANY ID:", company_id)
    investing_html = fetch_cf_schedule(
    session,
    company_id,
    "Cash from Investing Activity",
)

   # print(investing_html)
    if investing_html:

        try:
            investing_json = json.loads(investing_html)

            capex_data = investing_json.get(
                "Fixed assets purchased",
                {}
            )

            for period, raw_val in capex_data.items():

                val = _to_float(raw_val)

                if val is not None:

                    df = pd.concat([
                        df,
                        pd.DataFrame([{
                            "symbol": symbol,
                            "period": period,
                            "freq": "annual",
                            "metric": "Capex",
                            "value": abs(val),
                        }])
                    ], ignore_index=True)

        except Exception as e:

            print("Capex parse failed:", e)
# ─────────────────────────────────────────────
# Derive True Free Cash Flow
# ─────────────────────────────────────────────

    # ─────────────────────────────────────────────
    # Derive True Free Cash Flow
    # ─────────────────────────────────────────────

    # ─────────────────────────────────────────────
# Derive True Free Cash Flow
# ─────────────────────────────────────────────

    derived_rows = []

    for period in df["period"].unique():

        sub = df[df["period"] == period]

        try:
            cfo = sub.loc[
                sub["metric"] == "CFO",
                "value"
            ].iloc[0]

        except:
            cfo = None

        try:
            capex = sub.loc[
                sub["metric"] == "Capex",
                "value"
            ].iloc[0]

        except:
            capex = None

        if pd.notna(capex):
            capex = abs(capex)

        # ─────────────────────────────
        # True Free Cash Flow
        # ─────────────────────────────

        if (
            pd.notna(cfo)
            and pd.notna(capex)
        ):

            true_fcf = cfo - capex

            derived_rows.append({
                "symbol": symbol,
                "period": period,
                "freq": "annual",
                "metric": "True Free Cash Flow",
                "value": round(true_fcf, 2),
            })

    # Append derived metrics

    if derived_rows:

        df = pd.concat([
            df,
            pd.DataFrame(derived_rows)
        ], ignore_index=True)

    df = df.drop_duplicates(
        subset=["symbol", "period", "metric"]
    )

    return df.reset_index(drop=True)


# ─── COMBINED FETCHER ─────────────────────────────────────────────────────────

def fetch_symbol(session: requests.Session,
                  symbol: str,
                  page_html: str | None = None,refresh_ca=True
                 ) -> tuple[pd.DataFrame | None, pd.DataFrame | None, pd.DataFrame | None, pd.DataFrame | None, dict]:
    """
    Fetch shareholding + financials + cash flow + corporate actions + snapshot.

    Returns: (sh_df, fin_df, cf_df, ca_df, snapshot_dict)
    """
   
    snapshot  = {"symbol": symbol, "market_cap_cr": None, "ltp": None}
    sh_df     = None
    fin_df    = None
    cf_df     = None
    ca_df     = None

    # ── Pass 1: HTML page for shareholding + snapshot ─────────────────────────
    if page_html is None:

        html_urls = [
        f"https://www.screener.in/company/{symbol}/consolidated/",
    ]

        for url in html_urls:
            for attempt in range(1, MAX_RETRIES + 2):
                try:
                    r = session.get(url, timeout=(10,30))
                    if r.status_code == 200:
                        page_html = r.text
                        break   # page ok but no shareholding — try consolidated
                    elif r.status_code == 404:
                        break
                    else:
                        time.sleep(2)
                except requests.RequestException:
                    time.sleep(2)
            if sh_df is not None:
                break

    # ── Pass 2: Financials + Cash Flow + CA from HTML ────────────────────────
    if page_html:

        sh_df = parse_shareholding_page(page_html, symbol)

        snapshot = parse_snapshot(page_html, symbol)

        fin_df = parse_financials_from_html(page_html, symbol)

        cf_df = parse_cash_flow_from_html(page_html, symbol,session)

        ca_df = _parse_corporate_actions_html(page_html, symbol)

    # Also try JSON CA endpoints (they may have more history)
    if refresh_ca:
        company_id = get_company_id(session, symbol)
        if company_id:
            time.sleep(0.3)
            ca_api = fetch_corporate_actions_api(session, symbol, company_id)
            if ca_api is not None and not ca_api.empty:
                if ca_df is not None and not ca_df.empty:
                    ca_df = pd.concat([ca_df, ca_api], ignore_index=True).drop_duplicates(
                        subset=["symbol", "date", "action_type", "value"])
                else:
                    ca_df = ca_api

    rows_sh  = len(sh_df)  if sh_df  is not None else 0
    rows_fin = len(fin_df) if fin_df is not None else 0
    rows_cf  = len(cf_df)  if cf_df  is not None else 0
    rows_ca  = len(ca_df)  if ca_df  is not None else 0
    log.info(
        f"✓ {symbol}: SH={rows_sh} | FIN={rows_fin} | CF={rows_cf} | CA={rows_ca} | "
        f"LTP={snapshot['ltp']} | MCap={snapshot['market_cap_cr']}"
    )
    return sh_df, fin_df, cf_df, ca_df, snapshot


# ─── MAIN LOOP ────────────────────────────────────────────────────────────────

def _is_cached(sh_path: Path, fin_path: Path) -> bool:

    try:

        if not sh_path.exists() or not fin_path.exists():
            return False

        sh_c = pd.read_parquet(sh_path)
        fin_c = pd.read_parquet(fin_path)

        if sh_c.empty or fin_c.empty:
            return False

        return True

        if fin_path.exists():

            try:
                fin_c = pd.read_parquet(fin_path)

                # if finance exists and has data → great
                if not fin_c.empty:
                    return True

            except:
                pass

        return False

    except Exception:

        return False


def _read_snapshot_from_cache(snap_path: Path, symbol: str) -> dict:
    """Read a single symbol's snapshot (LTP / MCap) from the existing snapshot CSV."""
    blank = {"symbol": symbol, "market_cap_cr": None, "ltp": None}
    try:
        if not snap_path.exists():
            return blank
        df = pd.read_parquet(snap_path)
        row = df[df["symbol"] == symbol]
        if row.empty:
            return blank
        row_dict = row.iloc[0]
        return {
            "symbol":        symbol,
            "market_cap_cr": row_dict["market_cap_cr"],
            "ltp":           row_dict["ltp"],
        }
    except Exception:
        return blank


def _rebuild_masters(symbols: list[str]) -> None:
    """
    Rebuild all master CSVs by scanning ALL per-stock files on disk (in parallel batches).
    Runs after every fetch so cached + newly fetched stocks all appear in masters.
    """
    all_sh, all_fin, all_cf, all_ca = [], [], [], []

    # Batch read all files with minimal I/O overhead
    dtypes_sh  = {"symbol": "str", "quarter": "str", "category": "str", "pct": "float"}
    dtypes_fin = {"symbol": "str", "period": "str", "freq": "str", "metric": "str", "value": "float"}
    dtypes_cf  = {"symbol": "str", "period": "str", "freq": "str", "metric": "str", "value": "float"}
    dtypes_ca  = {"symbol": "str", "date": "str", "action_type": "str", "value": "str", "description": "str"}

    for sym in symbols:
        for path, bucket, dtypes in [
            (OUT_DIR_SH  / f"shareholding_{sym}.parquet",        all_sh,  dtypes_sh),
            (OUT_DIR_FIN / f"financials_{sym}.parquet",          all_fin, dtypes_fin),
            (OUT_DIR_CF  / f"cashflow_{sym}.parquet",            all_cf,  dtypes_cf),
            (OUT_DIR_CA  / f"corporate_actions_{sym}.parquet",   all_ca,  dtypes_ca),
        ]:
            if path.exists():
                try:
                    df = pd.read_parquet(path)
                    if not df.empty:
                        bucket.append(df)
                except Exception:
                    pass

    for bucket, path, label in [
        (all_sh,  MASTER_CSV_SH,  "Shareholding"),
        (all_fin, MASTER_CSV_FIN, "Financials"),
        (all_cf,  MASTER_CSV_CF,  "Cash Flow"),
        (all_ca,  MASTER_CSV_CA,  "Corporate Actions"),
    ]:
        if bucket:
            master_df = pd.concat(bucket, ignore_index=True)
            master_df.to_parquet(path, index=False)
            log.info(f"{label} master rebuilt → {path}  ({len(master_df)} rows)")



# def extract_latest_period_from_html(html: str):

#     if not html:
#         return None

#     # Parse visible text only
#     soup = BeautifulSoup(html, "lxml")

#     text = soup.get_text(" ", strip=True)

#     matches = re.findall(
#         r'(Mar|Jun|Sep|Dec)\s+20\d{2}',
#         text,
#         flags=re.IGNORECASE,
#     )

#     if not matches:
#         return None

#     # Rebuild full quarter strings
#     full_matches = re.findall(
#         r'(?:Mar|Jun|Sep|Dec)\s+20\d{2}',
#         text,
#         flags=re.IGNORECASE,
#     )

#     quarter_map = {
#         'Mar': 3,
#         'Jun': 6,
#         'Sep': 9,
#         'Dec': 12,
#     }

#     parsed = []

#     for item in full_matches:

#         try:

#             q, year = item.split()

#             parsed.append(
#                 (
#                     int(year),
#                     quarter_map[q.title()],
#                     item.strip(),
#                 )
#             )

#         except:
#             continue

#     if not parsed:
#         return None

#     parsed.sort()

#     return parsed[-1][2]
def extract_latest_period_from_html(html: str):
    """
    Return the latest period string found in the quarterly-results table
    (section#quarters thead) only.

    Scoping to #quarters prevents shareholding table headers (which are
    updated earlier than financial results) from triggering a false
    re-fetch when financials for that quarter aren't declared yet.
    """
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")

    # ── Only look inside the quarterly-results section ────────────────────
    section = soup.find("section", {"id": "quarters"})
    if not section:
        return None

    thead = section.find("thead")
    if not thead:
        return None

    # Period strings are the <th> cells in the header row
    header_row = thead.find("tr")
    if not header_row:
        return None

    quarter_map = {"Mar": 3, "Jun": 6, "Sep": 9, "Dec": 12}
    parsed = []

    for th in header_row.find_all(["th", "td"]):
        text = th.get_text(" ", strip=True)
        m = re.match(r'(Mar|Jun|Sep|Dec)\s+(20\d{2})', text, re.IGNORECASE)
        if m:
            q, year = m.group(1).title(), int(m.group(2))
            if q in quarter_map:
                parsed.append((year, quarter_map[q], text.strip()))

    if not parsed:
        return None

    parsed.sort()
    return parsed[-1][2]
def get_local_latest_period(file_path: Path):

    if not file_path.exists():
        return None

    try:

        df = pd.read_parquet(file_path)

        if df.empty:
            return None

        periods = (
            df["period"]
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )

        if not periods:
            return None

        quarter_map = {
            'Mar': 3,
            'Jun': 6,
            'Sep': 9,
            'Dec': 12,
        }

        parsed = []

        for p in periods:

            try:

                q, year = p.split()

                parsed.append(
                    (
                        int(year),
                        quarter_map[q.title()],
                        p,
                    )
                )

            except:
                continue

        if not parsed:
            return None

        parsed.sort()

        return parsed[-1][2]

    except:

        return None

def run(session_id: str = SESSION_ID, symbols: list[str] | None = None):
    """
    Fetch shareholding + financials + cash flow + corporate actions for all symbols.

    Cache behaviour
    ───────────────
    A symbol is skipped when both its shareholding AND financials CSVs exist
    and contain data.  Cash-flow and CA are excluded from the gate (may be
    legitimately empty for certain stocks).

    Master CSVs are always rebuilt from ALL per-stock files on disk, so
    running for a subset of symbols never wipes already-cached stocks.
    """
    Path("logs").mkdir(exist_ok=True)
    for d in [OUT_DIR_SH, OUT_DIR_FIN, OUT_DIR_CF, OUT_DIR_CA]:
        d.mkdir(parents=True, exist_ok=True)
    MASTER_CSV_SH.parent.mkdir(parents=True, exist_ok=True)

    if symbols is None:
        symbols = parse_watchlist()

    if not symbols:
        log.error("No symbols to process.")
        return (pd.DataFrame(),) * 5

    total        = len(symbols)
    fetched      = 0
    cached_count = 0

    # ── Determine which symbols actually need fetching ────────────────────────
    to_fetch = []
    session = make_session(session_id)
    for sym in symbols:

        sh_path  = OUT_DIR_SH  / f"shareholding_{sym}.parquet"
        fin_path = OUT_DIR_FIN / f"financials_{sym}.parquet"

        needs_refresh = False

        # ─────────────────────────────────────────
        # If files exist → compare latest periods
        # ─────────────────────────────────────────

        if _is_cached(sh_path, fin_path):
            # if not force_refresh:
            if not (force_refresh or _needs_staleness_check(fin_path)):

                cached_count += 1

                continue
            try:

                local_latest = get_local_latest_period(
                    fin_path
                )

                # lightweight HTML fetch
                
                html = fetch_html(session, sym)
                web_latest = extract_latest_period_from_html(
                    html
                )

                # Compare latest quarter
                #if web_latest != local_latest:
                # Compare latest quarter
                if (
                    web_latest is not None
                    and web_latest != local_latest
                ):

                    log.info(
                        f"{sym}: New data detected | "
                        f"Local={local_latest} | "
                        f"Web={web_latest}"
                    )

                    needs_refresh = True

                elif web_latest is None:

                    log.warning(
                        f"{sym}: Could not detect latest web period"
                    )

                    cached_count += 1

                    continue

                else:

                    cached_count += 1

                    continue

            except Exception as e:

                log.warning(
                    f"{sym}: quarter detection failed → {e}"
                )

                needs_refresh = True

        else:

            needs_refresh = True

        # ─────────────────────────────────────────
        # Add for fetching
        # ─────────────────────────────────────────

        if needs_refresh:

            to_fetch.append(sym)

    log.info(
        f"Total symbols: {total} | "
        f"Already cached: {cached_count} | "
        f"Need fetching: {len(to_fetch)}"
    )

    # ── Fetch only symbols that are not cached ────────────────────────────────
    if to_fetch:
        session = make_session(session_id)
        try:
            session.get("https://www.screener.in/", timeout=10)
            time.sleep(0.5)
        except Exception:
            pass

        # Load existing snapshot so we can upsert rather than overwrite
        snap_list = []
        if SNAPSHOT_FILE.exists():
            try:
                snap_df = pd.read_parquet(SNAPSHOT_FILE)
                snap_list = snap_df[~snap_df["symbol"].isin(to_fetch)].to_dict('records')
            except Exception:
                pass

        # Empty dataframes for per-stock CSVs
        empty_sh = pd.DataFrame(columns=["symbol","quarter","category","pct"])
        empty_fin = pd.DataFrame(columns=["symbol","period","freq","metric","value"])
        empty_cf = pd.DataFrame(columns=["symbol","period","freq","metric","value"])
        empty_ca = pd.DataFrame(columns=["symbol","date","action_type","value","description"])

        for i, sym in enumerate(to_fetch, 1):
            log.info(f"[fetch {i}/{len(to_fetch)}  |  total {cached_count + i}/{total}] {sym}…")

            sh_path  = OUT_DIR_SH  / f"shareholding_{sym}.parquet"
            fin_path = OUT_DIR_FIN / f"financials_{sym}.parquet"
            cf_path  = OUT_DIR_CF  / f"cashflow_{sym}.parquet"
            ca_path  = OUT_DIR_CA  / f"corporate_actions_{sym}.parquet"

            #sh_df, fin_df, cf_df, ca_df, snapshot = fetch_symbol(session, sym)
            
            html = fetch_html(session, sym)
            sh_df, fin_df, cf_df, ca_df, snapshot = fetch_symbol(
                session,
                sym,
                page_html=html,
                refresh_ca=force_refresh
                )
            
            # ── Save per-stock files ──────────────────────────────────────────
            # (sh_df if sh_df is not None else empty_sh).to_parquet(sh_path, index=False)
            # (fin_df if fin_df is not None else empty_fin).to_parquet(fin_path, index=False)
            # (cf_df if cf_df is not None else empty_cf).to_parquet(cf_path, index=False)
            # (ca_df if ca_df is not None else empty_ca).to_parquet(ca_path, index=False)
            if sh_df  is not None: _upsert_parquet(sh_path,  sh_df,  ["symbol","quarter","category"])
            if fin_df is not None: _upsert_parquet(fin_path, fin_df, ["symbol","period","metric"])
            if cf_df  is not None: _upsert_parquet(cf_path,  cf_df,  ["symbol","period","metric"])
            if ca_df  is not None: _upsert_parquet(ca_path,  ca_df,  ["symbol","date","action_type"])
            # ── Batch snapshot updates (append for batch write at end) ────────
            snap_list.append(snapshot)

            fetched += 1
            #time.sleep(DELAY_BETWEEN_REQUESTS)
            time.sleep(random.uniform(4, 8))
        # Batch write snapshots at the end
        if snap_list:
            pd.DataFrame(snap_list).to_parquet(SNAPSHOT_FILE, index=False)
            log.info(f"Snapshot saved → {SNAPSHOT_FILE}  ({len(snap_list)} rows)")

    else:
        log.info("All symbols already cached — no HTTP requests needed.")

    # ── Rebuild master CSVs from ALL per-stock files on disk ──────────────────
    log.info("Rebuilding master CSVs from all per-stock files…")
    _rebuild_masters(symbols)

    log.info(
        f"\n✅ Done! Fetched: {fetched} | Cached: {cached_count} | "
        f"Total in watchlist: {total}"
    )

    def _read_master(path: Path) -> pd.DataFrame:
        try:
            return pd.read_parquet(path) if path.exists() else pd.DataFrame()
        except Exception:
            return pd.DataFrame()

    return (
        _read_master(MASTER_CSV_SH),
        _read_master(MASTER_CSV_FIN),
        _read_master(MASTER_CSV_CF),
        _read_master(MASTER_CSV_CA),
        _read_master(SNAPSHOT_FILE),
    )


# ─── DEBUG HELPER ─────────────────────────────────────────────────────────────

def debug_snapshot(symbol: str, session_id: str = SESSION_ID):
    """
    Fetch one stock and print ALL #top-ratios labels + values.

    Usage:
        python screener_fetcher.py --debug RELIANCE
    """
    session = make_session(session_id)
    url     = f"https://www.screener.in/company/{symbol}/"
    r       = session.get(url, timeout=20)
    if r.status_code != 200:
        print(f"HTTP {r.status_code}")
        return

    soup = BeautifulSoup(r.text, "lxml")
    print(f"\n=== #top-ratios for {symbol} ===")
    for li in soup.select("#top-ratios li"):
        name = li.find("span", class_="name")
        num  = li.find("span", class_="number")
        sub  = li.find("span", class_="sub")
        print(f"  label={name.get_text(strip=True) if name else '?':30s} "
              f"value={num.get_text(strip=True) if num else '?':15s} "
              f"unit={sub.get_text(strip=True) if sub else ''}")

    snap = parse_snapshot(r.text, symbol)
    print(f"\n=== Parsed snapshot ===")
    print(f"  LTP      : {snap['ltp']}")
    print(f"  MCap(Cr) : {snap['market_cap_cr']}")

    cid = get_company_id(session, symbol)
    print(f"\n=== Company ID: {cid} ===")
    if cid:
        fin = fetch_financials_via_api(session, symbol, cid)
        if fin is not None:
            print(fin.to_string(index=False))
        else:
            print("No financials returned")
def _upsert_parquet(path: Path, new_df: pd.DataFrame, key_cols: list[str]):
    """Merge new data into existing parquet, deduplicating on key_cols."""
    if path.exists():
        try:
            old_df = pd.read_parquet(path)
            merged = pd.concat([old_df, new_df], ignore_index=True)
            merged = merged.drop_duplicates(subset=key_cols, keep="last")
            merged.to_parquet(path, index=False)
            return
        except Exception:
            pass
    new_df.to_parquet(path, index=False)

# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    # --debug SYMBOL    : print raw HTML ratios + parsed snapshot
    # --test SYMBOL     : fully fetch ONE stock (SH+FIN+CF+CA) with debug logs
    # --test-fin SYMBOL : dump financials + cash-flow parse result for one stock
    if len(sys.argv) >= 3 and sys.argv[1] == "--debug":
        debug_snapshot(sys.argv[2].upper())

    elif len(sys.argv) >= 3 and sys.argv[1] == "--test-fin":
        sym = sys.argv[2].upper()
        logging.getLogger().setLevel(logging.DEBUG)
        sess = make_session(SESSION_ID)
        url  = "https://www.screener.in/company/%s/" % sym
        r    = sess.get(url, timeout=20)
        print("Page HTTP:", r.status_code, "  size:", len(r.text), "chars")
        if r.status_code == 200:
            from bs4 import BeautifulSoup as _BS
            soup = _BS(r.text, "lxml")
            for sid in ("quarters", "profit-loss", "cash-flow"):
                sec = soup.find("section", {"id": sid})
                print("Section #%s: %s" % (sid, "found" if sec else "NOT FOUND"))
                if sec:
                    tbl = sec.find("table")
                    print("  Table:", "found" if tbl else "NOT FOUND")
                    if tbl:
                        rows = tbl.find_all("tr")
                        print("  Rows:", len(rows))
                        for row in rows[:5]:
                            cells = [td.get_text(" ", strip=True) for td in row.find_all(["td","th"])]
                            print("  ", cells[:8])
            df_fin = parse_financials_from_html(r.text, sym)
            print("Parsed FIN rows:", len(df_fin) if df_fin is not None else 0)
            if df_fin is not None and not df_fin.empty:
                print(df_fin.to_string(index=False))
            df_cf = parse_cash_flow_from_html(r.text, sym)
            print("\nParsed CF rows:", len(df_cf) if df_cf is not None else 0)
            if df_cf is not None and not df_cf.empty:
                print(df_cf.to_string(index=False))

    elif len(sys.argv) >= 3 and sys.argv[1] == "--test":
        sym = sys.argv[2].upper()
        logging.getLogger().setLevel(logging.DEBUG)
        sess = make_session(SESSION_ID)
        sh, fin, cf, ca, snap = fetch_symbol(sess, sym)
        print("SH rows :", len(sh)  if sh  is not None else 0)
        print("FIN rows:", len(fin) if fin is not None else 0)
        print("CF rows :", len(cf)  if cf  is not None else 0)
        print("CA rows :", len(ca)  if ca  is not None else 0)
        print("Snapshot:", snap)
        if fin is not None and not fin.empty:
            print("\nFinancials:")
            print(fin.to_string(index=False))
        if cf is not None and not cf.empty:
            print("\nCash Flow:")
            print(cf.to_string(index=False))
        if ca is not None and not ca.empty:
            print("\nCorporate actions:")
            print(ca.to_string(index=False))

    else:
        sh_master, fin_master, cf_master, ca_master, snap = run()
        if not fin_master.empty:
            print("Financials sample:")
            print(fin_master.head(20).to_string(index=False))
        if not cf_master.empty:
            print("\nCash Flow sample:")
            print(cf_master.head(20).to_string(index=False))
        if not ca_master.empty:
            print("\nCorporate actions sample:")
            print(ca_master.head(10).to_string(index=False))
        if not snap.empty:
            print("\nSnapshot sample:")
            print(snap.head(10).to_string(index=False))
