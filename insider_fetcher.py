from datetime import date, timedelta
from io import StringIO
from urllib.parse import urlencode

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


def normalize_columns(df):
    df = df.copy()
    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.lower()
        .str.replace(r"[^a-z0-9]+", "_", regex=True)
        .str.strip("_")
    )
    return df


def clean_insider_data(df):
    df = normalize_columns(df)

    if "quantity" in df.columns:
        df["quantity"] = pd.to_numeric(
            df["quantity"].astype(str).str.replace(",", "", regex=False),
            errors="coerce",
        )

    if "value" in df.columns:
        df["value"] = pd.to_numeric(
            df["value"]
            .astype(str)
            .str.replace(",", "", regex=False)
            .str.replace("-", "", regex=False),
            errors="coerce",
        )

    if "traded" in df.columns:
        df["traded_pct"] = pd.to_numeric(
            df["traded"]
            .astype(str)
            .str.replace("%", "", regex=False)
            .str.replace("-", "", regex=False),
            errors="coerce",
        )

    if {"action", "value"}.issubset(df.columns):
        df["signed_value"] = 0.0
        df.loc[df["action"].eq("Acquisition"), "signed_value"] = df.loc[
            df["action"].eq("Acquisition"), "value"
        ].fillna(0)
        df.loc[df["action"].eq("Disposal"), "signed_value"] = -df.loc[
            df["action"].eq("Disposal"), "value"
        ].fillna(0)

    return df


def fetch_insider_data(start_date=None, end_date=None, hide_small_qty=True):
    url = build_url(start_date, end_date, hide_small_qty)
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()

    tables = pd.read_html(StringIO(response.text))
    if not tables:
        return pd.DataFrame()

    return clean_insider_data(tables[0])


def build_insider_summary(df):
    if df.empty:
        return {
            "action_counts": pd.Series(dtype="int64"),
            "value_by_action": pd.Series(dtype="float64"),
            "category_counts": pd.Series(dtype="int64"),
            "net_by_stock": pd.Series(dtype="float64"),
            "value_by_stock": pd.Series(dtype="float64"),
            "quantity_by_stock": pd.Series(dtype="float64"),
            "top_transactions": pd.DataFrame(),
            "top_traded_pct": pd.DataFrame(),
        }

    value_col = "value" if "value" in df.columns else None
    quantity_col = "quantity" if "quantity" in df.columns else None

    return {
        "action_counts": df["action"].value_counts()
        if "action" in df.columns
        else pd.Series(dtype="int64"),
        "value_by_action": df.groupby("action", dropna=False)[value_col].sum().sort_values(ascending=False)
        if value_col and "action" in df.columns
        else pd.Series(dtype="float64"),
        "category_counts": df["client_category"].value_counts()
        if "client_category" in df.columns
        else pd.Series(dtype="int64"),
        "net_by_stock": df[df["action"].isin(["Acquisition", "Disposal"])]
        .groupby("stock", dropna=False)["signed_value"]
        .sum()
        .sort_values(ascending=False)
        if {"stock", "action", "signed_value"}.issubset(df.columns)
        else pd.Series(dtype="float64"),
        "value_by_stock": df.groupby("stock", dropna=False)[value_col].sum().sort_values(ascending=False)
        if value_col and "stock" in df.columns
        else pd.Series(dtype="float64"),
        "quantity_by_stock": df.groupby("stock", dropna=False)[quantity_col].sum().sort_values(ascending=False)
        if quantity_col and "stock" in df.columns
        else pd.Series(dtype="float64"),
        "top_transactions": df.sort_values("value", ascending=False).head(20)
        if "value" in df.columns
        else df.head(20),
        "top_traded_pct": df.sort_values("traded_pct", ascending=False).head(20)
        if "traded_pct" in df.columns
        else df.head(20),
    }


def insider_score(row):
    score = 0

    if "Promoter" in str(row.get("client_category", "")):
        score += 3
    if row.get("action") == "Acquisition":
        score += 4
    if row.get("quantity", 0) > 100000:
        score += 2
    if row.get("value", 0) > 10000000:
        score += 2

    return score


def main():
    df = fetch_insider_data(
        start_date=date.today() - timedelta(days=3),
        end_date=date.today(),
    )
    summary = build_insider_summary(df)

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
