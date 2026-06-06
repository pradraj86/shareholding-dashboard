"""
nsdl_fpi_fetcher.py
───────────────────
Scrapes NSDL Fortnightly Sector-wise FPI Investment data from static HTML files.

No Playwright / Selenium needed. NSDL publishes each fortnight as a plain
static HTML file at a predictable URL:

  https://www.fpi.nsdl.co.in/web/StaticReports/
      Fortnightly_Sector_wise_FII_Investment_Data/
      FIIInvestSector_{Mon}{Day}{Year}.html

e.g.  FIIInvestSector_Apr302026.html   (April 30, 2026)
      FIIInvestSector_Apr152026.html   (April 15, 2026)

Files are published on the 15th and last calendar day of each month.
This script generates candidate URLs, fetches the ones that exist (200),
and parses the data table.

Table columns (confirmed from NSDL):
  Sector | Net Investment (₹Cr) | AUC (₹Cr) | % of Total AUC

Output
------
  data/nsdl_fpi_sector.csv        long-format: sector | date | net_inv_cr | auc_cr | pct_of_total
  data/nsdl_fpi_sector_wide.csv   wide pivot : rows=sector, cols=dates

Usage
-----
  pip install requests pandas beautifulsoup4 lxml

  python nsdl_fpi_fetcher.py                   # last 12 fortnights
  python nsdl_fpi_fetcher.py --fortnights 6
  python nsdl_fpi_fetcher.py --all             # every fortnight since 2012
  python nsdl_fpi_fetcher.py --debug           # print raw HTML of latest file
"""

import argparse
import calendar
import logging
import time
from datetime import date
from pathlib import Path

import requests
import pandas as pd
from bs4 import BeautifulSoup

# ─── CONFIG ───────────────────────────────────────────────────────────────────

BASE_URL = (
    "https://www.fpi.nsdl.co.in/web/StaticReports/"
    "Fortnightly_Sector_wise_FII_Investment_Data/"
)

OUT_DIR  = Path("data")
OUT_LONG = OUT_DIR / "nsdl_fpi_sector.csv"
OUT_WIDE = OUT_DIR / "nsdl_fpi_sector_wide.csv"

DEFAULT_FORTNIGHTS = 12
DELAY              = 0.8   # seconds between requests — be polite
MAX_RETRIES        = 2

MONTHS = ["Jan","Feb","Mar","Apr","May","Jun",
          "Jul","Aug","Sep","Oct","Nov","Dec"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ─── URL GENERATION ───────────────────────────────────────────────────────────

def fortnightly_dates(start_year: int = 2012) -> list[date]:
    """
    Generate every fortnightly date from start_year to today.
    NSDL publishes on the 15th and last calendar day of each month.
    """
    today  = date.today()
    result = []
    for year in range(start_year, today.year + 1):
        for month in range(1, 13):
            if date(year, month, 1) > today:
                break
            last = calendar.monthrange(year, month)[1]
            for day in [15, last]:
                d = date(year, month, day)
                if d <= today:
                    result.append(d)
    return result


def date_to_url(d: date) -> str:
    mon = MONTHS[d.month - 1]
    return f"{BASE_URL}FIIInvestSector_{mon}{d.day}{d.year}.html"


def date_to_label(d: date) -> str:
    """Human-readable label: '30-Apr-2026'"""
    return f"{d.day:02d}-{MONTHS[d.month-1]}-{d.year}"


# ─── HTTP SESSION ─────────────────────────────────────────────────────────────

def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
        "Referer": "https://www.fpi.nsdl.co.in/",
    })
    return s


def fetch_html(session: requests.Session, url: str) -> str | None:
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            r = session.get(url, timeout=15)
            if r.status_code == 200 and len(r.text) > 500:
                return r.text
            elif r.status_code == 404:
                return None   # file doesn't exist for this date
            else:
                log.debug(f"HTTP {r.status_code} for {url} (attempt {attempt})")
                time.sleep(1)
        except requests.RequestException as e:
            log.debug(f"Request error (attempt {attempt}): {e}")
            time.sleep(1)
    return None


# ─── TABLE PARSER ─────────────────────────────────────────────────────────────

