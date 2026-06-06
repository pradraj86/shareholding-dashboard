"""
deals_fetcher.py
────────────────
Fetches Insider Trading, Bulk Deals, and Block Deals from NSE India
for every stock in your TradingView watchlist.

Data Sources
────────────
• Insider Trading  : NSE SAST/SEBI disclosures via
                     https://www.nseindia.com/api/corporates-pit?symbol=<SYM>&issuerCode=<ISIN>
                     + company page HTML on NSE for promoter/insider trades
• Bulk Deals       : https://www.nseindia.com/api/snapshot-capital-market-largedeal?category=bulk_deals
• Block Deals      : https://www.nseindia.com/api/snapshot-capital-market-largedeal?category=block_deals
• Historical       : https://www.nseindia.com/api/historical/bulk-deals?symbol=<SYM>
                     https://www.nseindia.com/api/historical/block-deals?symbol=<SYM>

Output
──────
  data/bulk_deals_all.csv      symbol | date | client | deal_type | buy_sell | qty | price | exchange
  data/block_deals_all.csv     same schema
  data/insider_trading_all.csv symbol | date | person | type_of_security | qty | price | mode | type (buy/sell)
  data/deals_per_stock/        one CSV per stock (all three types combined)

Usage
─────
  pip install requests pandas beautifulsoup4 lxml

  python deals_fetcher.py                  # all watchlist stocks
  python deals_fetcher.py --symbol INFY    # single stock test
  python deals_fetcher.py --days 365       # look back 365 days (default 180)
"""

import argparse
import json
import logging
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

# ─── CONFIGURATION ────────────────────────────────────────────────────────────

WATCHLIST_FILE = Path("watchlist.txt")
OUT_DIR        = Path("data")
OUT_BULK       = OUT_DIR / "bulk_deals_all.csv"
OUT_BLOCK      = OUT_DIR / "block_deals_all.csv"
OUT_INSIDER    = OUT_DIR / "insider_trading_all.csv"
OUT_PER_STOCK  = OUT_DIR / "deals_per_stock"

DEFAULT_DAYS   = 180   # look-back window
DELAY          = 1.0   # seconds between requests
MAX_RETRIES    = 3

