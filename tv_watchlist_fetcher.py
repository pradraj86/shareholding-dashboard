"""
tv_watchlist_fetcher.py
───────────────────────
Reads TradingView watchlist export .txt files and saves structured CSVs
for the Streamlit dashboard.

HOW TO EXPORT FROM TRADINGVIEW
───────────────────────────────
1. Open TradingView and go to your watchlist:
   • TV BLUE LIST : https://in.tradingview.com/watchlists/97730743/
   • TV GREEN LIST: https://in.tradingview.com/watchlists/101052775/
2. Click ⋮ (three-dot menu) next to the watchlist name
3. Click "Export watchlist" → a .txt file downloads
4. Rename and save in same folder as this script:
       tv_blue_list.txt
       tv_green_list.txt
5. Run: python tv_watchlist_fetcher.py

Output:
    data/tv_blue_list.csv
    data/tv_green_list.csv
    data/tv_watchlists.csv   ← combined
"""

import argparse
import logging
import re
from pathlib import Path
import pandas as pd

BLUE_LIST_FILE  = Path("tv_blue_list.txt")
GREEN_LIST_FILE = Path("tv_green_list.txt")
OUT_DIR      = Path("data")
OUT_BLUE     = OUT_DIR / "tv_blue_list.csv"
OUT_GREEN    = OUT_DIR / "tv_green_list.csv"
OUT_COMBINED = OUT_DIR / "tv_watchlists.csv"
TV_BASE_URL  = "https://in.tradingview.com/chart/?symbol="
BLUE_LIST_TV_URL  = "https://in.tradingview.com/watchlists/97730743/"
GREEN_LIST_TV_URL = "https://in.tradingview.com/watchlists/101052775/"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def parse_tv_export(filepath: Path, list_name: str) -> pd.DataFrame:
    if not filepath.exists():
        log.warning(f"[{list_name}] File not found: {filepath}")
        log.warning("  → Export from TradingView (⋮ menu → Export watchlist) and save here.")
        return pd.DataFrame(columns=["symbol","exchange","full_symbol","tv_link","list_name"])

    records, seen = [], set()
    for line in filepath.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("###"):
            continue
        for part in [p.strip() for p in line.split(",") if p.strip()]:
            if not part or part.startswith("###"):
                continue
            if ":" in part:
                exchange, sym = part.split(":", 1)
                exchange, sym = exchange.strip().upper(), sym.strip().upper()
            else:
                sym, exchange = re.sub(r"[^A-Z0-9&]", "", part.upper()), "NSE"
            if not sym:
                continue
            full_symbol = f"{exchange}:{sym}"
            if full_symbol in seen:
                continue
            seen.add(full_symbol)
            records.append({
                "symbol":      sym,
                "exchange":    exchange,
                "full_symbol": full_symbol,
                "tv_link":     f"{TV_BASE_URL}{exchange}%3A{sym}",
                "list_name":   list_name,
            })

    df = pd.DataFrame(records)
    log.info(f"[{list_name}] Parsed {len(df)} symbols")
    return df


# def run(blue_file=BLUE_LIST_FILE, green_file=GREEN_LIST_FILE):
#     OUT_DIR.mkdir(parents=True, exist_ok=True)
#     df_blue  = parse_tv_export(Path(blue_file),  "TV BLUE LIST")
#     df_green = parse_tv_export(Path(green_file), "TV GREEN LIST")

#     for df, path, name in [
#         (df_blue,  OUT_BLUE,  "TV BLUE LIST"),
#         (df_green, OUT_GREEN, "TV GREEN LIST"),
#     ]:
#         if not df.empty:
#             path.parent.mkdir(parents=True, exist_ok=True)
#             df.to_csv(path, index=False)
#             log.info(f"Saved {len(df)} rows → {path}")

#     frames = [df for df in [df_blue, df_green] if not df.empty]
#     if frames:
#         combined = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["full_symbol","list_name"])
#         combined.to_csv(OUT_COMBINED, index=False)
#         log.info(f"Combined: {len(combined)} rows → {OUT_COMBINED}")
#     else:
        # print("""
# No data foWATCHLIST_FILE = Path(r"D:\Pradeep\Project\shareholding\watchlist.txt")
WATCHLIST_FILE = Path(r"D:\Pradeep\Project\shareholding\watchlist.txt")

def run(blue_file=BLUE_LIST_FILE, green_file=GREEN_LIST_FILE):

    df_blue  = parse_tv_export(Path(blue_file),  "TV BLUE LIST")
    df_green = parse_tv_export(Path(green_file), "TV GREEN LIST")

    frames = [df for df in [df_blue, df_green] if not df.empty]

    if not frames:
        print("""
No data found. Please:
  1. Export TradingView watchlists
  2. Save as:
        tv_blue_list.txt
        tv_green_list.txt
  3. Run script again.
""")
        return

    # Combine both lists
    combined = (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(subset=["symbol"])
        .sort_values("symbol")
    )

    # Write symbols one per line
    WATCHLIST_FILE.write_text(
        "\n".join(combined["symbol"].astype(str)),
        encoding="utf-8"
    )

    log.info(f"Saved {len(combined)} symbols → {WATCHLIST_FILE}")

    print(f"✅ Watchlist updated: {len(combined)} symbols")

    return combined

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--blue",  default=str(BLUE_LIST_FILE))
    parser.add_argument("--green", default=str(GREEN_LIST_FILE))
    args = parser.parse_args()
    run(args.blue, args.green)