import pandas as pd

bulk = pd.read_csv(
    "Bulk-Deals-07-03-2026-to-07-06-2026.csv"
)

block = pd.read_csv(
    "Block-Deals-07-03-2026-to-07-06-2026.csv"
)

bulk.columns = bulk.columns.str.strip()
block.columns = block.columns.str.strip()

bulk["Trade_Value"] = (
    pd.to_numeric(
        bulk["Quantity Traded"],
        errors="coerce"
    )
    *
    pd.to_numeric(
        bulk["Trade Price / Wght. Avg. Price"],
        errors="coerce"
    )
)

block["Trade_Value"] = (
    pd.to_numeric(
        block["Quantity Traded"],
        errors="coerce"
    )
    *
    pd.to_numeric(
        block["Trade Price / Wght. Avg. Price"],
        errors="coerce"
    )
)

bulk["Date"] = pd.to_datetime(
    bulk["Date"],
    format="%d-%b-%Y",
    errors="coerce"
)

block["Date"] = pd.to_datetime(
    block["Date"],
    format="%d-%b-%Y",
    errors="coerce"
)

bulk.to_parquet(
    "data/bulk_deals.parquet",
    index=False
)

block.to_parquet(
    "data/block_deals.parquet",
    index=False
)

print("Bulk rows:", len(bulk))
print("Block rows:", len(block))