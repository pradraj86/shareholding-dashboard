import threading
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
from concurrent.futures import ThreadPoolExecutor


log = logging.getLogger(__name__)

# ─── CONFIGURATION ────────────────────────────────────────────────────────────

SESSION_ID      = os.getenv("zln6z7ayq33706rxkatfg5qe6lo19q2c", "")   # Set this in your environment
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
COMPANY_ID_CACHE_FILE = Path(
    "data/company_ids.json"
)

# "standalone" | "consolidated" | "auto"
# "auto" = try consolidated first, fall back to standalone if no data
REPORT_TYPE = "consolidated"

DELAY_BETWEEN_REQUESTS = 1.5
MAX_RETRIES            = 2
FULL_REFRESH_DAY = "Sunday"
# Replace the hard Sunday gate with a staleness check
REFRESH_AFTER_DAYS = 2   # check for new quarters if file is older than this

def _needs_staleness_check(path: Path) -> bool:
    """
    Checks if the file is older than REFRESH_AFTER_DAYS.
    Uses pathlib for consistency and handles potential OS errors.
    """
    if not path.exists():
        return True

    try:
        # Using path.stat() is the pathlib-native way to get mtime
        file_mtime = path.stat().st_mtime
        age_days = (time.time() - file_mtime) / 86400
        
        return age_days >= REFRESH_AFTER_DAYS
        
    except (OSError, PermissionError) as e:
        # If we can't even read the metadata, assume it's stale 
        # so we can try to re-download and fix it.
        log.error(f"Error accessing metadata for {path}: {e}")
        return True
# ─── LOGGING ──────────────────────────────────────────────────────────────────
today = datetime.now().strftime("%A")

force_refresh = today == FULL_REFRESH_DAY


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
    """
    Parse TradingView watchlist TXT → clean NSE symbols.
    Handles formats: 'NSE:RELIANCE', 'RELIANCE', 'RELIANCE, INFY'
    """
    if not filepath.exists():
        log.warning(f"Watchlist not found at {filepath}. Using defaults.")
        return ["RELIANCE", "INFY", "HDFCBANK", "TCS", "ICICIBANK"]

    symbols, seen = [], set()
    
    # Read file and split by lines
    lines = filepath.read_text(encoding="utf-8").splitlines()

    for line in lines:
        line = line.strip()
        
        # Skip empty lines or comments
        if not line or line.startswith("###"):
            continue
            
        # Split by comma to handle multiple symbols on one line
        parts = line.split(",")
        
        for part in parts:
            part = part.strip()
            if not part or part.startswith("###"):
                continue
            
            # Case 1: Explicit Exchange format (e.g., "NSE:RELIANCE")
            if ":" in part:
                exchange, sym = part.split(":", 1)
                if exchange.strip().upper() in KNOWN_EXCHANGES:
                    clean_sym = sym.strip().upper()
                    if clean_sym and clean_sym not in seen:
                        seen.add(clean_sym)
                        symbols.append(clean_sym)
                else:
                    # If the exchange is unknown, we treat it as a raw symbol 
                    # to try and salvage it, or log it.
                    log.debug(f"Unknown exchange '{exchange}' in part '{part}'. Treating as raw symbol.")
                    clean_sym = part.split()[-1].upper() # Take last part
                    if clean_sym and clean_sym not in seen:
                        seen.add(clean_sym)
                        symbols.append(clean_sym)
            
            # Case 2: Raw symbol format (e.g., "RELIANCE-EQ")
            else:
                # Instead of a destructive regex, we just clean up 
                # leading/trailing whitespace and ensure it's uppercase.
                # We only remove characters that are definitely not in symbols.
                clean_sym = part.upper()
                
                if clean_sym and clean_sym not in seen:
                    seen.add(clean_sym)
                    symbols.append(clean_sym)

    log.info(f"Loaded {len(symbols)} unique symbols from watchlist.")
    return symbols



def make_session(session_id: str) -> requests.Session:
    s = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
    s.mount("https://", adapter)
    s.mount("http://", adapter)

    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "en-IN,en;q=0.9",
        "Referer": "https://www.screener.in/",
    })

    if session_id:
        # FIX: Use ".screener.in" with a leading dot to ensure the cookie 
        # is sent to ALL sub-paths and sub-domains.
        s.cookies.set("sessionid", session_id, domain=".screener.in")

    return s

def fetch_html(session: requests.Session, symbol: str) -> str | None:
    # FIX: Use the MAIN company URL for detection. 
    # The /consolidated/ URL is often the cause of the "Guest" fallback.
    # url = f"https://www.screener.in/company/{symbol}/"
    # url = f"https://www.screener.in/company/{symbol}/consolidated/"
    urls = [
        # f"https://www.screener.in/company/{symbol}/",
        # f"https://www.screener.in/company/{symbol}/consolidated/",
        f"https://www.screener.in/company/{symbol}/consolidated/#quarters",
    ]

    for url in urls:
        try:
            r = session.get(url, timeout=20)

            if r.status_code == 200:
                return r.text

        except Exception as e:
            log.warning(f"{symbol}: {e}")

        return None
    
    try:
        r = session.get(url, timeout=20)
        if r.status_code == 200:
            return r.text
        log.warning(f"{symbol}: HTTP {r.status_code}")
        return None
    except Exception as e:
        log.error(f"{symbol}: Fetch error → {e}")
        return None
# ─── SHAREHOLDING PARSER (HTML scrape — unchanged, works correctly) ───────────

