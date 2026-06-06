# brokerage_research.py

from io import StringIO
from pathlib import Path
from datetime import datetime
import time
import random

import pandas as pd
import requests
from bs4 import BeautifulSoup


# ─────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────

BASE_URL = "https://trendlyne.com/research-reports/all/"

OUT_FILE = Path("data/brokerage_reports.parquet")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}


# ─────────────────────────────────────────────────────────────
# Session
# ─────────────────────────────────────────────────────────────

def make_session():

    s = requests.Session()

    s.headers.update(HEADERS)

    return s


# ─────────────────────────────────────────────────────────────
# Fetch Page
# ─────────────────────────────────────────────────────────────

def fetch_page(session, page=1):

    url = f"{BASE_URL}?page={page}"

    # print(f"Fetching: {url}")

    r = session.get(
        url,
        timeout=30,
    )

    r.raise_for_status()

    return r.text


# ─────────────────────────────────────────────────────────────
# Parse Table
# ─────────────────────────────────────────────────────────────

def parse_reports(html):

    tables = pd.read_html(StringIO(html))

    if not tables:
        return pd.DataFrame()

    df = tables[0].copy()

    return df


# ─────────────────────────────────────────────────────────────
# Normalize Columns
# ─────────────────────────────────────────────────────────────

def normalize_columns(df):

    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.lower()
        .str.replace(r"[^a-z0-9]+", "_", regex=True)
        .str.strip("_")
    )

    return df


# ─────────────────────────────────────────────────────────────
# Clean Data
# ─────────────────────────────────────────────────────────────

def clean_data(df):

    if df.empty:
        return df

    df = normalize_columns(df)

    rename_map = {}

    for c in df.columns:

        lc = c.lower()

        if "stock" in lc:
            rename_map[c] = "symbol"

        elif "broker" in lc:
            rename_map[c] = "broker"

        elif "rating" in lc or "call" in lc:
            rename_map[c] = "rating"

        elif "target" in lc:
            rename_map[c] = "target_price"

        elif "cmp" in lc or "price" in lc:
            rename_map[c] = "cmp"

        elif "upside" in lc:
            rename_map[c] = "upside_pct"

        elif "date" in lc:
            rename_map[c] = "date"

    df.rename(columns=rename_map, inplace=True)

    # ── Cleanup ─────────────────────────────────────────────

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

    # Add fetch timestamp
    df["fetched_at"] = datetime.now()

    return df.reset_index(drop=True)


# ─────────────────────────────────────────────────────────────
# Fetch Multiple Pages
# ─────────────────────────────────────────────────────────────

def fetch_all_reports(
    pages=5,
    delay=(1, 3),
):

    session = make_session()

    frames = []

    for page in range(1, pages + 1):

        try:

            html = fetch_page(
                session,
                page=page,
            )

            df = parse_reports(html)

            df = clean_data(df)

            if not df.empty:

                frames.append(df)

                # print(
                    # f"Page {page}: "
                    # f"{len(df)} rows"
                # )

            sleep_time = random.uniform(
                delay[0],
                delay[1],
            )

            time.sleep(sleep_time)

        except Exception as e:

            print(
                f"Page {page} failed: {e}"
            )

    if not frames:
        return pd.DataFrame()

    out = pd.concat(
        frames,
        ignore_index=True
    )

    out = out.drop_duplicates()

    return out.reset_index(drop=True)


# ─────────────────────────────────────────────────────────────
# Save
# ─────────────────────────────────────────────────────────────

def save_data(df):

    if df.empty:

        # print("No data found")

        return

    OUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.to_parquet(
        OUT_FILE,
        index=False,
    )

    print(
        f"Saved {len(df)} rows → {OUT_FILE}"
    )


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

def main():

    df = fetch_all_reports(
        pages=10,
    )

    if df.empty:

        # print("No reports fetched")

        return

    # print("\nColumns:")
    # print(df.columns.tolist())

    # print("\nSample:")
    # print(df.head())

    save_data(df)

    
if __name__ == "__main__":

    main()