KNOWN_EXCHANGES = {"NSE", "BSE", "NIFTY"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ─── WATCHLIST ────────────────────────────────────────────────────────────────

def parse_watchlist(filepath: Path = WATCHLIST_FILE) -> list[str]:
    if not filepath.exists():
        log.warning(f"Watchlist not found at {filepath}.")
        return []
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


# ─── NSE SESSION ─────────────────────────────────────────────────────────────

class NseSession:
    """
    NSE requires a valid browser session (cookies from the homepage) before
    hitting any API endpoint. We fetch the homepage once to get cookies, then
    reuse the session.
    """
    BASE = "https://www.nseindia.com"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept":           "application/json, text/plain, */*",
            "Accept-Language":  "en-IN,en;q=0.9",
            "Accept-Encoding":  "gzip, deflate, br",
            "Referer":          "https://www.nseindia.com/",
            "X-Requested-With": "XMLHttpRequest",
        })
        self._init_cookies()

    def _init_cookies(self):
        """Prime the session with homepage cookies NSE needs."""
        try:
            r = self.session.get(self.BASE, timeout=15)
            log.debug(f"NSE homepage: HTTP {r.status_code}")
            time.sleep(1)
            # Also hit the markets page which sets additional cookies
            self.session.get(f"{self.BASE}/market-data/bulk-deal-watch", timeout=15)
            time.sleep(0.5)
        except Exception as e:
            log.warning(f"Could not prime NSE session: {e}")

    def get_json(self, path: str, params: dict | None = None) -> dict | list | None:
        url = f"{self.BASE}{path}"
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                r = self.session.get(url, params=params, timeout=20)
                if r.status_code == 200:
                    return r.json()
                elif r.status_code == 401:
                    log.debug(f"401 on {url} — refreshing session cookies")
                    self._init_cookies()
                    time.sleep(2)
                else:
                    log.debug(f"HTTP {r.status_code} for {url} (attempt {attempt})")
                    time.sleep(1.5)
            except (requests.RequestException, json.JSONDecodeError) as e:
                log.debug(f"Request error (attempt {attempt}): {e}")
                time.sleep(2)
        return None


# ─── BULK DEALS ───────────────────────────────────────────────────────────────

# NSE column names → our canonical names
BULK_COL_MAP = {
    "symbol":         "symbol",
    "Symbol":         "symbol",
    "clientName":     "client",
    "Client Name":    "client",
    "dealType":       "deal_type",
    "BD_DT_DATE":     "date",
    "mTIMESTAMP":     "date",
    "BD_SYMBOL":      "symbol",
    "BD_CLIENT_NAME": "client",
    "BD_BUY_SELL":    "buy_sell",
    "buyOrSell":      "buy_sell",
    "BD_QTY_TRD":     "qty",
    "quantity":       "qty",
    "BD_TP_WATP":     "price",
    "tradePrice":     "price",
    "exchange":       "exchange",
}


def _normalise_deals(raw: list[dict], symbol: str, deal_type: str) -> list[dict]:
    """Flatten NSE JSON rows into our schema."""
    records = []
    for row in raw:
        rec = {
            "symbol":    symbol,
            "deal_type": deal_type,
            "date":      None,
            "client":    None,
            "buy_sell":  None,
            "qty":       None,
            "price":     None,
            "exchange":  "NSE",
        }
        for src_key, tgt_key in BULK_COL_MAP.items():
            if src_key in row and row[src_key] not in (None, "", "NA"):
                rec[tgt_key] = row[src_key]

        # Also try unknown key names generically
        for k, v in row.items():
            k_lower = k.lower()
            if rec["date"]     is None and "date"   in k_lower: rec["date"]    = v
            if rec["client"]   is None and "client" in k_lower: rec["client"]  = v
            if rec["qty"]      is None and ("qty" in k_lower or "quant" in k_lower): rec["qty"] = v
            if rec["price"]    is None and "price"  in k_lower: rec["price"]   = v
            if rec["buy_sell"] is None and ("buy" in k_lower or "sell" in k_lower): rec["buy_sell"] = v

        if rec["symbol"] and rec["date"]:
            records.append(rec)
    return records


def fetch_bulk_deals_today(nse: NseSession) -> list[dict]:
    """Fetch today's bulk deals from NSE snapshot API."""
    data = nse.get_json("/api/snapshot-capital-market-largedeal", {"category": "bulk_deals"})
    if not data:
        return []
    rows = data if isinstance(data, list) else data.get("data", data.get("bulk_deals", []))
    # Each row has the symbol embedded; we extract all at once
    records = []
    for row in rows:
        sym = (row.get("symbol") or row.get("Symbol") or row.get("BD_SYMBOL") or "").upper().strip()
        if sym:
            rec = _normalise_deals([row], sym, "Bulk")[0]
            records.append(rec)
    log.info(f"Today's bulk deals: {len(records)} records")
    return records


def fetch_block_deals_today(nse: NseSession) -> list[dict]:
    """Fetch today's block deals from NSE snapshot API."""
    data = nse.get_json("/api/snapshot-capital-market-largedeal", {"category": "block_deals"})
    if not data:
        return []
    rows = data if isinstance(data, list) else data.get("data", data.get("block_deals", []))
    records = []
    for row in rows:
        sym = (row.get("symbol") or row.get("Symbol") or row.get("BD_SYMBOL") or "").upper().strip()
        if sym:
            rec = _normalise_deals([row], sym, "Block")[0]
            records.append(rec)
    log.info(f"Today's block deals: {len(records)} records")
    return records


def fetch_bulk_deals_historical(nse: NseSession, symbol: str,
                                 from_date: date, to_date: date) -> list[dict]:
    """Fetch historical bulk deals for a symbol."""
    params = {
        "symbol":   symbol,
        "from":     from_date.strftime("%d-%m-%Y"),
        "to":       to_date.strftime("%d-%m-%Y"),
        "dataType": "bulk_deals",
    }
    data = nse.get_json("/api/historical/bulk-deals", params)
    if not data:
        return []
    rows = data if isinstance(data, list) else data.get("data", [])
    return _normalise_deals(rows, symbol, "Bulk")


def fetch_block_deals_historical(nse: NseSession, symbol: str,
                                  from_date: date, to_date: date) -> list[dict]:
    """Fetch historical block deals for a symbol."""
    params = {
        "symbol":   symbol,
        "from":     from_date.strftime("%d-%m-%Y"),
        "to":       to_date.strftime("%d-%m-%Y"),
        "dataType": "block_deals",
    }
    data = nse.get_json("/api/historical/block-deals", params)
    if not data:
        return []
    rows = data if isinstance(data, list) else data.get("data", [])
    return _normalise_deals(rows, symbol, "Block")


# ─── INSIDER TRADING ─────────────────────────────────────────────────────────

INSIDER_COL_MAP = {
    # NSE PIT (Prohibition of Insider Trading) API keys
    "symbol":                    "symbol",
    "acqName":                   "person",
    "acquisitionName":           "person",
    "personName":                "person",
    "acqfromDt":                 "date_from",
    "acqtoDt":                   "date_to",
    "secAcq":                    "qty",
    "secType":                   "type_of_security",
    "befAcqSharesNo":            "shares_before",
    "afterAcqSharesNo":          "shares_after",
    "befAcqSharesPer":           "pct_before",
    "afterAcqSharesPer":         "pct_after",
    "acqMode":                   "mode",
    "acqType":                   "transaction_type",
    "tdpTransactionType":        "transaction_type",
    "secVal":                    "value",
}


def fetch_insider_trading_nse(nse: NseSession, symbol: str) -> list[dict]:
    """
    Fetch insider trading (PIT disclosures) for a symbol from NSE.
    NSE endpoint: /api/corporates-pit?symbol=<SYM>&issuerCode=<ISIN>
    We first get the ISIN from the equity info endpoint.
    """
    # Step 1: Get ISIN for the symbol
    info = nse.get_json(f"/api/quote-equity?symbol={symbol}")
    isin = None
    if info:
        isin = (info.get("info", {}).get("isin")
                or info.get("metadata", {}).get("isin")
                or info.get("isin"))
    time.sleep(0.4)

    # Step 2: Fetch PIT data
    params = {"symbol": symbol}
    if isin:
        params["issuerCode"] = isin

    data = nse.get_json("/api/corporates-pit", params)
    if not data:
        return []

    rows = data if isinstance(data, list) else data.get("data", data.get("pit", []))

    records = []
    for row in rows:
        rec = {
            "symbol":           symbol,
            "date":             None,
            "person":           None,
            "type_of_security": None,
            "qty":              None,
            "value":            None,
            "shares_before":    None,
            "shares_after":     None,
            "pct_before":       None,
            "pct_after":        None,
            "mode":             None,
            "transaction_type": None,
        }
        for src_key, tgt_key in INSIDER_COL_MAP.items():
            if src_key in row and row[src_key] not in (None, "", "NA", "-"):
                rec[tgt_key] = row[src_key]

        # Use acqfromDt as the primary date
        date_raw = (row.get("acqfromDt") or row.get("acqtoDt")
                    or row.get("date") or row.get("dateOfTransaction", ""))
        rec["date"] = date_raw

        if rec["person"] or rec["qty"]:
            records.append(rec)

    log.debug(f"  {symbol}: {len(records)} insider trading records from NSE PIT")
    return records


def parse_insider_from_screener_html(html: str, symbol: str) -> list[dict]:
    """
    Fallback: parse insider/promoter transaction table from Screener.in HTML.
    Screener has a section #insider (or similar) with promoter buying/selling.
    """
    soup = BeautifulSoup(html, "lxml")
    records = []

    # Try known Screener section IDs for insider activity
    for section_id in ("insider", "promoter-transactions", "recent-transactions",
                       "insider-trading", "promoterTransactions"):
        section = soup.find("section", {"id": section_id})
        if section:
            table = section.find("table")
            if table:
                records.extend(_parse_insider_table(table, symbol, f"Screener #{section_id}"))
                if records:
                    break

    # Also try any table whose headers mention promoter/insider buy/sell
    if not records:
        for tbl in soup.find_all("table"):
            header_text = " ".join(
                th.get_text(" ", strip=True).lower()
                for th in tbl.find_all(["th", "td"])[:10]
            )
            if any(kw in header_text for kw in
                   ("promoter", "insider", "acquirer", "acq", "transaction", "pit")):
                rows_found = _parse_insider_table(tbl, symbol, "Screener generic")
                if rows_found:
                    records.extend(rows_found)
                    break

    return records


def _parse_insider_table(table, symbol: str, source: str) -> list[dict]:
    """Parse a single insider-trading HTML table."""
    thead = table.find("thead")
    if thead:
        headers = [th.get_text(" ", strip=True) for th in thead.find_all(["th", "td"])]
    else:
        rows = table.find_all("tr")
        if not rows:
            return []
        headers = [td.get_text(" ", strip=True) for td in rows[0].find_all(["th", "td"])]

    hl = [h.lower() for h in headers]

    def col(*kws):
        for kw in kws:
            for i, h in enumerate(hl):
                if kw in h:
                    return i
        return None

    date_col   = col("date", "dt")
    person_col = col("name", "person", "acquir", "promoter")
    type_col   = col("type", "security")
    qty_col    = col("qty", "quant", "shares")
    price_col  = col("price", "rate", "value")
    mode_col   = col("mode", "transact")
    action_col = col("buy", "sell", "action")

    records = []
    tbody = table.find("tbody") or table
    for row in tbody.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in row.find_all(["td", "th"])]
        if len(cells) < 2:
            continue

        def _g(idx):
            return cells[idx].strip() if idx is not None and idx < len(cells) else None

        date_raw = _g(date_col)
        person   = _g(person_col)
        qty_raw  = _g(qty_col)
        price_raw = _g(price_col)

        if not (date_raw or person or qty_raw):
            continue

        # Determine buy/sell
        action = _g(action_col) or _g(mode_col) or ""
        if "buy" in action.lower() or "acqui" in action.lower() or "purchase" in action.lower():
            txn_type = "Buy"
        elif "sell" in action.lower() or "disp" in action.lower():
            txn_type = "Sell"
        else:
            txn_type = action or "—"

        # Clean qty / price
        def _to_num(raw):
            if not raw:
                return None
            raw = raw.replace(",", "").replace("₹", "").strip()
            try:
                return float(raw)
            except ValueError:
                return None

        records.append({
            "symbol":           symbol,
            "date":             date_raw,
            "person":           person,
            "type_of_security": _g(type_col) or "Equity",
            "qty":              _to_num(qty_raw),
            "value":            _to_num(price_raw),
            "shares_before":    None,
            "shares_after":     None,
            "pct_before":       None,
            "pct_after":        None,
            "mode":             _g(mode_col),
            "transaction_type": txn_type,
            "source":           source,
        })

    return records


# ─── COMBINED PER-SYMBOL FETCH ────────────────────────────────────────────────

def fetch_all_for_symbol(
    nse: NseSession,
    symbol: str,
    from_date: date,
    to_date: date,
    screener_html: str | None = None,
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Returns (bulk_records, block_records, insider_records) for one symbol.
    """
    # Bulk deals
    bulk = fetch_bulk_deals_historical(nse, symbol, from_date, to_date)
    time.sleep(DELAY)

    # Block deals
    block = fetch_block_deals_historical(nse, symbol, from_date, to_date)
    time.sleep(DELAY)

    # Insider trading from NSE PIT
    insider = fetch_insider_trading_nse(nse, symbol)
    time.sleep(DELAY)

    # Supplement insider data from Screener HTML if provided
    if screener_html and not insider:
        screener_insider = parse_insider_from_screener_html(screener_html, symbol)
        if screener_insider:
            log.debug(f"  {symbol}: {len(screener_insider)} insider records from Screener fallback")
            insider = screener_insider

    log.info(
        f"✓ {symbol}: Bulk={len(bulk)} | Block={len(block)} | Insider={len(insider)}"
    )
    return bulk, block, insider


# ─── CLEAN & SAVE ─────────────────────────────────────────────────────────────

def _clean_deals(records: list[dict], deal_type: str) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    df["deal_type"] = deal_type
    df["date"]      = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
    for col in ("qty", "price"):
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",", "").str.strip(),
                errors="coerce"
            )
    df.dropna(subset=["date"], inplace=True)
    df.drop_duplicates(subset=["symbol","date","client","qty","price"], inplace=True)
    df.sort_values("date", ascending=False, inplace=True)
    return df.reset_index(drop=True)


def _clean_insider(records: list[dict]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
    for col in ("qty", "value", "pct_before", "pct_after"):
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",", "").str.replace("%","").strip(),
                errors="coerce"
            )
    df.dropna(subset=["date"], inplace=True)
    df.drop_duplicates(
        subset=[c for c in ["symbol","date","person","qty"] if c in df.columns],
        inplace=True
    )
    df.sort_values("date", ascending=False, inplace=True)
    return df.reset_index(drop=True)


def merge_and_save(df_new: pd.DataFrame, path: Path,
                   dedup_cols: list[str]) -> pd.DataFrame:
    """Merge with existing CSV, dedup, save."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not df_new.empty:
        try:
            existing = pd.read_csv(path, parse_dates=["date"])
            combined = pd.concat([existing, df_new], ignore_index=True)
            valid_dedup = [c for c in dedup_cols if c in combined.columns]
            combined.drop_duplicates(subset=valid_dedup, keep="last", inplace=True)
        except Exception:
            combined = df_new
    else:
        combined = df_new

    if not combined.empty:
        combined.sort_values("date", ascending=False, inplace=True)
        combined.to_csv(path, index=False)
        log.info(f"Saved → {path}  ({len(combined)} rows)")
    return combined


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def run(symbols: list[str] | None = None, days: int = DEFAULT_DAYS):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PER_STOCK.mkdir(parents=True, exist_ok=True)

    if symbols is None:
        symbols = parse_watchlist()
    if not symbols:
        log.error("No symbols to process.")
        return

    to_date   = date.today()
    from_date = to_date - timedelta(days=days)

    log.info(f"Fetching deals for {len(symbols)} symbols "
             f"from {from_date} to {to_date}")

    nse = NseSession()

    # Also fetch today's market-wide bulk+block deals (no symbol filter needed)
    log.info("Fetching today's market-wide bulk/block deals…")
    today_bulk  = fetch_bulk_deals_today(nse)
    today_block = fetch_block_deals_today(nse)
    time.sleep(DELAY)

    all_bulk, all_block, all_insider = (
        list(today_bulk),
        list(today_block),
        [],
    )

    for i, sym in enumerate(symbols, 1):
        log.info(f"[{i}/{len(symbols)}] {sym}")
        bulk, block, insider = fetch_all_for_symbol(
            nse, sym, from_date, to_date
        )
        all_bulk.extend(bulk)
        all_block.extend(block)
        all_insider.extend(insider)
        time.sleep(DELAY)

    # Clean
    df_bulk    = _clean_deals(all_bulk,  "Bulk")
    df_block   = _clean_deals(all_block, "Block")
    df_insider = _clean_insider(all_insider)

    # Save masters
    merge_and_save(df_bulk,    OUT_BULK,    ["symbol","date","client","qty","price"])
    merge_and_save(df_block,   OUT_BLOCK,   ["symbol","date","client","qty","price"])
    merge_and_save(df_insider, OUT_INSIDER, ["symbol","date","person","qty"])

    # Per-stock files
    all_deals = []
    if not df_bulk.empty:
        all_deals.append(df_bulk)
    if not df_block.empty:
        all_deals.append(df_block)

    if all_deals:
        df_all = pd.concat(all_deals, ignore_index=True)
        for sym in df_all["symbol"].unique():
            sym_deals = df_all[df_all["symbol"] == sym]
            sym_deals.to_csv(OUT_PER_STOCK / f"deals_{sym}.csv", index=False)

    if not df_insider.empty:
        for sym in df_insider["symbol"].unique():
            sym_ins = df_insider[df_insider["symbol"] == sym]
            sym_ins.to_csv(OUT_PER_STOCK / f"insider_{sym}.csv", index=False)

    log.info(
        f"\n✅ Done — Bulk: {len(df_bulk)} rows | "
        f"Block: {len(df_block)} rows | "
        f"Insider: {len(df_insider)} rows"
    )
    return df_bulk, df_block, df_insider


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch NSE bulk/block/insider trading data")
    parser.add_argument("--symbol", help="Single symbol to test")
    parser.add_argument("--days",   type=int, default=DEFAULT_DAYS,
                        help=f"Look-back days (default {DEFAULT_DAYS})")
    args = parser.parse_args()

    if args.symbol:
        syms = [args.symbol.upper()]
    else:
        syms = None

    run(symbols=syms, days=args.days)