def parse_shareholding_page(html: str, symbol: str) -> pd.DataFrame | None:
    """
    Extract the shareholding table from a Screener.in company page.
    Returns tidy DataFrame: symbol | quarter | category | pct
    """
    soup = BeautifulSoup(html, "lxml")

    # 1. Find the target section
    section = soup.find("section", {"id": "shareholding"})
    if not section:
        # Fallback: Look for any table that contains key shareholding keywords
        for tbl in soup.find_all("table"):
            text = tbl.get_text()
            if "Promoters" in text and "FIIs" in text:
                section = tbl.parent
                break

    if not section:
        return None

    table = section.find("table")
    if not table:
        return None

    # 2. Extract Header (Periods)
    thead = table.find("thead")
    header_row = thead.find("tr") if thead else table.find("tr")
    if not header_row:
        return None

    header_cells = header_row.find_all(["th", "td"])
    # Skip the first cell (which is the 'Category' label)
    periods = [cell.get_text(" ", strip=True) for cell in header_cells[1:]]
    if not periods:
        return None

    # 3. Target only the BODY to avoid "Header Pollution"
    tbody = table.find("tbody")
    if tbody:
        rows = tbody.find_all("tr")
    else:
        # Fallback: if no tbody, find all rows and skip the first one (the header)
        all_rows = table.find_all("tr")
        rows = all_rows[1:] if len(all_rows) > 1 else []

    records = []
    keep_categories = {"promoters", "fiis", "diis", "public", "govt", "others"}

    for row in rows:
        cells = row.find_all(["td", "th"])
        if len(cells) <= 1:
            continue
        
        # Clean the category name (e.g., "Promoters %" -> "promoters")
        raw_category = cells[0].get_text(" ", strip=True).lower()
        # Remove special chars and spaces to make matching easier
        clean_category = re.sub(r'[^a-z]', '', raw_category)
        
        # Only proceed if the category matches our target list
        if not any(k in clean_category for k in keep_categories):
            continue

        # Standardize category names
        category_map = {
            "promoters": "Promoters",
            "fiis": "FIIs",
            "diis": "DIIs",
            "public": "Public",
            "others": "Others",
            "govt": "Govt",
        }

        normalized_category = None

        for key, value in category_map.items():
            if key in clean_category:
                normalized_category = value
                break

        if normalized_category is None:
            continue
                # 4. Extract Values for the period columns
        values = [cell.get_text(" ", strip=True) for cell in cells[1:]]
        
        for period, raw_val in zip(periods, values):
            if not period or period.upper() == "TTM":
                continue
                
            # Clean numeric value (rements commas, %, and ₹)
            clean_val = raw_val.replace(",", "").replace("%", "").replace("₹", "").strip()
            try:
                val = float(clean_val)
            except ValueError:
                val = None

            if val is not None:
                records.append({
                    "symbol": symbol,
                    "quarter": period,
                    # "category": raw_category.title(), # Store original name nicely
                    "category": normalized_category,
                    "pct": val,
                })

    if not records:
        return None

    df = pd.DataFrame(records)
    return df.reset_index(drop=True)


def parse_snapshot(html: str, symbol: str) -> dict:
    """
    Extracts LTP, Market Cap, P/E, and P/B from Screener.in #top-ratios.
    """
    soup = BeautifulSoup(html, "lxml")
    snapshot = {
        "symbol": symbol,
        "market_cap_cr": None,
        "ltp": None,
        "pe": None,
        "pb": None,
    }

    items = soup.select("#top-ratios li")
    for li in items:
        name_tag = li.find("span", class_="name")
        val_tag  = li.find("span", class_="number")
        if not (name_tag and val_tag):
            continue

        label = name_tag.get_text(strip=True).lower()
        raw_val = val_tag.get_text(strip=True).strip()

        # Skip empty or placeholder values
        if not raw_val or raw_val == "-":
            continue

        # Clean the value: remove commas, ₹ symbol, and units (Cr, cr, B, b)
        cleaned = raw_val.replace(",", "").replace("₹", "").strip()
        # Remove "Cr", "cr", "B", "b" at the end (with optional space)
        for unit in [" Cr", " cr", " B", " b"]:
            if cleaned.endswith(unit):
                cleaned = cleaned[:-len(unit)].strip()
                break

        try:
            val = float(cleaned)
        except ValueError:
            continue

        # ----- Priority order: PE and PB first -----
        if any(phrase in label for phrase in ["pe ratio", "price/earnings", "p/e"]):
            snapshot["pe"] = val
        elif any(phrase in label for phrase in ["pb ratio", "price/book", "p/b"]):
            snapshot["pb"] = val
        elif any(phrase in label for phrase in ["current price", "ltp", "cmp", "last price"]):
            snapshot["ltp"] = val
        elif any(phrase in label for phrase in ["market cap", "market capitalization"]):
            snapshot["market_cap_cr"] = val

        # Early exit if we've found all four (optional, but can speed up)
        if all(snapshot[k] is not None for k in ["ltp", "market_cap_cr", "pe", "pb"]):
            break

    return snapshot

def parse_financials_from_html(
    html: str,
    symbol: str,
) -> pd.DataFrame | None:

    soup = BeautifulSoup(html, "lxml")

    records = []

    # =====================================================
    # QUARTERLY RESULTS
    # =====================================================

    q_section = soup.find(
        "section",
        {"id": "quarters"}
    )

    if q_section:

        q_table = q_section.find("table")

        if q_table:

            rows = _parse_fin_table(
                q_table,
                symbol,
                "quarterly",
            )

            if rows:
                records.extend(rows)

    # =====================================================
    # PROFIT & LOSS (ANNUAL)
    # =====================================================

    pl_section = soup.find(
        "section",
        {"id": "profit-loss"}
    )

    if pl_section:

        pl_table = pl_section.find("table")

        if pl_table:

            rows = _parse_fin_table(
                pl_table,
                symbol,
                "annual",
            )

            if rows:
                records.extend(rows)

    # =====================================================
    # NOTHING FOUND
    # =====================================================

    if not records:

        log.warning(
            "%s: no financial records found",
            symbol,
        )

        return None

    # =====================================================
    # BUILD DF
    # =====================================================

    df = pd.DataFrame(records)

    df["value"] = pd.to_numeric(
        df["value"],
        errors="coerce",
    )

    df = df.dropna(
        subset=["value"]
    )

    # =====================================================
    # REMOVE DUPLICATES
    # =====================================================

    freq_rank = {
        "annual": 1,
        "quarterly": 2,
    }

    df["rank"] = (
        df["freq"]
        .map(freq_rank)
        .fillna(0)
    )

    df = (
        df.sort_values("rank")
          .drop_duplicates(
                subset=[
                    "symbol",
                    "period",
                    "metric",
                ],
                keep="last",
          )
          .drop(columns=["rank"])
    )

    return (
        df.sort_values(
            [
                "freq",
                "period",
                "metric",
            ]
        )
        .reset_index(drop=True)
    )
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
            

            # ─────────────────────────────────────────────
