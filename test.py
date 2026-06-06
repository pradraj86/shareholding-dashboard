import pandas as pd

df = pd.read_parquet("data/brokerage_reports.parquet")

print(
    df[["symbol","target_price"]]
    .head(20)
    .to_string()
)