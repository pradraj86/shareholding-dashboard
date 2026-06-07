from pathlib import Path
import pandas as pd
import requests
import io
import logging

# =====================================================
# FOLDERS
# =====================================================

DATA_DIR = Path("data")
LOG_DIR = Path("logs")

DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

BULK_FILE = DATA_DIR / "bulk_deals.parquet"
BLOCK_FILE = DATA_DIR / "block_deals.parquet"

# =====================================================
# LOGGING
# =====================================================

logging.basicConfig(
    filename=LOG_DIR / "bulk_block.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

log = logging.getLogger(__name__)

# =====================================================
# NSE URLS
# =====================================================

BULK_URL = (
    "https://nsearchives.nseindia.com/content/equities/bulk.csv"
)

BLOCK_URL = (
    "https://nsearchives.nseindia.com/content/equities/block.csv"
)

HEADERS = {
    "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

# =====================================================
# DOWNLOAD CSV
# =====================================================

def download_csv(url):

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        if response.status_code != 200:

            log.warning(
                f"HTTP {response.status_code}: {url}"
            )

            return None

        df = pd.read_csv(
            io.StringIO(response.text)
        )

        # Clean column names
        df.columns = (
            df.columns
            .str.strip()
            .str.replace(r"\s*/\s*", "/", regex=True)
        )

        return df

    except Exception as e:

        log.exception(
            f"Download failed: {url}"
        )

        print(e)

        return None


# =====================================================
# ADD TRADE VALUE
# =====================================================

def add_trade_value(df):

    if df is None or df.empty:
        return df

    df["Quantity Traded"] = (
        df["Quantity Traded"]
        .astype(str)
        .str.replace(",", "", regex=False)
    )

    price_col = "Trade Price/Wght. Avg. Price"

    df[price_col] = (
        df[price_col]
        .astype(str)
        .str.replace(",", "", regex=False)
    )

    df["Quantity Traded"] = pd.to_numeric(
        df["Quantity Traded"],
        errors="coerce"
    )

    df[price_col] = pd.to_numeric(
        df[price_col],
        errors="coerce"
    )

    df["Trade_Value"] = (
        df["Quantity Traded"]
        *
        df[price_col]
    )

    return df


# =====================================================
# APPEND TO PARQUET
# =====================================================

def append_parquet(new_df, parquet_file):

    if new_df is None or new_df.empty:
        return

    new_df = normalize_bulk_block_columns(
        new_df
    )

    if parquet_file.exists():

        old_df = pd.read_parquet(
            parquet_file
        )

        old_df = normalize_bulk_block_columns(
            old_df
        )

        combined = pd.concat(
            [old_df, new_df],
            ignore_index=True
        )

    else:

        combined = new_df.copy()

    # -------------------------------------------------
    # Remove duplicates
    # -------------------------------------------------

    dedupe_cols = [
        c for c in [
            "Date",
            "Symbol",
            "Client Name",
            "Buy/Sell",
            "Quantity Traded",
            "Trade Price/Wght. Avg. Price"
        ]
        if c in combined.columns
    ]

    combined = combined.drop_duplicates(
        subset=dedupe_cols,
        keep="last"
    )

    # -------------------------------------------------
    # Sort by Date
    # -------------------------------------------------

    if "Date" in combined.columns:

        combined["Date"] = pd.to_datetime(
            combined["Date"],
            format="%d-%b-%Y",
            errors="coerce"
        )

        combined = combined.sort_values(
            "Date",
            ascending=False
        )
    for col in [
    "Quantity Traded",
    "Trade Price/Wght. Avg. Price",
    "Trade_Value"
]:

        if col in combined.columns:

            combined[col] = (
                combined[col]
                .astype(str)
                .str.replace(",", "", regex=False)
            )

            combined[col] = pd.to_numeric(
                combined[col],
                errors="coerce"
            )
    combined.to_parquet(
        parquet_file,
        index=False
    )

    log.info(
        f"{parquet_file.name} saved "
        f"({len(combined)} rows)"
    )


def normalize_bulk_block_columns(df):

    if df is None or df.empty:
        return df

    df = df.copy()

    df.columns = (
        df.columns
        .astype(str)
        .str.strip()
        .str.replace(r"\s*/\s*", "/", regex=True)
    )

    if df.columns.has_duplicates:

        merged = {}

        for col in pd.Index(df.columns).unique():

            matching = df.loc[:, df.columns == col]

            if matching.shape[1] == 1:

                merged[col] = matching.iloc[:, 0]

            else:

                merged[col] = matching.bfill(axis=1).iloc[:, 0]

        df = pd.DataFrame(
            merged,
            index=df.index
        )

    return df


# =====================================================
# MAIN
# =====================================================

def main():

    print(
        "\nRefreshing NSE Bulk/Block Deals...\n"
    )

    log.info(
        "========== START =========="
    )

    today = pd.Timestamp.today().date()

    # =================================================
    # BULK DEALS
    # =================================================

    bulk_df = download_csv(
        BULK_URL
    )

    if bulk_df is not None and not bulk_df.empty:

        bulk_df["Download_Date"] = today
        bulk_df["Source"] = "Bulk"

        bulk_df = add_trade_value(
            bulk_df
        )

        print(
            f"Bulk rows downloaded: "
            f"{len(bulk_df)}"
        )

        append_parquet(
            bulk_df,
            BULK_FILE
        )

        log.info(
            f"Bulk downloaded: "
            f"{len(bulk_df)} rows"
        )

    else:

        print(
            "Bulk file unavailable"
        )

        log.info(
            "Bulk file unavailable"
        )

    # =================================================
    # BLOCK DEALS
    # =================================================

    block_df = download_csv(
        BLOCK_URL
    )

    if block_df is not None and not block_df.empty:

        block_df["Download_Date"] = today
        block_df["Source"] = "Block"

        block_df = add_trade_value(
            block_df
        )

        print(
            f"Block rows downloaded: "
            f"{len(block_df)}"
        )

        append_parquet(
            block_df,
            BLOCK_FILE
        )

        log.info(
            f"Block downloaded: "
            f"{len(block_df)} rows"
        )

    else:

        print(
            "Block file unavailable"
        )

        log.info(
            "Block file unavailable"
        )

    log.info(
        "========== END =========="
    )

    print(
        "\nBulk/Block Refresh Completed.\n"
    )


# =====================================================
# ENTRY
# =====================================================

if __name__ == "__main__":

    main()