def _to_float(raw: str) -> float | None:
    """
    Handles NSDL formatting:
      - Commas in numbers: "1,23,456"
      - Negative in brackets: "(1,234)"
      - Percentage: "12.34%"
      - Dashes for zero/null: "-" or "--"
    """
    s = raw.strip().replace(",", "").replace("%", "").replace("₹", "")
    if s in ("-", "--", "", "N.A.", "NA", "n.a."):
        return None
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return None


# def parse_html(html: str, period_label: str) -> list[dict]:
    # """
    # Parse one NSDL static HTML report page.

    # NSDL table structure (consistent across years):
      # Row 0: title / header spanning all columns
      # Row 1: column headers — typically:
               # "Sector" | "Net Inv. (Rs. Cr.)" | "AUC (Rs. Cr.)" | "% to Total"
               # (older files may have slightly different header text)
      # Row 2+: data rows — one per sector, last row = "Total"

    # Returns list of dicts: sector | date | net_inv_cr | auc_cr | pct_of_total
    # """
    # soup = BeautifulSoup(html, "lxml")

    # # Find the main data table — largest table with sector rows
    # best_table = None
    # best_rows  = 0
    # for tbl in soup.find_all("table"):
        # rows = tbl.find_all("tr")
        # if len(rows) > best_rows:
            # best_rows  = len(rows)
            # best_table = tbl

    # if not best_table or best_rows < 3:
        # log.warning(f"No usable table found for {period_label}")
        # return []

    # rows = best_table.find_all("tr")

    # # ── Detect header row ─────────────────────────────────────────────────────
    # # Find the first row where the first cell looks like "Sector" / "Industry"
    # header_idx = None
    # for i, row in enumerate(rows):
        # cells = [td.get_text(strip=True) for td in row.find_all(["th", "td"])]
        # first = cells[0].lower() if cells else ""
        # if "sector" in first or "industry" in first or "segment" in first:
            # header_idx = i
            # break

    # if header_idx is None:
        # log.warning(f"Could not find header row for {period_label}")
        # return []

    # headers = [td.get_text(strip=True) for td in rows[header_idx].find_all(["th", "td"])]
    # log.debug(f"{period_label} headers: {headers}")

    # # Map column indices
    # col_sector  = 0
    # col_net_inv = None
    # col_auc     = None
    # col_pct     = None

    # for i, h in enumerate(headers):
        # hl = h.lower()
        # if i == 0:
            # continue
        # if "auc" in hl:
            # col_auc = i
        # elif "%" in hl or "percent" in hl or "ratio" in hl:
            # col_pct = i
        # elif col_net_inv is None:   # first numeric column after sector = net investment
            # col_net_inv = i

    # # Fallback: assign by position if header matching failed
    # if col_net_inv is None and len(headers) >= 2:
        # col_net_inv = 1
    # if col_auc is None and len(headers) >= 3:
        # col_auc = 2
    # if col_pct is None and len(headers) >= 4:
        # col_pct = 3

    # # ── Parse data rows ───────────────────────────────────────────────────────
    # records = []
    # for row in rows[header_idx + 1:]:
        # cells = [td.get_text(strip=True) for td in row.find_all(["th", "td"])]
        # if not cells or len(cells) < 2:
            # continue

        # sector = cells[col_sector].strip()

        # # Skip empty, header-repeat, total, and footnote rows
        # if not sector:
            # continue
        # if sector.lower() in ("total", "grand total", "sector", "industry"):
            # continue
        # if sector.startswith("Note") or sector.startswith("*") or sector.startswith("#"):
            # continue
        # # Skip rows where the sector cell is a number (malformed row)
        # if _to_float(sector) is not None:
            # continue

        # def _get(col):
            # return _to_float(cells[col]) if col is not None and col < len(cells) else None

        # records.append({
            # "sector":       sector,
            # "date":         period_label,
            # "net_inv_cr":   _get(col_net_inv),
            # "auc_cr":       _get(col_auc),
            # "pct_of_total": _get(col_pct),
        # })

    # return records