# Operating Schedule
# ─────────────────────────────────────────────

            operating_html = fetch_cf_schedule(
                session,
                company_id,
                "Cash from Operating Activity",
            )

            if operating_html:

                try:

                    operating_json = json.loads(
                        operating_html
                    )

                   

                    op_data = operating_json.get(
                        "Profit from operations",
                        {}
                    )

                    for period, raw_val in op_data.items():

                        val = _to_float(raw_val)

                        if val is not None:

                            df = pd.concat([
                                df,
                                pd.DataFrame([{
                                    "symbol": symbol,
                                    "period": period,
                                    "freq": "annual",
                                    "metric": "Profit from Operations",
                                    "value": val,
                                }])
                            ], ignore_index=True)

                except Exception as e:

                    print(
                        "Operating schedule parse failed:",
                        e
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
    # return parse_financials_from_html(html, symbol)
def fetch_corporate_actions_api(session: requests.Session,
                                symbol: str,
                                company_id: int,
                                html: str | None = None) -> pd.DataFrame | None:
    """
    Fetch corporate actions from Screener's JSON API.
    
    If API calls fail or return no data, it falls back to parsing 
    the provided HTML content using the HTML parser.
    """
    records = []

    # ── Endpoint 1: Dividends ─────────────────────────────────────────────────
    div_url = f"https://www.screener.in/api/company/{company_id}/dividends/"
    try:
        r = session.get(div_url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            items = data if isinstance(data, list) else data.get("dividends", [])
            for item in items:
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

    # ── Endpoint 2: Corporate Events ──────────────────────────────────────────
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

    # ── THE ACTUAL FALLBACK ───────────────────────────────────────────────────
    # If API returned nothing, attempt to parse the HTML provided
    if not records and html:
        log.info(f"{symbol}: API failed. Attempting HTML fallback...")
        html_records = _parse_corporate_actions_html(html, symbol)
        if html_records is not None:
            return html_records

    # If we have records (from API or fallback), clean and return them
    if records:
        return _records_to_df(records, symbol)
    
    return None


def _parse_corporate_actions_html(html: str, symbol: str) -> pd.DataFrame | None:
    """
    Fallback HTML parser for corporate actions.
    Handles different section IDs and avoids 'Header Pollution' by 
    properly targeting the table body.
    """
    soup = BeautifulSoup(html, "lxml")
    records = []

    # 1. Target specific sections used by Screener.in
    sections_to_check = [
        ("dividends", "Dividend"),
        ("corporate-actions", "Corporate Action"),
        ("bonus", "Bonus"),
        ("splits", "Split")
    ]

    for section_id, default_action in sections_to_check:
        section = soup.find("section", {"id": section_id})
        if not section:
            continue
            
        table = section.find("table")
        if not table:
            continue

        # 2. Robust Header Extraction
        thead = table.find("thead")
        header_row = thead.find("tr") if thead else table.find("tr")
        if not header_row:
            continue

        header_cells = header_row.find_all(["th", "td"])
        headers_lc = [h.get_text(strip=True).lower() for h in header_cells]

        # 3. Identify column positions via keyword mapping
        def get_col_idx(*keywords):
            for kw in keywords:
                for i, h in enumerate(headers_lc):
                    if kw in h:
                        return i
            return None

        date_col   = get_col_idx("ex-div", "ex date", "ex_date", "announcement", "date")
        type_col   = get_col_idx("type", "dividend type", "action")
        value_col  = get_col_idx("dividend", "amount", "value", "ratio")
        desc_col   = get_col_idx("remark", "description", "notes")

        # 4. Target only the DATA rows (The Fix for the Header Bug)
        # If <tbody> exists, use it. If not, find all <tr> and skip the first one.
        tbody = table.find("tbody")
        if tbody:
            rows = tbody.find_all("tr")
        else:
            all_rows = table.find_all("tr")
            rows = all_rows[1:] if len(all_rows) > 1 else []

        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            
            # Extract raw values safely
            def _get_val(idx):
                return cells[idx].get_text(strip=True) if idx is not None and idx < len(cells) else ""

            date_raw    = _get_val(date_col)
            action_type = _get_val(type_col)
            value       = _get_val(value_col)
            desc        = _get_val(desc_col)

            # Skip rows that are completely empty or just whitespace
            if not date_raw and not value:
                continue

            # Logic: Use the column's value if found, otherwise fallback to the section name
            final_action = action_type.strip() if action_type else default_action

            records.append({
                "symbol":      symbol,
                "date":        date_raw,
                "action_type": final_action,
                "value":       value.strip(),
                "description": desc.strip(),
            })

    # 5. Clean, Deduplicate, and Convert
    return _records_to_df(records, symbol)


def _records_to_df(records: list[dict], symbol: str) -> pd.DataFrame | None:
    """
    Convert a list of corporate-action record dicts into a clean, 
    type-safe DataFrame.
    """
    if not records:
        return None

    df = pd.DataFrame(records)

    # 1. Defensive Check: Ensure required columns exist to prevent KeyError
    required_cols = {"symbol", "date", "action_type", "value"}
    if not required_cols.issubset(df.columns):
        log.error(f"{symbol}: Corporate actions missing required columns. Found: {df.columns}")
        return None

    # 2. Standardize Types (The "Duplicate Fix")
    # We convert 'value' to numeric immediately. This ensures '10' and 10.0 
    # are seen as the same value during deduplication.
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    # 3. Clean Action Type
    # Ensure we are checking against strings and stripping whitespace
    df["action_type"] = df["action_type"].astype(str).str.strip()
    df = df[df["action_type"].notna() & (df["action_type"] != "")]

    # 4. Deduplicate and Sort
    # Now that types are normalized, drop_duplicates is 100% reliable
    df = df.drop_duplicates(subset=["symbol", "date", "action_type", "value"])
    
    # Sort by date descending (newest first)
    df = df.sort_values("date", ascending=False).reset_index(drop=True)

    return df if not df.empty else None

# ─── COMPANY ID CACHE ──────────────────────────────────────────────────────────

COMPANY_ID_CACHE_FILE = Path("data/company_ids.json")

try:
    if COMPANY_ID_CACHE_FILE.exists():
        # Use a context manager to ensure the file is closed properly
        with open(COMPANY_ID_CACHE_FILE, "r") as f:
            _id_cache = json.load(f)
    else:
        _id_cache = {}
except (json.JSONDecodeError, IOError) as e:
    # If the file is corrupted or unreadable, start fresh rather than crashing
    log.error(f"Failed to load company ID cache: {e}")
    _id_cache = {}



# Global lock for thread-safe cache access
_id_cache_lock = threading.Lock()
_id_cache = {} # Ensure this is initialized

def get_company_id(session: requests.Session, symbol: str) -> int | None:
    """
    Thread-safe lookup for Screener's internal numeric company ID.
    """
    # 1. Fast check with lock
    with _id_cache_lock:
        if symbol in _id_cache:
            return _id_cache[symbol]

    url = f"https://www.screener.in/api/company/search/?q={symbol}&v=3&fts=1"
    try:
        r = session.get(url, timeout=10)
        if r.status_code != 200:
            log.warning(f"{symbol}: API returned {r.status_code}")
            return None

        results = r.json()
        if not results:
            return None

        # 2. Exact Match Logic
        company_id = None
        for res in results:
            slug = res.get("url", "").strip("/").split("/")[-1].upper()
            if slug == symbol or res.get("name", "").upper() == symbol:
                company_id = res["id"]
                break
        
        # Fallback to first result
        if company_id is None:
            company_id = results[0]["id"]

        # 3. Update the cache safely using the lock
        with _id_cache_lock:
            _id_cache[symbol] = company_id
        
        log.debug(f"{symbol}: company_id={company_id}")
        return company_id

    except Exception as e:
        log.warning(f"{symbol}: company ID lookup failed: {e}")
        return None

def save_id_cache():
    """Saves the in-memory ID cache to disk. Call this ONCE at the end of run()."""
    try:
        COMPANY_ID_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _id_cache_lock: # Ensure we don't save while another thread is writing
            with open(COMPANY_ID_CACHE_FILE, "w") as f:
                json.dump(_id_cache, f)
        log.info(f"Successfully saved {len(_id_cache)} company IDs to disk.")
    except Exception as e:
        log.error(f"Failed to save company ID cache: {e}")

WANTED_METRICS = {
    "sales": "Sales",
    "revenue": "Sales",
    "total income": "Sales",  # More specific than just 'income'

    "operating profit": "EBITDA",
    "ebitda": "EBITDA",
    "profit before tax": "PBT",
    "pbt": "PBT",

    "opm %": "EBITDA Margin %",
    "operating margin": "EBIT_Margin %",

    "net profit": "Net Profit",
    "profit after tax": "Net Profit",
    "pat": "Net Profit",

    "eps in rs": "EPS",
    "eps": "EPS",
}

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

    # CFO/OP is NOT a Screener table row — derived in utils.calc_cfo_op()

    # ─────────────────────────────────────────
    # Fixed Assets / Capex
    # ─────────────────────────────────────────
    # Capex / Fixed Assets
    "fixed assets purchased": "Fixed Asset Purchased",
    "purchase of fixed assets": "Fixed Asset Purchased",
    "purchase of property": "Fixed Asset Purchased",
    "property plant equipment": "Fixed Asset Purchased",
    "purchase of property plant": "Fixed Asset Purchased",
    "purchase of ppe": "Fixed Asset Purchased",
    "capital expenditure": "Fixed Asset Purchased",
    "capex": "Fixed Asset Purchased",
    "profit from operations": "Profit from operations",
    # asset sale proceeds
    "fixed assets sold":      "Fixed Assets Sold",
}
def _to_float(raw):

    if raw is None:
        return None

    if isinstance(raw, dict):
        return None

    raw = str(raw)

    raw = (
        raw.strip()
           .replace(",", "")
           .replace("%", "")
           .replace("₹", "")
    )

    if raw == "-":
        return 0.0

    try:
        return float(raw)
    except:
        return None
def _parse_fin_table(table, symbol: str, freq: str) -> list[dict]:
    """
    Parse Screener's financial <table>. 
    Ensures only data rows are processed and handles TTM/empty periods correctly.
    """
    records = []
    
    # 1. Extract Header and Periods
    thead = table.find("thead")
    header_row = thead.find("tr") if thead else table.find("tr")
    if not header_row:
        return records

    # Get all header cells and skip the first one (the metric label)
    header_cells = header_row.find_all(["th", "td"])
    periods = [cell.get_text(" ", strip=True) for cell in header_cells[1:]]
    
    if not periods:
        return records

    # 2. Target only the data rows (tbody)
    # If <tbody> is missing, we find all <tr> but skip the first one (the header)
    tbody = table.find("tbody")
    if tbody:
        rows = tbody.find_all("tr")
    else:
        # Fallback: find all rows but skip the first one to avoid the header
        rows = table.find_all("tr")[1:]

    # 3. Process Rows
    for row in rows:
        cells = row.find_all(["td", "th"])
        if len(cells) <= 1:
            continue
        
        # The first cell is the metric name (e.g., "Sales")
        # label_lc = cells[0].get_text(" ", strip=True).lower()
        label_lc = (  cells[0]  .get_text(" ", strip=True)  .lower()   .replace("+", "")   .replace("-", "")
    .strip()
)
        
        # Keyword matching
        matched_metric = None
        for key, canonical in WANTED_METRICS.items():
            if key in label_lc:
                matched_metric = canonical
                break
        
        if not matched_metric:
            continue

        # 4. Map values to periods using zip
        # We iterate through the remaining cells (data) alongside the period headers
        data_cells = cells[1:]
        for period, cell in zip(periods, data_cells):
            # Skip TTM or empty period strings
            if not period or period.upper() == "TTM":
                continue
                
            raw_val = cell.get_text(" ", strip=True)
            val = _to_float(raw_val)
            
            if val is not None:
                records.append({
                    "symbol": symbol,
                    "period": period,
                    "freq": freq,
                    "metric": matched_metric,
                    "value": val,
                })
                
    return records

# ============================================================
# MAIN FINANCIAL PARSER
# ============================================================


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

# ============================================================
# CASHFLOW TABLE PARSER
# ============================================================

def _parse_cf_table(table, symbol: str) -> list[dict]:

    records = []

    # --------------------------------------------------------
    # HEADER EXTRACTION
    # --------------------------------------------------------

    thead = table.find("thead")

    header_row = (
        thead.find("tr")
        if thead
        else table.find("tr")
    )

    if not header_row:
        return records

    header_cells = header_row.find_all(["th", "td"])

    periods = [
        c.get_text(" ", strip=True)
        for c in header_cells[1:]
    ]

    if not periods:
        return records

    # --------------------------------------------------------
    # BODY ROWS
    # --------------------------------------------------------

    tbody = table.find("tbody") or table

    rows = table.find_all("tr")

    for row in rows:

        cells = row.find_all(["td", "th"])

        if len(cells) <= 1:
            continue

        # ----------------------------------------------------
        # CLEAN LABEL
        # ----------------------------------------------------

        label_lc = (
            cells[0]
            .get_text(" ", strip=True)
            .lower()
            .replace("+", "")
            .replace("-", "")
            .strip()
        )

       
        # ----------------------------------------------------
        # METRIC MATCH
        # ----------------------------------------------------

        matched_metric = None

        for key, canonical in WANTED_CF_METRICS.items():

            if key in label_lc:
                matched_metric = canonical
                break

        if not matched_metric:
            continue

        # ----------------------------------------------------
        # EXTRACT VALUES
        # ----------------------------------------------------

        for period, cell in zip(periods, cells[1:]):

            if not period:
                continue

            if period.upper() == "TTM":
                continue

            raw_val = cell.get_text(" ", strip=True)

            val = _to_float(raw_val)

            if val is None:
                continue

            records.append({
                "symbol": symbol.upper().strip(),
                "period": period,
                "freq": "annual",
                "metric": matched_metric,
                "value": val,
            })

    return records

def fetch_cf_schedule(
    session: requests.Session,
    company_id: int,
    parent: str
) -> str | None:
    """
    Fetches the JSON schedule for the cash-flow section from Screener API.
    Returns the raw JSON string if successful, otherwise returns None.
    """
    url = f"https://www.screener.in/api/company/{company_id}/schedules/"
    
    params = {
        "parent": parent,
        "section": "cash-flow",
        "consolidated": "",  # Empty string acts as the boolean flag in Screener's API
    }

    try:
        # Perform the GET request with a timeout to prevent hanging
        resp = session.get(url, params=params, timeout=20)

        if resp.status_code == 200:
            return resp.text
        
        # If the API returns an error (like 404 or 429), log it as a warning
        log.warning(f"Schedule API returned HTTP {resp.status_code} for company_id: {company_id}")
        return None

    except requests.exceptions.RequestException as e:
        # Handles timeouts, connection errors, and DNS issues
        log.error(f"Network error while fetching schedule for {company_id}: {e}")
        return None
    except Exception as e:
        # Cat%%hes any other unexpected errors (like JSON decoding or logic errors)
        log.error(f"Unexpected error fetching schedule for {company_id}: {e}")
        return None


def parse_cash_flow_from_html(html: str, symbol: str, session) -> pd.DataFrame | None:
    """
    Parses Cash Flow from HTML, supplements Capex from API, 
    and derives True Free Cash Flow using vectorized operations.
    """
    soup = BeautifulSoup(html, "lxml")
    section = soup.find("section", {"id": "cash-flow"})

    if not section:
        log.debug("%s: section #cash-flow not found in HTML", symbol)
        return None

    table = section.find("table")
    if not table:
        log.debug("%s: no table inside #cash-flow", symbol)
        return None

    # 1. Parse the primary table from HTML
    records = _parse_cf_table(table, symbol)
    if not records:
        return None

    df = pd.DataFrame(records)

    # 2. Extract Company ID for API call
    # We look for the ID in the HTML attributes
    m = re.search(r'data-company-id="(\d+)"', html)
    company_id = m.group(1) if m else None

    # 3. Supplement with API Capex data if available
    if company_id:
        try:
            # Call the schedule API for Investing activity
            investing_html = fetch_cf_schedule(session, company_id, "Cash from Investing Activity")
            
            if investing_html:
                investing_json = json.loads(investing_html)
                # Use .get() with an empty dict to prevent crashes
                capex_data = investing_json.get("Fixed assets purchased", {})

                new_capex_records = []
                for period, raw_val in capex_data.items():
                    val = _to_float(raw_val)
                    if val is not None:
                        new_capex_records.append({
                            "symbol": symbol,
                            "period": period,
                            "freq": "annual",
                            "metric": "Fixed Asset Purchased",
                            "value": -abs(val),  # Store as outflow (negative)
                        })
                
                if new_capex_records:
                    new_df = pd.DataFrame(new_capex_records)
                    df = pd.concat([df, new_df], ignore_index=True)
                    # Remove duplicates in case API and HTML overlap
                    df = df.drop_duplicates(subset=["symbol", "period", "metric"])


            operating_html = fetch_cf_schedule(session,company_id,"Cash from Operating Activity")
            if operating_html:
                operating_json = json.loads(operating_html)
                
                op_data = operating_json.get("Profit from operations", {})
                
                new_op_records = []
                for period, raw_val in op_data.items():

    # Skip Screener metadata row
                    if period == "setAttributes":
                        continue

                    # Skip nested dicts
                    if isinstance(raw_val, dict):
                        continue

                    val = _to_float(str(raw_val))

                    if val is not None:

                        new_op_records.append({
                            "symbol": symbol,
                            "period": period,
                            "freq": "annual",
                            "metric": "Profit from Operations",
                            "value": val,
                        })
                if new_op_records:
                    new_op_df = pd.DataFrame(new_op_records)
                    df = pd.concat([df, new_op_df], ignore_index=True)
                    df = df.drop_duplicates(subset=["symbol", "period", "metric"])
        
        except Exception as e:
            log.error(f"{symbol}: Capex API supplemental parsing failed: {e}")

    # 4. DERIVE TRUE FREE CASH FLOW (Vectorized - MUCH FASTER)
    # Instead of a loop, we pivot the data to perform math across columns
    try:
        # Pivot so metrics become columns: index=period, columns=metric
        pivot_df = df.pivot_table(
            index=["symbol", "period", "freq"], 
            columns="metric", 
            values="value"
        ).reset_index()

        # Ensure required columns exist before math
        if "CFO" in pivot_df.columns and "Fixed Asset Purchased" in pivot_df.columns:
            # Calculation: True FCF = CFO + Capex (since Capex is already negative)
            # Or: CFO - abs(Capex)
            pivot_df["True Free Cash Flow"] = pivot_df["CFO"] + pivot_df["Fixed Asset Purchased"]
            
            # Convert back from wide format to long format (the original structure)
            # We only want to add the NEW derived metric to our original df
            derived_df = pivot_df[["symbol", "period", "freq", "True Free Cash Flow"]].melt(
                id_vars=["symbol", "period", "freq"],
                value_name="value"
            )
            # Filter out rows where True FCF couldn't be calculated (NaN)
            derived_df = derived_df.dropna(subset=["value"])
            
            # Append to original dataframe
            df = pd.concat([df, derived_df], ignore_index=True)
            
    except Exception as e:
        log.error(f"{symbol}: Failed to derive True Free Cash Flow: {e}")

    # 5. Final Clean up
    df = df.drop_duplicates(subset=["symbol", "period", "metric"])
    return df.reset_index(drop=True)



def fetch_symbol(session: requests.Session,
                  symbol: str,
                  page_html: str | None = None, refresh_ca=True
                 ) -> tuple[pd.DataFrame | None, pd.DataFrame | None, pd.DataFrame | None, pd.DataFrame | None, dict]:
    
    snapshot  = {"symbol": symbol, "market_cap_cr": None, "ltp": None}
    sh_df, fin_df, cf_df, ca_df = None, None, None, None

    if page_html is None:
        # FIX: Prioritize the MAIN company page. 
        # The /consolidated/ sub-pages are often missing the #top-ratios section.
        urls = [
            # f"https://www.screener.in/company/{symbol}/", 
            f"https://www.screener.in/company/{symbol}/consolidated/#quarters",
        ]

        for url in urls:
            try:
                r = session.get(url, timeout=(10,30))
                if r.status_code == 200:
                    page_html = r.text
                    break
                elif r.status_code == 404:
                    continue 
            except Exception:
                continue

    if page_html:
        sh_df = parse_shareholding_page(page_html, symbol)
        snapshot = parse_snapshot(page_html, symbol)
        fin_df = parse_financials_from_html(page_html, symbol)
        cf_df = parse_cash_flow_from_html(page_html, symbol, session)
        ca_df = _parse_corporate_actions_html(page_html, symbol)

    # ... [Keep the rest of your existing CA refresh logic] ...
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
    log.info(f"✓ {symbol}: SH={rows_sh} | FIN={rows_fin} | CF={rows_cf} | CA={rows_ca} | LTP={snapshot['ltp']} | MCap={snapshot['market_cap_cr']}")
    
    return sh_df, fin_df, cf_df, ca_df, snapshot
# ─── MAIN LOOP ────────────────────────────────────────────────────────────────



def _is_cached(sh_path: Path, fin_path: Path) -> bool:
    """
    Ultra-fast check to see if files exist and contain data.
    Uses file metadata (size) instead of reading the entire file.
    """
    try:
        # 1. Check if both files exist
        if not sh_path.exists() or not fin_path.exists():
            return False

        # 2. Check if files are non-empty using os.path.getsize
        # getsize() is a metadata operation; it is nearly instantaneous.
        # This avoids the massive overhead of pd.read_parquet().
        if os.path.getsize(sh_path) > 0 and os.path.getsize(fin_path) > 0:
            return True
            
        return False

    except Exception:
        # If any OS error occurs, assume not cached
        return False


def _read_snapshot_from_cache(snap_path: Path, symbol: str) -> dict:
    """
    Optimized for single-lookup. 
    Returns pure Python types (None instead of NaN) to prevent JSON/Streamlit errors.
    """
    # Default return value
    blank = {"symbol": symbol, "market_cap_cr": None, "ltp": None}
    
    if not snap_path.exists():
        return blank

    try:
        # Load the file
        df = pd.read_parquet(snap_path)
        
        if df.empty or "symbol" not in df.columns:
            return blank

        # Filter for the symbol
        row = df[df["symbol"] == symbol]
        
        if row.empty:
            return blank

        # Extract values
        # We use .item() or float conversion to ensure we don't return 
        # numpy.float64 (which causes issues in some UI components)
        raw_mcap = row.iloc[0].get("market_cap_cr")
        raw_ltp = row.iloc[0].get("ltp")

        return {
            "symbol": symbol,
            "market_cap_cr": float(raw_mcap) if pd.notna(raw_mcap) else None,
            "ltp": float(raw_ltp) if pd.notna(raw_ltp) else None,
        }

    except Exception as e:
        # In a production app, you might want to log this error
        # log.error(f"Snapshot lookup error for {symbol}: {e}")
        return blank




def _rebuild_masters(symbols: list[str]) -> None:
    """
    High-performance rebuild of master files using Parallel I/O 
    and strict type enforcement.
    """
    
    # Define strict schema to prevent "Object" column corruption during concat
    SCHEMAS = {
        "sh":  {"symbol": "str", "quarter": "str", "category": "str", "pct": "float"},
        "fin": {"symbol": "str", "period": "str", "freq": "str", "metric": "str", "value": "float"},
        "cf":  {"symbol": "str", "period": "str", "freq": "str", "metric": "str", "value": "float"},
        "ca":  {"symbol": "str", "date": "str", "action_type": "str", "value": "str", "description": "str"},
    }

    # Mapping of directory to type-key
    DIR_MAP = [
        (OUT_DIR_SH, "sh", MASTER_CSV_SH, "Shareholding"),
        (OUT_DIR_FIN, "fin", MASTER_CSV_FIN, "Financials"),
        (OUT_DIR_CF, "cf", MASTER_CSV_CF, "Cash Flow"),
        (OUT_DIR_CA, "ca", MASTER_CSV_CA, "Corporate Actions"),
    ]

    def _read_task(task):
        """Worker function for threads: Reads and enforces schema."""
        path, type_key = task
        if not path.exists():
            return None
        try:
            df = pd.read_parquet(path)
            if df.empty:
                return None
            
            # CRITICAL: Enforce schema immediately to prevent concat errors
            for col, dtype in SCHEMAS[type_key].items():
                if col in df.columns:
                    if dtype == "float":
                        df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)
                    else:
                        df[col] = df[col].astype(dtype)
            return (type_key, df)
        except Exception as e:
            # log.error(f"Failed to read {path}: {e}") # Uncomment if you want detailed errors
            return None

    # 1. Prepare all tasks (Every symbol x Every category)
    all_tasks = []
    for sym in symbols:
        all_tasks.append((OUT_DIR_SH / f"shareholding_{sym}.parquet", "sh"))
        all_tasks.append((OUT_DIR_FIN / f"financials_{sym}.parquet", "fin"))
        all_tasks.append((OUT_DIR_CF / f"cashflow_{sym}.parquet", "cf"))
        all_tasks.append((OUT_DIR_CA / f"corporate_actions_{sym}.parquet", "ca"))

    # 2. Execute Parallel I/O
    log.info(f"🚀 Rebuilding masters using {len(all_tasks)} parallel tasks...")
    
    # Using 8 workers is usually the "sweet spot" for SSD I/O
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(_read_task, all_tasks))

    # 3. Group results by type
    buckets = {"sh": [], "fin": [], "cf": [], "ca": []}
    for res in results:
        if res:
            type_key, df = res
            buckets[type_key].append(df)

    # 4. Concatenate and Save
    for type_key, master_path, label in [(k, d[2], d[3]) for k, d in zip(buckets.keys(), DIR_MAP)]:
        bucket_list = buckets[type_key]
        if bucket_list:
            master_df = pd.concat(bucket_list, ignore_index=True)
            
            # Final Safety: Drop duplicates that might have crept in via overlapping scrapes
            if type_key == "sh":
                master_df = master_df.drop_duplicates(subset=["symbol", "quarter", "category"])
            elif type_key == "fin":
                master_df = master_df.drop_duplicates(subset=["symbol", "period", "metric"])
            elif type_key == "cf":
                master_df = master_df.drop_duplicates(subset=["symbol", "period", "metric"])
            elif type_key == "ca":
                master_df = master_df.drop_duplicates(subset=["symbol", "date", "action_type"])

            master_df.to_parquet(master_path, index=False)
            log.info(f"✅ {label} master rebuilt → {master_path} ({len(master_df)} rows)")
        else:
            log.warning(f"⚠️ No data found for {label} master.")



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
# def extract_latest_period_from_html(html: str):
    # """
    # Return the latest period string found in the quarterly-results table
    # (section#quarters thead) only.

    # Scoping to #quarters prevents shareholding table headers (which are
    # updated earlier than financial results) from triggering a false
    # re-fetch when financials for that quarter aren't declared yet.
    # """
    # if not html:
        # return None

    # soup = BeautifulSoup(html, "lxml")

    # # ── Only look inside the quarterly-results section ────────────────────
    # section = soup.find("section", {"id": "quarters"})
    # if not section:
        # return None

    # thead = section.find("thead")
    # if not thead:
        # return None

    # # Period strings are the <th> cells in the header row
    # header_row = thead.find("tr")
    # if not header_row:
        # return None

    # quarter_map = {"Mar": 3, "Jun": 6, "Sep": 9, "Dec": 12}
    # parsed = []

    # for th in header_row.find_all(["th", "td"]):
        # text = th.get_text(" ", strip=True)
        # m = re.match(r'(Mar|Jun|Sep|Dec)\s+(20\d{2})', text, re.IGNORECASE)
        # if m:
            # q, year = m.group(1).title(), int(m.group(2))
            # if q in quarter_map:
                # parsed.append((year, quarter_map[q], text.strip()))

    # if not parsed:
        # return None

    # parsed.sort()
    # return parsed[-1][2]
