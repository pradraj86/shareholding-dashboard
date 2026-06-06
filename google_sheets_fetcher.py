"""
google_sheets_fetcher.py
────────────────────────
Fetches TradingView alerts saved in a Google Sheet and stores them locally
as  data/tv_alerts.csv  for use by the Streamlit dashboard.

Google Sheet columns expected
─────────────────────────────
  Date        – alert trigger time  e.g. "08/05/2026 14:45:18"
  Ticker      – NSE symbol          e.g. "AADHARHFC"
  Price       – float               e.g. 505
  Column 1    – bar/candle time     e.g. "2026-05-04T03:45:00Z"
  Alert Type  – string              e.g. "Near Monthly ITH"

Setup (one-time)
────────────────
1. Go to https://console.cloud.google.com/
2. Create a project → enable "Google Sheets API"
3. IAM & Admin → Service Accounts → Create → download JSON key
4. Share your Google Sheet with the service account email
   (the "client_email" field in the JSON key) — Viewer access is enough.
5. Put the JSON key file path in SERVICE_ACCOUNT_JSON below (or pass via env).
6. Paste your Sheet ID in SHEET_ID below.

Usage
─────
  pip install google-auth google-auth-httplib2 google-api-python-client pandas

  python google_sheets_fetcher.py              # fetch & save
  python google_sheets_fetcher.py --tail 20    # print last 20 rows after fetch
"""

import argparse
import logging
import os
from datetime import datetime
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(stream=open(1, 'w', encoding='utf-8', closefd=False)),
    ]

)

# ─── CONFIGURATION ────────────────────────────────────────────────────────────

# Path to your downloaded service-account JSON key file.
# Can also be set via env var:  GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/key.json
SERVICE_ACCOUNT_JSON: str = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_JSON",
    "service_account.json",   # ← default: same directory as this script
)

# The long ID in your Google Sheet URL:
#   https://docs.google.com/spreadsheets/d/<SHEET_ID>/edit
SHEET_ID: str = "1eCgxl3xVJQXdhPDultBo5i7PbCu57KXsahc1YwBYBmw"

# Tab/worksheet name inside the spreadsheet
WORKSHEET_NAME: str = "Sheet1"

# Where to save the merged CSV
OUT_CSV = Path("data/tv_alerts.csv")

# ─── COLUMN MAP ───────────────────────────────────────────────────────────────
# Maps raw Google Sheet header → internal name used by the dashboard.
# Adjust if your headers differ.
COLUMN_MAP = {
    "Date":       "date",
    "Ticker":     "symbol",
    "Price":      "price",
    "Column 1":   "bar_time",
    "Alert Type": "alert_type",
}

# ─── FETCH ────────────────────────────────────────────────────────────────────

def _build_service():
    """Build an authenticated Google Sheets API service object."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        raise ImportError(
            "Missing Google client libraries.\n"
            "Run:  pip install google-auth google-auth-httplib2 google-api-python-client"
        )

    key_path = Path(SERVICE_ACCOUNT_JSON)
    if not key_path.exists():
        raise FileNotFoundError(
            f"Service account key not found at: {key_path.resolve()}\n"
            "Set SERVICE_ACCOUNT_JSON env var or update the constant in this file."
        )

    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds  = service_account.Credentials.from_service_account_file(
        str(key_path), scopes=scopes
    )
    service = build("sheets", "v4", credentials=creds, cache_discovery=False)
    return service


def fetch_alerts(sheet_id: str = SHEET_ID,
                 worksheet: str = WORKSHEET_NAME) -> pd.DataFrame:
    """
    Pull all rows from the Google Sheet and return a cleaned DataFrame.
    Merges with any existing local data so no rows are lost between runs.
    """
    service  = _build_service()
    sheet    = service.spreadsheets()
    range_   = f"{worksheet}!A:Z"   # grab everything; we'll filter by header

    log.info(f"Fetching from sheet {sheet_id} / {worksheet} …")
    result = sheet.values().get(spreadsheetId=sheet_id, range=range_).execute()
    values = result.get("values", [])

    if not values:
        log.warning("Sheet appears to be empty.")
        return pd.DataFrame()

    headers = values[0]
    rows    = values[1:]

    if not rows:
        log.warning("Sheet has headers but no data rows.")
        return pd.DataFrame(columns=headers)

    # Pad short rows (Google omits trailing empty cells)
    rows = [r + [""] * (len(headers) - len(r)) for r in rows]

    df = pd.DataFrame(rows, columns=headers)
    log.info(f"  Raw rows fetched: {len(df)}")

    # ── Rename columns ────────────────────────────────────────────────────────
    df.rename(columns=COLUMN_MAP, inplace=True)

    # ── Parse / clean ─────────────────────────────────────────────────────────
    # Date column: "08/05/2026 14:45:18"
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")

    # bar_time: ISO 8601 UTC
    if "bar_time" in df.columns:
        df["bar_time"] = pd.to_datetime(df["bar_time"], utc=True, errors="coerce")

    # price: numeric
    if "price" in df.columns:
        df["price"] = pd.to_numeric(df["price"], errors="coerce")

    # symbol: upper-strip
    if "symbol" in df.columns:
        df["symbol"] = df["symbol"].str.upper().str.strip()

    # Drop rows with no symbol or no date
    df.dropna(subset=["symbol"], inplace=True)
    df = df[df["symbol"] != ""]

    log.info(f"  Clean rows: {len(df)}")
    return df.reset_index(drop=True)


# ─── SAVE (merge with existing) ───────────────────────────────────────────────

def save(df: pd.DataFrame, out_csv: Path = OUT_CSV) -> pd.DataFrame:
    """
    Merge freshly fetched data with any previously saved CSV so we keep
    historical alerts even if the sheet is trimmed.
    """
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    if out_csv.exists():
        try:
            existing = pd.read_csv(out_csv, parse_dates=["date", "bar_time"])
            combined = pd.concat([existing, df], ignore_index=True)
            # De-duplicate on (date, symbol, alert_type, price)
            dedup_cols = [c for c in ["date", "symbol", "alert_type", "price"]
                          if c in combined.columns]
            combined.drop_duplicates(subset=dedup_cols, keep="last", inplace=True)
            log.info(f"  Merged with existing — total unique rows: {len(combined)}")
        except Exception as e:
            log.warning(f"Could not read existing CSV ({e}); overwriting.")
            combined = df
    else:
        combined = df

    combined.sort_values("date", ascending=False, inplace=True)
    combined.to_csv(out_csv, index=False)
    log.info(f"Saved → {out_csv}  ({len(combined)} rows)")
    return combined


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch TradingView alerts from Google Sheets")
    parser.add_argument("--tail", type=int, default=0,
                        help="Print last N rows after saving (0 = silent)")
    parser.add_argument("--sheet-id",   default=SHEET_ID,      help="Google Sheet ID")
    parser.add_argument("--worksheet",  default=WORKSHEET_NAME, help="Tab name")
    args = parser.parse_args()

    df      = fetch_alerts(sheet_id=args.sheet_id, worksheet=args.worksheet)
    combined = save(df)

    if args.tail > 0 and not combined.empty:
        print(f"\nLatest {args.tail} alerts:\n")
        print(combined.head(args.tail).to_string(index=False))

    print(f"\nDone — {len(combined)} total alerts in {OUT_CSV}")


if __name__ == "__main__":
    main()