def parse_html(html: str, period_label: str) -> list[dict]:
    """
    Robust parser for NSDL FPI sector HTML pages.
    Handles old and new NSDL table formats.
    """

    soup = BeautifulSoup(html, "lxml")

    tables = soup.find_all("table")

    if not tables:
        log.warning(f"No tables found for {period_label}")
        return []

    best_table = None
    best_score = 0

    # Find table most likely containing sector data
    for tbl in tables:
        rows = tbl.find_all("tr")

        score = 0

        for row in rows[:10]:
            text = row.get_text(" ", strip=True).lower()

            if "sector" in text:
                score += 5

            if "auc" in text:
                score += 5

            if "net" in text:
                score += 5

            if "%" in text:
                score += 3

        if score > best_score:
            best_score = score
            best_table = tbl

    if best_table is None:
        log.warning(f"No suitable table found for {period_label}")
        return []

    rows = best_table.find_all("tr")

    header_idx = None
    headers = []

    # Detect header row
    for i, row in enumerate(rows):

        cells = [
            td.get_text(" ", strip=True)
            for td in row.find_all(["td", "th"])
        ]

        joined = " ".join(cells).lower()

        if (
            "sector" in joined
            or "auc" in joined
            or "net" in joined
        ):
            header_idx = i
            headers = cells
            break

    if header_idx is None:
        log.warning(f"Could not find header row for {period_label}")
        return []

    log.debug(f"{period_label} headers: {headers}")

    col_sector = 0
    col_net_inv = None
    col_auc = None
    col_pct = None

    for i, h in enumerate(headers):

        hl = h.lower()

        if "auc" in hl:
            col_auc = i

        elif "%" in hl or "percent" in hl:
            col_pct = i

        elif "net" in hl or "investment" in hl:
            col_net_inv = i

    # fallback positions
    if col_net_inv is None:
        col_net_inv = 1

    if col_auc is None:
        col_auc = 2

    if col_pct is None:
        col_pct = 3

    records = []

    for row in rows[header_idx + 1:]:

        cells = [
            td.get_text(" ", strip=True)
            for td in row.find_all(["td", "th"])
        ]

        if len(cells) < 2:
            continue

        sector = cells[col_sector].strip()

        if not sector:
            continue

        sl = sector.lower()

        if sl in (
            "total",
            "grand total",
            "sector",
            "industry"
        ):
            continue

        if sector.startswith("Note"):
            continue

        if _to_float(sector) is not None:
            continue

        def _get(col):
            if col is None:
                return None

            if col >= len(cells):
                return None

            return _to_float(cells[col])

        rec = {
            "sector": sector,
            "date": period_label,
            "net_inv_cr": _get(col_net_inv),
            "auc_cr": _get(col_auc),
            "pct_of_total": _get(col_pct),
        }

        # skip fully empty rows
        if (
            rec["net_inv_cr"] is None
            and rec["auc_cr"] is None
            and rec["pct_of_total"] is None
        ):
            continue

        records.append(rec)

    return records
# ─── MAIN SCRAPER ─────────────────────────────────────────────────────────────

def scrape(n_fortnights: int = DEFAULT_FORTNIGHTS,
           scrape_all: bool = False) -> pd.DataFrame:
    """
    Generate candidate URLs, fetch ones that exist, parse and combine.
    Works from newest to oldest so we collect the most recent data first.
    """
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    all_dates = fortnightly_dates()             # oldest → newest
    candidates = list(reversed(all_dates))      # newest → oldest

    if not scrape_all:
        candidates = candidates[:n_fortnights * 2]  # over-fetch in case some 404

    session    = make_session()
    all_records: list[dict] = []
    collected  = 0
    target     = None if scrape_all else n_fortnights

    log.info(f"Fetching {'all' if scrape_all else f'last {n_fortnights}'} fortnights "
             f"from {len(candidates)} candidate dates")

    for d in candidates:
        if target and collected >= target:
            break

        url   = date_to_url(d)
        label = date_to_label(d)
        html  = fetch_html(session, url)

        if html is None:
            log.debug(f"  {label}: not found (404 or error)")
            time.sleep(0.2)
            continue

        records = parse_html(html, label)
        if records:
            all_records.extend(records)
            collected += 1
            log.info(f"  ✓ {label}: {len(records)} sectors")
        else:
            log.warning(f"  ✗ {label}: page found but no data rows parsed")

        time.sleep(DELAY)

    if not all_records:
        log.error("No data collected. Check your internet connection.")
        return pd.DataFrame()

    df = pd.DataFrame(all_records)
    df = df.drop_duplicates(subset=["sector", "date"])

    # Sort dates chronologically for output
    def _date_sort_key(label: str) -> int:
        months = {m: i+1 for i, m in enumerate(MONTHS)}
        parts  = label.split("-")   # "30-Apr-2026"
        try:
            return int(parts[2]) * 10000 + months.get(parts[1], 0) * 100 + int(parts[0])
        except (IndexError, ValueError):
            return 0

    df["_sort"] = df["date"].map(_date_sort_key)
    df = df.sort_values(["_sort", "sector"]).drop(columns="_sort")

    log.info(f"\nDone: {df['date'].nunique()} periods | {df['sector'].nunique()} sectors | {len(df)} rows")
    return df