# ─── UPDATED DATE DETECTION (FIXES BUG #2) ─────────────────────────────────────

# 

def get_latest_period_from_fin_df(fin_df):

    if fin_df is None or fin_df.empty:
        return None

    quarter_map = {
        "Mar": 3,
        "Jun": 6,
        "Sep": 9,
        "Dec": 12,
    }

    parsed = []

    for p in fin_df["period"].dropna().astype(str).unique():

        m = re.match(
            r"(Mar|Jun|Sep|Dec)\s+(\d{4})",
            p,
            flags=re.I,
        )

        if not m:
            continue

        q = m.group(1).title()
        y = int(m.group(2))

        parsed.append(
            (y, quarter_map[q], f"{q} {y}")
        )

    if not parsed:
        return None

    parsed.sort()

    return parsed[-1][2]


def get_local_latest_period(file_path: Path):
    """
    Robustly finds the latest period (e.g., 'Mar 2024') from a parquet file.
    Handles: 'Mar 2024', 'Mar 24', 'Mar-2024', 'Mar 2024 (Consolidated)'
    """
    if not file_path.exists():
        return None

    try:
        df = pd.read_parquet(file_path)
        if df.empty or "period" not in df.columns:
            return None

        # 1. Get unique periods and ensure they are strings
        periods = df["period"].dropna().astype(str).unique()
        if len(periods) == 0:
            return None

        quarter_map = {
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
            'q1': 3, 'q2': 6, 'q3': 9, 'q4': 12
        }

        parsed = []
        
        # 2. Use Regex for robust parsing
        # This pattern looks for: (Letters) followed by (Space/Dash) followed by (2 or 4 digits)
        pattern = re.compile(r'([a-zA-Z]+)[\s\-_]+(\d{2,4})')

        for p in periods:
            match = pattern.search(p)
            if match:
                month_str = match.group(1).lower()
                year_raw = match.group(2)
                
                if month_str in quarter_map:
                    # Convert year: '24' -> 2024, '2024' -> 2024
                    year = int(year_raw)
                    if year < 100:
                        year += 2000
                    
                    # Store as (Year, Month_Num, Original_String) for perfect sorting
                    parsed.append((year, quarter_map[month_str], p))

        if not parsed:
            return None

        # 3. Sort chronologically and return the last one
        parsed.sort()
        return parsed[-1][2]

    except Exception as e:
        # Use a real logger here in your main app, but for now:
        # print(f"Error reading period from {file_path}: {e}")
        return None
