from pathlib import Path

# ─────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────

BASE_DIR = Path(r"D:\Pradeep\Project\shareholding")

DELETE_LIST_FILE = BASE_DIR / "delete.txt"

TARGET_FOLDERS = [
    BASE_DIR / r"data\cashflow_screener",
    BASE_DIR / r"data\financials_screener",
    BASE_DIR / r"data\shareholding_screener",
    BASE_DIR / r"data\corporate_actions_screener",
]

# ─────────────────────────────────────────────
# FILE PREFIX MAP
# ─────────────────────────────────────────────

PREFIX_MAP = {
    "cashflow_screener": "cashflow_",
    "financials_screener": "financials_",
    "shareholding_screener": "shareholding_",
    "corporate_actions_screener": "corporate_actions_",
}

# ─────────────────────────────────────────────
# READ STOCK LIST
# ─────────────────────────────────────────────

if not DELETE_LIST_FILE.exists():
    print(f"delete.txt not found: {DELETE_LIST_FILE}")
    raise SystemExit

stocks = []

with open(DELETE_LIST_FILE, "r", encoding="utf-8") as f:

    for line in f:

        symbol = line.strip().upper()

        if symbol:
            stocks.append(symbol)

print(f"\nLoaded {len(stocks)} symbols from delete.txt")

# ─────────────────────────────────────────────
# DELETE FILES
# ─────────────────────────────────────────────

deleted = 0
missing = 0

for folder in TARGET_FOLDERS:

    folder_name = folder.name

    prefix = PREFIX_MAP.get(folder_name)

    if not prefix:
        continue

    print(f"\nChecking folder: {folder}")

    for symbol in stocks:

        file_path = folder / f"{prefix}{symbol}.parquet"

        if file_path.exists():

            try:

                file_path.unlink()

                print(f"Deleted: {file_path.name}")

                deleted += 1

            except Exception as e:

                print(f"ERROR deleting {file_path.name}: {e}")

        else:

            print(f"Missing: {file_path.name}")

            missing += 1

# ─────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────

print("\n" + "=" * 60)
print("DELETE SUMMARY")
print("=" * 60)

print(f"Deleted files : {deleted}")
print(f"Missing files : {missing}")
print("=" * 60)