# ─── SAVE ─────────────────────────────────────────────────────────────────────

def save(df: pd.DataFrame):
    if df.empty:
        log.error("Nothing to save.")
        return

    # Long format
    df.to_csv(OUT_LONG, index=False)
    log.info(f"Long CSV → {OUT_LONG}")

    # Wide pivot: net investment per sector per date
    try:
        pivot = df.pivot_table(
            index="sector", columns="date", values="net_inv_cr", aggfunc="first"
        )
        # Sort columns chronologically
        def _key(label):
            months = {m: i+1 for i, m in enumerate(MONTHS)}
            parts  = label.split("-")
            try:
                return int(parts[2]) * 10000 + months.get(parts[1], 0) * 100 + int(parts[0])
            except:
                return 0
        pivot = pivot[sorted(pivot.columns, key=_key)]
        pivot.to_csv(OUT_WIDE)
        log.info(f"Wide CSV → {OUT_WIDE}")
    except Exception as e:
        log.warning(f"Wide pivot failed: {e}")

    # Print latest period summary
    latest = df[df["date"] == df["date"].iloc[-1]].copy()
    latest = latest.sort_values("net_inv_cr", ascending=False)
    print(f"\n{'='*60}")
    print(f"Latest period: {df['date'].iloc[-1]}")
    print(f"{'='*60}")
    print(f"{'Sector':<35} {'Net Inv (₹Cr)':>15} {'AUC (₹Cr)':>14} {'% Total':>8}")
    print("-" * 75)
    for _, row in latest.iterrows():
        net = f"{row['net_inv_cr']:>15,.2f}" if pd.notna(row['net_inv_cr']) else f"{'—':>15}"
        auc = f"{row['auc_cr']:>14,.2f}"     if pd.notna(row['auc_cr'])     else f"{'—':>14}"
        pct = f"{row['pct_of_total']:>8.2f}" if pd.notna(row['pct_of_total']) else f"{'—':>8}"
        print(f"{row['sector']:<35} {net} {auc} {pct}")


# ─── DEBUG ────────────────────────────────────────────────────────────────────

def debug_latest():
    """Fetch and print raw HTML of the most recent available file."""
    session   = make_session()
    all_dates = list(reversed(fortnightly_dates()))
    for d in all_dates[:10]:
        url  = date_to_url(d)
        html = fetch_html(session, url)
        if html:
            print(f"\nFound: {date_to_label(d)}")
            print(f"URL:   {url}")
            print(f"Length: {len(html)} chars")
            soup  = BeautifulSoup(html, "lxml")
            tables = soup.find_all("table")
            print(f"Tables in page: {len(tables)}")
            for i, tbl in enumerate(tables):
                rows = tbl.find_all("tr")
                print(f"\n  Table {i} — {len(rows)} rows:")
                for row in rows[:8]:
                    cells = [td.get_text(strip=True) for td in row.find_all(["td","th"])]
                    print(f"    {cells}")
            return
    print("No recent file found.")


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch NSDL Fortnightly Sector-wise FPI data (no browser needed)"
    )
    parser.add_argument(
        "--fortnights", type=int, default=DEFAULT_FORTNIGHTS,
        help=f"Number of recent fortnights to fetch (default: {DEFAULT_FORTNIGHTS})"
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Fetch all fortnights since 2012 (~340 files, takes ~5 mins)"
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Print raw HTML structure of the latest available file"
    )
    args = parser.parse_args()

    if args.debug:
        debug_latest()
    else:
        df = scrape(n_fortnights=args.fortnights, scrape_all=args.all)
        save(df)