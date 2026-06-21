from pathlib import Path
import pandas as pd

DATA_DIR = Path("data")

files = sorted(
    DATA_DIR.glob("EPS YOY AND QOQ_*.csv"),
    key=lambda x: x.stat().st_mtime,
    reverse=True
)

if not files:
    raise FileNotFoundError(
        "No TradingView CSV found"
    )

latest_csv = files[0]

print(f"Using: {latest_csv.name}")

df = pd.read_csv(latest_csv)

df.to_parquet(
    DATA_DIR / "tradingview_growth.parquet",
    index=False
)

print(df.shape)
print("Parquet updated")