def run(session_id: str = SESSION_ID, symbols: list[str] | None = None):
    """
    OPTIMIZED ONE-PASS STRATEGY
    ──────────────────────────
    1. Scans symbols to see if they are stale or missing.
    2. Fetches HTML ONLY ONCE per symbol.
    3. Uses the ALREADY FETCHED HTML to both check the period AND parse data.
    4. Eliminates the 'Double Download' bug, making it ~2x faster.
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

    # This will now store tuples of (symbol, html_content)
    # This is the key to the "One-Pass" speedup
    to_fetch_with_html = [] 
    session = make_session(session_id)

    log.info(f"🔍 Scanning {total} symbols for updates...")

    # ── PHASE 1: DETECTION ──────────────────────────────────────────────────────
    
    for idx, sym in enumerate(symbols, start=1):

        if idx % 25 == 0:
            log.info(
                f"Scan progress: {idx}/{len(symbols)}"
    )
        sh_path  = OUT_DIR_SH  / f"shareholding_{sym}.parquet"
        fin_path = OUT_DIR_FIN / f"financials_{sym}.parquet"

        needs_refresh = False

        # Check if we have local data
        if _is_cached(sh_path, fin_path):
            # Check if the file itself is too old based on timestamp
            if not (force_refresh or _needs_staleness_check(fin_path)):
                cached_count += 1
                continue
            
            try:
                local_latest = get_local_latest_period(fin_path)
                
                # Fetch HTML once to check the period
                html = fetch_html(session, sym)
                if not html:
                    log.warning(f"{sym}: Could not fetch HTML for period check.")
                    cached_count += 1 # Treat as cached to avoid infinite loop if blocked
                    continue

                web_latest = extract_latest_period_from_html(html)
                if not html:
                    cached_count += 1
                    continue

                fin_df = parse_financials_from_html(html,sym,)

                # web_latest = get_latest_period_from_fin_df(fin_df)                )

                if web_latest is not None and web_latest != local_latest:
                    log.info(f"{sym}: New data detected | Local={local_latest} | Web={web_latest}")
                    needs_refresh = True
                elif web_latest is None:
                    log.warning(f"{sym}: Could not detect latest web period")
                    cached_count += 1
                    continue
                else:
                    cached_count += 1
                    continue
            except Exception as e:
                log.warning(f"{sym}: Period detection failed → {e}")
                needs_refresh = True
        else:
            needs_refresh = True

        if needs_refresh:
            # IMPORTANT: We fetch the HTML here and save it in our list
            # This prevents downloading it a second time in Phase 2
            html = fetch_html(session, sym)
            if html:
                to_fetch_with_html.append((sym, html))
            else:
                log.error(f"{sym}: Failed to fetch HTML during detection phase.")

    log.info(f"Total: {total} | Cached: {cached_count} | Need fetching: {len(to_fetch_with_html)}")

    # ── PHASE 2: ACTUAL FETCHING (USING PRE-DOWNLOADED HTML) ───────────────────
    if to_fetch_with_html:
        # Initialize snapshot list for upsert
        snap_list = []
        if SNAPSHOT_FILE.exists():
            try:
                snap_df = pd.read_parquet(SNAPSHOT_FILE)
                # Keep snapshots for stocks NOT being updated
                to_update_syms = [item[0] for item in to_fetch_with_html]
                snap_list = snap_df[~snap_df["symbol"].isin(to_update_syms)].to_dict('records')
            except Exception:
                pass

        for i, (sym, html) in enumerate(to_fetch_with_html, 1):
            log.info(f"[fetch {i}/{len(to_fetch_with_html)} | total {cached_count + i}/{total}] {sym}...")

            sh_path  = OUT_DIR_SH  / f"shareholding_{sym}.parquet"
            fin_path = OUT_DIR_FIN / f"financials_{sym}.parquet"
            cf_path  = OUT_DIR_CF  / f"cashflow_{sym}.parquet"
            ca_path  = OUT_DIR_CA  / f"corporate_actions_{sym}.parquet"

            # FIX: We pass page_html=None. 
            # This FORCES fetch_symbol to perform a fresh, authenticated 
            # download in Phase 2, bypassing the potentially "Guest" HTML from Phase 1.
            sh_df, fin_df, cf_df, ca_df, snapshot = fetch_symbol(
                session,
                sym,
                page_html=html, # <--- CHANGE THIS FROM 'html' TO 'None'
                refresh_ca=force_refresh
            )
            
            # Save per-stock files using upsert to prevent data loss
            if sh_df  is not None: _upsert_parquet(sh_path,  sh_df,  ["symbol","quarter","category"])
            if fin_df is not None: _upsert_parquet(fin_path, fin_df, ["symbol","period","metric"])
            if cf_df  is not None: _upsert_parquet(cf_path,  cf_df,  ["symbol","period","metric"])
            if ca_df  is not None: _upsert_parquet(ca_path,  ca_df,  ["symbol","date","action_type"])
            
            snap_list.append(snapshot)
            fetched += 1
            
            # Reduced sleep slightly since we are already respecting rate limits 
            # by not double-downloading.
            time.sleep(random.uniform(2, 4))

        # Batch write snapshots
        if snap_list:
            pd.DataFrame(snap_list).to_parquet(SNAPSHOT_FILE, index=False)
            log.info(f"Snapshot saved → {SNAPSHOT_FILE}")

    else:
        log.info("All symbols already cached — no HTTP requests needed.")

    # Rebuild masters
    log.info("Rebuilding master files...")
    _rebuild_masters(symbols)

    log.info(f"\n✅ Done! Fetched: {fetched} | Cached: {cached_count} | Total: {total}")

    # Helper to read master files
    def _read_master(path: Path) -> pd.DataFrame:
        try: return pd.read_parquet(path) if path.exists() else pd.DataFrame()
        except: return pd.DataFrame()

    return (
        _read_master(MASTER_CSV_SH),
        _read_master(MASTER_CSV_FIN),
        _read_master(MASTER_CSV_CF),
        _read_master(MASTER_CSV_CA),
        _read_master(SNAPSHOT_FILE),
    )

# ─── DEBUG HELPER ─────────────────────────────────────────────────────────────
from bs4 import BeautifulSoup
import re

def extract_latest_period_from_html(html):
    """
    Fast detection of latest quarterly period without
    building the entire financial dataframe.
    """

    soup = BeautifulSoup(html, "lxml")

    quarters = soup.select_one("#quarters table")

    if not quarters:
        return None

    headers = [
        th.get_text(" ", strip=True)
        for th in quarters.select("thead th")
    ]

    periods = []

    for h in headers:
        if re.match(r"^(Mar|Jun|Sep|Dec)\s+\d{4}$", h):
            periods.append(h)

    return periods[-1] if periods else None
def debug_snapshot(symbol: str, session_id: str = SESSION_ID):
    """
    REFACTORED DEBUGGER:
    Fetches one stock and prints ALL #top-ratios labels + values.
    Now uses the working HTML parsing method for financials.
    """
    session = make_session(session_id)
    # url     = f"https://www.screener.in/company/{symbol}/"
    url = f"https://www.screener.in/company/{symbol}/consolidated/#quarters",

    
    log.info(f"Running debug for {symbol}...")
    r = session.get(url, timeout=20)
    
    if r.status_code != 200:
        print(f"❌ HTTP Error: {r.status_code}")
        return

    html = r.text
    soup = BeautifulSoup(html, "lxml")

    print(f"\n{'='*50}")
    print(f"🔍 DEBUGGING: {symbol}")
    print(f"{'='*50}")

    # 1. Print Top Ratios (The "Snapshot" section)
    # print(f"\n--- #top-ratios for {symbol} ---")
    found_ratios = False
    for li in soup.select("#top-ratios li"):
        name = li.find("span", class_="name")
        num  = li.find("span", class_="number")
        sub  = li.find("span", class_="sub")
        if name and num:
            found_ratios = True
            print(f"  {name.get_text(strip=True):30s} | {num.get_text(strip=True):12s} | {sub.get_text(strip=True) if sub else ''}")
    
    if not found_ratios:
        print("  (No ratios found in #top-ratios)")

    # 2. Print Parsed Snapshot (LTP / MCap)
    snap = parse_snapshot(html, symbol)
    print(f"\n--- Parsed Snapshot ---")
    print(f"  LTP      : {snap['ltp']}")
    print(f"  MCap(Cr) : {snap['market_cap_cr']}")

    # 3. Print Financials (USING THE NEW WORKING PARSER)
    print(f"\n--- Financials (HTML Parsed) ---")
    fin = parse_financials_from_html(html, symbol)
    
    if fin is not None and not fin.empty:
        print(fin.to_string(index=False))
    else:
        print("  (No financials parsed from HTML)")

    print(f"\n{'='*50}")
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
        # url  = "https://www.screener.in/company/%s/" % sym
        url = f"https://www.screener.in/company/%s/consolidated/#quarters" % sym
        
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
            df_cf = parse_cash_flow_from_html(r.text, sym,sess)
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
        # sh_master, fin_master, cf_master, ca_master, snap = run(symbols=["LTF"])
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