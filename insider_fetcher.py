from datetime import date, timedelta
from io import StringIO
from urllib.parse import urlencode
from utils import (
    clean_insider_data,
    build_insider_summary,
    insider_score
)
import pandas as pd
import requests


BASE_URL = "https://trendlyne.com/equity/group-insider-trading-sast/"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def build_url(start_date=None, end_date=None, hide_small_qty=True):
    end_date = end_date or date.today()
    start_date = start_date or (end_date - timedelta(days=7))

    params = {
        "deal-type": "-1",
        "trans-type": "all",
        "start-date": pd.to_datetime(start_date).strftime("%Y-%m-%d"),
        "end-date": pd.to_datetime(end_date).strftime("%Y-%m-%d"),
    }
    if hide_small_qty:
        params["hide-small-qty"] = "on"

    return f"{BASE_URL}?{urlencode(params)}"




def fetch_insider_data(start_date=None, end_date=None, hide_small_qty=True):
    url = build_url(start_date, end_date, hide_small_qty)
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()

    tables = pd.read_html(StringIO(response.text))
    if not tables:
        return pd.DataFrame()

    return clean_insider_data(tables[0])







def main():
    df = fetch_insider_data(
        start_date=date.today() - timedelta(days=3),
        end_date=date.today(),
    )
    summary = build_insider_summary(df)
    from pathlib import Path

    INSIDER_FILE = Path(
        "data/insider_trades.parquet"
    )

    INSIDER_FILE.parent.mkdir(
        exist_ok=True
    )

    df.to_parquet(
        INSIDER_FILE,
        index=False
    )

    print(
        f"Saved {len(df)} rows to "
        f"{INSIDER_FILE}"
    )

    print(f"Rows found: {len(df)}")
    print("\nTop rows")
    print(df.head())

    print("\nRows by action")
    print(summary["action_counts"])

    print("\nValue by action")
    print(summary["value_by_action"].map(lambda value: f"{value:,.0f}"))

    print("\nRows by client category")
    print(summary["category_counts"])

    print("\nNet disclosed buy/sell value by stock")
    print(summary["net_by_stock"].head(10).map(lambda value: f"{value:,.0f}"))

    print("\nTop 10 stocks by disclosed transaction value")
    print(summary["value_by_stock"].head(10).map(lambda value: f"{value:,.0f}"))

    print("\nTop 10 stocks by traded quantity")
    print(summary["quantity_by_stock"].head(10).map(lambda value: f"{value:,.0f}"))

    print("\nTop 10 individual disclosed transactions by value")
    cols = [
        "stock",
        "client_name",
        "client_category",
        "action",
        "quantity",
        "avg_price",
        "value",
        "mode",
    ]
    print(summary["top_transactions"][[c for c in cols if c in df.columns]].head(10).to_string(index=False))


if __name__ == "__main__":
    main()
