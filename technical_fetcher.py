import pandas as pd
import numpy as np
import yfinance as yf
import pandas_ta as ta
from pathlib import Path

WATCHLIST = "watchlist.txt"
OUTFILE = "data/technicals_all.parquet"
def load_watchlist():

    syms = []

    with open(WATCHLIST, "r") as f:

        for line in f:

            line = line.strip()

            if line.startswith("NSE:"):
                syms.append(
                    line.replace("NSE:", "")
                )

    return sorted(set(syms))

def technical_score(row):

    score = 0

    if row["close"] > row["ema200"]:
        score += 20

    if row["close"] > row["ema50"]:
        score += 15

    if row["ema50"] > row["ema200"]:
        score += 15

    if 50 <= row["rsi14"] <= 70:
        score += 10

    if row["macd"] > row["macd_signal"]:
        score += 10

    if row["relative_volume"] > 1.5:
        score += 10

    if row["pct_from_high"] > -15:
        score += 20

    return score
def entry_status(score, rsi, close, ema200):

    if close < ema200:
        return "AVOID"

    if rsi > 75:
        return "WAIT_PULLBACK"

    if score >= 80:
        return "BUY_NOW"

    if score >= 60:
        return "WATCH"

    return "AVOID"

def fetch_symbol(sym):

    tv_symbol = f"{sym}.NS"

    try:

        df = yf.download(
            tv_symbol,
            period="18mo",
            auto_adjust=True,
            progress=False
        )

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if len(df) < 220:
            return None

        close = df["Close"]

        ema20 = ta.ema(close, length=20)
        ema50 = ta.ema(close, length=50)
        ema200 = ta.ema(close, length=200)

        rsi = ta.rsi(close, length=14)

        macd = ta.macd(close)
        
        latest_close = float(close.iloc[-1])

        latest_ema20 = float(ema20.iloc[-1])
        latest_ema50 = float(ema50.iloc[-1])
        latest_ema200 = float(ema200.iloc[-1])

        latest_rsi = float(rsi.iloc[-1])

        macd_col = macd.columns[0]     # MACD
        signal_col = macd.columns[2]   # MACDs

        latest_macd = float(
            macd[macd_col].iloc[-1]
        )

        latest_signal = float(
            macd[signal_col].iloc[-1]
        )
        high52 = float(close.tail(252).max())

        pct_from_high = (
            latest_close / high52 - 1
        ) * 100

        vol20 = (
            df["Volume"]
            .tail(20)
            .mean()
        )

        rel_vol = (
            df["Volume"].iloc[-1]
            / vol20
        )

        row = {

            "symbol": sym,

            "close": latest_close,

            "ema20": latest_ema20,
            "ema50": latest_ema50,
            "ema200": latest_ema200,

            "rsi14": latest_rsi,

            "macd": latest_macd,
            "macd_signal": latest_signal,

            "relative_volume": rel_vol,

            "pct_from_high": pct_from_high
        }

        row["technical_score"] = (
            technical_score(row)
        )

        row["entry_status"] = (
            entry_status(
                row["technical_score"],
                latest_rsi,
                latest_close,
                latest_ema200
            )
        )
        print(
    sym,
    row["technical_score"],
    row["entry_status"]
)
        return row

    except Exception as e:

        print(sym, e)

        return None
    

def run():

    symbols = load_watchlist()

    rows = []

    for idx, sym in enumerate(symbols, start=1):

        print(
            f"{idx}/{len(symbols)} {sym}"
        )
        if idx % 25 == 0:
            print(
                f"Processed {idx}/{len(symbols)}"
            )
        r = fetch_symbol(sym)

        if r:
            rows.append(r)

    tech = pd.DataFrame(rows)

    tech.to_parquet(
        OUTFILE,
        index=False
    )

    print(tech.head())

if __name__ == "__main__":
    run()       